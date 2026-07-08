from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv()) # Searches parent directories for .env

from src.ingest import process_github_repo
from src.agent import run_agent

app = FastAPI(title="Codebase RAG AI Service")

class IngestRequest(BaseModel):
    repo_url: str

class ChatRequest(BaseModel):
    message: str

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
        answer = run_agent(request.message)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
