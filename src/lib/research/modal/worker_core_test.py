"""Pure-unit test for the injectable research worker core.

No framework, no network, no modal, no openai. Run directly:
    python3 src/lib/research/modal/worker_core_test.py

Injects fake fetch_fn / extract_fn so we test the loop, not the IO.
"""

from __future__ import annotations

import sys

from worker import extract_source_text, run_research_core


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


def test_extract_source_text_decodes_html_as_utf8() -> None:
    # Non-PDF content (HTML/plain) is decoded as text directly.
    raw = "<html><body>Rule 201 requires a permit.</body></html>".encode("utf-8")
    text = extract_source_text(raw, "https://example.gov/rule.html")
    assert "Rule 201 requires a permit." in text


def test_extract_source_text_pulls_words_from_pdf_not_mojibake() -> None:
    # A PDF byte stream must NOT be utf-8 force-decoded (that yields mojibake the
    # verifier can't ground on). The extracted text must contain the real words
    # from the PDF's content stream, and must not be dominated by replacement
    # chars. We build a tiny valid PDF with the literal phrase below.
    phrase = "Permit required for emitting equipment"
    pdf_bytes = _minimal_pdf(phrase)

    text = extract_source_text(pdf_bytes, "https://example.gov/rule-201.pdf")

    assert phrase in text
    # The lossy old path produced strings full of U+FFFD; assert we didn't.
    assert "�" not in text


def _minimal_pdf(phrase: str) -> bytes:
    """Smallest hand-rolled PDF that renders one line of text, for offline tests."""
    content = f"BT /F1 12 Tf 72 720 Td ({phrase}) Tj ET".encode("latin-1")
    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
    )
    objs.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer\n<< /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R >>\n"
    out += b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    return bytes(out)


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
