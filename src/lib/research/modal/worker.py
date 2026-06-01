"""Modal Sandbox worker for PermitPilot research tasks.

For each ResearchTask, this worker spins up an ephemeral Modal Sandbox,
runs a trivial isolation-proof command inside it, and returns a
deterministic EvidenceBundle dict (mirrors src/lib/research/fixtures/sources.ts).

Modeled after modal-labs/openai-agents-python-example: one sandbox per
subagent / per research task.

Invocation:
    modal run src/lib/research/modal/worker.py --task-json '{"task_id":"T-1","hypothesis_id":"H-AIR-201"}'
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import sys
import urllib.request
from typing import Callable

# modal is only needed for the remote/sandbox entrypoints. The pure research
# core (run_research_core) must be importable without it so it can be unit
# tested offline (worker_core_test.py) and reused outside Modal.
try:
    import modal

    app = modal.App("permitpilot-research")
    # The research function fetches sources and calls OpenAI inside the container,
    # so the image needs the openai SDK (urllib is stdlib). debian_slim keeps the
    # base small; pip_install adds the one runtime dep.
    sandbox_image = modal.Image.debian_slim().pip_install("openai>=1.0", "pypdf>=4.0")
    # OPENAI_API_KEY reaches the container via a Modal Secret, never baked into the
    # image. The secret must expose the key as OPENAI_API_KEY (what default_extract_fn
    # reads via os.environ). Register with:
    #   modal secret create permitpilot-openai OPENAI_API_KEY=sk-...
    # Resolved lazily (from_name doesn't hit the network at import time).
    openai_secret = modal.Secret.from_name("permitpilot-openai")
    _HAS_MODAL = True
except ModuleNotFoundError:  # pragma: no cover - exercised only without modal installed
    modal = None  # type: ignore[assignment]
    app = None  # type: ignore[assignment]
    sandbox_image = None  # type: ignore[assignment]
    openai_secret = None  # type: ignore[assignment]
    _HAS_MODAL = False


FetchFn = Callable[[str], dict]
ExtractFn = Callable[[str, str], dict]


def run_research_core(
    hypothesis_id: str,
    question: str,
    source_url: str,
    fetch_fn: FetchFn,
    extract_fn: ExtractFn,
) -> dict:
    """Pure, injectable research loop: fetch a source, extract a grounded claim,
    assemble an EvidenceBundle. No modal, no network, no SDK dependency of its
    own — all IO arrives through fetch_fn / extract_fn. Fails closed to a
    needs_review bundle if any step raises, so a fetch/extract failure can never
    masquerade as a real determination.
    """
    try:
        source = fetch_fn(source_url)
        source_text = source["text"]
        extracted = extract_fn(question, source_text)
    except Exception as exc:  # noqa: BLE001 - any failure must fail closed
        return _failed_bundle(hypothesis_id, f"research failed: {exc}")

    quote = extracted.get("quote", source_text)
    fetched_at = source.get("fetched_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    content_hash = source.get("content_hash") or _content_hash(source_text)
    return {
        "hypothesis_id": hypothesis_id,
        "sources": [
            {
                "url": source["url"],
                "source_name": source.get("source_name", source["url"]),
                "authority_rank": source.get("authority_rank", 1),
                "fetched_at": fetched_at,
                "content_hash": content_hash,
                "effective_date": source.get("effective_date"),
                "quote": quote,
            }
        ],
        "extracted_claims": [
            {
                "field": extracted.get("field", "source_claim"),
                "value": str(extracted.get("value", "")),
                "source_url": source["url"],
                "quote": quote,
                "confidence": extracted.get("confidence", 0.5),
            }
        ],
        "researcher_conclusion": extracted.get("conclusion", "needs_review"),
        "uncertainties": extracted.get("uncertainties", []),
    }


def _content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_source_text(raw: bytes, url: str) -> str:
    """Turn fetched bytes into grounding-quality text.

    PDFs must not be utf-8 force-decoded — that yields U+FFFD mojibake the
    verifier can never ground a verbatim quote against. Detect a PDF by magic
    bytes (or .pdf url) and pull real text from its content streams; everything
    else is decoded as utf-8 text.
    """
    is_pdf = raw[:5] == b"%PDF-" or url.lower().split("?")[0].endswith(".pdf")
    if is_pdf:
        return _extract_pdf_text(raw)
    return raw.decode("utf-8", errors="replace")


def _extract_pdf_text(raw: bytes) -> str:
    """Extract text from PDF bytes. Prefer pypdf when present (handles compressed
    streams, real layout); fall back to a stdlib content-stream scan so the
    function still works offline / without the dependency."""
    try:
        from io import BytesIO

        from pypdf import PdfReader  # type: ignore[import-not-found]

        reader = PdfReader(BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        if text:
            return text
    except Exception:  # noqa: BLE001 - any pypdf failure falls back to the stdlib scan
        pass
    return _extract_pdf_text_stdlib(raw)


def _extract_pdf_text_stdlib(raw: bytes) -> str:
    """Dependency-free PDF text scan: pull the strings drawn by Tj/TJ text
    operators out of uncompressed content streams. Good enough to recover
    verbatim phrases from simple regulation PDFs; not a full PDF renderer."""
    import re
    import zlib

    chunks: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.DOTALL):
        body = match.group(1)
        try:
            body = zlib.decompress(body)
        except Exception:  # noqa: BLE001 - stream may be uncompressed
            pass
        chunks.append(body)
    if not chunks:
        chunks.append(raw)

    pieces: list[str] = []
    for body in chunks:
        # ( ... ) Tj  and  [ (..) (..) ] TJ  — capture the parenthesized strings.
        for s in re.findall(rb"\(((?:[^()\\]|\\.)*)\)", body):
            text = s.decode("latin-1", errors="replace")
            text = text.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
            pieces.append(text)
    return " ".join(pieces).strip()


def default_fetch_fn(url: str) -> dict:
    """Real source fetch over HTTP. Returns grounding-quality text for extraction
    (PDF content is parsed, not byte-decoded)."""
    req = urllib.request.Request(url, headers={"User-Agent": "permitpilot-research/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - allowlisted sources upstream
        raw = resp.read()
    return {"url": url, "source_name": url, "authority_rank": 1, "text": extract_source_text(raw, url)}


def default_extract_fn(question: str, source_text: str) -> dict:
    """Real extraction via OpenAI. Raises when no key is set so the core fails
    closed rather than fabricating a claim."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY unset; extraction unavailable")
    from openai import OpenAI  # imported lazily so the core stays dependency-free

    client = OpenAI(api_key=api_key)
    model = os.environ.get("OPENAI_INTAKE_MODEL", "gpt-4o-mini")
    prompt = (
        "Given the regulation text, answer the research question. Return ONLY JSON: "
        '{"field":string,"value":string,"quote":string (verbatim span from the text '
        'that grounds the claim),"confidence":number,"conclusion":'
        '"applies"|"does_not_apply"|"needs_review"}.\n\n'
        f"QUESTION: {question}\n\nTEXT:\n{source_text[:8000]}"
    )
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        max_tokens=800,
    )
    return json.loads(completion.choices[0].message.content or "{}")


# Mirror of src/lib/research/fixtures/sources.ts. Kept in sync by hand
# because the hackathon stage doesn't need a build-time pipeline. If you
# add a fixture in sources.ts, mirror it here.
SOURCE_FIXTURES: dict[str, dict] = {
    "scaqmd_rule_201": {
        "source_name": "SCAQMD Rule 201",
        "url": "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-201.pdf",
        "authority_rank": 1,
        "fetched_at": "2026-05-30T00:00:00Z",
        "content_hash": "sha256:demo-scaqmd-rule-201",
        "effective_date": None,
        "quote": "A person shall not build, erect, install, alter, or replace any equipment that may emit air contaminants without written authorization.",
        "extracted": {"permit_trigger": "new or altered equipment that may emit air contaminants"},
    },
    "scaqmd_rule_219": {
        "source_name": "SCAQMD Rule 219",
        "url": "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-219.pdf",
        "authority_rank": 1,
        "fetched_at": "2026-05-30T00:00:00Z",
        "content_hash": "sha256:demo-scaqmd-rule-219",
        "effective_date": None,
        "quote": "Equipment listed in this rule may be exempt from written permit requirements when the listed conditions are satisfied.",
        "extracted": {"exemption_check_required": True},
    },
    "scaqmd_rule_222": {
        "source_name": "SCAQMD Rule 222",
        "url": "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-222.pdf",
        "authority_rank": 1,
        "fetched_at": "2026-05-30T00:00:00Z",
        "content_hash": "sha256:demo-scaqmd-rule-222",
        "effective_date": None,
        "quote": "Owners or operators of specified equipment shall file registration information when the rule applies to that equipment category.",
        "extracted": {"registration_possible": True},
    },
    "industrial_general_permit": {
        "source_name": "California Industrial General Permit",
        "url": "https://www.waterboards.ca.gov/water_issues/programs/stormwater/industrial.html",
        "authority_rank": 1,
        "fetched_at": "2026-05-30T00:00:00Z",
        "content_hash": "sha256:demo-ca-igp",
        "effective_date": None,
        "quote": "Industrial facilities described by regulated Standard Industrial Classification codes must obtain coverage under the Industrial General Permit unless an exclusion applies.",
        "extracted": {"regulated_sic": "3471"},
    },
    "construction_general_permit": {
        "source_name": "California Construction General Permit",
        "url": "https://www.waterboards.ca.gov/water_issues/programs/stormwater/construction.html",
        "authority_rank": 1,
        "fetched_at": "2026-05-30T00:00:00Z",
        "content_hash": "sha256:demo-ca-cgp",
        "effective_date": None,
        "quote": "Construction activity that disturbs one or more acres of soil must obtain coverage under the Construction General Permit.",
        "extracted": {"acreage_threshold": 1},
    },
    "hmbp_threshold_bad": {
        "source_name": "California HMBP Threshold Summary",
        "url": "https://calepa.ca.gov/cupa/hazardous-materials-business-plan/",
        "authority_rank": 1,
        "fetched_at": "2026-05-30T00:00:00Z",
        "content_hash": "sha256:demo-hmbp-bad",
        "effective_date": None,
        "quote": "Businesses must submit information for hazardous materials at or above threshold quantities.",
        "extracted": {"overbroad_claim": "HMBP applies to all hazardous material storage"},
    },
    "hazardous_waste_generator": {
        "source_name": "EPA Hazardous Waste Generator Categories",
        "url": "https://www.epa.gov/hwgenerators/categories-hazardous-waste-generators",
        "authority_rank": 1,
        "fetched_at": "2026-05-30T00:00:00Z",
        "content_hash": "sha256:demo-epa-generator",
        "effective_date": None,
        "quote": "Generator category depends on the amount of hazardous waste generated in a calendar month.",
        "extracted": {"generator_quantity_required": True},
    },
    "wastewater_pretreatment": {
        "source_name": "EPA Pretreatment Program Overview",
        "url": "https://www.epa.gov/npdes/national-pretreatment-program",
        "authority_rank": 1,
        "fetched_at": "2026-05-30T00:00:00Z",
        "content_hash": "sha256:demo-epa-pretreatment",
        "effective_date": None,
        "quote": "Industrial users that discharge process wastewater to publicly owned treatment works may be subject to pretreatment requirements.",
        "extracted": {"process_discharge_required": True},
    },
}


# Mirror of fixtureForHypothesis() in workers.ts.
HYPOTHESIS_TO_FIXTURE: dict[str, str] = {
    "H-AIR-201": "scaqmd_rule_201",
    "H-AIR-VOC": "scaqmd_rule_201",
    "H-AIR-219": "scaqmd_rule_219",
    "H-AIR-222": "scaqmd_rule_222",
    "H-STORM-IGP": "industrial_general_permit",
    "H-STORM-CGP": "construction_general_permit",
    "H-HAZMAT-HMBP": "hmbp_threshold_bad",
    "H-WASTE-GENERATOR": "hazardous_waste_generator",
    "H-WASTEWATER-PRETREATMENT": "wastewater_pretreatment",
}


def _failed_bundle(hypothesis_id: str, reason: str) -> dict:
    return {
        "hypothesis_id": hypothesis_id,
        "sources": [],
        "extracted_claims": [],
        "researcher_conclusion": "needs_review",
        "uncertainties": [reason],
    }


def _preliminary_conclusion(hypothesis_id: str) -> str:
    if hypothesis_id in ("H-WASTE-GENERATOR", "H-WASTEWATER-PRETREATMENT"):
        return "needs_review"
    return "applies"


def _build_evidence_bundle(hypothesis_id: str) -> dict:
    fixture_id = HYPOTHESIS_TO_FIXTURE.get(hypothesis_id, "")
    fixture = SOURCE_FIXTURES.get(fixture_id)
    if fixture is None:
        return _failed_bundle(hypothesis_id, f"No source fixture found for {hypothesis_id}")

    extracted = fixture["extracted"]
    first_field = next(iter(extracted.keys()), "source_claim")
    first_value = next(iter(extracted.values()), hypothesis_id)

    return {
        "hypothesis_id": hypothesis_id,
        "sources": [
            {
                "url": fixture["url"],
                "source_name": fixture["source_name"],
                "authority_rank": fixture["authority_rank"],
                "fetched_at": fixture["fetched_at"],
                "content_hash": fixture["content_hash"],
                "effective_date": fixture["effective_date"],
                "quote": fixture["quote"],
            }
        ],
        "extracted_claims": [
            {
                "field": first_field,
                "value": str(first_value),
                "source_url": fixture["url"],
                "quote": fixture["quote"],
                "confidence": 0.82,
            }
        ],
        "researcher_conclusion": _preliminary_conclusion(hypothesis_id),
        "uncertainties": (
            ["Monthly hazardous waste quantity is missing."]
            if hypothesis_id == "H-WASTE-GENERATOR"
            else []
        ),
    }


def _modal_function(**kwargs):
    """Apply @app.function only when modal is installed; otherwise a no-op so the
    module (and its pure core) imports without modal for offline unit tests.
    Injects the OpenAI secret so OPENAI_API_KEY is present in the container env."""
    if _HAS_MODAL:
        kwargs.setdefault("secrets", [openai_secret])
        return app.function(**kwargs)
    return lambda fn: fn


def _modal_local_entrypoint():
    if _HAS_MODAL:
        return app.local_entrypoint()
    return lambda fn: fn


@_modal_function(image=sandbox_image, timeout=120)
def research_task(task_spec: dict) -> dict:
    """Run one research task inside a Modal Sandbox: fetch the hypothesis's
    primary source, extract a grounded claim via the real core, return evidence.
    Falls back to the deterministic fixture bundle when no source URL is known
    for the hypothesis, so unmapped hypotheses still fail closed cleanly.
    """
    hypothesis_id = task_spec.get("hypothesis_id", "")
    question = task_spec.get("question") or task_spec.get("claim_to_test") or ""
    source_url = task_spec.get("source_url") or _fixture_source_url(hypothesis_id)

    if not source_url:
        return _build_evidence_bundle(hypothesis_id)

    def fetch_with_task_metadata(url: str) -> dict:
        source = default_fetch_fn(url)
        source["source_name"] = task_spec.get("source_name") or source["source_name"]
        source["authority_rank"] = task_spec.get("authority_rank") or source["authority_rank"]
        source["effective_date"] = task_spec.get("effective_date")
        return source

    return run_research_core(
        hypothesis_id=hypothesis_id,
        question=question,
        source_url=source_url,
        fetch_fn=fetch_with_task_metadata,
        extract_fn=default_extract_fn,
    )


def _fixture_source_url(hypothesis_id: str) -> str:
    fixture = SOURCE_FIXTURES.get(HYPOTHESIS_TO_FIXTURE.get(hypothesis_id, ""))
    return fixture["url"] if fixture else ""


@_modal_local_entrypoint()
def main(task_json: str) -> None:
    """Entry point for `modal run`. Parses task JSON, calls research_task, prints result JSON.

    The TS bridge (runModalPool.ts) extracts the last JSON line from stdout,
    so we keep stdout disciplined: status comes from Modal itself, we only
    print the final JSON line.
    """
    task_spec = json.loads(task_json)
    result = research_task.remote(task_spec)
    # Single JSON line on stdout, marked for the TS bridge to grep.
    sys.stdout.write("PERMITPILOT_BUNDLE_JSON " + json.dumps(result) + "\n")
    sys.stdout.flush()
