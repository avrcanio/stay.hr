# Gunicorn + SSE monitoring checklist

Operational runbook after [ADR 0005 — Gunicorn worker scaling](../architecture/adr/0005-gunicorn-sse-worker-evolution.md) (Phase 1 deploy). Review daily for **3–7 days**, then weekly until stable.

**Incident postmortem:** [2026-07-08 SSE worker exhaustion](incidents/2026-07-08-sse-worker-exhaustion.md)

## Emergency stabilization (2026-07-08 hotfix)

Reception reservation **detail views** temporarily use **poll only** — no SSE streams from detail panels:

| Component | Scope | Transport |
|-----------|-------|-----------|
| `GuestMessagesPanel` | `messages` | `poll` |
| `ReservationDetailPanel` | `payments` | `poll` |

Backend guard: before opening a new SSE stream, reject with **503** when the **current worker's** active SSE count is `>= GUNICORN_WORKERS - 1` (log: `sse_stream_rejected`). Clients with SSE enabled elsewhere should fall back to poll on 503.

**Keep polling on detail views** until Phase **2a** (Redis `ReservationVersionEventBus`) and **2b** (dedicated Uvicorn SSE) are deployed **and** pass their validation windows. Do not re-enable SSE on detail views just because Uvicorn exists — restore only after the full Redis + Uvicorn path is stable.

To restore SSE on detail views later: remove explicit `transport: "poll"` from the two components above after ops sign-off on Post-Phase 2b validation.

### SSE lifecycle check (disconnect cleanup)

`opened` vs `closed` log totals are **per worker** and only increment on that worker process. Zero `sse_stream_closed` during saturation can mean many tabs still open **or** a disconnect cleanup gap.

Verify cleanup after a deliberate tab close:

1. Hard-refresh Reception so detail panels use poll (no new SSE from detail).
2. From a test client or browser devtools, open **one** SSE stream (e.g. list view or manual `EventSource` to `reservation-versions/stream/`).
3. Confirm `sse_stream_opened` in django logs for that `reservation_id` / `scope`.
4. Close the tab or call `EventSource.close()`.
5. Within ~30 s (next heartbeat), confirm `sse_stream_closed` for the same worker PID.

If step 5 never fires after a clean single-tab test, file a follow-up bug for WSGI disconnect detection — independent of the poll hotfix.

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

## Symptom → phase → document

| Symptom | Likely phase | Document |
|---------|--------------|----------|
| `WORKER TIMEOUT`, health timeout, API hang with open Reception tabs | Phase 1 (capacity) | This runbook |
| Push miss, updates only after ~5 s poll, Celery change not reflected live | Phase 2a (distribution) | [ADR 0005 Phase 2a](../architecture/adr/0005-gunicorn-sse-worker-evolution.md) |
| High concurrent SSE, REST healthy but need many streams | Phase 2b (transport) | [ADR 0005 Phase 2b](../architecture/adr/0005-gunicorn-sse-worker-evolution.md) |
| Redis reconnect count rising, push flaky across all transports | Phase 2a infra | ADR 0005 + Redis ops |
| Need WebSocket / full async Django | Phase 2c (optional) | [ADR 0005 Phase 2c](../architecture/adr/0005-gunicorn-sse-worker-evolution.md) |

## Signals

| Signal | Command / source | Healthy | Investigate |
|--------|------------------|---------|-------------|
| Active Gunicorn workers | `docker compose top django` | ~1 master + `GUNICORN_WORKERS` workers | Fewer workers after crash loop |
| Active SSE (per worker) | `GET /system/status` → `sse.active_connections` | Below worker count under normal load | **> 0** after load test teardown → leak; **> 30** aggregated → Phase 2 |
| Peak SSE | `sse.peak_connections` | Trend stable after deploy | Sustained **> 30** aggregated → Phase 2 |
| SSE lifetime | `sse.average_duration_seconds`, opened/closed totals | Stable | Drift or leak (opened >> closed) |
| Health p95 | `benchmark-health-latency.sh` | **< 500 ms** | **> 500 ms** sustained → Phase 2 trigger |
| Worker timeout | `docker compose logs django \| rg "WORKER TIMEOUT"` | **0** | Any hit → Phase 2 trigger |
| SSE lifecycle | `docker compose logs django \| rg "sse_stream_"` | Opens/closes match usage | Stuck opens, very short durations |
| Access log SSE | `docker compose logs django \| rg "reservation-versions/stream"` | Steady during reception use | Missing streams when UI open |
| CPU / memory | `docker stats stay_django --no-stream` | Stable | Sustained high CPU with low traffic |
| Push vs poll | Operator feedback | Updates within ~1 s | Delays ~5 s only → poll fallback; shorter delays needed → Phase 2a |
| Redis reconnect (Phase 2a+) | `redis_reconnect_count` metric / logs | Stable, near zero | Rising → Redis connectivity problem, not SSE transport |

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

## Post-Phase 1 validation (3–7 days)

After [2026-07-08 incident mitigation](incidents/2026-07-08-sse-worker-exhaustion.md) or any Gunicorn env change:

- [ ] **0** `WORKER TIMEOUT` in django logs
- [ ] Health latency p95 **< 500 ms**
- [ ] Aggregated active SSE **< 30** under normal Reception load
- [ ] Load test **PASS**
- [ ] SSE opened/closed ratio stable (no leak)
- [ ] Ops sign-off → incident closed; Phase 2a gate may proceed if ADR triggers also met

## Post-Phase 2a validation (14 days)

After enabling `RESERVATION_VERSION_EVENT_BUS=redis`:

- [ ] Push reliability: `touch` → SSE delivery within **2 s**
- [ ] Celery-originated publishes delivered to SSE clients
- [ ] SSE reconnect rate stable (`sse_stream_opened` / `sse_stream_closed` ratio)
- [ ] Health latency p95 **< 500 ms** (unchanged from Phase 1 baseline)
- [ ] **`redis_reconnect_count`** stable — if rising, investigate Redis connectivity before Phase 2b
- [ ] Rollback drill: `RESERVATION_VERSION_EVENT_BUS=in_process` + recreate django/celery restores prior behaviour
- [ ] Ops sign-off before enabling `SSE_TRANSPORT=uvicorn` in production

## Post-Phase 2b validation (14 days)

After enabling `SSE_TRANSPORT=uvicorn` (dedicated Uvicorn SSE service):

- [ ] Gunicorn worker pool no longer saturated by SSE under normal load
- [ ] SSE active count tracked on Uvicorn service; Gunicorn REST `/health/` unaffected
- [ ] REST endpoints never routed to Uvicorn (only `reservation-versions/stream/`)
- [ ] Rollback drill: `SSE_TRANSPORT=gunicorn` + Traefik routes all API to `stay_django`
- [ ] Ops sign-off

## Phase 2 escalation

### Phase 2a — Redis EventBus (distribution)

Escalate when push reliability is business-critical or ADR triggers met **and** Phase 2a gate passed (incident closed + Phase 1 validation + triggers):

- `RESERVATION_VERSION_EVENT_BUS=redis`
- Channel: `stay:v1:reservation_version:{tenant_slug}`
- See [ADR 0005 — EventBus](../architecture/adr/0005-gunicorn-sse-worker-evolution.md#reservationversioneventbus-abstraction)

### Phase 2b — dedicated Uvicorn SSE (transport)

Escalate when Phase 2a validation passed **and** Gunicorn still saturated by SSE or `peak_connections` > `GUNICORN_WORKERS × 3`:

- `SSE_TRANSPORT=uvicorn`
- Only `GET /api/v1/reception/reservation-versions/stream/` on Uvicorn; REST stays on Gunicorn
- See [ADR 0005 — Phase 2b invariant](../architecture/adr/0005-gunicorn-sse-worker-evolution.md)

### Phase 2c — full Django ASGI (optional)

Only when whole-app async is independently justified — not required for SSE scaling.

## Related

- [2026-07-08 SSE worker exhaustion postmortem](incidents/2026-07-08-sse-worker-exhaustion.md)
- [reservation-versioning.md](../architecture/reservation-versioning.md)
- [domain-setup.md](domain-setup.md)
