# Polyglot Agentic Codebase RAG Application

This monorepo contains a Codebase RAG application using React, Node.js/Express, MongoDB Atlas, and Python (FastAPI) + LangGraph.

## Architecture

1. **Frontend**: React (Vite) + Tailwind CSS
2. **API Gateway**: Node.js/Express + MongoDB for state/history
3. **AI Service**: Python (FastAPI) + LangGraph + MongoDB Atlas Vector Search

## Setup Instructions

1. Copy `.env.example` to `.env` in the root directory and fill in your keys.
2. In MongoDB Atlas, create a Search Index on your vector collection using the schema in `atlas_search_index.json`.
3. Start the AI Service (Python):
   ```bash
   cd ai-service
   pip install -r requirements.txt
   uvicorn src.main:app --reload
   ```
4. Start the API Gateway (Node.js):
   ```bash
   cd api-gateway
   npm install
   npm run dev
   ```
5. Start the Frontend (React):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
