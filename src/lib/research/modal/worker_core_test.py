"""Pure-unit test for the injectable research worker core.

No framework, no network, no modal, no openai. Run directly:
    python3 src/lib/research/modal/worker_core_test.py

Injects fake fetch_fn / extract_fn so we test the loop, not the IO.
"""

from __future__ import annotations

import sys

from worker import run_research_core


def test_real_extraction_builds_bundle_from_fetched_source() -> None:
    # The fetch returns page text; the extract returns a real claim + the
    # verbatim quote it grounded on. The core must thread these into a bundle
    # whose source quote == the fetched evidence (not a hardcoded fixture).
    fetched = {
        "url": "https://example.gov/rule-201",
        "source_name": "SCAQMD Rule 201",
        "authority_rank": 1,
        "text": "A person shall not build any equipment that may emit air contaminants without authorization.",
    }

    def fake_fetch(url: str) -> dict:
        assert url == "https://example.gov/rule-201"
        return fetched

    def fake_extract(question: str, source_text: str) -> dict:
        assert "emit air contaminants" in source_text
        return {
            "field": "permit_trigger",
            "value": "new or altered emitting equipment",
            "quote": "A person shall not build any equipment that may emit air contaminants without authorization.",
            "confidence": 0.9,
            "conclusion": "applies",
        }

    bundle = run_research_core(
        hypothesis_id="H-AIR-201",
        question="Does Rule 201 require a permit for new emitting equipment?",
        source_url="https://example.gov/rule-201",
        fetch_fn=fake_fetch,
        extract_fn=fake_extract,
    )

    assert bundle["hypothesis_id"] == "H-AIR-201"
    assert bundle["sources"][0]["url"] == "https://example.gov/rule-201"
    assert bundle["sources"][0]["quote"] == fetched["text"]
    assert bundle["sources"][0]["fetched_at"].endswith("Z")
    assert bundle["sources"][0]["content_hash"].startswith("sha256:")
    assert bundle["extracted_claims"][0]["field"] == "permit_trigger"
    assert bundle["extracted_claims"][0]["value"] == "new or altered emitting equipment"
    assert bundle["extracted_claims"][0]["quote"] == fetched["text"]
    assert bundle["researcher_conclusion"] == "applies"


def test_fails_closed_when_fetch_raises() -> None:
    def boom_fetch(url: str) -> dict:
        raise RuntimeError("network down")

    def never_extract(question: str, source_text: str) -> dict:  # pragma: no cover
        raise AssertionError("extract should not run when fetch fails")

    bundle = run_research_core(
        hypothesis_id="H-AIR-201",
        question="q",
        source_url="https://example.gov/x",
        fetch_fn=boom_fetch,
        extract_fn=never_extract,
    )

    assert bundle["hypothesis_id"] == "H-AIR-201"
    assert bundle["sources"] == []
    assert bundle["extracted_claims"] == []
    assert bundle["researcher_conclusion"] == "needs_review"
    assert len(bundle["uncertainties"]) >= 1


def main() -> int:
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    if failures:
        print(f"\n{failures} failed")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
