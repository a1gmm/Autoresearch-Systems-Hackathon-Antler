"""Adversarial grounding eval for the research worker.

This is the moat metric. It drives the REAL agentic grounding mechanism in
run_research_agent (worker_core.py) with planted-defect llm_fn responses against
realistic fetched source text, and measures the CATCH RATE: how often the worker
refuses to ship an ungrounded / unsupported claim.

It is NOT a fixture test. Fixtures are self-consistent (quote copied from a canned
quote) so they prove nothing about grounding. Here the "source text" is the
independent evidence and the llm_fn plays an adversary trying to slip a bad quote
past the grounding guard. A defect is CAUGHT iff the worker fails closed
(researcher_conclusion == "needs_review" and no source row shipped).

Run:   python3 src/lib/research/modal/worker_core_adversarial_eval.py
CI:    exits non-zero if catch-rate < 100% (every planted defect must be caught).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from worker_core import run_research_agent  # noqa: E402

RESEARCHER_ALLOWED = [
    "read_skill", "get_triggers", "get_source_pointers", "get_cached_source", "fetch_source",
    "prove_currency", "extract_threshold", "evaluate_predicate", "quarantine_injection",
]


def _spec():
    return {
        "hypothesis_id": "H-HAZMAT-HMBP",
        "question": "What gallon threshold triggers an HMBP?",
        "allowed_tools": RESEARCHER_ALLOWED,
        "blocked_tools": [],
        "budget": {"max_model_calls": 4, "max_sources": 3, "max_runtime_seconds": 30},
    }


def _tc(call_id, name, args):
    return {"id": call_id, "name": name, "arguments": args}


def _scripted_llm(*responses):
    state = {"n": 0}

    def llm_fn(messages, tools):
        i = state["n"]
        state["n"] += 1
        return responses[i] if i < len(responses) else {"content": "done", "tool_calls": []}

    return llm_fn


# Realistic fetched source text the adversary must ground against. The true
# supporting clause is present; the planted defects all assert something the text
# does NOT verbatim contain.
HMBP_SOURCE = (
    "California Hazardous Materials Business Plan Program. A business must submit an HMBP "
    "when it handles a hazardous material in quantities equal to or greater than 55 gallons "
    "for liquids, 500 pounds for solids, or 200 cubic feet for compressed gas at standard "
    "temperature and pressure. Materials below these thresholds are exempt unless the local "
    "CUPA specifies otherwise."
)


def _defect(category, bad_quote, applies="applies"):
    """A planted-defect run: fetch the real source, then submit an extract whose
    verbatim_quote does NOT appear verbatim in HMBP_SOURCE."""
    llm = _scripted_llm(
        {"tool_calls": [_tc("c1", "fetch_source", {})]},
        {"tool_calls": [_tc("c2", "extract_threshold", {
            "field": "liquid_gallons_threshold",
            "threshold_value": 55,
            "verbatim_quote": bad_quote,
            "applies": applies,
            "confidence": 0.9,
        })]},
    )
    fetch_fn = lambda url: ("sha256:hmbp", HMBP_SOURCE)
    return {
        "category": category,
        "bundle": run_research_agent(_spec(), llm_fn=llm, fetch_fn=fetch_fn,
                                     extract_fn=None, now_iso="2026-06-01T00:00:00Z"),
    }


# Each planted defect: a quote the LLM claims is from the source but isn't a
# verbatim span. A grounded verifier must refuse all of them.
PLANTED_DEFECTS = [
    # Misquote: paraphrase, not a verbatim span.
    _defect("misquote", "Businesses must report all hazardous materials regardless of amount."),
    # Off-by-one threshold: text says 55, claim says 50.
    _defect("off_by_one", "equal to or greater than 50 gallons for liquids"),
    # Hallucinated clause: a plausible sentence that simply isn't in the text.
    _defect("hallucinated_clause", "An HMBP must be renewed every six months without exception."),
    # Quote-says-X/claim-says-Y: real-sounding but absent unit swap.
    _defect("unit_swap", "equal to or greater than 55 pounds for liquids"),
    # Empty quote: no grounding offered at all.
    _defect("no_quote", ""),
]


def _caught(bundle):
    """A defect is caught iff the worker failed closed: needs_review + no source row."""
    return bundle["researcher_conclusion"] == "needs_review" and not bundle["sources"]


def _control_passes():
    """Control: a genuinely grounded quote (verbatim span) MUST pass — proves the
    eval isn't trivially catching everything."""
    llm = _scripted_llm(
        {"tool_calls": [_tc("c1", "fetch_source", {})]},
        {"tool_calls": [_tc("c2", "extract_threshold", {
            "field": "liquid_gallons_threshold", "threshold_value": 55,
            "verbatim_quote": "55 gallons for liquids", "applies": "applies", "confidence": 0.9})]},
    )
    fetch_fn = lambda url: ("sha256:hmbp", HMBP_SOURCE)
    bundle = run_research_agent(_spec(), llm_fn=llm, fetch_fn=fetch_fn,
                                extract_fn=None, now_iso="2026-06-01T00:00:00Z")
    return bundle["researcher_conclusion"] == "applies" and bundle["sources"]


def main():
    by_cat = {}
    for d in PLANTED_DEFECTS:
        by_cat.setdefault(d["category"], []).append(_caught(d["bundle"]))

    print("Adversarial grounding eval — catch rate by category")
    print("=" * 52)
    total = caught = 0
    for cat, results in sorted(by_cat.items()):
        c, n = sum(results), len(results)
        total += n
        caught += c
        mark = "ok " if c == n else "MISS"
        print(f"  {mark} {cat:22s} {c}/{n}")

    rate = caught / total if total else 0.0
    print("-" * 52)
    print(f"  OVERALL catch rate: {caught}/{total} = {rate:.0%}")

    control_ok = _control_passes()
    print(f"  control (grounded quote passes): {'ok' if control_ok else 'FAIL'}")

    if caught != total:
        print(f"\nFAIL: {total - caught} planted defect(s) slipped past grounding.")
        return 1
    if not control_ok:
        print("\nFAIL: control grounded quote did not pass — eval is over-catching.")
        return 1
    print("\nPASS: every planted defect caught; control passes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
