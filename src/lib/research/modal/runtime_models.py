from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ReviewDecision = Literal["accepted", "needs_repair", "needs_human_review"]


@dataclass(frozen=True)
class RuntimeTask:
    task_id: str
    hypothesis_id: str
    question: str
    family: str
    skill_id: str | None
    allowed_domains: list[str] = field(default_factory=list)
    input: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerDraft:
    task_id: str
    hypothesis_id: str
    answer: str
    evidence: list[dict[str, Any]]
    caveats: list[str]
    artifact_path: str


@dataclass(frozen=True)
class ReviewFinding:
    severity: Literal["blocker", "major", "minor"]
    signal: str
    explanation: str
    repair_instruction: str


@dataclass(frozen=True)
class ReviewResult:
    task_id: str
    decision: ReviewDecision
    findings: list[ReviewFinding]
    accepted_evidence_ids: list[str]
    artifact_path: str
