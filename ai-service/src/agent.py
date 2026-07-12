import os
import re
from typing import TypedDict, Optional
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_groq import ChatGroq
from langchain_community.embeddings import JinaEmbeddings
from langchain_mongodb import MongoDBAtlasVectorSearch
from pymongo import MongoClient
from langgraph.graph import StateGraph, END

MAX_RETRIES = 2
RELEVANCE_SCORE_THRESHOLD = 0.3  # Cosine similarity — chunks below this are filtered out

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    question: str           # Current (possibly rewritten) question
    original_question: str  # The user's original question — never mutated
    generation: str         # Final LLM answer
    documents: list         # Retrieved Document objects
    retry_count: int        # How many times we've rewritten and retried
    is_relevant: bool       # Whether grade_documents found the chunks useful
    chat_history: list      # List of BaseMessage objects (prior turns)
    sources: list[str]      # Source file paths used in generation

# ---------------------------------------------------------------------------
# Keyword helpers for smart routing inside retrieve
# ---------------------------------------------------------------------------

STRUCTURAL_KEYWORDS = [
    "structure", "summary", "directory", "files", "overview",
    "project", "repo", "repository", "what is this", "explain this repo",
    "codebase", "architecture", "layout", "folders"
]

FILE_EXTENSION_PATTERN = re.compile(
    r'\b[\w\-]+\.(py|js|jsx|ts|tsx|md|txt|json|yaml|yml|html|css|env)\b',
    re.IGNORECASE
)

def is_structural_query(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in STRUCTURAL_KEYWORDS)

def extract_mentioned_filename(question: str) -> str | None:
    match = FILE_EXTENSION_PATTERN.search(question)
    return match.group(0) if match else None

# ---------------------------------------------------------------------------
# LLM / Vectorstore factories
# ---------------------------------------------------------------------------

def get_llm():
    """Create LLM at call time to ensure env vars are loaded."""
    return ChatGroq(
        model_name="llama-3.1-8b-instant",
        groq_api_key=os.environ.get("GROQ_API_KEY")
    )

def get_vectorstore():
    mongo_uri = os.environ.get("MONGO_URI")
    client = MongoClient(mongo_uri)
    collection = client["codebase_rag"]["vectors"]
    embeddings = JinaEmbeddings(
        jina_api_key=os.environ.get("JINA_API_KEY"),
        model_name="jina-embeddings-v3"
    )
    return MongoDBAtlasVectorSearch(
        collection=collection,
        embedding=embeddings,
        index_name="default",
        relevance_score_fn="cosine"
    )

# ---------------------------------------------------------------------------
# Node 1: retrieve
# ---------------------------------------------------------------------------

def retrieve(state: GraphState) -> GraphState:
    question = state["question"]
    vectorstore = get_vectorstore()

    # Priority 1: Structural query → fetch the directory tree document
    if is_structural_query(question):
        try:
            results = vectorstore.similarity_search(
                query=question,
                k=3,
                pre_filter={"metadata.type": {"$eq": "structure"}}
            )
            if results:
                print("[retrieve] Structural query — using directory_tree document")
                return {**state, "documents": results}
        except Exception:
            pass

    # Priority 2: File-specific query → filter by filename in source path
    filename = extract_mentioned_filename(question)
    if filename:
        try:
            results = vectorstore.similarity_search(
                query=question,
                k=20,  # Grab plenty of chunks to cover the whole file
                pre_filter={"source": {"$regex": re.escape(filename), "$options": "i"}}
            )
            if results:
                print(f"[retrieve] File-specific query — filtered to '{filename}' ({len(results)} chunks)")
                return {**state, "documents": results}
        except Exception:
            pass

    # Default: Similarity search with score — filter out weak matches
    try:
        results_with_scores = vectorstore.similarity_search_with_score(query=question, k=12)
        filtered = [
            doc for doc, score in results_with_scores
            if score >= RELEVANCE_SCORE_THRESHOLD
        ]
        print(f"[retrieve] Score-filtered: {len(filtered)}/{len(results_with_scores)} chunks above threshold {RELEVANCE_SCORE_THRESHOLD}")
        documents = filtered if filtered else [doc for doc, _ in results_with_scores]
    except Exception:
        # Fallback: plain similarity search without scores
        retriever = vectorstore.as_retriever(search_kwargs={"k": 12})
        documents = retriever.invoke(question)

    return {**state, "documents": documents}

# ---------------------------------------------------------------------------
# Node 2: grade_documents — REAL grading with LLM
# ---------------------------------------------------------------------------

def grade_documents(state: GraphState) -> GraphState:
    question = state["question"]
    documents = state["documents"]

    if not documents:
        print("[grade] No documents — marking as not relevant")
        return {**state, "is_relevant": False}

    context_preview = "\n\n".join([doc.page_content[:800] for doc in documents[:8]])

    grade_prompt = f"""You are a relevance grader. Given a user question and code/text chunks from a repository, 
determine if the chunks contain enough information to meaningfully answer the question.

Respond with ONLY "yes" or "no".

Question: {question}

Chunks:
{context_preview}

Are these chunks relevant and sufficient to answer the question? (yes/no):"""

    llm = get_llm()
    result = llm.invoke([HumanMessage(content=grade_prompt)])
    verdict = result.content.strip().lower()
    is_relevant = verdict.startswith("yes")

    print(f"[grade] Verdict: {'RELEVANT ✓' if is_relevant else 'NOT RELEVANT ✗'} (raw: '{verdict}')")
    return {**state, "is_relevant": is_relevant}

# ---------------------------------------------------------------------------
# Node 3: rewrite_query — generate a better search query
# ---------------------------------------------------------------------------

def rewrite_query(state: GraphState) -> GraphState:
    original = state["original_question"]
    retry_count = state.get("retry_count", 0)

    rewrite_prompt = f"""You are a query optimizer for a code search system that retrieves source code chunks from a GitHub repository.

The original question failed to retrieve useful code chunks. Rewrite it to be more effective for semantic code search.

Guidelines:
- Use technical terms and code-specific language
- Mention likely file names, function names, or patterns that might appear in the code
- Keep it concise (1–2 sentences max)
- Do NOT add explanations — return ONLY the rewritten query

Original question: {original}
Attempt number: {retry_count + 1}

Rewritten query:"""

    llm = get_llm()
    result = llm.invoke([HumanMessage(content=rewrite_prompt)])
    new_question = result.content.strip()

    print(f"[rewrite] Attempt {retry_count + 1}: '{original}' → '{new_question}'")
    return {**state, "question": new_question, "retry_count": retry_count + 1}

# ---------------------------------------------------------------------------
# Node 4: generate — answer with memory + source attribution
# ---------------------------------------------------------------------------

def generate(state: GraphState) -> GraphState:
    question = state["original_question"]
    documents = state["documents"]
    chat_history = state.get("chat_history", [])

    # Build context + collect sources
    context_parts = []
    sources = set()
    for doc in documents:
        context_parts.append(doc.page_content)
        src = doc.metadata.get("source", "")
        if src and src != "directory_tree":
            sources.add(os.path.basename(src))

    context = "\n\n".join(context_parts)

    # Build conversation history string
    history_str = ""
    if chat_history:
        turns = []
        for msg in chat_history[-20:]:  # Last 10 exchanges (20 messages)
            if isinstance(msg, HumanMessage):
                turns.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                turns.append(f"Assistant: {msg.content}")
        history_str = "\n".join(turns)

    history_section = f"""
Previous conversation (for context only — do not repeat it):
{history_str}

""" if history_str else ""

    prompt = f"""You are an expert software developer analyzing a real codebase.
The context below is ACTUAL source code retrieved from the repository.
{history_section}Answer the question based STRICTLY on the provided code context.
- Be direct and specific — do not say "it may" or "it might", state what the code DOES.
- Quote specific function names, variables, and logic from the context.
- If the context is insufficient to answer fully, say so clearly — do not guess.
- If prior conversation is provided, use it to understand follow-up questions.

Question: {question}

Code Context:
{context}

Answer:"""

    llm = get_llm()
    response = llm.invoke([HumanMessage(content=prompt)])

    return {
        **state,
        "generation": response.content,
        "sources": sorted(list(sources))
    }

# ---------------------------------------------------------------------------
# Conditional edge: decide_to_generate
# ---------------------------------------------------------------------------

def decide_to_generate(state: GraphState) -> str:
    """
    If chunks are relevant → generate.
    If not relevant and retries remain → rewrite and retry.
    If not relevant and retries exhausted → generate anyway (graceful degradation).
    """
    if state.get("is_relevant", False):
        print("[router] Chunks are relevant — proceeding to generate")
        return "generate"

    retry_count = state.get("retry_count", 0)
    if retry_count < MAX_RETRIES:
        print(f"[router] Chunks not relevant — rewriting query (attempt {retry_count + 1}/{MAX_RETRIES})")
        return "rewrite_query"

    print(f"[router] Max retries ({MAX_RETRIES}) reached — generating from best available context")
    return "generate"

# ---------------------------------------------------------------------------
# Build LangGraph
# ---------------------------------------------------------------------------

workflow = StateGraph(GraphState)

workflow.add_node("retrieve", retrieve)
workflow.add_node("grade_documents", grade_documents)
workflow.add_node("rewrite_query", rewrite_query)
workflow.add_node("generate", generate)

workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "grade_documents")
workflow.add_conditional_edges(
    "grade_documents",
    decide_to_generate,
    {
        "generate": "generate",
        "rewrite_query": "rewrite_query",
    }
)
workflow.add_edge("rewrite_query", "retrieve")   # Loop back
workflow.add_edge("generate", END)

app = workflow.compile()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_agent(
    question: str,
    chat_history: Optional[list[BaseMessage]] = None,
) -> dict:
    """
    Run the self-healing RAG agent.

    Args:
        question:     The user's current question.
        chat_history: List of BaseMessage objects representing prior turns.

    Returns:
        dict with keys: generation (str), sources (list[str]), retry_count (int)
    """
    inputs: GraphState = {
        "question": question,
        "original_question": question,
        "generation": "",
        "documents": [],
        "retry_count": 0,
        "is_relevant": False,
        "chat_history": chat_history or [],
        "sources": [],
    }

    final_state = None
    for output in app.stream(inputs):
        for key, value in output.items():
            final_state = value

    return {
        "generation": final_state.get("generation", ""),
        "sources": final_state.get("sources", []),
        "retry_count": final_state.get("retry_count", 0),
    }
