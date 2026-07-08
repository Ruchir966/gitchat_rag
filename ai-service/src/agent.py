import os
from typing import Dict, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage
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
    retriever = vectorstore.as_retriever()
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

    prompt = f"""You are an expert software developer and architect. 
    Use the following pieces of retrieved codebase context to answer the question. 
    If you don't know the answer, just say that you don't know. 
    
    Question: {question} 
    Context: {context} 
    
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
