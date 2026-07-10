import os
import re
from typing import TypedDict
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq
from langchain_community.embeddings import JinaEmbeddings
from langchain_mongodb import MongoDBAtlasVectorSearch
from pymongo import MongoClient
from langgraph.graph import StateGraph, END

# Define State
class GraphState(TypedDict):
    question: str
    generation: str
    documents: list[str]

# Keywords that signal the user wants project-level structural context
STRUCTURAL_KEYWORDS = [
    "structure", "summary", "directory", "files", "overview",
    "project", "repo", "repository", "what is this", "explain this repo",
    "codebase", "architecture", "layout", "folders"
]

# Regex to detect filenames like agent.py, main.js, App.tsx etc. in a question
FILE_EXTENSION_PATTERN = re.compile(
    r'\b[\w\-]+\.(py|js|jsx|ts|tsx|md|txt|json|yaml|yml|html|css|env)\b',
    re.IGNORECASE
)

def is_structural_query(question: str) -> bool:
    """Return True if the question is asking about the repo at a high level."""
    q = question.lower()
    return any(kw in q for kw in STRUCTURAL_KEYWORDS)

def extract_mentioned_filename(question: str) -> str | None:
    """
    Detect if the user is asking about a specific file (e.g. 'agent.py', 'main.js').
    Returns the filename string if found, else None.
    """
    match = FILE_EXTENSION_PATTERN.search(question)
    return match.group(0) if match else None

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

def retrieve(state: GraphState):
    question = state["question"]
    vectorstore = get_vectorstore()

    # --- Priority 1: Structural query → fetch the directory tree document ---
    if is_structural_query(question):
        try:
            results = vectorstore.similarity_search(
                query=question,
                k=1,
                pre_filter={"metadata.type": {"$eq": "structure"}}
            )
            if results:
                print("[retrieve] Structural query — using directory_tree document")
                return {"documents": results, "question": question}
        except Exception:
            pass  # pre_filter not supported or tree doc missing — fall through

    # --- Priority 2: File-specific query → filter by filename in source path ---
    filename = extract_mentioned_filename(question)
    if filename:
        try:
            results = vectorstore.similarity_search(
                query=question,
                k=8,  # Grab more chunks to cover the whole file
                pre_filter={"source": {"$regex": re.escape(filename), "$options": "i"}}
            )
            if results:
                print(f"[retrieve] File-specific query — filtered to '{filename}' ({len(results)} chunks)")
                return {"documents": results, "question": question}
        except Exception:
            pass  # pre_filter not supported — fall through to generic search

    # --- Default: Generic similarity search ---
    retriever = vectorstore.as_retriever(search_kwargs={"k": 6})
    documents = retriever.invoke(question)
    return {"documents": documents, "question": question}

def grade_documents(state: GraphState):
    question = state["question"]
    documents = state["documents"]
    # Pass all retrieved chunks through
    return {"documents": documents, "question": question}

def generate(state: GraphState):
    question = state["question"]
    documents = state["documents"]

    context = "\n\n".join([doc.page_content for doc in documents])

    prompt = f"""You are an expert software developer analyzing a real codebase.
The context below is the ACTUAL source code retrieved from the repository.
Answer the question based STRICTLY on the provided code context.
- Be direct and specific — do not say "it may" or "it might", state what the code DOES.
- Quote specific function names, variables, and logic from the context.
- If the context is insufficient to answer fully, say so clearly — do not guess.

Question: {question}

Code Context:
{context}

Answer:"""

    llm = get_llm()
    response = llm.invoke([HumanMessage(content=prompt)])

    return {"documents": documents, "question": question, "generation": response.content}

# Build Graph
workflow = StateGraph(GraphState)

workflow.add_node("retrieve", retrieve)
workflow.add_node("grade_documents", grade_documents)
workflow.add_node("generate", generate)

workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "grade_documents")
workflow.add_edge("grade_documents", "generate")
workflow.add_edge("generate", END)

app = workflow.compile()

def run_agent(question: str):
    inputs = {"question": question}
    for output in app.stream(inputs):
        for key, value in output.items():
            pass
    return value["generation"]
