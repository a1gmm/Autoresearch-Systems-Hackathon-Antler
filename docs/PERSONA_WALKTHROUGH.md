# Persona walkthrough — manually test PermitPilot (production-core branch)

A hands-on script you run yourself against the live app. This branch
(`feat/real-verifier-moat`) runs the **production core**: one real research
path, ID-agnostic mechanical verifier, 0.9 confidence gate, real SDS→synthesis.

## Before you start

- Dev server: **http://localhost:3002** (this worktree).
- Two things to know about this branch:
  1. **Research fails closed without a live backend.** Scope/intake run live on
     `OPENAI_API_KEY`, but the research workers need `MODAL_RESEARCH_ENDPOINT` +
     `MODAL_RESEARCH_TOKEN`. Without them, every hypothesis comes back
     **needs_review** (by design — no canned "applies" anymore). You'll still see
     the full pipeline: scope → plan → coverage families → determinations, all
     honestly marked needs_review.
  2. **SDS upload is not wired into the UI yet** (`SdsDocumentPicker` exists but
     isn't mounted; `InputPanel` sends `demo_documents: []`). To test the
     SDS→synthesis path, use the API recipe in Persona D below.

---

## Persona A — New manufacturer (UI, one click)

**Who:** A SoCal manufacturer adding a coating booth + storing flammable solvent.

1. Open http://localhost:3002
2. Click the **"Complex SoCal Manufacturing"** scenario button.
3. Watch: the agent workstation should show scope parsing → coverage families
   (air, hazmat, stormwater, waste, wastewater) → research tasks fan out.
4. **What to look for:**
   - An **Applicability Matrix** appears with one row per hypothesis.
   - Each row shows `applies` + `verified` + a confidence %.
   - Without a live Modal backend: rows read **needs_review** (honest fail-closed),
     NOT a fabricated "yes". That is the production behavior working.
   - The trace stream should show a `research_pool / fanout` event saying
     **"Live research unavailable — failing closed to needs_review"** if no backend.

**Pass criteria:** no row claims `verified: yes` without a real source + quote. A
needs_review-everywhere result with no backend is CORRECT, not a bug.

---

## Persona B — Simple construction (UI, dynamism check)

**Who:** A construction project disturbing 1.2 acres, no chemicals.

1. Click **"Simple Construction (1.2 acres)"**.
2. **What to look for:** FEWER research tasks than Persona A — hazmat/air should
   be out of scope (no chemicals, no equipment), stormwater active (acreage).
3. **Pass criteria:** the hypothesis set is *smaller and different* than Persona A.
   This proves the plan is fact-driven, not a fixed list.

---

## Persona C — Missing facts (UI, fail-closed check)

**Who:** A project that omits key facts.

1. Click **"Missing Facts"**.
2. **What to look for:** families that depend on the missing facts come back
   **blocked_missing_fact** / **needs_review**, with a "Missing Facts" card listing
   what's needed.
3. **Pass criteria:** the system never guesses past a missing fact — it flags for
   human review. This is the core "fail closed" promise.

---

## Persona D — Real SDS → synthesis (API recipe)

**Who:** A printer adding a UV-curable inkjet line; you attach a real SDS.

Since SDS upload isn't in the UI yet, run this from a terminal. It feeds a REAL
IHOPE inkjet-ink SDS into the pipeline and shows the SDS facts reaching synthesis.

```bash
cd /Users/mac/Documents/antler-moat

# Extract one real SDS to text, then POST a run with it attached.
SDS=$(pdftotext "/Users/mac/Downloads/08_Internships/CAYI/inkjet sds/IHOPE INKJET INK JHV-09 BLACK (CGHS-EN).pdf" - 2>/dev/null)

python3 - "$SDS" <<'PY'
import json, sys, urllib.request
sds = sys.argv[1]
body = json.dumps({
  "project_description": "A Los Angeles County printer adds a UV-curable inkjet line and stores UV ink.",
  "demo_documents": [{"name": "IHOPE JHV-09 Black SDS", "type": "sds", "text": sds}],
}).encode()
req = urllib.request.Request("http://localhost:3002/api/research/run",
                             data=body, headers={"content-type": "application/json"})
run = json.load(urllib.request.urlopen(req, timeout=180))
print("status:", run["status"])
print("sds_reviews:", len(run.get("sds_reviews") or []))
facts = [f["field"] for r in (run.get("sds_reviews") or []) for f in r["permit_handoff_facts"]]
print("SDS handoff facts:", facts)
refs = [f["field"] for d in run["determinations"] for f in (d.get("sds_handoff_refs") or [])]
print("SDS refs that reached determinations:", refs)
PY
```

**What to look for:**
- `sds_reviews: 1` — the SDS was reviewed.
- `SDS handoff facts:` lists real findings from the document (e.g.
  `voc_air_emissions_review`, `hazardous_material_inventory_review`,
  `hazardous_waste_review`) — extracted from the REAL ink SDS, not canned.
- `SDS refs that reached determinations:` is non-empty — proving the SDS shaped
  the synthesis (the bug you originally reported is fixed).

**Pass criteria:** the SDS's flagged facts appear as `sds_handoff_refs` on
determinations. If `sds_reviews: 1` but refs is empty, that's the original bug
(it should NOT happen on this branch).

---

## Persona E — Your own facility (UI, free text)

1. Type your own scenario in the textarea, e.g.:
   *"A Vernon textile facility adds a UV inkjet printer, stores 40 gallons of ink
   and 10 gallons of cleaning solvent, generates spent-solvent waste."*
2. Click **Run**.
3. **What to look for:** scope should extract your equipment, chemicals (with
   quantities), and waste; the plan should activate hazmat + waste + air.

**Pass criteria:** the scope reflects YOUR facts (live LLM extraction), and the
matrix is built from them — nothing hardcoded to a demo.

---

## What "good" looks like overall

- Every `verified: yes` row has a real source URL + verbatim quote and confidence ≥ 0.9.
- Missing facts and unreachable sources → needs_review, never a guessed answer.
- A different input produces a different hypothesis set (fact-driven plan).
- A real SDS changes the determinations it's relevant to.

If you see a confident "yes" with no source, or identical results regardless of
input, that's a regression — tell me and I'll investigate.
