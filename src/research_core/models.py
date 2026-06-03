from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    QUEUED = "queued"
    SCOPING = "scoping"
    NEEDS_INFORMATION = "needs_information"
    PLANNING = "planning"
    RESEARCHING = "researching"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    SYNTHESIZING = "synthesizing"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class FactProvenance(str, Enum):
    PROVIDED_EXACT = "provided_exact"
    PROVIDED_ESTIMATE = "provided_estimate"
    AGENT_SUGGESTED_USER_ACCEPTED = "agent_suggested_user_accepted"
    AGENT_INFERRED = "agent_inferred"
    MISSING = "missing"


CoverageFamily = Literal[
    "air",
    "stormwater",
    "hazmat",
    "waste",
    "wastewater",
    "land_use",
    "fire_code",
    "ceqa",
    "osha",
]
CoverageStatus = Literal[
    "active",
    "blocked_missing_fact",
    "out_of_scope",
    "discovery_candidate",
]


class Facility(BaseModel):
    address: str
    jurisdiction_stack: list[str]
    county: str | None
    city: str | None
    naics: str | None
    sic: str | None


class Equipment(BaseModel):
    kind: str
    description: str


class Chemical(BaseModel):
    name: str
    quantity: float | None
    unit: str | None
    hazard: str | None = None


class WasteStream(BaseModel):
    description: str
    kg_per_month: float | None


class ProjectChange(BaseModel):
    description: str
    equipment: list[Equipment]
    chemicals: list[Chemical]
    waste_streams: list[WasteStream]
    disturbance_acres: float | None
    process_discharge: bool | None


class ProvidedDocument(BaseModel):
    """A facility-provided document (SDS, technical data sheet, permit, equipment spec)
    uploaded at intake. Text is extracted client-side and rides along in scope so each
    research subagent can analyze the real composition/usage data, not a stand-in."""

    name: str
    type: str = "other"
    text: str = ""


class MissingFact(BaseModel):
    field: str
    why_needed: str
    blocks: list[str]


class Assumption(BaseModel):
    field: str
    value: Any
    basis: str
    confidence: float = Field(ge=0, le=1)
    provenance: FactProvenance


class ScopePack(BaseModel):
    run_id: str
    facility: Facility
    project_change: ProjectChange
    missing_facts: list[MissingFact]
    assumptions: list[Assumption]
    provided_documents: list[ProvidedDocument] = Field(default_factory=list)


class InformationRequest(BaseModel):
    field: str
    question: str
    why_needed: str
    blocks: list[str]


class ScenarioAssumption(BaseModel):
    field: str
    value: Any
    unit: str | None = None
    provenance: FactProvenance


class Scenario(BaseModel):
    id: str
    label: Literal["low", "expected", "high"]
    assumptions: list[ScenarioAssumption]
    rationale: str
    affects: list[str]
