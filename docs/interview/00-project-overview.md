# 00 — Project Overview: GitChat RAG

> **Read this first before any interview.** This is the "30,000-foot view" you need to answer
> "Tell me about a project you've worked on" without rambling.

---

## What Is This?

**GitChat RAG** is a full-stack AI application that lets a user point at any public GitHub repository
and have a natural-language conversation with the codebase. You ask questions like
*"How does authentication work?"* or *"What does the ingest pipeline do?"* and the system
retrieves the actual source code chunks that answer your question, feeds them to an LLM,
and responds with cited, grounded answers — not hallucinated guesses.

**Core Users:** Developers who need to quickly understand an unfamiliar codebase.

---

## Feature List (What It Actually Does)

| Feature | Description |
|---|---|
| **Repo Ingestion** | Clone any public GitHub repo, chunk the source files, embed them via Jina AI, store in MongoDB Atlas Vector Search |
| **Conversational Q&A** | Multi-turn chat with full conversation memory per session |
| **Self-Correcting Retrieval** | If the first vector search returns irrelevant chunks, the system automatically rewrites the query and retries (up to 2 times) |
| **Smart Retrieval Routing** | Three retrieval strategies: structural queries, file-specific queries, and scored similarity search |
| **Source Attribution** | Every AI answer shows which files the answer was derived from |
| **Retry Transparency** | The UI shows a badge when the system had to rephrase your query |
| **Directory Tree Awareness** | Questions about project structure use a pre-indexed directory snapshot |

---

## Architecture: The 3-Service Model

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (React + Vite)                  │
│  Dashboard.jsx          ──►      ChatRoom.jsx               │
│  (repo URL input)               (chat interface)            │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP / axios (localhost:3000)
                         ▼
┌────────────────────────────────────────────────────────────┐
│              API Gateway  (Node.js / Express)              │
│                                                            │
│  POST /api/repo/submit   →  proxy to AI service            │
│  POST /api/chat/message  →  fetch history + proxy + save   │
│  GET  /api/chat/history  →  return raw history             │
│                                                            │
│  MongoDB Atlas ◄─ ChatHistory model (Mongoose)             │
└────────────────────────┬───────────────────────────────────┘
                         │ HTTP / axios (localhost:8000)
                         ▼
┌────────────────────────────────────────────────────────────┐
│               AI Service  (Python / FastAPI)               │
│                                                            │
│  POST /agent/ingest  →  ingest.py pipeline                 │
│  POST /agent/chat    →  LangGraph RAG agent                │
│                                                            │
│  ┌──────────── LangGraph Graph ─────────────────────────┐  │
│  │  retrieve → grade → [rewrite → retrieve]* → generate │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  MongoDB Atlas Vector Search  ◄─  Jina Embeddings (1024d) │
│  Groq LLM (llama-3.1-8b-instant)                          │
└────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

### AI Service (Python)
| Technology | Version/Model | Why |
|---|---|---|
| **FastAPI** | latest | Async HTTP server for the AI service |
| **LangGraph** | latest | State machine for the self-correcting RAG loop |
| **LangChain** | latest | Document loaders, text splitters, vectorstore abstraction |
| **Jina AI** | `jina-embeddings-v3` | 1024-dim code-aware embeddings, free tier |
| **Groq** | `llama-3.1-8b-instant` | Fast, cheap LLM inference |
| **MongoDB Atlas Vector Search** | cosine, 1024d | Combined vector store + chat DB in one service |
| **GitPython** | latest | Programmatic git clone |

### API Gateway (Node.js)
| Technology | Why |
|---|---|
| **Express** | Minimal HTTP layer, routing |
| **Mongoose** | MongoDB ODM with schema validation + index definition |
| **Axios** | HTTP client for proxying to AI service |

### Frontend (React)
| Technology | Why |
|---|---|
| **React + Vite** | Fast HMR dev experience |
| **Tailwind CSS** | Rapid utility-class styling |
| **ReactMarkdown** | Renders LLM markdown responses in the chat UI |
| **Lucide React** | Icon set |

### Infrastructure
| Component | Choice |
|---|---|
| **Database** | MongoDB Atlas (cloud-hosted, dual-use: vector store + relational history) |
| **Deployment** | Local dev only (3 processes: Vite, Node, Uvicorn) |

---

## Data Flow: Happy Path (One Chat Turn)

```
1. User types question in ChatRoom.jsx
2. POST /api/chat/message { repo_url, message, session_id }
3. API Gateway fetches last 10 exchanges from MongoDB (sorted by created_at)
4. API Gateway forwards { message, chat_history, session_id } to AI service
5. AI service: retrieve() — 3-tier vector search
6. AI service: grade_documents() — LLM relevance check
7.   If relevant → generate()
8.   If not → rewrite_query() → retrieve() → grade() → generate()
9. AI service returns { answer, sources, retry_count }
10. API Gateway saves exchange to MongoDB ChatHistory collection
11. API Gateway returns { answer, sources, retry_count, session_id } to frontend
12. ChatRoom renders answer as Markdown + source badges
```

---

## Resume Summary (Say This Out Loud)

> *"I built a full-stack RAG application that lets developers chat with any GitHub repository.
> The interesting part is the AI layer — I used LangGraph to build a self-correcting retrieval
> loop where if the first vector search returns irrelevant chunks, the system automatically
> rewrites the query with code-search-optimized language and retries, up to two times.
> I also implemented smart retrieval routing that detects structural queries and file-specific
> queries before falling back to scored similarity search. The backend is split between a
> Node.js API gateway that handles chat history in MongoDB and a Python FastAPI service
> that owns all the AI logic — embeddings via Jina AI, inference via Groq, and vector
> storage in MongoDB Atlas."*

**One sentence version:**
> *"I built a RAG system with a self-correcting LangGraph retrieval loop that automatically
> rewrites bad queries and retries, backed by MongoDB Atlas for both vector storage and
> chat history."*
