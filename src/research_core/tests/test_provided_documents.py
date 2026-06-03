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
