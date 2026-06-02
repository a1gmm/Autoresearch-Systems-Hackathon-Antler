from __future__ import annotations

import re

from pydantic import BaseModel


class QuarantineResult(BaseModel):
    flagged: bool
    reason: str | None = None


INJECTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"ignore (all |the )?(previous|prior|above) (instructions|prompts?)", re.I),
        "override-instructions",
    ),
    (
        re.compile(r"disregard (the |your )?(system|previous) (prompt|instructions)", re.I),
        "override-instructions",
    ),
    (re.compile(r"you are now\b", re.I), "role-redefinition"),
    (
        re.compile(
            r"(^|\n)\s*(system|developer)\s*:\s*"
            r"(ignore|disregard|you are now|do not|never|always|approve every)",
            re.I,
        ),
        "fake-role-tag",
    ),
    (
        re.compile(r"\b(system prompt|developer prompt|hidden prompt)\b", re.I),
        "prompt-exfiltration-or-tampering",
    ),
    (
        re.compile(
            r"\b(?:also\s+)?(?:add|include|drop|remove|skip|ignore)\s+"
            r"(?:(?:the|a|an|all|air|wastewater|hazmat|stormwater|waste|fire|building|"
            r"environmental|required)\s+)*permits?\b"
            r"(?![-\s]+(?:applications?|exempt|forms?|portal|package|conditions?|"
            r"limits?|required|requirements?|equipment)\b)"
            r"|\b(skip|remove|ignore)\s+required\s+permits?\b"
            r"|\bdrop\s+(required\s+)?permits?\s+from\s+the\s+plan\b",
            re.I,
        ),
        "permit-set-tampering",
    ),
    (
        re.compile(r"\bapprove\s+(all|every)\s+permits?\b", re.I),
        "permit-set-tampering",
    ),
)


def quarantine_injection(text: str) -> QuarantineResult:
    for pattern, reason in INJECTION_PATTERNS:
        if pattern.search(text):
            return QuarantineResult(flagged=True, reason=reason)
    return QuarantineResult(flagged=False)
