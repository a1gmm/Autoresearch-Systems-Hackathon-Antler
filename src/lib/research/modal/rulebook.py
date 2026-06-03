from __future__ import annotations

from runtime_models import RuntimeTask


REVIEW_SIGNALS = [
    "Is the claim grounded by a real allowed source?",
    "Is applicability separated from compliance obligation?",
    "Is the conclusion scoped to the facility facts?",
    "Are missing facts called out instead of guessed?",
    "Are SDS-driven determinations explicit when relevant?",
    "Are local agency and state/federal jurisdiction layers separated?",
    "Does the answer avoid overclaiming exemptions?",
]


def build_rulebook(task: RuntimeTask, skill_text: str | None = None) -> str:
    domains = ", ".join(task.allowed_domains) if task.allowed_domains else "No explicit allowed domains provided."
    skill_section = skill_text.strip() if skill_text else "No skill text provided."

    signals = "\n".join(f"- {signal}" for signal in REVIEW_SIGNALS)
    return "\n".join([
        "PermitPilot CrossBeam Modal Reviewer Rulebook",
        f"Task family: {task.family}",
        f"Hypothesis: {task.hypothesis_id}",
        f"Question: {task.question}",
        f"Allowed domains: {domains}",
        "",
        "Skill context:",
        skill_section,
        "",
        "Project-specific review signals:",
        signals,
        "",
        "Same-worker repair policy:",
        (
            "If the draft needs repair, send the critique back to the same worker identity "
            "and the same RuntimeTask. The repair must address reviewer findings verbatim, "
            "preserve grounded evidence, and avoid introducing final permit prose."
        ),
    ])
