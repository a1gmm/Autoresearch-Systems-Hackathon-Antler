from __future__ import annotations

import json

from research_core.registry import (
    PROGRAM_REGISTRY,
    _SKILLS_ROOT,
    _TRIGGERS,
    skill_for_hypothesis,
)


def test_registry_is_built_from_skill_program_files():
    # Skills are the source of truth: one program.json per program, ids match exactly.
    files = list(_SKILLS_ROOT.glob("*/program.json"))
    ids_from_files = {json.loads(path.read_text(encoding="utf-8"))["id"] for path in files}
    ids_from_registry = {program.id for program in PROGRAM_REGISTRY}
    assert len(files) == len(PROGRAM_REGISTRY)
    assert ids_from_files == ids_from_registry


def test_every_program_has_its_skill_md_and_a_known_trigger():
    trigger_fns = set(_TRIGGERS.values())
    for program in PROGRAM_REGISTRY:
        assert (_SKILLS_ROOT / program.id / "SKILL.md").exists(), program.id
        assert program.triggered_by in trigger_fns, program.id
        assert program.family
        assert program.hypotheses


def test_program_folder_name_equals_program_id_and_owns_its_hypotheses():
    for program in PROGRAM_REGISTRY:
        for hypothesis in program.hypotheses:
            assert skill_for_hypothesis(hypothesis.id) == program.id
