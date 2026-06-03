"""Pure helpers for the PermitPilot Modal research worker.

No third-party imports (no modal/httpx/openai) so this is unit-testable in any
plain Python environment. worker.py does the I/O and imports these.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

# hypothesis_id -> the single official source the worker may fetch (the allowlist).
SOURCE_POINTERS: dict[str, dict] = {
    "H-AIR-201": {"source_name": "SCAQMD Rule 201", "url": "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-201.pdf", "authority_rank": 1},
    "H-AIR-VOC": {"source_name": "SCAQMD Rule 201", "url": "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-201.pdf", "authority_rank": 1},
    "H-AIR-219": {"source_name": "SCAQMD Rule 219", "url": "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-219.pdf", "authority_rank": 1},
    "H-AIR-222": {"source_name": "SCAQMD Rule 222", "url": "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-222.pdf", "authority_rank": 1},
    "H-STORM-IGP": {"source_name": "California Industrial General Permit", "url": "https://www.waterboards.ca.gov/water_issues/programs/stormwater/industrial.html", "authority_rank": 1},
    "H-STORM-CGP": {"source_name": "California Construction General Permit", "url": "https://www.waterboards.ca.gov/water_issues/programs/stormwater/construction.html", "authority_rank": 1},
    "H-HAZMAT-HMBP": {"source_name": "California HMBP Threshold Summary", "url": "https://calepa.ca.gov/cupa/hazardous-materials-business-plan/", "authority_rank": 1},
    "H-WASTE-GENERATOR": {"source_name": "EPA Hazardous Waste Generator Categories", "url": "https://www.epa.gov/hwgenerators/categories-hazardous-waste-generators", "authority_rank": 1},
    "H-WASTEWATER-PRETREATMENT": {"source_name": "EPA Pretreatment Program Overview", "url": "https://www.epa.gov/npdes/national-pretreatment-program", "authority_rank": 1},
    "H-HAZMAT-UST": {"source_name": "California UST Program (HSC 25281)", "url": "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=HSC&sectionNum=25281.", "authority_rank": 1},
    "H-HAZMAT-APSA": {"source_name": "Aboveground Petroleum Storage Act (HSC 25270)", "url": "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=HSC&sectionNum=25270.", "authority_rank": 1},
    "H-HAZMAT-CALARP": {"source_name": "CalARP (19 CCR Ch. 2)", "url": "https://calepa.ca.gov/wp-content/uploads/2024/08/California-Code-of-Regulations-Title-19-Division-5-Chapter-2-%E2%80%93-California-Accidental-Release-Prevention.pdf", "authority_rank": 1},
    "H-AIR-AB2588": {"source_name": "AB 2588 Air Toxics Hot Spots", "url": "https://ww2.arb.ca.gov/our-work/programs/ab-2588-air-toxics-hot-spots", "authority_rank": 1},
    "H-HAZMAT-PROP65": {"source_name": "Proposition 65 (HSC 25249.6)", "url": "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=HSC&sectionNum=25249.6.", "authority_rank": 1},
    "H-WASTE-CA-TITLE22": {"source_name": "DTSC non-RCRA hazardous waste", "url": "https://dtsc.ca.gov/non-rcra-hazardous-wastes/", "authority_rank": 1},
    "H-WASTE-MEDICAL": {"source_name": "Medical Waste Management Act (HSC 117600)", "url": "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=HSC&sectionNum=117600.", "authority_rank": 1},
    "H-WASTE-UNIVERSAL": {"source_name": "DTSC Universal Waste", "url": "https://dtsc.ca.gov/requirements-for-handlers-and-or-recyclers/", "authority_rank": 1},
    "H-AIR-TITLE-V": {"source_name": "CARB Title V Operating Permits", "url": "https://ww2.arb.ca.gov/our-work/programs/federal-clean-air-act-title-v-operating-permits/fcaa-title-v-overview", "authority_rank": 1},
    "H-WASTEWATER-WDR": {"source_name": "Waterboards Waste Discharge Requirements", "url": "https://www.waterboards.ca.gov/water_issues/programs/waste_discharge_requirements/", "authority_rank": 1},
}

# Per-hypothesis extraction guidance. `field` MUST match what verifier.ts reads
# for its math branches (liquid_gallons_threshold for HMBP); others are informational.
EXTRACTION_HINTS: dict[str, dict] = {
    "H-HAZMAT-HMBP": {"field": "liquid_gallons_threshold", "ask": "the numeric gallon threshold at or above which a Hazardous Materials Business Plan (HMBP) is required for a hazardous liquid"},
    "H-STORM-CGP": {"field": "acreage_threshold", "ask": "the number of acres of soil disturbance that triggers Construction General Permit coverage"},
    "H-STORM-IGP": {"field": "regulated_sic", "ask": "which industrial activities or SIC categories must obtain Industrial General Permit coverage"},
    "H-AIR-201": {"field": "permit_trigger", "ask": "what equipment or activity requires written authorization or a permit to construct"},
    "H-AIR-VOC": {"field": "permit_trigger", "ask": "what equipment or activity requires written authorization or a permit to construct"},
    "H-AIR-219": {"field": "exemption_check_required", "ask": "which equipment is exempt from written permit requirements and under what conditions"},
    "H-AIR-222": {"field": "registration_possible", "ask": "which equipment may use registration instead of a full permit"},
    "H-WASTE-GENERATOR": {"field": "generator_quantity_required", "ask": "what monthly hazardous waste quantity determines the generator category"},
    "H-WASTEWATER-PRETREATMENT": {"field": "process_discharge_required", "ask": "when industrial process wastewater discharge triggers pretreatment requirements"},
}

# hypothesis_id -> EHS domain skill id (src/lib/research/skills/<id>/SKILL.md).
# Mirrors skillForHypothesis.ts on the TS side; read_skill resolves the current
# hypothesis to its skill so the agent can orient before fetching the primary source.
SKILL_FOR_HYPOTHESIS: dict[str, str] = {
    "H-AIR-201": "scaqmd-permit-to-construct", "H-AIR-VOC": "scaqmd-permit-to-construct",
    "H-AIR-219": "scaqmd-rule-219-exemption", "H-AIR-222": "scaqmd-rule-222-registration",
    "H-STORM-IGP": "ca-industrial-general-permit", "H-STORM-CGP": "ca-construction-general-permit",
    "H-HAZMAT-HMBP": "ca-hmbp",
    "H-WASTE-GENERATOR": "epa-hazwaste-generator",
    "H-WASTEWATER-PRETREATMENT": "epa-pretreatment",
    "H-HAZMAT-UST": "ca-ust-program",
    "H-HAZMAT-APSA": "ca-apsa-spcc",
    "H-HAZMAT-CALARP": "ca-calarp-program",
    "H-AIR-AB2588": "ca-ab2588-hot-spots",
    "H-HAZMAT-PROP65": "ca-prop-65",
    "H-WASTE-CA-TITLE22": "ca-title22-hazwaste",
    "H-WASTE-MEDICAL": "ca-medical-waste",
    "H-WASTE-UNIVERSAL": "ca-universal-waste",
    "H-AIR-TITLE-V": "ca-title-v-permit",
    "H-WASTEWATER-WDR": "ca-wdr-npdes",
}

ALLOWED_HOSTS = {
    "www.aqmd.gov", "aqmd.gov",
    "www.waterboards.ca.gov", "waterboards.ca.gov",
    "calepa.ca.gov", "www.calepa.ca.gov",
    "www.epa.gov", "epa.gov",
    # Additional verified California authorities (registry-expansion programs):
    "leginfo.legislature.ca.gov",
    "oehha.ca.gov",
    "dtsc.ca.gov",
    "ww2.arb.ca.gov", "arb.ca.gov",
    "osfm.fire.ca.gov",
    "www.cdph.ca.gov", "cdph.ca.gov",
}


def host_allowed(url: str) -> bool:
    """Tier 1: a curated allowlist authority (highest trust)."""
    host = (urlparse(url).hostname or "").lower()
    return host in ALLOWED_HOSTS


def host_credible(url: str) -> bool:
    """Tier 2: fetchable fallback when the curated allowlist yields nothing —
    any US government domain (.gov, incl. *.ca.gov / county / city .gov). NOT the open
    web: non-government hosts stay out. Allowlist-first; this only broadens to other
    official sources so a discoverable rule is never unreachable."""
    host = (urlparse(url).hostname or "").lower()
    return host in ALLOWED_HOSTS or host.endswith(".gov")


def evidence_row(run_id: str, bundle: dict) -> dict:
    """Pure mapping: EvidenceBundle -> research_evidence row (Supabase upsert payload)."""
    return {"run_id": run_id, "hypothesis_id": bundle.get("hypothesis_id", ""), "bundle": bundle}


def failed_bundle(hypothesis_id: str, reason: str) -> dict:
    return {
        "hypothesis_id": hypothesis_id,
        "sources": [],
        "extracted_claims": [],
        "researcher_conclusion": "needs_review",
        "uncertainties": [reason],
    }


def assemble_evidence(hypothesis_id: str, pointer: dict, content_hash: str, fetched_at: str, extract: dict) -> dict:
    """Pure mapping: extraction result + fetch metadata -> EvidenceBundle dict.

    Falls back to needs_review when no verbatim quote was grounded.
    """
    quote = (extract.get("verbatim_quote") or "").strip()
    if not quote:
        return failed_bundle(hypothesis_id, "No supporting verbatim quote found in the fetched source.")

    field = extract.get("field") or "source_claim"
    value = extract.get("threshold_value")
    applies = extract.get("applies") or "needs_review"
    try:
        confidence = float(extract.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.5

    return {
        "hypothesis_id": hypothesis_id,
        "sources": [
            {
                "url": pointer["url"],
                "source_name": pointer["source_name"],
                "authority_rank": pointer["authority_rank"],
                "fetched_at": fetched_at,
                "content_hash": content_hash,
                "effective_date": extract.get("effective_date"),
                "quote": quote,
            }
        ],
        "extracted_claims": [
            {
                "field": field,
                "value": "" if value is None else str(value),
                "source_url": pointer["url"],
                "quote": quote,
                "confidence": confidence,
            }
        ],
        "researcher_conclusion": applies if applies in ("applies", "does_not_apply", "needs_review") else "needs_review",
        "uncertainties": [],
    }


# ---------------------------------------------------------------------------
# Catalog-governed agentic researcher loop
# ---------------------------------------------------------------------------

# Prompts and tool definitions live in sibling modules so this file is just the
# agent loop + pure mappings.
from prompts import RESEARCH_SKILL_PROMPT  # noqa: E402
from tools import TOOL_SCHEMAS, handle_chemical_tool, norm_cas  # noqa: E402

_UNUSED_DOC = """OpenAI function schemas, the system prompt, and chemical-tool
handlers were extracted to tools.py / prompts.py. This file keeps the loop."""
# Non-LLM-callable researcher tools (allowed in scope but not offered as model tools):
# get_cached_source (no cache in demo) and quarantine_injection (embedded in fetch_source).
_NON_CALLABLE = {"get_cached_source", "quarantine_injection"}


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _int_or(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def exposed_tool_schemas(allowed_tools: list[str]) -> list[dict]:
    """The OpenAI tools to offer = allowed_tools that we actually implement as model tools."""
    return [TOOL_SCHEMAS[t] for t in allowed_tools if t in TOOL_SCHEMAS]


def run_research_agent(task_spec: dict, *, llm_fn, fetch_fn, extract_fn, now_iso: str,
                       source_pointers: dict | None = None, read_skill_fn=None, search_fn=None) -> dict:
    """Catalog-governed agentic researcher.

    llm_fn(messages, tools) -> {"content": str|None, "tool_calls": [{"id","name","arguments"}]} | {"tool_calls": []}
    fetch_fn(url) -> (content_hash, text)
    extract_fn(text, question, hint) -> extract dict   (used only by the deterministic fallback)
    search_fn(query) -> [{"title","url","snippet"}]     (allowlist-filtered web discovery)

    SOURCE_POINTERS is now an OPTIONAL seed: a hypothesis without a curated pointer is
    still researchable — the agent discovers the official primary source via web_search.
    There is no pointer gate.
    """
    pointers = source_pointers if source_pointers is not None else SOURCE_POINTERS
    hid = task_spec.get("hypothesis_id", "")
    question = task_spec.get("question") or hid
    jurisdiction_context = (task_spec.get("jurisdiction_context") or "").strip()
    allowed = set(task_spec.get("allowed_tools", []))
    blocked = set(task_spec.get("blocked_tools", []))
    budget = task_spec.get("budget", {}) or {}
    max_calls = _int_or(budget.get("max_model_calls"), 4)
    max_sources = _int_or(budget.get("max_sources"), 3)
    # Cap discovery searches separately so the agent can't burn its whole turn budget
    # searching and never get to fetch + read + ground.
    max_searches = _int_or(budget.get("max_searches"), 3)
    searches_used = 0

    # Optional curated seed; may be None (then the agent must discover via web_search).
    pointer = pointers.get(hid)
    # The source actually fetched and grounded against — pointer when used, else discovered.
    last_source: dict | None = None

    tools = exposed_tool_schemas(list(allowed))
    user_content = f"Hypothesis {hid}. Question: {question}"
    if jurisdiction_context:
        # Orient the subagent on the resolved controlling authorities (and any
        # UNRESOLVED levels it must not assume). It still must fetch and quote a
        # primary source; this only tells it WHOSE rules apply for this location.
        user_content += (
            "\n\nLocal jurisdiction context (orientation only — still fetch and quote the "
            "primary source):\n" + jurisdiction_context
        )
    messages = [
        {"role": "system", "content": RESEARCH_SKILL_PROMPT},
        {"role": "user", "content": user_content},
    ]

    fetched_text = ""
    content_hash = ""
    sources_used = 0

    for _ in range(max_calls):
        # Offer tools dynamically. Two rules keep the agent on-task:
        #  - A curated seed IS the authoritative source: when this hypothesis has a
        #    pointer, do NOT offer web_search at all — the agent must fetch + extract
        #    from the seed, not wander the web (which regressed mapped hypotheses).
        #    Discovery is strictly the fallback for hypotheses with NO seed.
        #  - Hard-enforce the search cap and source cap by removing the exhausted tool
        #    (a soft error wasn't enough; reasoning models ignore it and burn the budget).
        available = list(allowed)
        if "web_search" in available and (pointer is not None or searches_used >= max_searches):
            available.remove("web_search")
        if "fetch_source" in available and sources_used >= max_sources:
            available.remove("fetch_source")
        tools = exposed_tool_schemas(available)
        resp = llm_fn(messages, tools)
        calls = resp.get("tool_calls") or []
        # Record the assistant turn before any tool results (OpenAI ordering rule).
        messages.append({"role": "assistant", "content": resp.get("content"), "tool_calls": calls})
        if not calls:
            break
        for call in calls:
            name = call.get("name", "")
            args = call.get("arguments", {}) or {}
            call_id = call.get("id", "")

            # Scope enforcement: refuse blocked / non-permitted / non-callable tools, keep going.
            if name in blocked or (name not in allowed) or (name in _NON_CALLABLE):
                messages.append({"role": "tool", "tool_call_id": call_id, "name": name,
                                 "content": json.dumps({"error": f"tool '{name}' is not permitted for this skill"})})
                continue

            if name == "extract_threshold":
                # Cite whatever source was actually fetched and grounded against: the
                # discovered source if the agent searched, else the curated seed.
                source = last_source or pointer
                if source is None:
                    return failed_bundle(hid, "No source was fetched; cannot ground a claim.")
                extract = dict(args)
                quote = (extract.get("verbatim_quote") or "").strip()
                grounded = bool(quote) and _norm_ws(quote) in _norm_ws(fetched_text)
                if quote and not grounded:
                    extract["verbatim_quote"] = ""
                    extract["applies"] = "needs_review"
                extract.setdefault("field", EXTRACTION_HINTS.get(hid, {}).get("field", "source_claim"))
                return assemble_evidence(hid, source, content_hash, now_iso, extract)

            if name == "web_search":
                query = (args.get("query") or "").strip()
                if searches_used >= max_searches:
                    payload = {"error": "max_searches reached — stop searching and fetch_source the most authoritative result you already found"}
                elif not query:
                    payload = {"error": "web_search requires a non-empty query"}
                elif search_fn is None:
                    payload = {"error": "web search is unavailable"}
                else:
                    try:
                        results = search_fn(query) or []
                    except Exception as exc:  # noqa: BLE001 — never throw out of the loop
                        results = []
                        payload = {"error": f"web_search failed: {exc}"}
                    else:
                        searches_used += 1
                        # search_fn returns allowlisted results first, then other official
                        # .gov; surface them so the agent can fetch_source the best one.
                        payload = {"results": results, "searches_left": max_searches - searches_used} if results else {
                            "results": [],
                            "note": "No official source matched; refine the query (rule number, program, authority).",
                            "searches_left": max_searches - searches_used,
                        }
            elif name == "get_source_pointers":
                # A curated seed if one exists; otherwise instruct discovery (no gate).
                payload = ({"url": pointer["url"], "source_name": pointer["source_name"],
                            "authority_rank": pointer["authority_rank"]} if pointer else
                           {"seed": None,
                            "note": "No curated source seed for this hypothesis. Use web_search to "
                                    "find the official primary source on an allowlisted authority, then fetch_source it."})
            elif name == "get_triggers":
                payload = EXTRACTION_HINTS.get(hid, {})
            elif name == "read_skill":
                # The agent's skill_id is a HINT. Models routinely guess non-existent ids
                # (e.g. "SCAQMD.Rule201"), so if the hint misses, fall back to the
                # hypothesis's canonical mapped skill — otherwise curated guidance is
                # never actually loaded and the skill library goes unused.
                requested = (args.get("skill_id") or "").strip()
                mapped = SKILL_FOR_HYPOTHESIS.get(hid, "")
                candidates = [c for c in (requested, mapped) if c]
                if not candidates:
                    payload = {"error": f"no skill mapped for {hid}"}
                elif read_skill_fn is None:
                    payload = {"error": "skill library unavailable"}
                else:
                    loaded, content = "", ""
                    for cand in candidates:
                        try:
                            content = read_skill_fn(cand)
                        except Exception:  # noqa: BLE001 — never throw out of the loop
                            content = ""
                        if content:
                            loaded = cand
                            break
                    payload = ({"skill_id": loaded, "content": content} if content
                               else {"error": f"no skill found for {hid} (tried {candidates})"})
            elif name == "fetch_source":
                if sources_used >= max_sources:
                    payload = {"error": "max_sources budget exceeded"}
                else:
                    # Default to the curated seed url only when one exists; otherwise the
                    # agent must supply a url it discovered via web_search.
                    url = (args.get("url") or "").strip() or (pointer["url"] if pointer else "")
                    if not url:
                        payload = {"error": "no url to fetch; use web_search to find an official source first"}
                    elif not host_credible(url):
                        payload = {"error": f"host not an official source (allowlist or .gov required): {url}"}
                    else:
                        try:
                            content_hash, fetched_text = fetch_fn(url)
                        except Exception as exc:  # noqa: BLE001 — a dead/404 url must not crash the run
                            # Return the error so the agent can recover (search again / try
                            # another result). A failed fetch does NOT consume the source budget.
                            payload = {"error": f"could not fetch {url}: {exc}"}
                        else:
                            sources_used += 1
                            # Record the source actually fetched so extract_threshold cites it.
                            if pointer and url == pointer["url"]:
                                last_source = dict(pointer)
                            else:
                                host = (urlparse(url).hostname or "").lower()
                                # Curated allowlist authority = rank 1; other official .gov = rank 2.
                                last_source = {"url": url, "source_name": host or url,
                                               "authority_rank": 1 if host_allowed(url) else 2}
                            payload = {"content_hash": content_hash, "text": fetched_text}
            elif name == "prove_currency":
                payload = ({"status": "no_source", "detail": "fetch a source first"}
                           if not fetched_text
                           else {"status": "unconfirmed", "detail": "no effective date parsed; currency not independently verified"})
            elif name == "evaluate_predicate":
                payload = {"note": args.get("note", "predicate recorded")}
            else:
                # Chemical-analysis tools (VOC/composition/CAS/aggregate) are
                # computed in tools.py; returns None if not one of those.
                chem = handle_chemical_tool(name, args)
                payload = chem if chem is not None else {"error": f"unknown tool '{name}'"}

            messages.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": json.dumps(payload)})

    # Budget exhausted without the agent submitting a grounded finding -> FAIL
    # CLOSED. We do not run a canned/deterministic extraction to manufacture a
    # result; if the agent could not ground it within budget, it is needs_review.
    return failed_bundle(hid, "Budget exhausted before the agent submitted a grounded finding.")
