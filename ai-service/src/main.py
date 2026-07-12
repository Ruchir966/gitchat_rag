from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())  # Searches parent directories for .env

from src.ingest import process_github_repo
from src.agent import run_agent
from langchain_core.messages import HumanMessage, AIMessage

app = FastAPI(title="Codebase RAG AI Service")


class IngestRequest(BaseModel):
    repo_url: str


class ChatMessage(BaseModel):
    role: str   # "user" or "ai"
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    chat_history: Optional[list[ChatMessage]] = []


@app.post("/agent/ingest")
async def ingest_repo(request: IngestRequest):
    try:
        result = process_github_repo(request.repo_url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/chat")
async def chat(request: ChatRequest):
    try:
        # Convert chat_history dicts → LangChain message objects
        lc_history = []
        for msg in (request.chat_history or []):
            if msg.role == "user":
                lc_history.append(HumanMessage(content=msg.content))
            elif msg.role in ("ai", "assistant"):
                lc_history.append(AIMessage(content=msg.content))

        result = run_agent(
            question=request.message,
            chat_history=lc_history,
        )

        return {
            "answer": result["generation"],
            "sources": result["sources"],
            "retry_count": result["retry_count"],
            "session_id": request.session_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("src.main:app", host="0.0.0.0", port=port)
