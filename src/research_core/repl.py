"""PermitPilot interactive CLI — a Claude-Code-style REPL for EHS permit research.

Launch a session, describe a facility/project in plain English, and watch the research run
with live streaming progress (phase, hypotheses verified, elapsed), then read the report.
Carry facts across turns and refine with slash commands. Same engine as the web app
(run_research_sync), no Next.js / Modal.

    PYTHONPATH=src python -m research_core.repl            # live agents (key from .env.local)
    PYTHONPATH=src python -m research_core.repl --mode fake # instant deterministic smoke

In the session:
    just type a project        run research with the facts collected so far
    /county Ventura            set a fact (also /city /naics /quantity)
    /sds a.pdf b.pdf           attach SDS PDFs
    /mode live|fake  /model X  switch engine / worker model
    /show  /trace  /reset      inspect scope / toggle trace / clear
    /help  /quit
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Any

from research_core.cli import _Style, _load_env_local, _sds_documents, _status_badge, render
from research_core.orchestrator import run_research_sync
from research_core.store import LocalRunStore


_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Session:
    """Conversation state carried across turns."""

    def __init__(self, mode: str, model: str | None) -> None:
        self.facility: dict[str, Any] = {}
        self.provided_estimates: dict[str, Any] = {}
        self.documents: list[dict[str, Any]] = []
        self.mode = mode
        self.model = model
        self.show_trace = False

    def payload(self, description: str) -> dict[str, Any]:
        out: dict[str, Any] = {"project_description": description}
        if self.facility:
            out["facility"] = dict(self.facility)
        if self.provided_estimates:
            out["provided_estimates"] = dict(self.provided_estimates)
        if self.documents:
            out["demo_documents"] = list(self.documents)
        return out

    def summary(self) -> str:
        parts = []
        if self.facility:
            parts.append("facility " + ", ".join(f"{k}={v}" for k, v in self.facility.items()))
        if self.provided_estimates:
            parts.append("facts " + ", ".join(f"{k}={v}" for k, v in self.provided_estimates.items()))
        if self.documents:
            parts.append(f"{len(self.documents)} document(s)")
        parts.append(f"mode={self.mode}")
        if self.model:
            parts.append(f"model={self.model}")
        return " · ".join(parts)


def run_with_progress(payload: dict[str, Any], mode: str, style: _Style) -> dict[str, Any] | None:
    """Run the research on a background thread and stream live progress from the store
    (status phase, evidence/verdicts as they accumulate) until it finishes."""
    store = LocalRunStore()
    record = store.create_run(payload)
    run_id = str(record["run_id"])
    out: dict[str, Any] = {}

    def _bg() -> None:
        try:
            out["result"] = run_research_sync(payload, deps=mode, store=store, run_id=run_id).model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            out["error"] = exc

    thread = threading.Thread(target=_bg, name="research", daemon=True)
    thread.start()

    start = time.monotonic()
    frame = 0
    interactive = sys.stdout.isatty()
    while thread.is_alive():
        rec = store.get_run(run_id) or {}
        status = rec.get("status", "queued")
        researched = len(rec.get("evidence") or [])
        verified = len(rec.get("verdicts") or [])
        elapsed = time.monotonic() - start
        clock = f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}"
        line = (f"  {_SPINNER[frame % len(_SPINNER)]} {style.cyan(status):<22} "
                f"{researched} researched · {verified} verified  {style.dim(clock)}")
        if interactive:
            sys.stdout.write("\r\033[K" + line)
            sys.stdout.flush()
        frame += 1
        time.sleep(0.15)
    thread.join()
    if interactive:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    if "error" in out:
        print(style.red(f"  run failed: {out['error']}"))
        return None
    return out.get("result")


def _handle_command(line: str, session: Session, style: _Style) -> bool:
    """Process a /slash command. Returns False to quit, True to continue."""
    parts = line.split()
    cmd, rest = parts[0].lower(), " ".join(parts[1:]).strip()
    if cmd in {"/quit", "/exit", "/q"}:
        return False
    if cmd == "/help":
        print(__doc__.split("In the session:")[1])
        return True
    if cmd in {"/county", "/city", "/naics"}:
        session.facility[cmd[1:]] = rest
        print(style.dim(f"  set {cmd[1:]} = {rest}"))
    elif cmd == "/quantity":
        session.provided_estimates["chemicals.quantity"] = rest
        print(style.dim(f"  set chemicals.quantity = {rest}"))
    elif cmd == "/sds":
        docs = _sds_documents(rest.split())
        session.documents.extend(docs)
        print(style.dim(f"  attached {len(docs)} document(s) ({len(session.documents)} total)"))
    elif cmd == "/mode":
        if rest in {"live", "fake", "offline"}:
            session.mode = rest
            print(style.dim(f"  mode = {rest}"))
        else:
            print(style.red("  usage: /mode live|fake"))
    elif cmd == "/model":
        session.model = rest or None
        import os
        if rest:
            os.environ["RESEARCH_CORE_AGENT_MODEL"] = rest
        print(style.dim(f"  model = {rest or 'default'}"))
    elif cmd == "/trace":
        session.show_trace = not session.show_trace
        print(style.dim(f"  trace = {'on' if session.show_trace else 'off'}"))
    elif cmd == "/show":
        print(style.dim("  " + (session.summary() or "no facts set yet")))
    elif cmd == "/reset":
        session.facility.clear()
        session.provided_estimates.clear()
        session.documents.clear()
        print(style.dim("  scope cleared"))
    else:
        print(style.red(f"  unknown command {cmd} — try /help"))
    return True


def _offer_missing_facts(result: dict[str, Any], session: Session, style: _Style) -> None:
    """If the run needs information, walk the user through providing it (Claude-Code style)."""
    reqs = result.get("information_requests") or []
    if result.get("status") != "needs_information" or not reqs:
        return
    print(style.yellow("  This run needs a few facts. Answer to refine (blank to skip):"))
    for req in reqs:
        field = req.get("field", "")
        q = req.get("question") or field
        try:
            ans = input(f"    {q}\n    {style.dim(field)} ▸ ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not ans:
            continue
        key = field.lower()
        if "county" in key or "jurisdiction" in key or "location" in key:
            session.facility["county"] = ans
        elif key.startswith("chemicals") or "quantity" in key:
            session.provided_estimates[field] = ans
        else:
            session.provided_estimates[field] = ans
    print(style.dim("  facts captured — type your project again (or press Enter) to re-run."))


def repl(mode: str = "live", model: str | None = None) -> int:
    _load_env_local()
    import os
    if model:
        os.environ["RESEARCH_CORE_AGENT_MODEL"] = model
    style = _Style(enabled=sys.stdout.isatty())
    session = Session(mode=mode, model=model)
    last_description = ""

    print()
    print(style.cyan("  ┌─ PermitPilot ───────────────────────────────┐"))
    print(style.cyan("  │ ") + style.bold("EHS permit research") + style.cyan("                         │"))
    print(style.cyan("  └─────────────────────────────────────────────┘"))
    print(style.dim("  Describe a facility/project, or /help. " + session.summary()))
    print()

    while True:
        try:
            line = input(style.cyan("permitpilot ▸ ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line and not last_description:
            continue
        if line.startswith("/"):
            if not _handle_command(line, session, style):
                return 0
            continue

        description = line or last_description
        last_description = description
        if session.mode == "live" and not os.environ.get("OPENAI_API_KEY"):
            print(style.red("  live mode needs OPENAI_API_KEY (in env or .env.local) — try /mode fake"))
            continue
        if session.mode == "live":
            print(style.dim(f"  running live research ({os.environ.get('RESEARCH_CORE_AGENT_MODEL','default')} worker)…"))

        result = run_with_progress(session.payload(description), session.mode, style)
        if result is None:
            continue
        render(result, style, show_trace=session.show_trace)
        _offer_missing_facts(result, session, style)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="research_core.repl", description="Interactive PermitPilot research session.")
    parser.add_argument("--mode", choices=["live", "fake", "offline"], default="live")
    parser.add_argument("--model", default=None)
    args = parser.parse_args(argv)
    return repl(mode=args.mode, model=args.model)


if __name__ == "__main__":
    raise SystemExit(main())
