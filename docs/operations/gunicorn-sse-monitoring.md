# Gunicorn + SSE monitoring checklist

Operational runbook after [ADR 0005 — Gunicorn worker scaling](../architecture/adr/0005-gunicorn-sse-worker-evolution.md) (phase 1 deploy). Review daily for **3–7 days**, then weekly until stable.

## Quick checks

```bash
# Startup config (workers, timeout)
docker compose logs django 2>&1 | rg "Gunicorn configuration" -A 10 | tail -12

# Worker processes
docker compose top django

# Health + system status (status requires reception:read token)
curl -s https://api.stay.hr/api/v1/reception/health/
curl -s -H "Authorization: Bearer $RECEPTION_API_TOKEN" \
  https://api.stay.hr/api/v1/reception/system/status/ | python3 -m json.tool

# Health latency benchmark (before/after Gunicorn changes)
./scripts/benchmark-health-latency.sh
# Snapshots also appended by load-test to data/ops/health-latency-benchmark.txt
```

## Signals

| Signal | Command / source | Healthy | Investigate |
|--------|------------------|---------|-------------|
| Active Gunicorn workers | `docker compose top django` | ~1 master + `GUNICORN_WORKERS` workers | Fewer workers after crash loop |
| Active SSE (per worker) | `GET /system/status` → `sse.active_connections` | Below worker count under normal load | **> 0** after load test teardown → leak; **> 30** aggregated → phase 2 |
| Peak SSE | `sse.peak_connections` | Trend stable after deploy | Sustained **> 30** aggregated → phase 2 |
| SSE lifetime | `sse.average_duration_seconds`, opened/closed totals | Stable | Drift or leak (opened >> closed) |
| Health p95 | `benchmark-health-latency.sh` | **< 500 ms** | **> 500 ms** sustained → phase 2 |
| Worker timeout | `docker compose logs django \| rg "WORKER TIMEOUT"` | **0** | Any hit → phase 2 trigger |
| SSE lifecycle | `docker compose logs django \| rg "sse_stream_"` | Opens/closes match usage | Stuck opens, very short durations |
| Access log SSE | `docker compose logs django \| rg "reservation-versions/stream"` | Steady during reception use | Missing streams when UI open |
| CPU / memory | `docker stats stay_django --no-stream` | Stable | Sustained high CPU with low traffic |
| Push vs poll | Operator feedback | Updates within ~1 s | Delays ~5 s only → poll fallback; shorter delays needed → Redis |

## Load test (after any Gunicorn env change)

```bash
export RECEPTION_API_TOKEN="<reception bearer token>"
export LOAD_TEST_RESERVATION_ID="<valid reservation pk>"
export LOAD_TEST_API_BASE="https://api.stay.hr"   # or http://127.0.0.1:8000 from django exec

./scripts/load-test-gunicorn-sse.sh
```

Must print **PASS** before production sign-off.

## CI smoke (optional)

GitHub Actions workflow [`.github/workflows/gunicorn-perf-smoke.yml`](../../.github/workflows/gunicorn-perf-smoke.yml) runs light mode when API is reachable:

```bash
BENCHMARK_LIGHT=1 OPS_CI_ARTIFACT_DIR=./ci-artifacts ./scripts/benchmark-health-latency.sh
LOAD_TEST_LIGHT=1 OPS_CI_ARTIFACT_DIR=./ci-artifacts RECEPTION_API_TOKEN=... LOAD_TEST_RESERVATION_ID=... ./scripts/load-test-gunicorn-sse.sh
```

Artifacts include `timestamp`, `git_sha`, and latency percentiles for cross-commit comparison.

## Phase 2 escalation

If timeouts return, health latency degrades under SSE load, or push reliability is business-critical, see [ADR 0005 — Phase 2 trigger criteria](../architecture/adr/0005-gunicorn-sse-worker-evolution.md#phase-2-trigger-criteria):

1. **Redis pub/sub** with standard event envelope (multi-worker fan-out).
2. **ASGI (Uvicorn)** for long-term SSE/WebSocket.

## Related

- [reservation-versioning.md](../architecture/reservation-versioning.md)
- [domain-setup.md](domain-setup.md)
