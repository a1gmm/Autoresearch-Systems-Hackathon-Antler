from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import asdict, is_dataclass
from typing import Any

from runtime_models import ReviewFinding, ReviewResult, RuntimeTask, WorkerDraft

VALID_REVIEW_DECISIONS = {"accepted", "needs_repair", "needs_human_review"}
VALID_FINDING_SEVERITIES = {"blocker", "major", "minor"}


def _load_agents_sdk():
    from agents import Agent, Runner, function_tool

    return Agent, Runner, function_tool


def _build_worker_tools(function_tool: Any) -> list[Any]:
    from worker_core import SOURCE_POINTERS, assemble_evidence, failed_bundle, host_allowed

    @function_tool
    def is_source_url_allowed(url: str) -> dict[str, Any]:
        return {"url": url, "allowed": host_allowed(url)}

    @function_tool
    def get_official_source_pointer(hypothesis_id: str) -> dict[str, Any]:
        pointer = SOURCE_POINTERS.get(hypothesis_id)
        return {
            "hypothesis_id": hypothesis_id,
            "found": pointer is not None,
            "pointer": pointer or {},
        }

    @function_tool
    def build_failed_evidence_bundle(hypothesis_id: str, reason: str) -> dict[str, Any]:
        return failed_bundle(hypothesis_id, reason)

    @function_tool
    def assemble_grounded_evidence_bundle(
        hypothesis_id: str,
        source_name: str,
        url: str,
        authority_rank: int,
        content_hash: str,
        fetched_at: str,
        field: str,
        verbatim_quote: str,
        applies: str,
        confidence: float,
        threshold_value: str | None = None,
    ) -> dict[str, Any]:
        return assemble_evidence(
            hypothesis_id,
            {"source_name": source_name, "url": url, "authority_rank": authority_rank},
            content_hash,
            fetched_at,
            {
                "field": field,
                "verbatim_quote": verbatim_quote,
                "applies": applies,
                "confidence": confidence,
                "threshold_value": threshold_value,
            },
        )

    return [
        is_source_url_allowed,
        get_official_source_pointer,
        build_failed_evidence_bundle,
        assemble_grounded_evidence_bundle,
    ]


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _parse_final_output(final_output: Any) -> dict[str, Any]:
    if isinstance(final_output, str):
        parsed = json.loads(final_output)
        if not isinstance(parsed, dict):
            raise TypeError("Runner final_output JSON must decode to an object")
        return parsed
    if isinstance(final_output, dict):
        return final_output
    if is_dataclass(final_output):
        return asdict(final_output)
    if hasattr(final_output, "model_dump"):
        parsed = final_output.model_dump()
        if not isinstance(parsed, dict):
            raise TypeError("Runner final_output model_dump() must return an object")
        return parsed
    if hasattr(final_output, "dict"):
        parsed = final_output.dict()
        if not isinstance(parsed, dict):
            raise TypeError("Runner final_output dict() must return an object")
        return parsed
    raise TypeError(f"Unsupported final_output type: {type(final_output).__name__}")


def _run_agent(runner: Any, agent: Any, payload: dict[str, Any]) -> dict[str, Any]:
    result = runner.run(agent, _runner_input(payload))
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    return _parse_final_output(result.final_output)


def _runner_input(payload: dict[str, Any]) -> str:
    return (
        "Use the following JSON task payload. Return only a JSON object matching "
        f"{payload.get('output_schema', 'the requested schema')}.\n\n"
        f"{json.dumps(payload, sort_keys=True)}"
    )


def _worker_draft_from_payload(payload: dict[str, Any]) -> WorkerDraft:
    _require_keys(payload, ("task_id", "hypothesis_id", "answer", "artifact_path"), "WorkerDraft")
    evidence = payload.get("evidence", [])
    caveats = payload.get("caveats", [])
    if not isinstance(evidence, list):
        raise TypeError("WorkerDraft evidence must be a list")
    if not isinstance(caveats, list):
        raise TypeError("WorkerDraft caveats must be a list")
    return WorkerDraft(
        task_id=payload["task_id"],
        hypothesis_id=payload["hypothesis_id"],
        answer=payload["answer"],
        evidence=evidence,
        caveats=caveats,
        artifact_path=payload["artifact_path"],
    )


def _review_from_payload(payload: dict[str, Any]) -> ReviewResult:
    _require_keys(payload, ("task_id", "decision", "artifact_path"), "ReviewResult")
    decision = payload["decision"]
    if decision not in VALID_REVIEW_DECISIONS:
        raise ValueError(f"Invalid reviewer decision: {decision}")
    findings_payload = payload.get("findings", [])
    accepted_ids = payload.get("accepted_evidence_ids", [])
    if not isinstance(findings_payload, list):
        raise TypeError("ReviewResult findings must be a list")
    if not isinstance(accepted_ids, list):
        raise TypeError("ReviewResult accepted_evidence_ids must be a list")
    findings = [_finding_from_payload(finding) for finding in findings_payload]
    return ReviewResult(
        task_id=payload["task_id"],
        decision=decision,
        findings=findings,
        accepted_evidence_ids=accepted_ids,
        artifact_path=payload["artifact_path"],
    )


def _require_keys(payload: dict[str, Any], keys: tuple[str, ...], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise KeyError(f"{label} missing required field(s): {', '.join(missing)}")


def _finding_from_payload(finding: Any) -> ReviewFinding:
    if isinstance(finding, ReviewFinding):
        if finding.severity not in VALID_FINDING_SEVERITIES:
            raise ValueError(f"Invalid finding severity: {finding.severity}")
        return finding
    if not isinstance(finding, dict):
        raise TypeError("ReviewFinding must be an object")
    _require_keys(finding, ("severity", "signal", "explanation", "repair_instruction"), "ReviewFinding")
    if finding["severity"] not in VALID_FINDING_SEVERITIES:
        raise ValueError(f"Invalid finding severity: {finding['severity']}")
    return ReviewFinding(**finding)


def build_research_worker_agent(task: RuntimeTask, rulebook: str):
    Agent, _Runner, function_tool = _load_agents_sdk()
    return Agent(
        name=f"PermitPilot research worker {task.skill_id or task.family}",
        instructions=(
            "You are a PermitPilot research worker. Produce a worker draft only: "
            "an answer with evidence pointers, caveats, and artifact metadata. Do not "
            "write final permit prose. Ground every claim in allowed sources and follow "
            "the reviewer rulebook.\n\n"
            f"{rulebook}"
        ),
        tools=_build_worker_tools(function_tool),
    )


def build_reviewer_agent(rulebook: str):
    Agent, _Runner, _function_tool = _load_agents_sdk()
    return Agent(
        name="PermitPilot reviewer",
        instructions=(
            "You are the acceptance reviewer for PermitPilot CrossBeam Modal research. "
            "Return only the JSON review result. Findings must cite the rulebook signal "
            "that triggered the concern and include concrete repair instructions.\n\n"
            f"{rulebook}"
        ),
    )


def run_worker_draft(task: RuntimeTask, rulebook: str, context: dict[str, Any]) -> WorkerDraft:
    _Agent, Runner, _function_tool = _load_agents_sdk()
    agent = build_research_worker_agent(task, rulebook)
    payload = {
        "mode": "draft",
        "task": _jsonable(task),
        "rulebook": rulebook,
        "context": context,
        "output_schema": "WorkerDraft",
    }
    return _worker_draft_from_payload(_run_agent(Runner, agent, payload))


def run_worker_repair(
    task: RuntimeTask,
    original: WorkerDraft,
    review: ReviewResult,
    rulebook: str,
) -> WorkerDraft:
    _Agent, Runner, _function_tool = _load_agents_sdk()
    agent = build_research_worker_agent(task, rulebook)
    payload = {
        "mode": "repair",
        "task": _jsonable(task),
        "rulebook": rulebook,
        "original_draft": _jsonable(original),
        "review": _jsonable(review),
        "review_findings": _jsonable(review.findings),
        "repair_instructions": "\n".join(
            finding.repair_instruction for finding in review.findings
        ),
        "output_schema": "WorkerDraft",
    }
    return _worker_draft_from_payload(_run_agent(Runner, agent, payload))


def run_review(task: RuntimeTask, draft: WorkerDraft, rulebook: str) -> ReviewResult:
    _Agent, Runner, _function_tool = _load_agents_sdk()
    agent = build_reviewer_agent(rulebook)
    payload = {
        "task": _jsonable(task),
        "draft": _jsonable(draft),
        "rulebook": rulebook,
        "output_schema": "ReviewResult",
    }
    return _review_from_payload(_run_agent(Runner, agent, payload))
