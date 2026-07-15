# Interviewer Notes — GitChat RAG

> **This is the meta-document.** Read this BEFORE every interview session.
> It tells you where to spend your prep time and what to skip.

---

## SECTION 1: Things the Interviewer WILL Definitely Ask

These topics have one thing in common: they represent non-trivial decisions with real tradeoffs.
Any engineer who has read the JD for "backend" or "ML engineer" roles will zero in on these.

---

### 🔴 CRITICAL — Must Know Cold

#### 1. "Why LangGraph? What does it give you over a plain function chain?"

**What they're really asking:** Do you understand stateful orchestration vs. simple pipelines?

**Your answer core:** LangGraph models the RAG loop as a directed graph with typed state (`GraphState`). The critical thing it enables is the **conditional retry loop** — `grade_documents` decides whether to call `rewrite_query` or `generate`, and `rewrite_query` loops back to `retrieve`. A plain `if/else` chain in a Python function would work for 2 nodes, but breaks down when you need to add more decision points without refactoring everything. LangGraph also makes the state immutable per node (each node returns a new copy via `{**state, ...}`) — this prevents hard-to-debug mutation bugs.

**Gotcha they'll ask:** *"Isn't this overkill for a 4-node graph?"* Answer: Yes, for this scale. The payoff comes when you add nodes like `hallucination_grader` or `web_search_fallback` without touching existing node logic.

---

#### 2. "Explain the retrieval strategy. Why three tiers?"

**What they're really asking:** Did you just call `.similarity_search()` or did you think about the failure modes?

**The three tiers (exact code):**
- **Tier 1 (Structural):** Keywords like "structure", "directory", "overview" → pre-filter by `metadata.type == "structure"` → returns the directory tree doc
- **Tier 2 (File-specific):** Question mentions a filename like `agent.py` → regex pre-filter on `source` field → `k=20` to get all chunks from that file
- **Tier 3 (Default):** `similarity_search_with_score()` → filter by `RELEVANCE_SCORE_THRESHOLD = 0.3` → fallback to unfiltered if all scores below threshold

**Why they'd push back:** *"How did you pick 0.3 as the threshold?"* Honest answer: empirically. Cosine similarity in this embedding space — chunks below 0.3 were nearly always noise. You could make it configurable.

---

#### 3. "How does chat memory work? Walk me through the full lifecycle."

**The lifecycle:**
1. Frontend generates `session_id = crypto.randomUUID()` — stored in `useRef` (survives renders, not page refresh)
2. `POST /api/chat/message` sends `{ message, repo_url, session_id }`
3. API Gateway queries MongoDB: `ChatHistory.find({ repo_url, session_id }).sort({ created_at: -1 }).limit(10)` → reverses to chronological order
4. Constructs `[{role: 'user', content}, {role: 'ai', content}, ...]` flat list
5. Sends to AI service which converts to LangChain `HumanMessage`/`AIMessage` objects
6. `generate()` node injects history into prompt as a formatted conversation string, capped at last 20 messages
7. After AI responds, API Gateway saves the exchange as a new `ChatHistory` document

**Why cap at 10 exchanges?** Token budget. `llama-3.1-8b-instant` has an 8K context window. 10 exchanges + retrieved chunks + system prompt ≈ fills it without overflow.

---

#### 4. "What's the compound index for? Why those three fields?"

**Answer:** `{ repo_url: 1, session_id: 1, created_at: 1 }` is built for one query:
```javascript
ChatHistory.find({ repo_url, session_id }).sort({ created_at: -1 }).limit(10)
```
MongoDB can satisfy this query entirely from the index — it filters on the two equality fields first (reducing the scan), then sorts on `created_at` in the same index traversal (no separate sort step). Without this index, MongoDB does a full collection scan for every chat message sent.

**Tradeoff:** Write amplification — every insert into `ChatHistory` also writes to this index. Acceptable because reads outnumber writes and the history query is on the hot path.

---

#### 5. "Why is ingest synchronous? What breaks if a large repo times out?"

**Current reality (from the code):**
- `POST /api/repo/submit` → `axios.post(AI_SERVICE_URL + '/agent/ingest')` — no timeout set
- If the repo is large, the HTTP connection stays open for 60–300 seconds
- The browser's 30s default timeout will fire → user sees a 500 error even though ingest continues
- No way for the user to know if ingest completed or failed

**What you'd do next:** Move ingest to a background job queue (BullMQ or Celery), return a job ID immediately, poll or webhook the status back. This is the canonical "sync → async" evolution.

---

#### 6. "Walk me through what happens when a query fails twice."

**Exact flow:**
1. `retrieve()` — similarity search, returns weak chunks
2. `grade_documents()` — LLM says "no" → `is_relevant = False`
3. `decide_to_generate()` — `retry_count = 0 < MAX_RETRIES = 2` → routes to `rewrite_query`
4. `rewrite_query()` — LLM rewrites query, `retry_count = 1`
5. `retrieve()` again with new question
6. `grade_documents()` — LLM says "no" again → `is_relevant = False`
7. `decide_to_generate()` — `retry_count = 1 < 2` → `rewrite_query`
8. `rewrite_query()` — `retry_count = 2`
9. `retrieve()` → `grade_documents()` — still "no"
10. `decide_to_generate()` — `retry_count = 2 == MAX_RETRIES` → **routes to generate** (graceful degradation)
11. `generate()` uses whatever chunks exist, says "I couldn't find enough context"
12. `sources = []`, `retry_count = 2` returned to client
13. Frontend shows the amber "Query rephrased 2×" badge

---

#### 7. "Why use the same MongoDB instance for both the vector store and chat history?"

**Answer:** Pragmatic simplicity — one Atlas cluster, one connection string, no second infrastructure dependency. The two collections are logically separate: `vectors` is managed by `langchain_mongodb`, `chathistories` is managed by Mongoose on the Node.js side.

**The tradeoff they'll probe:** Operational coupling — a MongoDB Atlas outage kills both retrieval AND chat history simultaneously. In a production system you'd likely split them: dedicated vector DB (Pinecone, Weaviate) for retrieval, separate MongoDB for relational data. Here, cost/simplicity wins.

---

### 🟡 LIKELY — Know the Concept, Don't Need to Cite Line Numbers

#### 8. Chunking Strategy
- `chunk_size=2000`, `overlap=200`, `RecursiveCharacterTextSplitter`
- Recursive means: try splitting on `\n\n`, then `\n`, then ` `, then `""` — respects code structure
- Overlap ensures functions that span chunk boundaries aren't split mid-logic
- `MAX_CHUNKS=2000` cap exists to stay within Jina's free-tier monthly token budget

#### 9. Embedding Model Choice (Jina `jina-embeddings-v3`, 1024-dim)
- Code-aware embeddings outperform text-only models (like `text-embedding-ada-002`) on source code retrieval
- 1024 dimensions is a reasonable tradeoff between retrieval quality and storage cost
- The Atlas index must match: `numDimensions: 1024` in `atlas_search_index.json`

#### 10. Why Groq + LLaMA over OpenAI GPT?
- Speed: Groq's custom hardware (Language Processing Units) runs inference 10x faster than GPU-based APIs
- Cost: Free tier for prototyping
- Model: `llama-3.1-8b-instant` — small model, fast, good enough for structured yes/no grading + query rewriting
- Tradeoff: Not as capable as GPT-4 for complex reasoning; acceptable for this use case

#### 11. The `original_question` vs `question` distinction in GraphState
- `question` is mutated by `rewrite_query` on each retry
- `original_question` is never changed — `generate()` always answers the user's **actual** question, not the rewritten search query
- Without this: the LLM would answer a technically-phrased query that the user never asked

#### 12. The Directory Tree Document trick
- At ingest time, `get_directory_tree()` walks the repo and produces a human-readable file tree
- This is stored as a `Document` with `metadata={"type": "structure"}`
- At retrieval time, structural queries (containing "overview", "architecture", "what is this") trigger a pre-filtered search for this document
- Without it: questions like "what does this repo do?" return random code chunks that don't answer the question

---

## SECTION 2: Things the Interviewer Probably Won't Ask

Skip deep prep on these. Know they exist, but don't spend flashcard time here.

| Topic | Why Low Priority |
|---|---|
| Tailwind CSS classes | UI styling is not an architectural decision |
| Vite config (`vite.config.js`) | Standard setup, nothing custom |
| `BLOCKED_FILENAMES` set | Minor quality-of-life detail (filtering lockfiles) |
| `SKIP_DIRS` in directory tree | Same — pruning `node_modules` is obvious |
| `ReactMarkdown` integration | Off-the-shelf library, trivial integration |
| Lucide icon choices | Pure UI |
| `BATCH_DELAY = 1` second | Rate limit detail, not architecture |
| Express `cors()` middleware | Boilerplate, no decision made |
| `autodetect_encoding=True` in TextLoader | Defensive edge case handling, not a design choice |
| Mongoose `lean()` | Performance micro-optimization, rarely interview-worthy at SDE-1 level |
| `silent_errors=True` in DirectoryLoader | Error handling detail |
| `pyrightconfig.json` | Dev tooling config |
| Port numbers (3000, 8000, 5173) | Convention, not architecture |

---

## Interview Danger Zones (Common Traps)

> These are places where your architecture has a **known weakness**. Have a pre-prepared
> acknowledgment + what you'd fix next. Interviewers respect engineers who know their system's limits.

| Weakness | What You Say |
|---|---|
| **No auth** | "This is a prototype. In production I'd add JWT auth and scope session IDs to user accounts." |
| **No namespace isolation in vector store** | "Re-ingesting a repo adds duplicate vectors. The fix is to delete vectors by `repo_url` metadata before re-ingesting, or use a namespace-per-repo pattern." |
| **Synchronous ingest** | "This is the biggest production gap. I'd add a job queue (BullMQ on Node or Celery on Python), return a job ID immediately, and let the client poll for completion." |
| **Session ID lost on refresh** | "The session ID is in `useRef`, not `localStorage`. It's intentional for this prototype — you'd persist it in `localStorage` or derive it from a user account ID in production." |
| **3 separate LLM calls per query** | "Retrieve + grade + generate = 3 Groq API calls. I could eliminate the grade call and use a score-only approach, but the LLM grader catches semantic relevance failures that score thresholds miss." |
| **Hard-coded `localhost` in frontend** | "Should be a Vite env var (`VITE_API_URL`). Quick fix, just not done yet." |
