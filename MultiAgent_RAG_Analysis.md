# 🤖 Multi-Agent RAG System — Senior AI Engineer Analysis

> **Project:** Mistral AI + LangGraph + ChromaDB Research Agent  
> **Stack:** `mistral-small` + `mistral-large` | LangGraph | ChromaDB | Tavily | BeautifulSoup  
> **Mode:** Read-only analysis — no code changes, folder-wise suggestions only

---

## 🗺️ Current Architecture Flow

```
main.py
  └── pipeline/__init__.py → run_research()
        └── pipeline/runner.py → build_pipeline()
              ├── [Node 1] agents/search_agent.py   → Tavily Search (fast LLM)
              ├── [Node 2] agents/reader_agent.py   → Parallel Web Scraper
              ├── [Node 3] pipeline/rag.py          → ChromaDB Embed + Retrieve
              ├── [Node 4] pipeline/chains.py       → Writer (smart LLM)
              └── [Node 5] pipeline/chains.py       → Critic → loop/end (fast LLM)
```

---

## ❓ Question 1 — Performance কেন দেরি হয়? কীভাবে optimize করবো?

### 🔍 Current Problem (Folder by File)

| File | সমস্যা |
|------|--------|
| `pipeline/rag.py` | প্রতিবার `build_vectorstore()` নতুন করে তৈরি হয়, আবার `build_embeddings()` ও নতুন HuggingFace model load করে — overhead বিশাল |
| `agents/reader_agent.py` | `parallel_scraper_tool.invoke()` করে, কিন্তু max 3 URLs — scraping টা ভালো তবে timeout 12s হওয়ায় worst case 12s block |
| `pipeline/__init__.py` | `build_pipeline()` প্রতি `run_research()` call-এ নতুন করে সব build করে — LLM client, vectorstore, chains সব re-create |
| `pipeline/runner.py` | `get_llm()` দুইবার call হয়, দুইটা আলাদা Mistral client তৈরি হয় |

### ✅ Folder-wise Suggestions

**`pipeline/model.py`** — LLM Singleton Cache যোগ করো:
```python
# সমস্যা: প্রতিবার নতুন ChatMistralAI() তৈরি হয়
# সমাধান: module-level cache দিয়ে একবারই তৈরি করো

_llm_cache: dict = {}

def get_llm(kind: str):
    if kind not in _llm_cache:
        _llm_cache[kind] = ChatMistralAI(
            model=model_map[kind],
            temperature=0,
            api_key=os.getenv("MISTRALAI_API_KEY"),
        )
    return _llm_cache[kind]
```

**`pipeline/rag.py`** — Vectorstore Singleton + lazy embedding load:
```python
# সমস্যা: প্রতি run-এ নতুন Chroma + HuggingFace model load
# সমাধান: module-level singleton

_vectorstore = None

def get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        _vectorstore = Chroma(...)
    return _vectorstore
```

**`pipeline/__init__.py`** — Pipeline compile একবারই করো:
```python
# সমস্যা: প্রতিবার build_pipeline() call হয়
# সমাধান: compiled pipeline cache করো

_compiled_pipeline = None

def run_research(topic: str) -> dict:
    global _compiled_pipeline
    if _compiled_pipeline is None:
        _compiled_pipeline = build_pipeline()
    ...
```

**`tools/scraper.py`** — Connection pooling + smarter timeout:
```python
# সমস্যা: প্রতি request-এ নতুন connection, timeout 12s বেশি
# সমাধান: requests.Session() reuse + timeout কমাও

_session = requests.Session()
_session.headers.update(DEFAULT_HEADERS)

def scrape_one(url, timeout=8, max_chars=3000):
    response = _session.get(url, timeout=timeout)
    ...
```

> **Expected speedup:** 30–60% faster on repeated runs. প্রথম run সবসময় slow থাকবে (model load), পরেরগুলো দ্রুত।

---

## ❓ Question 2 — Token খরচ কমানো কীভাবে?

### 🔍 Current Token Waste

| File | সমস্যা |
|------|--------|
| `pipeline/chains.py` | `_writer_prompt` তে `search_results` + `scraped_content` + `rag_context` সব একসাথে পাঠায় — triple content overlap |
| `tools/scraper.py` | `max_chars=4000` × 3 URLs = 12,000 chars raw text, সব writer LLM-এ যায় |
| `pipeline/rag.py` | `k=5` chunks retrieve করে, প্রতিটা 500 chars = 2500 chars extra context |
| `pipeline/runner.py` | `max_retries=1` — rewrite হলে writer আবার full context পায়, double cost |

### ✅ Folder-wise Suggestions

**`tools/scraper.py`** — per-URL char limit কমাও:
```python
# সমস্যা: 4000 chars × 3 = 12000 chars → writer LLM তে বিশাল token
# সমাধান: 2000 chars per URL, মোট 6000 chars

def scrape_one(url, timeout=8, max_chars=2000):
    ...
```

**`pipeline/rag.py`** — chunk size এবং retrieval count optimize করো:
```python
# সমস্যা: k=5, chunk_size=500 → 2500 chars redundant context
# সমাধান: k=3, chunk_size=400

relevant_docs = vectorstore.similarity_search(topic, k=3)

splitter = RecursiveCharacterTextSplitter(
    chunk_size=400,
    chunk_overlap=40,
)
```

**`pipeline/chains.py`** — Writer prompt-এ token budget enforce করো:
```python
# সমস্যা: search_results টা full dump হয়, অনেক লম্বা
# সমাধান: writer prompt-এ truncation বা summarized input পাঠাও

# runner.py-তে writer call করার আগে:
search_results = state.get("search_results", "")[:2000]  # cap it
scraped_content = state.get("scraped_content", "")[:4000]  # cap it
rag_context = state.get("rag_context", "")[:1500]   # cap it
```

**`pipeline/runner.py`** — Critic-এ শুধু report যাক, full state নয়:
```python
# সমস্যা: run_critic() full state নেয়, কিন্তু critic শুধু report দেখে
# ভালো pattern: critic-এ শুধু truncated report পাঠাও

def run_critic_and_score(state: dict, critic_chain) -> dict:
    # Critic শুধু first 3000 chars দেখলেই যথেষ্ট
    truncated_state = {**state, "report": state.get("report", "")[:3000]}
    updated = run_critic(truncated_state, critic_chain)
    ...
```

> **Estimated token saving:** 40–55% less per run

---

## ❓ Question 3 — Hallucination কমানো কীভাবে?

### 🔍 Current Hallucination Risks

| File | Risk |
|------|------|
| `pipeline/chains.py` | `verified_urls` পাঠানো হয় ঠিকই, কিন্তু LLM কে শুধু "Never invent URLs" বলা হয় — weak instruction |
| `pipeline/rag.py` | RAG context আর scraped content আলাদা নয়, LLM blend করে ভুল fact বানাতে পারে |
| `agents/search_agent.py` | Search agent output-এ LLM নিজেই markdown format করে, URL alter করতে পারে |
| `pipeline/runner.py` | Score parse করা regex-based — LLM যদি "Score: 8.5/10" দেয় তাহলে 0 return করে bug |

### ✅ Folder-wise Suggestions

**`pipeline/chains.py`** — Stronger grounding instruction:
```python
# সমস্যা: "Never invent URLs" যথেষ্ট নয়
# সমাধান: Strict grounding prompt যোগ করো

system_prompt = """You are an expert research writer.
STRICT RULES:
1. ONLY use facts from the provided Search Results, Scraped Content, and RAG Context.
2. If a fact is not in the provided context, write "Not found in sources."
3. ONLY use URLs from the verified_urls list. Do NOT modify or create any URL.
4. Every claim must have a citation from the sources provided.
5. If sources conflict, mention both and prefer the most recent one."""
```

**`pipeline/runner.py`** — Score parser fix করো (bug আছে!):
```python
# সমস্যা: "Score: 8.5/10" বা "score:8/10" match করে না
# সমাধান: আরো robust regex

def parse_score(critique: str) -> int:
    match = re.search(
        r"score\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*/\s*10",
        critique or "",
        flags=re.IGNORECASE
    )
    if not match:
        return 0
    return max(0, min(10, round(float(match.group(1)))))
```

**`pipeline/rag.py`** — Source labeling যোগ করো:
```python
# সমস্যা: RAG context plain text, কোথা থেকে এলো বোঝা যায় না
# সমাধান: source label সহ context তৈরি করো

relevant_text = "\n\n".join(
    f"[Source chunk {i+1}]: {doc.page_content}"
    for i, doc in enumerate(relevant_docs)
)
```

**`agents/search_agent.py`** — Search agent output validate করো:
```python
# সমস্যা: LLM output directly state-এ যায়, URL যাচাই নেই
# সমাধান: raw tool output prefer করো, LLM summary trust করো না
# TavilySearchResults raw JSON দেয় → সেটাই verified_urls extract করো
```

---

## ❓ Question 4 — Vector DB (ChromaDB) কি ঠিক আছে? আরো ভালো option আছে?

### 🔍 Current ChromaDB Usage Analysis

**`pipeline/rag.py`** এ দেখো:
```python
vectorstore.add_documents(chunks)  # ← প্রতিবার নতুন docs add করে!
```

**Critical Bug:** প্রতি query-তে same topic-এর chunks আবার add হয়। Chroma-তে duplicate data জমা হতে থাকে। পুরনো irrelevant data search results pollute করে।

### ✅ ChromaDB Fix করার Suggestion (`pipeline/rag.py`):
```python
# সমস্যা: প্রতিবার add_documents() — duplicate accumulation
# সমাধান: topic-based collection ID দিয়ে check করো

import hashlib

def run_rag_node(state):
    topic = state.get("topic", "")
    raw_text = state.get("scraped_content", "")
    
    # Topic-specific collection
    topic_id = hashlib.md5(topic.encode()).hexdigest()[:8]
    
    vs = Chroma(
        collection_name=f"research_{topic_id}",  # unique per topic
        embedding_function=build_embeddings(),
        persist_directory=CHROMA_DIR,
    )
    
    # Check if already indexed
    if vs._collection.count() == 0:
        chunks = chunk_text(raw_text)
        vs.add_documents(chunks)
    
    ...
```

### 📊 Vector DB Comparison

| DB | Best For | Trade-off | Use in এই Project |
|----|----------|-----------|-------------------|
| **ChromaDB** ✅ | Local dev, small data | No scaling | ঠিক আছে এখনের জন্য |
| **FAISS** | Speed-first, offline | No persistence | Fast prototype |
| **Qdrant** | Production RAG | Docker needed | Next step হলে |
| **Weaviate** | Hybrid search (BM25+Vector) | Complex setup | Enterprise scale |
| **Pinecone** | Cloud-managed | Paid, API needed | SaaS product হলে |

> **Verdict:** ChromaDB এখনের জন্য ঠিক আছে, কিন্তু **duplicate bug** fix করা জরুরি। Production-এ গেলে **Qdrant** সবচেয়ে ভালো।

---

## ❓ Question 5 — Agent কে আরো powerful করার উপায়?

### 🚀 Feature Ideas (Folder-wise)

#### **`agents/` — নতুন Agent যোগ করো**

```
agents/
  ├── search_agent.py      ✅ আছে
  ├── reader_agent.py      ✅ আছে
  ├── fact_check_agent.py  ← NEW: claim verification
  ├── summarizer_agent.py  ← NEW: long content → key points  
  └── query_rewrite_agent.py ← NEW: bad query → better query
```

**`agents/query_rewrite_agent.py`** — Query Expansion:
```python
# কেন দরকার: "AI 2024" → "latest artificial intelligence breakthroughs 2024 research"
# Impact: search quality 40%+ improve হয়

def rewrite_query(topic: str, llm) -> str:
    prompt = f"""Rewrite this research topic into 3 specific search queries:
Topic: {topic}
Return: 3 queries, one per line."""
    return llm.invoke(prompt).content
```

**`agents/fact_check_agent.py`** — Claim Verification:
```python
# কেন দরকার: hallucination detect করতে
# Writer report-এর facts সরাসরি sources-এর সাথে match করো
```

#### **`tools/` — নতুন Tools**

```
tools/
  ├── scraper.py           ✅ আছে
  ├── tools.py             ✅ আছে
  ├── cache_tool.py        ← NEW: same query cache করো (Redis/SQLite)
  ├── pdf_reader.py        ← NEW: arxiv/papers PDF read  
  └── wikipedia_tool.py   ← NEW: Wikipedia as fallback source
```

**`tools/cache_tool.py`** — Query Result Cache:
```python
# কেন দরকার: same topic বারবার search করলে API call বাঁচে
# Implementation: SQLite বা diskcache দিয়ে simple key-value store

import diskcache as dc

_cache = dc.Cache("data/query_cache")

def cached_search(topic: str, search_fn, ttl=3600):
    if topic in _cache:
        return _cache[topic]
    result = search_fn(topic)
    _cache.set(topic, result, expire=ttl)
    return result
```

#### **`pipeline/` — Pipeline Upgrades**

**`pipeline/runner.py`** — নতুন node যোগ করো:
```
START
  → query_rewrite   ← NEW: query improve করো
  → search          
  → reader          
  → rag             
  → fact_check      ← NEW: source match করো
  → writer          
  → critic          
  → END
```

**`pipeline/chains.py`** — Streaming output যোগ করো:
```python
# কেন দরকার: user দেখতে পাবে output আসছে, wait কম feel হয়
# main.py-তে:
for chunk in writer_chain.stream(inputs):
    print(chunk, end="", flush=True)
```

#### **Extra Powerful Features:**

| Feature | File | কেন দরকার |
|---------|------|-----------|
| **Streaming output** | `main.py` + `chains.py` | Response আসতে আসতে দেখাবে |
| **Multi-query search** | `search_agent.py` | 3 different queries → better coverage |
| **Citation validator** | `chains.py` | URL scrape করে claim verify |
| **Export to PDF/Markdown** | `main.py` | Report save করা |
| **Web UI (FastAPI)** | নতুন `api/` folder | Browser-based interface |
| **Async pipeline** | `runner.py` | `asyncio` দিয়ে parallel nodes |
| **Memory/History** | নতুন `memory/` folder | পুরনো research access করা |
| **Auto retry on API fail** | `model.py` | `tenacity` already in requirements! |

---

## ❓ Question 6 — দুইটা LLM কোনটা কোথায় use হচ্ছে?

### 📍 Clear Breakdown (`pipeline/runner.py` → `pipeline/model.py`)

```python
# runner.py line 82-88:
fast_llm = get_llm("fast")    # mistral-small-2603
smart_llm = get_llm("smart")  # mistral-large-2512

search_agent = build_search_agent(fast_llm)   # ← FAST LLM
reader_agent = build_reader_agent()            # ← NO LLM (deterministic)
writer_chain = build_writer_chain(smart_llm)   # ← SMART LLM
critic_chain = build_critic_chain(fast_llm)    # ← FAST LLM
```

### 🧠 কোনটা কোথায় কেন?

| Model | Kind | কোথায় use হচ্ছে | কেন এই choice? |
|-------|------|----------------|----------------|
| `mistral-small-2603` | **fast** | Search Agent, Critic | সহজ কাজ — search query বানানো, score দেওয়া। Cheap + Fast. ✅ Smart choice |
| `mistral-large-2512` | **smart** | Writer Chain | Complex কাজ — full research report লেখা, citation সাজানো। এখানে quality দরকার। ✅ Smart choice |
| *(None)* | — | Reader Agent | Deterministic — regex + scraping, LLM দরকার নেই। ✅ Correct |

### 💡 এটা Agentic AI-এর কোন Part?

```
🔵 Search Agent → ReAct Pattern (Reason + Act)
   └── LLM decides: "I need to search" → calls Tavily Tool → gets results

🟢 Reader Agent → Deterministic Tool Use
   └── No LLM → URL extract → parallel scrape → pure function

🟡 RAG Node → Retrieval-Augmented Generation  
   └── Embed scraped text → store in ChromaDB → retrieve relevant chunks

🔴 Writer Chain → LCEL Chain (Prompt | LLM | OutputParser)
   └── LLM gets all context → generates structured report

🟣 Critic Chain → Evaluator-Optimizer Loop
   └── Scores report → routes back to writer if score < 8 → Self-refinement
```

---

## 🏗️ Current vs Recommended Architecture

```
CURRENT (Basic RAG Pipeline):
User → Search → Scrape → RAG → Write → Critique → Output

RECOMMENDED (Powerful Multi-Agent System):
User → QueryRewrite → MultiSearch → ParallelScrape+PDF → 
       RAG(Qdrant) → FactCheck → Write → Critique → 
       Export(MD/PDF) → Output + Cache
```

---

## 🐛 Bugs Found (Fix Priority)

| # | File | Bug | Severity |
|---|------|-----|----------|
| 1 | `pipeline/rag.py` | প্রতিবার `add_documents()` → duplicate data জমে | 🔴 HIGH |
| 2 | `pipeline/runner.py` | `parse_score()` "8.5/10" বা lowercase "score:" match করে না | 🟡 MED |
| 3 | `pipeline/rag.py` | `build_vectorstore()` আর `build_embeddings()` প্রতিবার create → slow | 🟡 MED |
| 4 | `pipeline/__init__.py` | `build_pipeline()` প্রতিবার নতুন করে compile → waste | 🟡 MED |
| 5 | `tools/tools.py` | `top_K` legacy parameter আছে কিন্তু এখন unused, confusing | 🟢 LOW |
| 6 | `tools/scraper.py` | Error URL গুলো ("ERROR scraping...") RAG-তে index হয়ে যায় | 🟡 MED |

---

## 📂 Recommended Folder Structure (Future)

```
MultiAgentPart/
│
├── main.py                      ← streaming + CLI args যোগ করো
├── requirements.txt
├── .env
│
├── agents/
│   ├── __init__.py
│   ├── search_agent.py          ✅ ভালো আছে
│   ├── reader_agent.py          ✅ ভালো আছে
│   ├── query_rewrite_agent.py   ← NEW: query expansion
│   └── fact_check_agent.py      ← NEW: hallucination guard
│
├── pipeline/
│   ├── __init__.py              → singleton pipeline cache
│   ├── model.py                 → LLM singleton cache
│   ├── rag.py                   → duplicate fix + source labels
│   ├── chains.py                → stronger grounding prompt
│   └── runner.py                → score parser fix + new nodes
│
├── tools/
│   ├── __init__.py
│   ├── tools.py                 → remove legacy top_K
│   ├── scraper.py               → session reuse + error filter
│   ├── cache_tool.py            ← NEW: query result cache
│   └── pdf_reader.py            ← NEW: arxiv paper support
│
├── memory/
│   └── history.py               ← NEW: past research store
│
├── api/
│   └── server.py                ← NEW: FastAPI web interface
│
└── data/
    └── chroma/                  ← topic-based collections
```

---

## 🎓 Learning Path — Agentic AI Concepts in এই Project

| Concept | কোন File | কী শিখছো |
|---------|---------|---------|
| **ReAct Agent** | `search_agent.py` | LLM + Tool loop = Agent |
| **LCEL Chain** | `chains.py` | `prompt | llm | parser` pipeline pattern |
| **LangGraph StateGraph** | `runner.py` | Node-based stateful workflow |
| **Conditional Routing** | `runner.py` | `add_conditional_edges` = if/else in graph |
| **RAG** | `rag.py` | Embed → Store → Retrieve → Augment |
| **Self-refinement Loop** | `runner.py` | Critic score → rewrite loop |
| **Parallel Tool Use** | `scraper.py` | ThreadPoolExecutor concurrent calls |
| **Dual Model Routing** | `model.py` | cheap model for simple, expensive for complex |
