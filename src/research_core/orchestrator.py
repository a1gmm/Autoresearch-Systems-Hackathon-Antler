from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from research_core.agents import run_repair_agent, run_researcher_agent
from research_core.discovery import merge_discovery_proposals_into_plan
from research_core.jurisdiction_resolve import apply_jurisdiction_to_scope
from research_core.models import (
    Assumption,
    Chemical,
    Equipment,
    Facility,
    FactProvenance,
    InformationRequest,
    MissingFact,
    ProjectChange,
    ProvidedDocument,
    RunStatus,
    Scenario,
    ScopePack,
    WasteStream,
)
from research_core.planner import Plan, ResearchTask, plan_research
from research_core.raindrop import WorkshopTracer, workshop
from research_core.scenarios import information_gap_options, scenarios_for_missing_fact
from research_core.store import get_default_store
from research_core.synthesis import synthesize_result
from research_core.tools import DEFAULT_ALLOWED_HOSTS, SandboxPolicy, source_authority_rank
from research_core.verifier import VerificationVerdict, repair_evidence, verify_evidence


DepsMode = Literal["fake", "offline", "live"]
ARTIFACT_ROOT_ENV = "RESEARCH_CORE_ARTIFACT_ROOT"
ALLOWED_HOSTS_ENV = "RESEARCH_CORE_ALLOWED_HOSTS"
ALLOW_NETWORK_ENV = "RESEARCH_CORE_ALLOW_NETWORK"
ALLOW_BROWSER_ENV = "RESEARCH_CORE_ALLOW_BROWSER"
SEARCH_ENDPOINT_ENV = "RESEARCH_CORE_SEARCH_ENDPOINT"
AGENT_MODEL_ENV = "RESEARCH_CORE_AGENT_MODEL"
DEFAULT_AGENT_MODEL = "gpt-5.5"
# Repair is the quality-critical re-research step. Keep it on a strong model even when the
# worker (researcher) runs cheap, so a tiered "cheap worker / strong repair" setup just
# needs RESEARCH_CORE_AGENT_MODEL=<cheap> while repair stays strong by default.
REPAIR_MODEL_ENV = "RESEARCH_CORE_REPAIR_MODEL"
DEFAULT_REPAIR_MODEL = "gpt-5.5"


class ResearchRunResult(BaseModel):
    run_id: str
    status: str
    information_requests: list[InformationRequest] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    verdicts: list[VerificationVerdict] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    # The run's own trace timeline, so the UI animates the REAL run (the adapter coerces
    # each {scope, payload, created_at} into a TraceEvent the replay drives the graph from).
    trace_events: list[dict[str, Any]] = Field(default_factory=list)


@dataclass
class ResearchDeps:
    mode: DepsMode = "offline"
    discovery_proposals: list[dict[str, Any]] = field(default_factory=list)
    max_repair_attempts: int = 1
    agent_model: str | None = None
    repair_model: str | None = None
    artifact_root: str | Path | None = None

    def discover(self, scope: ScopePack, plan: Plan) -> list[dict[str, Any]]:
        return list(self.discovery_proposals)

    def research(self, task: ResearchTask, scope: ScopePack) -> dict[str, Any]:
        if self.mode in {"fake", "offline"}:
            return _fake_research_bundle(task, scope)
        try:
            output = run_researcher_agent(
                task,
                scope,
                _sandbox_policy(scope, self.artifact_root),
                model=self.agent_model or _agent_model_from_env(),
            )
        except Exception as exc:
            return _agent_error_bundle(
                hypothesis_id=task.hypothesis_id,
                task_id=task.task_id,
                code="live_agent_failed",
                message=str(exc),
                exception_type=exc.__class__.__name__,
            )
        return _bundle_from_agent_output(
            hypothesis_id=task.hypothesis_id,
            task_id=task.task_id,
            output=output,
        )

    def repair(self, ticket: Any, previous_bundle: dict[str, Any], scope: ScopePack) -> dict[str, Any]:
        if self.mode in {"fake", "offline"}:
            return repair_evidence(ticket)
        try:
            output = run_repair_agent(
                ticket,
                previous_bundle,
                scope,
                _sandbox_policy(scope, self.artifact_root),
                model=self.repair_model or _repair_model_from_env(),
            )
        except Exception as exc:
            return _agent_error_bundle(
                hypothesis_id=str(getattr(ticket, "hypothesis_id", "unknown")),
                task_id=str(getattr(ticket, "ticket_id", "repair")),
                code="live_repair_agent_failed",
                message=str(exc),
                exception_type=exc.__class__.__name__,
            )
        return _bundle_from_agent_output(
            hypothesis_id=str(getattr(ticket, "hypothesis_id", "unknown")),
            task_id=str(getattr(ticket, "ticket_id", "repair")),
            output=output,
        )


def run_research_sync(
    input_payload: dict[str, Any],
    *,
    deps: str | ResearchDeps = "offline",
    store: Any | None = None,
    tracer: WorkshopTracer | None = None,
    run_id: str | None = None,
) -> ResearchRunResult:
    active_store = store or get_default_store()
    active_deps = _coerce_deps(deps)
    record = active_store.get_run(run_id) if run_id else None
    if record is None:
        record = active_store.create_run(input_payload, run_id=run_id)
    run_id = record["run_id"]
    active_tracer = tracer or workshop(_trace_endpoint(input_payload))

    try:
        active_store.update_status(run_id, RunStatus.SCOPING.value)
        active_tracer.event(run_id, "scope:start", {"mode": active_deps.mode})
        scope = apply_jurisdiction_to_scope(scope_from_input(input_payload, run_id))
        active_store.write_artifact(run_id, "scope", scope)
        active_tracer.event(
            run_id,
            "scope:complete",
            {"missing_facts": [fact.field for fact in scope.missing_facts]},
        )

        active_store.update_status(run_id, RunStatus.PLANNING.value)
        plan = plan_research(scope)
        discovery = active_deps.discover(scope, plan)
        plan = merge_discovery_proposals_into_plan(
            plan,
            discovery,
            jurisdiction_context=None,
        )
        active_store.write_artifact(run_id, "plan", plan)
        active_tracer.event(
            run_id,
            "plan:complete",
            {
                "tasks": len(plan.research_tasks),
                "discovery_proposals": len(discovery),
            },
        )

        information_requests = _information_requests(scope, plan)
        scenarios = _scenarios_for_requests(input_payload, information_requests)
        blocking_requests = _blocking_requests(scope, information_requests, input_payload)

        evidence: list[dict[str, Any]] = []
        verdicts: list[VerificationVerdict] = []
        if not blocking_requests:
            active_store.update_status(run_id, RunStatus.RESEARCHING.value)
            # Run hypotheses in PARALLEL: each is an independent subagent doing long
            # (up to 60 min) durable research, so total wall-clock ~= the slowest one
            # instead of the sum. The agents are I/O-bound (LLM + fetches), so threads
            # give real concurrency. Store writes + tracer events stay sequential and in
            # plan order below for deterministic, race-free persistence.
            tasks = list(plan.research_tasks)
            if tasks:
                workers = min(len(tasks), _max_research_concurrency())
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    bundles = list(executor.map(lambda t: active_deps.research(t, scope), tasks))
            else:
                bundles = []
            for task, bundle in zip(tasks, bundles):
                evidence.append(bundle)
                active_store.write_evidence(run_id, bundle)
                active_tracer.event(
                    run_id,
                    "research:bundle",
                    {"task_id": task.task_id, "hypothesis_id": task.hypothesis_id},
                )

            active_store.update_status(run_id, RunStatus.VERIFYING.value)
            for bundle in list(evidence):
                verdict = verify_evidence(bundle)
                if verdict.repair_tickets:
                    active_store.update_status(run_id, RunStatus.REPAIRING.value)
                    verdict = _repair_verdict(
                        verdict=verdict,
                        bundle=bundle,
                        scope=scope,
                        deps=active_deps,
                        evidence=evidence,
                        store=active_store,
                        tracer=active_tracer,
                        run_id=run_id,
                    )
                verdicts.append(verdict)
                active_store.write_verdict(run_id, verdict)
                active_tracer.event(
                    run_id,
                    "verify:verdict",
                    {
                        "hypothesis_id": verdict.hypothesis_id,
                        "verdict": verdict.verdict,
                        "confidence": verdict.confidence,
                    },
                )

        active_store.update_status(run_id, RunStatus.SYNTHESIZING.value)
        recall_floor_met = _recall_floor_met(plan, verdicts)
        result = synthesize_result(
            run_id=run_id,
            scope=scope,
            plan=plan,
            evidence=evidence,
            verdicts=verdicts,
            information_requests=information_requests,
            scenarios=scenarios,
            recall_floor_met=recall_floor_met,
        )
        if blocking_requests:
            status = RunStatus.NEEDS_INFORMATION.value
        elif result["determination"]["status"] == "verified":
            status = RunStatus.DONE.value
        else:
            status = RunStatus.NEEDS_REVIEW.value

        active_store.write_result(run_id, result)
        active_store.update_status(
            run_id,
            status,
            reason="; ".join(result["determination"]["reasons"][:3]),
        )
        active_tracer.event(run_id, "run:status", {"status": status})
        active_tracer.finish(run_id, {"status": status})
        active_store.write_artifact(run_id, "trace_events", active_tracer.events)
        return ResearchRunResult(
            run_id=run_id,
            status=status,
            information_requests=information_requests,
            scenarios=scenarios,
            evidence=evidence,
            verdicts=verdicts,
            result=result,
            trace_events=list(active_tracer.events),
        )
    except Exception as exc:
        active_store.update_status(run_id, RunStatus.FAILED.value, reason=str(exc))
        active_tracer.event(
            run_id,
            "run:failed",
            {"error_type": type(exc).__name__, "message": str(exc)},
        )
        active_tracer.finish(run_id, {"status": RunStatus.FAILED.value})
        active_store.write_artifact(run_id, "trace_events", active_tracer.events)
        raise


def resume_research_sync(
    run_id: str,
    *,
    deps: str | ResearchDeps = "offline",
    store: Any | None = None,
    tracer: WorkshopTracer | None = None,
) -> ResearchRunResult:
    active_store = store or get_default_store()
    record = active_store.resume_run(run_id)
    return run_research_sync(
        record["input"],
        deps=deps,
        store=active_store,
        tracer=tracer,
        run_id=run_id,
    )


def scope_from_input(input_payload: dict[str, Any], run_id: str) -> ScopePack:
    description = str(input_payload.get("project_description") or "").strip()
    facility_payload = dict(input_payload.get("facility") or {})
    _apply_location_answer(facility_payload, input_payload.get("provided_estimates") or {})
    chemicals = _chemicals_from_input(input_payload, description)
    equipment = _equipment_from_description(description)
    waste_streams = _waste_from_input(input_payload, description)
    provided_documents = _documents_from_input(input_payload)
    process_discharge = input_payload.get("process_discharge", False)
    if "wastewater" in description.lower() or "discharge" in description.lower():
        process_discharge = True

    scope = ScopePack(
        run_id=run_id,
        facility=Facility(
            address=str(facility_payload.get("address") or ""),
            jurisdiction_stack=list(facility_payload.get("jurisdiction_stack") or []),
            county=facility_payload.get("county"),
            city=facility_payload.get("city"),
            naics=facility_payload.get("naics"),
            sic=facility_payload.get("sic"),
        ),
        project_change=ProjectChange(
            description=description,
            equipment=equipment,
            chemicals=chemicals,
            waste_streams=waste_streams,
            disturbance_acres=input_payload.get("disturbance_acres"),
            process_discharge=process_discharge,
        ),
        missing_facts=[],
        assumptions=[],
        provided_documents=provided_documents,
    )
    return scope.model_copy(
        update={
            "missing_facts": _missing_facts(scope),
            "assumptions": _assumptions(input_payload),
        }
    )


def _apply_location_answer(facility_payload: dict[str, Any], provided_estimates: dict[str, Any]) -> None:
    """Fold a jurisdiction/county answer (a reply to the 'what county controls this facility'
    missing fact) into the facility so the jurisdiction resolver can resolve the controlling
    air district / CUPA. The answer arrives under a field naming county/jurisdiction/location."""
    if facility_payload.get("county"):
        return
    for field, value in provided_estimates.items():
        key = str(field).lower()
        if not any(token in key for token in ("county", "jurisdiction", "location")):
            continue
        text = str(value).strip()
        if not text:
            continue
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) >= 2:
            facility_payload.setdefault("city", parts[0])
            county = parts[1]
        else:
            county = parts[0]
        county = re.sub(r"\bcount(?:y|ies)\b\.?", "", county, flags=re.IGNORECASE).strip()
        if county:
            facility_payload["county"] = county
        return


def _coerce_quantity(value: Any) -> float | None:
    """A provided quantity arrives from the UI as free text ('30', '30 gal'). Pull the
    leading number so the hazmat threshold compare gets a real float, not a string."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def _documents_from_input(input_payload: dict[str, Any]) -> list[ProvidedDocument]:
    """Ingest intake-uploaded documents (SDS/TDS/permits) so each research subagent gets
    the real facility data in its context. Accepts both the production `documents` key and
    the legacy `demo_documents` alias; drops non-dict junk fail-closed."""
    raw = input_payload.get("documents")
    if not raw:
        raw = input_payload.get("demo_documents") or []
    # Provided docs ride along in every hypothesis's context, so bound each one's text:
    # 8 full SDS would otherwise overflow a small-context worker. ~6k chars keeps the SDS
    # identity + composition (Sections 1-3) while staying affordable.
    per_doc_cap = _provided_doc_char_cap()
    documents: list[ProvidedDocument] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "")
        if len(text) > per_doc_cap:
            text = text[:per_doc_cap] + "\n[...document truncated to fit context; re-upload a focused excerpt if a later section is needed...]"
        documents.append(
            ProvidedDocument(
                name=str(item.get("name") or "document").strip() or "document",
                type=str(item.get("type") or "other"),
                text=text,
            )
        )
    return documents


def _provided_doc_char_cap() -> int:
    raw = _empty_to_none(_env("RESEARCH_CORE_MAX_DOC_CHARS"))
    if raw:
        try:
            return max(1000, int(raw))
        except ValueError:
            pass
    return 6000


def _coerce_deps(deps: str | ResearchDeps) -> ResearchDeps:
    if isinstance(deps, ResearchDeps):
        return deps
    if deps in {"fake", "offline"}:
        return ResearchDeps(mode=deps)
    return ResearchDeps(mode="live")


def _sandbox_policy(scope: ScopePack, artifact_root: str | Path | None) -> SandboxPolicy:
    root = artifact_root
    if root is None:
        root = _env(ARTIFACT_ROOT_ENV)
    if root is None:
        root = (
            Path("/tmp/permitpilot-research-artifacts")
            if _running_on_modal()
            else Path.cwd() / ".research-artifacts"
        )
    return SandboxPolicy(
        run_id=scope.run_id,
        artifact_root=Path(root),
        allowed_hosts=_allowed_hosts_from_env(),
        allow_network=_bool_env(ALLOW_NETWORK_ENV, default=True),
        allow_browser=_bool_env(ALLOW_BROWSER_ENV, default=True),
        search_endpoint=_empty_to_none(_env(SEARCH_ENDPOINT_ENV)),
    )


def _running_on_modal() -> bool:
    return bool(_env("MODAL_TASK_ID") or _env("MODAL_ENVIRONMENT"))


def _allowed_hosts_from_env() -> tuple[str, ...]:
    raw = _env(ALLOWED_HOSTS_ENV)
    if not raw:
        return DEFAULT_ALLOWED_HOSTS
    hosts = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    return hosts or DEFAULT_ALLOWED_HOSTS


def _agent_model_from_env() -> str | None:
    # Default the research agents to gpt-5.5; RESEARCH_CORE_AGENT_MODEL overrides.
    return _empty_to_none(_env(AGENT_MODEL_ENV)) or DEFAULT_AGENT_MODEL


def _repair_model_from_env() -> str | None:
    # RESEARCH_CORE_REPAIR_MODEL overrides; defaults to a strong model so repair stays
    # high-quality even when the worker is cheap.
    return _empty_to_none(_env(REPAIR_MODEL_ENV)) or DEFAULT_REPAIR_MODEL


RESEARCH_CONCURRENCY_ENV = "RESEARCH_CORE_MAX_CONCURRENCY"
DEFAULT_RESEARCH_CONCURRENCY = 8


def _max_research_concurrency() -> int:
    raw = _empty_to_none(_env(RESEARCH_CONCURRENCY_ENV))
    if raw is not None:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_RESEARCH_CONCURRENCY


def _bool_env(name: str, *, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env(name: str) -> str | None:
    import os

    return os.environ.get(name)


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _trace_endpoint(input_payload: dict[str, Any]) -> str | None:
    value = input_payload.get("raindrop_endpoint")
    return str(value) if value else None


def _information_requests(scope: ScopePack, plan: Plan) -> list[InformationRequest]:
    requests: dict[str, InformationRequest] = {}
    for fact in scope.missing_facts:
        requests[fact.field] = _request_from_missing_fact(fact)
    for status in plan.coverage_family_statuses:
        for field in status.missing_facts:
            if field not in requests:
                requests[field] = InformationRequest(
                    field=field,
                    question=_question_for_field(field),
                    why_needed=status.reason,
                    blocks=[status.family],
                )
    return list(requests.values())


def _request_from_missing_fact(fact: MissingFact) -> InformationRequest:
    return InformationRequest(
        field=fact.field,
        question=_question_for_field(fact.field),
        why_needed=fact.why_needed,
        blocks=list(fact.blocks),
    )


def _scenarios_for_requests(
    input_payload: dict[str, Any],
    requests: list[InformationRequest],
) -> list[Scenario]:
    scenarios: list[Scenario] = []
    provided_estimates = input_payload.get("provided_estimates") or {}
    for request in requests:
        estimate = provided_estimates.get(request.field)
        if estimate is not None:
            scenarios.extend(scenarios_for_missing_fact(request, provided_estimate=estimate))
        elif _can_continue_with_gaps(input_payload):
            options = information_gap_options(request, user_does_not_know=True)
            scenarios.extend(options.scenarios)
    return scenarios


def _blocking_requests(
    scope: ScopePack,
    requests: list[InformationRequest],
    input_payload: dict[str, Any],
) -> list[InformationRequest]:
    if _can_continue_with_gaps(input_payload):
        return []
    required_scope_fields = {
        fact.field
        for fact in scope.missing_facts
        if fact.field in {"chemicals.quantity", "chemicals.unit"}
    }
    return [request for request in requests if request.field in required_scope_fields]


def _can_continue_with_gaps(input_payload: dict[str, Any]) -> bool:
    return bool(
        input_payload.get("user_does_not_know")
        or input_payload.get("continue_with_scenarios")
        or input_payload.get("provided_estimates")
    )


def _missing_facts(scope: ScopePack) -> list[MissingFact]:
    facts: list[MissingFact] = []
    for chemical in scope.project_change.chemicals:
        if chemical.quantity is None:
            facts.append(
                MissingFact(
                    field="chemicals.quantity",
                    why_needed=(
                        "Hazardous-material thresholds depend on the maximum "
                        "quantity stored on site."
                    ),
                    blocks=["hazmat"],
                )
            )
        if chemical.quantity is not None and not chemical.unit:
            facts.append(
                MissingFact(
                    field="chemicals.unit",
                    why_needed="Quantity units are required for threshold comparison.",
                    blocks=["hazmat"],
                )
            )
    return facts


def _assumptions(input_payload: dict[str, Any]) -> list[Assumption]:
    assumptions: list[Assumption] = []
    for field, value in (input_payload.get("provided_estimates") or {}).items():
        assumptions.append(
            Assumption(
                field=field,
                value=value,
                basis="User-provided estimate.",
                confidence=0.7,
                provenance=FactProvenance.PROVIDED_ESTIMATE,
            )
        )
    return assumptions


def _chemicals_from_input(input_payload: dict[str, Any], description: str) -> list[Chemical]:
    if input_payload.get("chemicals"):
        return [Chemical.model_validate(item) for item in input_payload["chemicals"]]

    lower = description.lower()
    if "solvent" not in lower and "chemical" not in lower and "paint" not in lower:
        return []
    provided_estimates = input_payload.get("provided_estimates") or {}
    quantity = _coerce_quantity(provided_estimates.get("chemicals.quantity"))
    unit = provided_estimates.get("chemicals.unit") or None
    if quantity is None:
        quantity = _quantity_from_text(description)
    if unit is None:
        unit = _unit_from_text(description)
    name = "solvent" if "solvent" in lower else "chemical"
    return [
        Chemical(
            name=name,
            quantity=quantity,
            unit=unit,
            hazard="flammable" if "solvent" in lower or "paint" in lower else None,
        )
    ]


def _equipment_from_description(description: str) -> list[Equipment]:
    lower = description.lower()
    equipment: list[Equipment] = []
    if "coating" in lower or "spray" in lower or "paint" in lower:
        equipment.append(
            Equipment(kind="coating_booth", description="Coating or paint operation")
        )
    if "boiler" in lower:
        equipment.append(Equipment(kind="boiler", description="Boiler"))
    return equipment


def _waste_from_input(input_payload: dict[str, Any], description: str) -> list[WasteStream]:
    if input_payload.get("waste_streams"):
        return [WasteStream.model_validate(item) for item in input_payload["waste_streams"]]
    if "waste" not in description.lower():
        return []
    return [WasteStream(description="process waste", kg_per_month=None)]


def _quantity_from_text(description: str) -> float | None:
    if "unknown quantity" in description.lower():
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:gal|gallon|gallons|kg|lb|lbs)?", description, re.I)
    if not match:
        return None
    return float(match.group(1))


def _unit_from_text(description: str) -> str | None:
    lower = description.lower()
    if "gallon" in lower or " gal" in lower:
        return "gal"
    if "kg" in lower:
        return "kg"
    if "lb" in lower:
        return "lb"
    return None


def _question_for_field(field: str) -> str:
    if "quantity" in field:
        return "What is the maximum quantity stored or used on site?"
    if "unit" in field:
        return "What unit applies to the quantity?"
    if "jurisdiction" in field or "county" in field:
        return "What county and local jurisdiction control the facility?"
    if "disturbance_acres" in field:
        return "How many acres will be disturbed?"
    return f"What value should be used for {field}?"


def _fake_research_bundle(task: ResearchTask, scope: ScopePack) -> dict[str, Any]:
    hypothesis_text = task.hypothesis_id.replace("-", " ")
    quote = (
        f"{hypothesis_text} applies when project facts trigger the listed program."
    )
    has_missing_required_fact = _task_blocked_by_scope_gap(task, scope)
    conclusion = "needs_review" if has_missing_required_fact else "applies"
    return {
        "hypothesis_id": task.hypothesis_id,
        "task_id": task.task_id,
        "sources": [
            {
                "url": f"https://offline.local/{task.hypothesis_id.lower()}",
                "source_name": "Offline deterministic registry source",
                "authority_rank": 1,
                "fetched_at": "2026-01-01T00:00:00Z",
                "effective_date": "2026-01-01",
                "currency_status": "current",
                "quote": quote,
            }
        ],
        "extracted_claims": [
            {
                "field": "applicability",
                "value": conclusion,
                "source_url": f"https://offline.local/{task.hypothesis_id.lower()}",
                "quote": quote,
                "confidence": 0.9,
            }
        ],
        "researcher_conclusion": conclusion,
        "uncertainties": (
            ["Required project facts are missing; scenario or human review needed."]
            if has_missing_required_fact
            else []
        ),
    }


def _task_blocked_by_scope_gap(task: ResearchTask, scope: ScopePack) -> bool:
    families = {
        task.assigned_agent.removesuffix("_researcher"),
        task.hypothesis_id.split("-")[1].lower() if "-" in task.hypothesis_id else "",
    }
    for fact in scope.missing_facts:
        if set(fact.blocks).intersection(families):
            return True
    return False


def _bundle_from_agent_output(
    *,
    hypothesis_id: str,
    task_id: str,
    output: dict[str, Any],
) -> dict[str, Any]:
    if output.get("ok") is False:
        error = output.get("error") if isinstance(output.get("error"), dict) else {}
        return _agent_error_bundle(
            hypothesis_id=hypothesis_id,
            task_id=task_id,
            code=str(error.get("code") or "agent_output_unavailable"),
            message=str(error.get("message") or "Agent returned an unavailable result."),
            output=output,
        )

    if _looks_like_evidence_bundle(output):
        bundle = dict(output)
        bundle.setdefault("hypothesis_id", hypothesis_id)
        bundle.setdefault("task_id", task_id)
        bundle.setdefault("uncertainties", [])
        return bundle

    finding = output.get("finding") if isinstance(output.get("finding"), dict) else None
    if finding is None:
        return _agent_error_bundle(
            hypothesis_id=hypothesis_id,
            task_id=task_id,
            code="invalid_agent_output",
            message="Agent output did not include an evidence bundle or submitted finding.",
            output=output,
        )

    metadata = finding.get("metadata") if isinstance(finding.get("metadata"), dict) else {}
    rich_sources = metadata.get("sources")
    sources = (
        rich_sources
        if isinstance(rich_sources, list) and all(isinstance(item, dict) for item in rich_sources)
        else _sources_from_finding(finding)
    )
    conclusion = str(
        metadata.get("researcher_conclusion")
        or metadata.get("conclusion")
        or ("applies" if float(finding.get("confidence") or 0) >= 0.9 else "needs_review")
    )
    claims = metadata.get("extracted_claims")
    if not isinstance(claims, list):
        first_source_url = str(sources[0].get("url")) if sources else ""
        quote = str(finding.get("summary") or finding.get("title") or "")
        claims = [
            {
                "field": "applicability",
                "value": conclusion,
                "source_url": first_source_url,
                "quote": quote,
                "confidence": float(finding.get("confidence") or 0),
            }
        ]
    return {
        "hypothesis_id": hypothesis_id,
        "task_id": task_id,
        "sources": sources,
        "extracted_claims": claims,
        "researcher_conclusion": conclusion,
        "uncertainties": [
            str(item)
            for item in metadata.get("uncertainties", [])
            if isinstance(item, str)
        ],
        "agent_output": output,
    }


def _looks_like_evidence_bundle(output: dict[str, Any]) -> bool:
    return all(key in output for key in ("sources", "extracted_claims", "researcher_conclusion"))


def _sources_from_finding(finding: dict[str, Any]) -> list[dict[str, Any]]:
    urls = finding.get("sources")
    if not isinstance(urls, list):
        return []
    summary = str(finding.get("summary") or finding.get("title") or "")
    return [
        {
            "url": str(url),
            "source_name": _source_name(str(url)),
            # Honest, host-derived authority so the verifier's authority gate works
            # now that fetching is open: curated authority -> 1, other .gov -> 2,
            # anything else -> 3 (which fails the verifier's rank<=2 requirement).
            "authority_rank": _source_authority_rank(str(url)),
            "fetched_at": None,
            "effective_date": None,
            "currency_status": "unconfirmed",
            "quote": summary,
        }
        for url in urls
        if isinstance(url, str)
    ]


def _source_authority_rank(url: str) -> int:
    return source_authority_rank(url, _allowed_hosts_from_env())


def _source_name(url: str) -> str:
    host = urlparse(url).hostname
    return host or "submitted source"


def _agent_error_bundle(
    *,
    hypothesis_id: str,
    task_id: str,
    code: str,
    message: str,
    exception_type: str | None = None,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if exception_type:
        error["exception_type"] = exception_type
    if output is not None:
        error["output"] = output
    return {
        "hypothesis_id": hypothesis_id,
        "task_id": task_id,
        "sources": [],
        "extracted_claims": [],
        "researcher_conclusion": "needs_review",
        "uncertainties": [message],
        "agent_error": error,
    }


def _clear_retry_counts(verdict: VerificationVerdict) -> VerificationVerdict:
    tickets = [
        ticket.model_copy(update={"max_attempts_remaining": 0})
        for ticket in verdict.repair_tickets
    ]
    if verdict.verdict == "needs_review" and not verdict.distrust_reasons:
        return verdict.model_copy(
            update={
                "repair_tickets": tickets,
                "distrust_reasons": [
                    "Verifier does not trust the repaired work after retry."
                ],
            }
        )
    return verdict.model_copy(update={"repair_tickets": tickets})


def _repair_verdict(
    *,
    verdict: VerificationVerdict,
    bundle: dict[str, Any],
    scope: ScopePack,
    deps: ResearchDeps,
    evidence: list[dict[str, Any]],
    store: Any,
    tracer: WorkshopTracer,
    run_id: str,
) -> VerificationVerdict:
    attempts = 0
    repaired_verdicts: list[VerificationVerdict] = []
    passing_repair: VerificationVerdict | None = None
    unresolved_tickets = []
    unresolved_reasons: list[str] = []
    for ticket in verdict.repair_tickets:
        if attempts >= deps.max_repair_attempts:
            unresolved_tickets.append(ticket)
            unresolved_reasons.append(
                f"Repair budget exhausted before resolving {ticket.ticket_id}: "
                f"{ticket.observed_problem}"
            )
            continue
        if ticket.max_attempts_remaining <= 0:
            unresolved_tickets.append(ticket)
            unresolved_reasons.append(
                f"Repair attempts exhausted for {ticket.ticket_id}: "
                f"{ticket.observed_problem}"
            )
            continue
        repaired = deps.repair(ticket, bundle, scope)
        repaired["repair_ticket_id"] = ticket.ticket_id
        repaired["repair_of_hypothesis_id"] = verdict.hypothesis_id
        evidence.append(repaired)
        store.write_evidence(run_id, repaired)
        repaired_verdict = verify_evidence(repaired)
        repaired_verdicts.append(repaired_verdict)
        if repaired_verdict.verdict == "pass":
            passing_repair = repaired_verdict
        else:
            unresolved_tickets.append(ticket.model_copy(update={"max_attempts_remaining": 0}))
            unresolved_reasons.extend(repaired_verdict.distrust_reasons)
        tracer.event(
            run_id,
            "repair:attempt",
            {
                "ticket_id": ticket.ticket_id,
                "hypothesis_id": verdict.hypothesis_id,
                "repaired_verdict": repaired_verdict.verdict,
            },
        )
        attempts += 1

    if passing_repair is not None and not unresolved_tickets:
        return passing_repair.model_copy(
            update={
                "repair_tickets": [],
                "distrust_reasons": [],
            }
        )

    distrust_reasons = _unique_strings(
        [
            *(verdict.distrust_reasons if passing_repair is None else []),
            *unresolved_reasons,
        ]
    )

    return verdict.model_copy(
        update={
            "verdict": "needs_review",
            "repair_tickets": unresolved_tickets,
            "distrust_reasons": distrust_reasons,
            "confidence": (
                max(
                    [verdict.confidence, *[item.confidence for item in repaired_verdicts]]
                )
                if passing_repair is not None
                else min(
                    [verdict.confidence, *[item.confidence for item in repaired_verdicts]]
                )
                if repaired_verdicts
                else verdict.confidence
            ),
        }
    )


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _recall_floor_met(plan: Plan, verdicts: list[VerificationVerdict]) -> bool:
    task_count = len(plan.research_tasks)
    if task_count == 0:
        return True
    pass_count = sum(1 for verdict in verdicts if verdict.verdict == "pass")
    return pass_count / task_count >= 0.8
