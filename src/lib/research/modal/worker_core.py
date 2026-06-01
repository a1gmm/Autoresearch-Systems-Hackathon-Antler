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
    "H-AIR-201": "scaqmd-air", "H-AIR-VOC": "scaqmd-air", "H-AIR-219": "scaqmd-air", "H-AIR-222": "scaqmd-air",
    "H-STORM-IGP": "ca-stormwater", "H-STORM-CGP": "ca-stormwater",
    "H-HAZMAT-HMBP": "ca-hmbp",
    "H-WASTE-GENERATOR": "hazwaste-generator",
    "H-WASTEWATER-PRETREATMENT": "industrial-pretreatment",
}

ALLOWED_HOSTS = {
    "www.aqmd.gov", "aqmd.gov",
    "www.waterboards.ca.gov", "waterboards.ca.gov",
    "calepa.ca.gov", "www.calepa.ca.gov",
    "www.epa.gov", "epa.gov",
}


def host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ALLOWED_HOSTS


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

# The research skill's done-condition (keep in sync with skillRegistry.ts `research`).
RESEARCH_SKILL_PROMPT = (
    "You are a permit-research subagent. Investigate ONE hypothesis. Start by calling "
    "read_skill to orient yourself on the relevant EHS thresholds, exemptions, and which "
    "primary source to fetch — this is orientation only, NEVER citable evidence. Then use "
    "the provided tools to load the official source pointer, fetch the allowlisted source, "
    "and prove currency, then call extract_threshold with the grounded finding. The "
    "verbatim_quote MUST be copied exactly from the fetched source text. If you cannot "
    "ground a finding, call extract_threshold with applies=needs_review and an empty "
    "verbatim_quote. You may only use the tools you are given."
)

# OpenAI function schemas, keyed by catalog tool id. Only researcher tools we actually
# implement appear here; everything else (get_form, build_applicability_matrix, ...) is
# therefore never exposable, and is also hard-refused by the dispatcher.
TOOL_SCHEMAS: dict[str, dict] = {
    "read_skill": {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": "Read the EHS domain skill for this hypothesis (triggers, threshold ranges, exemptions, and which primary source to fetch). Orientation only — never cite the skill as evidence; you must still fetch and quote the primary source.",
            "parameters": {"type": "object", "properties": {"skill_id": {"type": "string"}}},
        },
    },
    "get_source_pointers": {
        "type": "function",
        "function": {
            "name": "get_source_pointers",
            "description": "Return the allowlisted official source URL and authority rank for this hypothesis.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    "get_triggers": {
        "type": "function",
        "function": {
            "name": "get_triggers",
            "description": "Return the threshold/predicate extraction hint for this hypothesis.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    "fetch_source": {
        "type": "function",
        "function": {
            "name": "fetch_source",
            "description": "Fetch an allowlisted source URL and return its content hash and extracted text.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
            },
        },
    },
    "prove_currency": {
        "type": "function",
        "function": {
            "name": "prove_currency",
            "description": "Classify the fetched source as current, stale, or unconfirmed.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    "evaluate_predicate": {
        "type": "function",
        "function": {
            "name": "evaluate_predicate",
            "description": "Record evaluation of the trigger predicate against project attributes.",
            "parameters": {"type": "object", "properties": {"note": {"type": "string"}}},
        },
    },
    "extract_threshold": {
        "type": "function",
        "function": {
            "name": "extract_threshold",
            "description": "Submit the grounded finding. Terminal — ends the investigation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "threshold_value": {"type": ["number", "null"]},
                    "triggering_clause": {"type": "string"},
                    "verbatim_quote": {"type": "string"},
                    "applies": {"type": "string", "enum": ["applies", "does_not_apply", "needs_review"]},
                    "confidence": {"type": "number"},
                },
                "required": ["field", "verbatim_quote", "applies", "confidence"],
            },
        },
    },
    "analyze_voc_content": {
        "type": "function",
        "function": {
            "name": "analyze_voc_content",
            "description": "Compute regulated VOC content in g/L from SDS / product data. Provide the values read off the SDS; the tool does the math and returns g/L and lb/gal so you can compare against a rule threshold. Quote the SDS lines you read the inputs from.",
            "parameters": {
                "type": "object",
                "properties": {
                    "voc_weight_percent": {"type": ["number", "null"], "description": "VOC content as weight % of the product (e.g. 42 for 42%)."},
                    "density_g_per_l": {"type": ["number", "null"], "description": "Product density/specific gravity in g/L (specific gravity * 1000)."},
                    "voc_grams_per_liter": {"type": ["number", "null"], "description": "VOC g/L if the SDS states it directly; if given, returned as-is."},
                    "water_weight_percent": {"type": ["number", "null"], "description": "Water weight % to subtract from the regulated volume basis, if applicable."},
                    "exempt_solvent_weight_percent": {"type": ["number", "null"], "description": "Exempt-solvent weight % to subtract, if applicable."},
                },
            },
        },
    },
    "verify_chemical_composition": {
        "type": "function",
        "function": {
            "name": "verify_chemical_composition",
            "description": "Verify that the constituents a determination relies on actually appear in the SDS Section 3 disclosure. Provide the SDS components (name, CAS, weight range) and the constituents you are claiming; the tool reports which claimed constituents are matched/unmatched by CAS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sds_components": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "cas": {"type": "string"},
                                "weight_percent_min": {"type": ["number", "null"]},
                                "weight_percent_max": {"type": ["number", "null"]},
                            },
                        },
                    },
                    "claimed_cas": {"type": "array", "items": {"type": "string"}, "description": "CAS numbers the determination claims are present."},
                },
                "required": ["sds_components", "claimed_cas"],
            },
        },
    },
    "lookup_cas_hazards": {
        "type": "function",
        "function": {
            "name": "lookup_cas_hazards",
            "description": "Look up which California regulatory lists a CAS number appears on (Prop 65, CARB regulated VOC, SCAQMD toxics). Returns the lists + the citation pointer to fetch and quote. Orientation: you must still fetch and quote the cited list to ground the claim.",
            "parameters": {
                "type": "object",
                "properties": {"cas": {"type": "string"}},
                "required": ["cas"],
            },
        },
    },
    "compute_aggregate_quantity": {
        "type": "function",
        "function": {
            "name": "compute_aggregate_quantity",
            "description": "Sum a hazardous constituent across multiple products/containers to compare against a reporting/permit threshold. Provide per-container amounts in a common unit; the tool returns the total and unit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amounts": {"type": "array", "items": {"type": "number"}, "description": "Per-container amounts in the same unit."},
                    "unit": {"type": "string", "description": "The unit (e.g. gallons, pounds, kg)."},
                },
                "required": ["amounts", "unit"],
            },
        },
    },
}

# California regulatory-list membership by CAS. Orientation pointers only — the
# agent must still fetch and quote the cited primary list to ground a claim.
# Scoped to California (Prop 65 / CARB / SCAQMD), matching the project scope.
CA_CAS_LISTS: dict[str, dict] = {
    # toluene
    "108-88-3": {"lists": ["CA Prop 65 (developmental)", "CARB regulated VOC"],
                  "source": "https://oehha.ca.gov/proposition-65/proposition-65-list"},
    # xylene
    "1330-20-7": {"lists": ["CARB regulated VOC"],
                   "source": "https://ww2.arb.ca.gov/resources/documents/regulated-voc"},
    # methyl ethyl ketone (MEK)
    "78-93-3": {"lists": ["CARB regulated VOC"],
                 "source": "https://ww2.arb.ca.gov/resources/documents/regulated-voc"},
    # ethylene glycol
    "107-21-1": {"lists": ["CA Prop 65 (developmental)"],
                  "source": "https://oehha.ca.gov/proposition-65/proposition-65-list"},
    # formaldehyde
    "50-00-0": {"lists": ["CA Prop 65 (carcinogen)", "SCAQMD toxic air contaminant"],
                 "source": "https://oehha.ca.gov/proposition-65/proposition-65-list"},
}


def _voc_grams_per_liter(args: dict) -> dict:
    """Deterministic VOC math. Either the SDS states g/L directly, or we derive it
    from weight % * density, optionally on a water/exempt-reduced basis."""
    direct = args.get("voc_grams_per_liter")
    if isinstance(direct, (int, float)):
        g_per_l = float(direct)
    else:
        wpct = args.get("voc_weight_percent")
        density = args.get("density_g_per_l")
        if not isinstance(wpct, (int, float)) or not isinstance(density, (int, float)):
            return {"error": "need voc_grams_per_liter, OR both voc_weight_percent and density_g_per_l"}
        g_per_l = (float(wpct) / 100.0) * float(density)
    basis = "total product"
    water = args.get("water_weight_percent") or 0
    exempt = args.get("exempt_solvent_weight_percent") or 0
    reduced = float(water) + float(exempt)
    if reduced > 0:
        basis = f"less water+exempt ({reduced}% of mass) — approximate; confirm regulated basis in the rule"
    return {
        "voc_g_per_l": round(g_per_l, 2),
        "voc_lb_per_gal": round(g_per_l * 0.0083454, 4),
        "basis": basis,
        "note": "Orientation math only. Quote the SDS lines used and the rule's VOC definition; the rule's regulated basis governs.",
    }

# Non-LLM-callable researcher tools (allowed in scope but not offered as model tools):
# get_cached_source (no cache in demo) and quarantine_injection (embedded in fetch_source).
_NON_CALLABLE = {"get_cached_source", "quarantine_injection"}


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _norm_cas(cas: str) -> str:
    """Normalize a CAS number to digits-with-dashes for comparison."""
    return re.sub(r"[^0-9-]", "", str(cas or "")).strip()


def _int_or(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def exposed_tool_schemas(allowed_tools: list[str]) -> list[dict]:
    """The OpenAI tools to offer = allowed_tools that we actually implement as model tools."""
    return [TOOL_SCHEMAS[t] for t in allowed_tools if t in TOOL_SCHEMAS]


def run_research_agent(task_spec: dict, *, llm_fn, fetch_fn, extract_fn, now_iso: str,
                       source_pointers: dict | None = None, read_skill_fn=None) -> dict:
    """Catalog-governed agentic researcher.

    llm_fn(messages, tools) -> {"content": str|None, "tool_calls": [{"id","name","arguments"}]} | {"tool_calls": []}
    fetch_fn(url) -> (content_hash, text)
    extract_fn(text, question, hint) -> extract dict   (used only by the deterministic fallback)
    """
    pointers = source_pointers if source_pointers is not None else SOURCE_POINTERS
    hid = task_spec.get("hypothesis_id", "")
    question = task_spec.get("question") or hid
    allowed = set(task_spec.get("allowed_tools", []))
    blocked = set(task_spec.get("blocked_tools", []))
    budget = task_spec.get("budget", {}) or {}
    max_calls = _int_or(budget.get("max_model_calls"), 4)
    max_sources = _int_or(budget.get("max_sources"), 3)

    pointer = pointers.get(hid)
    if pointer is None:
        return failed_bundle(hid, f"No source pointer for {hid}")

    tools = exposed_tool_schemas(list(allowed))
    messages = [
        {"role": "system", "content": RESEARCH_SKILL_PROMPT},
        {"role": "user", "content": f"Hypothesis {hid}. Question: {question}"},
    ]

    fetched_text = ""
    content_hash = ""
    sources_used = 0

    for _ in range(max_calls):
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
                extract = dict(args)
                quote = (extract.get("verbatim_quote") or "").strip()
                grounded = bool(quote) and _norm_ws(quote) in _norm_ws(fetched_text)
                if quote and not grounded:
                    extract["verbatim_quote"] = ""
                    extract["applies"] = "needs_review"
                extract.setdefault("field", EXTRACTION_HINTS.get(hid, {}).get("field", "source_claim"))
                return assemble_evidence(hid, pointer, content_hash, now_iso, extract)

            if name == "get_source_pointers":
                payload = {"url": pointer["url"], "source_name": pointer["source_name"],
                           "authority_rank": pointer["authority_rank"]}
            elif name == "get_triggers":
                payload = EXTRACTION_HINTS.get(hid, {})
            elif name == "read_skill":
                requested = (args.get("skill_id") or "").strip() or SKILL_FOR_HYPOTHESIS.get(hid, "")
                if not requested:
                    payload = {"error": f"no skill mapped for {hid}"}
                elif read_skill_fn is None:
                    payload = {"error": "skill library unavailable"}
                else:
                    try:
                        content = read_skill_fn(requested)
                    except Exception:  # noqa: BLE001 — never throw out of the loop
                        content = ""
                    payload = ({"skill_id": requested, "content": content} if content
                               else {"error": f"skill '{requested}' not found"})
            elif name == "fetch_source":
                if sources_used >= max_sources:
                    payload = {"error": "max_sources budget exceeded"}
                else:
                    url = (args.get("url") or "").strip() or pointer["url"]
                    if not host_allowed(url):
                        payload = {"error": f"host not allowlisted: {url}"}
                    else:
                        content_hash, fetched_text = fetch_fn(url)
                        sources_used += 1
                        payload = {"content_hash": content_hash, "text": fetched_text}
            elif name == "prove_currency":
                payload = ({"status": "no_source", "detail": "fetch a source first"}
                           if not fetched_text
                           else {"status": "unconfirmed", "detail": "no effective date parsed; currency not independently verified"})
            elif name == "evaluate_predicate":
                payload = {"note": args.get("note", "predicate recorded")}
            elif name == "analyze_voc_content":
                payload = _voc_grams_per_liter(args)
            elif name == "verify_chemical_composition":
                claimed = {_norm_cas(c) for c in (args.get("claimed_cas") or [])}
                comps = args.get("sds_components") or []
                by_cas = {_norm_cas(c.get("cas", "")): c for c in comps if c.get("cas")}
                matched = sorted(c for c in claimed if c in by_cas)
                unmatched = sorted(c for c in claimed if c not in by_cas)
                payload = {
                    "matched": [{"cas": c, "component": by_cas[c]} for c in matched],
                    "unmatched_claimed_cas": unmatched,
                    "all_verified": len(unmatched) == 0,
                    "note": "A claimed constituent not found in SDS Section 3 must not be relied on; fail closed.",
                }
            elif name == "lookup_cas_hazards":
                cas = _norm_cas(args.get("cas", ""))
                hit = CA_CAS_LISTS.get(cas)
                payload = ({"cas": cas, "lists": hit["lists"], "source": hit["source"],
                            "note": "Orientation only — fetch and quote the cited list to ground the claim."}
                           if hit else
                           {"cas": cas, "lists": [], "note": "Not in the CA orientation list; fetch the authoritative list to confirm presence/absence."})
            elif name == "compute_aggregate_quantity":
                amounts = [float(a) for a in (args.get("amounts") or []) if isinstance(a, (int, float))]
                payload = {"total": round(sum(amounts), 4), "unit": args.get("unit", ""), "count": len(amounts)}
            else:
                payload = {"error": f"unknown tool '{name}'"}

            messages.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": json.dumps(payload)})

    # Budget exhausted without a grounded submit -> deterministic fetch+extract fallback.
    return _deterministic_fallback(hid, pointer, question, fetch_fn, extract_fn, now_iso, fetched_text, content_hash)


def _deterministic_fallback(hid, pointer, question, fetch_fn, extract_fn, now_iso, fetched_text, content_hash) -> dict:
    if not fetched_text:
        try:
            content_hash, fetched_text = fetch_fn(pointer["url"])
        except Exception as exc:  # noqa: BLE001
            return failed_bundle(hid, f"Fallback fetch failed: {exc}")
    if extract_fn is None:
        return failed_bundle(hid, "Budget exhausted with no grounded finding.")
    extract = extract_fn(fetched_text, question, EXTRACTION_HINTS.get(hid, {}))
    quote = (extract.get("verbatim_quote") or "").strip()
    if quote and _norm_ws(quote) not in _norm_ws(fetched_text):
        extract["verbatim_quote"] = ""
        extract["applies"] = "needs_review"
    return assemble_evidence(hid, pointer, content_hash, now_iso, extract)
