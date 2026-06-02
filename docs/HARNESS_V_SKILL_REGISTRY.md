# Harness V - Python Skill Assets

Companion to `HARNESS_V_TOOL_CATALOG.md`. The TypeScript skill registry was
retired with the TypeScript research runtime. The active runtime now reads skill
and jurisdiction assets from `src/lib/research/skills/**` while Python owns the
agent definitions, tool scoping, planning, verification, repair, and synthesis.

## Active Skill Surfaces

| Python surface | Role |
| --- | --- |
| `src/research_core/agents.py` | OpenAI Agents SDK agent definitions and sandbox tool binding |
| `src/research_core/tools.py` | Regulatory web, browser, document, spreadsheet, and artifact tools |
| `src/research_core/jurisdiction_skills.py` | Markdown skill asset loading for county/city context |
| `src/research_core/planner.py` | Registry-driven coverage families and task fanout |
| `src/research_core/verifier.py` | Verification, repair tickets, confidence gates, distrust reasons |
| `src/research_core/orchestrator.py` | Runtime sequencing and bounded repair/information loops |

## Runtime Skills

| Skill | Python owner | Trigger | Done |
| --- | --- | --- | --- |
| Intake & completeness | `orchestrator.scope_from_input` | New project payload | Scope has missing facts, assumptions, and jurisdiction gaps |
| Planning & jurisdiction | `planner.py`, `jurisdiction_resolve.py` | Scope ready | Coverage statuses, hypotheses, and research tasks exist |
| Discovery | `discovery.py` | Proposed novel regime/form | Candidate hypotheses are staged as discovery work |
| Research | `agents.py` researcher agent | One planned task | Evidence bundle or fail-closed review bundle |
| Verification | `verifier.py` | Evidence bundle ready | Pass/fail/needs_review verdict with confidence |
| Repair orchestration | `orchestrator._repair_verdict` | Repair tickets exist | Repaired evidence passes or attempt budget is exhausted |
| Scenario support | `scenarios.py` | User lacks exact facts or provides estimates | Low/expected/high scenarios with provenance |
| Synthesis | `synthesis.py` | Plan, evidence, verdicts, requests ready | Determination, report payload, review reasons |
| Durable execution | `modal_app.py`, `store.py` | Start/resume run | Supabase-backed run record is updated through terminal status |

## Validation

The former TypeScript registry and validator are not part of the active runtime.
Current drift protection comes from Python tests under `src/research_core/tests/`,
especially agent/tool, planner, verifier, scenario, orchestration, Modal, and
store coverage.

The invariant remains the same as Harness V: tool capabilities are scoped by the
runtime, not trusted to model prose alone. The live researcher and repair agents
receive only sandboxed functions for web use, browser use, PDF/DOCX/spreadsheet
reads, artifact writes, and terminal finding submission.
