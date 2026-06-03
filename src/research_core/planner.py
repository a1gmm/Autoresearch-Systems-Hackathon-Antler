from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, model_serializer

from research_core.jurisdiction_resolve import jurisdiction_context_for
from research_core.models import ScopePack
from research_core.registry import PROGRAM_REGISTRY, ProgramHypothesis, ProgramRegistryEntry

CoverageStatus = Literal[
    "active",
    "blocked_missing_fact",
    "out_of_scope",
    "discovery_candidate",
]
ExpectedSourceType = Literal[
    "statute",
    "regulation",
    "agency_guidance",
    "permit_portal",
    "technical_doc",
]


class CoverageFamilyStatus(BaseModel):
    id: str
    family: str
    status: CoverageStatus
    reason: str
    project_facts_considered: list[str]
    missing_facts: list[str]


class RegulatoryAngle(BaseModel):
    id: str
    family: str
    label: str
    reason: str
    triggering_facts: list[str]
    status: CoverageStatus


class ResearchHypothesis(BaseModel):
    id: str
    angle_id: str
    family: str
    question: str
    claim_to_test: str | None = None
    required_facts: list[str]
    expected_source_type: ExpectedSourceType
    success_criteria: list[str]
    dependencies: list[str]


class ResearchTaskBudget(BaseModel):
    max_sources: int
    max_runtime_seconds: int
    max_model_calls: int


class ResearchTask(BaseModel):
    task_id: str
    hypothesis_id: str
    assigned_agent: str
    allowed_tools: list[str]
    blocked_tools: list[str]
    budget: ResearchTaskBudget
    jurisdiction_context: str | None = None

    @model_serializer(mode="wrap")
    def _serialize_without_absent_context(self, handler) -> dict[str, Any]:
        data = handler(self)
        if self.jurisdiction_context is None:
            data.pop("jurisdiction_context", None)
        return data


class Plan(BaseModel):
    coverage_family_statuses: list[CoverageFamilyStatus]
    regulatory_angles: list[RegulatoryAngle]
    research_graph: list[ResearchHypothesis]
    research_tasks: list[ResearchTask]


UNIVERSAL_TOOL_IDS = (
    "send_message",
    "emit_trace_event",
    "validate_artifact_schema",
    "log_step",
    "escalate_to_human",
)
RESEARCHER_CORE_TOOL_IDS = (
    "read_skill",
    "get_triggers",
    "get_source_pointers",
    "get_cached_source",
    "fetch_source",
    "prove_currency",
    "extract_threshold",
    "evaluate_predicate",
    "quarantine_injection",
    "analyze_voc_content",
    "verify_chemical_composition",
    "lookup_cas_hazards",
    "compute_aggregate_quantity",
)
BLOCKED_RESEARCHER_TOOL_IDS = (
    "get_form",
    "build_applicability_matrix",
    "generate_compliance_calendar",
    "assemble_review_package",
    "freshness_sweep",
    "propose_map_entry",
    "propose_form_entry",
)


def _unique(ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def research_worker_tool_ids() -> list[str]:
    return _unique((*UNIVERSAL_TOOL_IDS, *RESEARCHER_CORE_TOOL_IDS))


def blocked_tool_ids_for_role(role: str) -> list[str]:
    if role == "researcher":
        return list(BLOCKED_RESEARCHER_TOOL_IDS)
    return []


def plan_research(
    scope: ScopePack,
    sds_active_families: frozenset[str] | set[str] = frozenset(),
) -> Plan:
    families = _unique(program.family for program in PROGRAM_REGISTRY)
    coverage_family_statuses = [
        coverage_status_for(
            family,
            scope,
            family in sds_active_families,
        )
        for family in families
    ]
    active_families = {
        status.family
        for status in coverage_family_statuses
        if status.status != "out_of_scope"
    }
    active_programs = [
        program
        for program in PROGRAM_REGISTRY
        if program.family in active_families
        and (program.triggered_by(scope) or program.family in sds_active_families)
    ]
    family_status_by = {status.family: status for status in coverage_family_statuses}
    regulatory_angles = [
        angle_for_program(program, family_status_by.get(program.family))
        for program in active_programs
    ]
    research_graph = [
        hypothesis_from_registry(program, hypothesis, family_status_by.get(program.family))
        for program in active_programs
        for hypothesis in program.hypotheses
    ]
    jurisdiction_context = (
        jurisdiction_context_for(
            {"county": scope.facility.county, "city": scope.facility.city}
        )
        if scope.facility.county or scope.facility.city
        else None
    )
    research_tasks = [
        task_for_hypothesis(hypothesis, jurisdiction_context)
        for hypothesis in research_graph
    ]
    return Plan(
        coverage_family_statuses=coverage_family_statuses,
        regulatory_angles=regulatory_angles,
        research_graph=research_graph,
        research_tasks=research_tasks,
    )


def coverage_status_for(
    family: str,
    scope: ScopePack,
    sds_flagged: bool,
) -> CoverageFamilyStatus:
    equipment_kinds = [item.kind for item in scope.project_change.equipment]
    has_chemicals = len(scope.project_change.chemicals) > 0
    has_waste = len(scope.project_change.waste_streams) > 0
    disturbance = scope.project_change.disturbance_acres
    id = f"CF-{family.upper()}"

    if family == "air":
        equipment_active = len(scope.project_change.equipment) > 0
        active = equipment_active or sds_flagged
        return CoverageFamilyStatus(
            id=id,
            family=family,
            status="active" if active else "out_of_scope",
            reason=(
                "Project adds equipment that may emit air contaminants."
                if equipment_active
                else (
                    "SDS review flagged VOC or air-emissions relevance; air "
                    "permit applicability requires review."
                    if sds_flagged
                    else "No equipment added that could emit air contaminants."
                )
            ),
            project_facts_considered=(
                [*equipment_kinds, "sds:voc_air_emissions_review"]
                if sds_flagged
                else equipment_kinds
            ),
            missing_facts=[],
        )

    if family == "stormwater":
        missing_code = (
            not scope.facility.sic
            and not scope.facility.naics
            and disturbance is None
        )
        return CoverageFamilyStatus(
            id=id,
            family=family,
            status="blocked_missing_fact" if missing_code else "active",
            reason=(
                "SIC/NAICS and disturbance acreage are missing."
                if missing_code
                else (
                    "Industrial activity codes or construction acreage require "
                    "stormwater review."
                )
            ),
            project_facts_considered=[
                f"sic={scope.facility.sic}",
                f"naics={scope.facility.naics}",
                f"acres={disturbance}",
            ],
            missing_facts=(
                ["facility.naics_or_sic", "project_change.disturbance_acres"]
                if missing_code
                else []
            ),
        )

    if family == "hazmat":
        missing_quantity = has_chemicals and any(
            chemical.quantity is None
            for chemical in scope.project_change.chemicals
        )
        return CoverageFamilyStatus(
            id=id,
            family=family,
            status=(
                "active"
                if (not has_chemicals and sds_flagged)
                else (
                    "out_of_scope"
                    if not has_chemicals
                    else "blocked_missing_fact"
                    if missing_quantity
                    else "active"
                )
            ),
            reason=(
                "Project includes hazardous material storage."
                if has_chemicals
                else (
                    "SDS review flagged hazardous material content; HMBP "
                    "applicability requires review."
                    if sds_flagged
                    else "No hazardous materials indicated in intake."
                )
            ),
            project_facts_considered=[
                f"{chemical.name}:{chemical.quantity if chemical.quantity is not None else 'missing'} {chemical.unit or ''}"
                for chemical in scope.project_change.chemicals
            ],
            missing_facts=(
                ["chemicals.quantity", "chemicals.unit"] if missing_quantity else []
            ),
        )

    if family == "waste":
        return CoverageFamilyStatus(
            id=id,
            family=family,
            status="active" if has_waste or sds_flagged else "out_of_scope",
            reason=(
                "Project identifies waste streams that need generator-status review."
                if has_waste
                else (
                    "SDS review flagged hazardous waste relevance; generator-status "
                    "review required."
                    if sds_flagged
                    else "No waste stream indicated."
                )
            ),
            project_facts_considered=[
                f"{stream.description}:{stream.kg_per_month if stream.kg_per_month is not None else 'missing'} kg/month"
                for stream in scope.project_change.waste_streams
            ],
            missing_facts=(
                ["waste_streams.kg_per_month"]
                if any(
                    stream.kg_per_month is None
                    for stream in scope.project_change.waste_streams
                )
                else []
            ),
        )

    if family == "wastewater":
        discharge = scope.project_change.process_discharge
        return CoverageFamilyStatus(
            id=id,
            family=family,
            status=(
                "active"
                if discharge or sds_flagged
                else "blocked_missing_fact"
                if discharge is None
                else "out_of_scope"
            ),
            reason=(
                (
                    "SDS review flagged spill/stormwater containment relevance; "
                    "pretreatment review required."
                )
                if discharge is None and sds_flagged
                else "Process discharge status is missing."
                if discharge is None
                else "Project may discharge process wastewater."
                if discharge
                else "No process wastewater discharge indicated."
            ),
            project_facts_considered=[f"process_discharge={discharge}"],
            missing_facts=(
                ["project_change.process_discharge"] if discharge is None else []
            ),
        )

    return CoverageFamilyStatus(
        id=id,
        family=family,
        status="active",
        reason="Registry program applies to this family; investigate.",
        project_facts_considered=[],
        missing_facts=[],
    )


def angle_for_program(
    program: ProgramRegistryEntry,
    status: CoverageFamilyStatus | None,
) -> RegulatoryAngle:
    return RegulatoryAngle(
        id=f"A-{program.id}",
        family=program.family,
        label=program.name,
        reason=program.what_it_does,
        triggering_facts=status.project_facts_considered if status else [],
        status=status.status if status else "active",
    )


def hypothesis_from_registry(
    program: ProgramRegistryEntry,
    hypothesis: ProgramHypothesis,
    status: CoverageFamilyStatus | None,
) -> ResearchHypothesis:
    return ResearchHypothesis(
        id=hypothesis.id,
        angle_id=f"A-{program.id}",
        family=program.family,
        question=hypothesis.question,
        claim_to_test=hypothesis.claim_to_test,
        required_facts=status.project_facts_considered if status else [],
        expected_source_type="regulation",
        success_criteria=[
            "official or high-authority source",
            "quote contains trigger, threshold, exemption, or blocker",
            "predicate evaluation is reproducible",
        ],
        dependencies=[],
    )


def task_for_hypothesis(
    hypothesis: ResearchHypothesis,
    jurisdiction_context: str | None = None,
) -> ResearchTask:
    return ResearchTask(
        task_id=f"T-{hypothesis.id[2:]}",
        hypothesis_id=hypothesis.id,
        assigned_agent=f"{hypothesis.family}_researcher",
        allowed_tools=research_worker_tool_ids(),
        blocked_tools=blocked_tool_ids_for_role("researcher"),
        budget=ResearchTaskBudget(
            # Headroom for the real flow: read_skill -> web_search -> web_fetch/browser
            # -> read + corroborate -> submit_finding, with room to recover from a bad
            # fetch. 4 turns was too tight (couldn't even reach submit after orienting).
            max_sources=5,
            max_runtime_seconds=120,
            max_model_calls=10,
        ),
        jurisdiction_context=jurisdiction_context,
    )
