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

**Invariant:** `connections_opened_total − connections_closed_total = active_connections` (and `active_stream_count`). Example: opened=400, closed=387 ⇒ **13** living streams. Alarm when `invariant_delta != 0` or `active_connections > 0` long after load-test teardown.

Structured fields (correlate one connection end-to-end):

| Field | Where |
|-------|--------|
| `stream_id` | `sse_stream_opened` / `sse_stream_closed`, `X-SSE-Stream-Id`, `connected` SSE payload |
| `close_reason` | `client_disconnect` \| `exception` \| `unknown` on `sse_stream_closed` |
| `opened_at` / `closed_at` | ISO-8601 UTC on both log lines |
| `last_heartbeat` | Per-stream registry via `/system/status` → `sse.active_streams[]` |
| BFF (reception) | `bff_sse_proxy_start`, `bff_sse_upstream_connected`, `bff_sse_client_aborted` with `upstream_abort_wired: true` |

`/system/status` SSE block (per worker):

| Field | Healthy |
|-------|---------|
| `active_connections` / `active_stream_count` | Match; fall to **0** after deliberate close |
| `active_streams` | Compact list of live streams (`stream_id`, reservation, scope, timestamps) |
| `invariant_ok` | **true** |
| `invariant_delta` | **0** (`opened − closed − active`) |
| `components.sse.status` | **healthy** (derived; `invariant_breach` if delta ≠ 0) |
| `components.event_bus.status` | **healthy** (or `warning`/`critical` + `reason` from raw EventBus fields) |
| `components.database.status` | **healthy** |
| Log `sse_invariant_breach` | **absent** |

Verify cleanup after a deliberate tab close:

1. Hard-refresh Reception so detail panels use poll (no new SSE from `messages`/`payments`) — keep checkin SSE when deliberately testing that path.
2. From a test client or browser, open **one** SSE stream.
3. Confirm `sse_stream_opened` with a `stream_id`.
4. Close the tab or call `EventSource.close()`.
5. Within ~30 s (next heartbeat write), confirm `sse_stream_closed` for the **same** `stream_id` and `close_reason=client_disconnect`.
6. Confirm `/system/status` → `invariant_delta == 0` and `active_connections == 0`.
7. Lifecycle proof: `./scripts/prove-sse-proxy-disconnect.sh` — Phase A (direct Django) + Phase B (BFF with AbortSignal wired).

If step 5 never fires after a clean single-tab test, file a follow-up for WSGI disconnect detection — independent of the poll hotfix. If BFF logs `bff_sse_client_aborted` with `upstream_abort_wired: true` but Django never closes that `stream_id`, investigate AbortSignal propagation or a proxy buffering layer.
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
| SSE invariant | `sse.invariant_delta`, `sse.invariant_ok` | **delta=0**, `ok=true` | `invariant_delta != 0` or `sse_invariant_breach` log → leak/drift |
| SSE lifetime | `sse.average_duration_seconds`, opened/closed totals | Stable; opened−closed=active | Drift or leak (opened >> closed) |
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

## Phase 1 lifecycle instrumentation — permanent

Phase 1 lifecycle is **closed**. Keep these on through Phase **2a (Redis)** and **2b (Uvicorn)** — Redis/Uvicorn do not replace disconnect proof:

| Layer | Keep |
|-------|------|
| BFF | AbortSignal; `bff_sse_proxy_start` / `bff_sse_upstream_connected` / `bff_sse_client_aborted` |
| Django | `stream_id`, `sse_stream_opened` / `sse_stream_closed`, registry, `check_sse_invariant` |
| Status / ops | `/system/status` → `sse.*`; daily ops CRIT on `sse_invariant_breach` |

**Rule:** no calendar “N days PASS” gate blocks Redis. During normal use, if leak or saturation returns → stop and analyze (`stream_id`, `invariant_delta`, registry). If it does not recur → continue Phase 2a. Observation scripts remain optional diagnostics, not a Phase 2a lock.

Optional daily snapshot: `./scripts/observe-sse-lifecycle.sh --append-log` → [sse-lifecycle-observation-log.md](sse-lifecycle-observation-log.md).

**Healthy signals:**

- [ ] `sse.invariant_delta == 0` / `invariant_ok == true` on `GET /system/status`
- [ ] `components.sse` / `components.event_bus` / `components.database` are **healthy** (or known `warning` with `reason`)
- [ ] No `sse_invariant_breach` in django logs (`docker compose logs django | rg sse_invariant_breach`)
- [ ] `active_connections` / registry list matches real Reception tabs (or falls to 0 when idle)
- [ ] `opened ≈ closed + active` (docker log totals / `docker_signals.json`)

Daily ops email also surfaces `sse.invariant_delta` / `docker.sse_invariant_breach` (**CRIT** on breach).

## Post-Phase 1 validation (capacity / incident)

After [2026-07-08 incident mitigation](incidents/2026-07-08-sse-worker-exhaustion.md) or any Gunicorn env change:

- [ ] **0** `WORKER TIMEOUT` in django logs
- [ ] Health latency p95 **< 500 ms**
- [ ] Aggregated active SSE **< 30** under normal Reception load
- [ ] Load test **PASS**
- [ ] SSE opened/closed ratio stable (no leak); `invariant_delta == 0`
- [ ] Phase 1 lifecycle gate: single-tab + BFF AbortSignal + direct Django close proofs
- [ ] Lifecycle instrumentation still present (not stripped for “cleanup”)
- [ ] Ops aware → Phase 2a may proceed if no open leak and ADR triggers / product need justify Redis

## Post-Phase 2a validation (14 days)

After enabling `RESERVATION_VERSION_EVENT_BUS=redis`:

- [ ] **Lifecycle instrumentation still on** (registry, invariant, BFF/Django logs, `/system/status`) — Redis does not replace disconnect proof
- [ ] Push reliability: `touch` → SSE delivery within **2 s**
- [ ] Celery-originated publishes delivered to SSE clients
- [ ] SSE reconnect rate stable (`sse_stream_opened` / `sse_stream_closed` ratio)
- [ ] Health latency p95 **< 500 ms** (unchanged from Phase 1 baseline)
- [ ] **`redis_reconnect_count`** stable — if rising, investigate Redis connectivity before Phase 2b
- [ ] Rollback drill: `RESERVATION_VERSION_EVENT_BUS=in_process` + recreate django/celery restores prior behaviour
- [ ] Ops sign-off before enabling `SSE_TRANSPORT=uvicorn` in production

## Post-Phase 2b validation (14 days)

After enabling `SSE_TRANSPORT=uvicorn` (dedicated Uvicorn SSE service):

- [ ] **Lifecycle instrumentation still on** on the SSE service (stream registry / invariant / opened-closed); REST `/system/status` on Gunicorn remains useful for capacity
- [ ] Gunicorn worker pool no longer saturated by SSE under normal load
- [ ] SSE active count tracked on Uvicorn service; Gunicorn REST `/health/` unaffected
- [ ] REST endpoints never routed to Uvicorn (only `reservation-versions/stream/`)
- [ ] Rollback drill: `SSE_TRANSPORT=gunicorn` + Traefik routes all API to `stay_django`
- [ ] Ops sign-off

## Phase 2 escalation

### Phase 2a — Redis EventBus (distribution)

Escalate when push reliability is business-critical or ADR triggers met **and** lifecycle instrumentation is still on (no open unresolved leak):

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
