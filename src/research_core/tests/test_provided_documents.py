from __future__ import annotations

from research_core.orchestrator import scope_from_input


def test_scope_ingests_uploaded_documents_so_agents_can_analyze_them():
    scope = scope_from_input(
        {
            "project_description": "UV inkjet printing operation in Oxnard",
            "facility": {"county": "Ventura", "city": "Oxnard"},
            "demo_documents": [
                {"name": "SDS BLACK", "type": "sds", "text": "Contains acrylate monomers and BAPO photoinitiator."},
                {"name": "SDS CYAN", "type": "sds", "text": "Contains isobornyl acrylate."},
            ],
        },
        "run_1",
    )

    assert len(scope.provided_documents) == 2
    assert scope.provided_documents[0].name == "SDS BLACK"
    assert scope.provided_documents[0].type == "sds"
    assert "acrylate" in scope.provided_documents[0].text


def test_scope_accepts_production_documents_key_as_alias():
    scope = scope_from_input(
        {
            "project_description": "x",
            "documents": [{"name": "Permit", "type": "permit", "text": "Authority to Construct."}],
        },
        "run_2",
    )

    assert [doc.name for doc in scope.provided_documents] == ["Permit"]


def test_scope_has_no_documents_when_none_supplied():
    scope = scope_from_input({"project_description": "x"}, "run_3")
    assert scope.provided_documents == []


def test_scope_skips_malformed_document_entries():
    scope = scope_from_input(
        {"project_description": "x", "demo_documents": ["not a dict", {"text": "no name ok"}, {}]},
        "run_4",
    )
    # Garbage strings are dropped; dict entries are kept (name defaults).
    assert len(scope.provided_documents) == 2
    assert scope.provided_documents[0].text == "no name ok"


# --- provided_estimates: answering missing facts (county + quantity) -----------

def test_provided_estimates_resolve_county_from_jurisdiction_answer():
    scope = scope_from_input(
        {
            "project_description": "Inkjet printing operation using solvent",
            "provided_estimates": {"location:county_unknown": "Oxnard, Ventura County"},
        },
        "run_loc",
    )
    assert scope.facility.county == "Ventura"
    assert scope.facility.city == "Oxnard"


def test_provided_estimates_set_chemical_quantity_and_clear_missing_fact():
    scope = scope_from_input(
        {
            "project_description": "A shop stores solvent of unknown quantity",
            "provided_estimates": {"chemicals.quantity": "30 gal", "chemicals.unit": "gal"},
        },
        "run_qty",
    )
    assert scope.project_change.chemicals
    assert scope.project_change.chemicals[0].quantity == 30.0
    assert scope.project_change.chemicals[0].unit == "gal"
    # The quantity-blocking missing fact is now satisfied.
    assert not any(f.field == "chemicals.quantity" for f in scope.missing_facts)


def test_explicit_facility_county_is_not_overwritten_by_answer():
    scope = scope_from_input(
        {
            "project_description": "x",
            "facility": {"county": "Los Angeles"},
            "provided_estimates": {"location:county_unknown": "Ventura"},
        },
        "run_keep",
    )
    assert scope.facility.county == "Los Angeles"
