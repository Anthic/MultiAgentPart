# 🚀 Production Roadmap — Multi-Agent Research System
### Senior AI Engineer Analysis

---

## 🔬 Current Stack — Honest Assessment

| Component | Current | Production-Ready? | Issue |
|-----------|---------|:-:|-------|
| LLM | Mistral AI (API) | ✅ | None |
| Search | Tavily API | ✅ | None |
| Pipeline | LangGraph | ✅ | None |
| Vector DB | **Chroma (local files)** | ❌ | File-based, dies on serverless |
| History DB | **SQLite** | ❌ | File-based, no persistence |
| Cache | **diskcache (SQLite)** | ❌ | File-based, no persistence |
| Embeddings | HuggingFace local model | ⚠️ | 5–10s cold start on free tier |
| API | FastAPI (`api/server.py`) | ✅ | Needs async job pattern |
| Runtime | 95+ seconds per request | ❌ | Too slow for HTTP timeout |

> [!CAUTION]
> **Vercel-এ সরাসরি Python backend deploy করা সম্ভব নয়** কারণ:
> 1. তোমার pipeline **95 seconds** লাগে — Vercel Hobby timeout **10 seconds**
> 2. Chroma/SQLite/diskcache সব **local file** — serverless এ প্রতিটা invocation আলাদা, কোনো data থাকে না
> 3. HuggingFace model loading cold start = আরো 8-10s

---

## 🏗️ Production Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER BROWSER                                │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTPS
┌───────────────────────▼─────────────────────────────────────────┐
│            REACT FRONTEND  ──── Vercel (Free ✅)                │
│   • Topic input, streaming SSE display                          │
│   • History dashboard, source links                             │
└───────────────────────┬─────────────────────────────────────────┘
                        │ REST API
┌───────────────────────▼─────────────────────────────────────────┐
│         NODE.JS API GATEWAY ──── Vercel Serverless (Free ✅)    │
│   • Auth / rate limiting / input validation                     │
│   • Short-lived: POST /research → returns job_id               │
│   • GET /job/:id → polls Python service                         │
│   • GET /history, GET /health                                   │
│   (Next.js API routes — কোনো timeout issue নেই এখানে)          │
└───────────────────────┬─────────────────────────────────────────┘
                        │ Internal HTTP
┌───────────────────────▼─────────────────────────────────────────┐
│     PYTHON FASTAPI  ──── Google Cloud Run (Free Tier ✅)        │
│   • /run-research   → starts background job (returns job_id)    │
│   • /job/{id}       → returns status + result                   │
│   • /stream/{id}    → SSE stream of progress events             │
│   LangGraph pipeline (95s runs in background, not HTTP timeout) │
└──────┬──────────────────┬───────────────────┬───────────────────┘
       │                  │                   │
┌──────▼──────┐  ┌────────▼────────┐  ┌───────▼──────────┐
│ Qdrant Cloud│  │   Supabase      │  │  Upstash Redis   │
│ (Vector DB) │  │  (PostgreSQL)   │  │  (Cache/Queue)   │
│  Free ✅    │  │   Free ✅        │  │   Free ✅         │
│ RAG storage │  │ Research history│  │ Job queue + cache│
└─────────────┘  └─────────────────┘  └──────────────────┘
       │                  │                   │
┌──────▼──────────────────▼───────────────────▼───────────┐
│            EXTERNAL APIs (পরিবর্তন নেই)                 │
│         Mistral AI        +        Tavily Search         │
└──────────────────────────────────────────────────────────┘
```

---

## ❓ `api/` Folder কি দরকার?

**হ্যাঁ, কিন্তু পরিবর্তন করতে হবে।**

বর্তমান `api/server.py` সরাসরি synchronous — 95s ধরে HTTP connection open রাখে। Production এ এটা করা যাবে না। Pattern পরিবর্তন করতে হবে:

```
❌ Current:  POST /research → [95s wait...] → return result
✅ Production: POST /research → return {job_id: "abc123"}
               GET /job/abc123 → {status: "running", progress: 60%}
               GET /job/abc123 → {status: "done", result: {...}}
```

এটাকে **Async Job Queue Pattern** বলে। Redis (Upstash) দিয়ে সহজে করা যায়।

---

## 📦 কোন Services Replace হবে

### 1. Vector DB: Chroma → Qdrant Cloud

```python
# ❌ Current (local files — dies on serverless)
from langchain_chroma import Chroma
vectorstore = Chroma(persist_directory="data/chroma")

# ✅ Production (Qdrant Cloud — free 1GB)
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)
vectorstore = QdrantVectorStore(client=client, collection_name="research")
```

**কেন Qdrant?**
- Free Cloud tier: 1GB storage, unlimited requests
- Production-grade, Docker-friendly
- তোমার user request এ Qdrant চাইছিলে — এখন সময় এসেছে!

### 2. History DB: SQLite → Supabase (PostgreSQL)

```python
# ❌ Current (local SQLite)
conn = sqlite3.connect("data/research_history.db")

# ✅ Production (Supabase — free 500MB)
import psycopg2
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
```

**Supabase Free:** 500MB DB, REST API auto-generated, real-time সাপোর্ট।

### 3. Cache: diskcache → Upstash Redis

```python
# ❌ Current (local diskcache)
import diskcache as dc
_cache = dc.Cache("data/query_cache")

# ✅ Production (Upstash Redis — free 10K req/day)
import redis
r = redis.from_url(os.getenv("UPSTASH_REDIS_URL"))
r.setex(key, ttl, json.dumps(value))
```

### 4. Embeddings: Local HuggingFace → Mistral Embeddings API

```python
# ❌ Current (5-10s model load on cold start)
HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# ✅ Production (API-based, no cold start)
from langchain_mistralai import MistralAIEmbeddings
embeddings = MistralAIEmbeddings(model="mistral-embed")
```

---

## 🆓 Free Hosting — সব অপশন

| Service | কি Host করবে | Free Tier | Limitation |
|---------|-------------|-----------|------------|
| **Vercel** | React + Next.js API | Unlimited | 10s serverless timeout |
| **Google Cloud Run** | Python FastAPI | 2M req/month | Cold start ~2s |
| **Qdrant Cloud** | Vector Database | 1GB | — |
| **Supabase** | PostgreSQL | 500MB | 2 projects |
| **Upstash Redis** | Cache + Job Queue | 10K req/day | — |
| **Hugging Face Spaces** | Python FastAPI (alt) | Free | Slow cold start |

> [!TIP]
> তোমার কাছে **Google Cloud Run MCP** আছে! Python backend সেখানে deploy করা সবচেয়ে সহজ এবং free-tier এ সবচেয়ে বেশি reliable।

---

## 🗺️ Phased Implementation Plan

### Phase 1 — Backend Production-Ready করো (Python)
**সময়: ২-৩ দিন**

- [ ] `pipeline/rag.py` → Qdrant Cloud এ migrate করো
- [ ] `memory/history.py` → Supabase PostgreSQL তে migrate করো
- [ ] `tools/cache_tool.py` → Upstash Redis তে migrate করো
- [ ] `pipeline/rag.py` → Mistral Embeddings API তে migrate করো
- [ ] `api/server.py` → Async Job Queue pattern implement করো
- [ ] `.env` তে নতুন সব API keys যোগ করো
- [ ] Google Cloud Run এ deploy করো (Cloud Run MCP দিয়ে)

### Phase 2 — Node.js API Gateway (Vercel)
**সময়: ১-২ দিন**

```
next-research-app/
├── pages/api/
│   ├── research.js      ← POST: Python service এ forward করো
│   ├── job/[id].js      ← GET: job status poll
│   ├── history.js       ← GET: Supabase থেকে directly
│   └── health.js        ← health check
└── ...
```

- [ ] `npx create-next-app` দিয়ে project তৈরি করো
- [ ] API routes লেখো (Python service proxy)
- [ ] Environment variables সেট করো
- [ ] Vercel এ deploy করো

### Phase 3 — React Frontend (Vercel)
**সময়: ২-৩ দিন**

```
src/
├── components/
│   ├── SearchBox.jsx        ← topic input + submit
│   ├── ProgressTracker.jsx  ← pipeline stages (SSE)
│   ├── ReportViewer.jsx     ← formatted markdown report
│   ├── SourceLinks.jsx      ← verified URLs list
│   ├── ScoreBadge.jsx       ← critique + fact-check scores
│   └── HistoryPanel.jsx     ← past research sessions
└── pages/
    ├── index.jsx            ← main research UI
    └── history.jsx          ← history dashboard
```

- [ ] React app তৈরি করো
- [ ] SSE connection দিয়ে streaming progress দেখাও
- [ ] Markdown report render করো (react-markdown)
- [ ] Vercel এ deploy করো

---

## ⚠️ Production এ Issues হবে কি?

### ✅ সমস্যা হবে না
- Mistral AI calls → API-based, serverless-safe
- Tavily search → API-based, serverless-safe
- LangGraph pipeline → stateless, fine

### ❌ অবশ্যই সমস্যা হবে (যদি এখনই deploy করো)
1. **95s timeout** → Cloud Run default 60s; বাড়াতে হবে `--timeout=300`
2. **Chroma local files** → Cloud Run এর disk ephemeral (restart এ মুছে যাবে)
3. **SQLite** → একই সমস্যা
4. **HuggingFace model** → প্রতিটা cold start এ re-download (2-5 min!)
5. **CORS** → Python backend তে React origin allow করতে হবে

---

## 🔑 নতুন Environment Variables (.env)

```bash
# Existing
MISTRALAI_API_KEY=...
TAVILY_API_KEY=...

# Phase 1 (New)
QDRANT_URL=https://xxxx.qdrant.tech
QDRANT_API_KEY=...
DATABASE_URL=postgresql://postgres:pass@db.supabase.co:5432/postgres
UPSTASH_REDIS_URL=rediss://default:pass@host.upstash.io:6379

# Phase 2 (Node.js)
PYTHON_SERVICE_URL=https://your-app.run.app
NEXT_PUBLIC_API_URL=https://your-next-app.vercel.app
```

---

## 🐳 Docker করতে হবে কি?

**Google Cloud Run এ হ্যাঁ** — কিন্তু Cloud Run MCP সেটা automatically করে দেয়! তুমি শুধু folder দাও, বাকি সব Cloud Run handle করে।

```bash
# এটুকুই করলে হয়
mcp_cloudrun_deploy_local_folder(
    folderPath="d:/Anthic/MultiagenSytemAllPart/MultiAgentPart",
    project="your-gcp-project"
)
```

Cloud Run নিজেই Dockerfile তৈরি করে, build করে, deploy করে।

---

## 📋 Summary — কোথা থেকে শুরু করবে

```
Priority 1 (আজকেই): Qdrant Cloud account খোলো (free)
Priority 2 (আজকেই): Supabase account খোলো (free)  
Priority 3 (আজকেই): Upstash account খোলো (free)
Priority 4 (এই সপ্তাহে): pipeline/rag.py Qdrant তে migrate
Priority 5 (এই সপ্তাহে): api/server.py async job pattern
Priority 6 (পরের সপ্তাহে): Cloud Run deploy
Priority 7 (পরের সপ্তাহে): Next.js API Gateway on Vercel
Priority 8 (পরের সপ্তাহে): React frontend on Vercel
```

**আমাকে বলো কোন Phase দিয়ে শুরু করতে চাও — আমি সেই কোড লিখে দেব।**
