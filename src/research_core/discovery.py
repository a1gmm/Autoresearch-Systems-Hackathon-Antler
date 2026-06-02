from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from research_core.planner import (
    CoverageFamilyStatus,
    Plan,
    RegulatoryAngle,
    ResearchHypothesis,
    task_for_hypothesis,
)


class StagedRegime(BaseModel):
    id: str
    family: str
    rationale: str
    human_verified: bool
    status: str


class DiscoveryCandidateBundle(BaseModel):
    coverage_family_statuses: list[CoverageFamilyStatus]
    regulatory_angles: list[RegulatoryAngle]
    research_graph: list[ResearchHypothesis]


_seq = 0
_DISCOVERY_ID_RE = re.compile(r"^H-DISCOVER-(\d+)$")


def stage_novel_regime(family: str, rationale: str) -> StagedRegime:
    global _seq
    _seq += 1
    return StagedRegime(
        id=f"staged-{_seq}",
        family=family,
        rationale=rationale,
        human_verified=False,
        status="needs_review",
    )


def discovery_candidates_from_proposals(
    proposals: list[dict[str, Any]],
) -> DiscoveryCandidateBundle:
    statuses: list[CoverageFamilyStatus] = []
    angles: list[RegulatoryAngle] = []
    hypotheses: list[ResearchHypothesis] = []
    idx = 0

    for proposal in proposals:
        family = str(proposal.get("family") or "discovery")
        rationale = str(
            proposal.get("rationale")
            or "Orchestrator proposed a family beyond the deterministic set."
        )
        for raw_hypothesis in proposal.get("hypotheses") or []:
            idx += 1
            angle_id = f"A-DISCOVER-{idx}"
            hypothesis_id = f"H-DISCOVER-{idx}"
            question = str(raw_hypothesis.get("question") or rationale)
            statuses.append(
                CoverageFamilyStatus(
                    id=f"CF-DISCOVER-{idx}",
                    family=family,
                    status="discovery_candidate",
                    reason=rationale,
                    project_facts_considered=[],
                    missing_facts=[],
                )
            )
            angles.append(
                RegulatoryAngle(
                    id=angle_id,
                    family=family,
                    label=f"Discovered: {family}",
                    reason=rationale,
                    triggering_facts=[],
                    status="discovery_candidate",
                )
            )
            hypotheses.append(
                ResearchHypothesis(
                    id=hypothesis_id,
                    angle_id=angle_id,
                    family=family,
                    question=question,
                    claim_to_test=raw_hypothesis.get("claim_to_test"),
                    required_facts=[],
                    expected_source_type="agency_guidance",
                    success_criteria=[
                        "official or high-authority source",
                        "verbatim quote grounds the claim",
                    ],
                    dependencies=[],
                )
            )

    return DiscoveryCandidateBundle(
        coverage_family_statuses=statuses,
        regulatory_angles=angles,
        research_graph=hypotheses,
    )


def merge_discovery_proposals_into_plan(
    baseline: Plan,
    proposals: list[dict[str, Any]],
    jurisdiction_context: str | None = None,
) -> Plan:
    candidate_keys = {
        _candidate_key(
            hypothesis.family,
            hypothesis.question,
            hypothesis.claim_to_test,
        )
        for hypothesis in baseline.research_graph
    }
    next_index = _next_discovery_index(baseline.research_graph)
    baseline_context = _first_jurisdiction_context(baseline)
    task_jurisdiction_context = (
        baseline_context if baseline_context is not None else jurisdiction_context
    )

    statuses: list[CoverageFamilyStatus] = []
    angles: list[RegulatoryAngle] = []
    hypotheses: list[ResearchHypothesis] = []

    for proposal in proposals:
        family = str(proposal.get("family") or "discovery")
        rationale = str(
            proposal.get("rationale")
            or "Orchestrator proposed a family beyond the deterministic set."
        )
        for raw_hypothesis in proposal.get("hypotheses") or []:
            question = str(raw_hypothesis.get("question") or rationale)
            claim_to_test = raw_hypothesis.get("claim_to_test")
            key = _candidate_key(family, question, claim_to_test)
            if key in candidate_keys:
                continue
            candidate_keys.add(key)

            idx = next_index
            next_index += 1
            angle_id = f"A-DISCOVER-{idx}"
            hypothesis_id = f"H-DISCOVER-{idx}"
            statuses.append(
                CoverageFamilyStatus(
                    id=f"CF-DISCOVER-{idx}",
                    family=family,
                    status="discovery_candidate",
                    reason=rationale,
                    project_facts_considered=[],
                    missing_facts=[],
                )
            )
            angles.append(
                RegulatoryAngle(
                    id=angle_id,
                    family=family,
                    label=f"Discovered: {family}",
                    reason=rationale,
                    triggering_facts=[],
                    status="discovery_candidate",
                )
            )
            hypotheses.append(
                ResearchHypothesis(
                    id=hypothesis_id,
                    angle_id=angle_id,
                    family=family,
                    question=question,
                    claim_to_test=claim_to_test,
                    required_facts=[],
                    expected_source_type="agency_guidance",
                    success_criteria=[
                        "official or high-authority source",
                        "verbatim quote grounds the claim",
                    ],
                    dependencies=[],
                )
            )

    return Plan(
        coverage_family_statuses=[
            *baseline.coverage_family_statuses,
            *statuses,
        ],
        regulatory_angles=[*baseline.regulatory_angles, *angles],
        research_graph=[*baseline.research_graph, *hypotheses],
        research_tasks=[
            *baseline.research_tasks,
            *(
                task_for_hypothesis(hypothesis, task_jurisdiction_context)
                for hypothesis in hypotheses
            ),
        ],
    )


def _next_discovery_index(hypotheses: list[ResearchHypothesis]) -> int:
    highest = 0
    for hypothesis in hypotheses:
        match = _DISCOVERY_ID_RE.match(hypothesis.id)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _first_jurisdiction_context(baseline: Plan) -> str | None:
    for task in baseline.research_tasks:
        if task.jurisdiction_context:
            return task.jurisdiction_context
    return None


def _candidate_key(
    family: str,
    question: str,
    claim_to_test: str | None,
) -> tuple[str, str, str]:
    return (
        family.strip().lower(),
        question.strip().lower(),
        (claim_to_test or "").strip().lower(),
    )
