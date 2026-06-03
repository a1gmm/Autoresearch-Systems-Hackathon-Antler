from research_core.models import ScopePack
from research_core.planner import plan_research


def scope_with_equipment_and_solvent() -> ScopePack:
    return ScopePack.model_validate(
        {
            "run_id": "run_1",
            "facility": {
                "address": "x",
                "jurisdiction_stack": [],
                "county": "Los Angeles",
                "city": "Los Angeles",
                "naics": None,
                "sic": None,
            },
            "project_change": {
                "description": "coating booth with solvent",
                "equipment": [{"kind": "coating_booth", "description": "new booth"}],
                "chemicals": [{"name": "solvent", "quantity": 60, "unit": "gal"}],
                "waste_streams": [],
                "disturbance_acres": None,
                "process_discharge": False,
            },
            "missing_facts": [],
            "assumptions": [],
        }
    )


def test_planner_creates_registry_backed_hypotheses():
    plan = plan_research(scope_with_equipment_and_solvent())
    ids = {h.id for h in plan.research_graph}

    assert "H-AIR-201" in ids
    assert "H-HAZMAT-HMBP" in ids


def test_planner_adds_jurisdiction_context_to_tasks():
    plan = plan_research(scope_with_equipment_and_solvent())

    assert plan.research_tasks
    assert all(task.jurisdiction_context for task in plan.research_tasks)
    assert "Los Angeles" in plan.research_tasks[0].jurisdiction_context
    dumped_task = plan.model_dump()["research_tasks"][0]
    assert dumped_task["jurisdiction_context"]
    assert "Los Angeles" in dumped_task["jurisdiction_context"]


def test_planner_omits_jurisdiction_context_when_county_and_city_unknown():
    scope = scope_with_equipment_and_solvent().model_copy(deep=True)
    scope.facility.county = None
    scope.facility.city = None

    plan = plan_research(scope)

    assert plan.research_tasks
    assert all(task.jurisdiction_context is None for task in plan.research_tasks)
    assert "jurisdiction_context" not in plan.model_dump()["research_tasks"][0]


def test_research_tasks_use_researcher_tool_boundaries():
    plan = plan_research(scope_with_equipment_and_solvent())
    task = plan.research_tasks[0]

    assert "read_skill" in task.allowed_tools
    assert "quarantine_injection" in task.allowed_tools
    assert "analyze_voc_content" in task.allowed_tools
    assert "get_form" in task.blocked_tools
    assert "propose_map_entry" in task.blocked_tools


def test_research_budget_is_production_grade():
    plan = plan_research(scope_with_equipment_and_solvent())
    task = plan.research_tasks[0]
    # Production, not demo: up to 60 min of durable research per hypothesis.
    assert task.budget.max_runtime_seconds == 3600
    assert task.budget.max_model_calls >= 12
    assert task.budget.max_sources >= 5
