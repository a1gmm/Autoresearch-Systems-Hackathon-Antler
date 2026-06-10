"""PermitPilot research CLI — run the production research engine from the terminal.

Same pipeline the web app uses (run_research_sync), rendered as an ASCII report so you can
test real determinations without the Next.js UI, Modal, or polling.

    PYTHONPATH=src python -m research_core.cli "UV inkjet printing operation in Oxnard" \
        --county Ventura --city Oxnard --sds /tmp/cayi-e2e/cayi/sds/*.pdf

    # fast, free, deterministic smoke run (no LLM calls):
    PYTHONPATH=src python -m research_core.cli "coating shop, 200 gal solvent" --mode fake

Flags: --county/--city, --naics, --quantity (chemicals.quantity), --sds <paths>,
--mode live|fake (default live), --model <id>, --trace, --json, --no-color.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from research_core.orchestrator import run_research_sync
from research_core.store import LocalRunStore


# --- terminal styling ---------------------------------------------------------

class _Style:
    def __init__(self, enabled: bool) -> None:
        self.on = enabled

    def _w(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.on else text

    def bold(self, t): return self._w("1", t)
    def dim(self, t): return self._w("2", t)
    def green(self, t): return self._w("32", t)
    def yellow(self, t): return self._w("33", t)
    def red(self, t): return self._w("31", t)
    def cyan(self, t): return self._w("36", t)
    def grey(self, t): return self._w("90", t)


# verdict / status → (symbol, color-fn-name)
def _status_badge(s: _Style, status: str) -> str:
    status = (status or "").lower()
    table = {
        "pass": ("✓", s.green), "verified": ("✓", s.green), "done": ("✓", s.green),
        "active": ("●", s.cyan),
        "needs_review": ("⚠", s.yellow), "needs_information": ("⚠", s.yellow),
        "blocked_missing_fact": ("▲", s.yellow), "queued": ("…", s.grey),
        "fail": ("✗", s.red), "failed": ("✗", s.red),
        "out_of_scope": ("·", s.grey),
    }
    sym, color = table.get(status, ("•", s.grey))
    return color(f"{sym} {status}")


def _rule(s: _Style, label: str = "", width: int = 78) -> str:
    if not label:
        return s.grey("─" * width)
    bar = "─" * max(0, width - len(label) - 3)
    return s.grey("── ") + s.bold(label) + " " + s.grey(bar)


# --- input assembly -----------------------------------------------------------

def _load_env_local() -> None:
    for parent in [Path.cwd(), *Path(__file__).resolve().parents]:
        env = parent / ".env.local"
        if not env.is_file():
            continue
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        return


def _sds_documents(paths: list[str]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    try:
        import fitz
    except ImportError:
        print("  (PyMuPDF not installed — skipping SDS extraction)", file=sys.stderr)
        return docs
    for raw in paths:
        p = Path(raw)
        if not p.is_file():
            continue
        try:
            with fitz.open(p) as doc:
                text = "\n".join(page.get_text("text") for page in doc)
            docs.append({"name": p.name, "type": "sds", "text": text})
        except Exception as exc:  # noqa: BLE001
            print(f"  (could not read {p.name}: {exc})", file=sys.stderr)
    return docs


def _build_input(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {"project_description": args.description}
    facility: dict[str, Any] = {}
    if args.county:
        facility["county"] = args.county
    if args.city:
        facility["city"] = args.city
    if args.naics:
        facility["naics"] = args.naics
    if facility:
        payload["facility"] = facility
    if args.quantity:
        payload.setdefault("provided_estimates", {})["chemicals.quantity"] = args.quantity
    if args.sds:
        payload["demo_documents"] = _sds_documents(args.sds)
    return payload


# --- rendering ----------------------------------------------------------------

def _hypothesis_family_map() -> dict[str, str]:
    from research_core.registry import PROGRAM_REGISTRY

    out: dict[str, str] = {}
    for program in PROGRAM_REGISTRY:
        for hyp in program.hypotheses:
            out[hyp.id] = program.family
    return out


def render(result: dict[str, Any], style: _Style, show_trace: bool) -> None:
    s = style
    res = result.get("result") or {}
    status = result.get("status", "?")
    run_id = result.get("run_id", "?")

    print()
    print(_rule(s, "PermitPilot research"))
    print(f"  run {s.dim(run_id)}    status {_status_badge(s, status)}")
    summary = (res.get("report") or {}).get("summary")
    if summary:
        print(f"  {summary}")

    # Coverage families
    coverage = (res.get("report") or {}).get("coverage") or []
    if coverage:
        print()
        print(_rule(s, "Coverage families"))
        for cf in coverage:
            fam = (cf.get("family") or "?").replace("_", " ").title()
            print(f"  {fam:<14} {_status_badge(s, cf.get('status',''))}")
            reason = cf.get("reason")
            if reason:
                print(f"  {'':<14} {s.grey(reason)}")

    # Determinations grouped by family (from verdicts)
    verdicts = result.get("verdicts") or []
    if verdicts:
        fam_of = _hypothesis_family_map()
        by_family: dict[str, list[dict[str, Any]]] = {}
        for v in verdicts:
            fam = fam_of.get(v.get("hypothesis_id", ""), "other")
            by_family.setdefault(fam, []).append(v)
        print()
        print(_rule(s, f"Determinations ({len(verdicts)} hypotheses)"))
        for fam in sorted(by_family):
            print(f"  {s.bold(fam.replace('_',' ').title())}")
            for v in by_family[fam]:
                conf = v.get("confidence")
                conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "—"
                print(f"    {_status_badge(s, v.get('verdict','')):<22} "
                      f"{s.dim(v.get('hypothesis_id','')):<24} conf {conf_s}")

    # Missing facts
    reqs = result.get("information_requests") or []
    if reqs:
        print()
        print(_rule(s, f"Missing facts ({len(reqs)})"))
        for r in reqs:
            print(f"  {s.yellow('?')} {r.get('question') or r.get('field')}")
            if r.get("why_needed"):
                print(f"    {s.grey(r['why_needed'])}")
            if r.get("blocks"):
                print(f"    {s.grey('blocks: ' + ', '.join(r['blocks']))}")

    # Scenarios
    scenarios = result.get("scenarios") or []
    if scenarios:
        print()
        print(_rule(s, f"Scenarios ({len(scenarios)})"))
        for sc in scenarios:
            print(f"  {s.cyan(sc.get('label','?'))}: {', '.join(sc.get('affects', []))}")

    # Findings (evidence) — show titles + confidence + first source
    evidence = result.get("evidence") or []
    if evidence:
        print()
        print(_rule(s, f"Findings ({len(evidence)})"))
        for ev in evidence[:25]:
            hid = ev.get("hypothesis_id", "?")
            claims = ev.get("extracted_claims") or []
            concl = ev.get("researcher_conclusion", "")
            srcs = ev.get("sources") or []
            src0 = (srcs[0].get("url") if isinstance(srcs[0], dict) else srcs[0]) if srcs else ""
            print(f"  {s.dim(hid):<24} {concl}")
            if src0:
                print(f"    {s.grey(str(src0)[:90])}")

    # Trace timeline
    if show_trace:
        events = result.get("trace_events") or []
        print()
        print(_rule(s, f"Trace ({len(events)} events)"))
        for e in events:
            scope = e.get("scope", "")
            payload = e.get("payload") or {}
            extra = payload.get("hypothesis_id") or payload.get("status") or payload.get("task_id") or ""
            print(f"  {s.grey('•')} {scope:<22} {s.dim(str(extra))}")

    print()
    print(_rule(s))
    print(f"  Final: {_status_badge(s, status)}   "
          f"{s.dim(f'{len(verdicts)} hypotheses · {len(evidence)} findings · {len(reqs)} missing facts')}")
    print()


# --- main ---------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="research_core.cli", description="Run PermitPilot research from the terminal.")
    parser.add_argument("description", help="the project change to research (free text)")
    parser.add_argument("--county", help="facility county (resolves air district + CUPA)")
    parser.add_argument("--city", help="facility city")
    parser.add_argument("--naics", help="facility NAICS code")
    parser.add_argument("--quantity", help="chemicals.quantity answer, e.g. '200 gal'")
    parser.add_argument("--sds", nargs="*", default=[], help="SDS PDF paths to attach as provided documents")
    parser.add_argument("--mode", choices=["live", "fake", "offline"], default="live",
                        help="live = real agents (default); fake = instant deterministic smoke run")
    parser.add_argument("--model", help="worker model id (sets RESEARCH_CORE_AGENT_MODEL)")
    parser.add_argument("--trace", action="store_true", help="show the trace event timeline")
    parser.add_argument("--json", action="store_true", help="print raw JSON result instead of the report")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI color")
    args = parser.parse_args(argv)

    _load_env_local()
    if args.model:
        os.environ["RESEARCH_CORE_AGENT_MODEL"] = args.model
    if args.mode == "live" and not os.environ.get("OPENAI_API_KEY"):
        print("error: live mode needs OPENAI_API_KEY (in env or .env.local). Use --mode fake for a free smoke run.",
              file=sys.stderr)
        return 2

    style = _Style(enabled=(not args.no_color) and sys.stdout.isatty())
    payload = _build_input(args)

    if args.mode == "live":
        print(style.dim(f"Running live research ({os.environ.get('RESEARCH_CORE_AGENT_MODEL', 'default')} worker) — "
                        "this is real, give it a few minutes…"), file=sys.stderr)
    try:
        result = run_research_sync(payload, deps=args.mode, store=LocalRunStore()).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        print(style.red(f"run failed: {exc}"), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        render(result, style, show_trace=args.trace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
