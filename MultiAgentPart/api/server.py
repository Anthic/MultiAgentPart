"""
api/server.py
────────────────────────────────────────────────────────────
Production FastAPI server with Async Job Queue pattern.

WHY JOB QUEUE?
  The research pipeline takes 90-120 seconds.
  HTTP timeout on most platforms = 30-60s.
  Solution: POST /research → returns {job_id} immediately,
            client polls GET /job/{id} until done.

FLOW:
  1. POST /research {"topic":"..."}
        → creates job in Redis
        → starts background thread
        → returns {"job_id": "abc123", "status": "queued"}

  2. GET /job/{job_id}
        → returns {status: "running"|"done"|"failed", progress: X%, result: ...}

  3. GET /stream/{job_id}   (Server-Sent Events)
        → streams progress events as they happen

Run locally:
  uvicorn api.server:app --reload --port 8000
"""

import json
import logging
import os
import sys
import threading
import time
import uuid
from typing import Optional

# ── Ensure project root is always on sys.path ──────────────────────────────────
# Works whether you run:  python api/server.py   OR   uvicorn api.server:app
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── Now safe to import project modules ────────────────────────────────────────
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv()

log = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Multi-Agent Research System",
    description="AI-powered deep research: QueryRewrite → Search → RAG → FactCheck → Report",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production: ["https://your-app.vercel.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Job Store (Upstash Redis or in-memory fallback) ───────────────────────────

class JobStore:
    """
    Stores job state in Upstash Redis.
    Falls back to a plain dict if Redis is unavailable (dev mode).
    """
    _local: dict = {}   # fallback in-memory store

    def _redis_key(self, job_id: str) -> str:
        return f"job:{job_id}"

    def set(self, job_id: str, data: dict, ttl: int = 3600) -> None:
        from tools.cache_tool import cache_put
        try:
            cache_put(self._redis_key(job_id), data, ttl=ttl)
        except Exception:
            self._local[job_id] = data  # fallback

    def get(self, job_id: str) -> Optional[dict]:
        from tools.cache_tool import cache_get
        try:
            result = cache_get(self._redis_key(job_id))
            if result is not None:
                return result
        except Exception:
            pass
        return self._local.get(job_id)  # fallback

    def update(self, job_id: str, patch: dict) -> None:
        existing = self.get(job_id) or {}
        existing.update(patch)
        self.set(job_id, existing)


_jobs = JobStore()


# ── Models ─────────────────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)


class JobResponse(BaseModel):
    job_id: str
    status: str          # queued | running | done | failed
    progress: int = 0    # 0–100
    stage: str = ""      # current pipeline stage name
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: float = 0.0


# ── Background runner ──────────────────────────────────────────────────────────

_STAGES = [
    ("query_rewrite", "🔍 Rewriting query",         10),
    ("search",        "🌐 Searching the web",        25),
    ("reader",        "📄 Scraping sources",         40),
    ("summarize",     "✂️  Summarising content",     52),
    ("rag",           "🧠 RAG retrieval (Qdrant)",   65),
    ("writer",        "✍️  Writing report",          78),
    ("fact_check",    "✅ Fact-checking claims",      88),
    ("critic",        "🎯 Critiquing report",        95),
]


def _run_pipeline_background(job_id: str, topic: str) -> None:
    """
    Runs in a daemon thread.
    Updates job store at each stage so the polling endpoint reflects progress.
    """
    try:
        _jobs.update(job_id, {"status": "running", "progress": 5, "stage": "starting"})

        # ── Patch pipeline to emit progress updates ────────────────────────
        import pipeline as pipe_module
        from pipeline import run_research

        # Override the compiled pipeline's invoke to intercept node calls.
        # We monkey-patch _compiled_pipeline with a thin wrapper.
        # Simpler approach: run normally and do stage % updates in a thread-safe way.

        # Progress thread — updates progress while pipeline runs
        stage_idx = [0]
        done_flag = [False]

        def _progress_ticker():
            while not done_flag[0]:
                idx = stage_idx[0]
                if idx < len(_STAGES):
                    name, msg, pct = _STAGES[idx]
                    _jobs.update(job_id, {"stage": msg, "progress": pct})
                    time.sleep(3.0)
                    stage_idx[0] = min(idx + 1, len(_STAGES) - 1)
                else:
                    time.sleep(1)

        ticker = threading.Thread(target=_progress_ticker, daemon=True)
        ticker.start()

        # Run the actual pipeline
        result = run_research(topic)

        # Stop ticker
        done_flag[0] = True

        # Store final result
        _jobs.update(job_id, {
            "status":   "done",
            "progress": 100,
            "stage":    "✅ Complete",
            "result":   {
                "topic":            result.get("topic", topic),
                "report":           result.get("report", ""),
                "critique":         result.get("critique", ""),
                "critique_score":   result.get("critique_score", 0),
                "fact_check_score": result.get("fact_check_score", 0.0),
                "rewritten_queries": result.get("rewritten_queries", []),
                "verified_urls":    result.get("verified_urls", []),
                "time_sec":         result.get("time_sec", 0),
                "error":            result.get("error", ""),
            },
        })
        log.info("Job %s done in %.1fs", job_id, result.get("time_sec", 0))

    except Exception as exc:
        log.exception("Job %s failed", job_id)
        _jobs.update(job_id, {
            "status":   "failed",
            "progress": 0,
            "stage":    "❌ Failed",
            "error":    str(exc),
        })


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — returns 200 if the server is alive."""
    return {"status": "ok", "service": "multi-agent-research", "version": "3.0.0"}


@app.post("/research", response_model=JobResponse, status_code=202)
async def start_research(req: ResearchRequest):
    """
    Start a research job.

    Returns immediately with a job_id.
    Poll GET /job/{job_id} for status and result.
    """
    job_id = str(uuid.uuid4())[:12]
    now    = time.time()

    job_data = {
        "job_id":     job_id,
        "topic":      req.topic,
        "status":     "queued",
        "progress":   0,
        "stage":      "⏳ Queued",
        "result":     None,
        "error":      None,
        "created_at": now,
    }
    _jobs.set(job_id, job_data, ttl=7200)  # keep for 2h

    # Fire background thread
    t = threading.Thread(
        target=_run_pipeline_background,
        args=(job_id, req.topic),
        daemon=True,
    )
    t.start()

    log.info("Job %s queued for topic=%r", job_id, req.topic)
    return job_data


@app.get("/job/{job_id}", response_model=JobResponse)
async def poll_job(job_id: str):
    """
    Poll job status.

    status values:
      queued  — waiting to start
      running — pipeline is executing
      done    — result ready in 'result' field
      failed  — error in 'error' field
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@app.get("/stream/{job_id}")
async def stream_job(job_id: str):
    """
    Server-Sent Events (SSE) stream for a job.

    Emits progress events every 2 seconds until job is done or failed.
    The React frontend subscribes to this for real-time updates.
    """
    async def event_generator():
        for _ in range(300):   # max 600s (300 × 2s)
            job = _jobs.get(job_id)
            if not job:
                yield f"event: error\ndata: {json.dumps({'message': 'job not found'})}\n\n"
                return

            import asyncio
            yield f"event: progress\ndata: {json.dumps(job)}\n\n"

            if job["status"] in ("done", "failed"):
                return

            await asyncio.sleep(2)

        yield f"event: timeout\ndata: {{}}\n\n"

    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/history")
async def get_history(limit: int = 10):
    """List recent completed research sessions from Supabase."""
    import asyncio
    try:
        from memory import get_recent
        loop = asyncio.get_event_loop()
        records = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: get_recent(limit=limit)),
            timeout=8.0,
        )
        return {"records": records, "count": len(records)}
    except asyncio.TimeoutError:
        return {"records": [], "count": 0, "note": "DB unavailable (timeout)"}
    except Exception as exc:
        log.warning("History endpoint failed: %s", exc)
        return {"records": [], "count": 0, "note": str(exc)}


@app.get("/history/{record_id}")
async def get_history_item(record_id: int):
    """Get a single research record by ID."""
    try:
        from memory.history import get_by_id
        record = get_by_id(record_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
        return record
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/cache/stats")
async def get_cache_stats():
    """Upstash Redis cache statistics."""
    try:
        from tools.cache_tool import cache_stats
        return cache_stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    # Use app object directly (not string) so it works when run as:
    #   python api/server.py  (from project root)
    # For hot-reload use uvicorn CLI instead:
    #   uvicorn api.server:app --reload   (from project root)
    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,    # reload=True requires running via uvicorn CLI
        log_level="info",
    )
