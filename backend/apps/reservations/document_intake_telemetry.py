"""Document intake OCR telemetry — write-only analysis layer.

Score reproducibility:
- ``computed_at`` is metadata only; excluded from score/reason math.
- No tenant_id, reservation_id, or job_id in score functions.
- Persons/images iterated in sorted index order.
- Reason dedup via ``sorted(set(...))``.
- ``round()`` applied once per component score and once for composite ``quality_score``.
"""

from __future__ import annotations

import json
import statistics
from datetime import date, timedelta
from io import BytesIO
from typing import Any, Iterable

from django.utils import timezone
from PIL import Image

from apps.reservations.document_intake_failure_reasons import OCRFailureReason
from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobStatus, Reservation

TELEMETRY_SCHEMA_VERSION = 1
QUALITY_MODEL_ID = "ocr-quality-v1"
PIPELINE_VERSION = "document-intake-v1"

RESOLUTION_THRESHOLD_PX = 800

_QUALITY_WEIGHTS = {
    "resolution": 0.15,
    "mrz_coverage": 0.25,
    "pairing": 0.20,
    "names": 0.25,
    "completeness": 0.15,
}


def build_document_intake_telemetry(
    *,
    ocr_result: dict,
    image_bytes_list: list[bytes] | None = None,
    matches: list[dict] | None = None,
    reservation: Reservation | None = None,
    image_count: int = 0,
    job_status: str = DocumentIntakeJobStatus.DONE,
) -> dict[str, Any]:
    """Pure orchestration: canonical inputs → telemetry dict (no DB writes)."""
    if job_status == DocumentIntakeJobStatus.FAILED:
        return _build_failed_telemetry(ocr_result=ocr_result)

    persons = _as_person_list(ocr_result.get("persons"))
    images_meta = _images_meta_by_index(ocr_result.get("images"))
    matches = matches if isinstance(matches, list) else []

    image_signals = _build_image_signals(image_bytes_list, image_count=image_count)
    images_telemetry = _build_images_telemetry(images_meta, image_signals)
    persons_telemetry = _build_persons_telemetry(persons, images_meta)

    job_reasons: list[str] = []
    job_metrics = _build_job_metrics(
        persons=persons,
        matches=matches,
        ocr_result=ocr_result,
        image_count=image_count,
        reservation=reservation,
        job_reasons=job_reasons,
    )

    quality_components = {
        "resolution": _compute_resolution_component(image_signals),
        "mrz_coverage": _compute_mrz_coverage_component(persons, images_meta),
        "pairing": _compute_pairing_component(
            persons=persons,
            image_count=image_count,
            unassigned_count=len(job_metrics.get("unassigned_indices") or []),
        ),
        "names": _compute_names_component(persons),
        "completeness": _compute_completeness_component(
            is_complete=job_metrics.get("is_complete"),
            ocr_under_extracted=bool(job_metrics.get("ocr_under_extracted")),
        ),
    }
    quality_score, quality_components = _calculate_quality_score(quality_components)

    summary_reasons = _derive_summary_reasons(
        images_telemetry=images_telemetry,
        persons_telemetry=persons_telemetry,
        job_reasons=job_reasons,
    )

    return {
        "schema_version": TELEMETRY_SCHEMA_VERSION,
        "quality_model": QUALITY_MODEL_ID,
        "pipeline_version": PIPELINE_VERSION,
        "computed_at": timezone.now().isoformat(),
        "quality_score": quality_score,
        "quality_components": quality_components,
        "summary_reasons": summary_reasons,
        "images": images_telemetry,
        "persons": persons_telemetry,
        "job_metrics": {
            k: v
            for k, v in job_metrics.items()
            if k
            not in {
                "unassigned_indices",
                "is_complete",
            }
        },
    }


def attach_document_intake_telemetry(ocr_result: dict, telemetry: dict) -> dict:
    """Merge telemetry into ocr_result; preserve unknown keys from prior ``_telemetry``."""
    existing = ocr_result.get("_telemetry")
    if not isinstance(existing, dict):
        existing = {}
    merged = {**existing, **telemetry}
    ocr_result["_telemetry"] = merged
    return ocr_result


def aggregate_telemetry_kpis(
    jobs: Iterable[DocumentIntakeJob],
    *,
    quality_model: str | None = None,
    pipeline_version: str | None = None,
) -> dict[str, Any]:
    """All KPI / reason-distribution logic for CLI and future OCR-G API."""
    processed = 0
    done_count = 0
    failed_count = 0
    missing_telemetry = 0
    quality_scores: list[int] = []
    auto_apply_total = 0
    auto_apply_yes = 0
    unknown_person_total = 0
    unknown_person_yes = 0
    completeness_total = 0
    ocr_under_extracted_yes = 0
    reason_counts: dict[str, int] = {}
    tenant_mismatch = 0

    for job in jobs:
        processed += 1
        if job.status == DocumentIntakeJobStatus.DONE:
            done_count += 1
        elif job.status == DocumentIntakeJobStatus.FAILED:
            failed_count += 1

        if job.reservation_id and job.tenant_id != job.reservation.tenant_id:
            tenant_mismatch += 1

        parsed = _parse_telemetry_blob(job.ocr_result or {})
        if parsed is None:
            missing_telemetry += 1
            continue
        if quality_model and parsed.get("quality_model") != quality_model:
            continue
        if pipeline_version and parsed.get("pipeline_version") != pipeline_version:
            continue

        score = parsed.get("quality_score")
        if isinstance(score, int):
            quality_scores.append(score)
        elif isinstance(score, float):
            quality_scores.append(int(round(score)))

        job_metrics = parsed.get("job_metrics") or {}
        match_count = int(job_metrics.get("match_count") or 0)
        auto_apply_count = int(job_metrics.get("auto_apply_count") or 0)
        unknown_count = int(job_metrics.get("unknown_person_count") or 0)
        auto_apply_total += match_count
        auto_apply_yes += auto_apply_count
        unknown_person_total += len(parsed.get("persons") or [])
        unknown_person_yes += unknown_count

        completeness_total += 1
        if job_metrics.get("ocr_under_extracted"):
            ocr_under_extracted_yes += 1

        for reason in parsed.get("summary_reasons") or []:
            key = str(reason)
            reason_counts[key] = reason_counts.get(key, 0) + 1

    top_reasons = sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))[:10]

    return {
        "processed": processed,
        "done_count": done_count,
        "failed_count": failed_count,
        "missing_telemetry": missing_telemetry,
        "quality_scores": quality_scores,
        "quality_stats": _quality_stats(quality_scores),
        "auto_apply_rate": _safe_rate(auto_apply_yes, auto_apply_total),
        "unknown_person_rate": _safe_rate(unknown_person_yes, unknown_person_total),
        "ocr_under_extracted_rate": _safe_rate(ocr_under_extracted_yes, completeness_total),
        "top_reasons": top_reasons,
        "tenant_mismatch": tenant_mismatch,
    }


def load_document_intake_quality_kpis(
    *,
    days: int,
    tenant_id: int | None = None,
    quality_model: str | None = QUALITY_MODEL_ID,
    pipeline_version: str | None = None,
) -> dict[str, Any]:
    """Load aggregate KPIs for the last N days (shared by CLI and email task)."""
    days = max(1, int(days))
    since = timezone.now() - timedelta(days=days)

    qs = DocumentIntakeJob.objects.filter(processed_at__gte=since).select_related(
        "reservation"
    )
    if tenant_id is not None:
        qs = qs.filter(tenant_id=tenant_id)

    return aggregate_telemetry_kpis(
        qs.order_by("-processed_at", "-id"),
        quality_model=quality_model,
        pipeline_version=pipeline_version,
    )


def format_report_email_subject(*, days: int, report_date: date) -> str:
    day_label = "1 day" if days == 1 else f"{days} days"
    return f"Stay.hr OCR Quality Report • {day_label} • {report_date.isoformat()}"


def format_telemetry_report(
    kpis: dict[str, Any],
    *,
    as_json: bool = False,
    previous_snapshot: dict | None = None,
    for_email: bool = False,
) -> str:
    """Presentation only — no business logic."""
    if as_json:
        return json.dumps(kpis, indent=2, sort_keys=True)

    lines: list[str] = []
    lines.append("Document intake quality report")
    lines.append("=" * 32)
    lines.append("")
    lines.append("Volume")
    lines.append(f"  processed:          {kpis.get('processed', 0)}")
    lines.append(f"  done:               {kpis.get('done_count', 0)}")
    lines.append(f"  failed:             {kpis.get('failed_count', 0)}")
    lines.append(f"  missing telemetry:  {kpis.get('missing_telemetry', 0)}")
    lines.append("")

    stats = kpis.get("quality_stats") or {}
    lines.append("Quality (quality_score)")
    lines.append(f"  mean:   {stats.get('mean')}")
    lines.append(f"  median: {stats.get('median')}")
    lines.append(f"  p10:    {stats.get('p10')}")
    lines.append(f"  p90:    {stats.get('p90')}")
    lines.append("")

    lines.append("Matching")
    lines.append(f"  auto_apply_rate:      {kpis.get('auto_apply_rate')}")
    lines.append(f"  unknown_person_rate:  {kpis.get('unknown_person_rate')}")
    lines.append("")

    lines.append("Completeness")
    lines.append(f"  ocr_under_extracted_rate: {kpis.get('ocr_under_extracted_rate')}")
    lines.append("")

    lines.append("Reason distribution (top 10)")
    for reason, count in kpis.get("top_reasons") or []:
        lines.append(f"  {reason}: {count}")
    if not kpis.get("top_reasons"):
        lines.append("  (none)")
    lines.append("")

    lines.append("Tenant health")
    lines.append(f"  tenant_id != reservation.tenant_id: {kpis.get('tenant_mismatch', 0)} (expect 0)")

    if for_email:
        lines.extend(_format_email_only_sections(kpis, previous_snapshot))

    return "\n".join(lines)


def _format_email_only_sections(
    kpis: dict[str, Any],
    previous_snapshot: dict | None,
) -> list[str]:
    lines: list[str] = ["", "Health"]
    lines.extend(_format_health_section(kpis))
    lines.append("")
    lines.append("Trends (vs previous report)")
    if previous_snapshot is None:
        lines.append("  (no previous report)")
    else:
        previous_kpis = previous_snapshot.get("kpis") or {}
        lines.extend(_format_trends_section(kpis, previous_kpis))
    lines.append("")
    lines.append("New reasons since previous report")
    if previous_snapshot is None:
        lines.append("  (no previous report)")
    else:
        previous_reasons = _top_reason_keys(previous_snapshot.get("top_reasons"))
        current_reasons = _top_reason_keys(kpis.get("top_reasons"))
        new_reasons = sorted(current_reasons - previous_reasons)
        if new_reasons:
            for reason in new_reasons:
                lines.append(f"  + {reason}")
        else:
            lines.append("  No new regression reasons.")
    return lines


def _format_health_section(kpis: dict[str, Any]) -> list[str]:
    mismatch = int(kpis.get("tenant_mismatch") or 0)
    mismatch_label = f"OK ({mismatch})" if mismatch == 0 else f"ALERT ({mismatch})"

    processed = int(kpis.get("processed") or 0)
    missing = int(kpis.get("missing_telemetry") or 0)
    coverage = round(100 * (processed - missing) / max(processed, 1))
    failed = int(kpis.get("failed_count") or 0)

    return [
        f"  Tenant mismatch .......... {mismatch_label}",
        f"  Telemetry coverage ....... {coverage}%",
        f"  Failed jobs .............. {failed}",
    ]


def _format_trends_section(current: dict[str, Any], previous: dict[str, Any]) -> list[str]:
    current_stats = current.get("quality_stats") or {}
    previous_stats = previous.get("quality_stats") or {}
    return [
        "  "
        + _format_metric_delta_line(
            "Quality score (mean)",
            current_stats.get("mean"),
            previous_stats.get("mean"),
        ),
        "  "
        + _format_metric_delta_line(
            "Unknown person rate",
            current.get("unknown_person_rate"),
            previous.get("unknown_person_rate"),
            as_percent=True,
        ),
        "  "
        + _format_metric_delta_line(
            "OCR under-extracted",
            current.get("ocr_under_extracted_rate"),
            previous.get("ocr_under_extracted_rate"),
            as_percent=True,
        ),
        "  "
        + _format_metric_delta_line(
            "Auto-apply rate",
            current.get("auto_apply_rate"),
            previous.get("auto_apply_rate"),
            as_percent=True,
        ),
    ]


def _format_metric_delta_line(
    label: str,
    current: float | int | None,
    previous: float | int | None,
    *,
    as_percent: bool = False,
) -> str:
    delta = _format_metric_delta(current, previous, as_percent=as_percent)
    if as_percent and current is not None:
        value = f"{round(float(current) * 100, 1)}%"
    elif current is not None:
        value = str(current)
    else:
        value = "—"
    return f"{label} .... {value}  {delta}"


def _format_metric_delta(
    current: float | int | None,
    previous: float | int | None,
    *,
    as_percent: bool = False,
) -> str:
    if current is None or previous is None:
        return "—"
    try:
        cur = float(current)
        prev = float(previous)
    except (TypeError, ValueError):
        return "—"
    diff = cur - prev
    if as_percent:
        diff_display = f"{round(diff * 100, 1)}%"
    elif abs(diff - round(diff)) < 1e-9:
        diff_display = f"{int(round(diff))}"
    else:
        diff_display = f"{round(diff, 1)}"
    if diff > 0:
        return f"▲ +{diff_display}"
    if diff < 0:
        return f"▼ {diff_display}"
    return "— 0"


def _top_reason_keys(top_reasons: Any) -> set[str]:
    if not isinstance(top_reasons, list):
        return set()
    keys: set[str] = set()
    for item in top_reasons:
        if isinstance(item, (list, tuple)) and item:
            keys.add(str(item[0]))
    return keys


def _build_failed_telemetry(*, ocr_result: dict) -> dict[str, Any]:
    job_reasons = [OCRFailureReason.OCR_FAILED.value]
    return {
        "schema_version": TELEMETRY_SCHEMA_VERSION,
        "quality_model": QUALITY_MODEL_ID,
        "pipeline_version": PIPELINE_VERSION,
        "computed_at": timezone.now().isoformat(),
        "quality_score": 0,
        "quality_components": {
            "resolution": {"score": 0, "min_edge_px": None, "image_count": 0, "below_threshold_count": 0, "threshold_px": RESOLUTION_THRESHOLD_PX},
            "mrz_coverage": {"score": 0, "id_side_count": 0, "with_mrz_count": 0},
            "pairing": {"score": 0, "unassigned_count": 0, "image_count": 0},
            "names": {"score": 0, "person_count": 0, "named_count": 0},
            "completeness": {"score": 0, "is_complete": False, "ocr_under_extracted": False},
        },
        "summary_reasons": _derive_summary_reasons(
            images_telemetry=[],
            persons_telemetry=[],
            job_reasons=job_reasons,
        ),
        "images": [],
        "persons": [],
        "job_metrics": {
            "auto_apply_count": 0,
            "match_count": 0,
            "unknown_person_count": 0,
            "ocr_under_extracted": False,
            "orphan_pass_ran": bool((ocr_result.get("_orphan_pass") or {}).get("ran")),
        },
    }


def _as_person_list(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    return [p for p in raw if isinstance(p, dict)]


def _images_meta_by_index(raw: Any) -> dict[int, dict]:
    result: dict[int, dict] = {}
    if not isinstance(raw, list):
        return result
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index", -1))
        except (TypeError, ValueError):
            continue
        if idx >= 0:
            result[idx] = item
    return result


def _non_empty_mrz_lines(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(line).strip() for line in raw if str(line).strip()]


def _measure_min_edge(data: bytes) -> int | None:
    try:
        with Image.open(BytesIO(data)) as im:
            w, h = im.size
            return min(w, h)
    except Exception:
        return None


def _build_image_signals(
    image_bytes_list: list[bytes] | None,
    *,
    image_count: int,
) -> list[dict[str, Any]]:
    count = image_count
    if image_bytes_list:
        count = max(count, len(image_bytes_list))
    signals: list[dict[str, Any]] = []
    for idx in range(count):
        min_edge: int | None = None
        if image_bytes_list and idx < len(image_bytes_list):
            min_edge = _measure_min_edge(image_bytes_list[idx])
        signals.append({"index": idx, "min_edge_px": min_edge})
    return signals


def _detect_image_reasons(image_meta: dict, signals: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    side = str(image_meta.get("side") or "").lower()

    if side == "non_document":
        reasons.append(OCRFailureReason.NON_DOCUMENT_IMAGE.value)

    min_edge = signals.get("min_edge_px")
    if isinstance(min_edge, int) and min_edge < RESOLUTION_THRESHOLD_PX:
        reasons.append(OCRFailureReason.IMAGE_TOO_SMALL.value)

    if side in {"back", "passport"}:
        mrz = _non_empty_mrz_lines(image_meta.get("mrz_lines"))
        if not mrz:
            reasons.append(OCRFailureReason.NO_MRZ.value)
        elif len(mrz) < 2:
            reasons.append(OCRFailureReason.MRZ_PARTIAL.value)

    return sorted(set(reasons))


def _detect_person_reasons(person: dict, images_meta: dict[int, dict]) -> list[str]:
    reasons: list[str] = []
    given = str(person.get("given_names") or "").strip()
    surnames = str(person.get("surnames") or "").strip()
    doc_type = str(person.get("document_type") or "national_id").lower()
    is_passport = doc_type == "passport"

    if not given and not surnames:
        reasons.append(OCRFailureReason.UNKNOWN_PERSON.value)

    front_idx = _optional_index(person.get("front_image_index"))
    back_idx = _optional_index(person.get("back_image_index"))

    if front_idx is None:
        reasons.append(OCRFailureReason.FRONT_NOT_FOUND.value)
    else:
        front_meta = images_meta.get(front_idx)
        if front_meta is None or str(front_meta.get("side") or "").lower() in {"unknown", "non_document"}:
            reasons.append(OCRFailureReason.FRONT_NOT_FOUND.value)
        elif not given and not surnames:
            front_side = str(front_meta.get("side") or "").lower()
            front_mrz = _non_empty_mrz_lines(
                person.get("mrz_lines") or front_meta.get("mrz_lines")
            )
            if front_side in {"front", "passport"} and not front_mrz:
                reasons.append(OCRFailureReason.FACE_ONLY.value)

    if not is_passport:
        if back_idx is None:
            reasons.append(OCRFailureReason.BACK_NOT_FOUND.value)
        else:
            back_meta = images_meta.get(back_idx)
            if back_meta is None or str(back_meta.get("side") or "").lower() in {"unknown", "non_document"}:
                reasons.append(OCRFailureReason.BACK_NOT_FOUND.value)
            else:
                mrz = _non_empty_mrz_lines(
                    person.get("mrz_lines") or (back_meta or {}).get("mrz_lines")
                )
                if not mrz:
                    reasons.append(OCRFailureReason.NO_MRZ.value)
                elif len(mrz) < 2:
                    reasons.append(OCRFailureReason.MRZ_PARTIAL.value)

    return sorted(set(reasons))


def _optional_index(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        idx = int(raw)
    except (TypeError, ValueError):
        return None
    return idx if idx >= 0 else None


def _build_images_telemetry(
    images_meta: dict[int, dict],
    image_signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    signals_by_index = {item["index"]: item for item in image_signals}
    indices = sorted(set(images_meta.keys()) | set(signals_by_index.keys()))
    result: list[dict[str, Any]] = []
    for idx in indices:
        meta = images_meta.get(idx, {"index": idx})
        signals = signals_by_index.get(idx, {"index": idx, "min_edge_px": None})
        result.append(
            {
                "index": idx,
                "reasons": _detect_image_reasons(meta, signals),
                "signals": {"min_edge_px": signals.get("min_edge_px")},
            }
        )
    return result


def _build_persons_telemetry(
    persons: list[dict],
    images_meta: dict[int, dict],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for person_index, person in enumerate(persons):
        result.append(
            {
                "person_index": person_index,
                "reasons": _detect_person_reasons(person, images_meta),
            }
        )
    return result


def _build_job_metrics(
    *,
    persons: list[dict],
    matches: list[dict],
    ocr_result: dict,
    image_count: int,
    reservation: Reservation | None,
    job_reasons: list[str],
) -> dict[str, Any]:
    auto_apply_count = sum(1 for m in matches if isinstance(m, dict) and m.get("auto_apply"))
    unknown_person_count = sum(
        1
        for p in persons
        if not str(p.get("given_names") or "").strip() and not str(p.get("surnames") or "").strip()
    )

    unassigned = _unassigned_image_indices(persons=persons, image_count=image_count)
    if unassigned:
        job_reasons.append(OCRFailureReason.UNASSIGNED_IMAGES.value)

    is_complete = False
    ocr_under_extracted = False
    if reservation is not None and image_count > 0:
        from apps.reservations.document_intake_completeness import evaluate_completeness

        completeness = evaluate_completeness(
            reservation=reservation,
            persons=persons,
            matches=matches,
            images=[None] * image_count,
        )
        is_complete = completeness.is_complete
        ocr_under_extracted = completeness.ocr_under_extracted
        if ocr_under_extracted:
            job_reasons.append(OCRFailureReason.OCR_UNDER_EXTRACTED.value)

    return {
        "auto_apply_count": auto_apply_count,
        "match_count": len(matches),
        "unknown_person_count": unknown_person_count,
        "ocr_under_extracted": ocr_under_extracted,
        "orphan_pass_ran": bool((ocr_result.get("_orphan_pass") or {}).get("ran")),
        "unassigned_indices": unassigned,
        "is_complete": is_complete,
    }


def _unassigned_image_indices(*, persons: list[dict], image_count: int) -> list[int]:
    from apps.reservations.document_intake_completeness import unassigned_image_indices

    return unassigned_image_indices(persons=persons, image_count=image_count)


def _compute_resolution_component(image_signals: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [s["min_edge_px"] for s in image_signals if isinstance(s.get("min_edge_px"), int)]
    image_count = len(image_signals) if image_signals else len(measured)
    below_threshold_count = sum(
        1 for edge in measured if edge < RESOLUTION_THRESHOLD_PX
    )
    min_edge_px = min(measured) if measured else None
    if image_count == 0:
        score = 100
    elif not measured:
        score = 100
    else:
        score = round(100 * (1 - below_threshold_count / max(len(measured), 1)))
    return {
        "score": score,
        "min_edge_px": min_edge_px,
        "image_count": image_count,
        "below_threshold_count": below_threshold_count,
        "threshold_px": RESOLUTION_THRESHOLD_PX,
    }


def _compute_mrz_coverage_component(
    persons: list[dict],
    images_meta: dict[int, dict],
) -> dict[str, Any]:
    id_side_count = 0
    with_mrz_count = 0

    for person in persons:
        doc_type = str(person.get("document_type") or "national_id").lower()
        back_idx = _optional_index(person.get("back_image_index"))
        front_idx = _optional_index(person.get("front_image_index"))
        if doc_type == "passport":
            id_side_count += 1
            mrz = _non_empty_mrz_lines(person.get("mrz_lines"))
            if not mrz and front_idx is not None:
                front_meta = images_meta.get(front_idx, {})
                mrz = _non_empty_mrz_lines(front_meta.get("mrz_lines"))
            if mrz:
                with_mrz_count += 1
        else:
            if back_idx is not None:
                id_side_count += 1
                back_meta = images_meta.get(back_idx, {})
                mrz = _non_empty_mrz_lines(
                    person.get("mrz_lines") or back_meta.get("mrz_lines")
                )
                if mrz:
                    with_mrz_count += 1

    for idx in sorted(images_meta.keys()):
        meta = images_meta[idx]
        side = str(meta.get("side") or "").lower()
        if side in {"back", "passport"} and not any(
            _optional_index(p.get("back_image_index")) == idx
            or _optional_index(p.get("front_image_index")) == idx
            for p in persons
        ):
            id_side_count += 1
            if _non_empty_mrz_lines(meta.get("mrz_lines")):
                with_mrz_count += 1

    if id_side_count == 0:
        score = 100
    else:
        score = round(100 * with_mrz_count / id_side_count)
    return {
        "score": score,
        "id_side_count": id_side_count,
        "with_mrz_count": with_mrz_count,
    }


def _compute_pairing_component(
    *,
    persons: list[dict],
    image_count: int,
    unassigned_count: int,
) -> dict[str, Any]:
    if image_count == 0:
        score = 100
    else:
        score = round(100 * (1 - unassigned_count / image_count))
    return {
        "score": score,
        "unassigned_count": unassigned_count,
        "image_count": image_count,
    }


def _compute_names_component(persons: list[dict]) -> dict[str, Any]:
    person_count = len(persons)
    named_count = sum(
        1
        for p in persons
        if str(p.get("given_names") or "").strip() or str(p.get("surnames") or "").strip()
    )
    if person_count == 0:
        score = 0
    else:
        score = round(100 * named_count / person_count)
    return {
        "score": score,
        "person_count": person_count,
        "named_count": named_count,
    }


def _compute_completeness_component(
    *,
    is_complete: bool | None,
    ocr_under_extracted: bool,
) -> dict[str, Any]:
    if ocr_under_extracted:
        score = 0
    elif is_complete:
        score = 100
    else:
        score = 50
    return {
        "score": score,
        "is_complete": bool(is_complete),
        "ocr_under_extracted": ocr_under_extracted,
    }


def _calculate_quality_score(components: dict[str, dict[str, Any]]) -> tuple[int, dict[str, dict[str, Any]]]:
    total = 0.0
    normalized: dict[str, dict[str, Any]] = {}
    for name, weight in _QUALITY_WEIGHTS.items():
        component = dict(components.get(name) or {})
        raw_score = component.get("score", 0)
        try:
            score = int(raw_score)
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(100, score))
        component["score"] = score
        normalized[name] = component
        total += score * weight
    return round(total), normalized


def _derive_summary_reasons(
    *,
    images_telemetry: list[dict[str, Any]],
    persons_telemetry: list[dict[str, Any]],
    job_reasons: list[str],
) -> list[str]:
    all_reasons = list(job_reasons)
    for item in images_telemetry:
        all_reasons.extend(item.get("reasons") or [])
    for item in persons_telemetry:
        all_reasons.extend(item.get("reasons") or [])
    return sorted(set(str(r) for r in all_reasons if r))


def _parse_telemetry_blob(ocr_result: dict) -> dict[str, Any] | None:
    telemetry = ocr_result.get("_telemetry")
    if not isinstance(telemetry, dict):
        return None
    if not telemetry:
        return None
    return telemetry


def _quality_stats(scores: list[int]) -> dict[str, float | None]:
    if not scores:
        return {"mean": None, "median": None, "p10": None, "p90": None}
    return {
        "mean": round(statistics.mean(scores), 2),
        "median": round(statistics.median(scores), 2),
        "p10": round(_percentile(scores, 10), 2),
        "p90": round(_percentile(scores, 90), 2),
    }


def _percentile(values: list[int], pct: float) -> float:
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * pct / 100.0
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)
