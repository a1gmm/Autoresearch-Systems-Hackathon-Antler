import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rulebook import build_rulebook  # noqa: E402
from runtime_models import RuntimeTask  # noqa: E402


def test_rulebook_includes_task_family_allowed_domains_and_repair_policy():
    task = RuntimeTask(
        task_id="task-1",
        hypothesis_id="H-AIR-201",
        question="Does Rule 201 apply?",
        family="air",
        skill_id="air-permit-skill",
        allowed_domains=["aqmd.gov", "arb.ca.gov"],
    )

    text = build_rulebook(task, skill_text="Only use source-backed applicability findings.")

    assert "air" in text
    assert "aqmd.gov" in text
    assert "arb.ca.gov" in text
    assert "Only use source-backed applicability findings." in text
    assert "same worker" in text.lower()
    assert "repair" in text.lower()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")
