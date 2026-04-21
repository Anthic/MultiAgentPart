"""
test_api.py
Full API test — no emojis (Windows cp1252 safe).
Run: python test_api.py
"""
import httpx
import json
import time
import sys

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://localhost:8002"

def sep(title=""):
    print(f"\n{'=' * 55}")
    if title:
        print(f"  {title}")
        print("=" * 55)

# ── Health ────────────────────────────────────────────────
sep("TEST 1: Health Check")
r = httpx.get(f"{BASE}/health")
assert r.status_code == 200
data = r.json()
print(f"  status  : {data['status']}")
print(f"  service : {data['service']}")
print(f"  version : {data['version']}")
print("  PASS")

# ── Start research job ──────────────────────────────────
sep("TEST 2: POST /research (Async Job Queue)")
r = httpx.post(
    f"{BASE}/research",
    json={"topic": "deep learning image recognition 2024"},
    timeout=10,
)
assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"
job = r.json()
job_id = job["job_id"]
print(f"  job_id  : {job_id}")
print(f"  status  : {job['status']}")
print(f"  topic   : {job.get('topic','')}")
print("  PASS - job created immediately (no 95s wait!)")

# ── Poll status ─────────────────────────────────────────
sep("TEST 3: GET /job/{id} - Polling Status")
print("  Polling every 3s (pipeline running in background)...\n")
for i in range(5):
    time.sleep(3)
    r = httpx.get(f"{BASE}/job/{job_id}")
    assert r.status_code == 200
    s = r.json()
    status   = s["status"]
    progress = s["progress"]
    stage    = s.get("stage", "")
    print(f"  [{i+1}] status={status:8s}  progress={progress:3d}%  stage={stage!r}")
    if status in ("done", "failed"):
        break

print("  PASS - polling works")

# ── Cache stats ──────────────────────────────────────────
sep("TEST 4: GET /cache/stats (Upstash Redis)")
r = httpx.get(f"{BASE}/cache/stats")
assert r.status_code == 200
stats = r.json()
print(f"  status   : {stats.get('status')}")
print(f"  provider : {stats.get('provider')}")
print(f"  db_size  : {stats.get('db_size')}")
print("  PASS")

# ── History ─────────────────────────────────────────────
sep("TEST 5: GET /history (Supabase)")
r = httpx.get(f"{BASE}/history")
assert r.status_code == 200
h = r.json()
print(f"  count   : {h.get('count', 0)}")
print(f"  records : {h.get('records', [])[:2]}")
print("  PASS (empty if Supabase not connected yet)")

# ── OpenAPI docs ─────────────────────────────────────────
sep("TEST 6: OpenAPI Docs")
r = httpx.get(f"{BASE}/docs")
assert r.status_code == 200
print(f"  Swagger UI accessible at: {BASE}/docs")
print("  PASS")

sep("ALL TESTS COMPLETE")
print("  Server: http://localhost:8001")
print("  Docs  : http://localhost:8001/docs")
print()
