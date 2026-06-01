"""Tool definitions for the PermitPilot research agent.

Separate from the agent loop (worker_core.py): this module owns the OpenAI tool
schemas, the chemical-analysis tool handlers, and their reference data. The loop
imports TOOL_SCHEMAS and handle_chemical_tool from here.
"""
from __future__ import annotations

import re

# OpenAI function schemas, keyed by catalog tool id. Only researcher tools we
# actually implement appear here; anything else is never exposable and is
# hard-refused by the dispatcher in worker_core.
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
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}},
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
            "parameters": {"type": "object", "properties": {"cas": {"type": "string"}}, "required": ["cas"]},
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
    "108-88-3": {"lists": ["CA Prop 65 (developmental)", "CARB regulated VOC"], "source": "https://oehha.ca.gov/proposition-65/proposition-65-list"},   # toluene
    "1330-20-7": {"lists": ["CARB regulated VOC"], "source": "https://ww2.arb.ca.gov/resources/documents/regulated-voc"},                                # xylene
    "78-93-3": {"lists": ["CARB regulated VOC"], "source": "https://ww2.arb.ca.gov/resources/documents/regulated-voc"},                                  # MEK
    "107-21-1": {"lists": ["CA Prop 65 (developmental)"], "source": "https://oehha.ca.gov/proposition-65/proposition-65-list"},                          # ethylene glycol
    "50-00-0": {"lists": ["CA Prop 65 (carcinogen)", "SCAQMD toxic air contaminant"], "source": "https://oehha.ca.gov/proposition-65/proposition-65-list"},  # formaldehyde
}

# Chemical-analysis tools are computed locally (not LLM-callable IO). The loop
# routes a tool call here; returns None for tools this module does not own.
CHEMICAL_TOOLS = {"analyze_voc_content", "verify_chemical_composition", "lookup_cas_hazards", "compute_aggregate_quantity"}


def norm_cas(cas: str) -> str:
    """Normalize a CAS number to digits-with-dashes for comparison."""
    return re.sub(r"[^0-9-]", "", str(cas or "")).strip()


def voc_grams_per_liter(args: dict) -> dict:
    """VOC math. Either the SDS states g/L directly, or derive it from
    weight % * density. Errors (never guesses) on insufficient inputs."""
    direct = args.get("voc_grams_per_liter")
    if isinstance(direct, (int, float)):
        g_per_l = float(direct)
    else:
        wpct = args.get("voc_weight_percent")
        density = args.get("density_g_per_l")
        if not isinstance(wpct, (int, float)) or not isinstance(density, (int, float)):
            return {"error": "need voc_grams_per_liter, OR both voc_weight_percent and density_g_per_l"}
        g_per_l = (float(wpct) / 100.0) * float(density)
    water = float(args.get("water_weight_percent") or 0)
    exempt = float(args.get("exempt_solvent_weight_percent") or 0)
    reduced = water + exempt
    basis = (f"less water+exempt ({reduced}% of mass) — approximate; confirm regulated basis in the rule"
             if reduced > 0 else "total product")
    return {
        "voc_g_per_l": round(g_per_l, 2),
        "voc_lb_per_gal": round(g_per_l * 0.0083454, 4),
        "basis": basis,
        "note": "Orientation math only. Quote the SDS lines used and the rule's VOC definition; the rule's regulated basis governs.",
    }


def handle_chemical_tool(name: str, args: dict) -> dict | None:
    """Dispatch a chemical-analysis tool call. Returns the tool payload, or None
    if `name` is not a chemical tool this module owns."""
    if name == "analyze_voc_content":
        return voc_grams_per_liter(args)
    if name == "verify_chemical_composition":
        claimed = {norm_cas(c) for c in (args.get("claimed_cas") or [])}
        by_cas = {norm_cas(c.get("cas", "")): c for c in (args.get("sds_components") or []) if c.get("cas")}
        matched = sorted(c for c in claimed if c in by_cas)
        unmatched = sorted(c for c in claimed if c not in by_cas)
        return {
            "matched": [{"cas": c, "component": by_cas[c]} for c in matched],
            "unmatched_claimed_cas": unmatched,
            "all_verified": len(unmatched) == 0,
            "note": "A claimed constituent not found in SDS Section 3 must not be relied on; fail closed.",
        }
    if name == "lookup_cas_hazards":
        cas = norm_cas(args.get("cas", ""))
        hit = CA_CAS_LISTS.get(cas)
        if hit:
            return {"cas": cas, "lists": hit["lists"], "source": hit["source"],
                    "note": "Orientation only — fetch and quote the cited list to ground the claim."}
        return {"cas": cas, "lists": [],
                "note": "Not in the CA orientation list; fetch the authoritative list to confirm presence/absence."}
    if name == "compute_aggregate_quantity":
        amounts = [float(a) for a in (args.get("amounts") or []) if isinstance(a, (int, float))]
        return {"total": round(sum(amounts), 4), "unit": args.get("unit", ""), "count": len(amounts)}
    return None
