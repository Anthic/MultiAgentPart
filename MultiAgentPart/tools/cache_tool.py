"""
tools/cache_tool.py
────────────────────────────────────────────────────────────
Production cache — Upstash Redis (REST API, serverless-safe).

Why Upstash REST instead of redis-py?
  • Works on serverless (Vercel, Cloud Run) without TCP connection pools
  • Upstash free tier: 10K requests/day, 256MB
  • Zero infrastructure — just HTTP calls

Usage:
  from tools.cache_tool import cached_search, cache_stats
"""

import json
import logging
import os
from typing import Any, Callable, Optional

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

UPSTASH_REDIS_URL   = os.getenv("UPSTASH_REDIS_URL", "")
UPSTASH_REDIS_TOKEN = os.getenv("UPSTASH_REDIS_TOKEN", "")

_DEFAULT_TTL = 3600   # 1 hour


# ── Low-level REST client ──────────────────────────────────────────────────────

def _redis_command(*args) -> Any:
    """
    Execute any Redis command via Upstash REST API.
    https://upstash.com/docs/redis/features/restapi

    Args:
        *args: Redis command + arguments, e.g. ("GET", "mykey") or ("SET", "k", "v", "EX", 60)

    Returns:
        Parsed JSON result from Upstash, or None on error.
    """
    if not UPSTASH_REDIS_URL or not UPSTASH_REDIS_TOKEN:
        log.debug("Cache: Upstash not configured — skipping")
        return None

    import httpx

    url     = f"{UPSTASH_REDIS_URL.rstrip('/')}/{'/'.join(str(a) for a in args)}"
    headers = {"Authorization": f"Bearer {UPSTASH_REDIS_TOKEN}"}

    try:
        response = httpx.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("result")
    except Exception as exc:
        log.warning("Cache: Upstash REST call failed — %s", exc)
        return None


def _cache_set(key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
    """Store a JSON-serialised value with TTL in seconds."""
    try:
        serialised = json.dumps(value)
        _redis_command("SET", key, serialised, "EX", ttl)
    except Exception as exc:
        log.warning("Cache: SET failed — %s", exc)


def _cache_get(key: str) -> Optional[Any]:
    """Retrieve and JSON-deserialise a cached value (None if missing/error)."""
    try:
        raw = _redis_command("GET", key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        log.warning("Cache: GET failed — %s", exc)
        return None


def _cache_delete(key: str) -> None:
    _redis_command("DEL", key)


def _cache_exists(key: str) -> bool:
    return _redis_command("EXISTS", key) == 1


# ── Public API ─────────────────────────────────────────────────────────────────

def cached_search(
    topic: str,
    search_fn: Callable[[str], Any],
    ttl: int = _DEFAULT_TTL,
) -> Any:
    """
    Execute search_fn(topic) with transparent Upstash Redis caching.

    On cache HIT  — returns stored result immediately (no API call).
    On cache MISS — calls search_fn, stores result, returns result.

    Args:
        topic:     Search query string (used as cache key).
        search_fn: Callable that accepts a topic string and returns results.
        ttl:       Cache lifetime in seconds (default 3600 = 1 hour).
    """
    key = f"search:{topic.lower().strip()}"

    cached = _cache_get(key)
    if cached is not None:
        log.info("Cache: 🎯 HIT for %r", topic)
        return cached

    log.info("Cache: MISS for %r — running search", topic)
    result = search_fn(topic)
    _cache_set(key, result, ttl=ttl)
    return result


def cache_put(key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
    """Manually store any JSON-serialisable value."""
    _cache_set(key, value, ttl=ttl)


def cache_get(key: str, default: Any = None) -> Any:
    """Retrieve a value by key, returning default if missing."""
    val = _cache_get(key)
    return val if val is not None else default


def cache_stats() -> dict:
    """
    Return basic Upstash Redis stats.
    Uses the INFO command (returns str on Upstash REST — we parse key fields).
    """
    if not UPSTASH_REDIS_URL or not UPSTASH_REDIS_TOKEN:
        return {"status": "not_configured"}

    try:
        db_size = _redis_command("DBSIZE")
        return {
            "status":   "active",
            "provider": "upstash_redis",
            "url":      UPSTASH_REDIS_URL,
            "db_size":  db_size,
            "ttl_default": _DEFAULT_TTL,
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
