from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime_models import ReviewFinding, ReviewResult, RuntimeTask
from worker_core import failed_bundle
from workspace_core import append_event, read_json, write_json

SYNTHESIS_ARTIFACT_PATH = "synthesis/runtime-synthesis.json"


def _timeline_events(workspace: Path) -> list[dict[str, Any]]:
    timeline = workspace / "logs" / "timeline.jsonl"
    if not timeline.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in timeline.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def _artifact_json(workspace: Path, artifact_path: str) -> dict[str, Any] | None:
    relative = Path(artifact_path)
    if relative.is_absolute():
        return None
    root = workspace.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        return None
    if not path.is_file():
        return None
    return read_json(path)


def _review_from_artifact(payload: dict[str, Any]) -> ReviewResult:
    findings = [
        ReviewFinding(
            severity=finding["severity"],
            signal=finding["signal"],
            explanation=finding["explanation"],
            repair_instruction=finding["repair_instruction"],
        )
        for finding in payload.get("findings", [])
    ]
    return ReviewResult(
        task_id=payload["task_id"],
        decision=payload["decision"],
        findings=findings,
        accepted_evidence_ids=payload.get("accepted_evidence_ids", []),
        artifact_path=payload["artifact_path"],
    )


def _latest_review(task: RuntimeTask, workspace: Path) -> ReviewResult | None:
    latest: ReviewResult | None = None
    for event in _timeline_events(workspace):
        if event.get("task_id") != task.task_id or event.get("type") != "review":
            continue
        payload = _artifact_json(workspace, event.get("artifact_path", ""))
        if payload is not None:
            latest = _review_from_artifact(payload)
    return latest


def _latest_worker_artifact(task: RuntimeTask, workspace: Path) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for event in _timeline_events(workspace):
        if event.get("task_id") != task.task_id or event.get("type") not in ("draft", "repair"):
            continue
        payload = _artifact_json(workspace, event.get("artifact_path", ""))
        if payload is not None:
            latest = payload
    return latest


def _value(entry: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = entry.get(key)
        if value not in (None, ""):
            return value
    return None


def _grounded_bundle(task: RuntimeTask, review: ReviewResult, draft: dict[str, Any]) -> dict[str, Any]:
    accepted_ids = set(review.accepted_evidence_ids)
    if not accepted_ids:
        return failed_bundle(task.hypothesis_id, "Accepted review did not identify accepted evidence IDs.")

    evidence_entries = [
        entry for entry in draft.get("evidence", [])
        if isinstance(entry, dict) and str(entry.get("id", "")) in accepted_ids
    ]
    if not evidence_entries:
        return failed_bundle(task.hypothesis_id, "Accepted evidence IDs were not found in the latest draft artifact.")

    sources: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    conclusions: list[str] = []

    for entry in evidence_entries:
        url = _value(entry, "source_url", "url")
        quote = _value(entry, "verbatim_quote", "quote")
        source_name = _value(entry, "source_name", "title")
        fetched_at = entry.get("fetched_at")
        content_hash = entry.get("content_hash")
        if not url or not quote or not source_name or not fetched_at or not content_hash:
            bundle = failed_bundle(
                task.hypothesis_id,
                "Accepted evidence is missing grounded URL, quote, source name, fetched date, or content hash.",
            )
            _attach_runtime_review(bundle, review, "needs_review", "Accepted evidence failed required metadata hygiene.")
            return bundle

        sources.append({
            "url": url,
            "source_name": source_name,
            "authority_rank": entry.get("authority_rank", 1),
            "fetched_at": fetched_at,
            "content_hash": content_hash,
            "effective_date": entry.get("effective_date"),
            "quote": quote,
        })
        claims.append({
            "field": entry.get("field") or "source_claim",
            "value": "" if entry.get("value") is None else str(entry.get("value")),
            "source_url": url,
            "quote": quote,
            "confidence": entry.get("confidence", 0.5),
        })
        conclusion = entry.get("applies") or entry.get("researcher_conclusion")
        if conclusion in ("applies", "does_not_apply", "needs_review"):
            conclusions.append(conclusion)

    conclusion = conclusions[0] if conclusions else "needs_review"
    if "needs_review" in conclusions:
        conclusion = "needs_review"

    verdict = "pass" if conclusion in ("applies", "does_not_apply") else "needs_review"
    bundle = {
        "hypothesis_id": task.hypothesis_id,
        "sources": sources,
        "extracted_claims": claims,
        "researcher_conclusion": conclusion,
        "uncertainties": [],
    }
    _attach_runtime_review(
        bundle,
        review,
        verdict,
        "Reviewer accepted grounded evidence with settled applicability."
        if verdict == "pass"
        else "Reviewer accepted grounded evidence, but applicability remains unresolved.",
    )
    return bundle


def evidence_bundle_from_review(task: RuntimeTask, review: ReviewResult, workspace: Path) -> dict[str, Any]:
    if review.decision != "accepted":
        bundle = failed_bundle(task.hypothesis_id, f"Runtime review ended with {review.decision}.")
        _attach_runtime_review(bundle, review, "needs_review", f"Reviewer decision was {review.decision}.")
        return bundle

    draft = _latest_worker_artifact(task, workspace)
    if draft is None:
        bundle = failed_bundle(task.hypothesis_id, "Accepted review has no worker draft or repair artifact.")
        _attach_runtime_review(bundle, review, "needs_review", "Accepted review has no worker artifact.")
        return bundle

    return _grounded_bundle(task, review, draft)


def _attach_runtime_review(bundle: dict[str, Any], review: ReviewResult, verdict: str, reason: str) -> None:
    bundle["runtime_review"] = {
        "decision": review.decision,
        "verdict": verdict,
        "artifact_path": review.artifact_path,
        "accepted_evidence_ids": review.accepted_evidence_ids,
        "reason": reason,
    }


def _ticket_from_review(task: RuntimeTask, review: ReviewResult, bundle: dict[str, Any]) -> dict[str, Any]:
    findings = [
        {
            "severity": getattr(finding, "severity", None),
            "signal": getattr(finding, "signal", None),
            "explanation": getattr(finding, "explanation", None),
            "repair_instruction": getattr(finding, "repair_instruction", None),
        }
        for finding in review.findings
    ]
    return {
        "task_id": task.task_id,
        "hypothesis_id": task.hypothesis_id,
        "reason": review.decision,
        "findings": findings,
        "uncertainties": bundle.get("uncertainties", []),
    }


def _report_markdown(run_id: str, determinations: list[dict[str, Any]]) -> str:
    lines = [f"# Runtime synthesis for {run_id}", ""]
    for determination in determinations:
        lines.append(
            f"- {determination['hypothesis_id']}: {determination['status']} "
            f"({determination['summary']})"
        )
    return "\n".join(lines) + "\n"


def synthesize_runtime_artifacts(run_id: str, tasks: list[RuntimeTask], workspace: Path) -> dict[str, Any]:
    determinations: list[dict[str, Any]] = []
    repair_tickets: list[dict[str, Any]] = []
    verification_verdicts: list[dict[str, Any]] = []
    evidence_bundles: list[dict[str, Any]] = []

    for task in tasks:
        review = _latest_review(task, workspace)
        if review is None:
            bundle = failed_bundle(task.hypothesis_id, "No reviewer artifact was found for this task.")
            verdict = "needs_review"
            summary = "No reviewer artifact was available."
            review_decision = "missing_review"
        else:
            bundle = evidence_bundle_from_review(task, review, workspace)
            review_decision = review.decision
            has_grounded_evidence = bool(bundle.get("sources")) and bool(bundle.get("extracted_claims"))
            has_applicability_conclusion = bundle.get("researcher_conclusion") in ("applies", "does_not_apply")
            if review.decision == "accepted" and has_grounded_evidence and has_applicability_conclusion and not bundle.get("uncertainties"):
                verdict = "pass"
                summary = "Reviewer accepted grounded evidence."
            else:
                verdict = "needs_review"
                summary = "Review did not produce grounded accepted evidence with a settled applicability conclusion."
                repair_tickets.append(_ticket_from_review(task, review, bundle))

        evidence_bundles.append(bundle)
        determinations.append({
            "task_id": task.task_id,
            "hypothesis_id": task.hypothesis_id,
            "review_decision": review_decision,
            "status": verdict,
            "summary": summary,
            "evidence_bundle": bundle,
        })
        verification_verdicts.append({
            "task_id": task.task_id,
            "hypothesis_id": task.hypothesis_id,
            "verdict": verdict,
            "review_decision": review_decision,
            "artifact_path": review.artifact_path if review is not None else None,
            "reason": summary,
        })

    payload: dict[str, Any] = {
        "run_id": run_id,
        "determinations": determinations,
        "report_markdown": _report_markdown(run_id, determinations),
        "repair_tickets": repair_tickets,
        "verification_verdicts": verification_verdicts,
        "evidence_bundles": evidence_bundles,
        "artifact_path": SYNTHESIS_ARTIFACT_PATH,
    }
    write_json(workspace / SYNTHESIS_ARTIFACT_PATH, payload)
    append_event(workspace, {
        "type": "synthesis",
        "artifact_path": SYNTHESIS_ARTIFACT_PATH,
    })
    return payload
