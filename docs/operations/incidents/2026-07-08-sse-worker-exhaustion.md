# Incident: Gunicorn SSE worker exhaustion (2026-07-08)

**Status:** Mitigated (emergency hotfix deployed) · **Phase 1 validation:** pending (3–7 day window)

**Related:** [ADR 0005 — Gunicorn worker scaling and SSE transport evolution](../../architecture/adr/0005-gunicorn-sse-worker-evolution.md) · [gunicorn-sse-monitoring.md](../gunicorn-sse-monitoring.md)

---

## Summary

Reception reservation version SSE (`GET /api/v1/reception/reservation-versions/stream/`) holds Gunicorn **sync** workers open for the lifetime of each browser tab. Under production load with a low worker count, concurrent SSE streams exhausted the worker pool. Remaining REST requests (`/health/`, `/sync-versions/`, reservation detail) queued until Gunicorn worker timeout — causing API hangs and operator-visible delays.

---

## Timeline

| Time (approx.) | Event |
|----------------|-------|
| Pre-incident | Production ran **2 sync workers** with `--timeout 120`. Reception reservation detail opened **2 SSE streams** per tab (messages + timeline version watch). |
| During incident | Reservation **#130** detail page open alongside other Reception tabs. `WORKER TIMEOUT` in django logs; `/health/` and `/sync-versions/` slow or timing out. |
| Detection | Daily ops report flagged health latency; log review showed `sse_stream_opened` distributed across workers with all workers holding long-lived streams. |
| Mitigation (same day) | Container restart restored service. Follow-up operational tuning: `GUNICORN_WORKERS=12`, `GUNICORN_TIMEOUT=3600`, `GuestMessagesPanel` → `transport: "poll"` (1 SSE per reservation detail instead of 2). |
| Post-incident | ADR 0005 amended with phased roadmap (2a Redis EventBus → 2b dedicated Uvicorn SSE). Phase 1 validation window started. |
| Recurrence (same day) | With `GUNICORN_WORKERS=12`, **12× `sse_stream_opened`, 0× `sse_stream_closed`** — worker pool saturated again (`payments` SSE on every open reservation detail). Restart restored service. |
| Emergency hotfix | Detail views → **poll only** (`messages` + `payments`). Backend **503** when per-worker SSE ≥ `GUNICORN_WORKERS - 1`. Polling retained until Phase 2a + 2b validated — see [runbook emergency section](../gunicorn-sse-monitoring.md#emergency-stabilization-2026-07-08-hotfix). |

---

## Root cause

1. **Architectural:** SSE on Gunicorn sync workers is a long-lived connection that blocks one worker per stream. In-process event fan-out only delivers push events to listeners on the **same worker** that holds the SSE connection (~1/N reliability with N workers).
2. **Capacity:** Worker count (2) was far below concurrent SSE demand during normal Reception use (multiple open reservation tabs × 2 streams each).
3. **Timeout mismatch:** Short Gunicorn timeout (120 s) was inappropriate for intentionally long-lived SSE; worker recycle under load compounded queueing.

Poll fallback (`useReservationVersionWatch` → `useTimelineVersionPoll`) kept UI partially usable (~5 s delay) but did not prevent API starvation.

---

## Impact

| Area | Effect |
|------|--------|
| Reception API | `/health/`, `/sync-versions/`, reservation detail requests queued or timed out |
| Operators | Delayed panel updates; intermittent 502/timeout on reservation detail (notably reservation #130) |
| Push reliability | SSE push missed on multi-worker setup even when workers were available |
| Duration | Service degraded until container restart; no data loss |

---

## Mitigation

### Phase 1 operational tuning (first response)

Operational adjustments within existing Phase 1 architecture — **not** new architecture:

| Change | Before | After | Rationale |
|--------|--------|-------|-----------|
| `GUNICORN_WORKERS` | 8 (incident env: 2) | **12** | More headroom for concurrent SSE + REST |
| `GUNICORN_TIMEOUT` | 120 (incident env) | **3600** | SSE connections are intentionally long-lived |
| `GuestMessagesPanel` transport | `"sse"` | **`"poll"`** | Reduce streams per reservation detail |
| Observability | — | Phase 1 metrics already deployed | `sse_stream_opened`/`closed`, `/system/status/`, load test gate |

Tuning alone was **insufficient**: recurrence showed 12 workers fully held by `payments` SSE on open detail tabs.

### Emergency production stabilization (hotfix)

Separate from Phase 2 architecture — keeps Reception REST healthy while Redis + Uvicorn are built:

| Change | Rationale |
|--------|-----------|
| `ReservationDetailPanel` → `transport: "poll"` (`payments`) | Eliminates the dominant SSE source on detail views |
| `GuestMessagesPanel` → `transport: "poll"` (`messages`) | No SSE from detail panels (both scopes poll) |
| SSE saturation guard → **503** when per-worker active SSE ≥ `GUNICORN_WORKERS - 1` | Last-resort protection if SSE is re-enabled elsewhere |

**Operational choice:** polling (~5 s delay) is acceptable until Phase **2a + 2b** are implemented and validated. Do **not** restore detail-view SSE until then.

**Follow-up (investigation):** zero `sse_stream_closed` during saturation may reflect open tabs **or** WSGI disconnect cleanup lag. Run the [lifecycle check](../gunicorn-sse-monitoring.md#sse-lifecycle-check-disconnect-cleanup) on a single deliberate open/close before assuming a lifecycle bug.

**Note:** Neither tuning nor hotfix replaces Phase 2 (Redis EventBus for cross-worker push; dedicated Uvicorn SSE for transport scaling).

---

## What went well

### Detection

- **Daily ops report** (`core.send_daily_ops_report`) surfaced health latency degradation.
- **Health endpoint timeouts** provided an early operator-visible signal.
- **Structured logs** (`sse_stream_opened` per `worker_pid`) made it possible to see SSE distribution across workers and confirm pool saturation.

### Recovery

- **Container restart** restored API responsiveness quickly with no data migration or schema change.

### Documentation

- **ADR 0005** already defined the evolution path (capacity → Redis → ASGI/Uvicorn), so the post-incident response was refinement and operational tuning rather than ad-hoc architecture.

### Observability

- Phase 1 SSE metrics (`active_connections`, `peak_connections`, opened/closed totals) and `GET /api/v1/reception/system/status/` enabled diagnosis without new instrumentation during the incident.

---

## Detection gaps

| Gap | Risk | Planned improvement |
|-----|------|---------------------|
| SSE counts are **per worker** — no single global counter in status API | Hard to see total concurrent SSE without log aggregation | Phase 2b: dedicated Uvicorn SSE service with service-level metrics |
| No automated alert on `WORKER TIMEOUT` | Relies on daily ops report or manual log review | Add to daily ops report threshold / alert when > 0 |
| Push miss rate not measured automatically | Operators notice ~5 s poll delay before ops does | Phase 2a validation: compare `touch` logs vs SSE delivery within 2 s |
| `redis_reconnect_count` not yet applicable | N/A until Phase 2a | Add to post-2a validation checklist |

---

## Action items

| Item | Owner | Status |
|------|-------|--------|
| Deploy Phase 1 operational tuning (`GUNICORN_WORKERS=12`, messages poll) | Ops | Done |
| Deploy emergency hotfix (detail poll + SSE 503 guard) | Ops / Engineering | Done |
| SSE disconnect lifecycle check (single tab open/close) | Engineering | **Pending** |
| Complete 3–7 day Phase 1 validation ([gunicorn-sse-monitoring.md](../gunicorn-sse-monitoring.md)) | Ops | **In progress** |
| Merge ADR 0005 amendment (phases 2a/2b/2c, EventBus contract) | Engineering | Done |
| Gate Phase 2a on: incident closed + validation + ADR triggers | Engineering / Ops | Pending validation |
| Implement `ReservationVersionEventBus` (Redis) | Engineering | Phase 2a — implemented (enable via `RESERVATION_VERSION_EVENT_BUS=redis`) |
| Implement dedicated Uvicorn SSE service | Engineering | Phase 2b — not started |

---

## Phase 2 gate (do not start 2a until all true)

1. **Incident closed** — this postmortem merged and ops sign-off
2. **Production validation complete** — Phase 1 runbook window (3–7 days) passed without regression
3. **ADR triggers justify architectural work** — measurable criteria in [ADR 0005 Phase 2 trigger criteria](../../architecture/adr/0005-gunicorn-sse-worker-evolution.md#phase-2-trigger-criteria-measurable)

Merging this postmortem alone is **not** sufficient to start Phase 2a code.

---

## Validation checklist (Phase 1 — post-incident)

- [ ] **3–7 days** elapsed since mitigation deploy
- [ ] **0** `WORKER TIMEOUT` in django logs
- [ ] Health latency p95 **< 500 ms** (`./scripts/benchmark-health-latency.sh`)
- [ ] Aggregated active SSE **< 30** under normal load
- [ ] Load test **PASS** (`./scripts/load-test-gunicorn-sse.sh`)
- [ ] Ops sign-off

When all boxes checked → incident fully closed; Phase 2a may proceed if ADR triggers also met.
