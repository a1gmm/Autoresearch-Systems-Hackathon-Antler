"""Modal worker — catalog-governed agentic researcher behind an HTTP endpoint.

The agentic loop + guardrails live in worker_core.run_research_agent (unit-tested
without modal/openai). This module supplies the real llm/fetch/extract functions
and a token-authed FastAPI endpoint. ALL-REASONING: uses a reasoning-tier model for
both the loop and extraction (max_completion_tokens, no temperature, tool_choice=required).

Deploy:  modal deploy src/lib/research/modal/worker.py
Secrets: `permitpilot-openai` (OPENAI_API_KEY), `permitpilot-research` (RESEARCH_TOKEN)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import modal

from agents_runtime import run_review, run_worker_draft, run_worker_repair
from orchestrator_runtime import run_task_with_review
from rulebook import build_rulebook
from runtime_models import RuntimeTask
from synthesis_runtime import evidence_bundle_from_review, synthesize_runtime_artifacts
from trace_events import trace_event
from worker_core import (
    EXTRACTION_HINTS,
    SOURCE_POINTERS,
    evidence_row,
    failed_bundle,
    run_research_agent,
)

app = modal.App("permitpilot-research")

image = (
    modal.Image.debian_slim()
    .pip_install("httpx", "pymupdf", "beautifulsoup4", "openai", "fastapi[standard]", "supabase", "openai-agents")
    .add_local_dir("src/lib/research/skills", remote_path="/root/skills")
    .add_local_python_source("worker_core")
    .add_local_python_source("prompts")
    .add_local_python_source("tools")
    .add_local_python_source("agents_runtime")
    .add_local_python_source("orchestrator_runtime")
    .add_local_python_source("rulebook")
    .add_local_python_source("runtime_models")
    .add_local_python_source("synthesis_runtime")
    .add_local_python_source("trace_events")
    .add_local_python_source("workspace_core")
)

MAX_BYTES = 5_000_000
MAX_TEXT_CHARS = 24_000
HTTP_TIMEOUT_S = 15.0

EXTRACT_SYSTEM = (
    "You are an EHS regulatory research assistant. Extract ONLY what the text actually "
    "says. The verbatim_quote MUST be copied exactly from the source text. If the text "
    "does not support a finding, set applies to needs_review and leave verbatim_quote empty."
)


def _model() -> str:
    # All-reasoning worker: default to a reasoning-tier model; operator overrides via env
    # with a reasoning model their OpenAI account has access to.
    return os.environ.get("OPENAI_RESEARCH_MODEL", "o4-mini")


# EHS skill files are bundled into the image at /root/skills/<id>/SKILL.md
# (see image .add_local_dir above). Overridable for local runs via SKILLS_DIR.
SKILLS_DIR = os.environ.get("SKILLS_DIR", "/root/skills")
_SKILL_ID_RE = re.compile(r"^[a-z0-9-]+$")


def _read_skill_fn(skill_id: str) -> str:
    """Read a bundled EHS SKILL.md by id. Slug-validated to prevent path traversal."""
    if not skill_id or not _SKILL_ID_RE.match(skill_id):
        return ""
    path = os.path.join(SKILLS_DIR, skill_id, "SKILL.md")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _fetch_fn(url: str) -> tuple[str, str]:
    import httpx

    with httpx.Client(follow_redirects=True, timeout=HTTP_TIMEOUT_S) as client:
        resp = client.get(url, headers={"User-Agent": "PermitPilot/0.1 (research)"})
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "").lower()
        data = resp.content[:MAX_BYTES]
    content_hash = "sha256:" + hashlib.sha256(data).hexdigest()
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        import fitz

        doc = fitz.open(stream=data, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    else:
        from bs4 import BeautifulSoup

        text = BeautifulSoup(data, "html.parser").get_text(" ", strip=True)
    return content_hash, text[:MAX_TEXT_CHARS]


def _to_openai_messages(messages: list[dict]) -> list[dict]:
    """Translate the loop's internal messages into OpenAI chat format.

    Internal assistant turns carry tool_calls as {"id","name","arguments"(dict)};
    internal tool turns carry {"tool_call_id","content"}. System/user pass through.
    """
    out = []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            out.append({
                "role": "assistant",
                "content": m.get("content") or "",
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments", {}))}}
                    for c in m["tool_calls"]
                ],
            })
        elif role == "tool":
            out.append({"role": "tool", "tool_call_id": m.get("tool_call_id", ""), "content": m.get("content", "")})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    return out


def _llm_fn(messages: list[dict], tools: list[dict]) -> dict:
    """One OpenAI chat call. Returns the assistant turn normalized for the loop.

    Does NOT mutate `messages` — the loop records the assistant turn itself.
    Reasoning-model compatible: max_completion_tokens, no temperature.
    """
    from openai import OpenAI

    client = OpenAI()
    kwargs = {"model": _model(), "messages": _to_openai_messages(messages), "max_completion_tokens": 4000}
    if tools:
        kwargs["tools"] = tools
    msg = client.chat.completions.create(**kwargs).choices[0].message
    out = []
    for tc in (msg.tool_calls or []):
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        out.append({"id": tc.id, "name": tc.function.name, "arguments": args})
    return {"content": msg.content, "tool_calls": out}


def _extract_fn(text: str, question: str, hint: dict) -> dict:
    from openai import OpenAI

    client = OpenAI()
    field = hint.get("field", "source_claim")
    ask = hint.get("ask", "the clause that determines whether this requirement applies")
    tool = {
        "type": "function",
        "function": {
            "name": "extract_finding",
            "description": "Return the grounded finding.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": [field]},
                    "threshold_value": {"type": ["number", "null"]},
                    "verbatim_quote": {"type": "string"},
                    "applies": {"type": "string", "enum": ["applies", "does_not_apply", "needs_review"]},
                    "confidence": {"type": "number"},
                },
                "required": ["field", "verbatim_quote", "applies", "confidence"],
            },
        },
    }
    completion = client.chat.completions.create(
        model=_model(),
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": f"Research question: {question}\nExtract {ask}.\n\nSOURCE TEXT:\n{text}"},
        ],
        tools=[tool],
        tool_choice="required",
        max_completion_tokens=2000,
    )
    calls = completion.choices[0].message.tool_calls or []
    if not calls:
        return {"field": field, "verbatim_quote": "", "applies": "needs_review", "confidence": 0.3}
    return json.loads(calls[0].function.arguments or "{}")


def _run(task_spec: dict) -> dict:
    hid = task_spec.get("hypothesis_id", "")
    if SOURCE_POINTERS.get(hid) is None:
        return failed_bundle(hid, f"No source pointer for {hid}")
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        return run_research_agent(task_spec, llm_fn=_llm_fn, fetch_fn=_fetch_fn,
                                  extract_fn=_extract_fn, now_iso=now_iso,
                                  read_skill_fn=_read_skill_fn)
    except Exception as exc:  # noqa: BLE001 — never throw out of the worker
        return failed_bundle(hid, f"Agent failed: {exc}")


def _runtime_task_from_spec(task_spec: dict[str, Any]) -> RuntimeTask:
    return RuntimeTask(
        task_id=task_spec["task_id"],
        hypothesis_id=task_spec["hypothesis_id"],
        question=task_spec["question"],
        family=task_spec.get("family", "unknown"),
        skill_id=task_spec.get("skill_id"),
        allowed_domains=task_spec.get("allowed_domains", []),
        input=task_spec,
    )


@app.function(image=image, secrets=[
    modal.Secret.from_name("permitpilot-openai"),
    modal.Secret.from_name("permitpilot-research"),
], timeout=600)
@modal.fastapi_endpoint(method="POST")
def research(payload: dict) -> dict:
    expected = os.environ.get("RESEARCH_TOKEN", "")
    if not expected or payload.get("token") != expected:
        return {"error": "unauthorized"}
    task_spec = payload.get("task_spec") or {}
    return _run(task_spec)


@app.function(image=image, secrets=[modal.Secret.from_name("permitpilot-openai")], timeout=600)
def research_task(task_spec: dict) -> dict:
    return _run(task_spec)


def _supabase():
    from supabase import create_client
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _write_bundle(sb, run_id: str, bundle: dict) -> None:
    sb.table("research_evidence").upsert(evidence_row(run_id, bundle)).execute()


def _update_run(sb, run_id: str, payload: dict[str, Any]) -> None:
    sb.table("research_runs").update(payload).eq("run_id", run_id).execute()


def _timeline_events(workspace: Path) -> list[dict[str, Any]]:
    timeline = workspace / "logs" / "timeline.jsonl"
    if not timeline.is_file():
        return []
    events = []
    for line in timeline.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def _artifact_index(workspace: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in _timeline_events(workspace):
        artifact_path = event.get("artifact_path")
        if not artifact_path or artifact_path in seen:
            continue
        seen.add(artifact_path)
        artifacts.append({
            "kind": event.get("type", "artifact"),
            "path": artifact_path,
            "task_id": event.get("task_id"),
        })
    return artifacts


def _trace_events_from_timeline(workspace: Path, run_id: str) -> list[dict[str, Any]]:
    mapped = []
    for event in _timeline_events(workspace):
        event_type = event.get("type")
        task_id = event.get("task_id")
        artifact_path = event.get("artifact_path")
        if event_type == "draft":
            mapped.append(trace_event(
                "research_worker",
                "draft.completed",
                "done",
                f"Draft completed for {task_id}",
                artifact_path or task_id,
                run_id=run_id,
            ))
        elif event_type == "review":
            decision = event.get("decision", "needs_human_review")
            status = "done" if decision == "accepted" else "needs_review"
            mapped.append(trace_event(
                "reviewer",
                f"review.decision.{decision}",
                status,
                f"Reviewer returned {decision} for {task_id}",
                artifact_path or task_id,
                run_id=run_id,
            ))
        elif event_type == "repair":
            mapped.append(trace_event(
                "research_worker",
                "repair.completed",
                "done",
                f"Repair attempt {event.get('attempt', 1)} completed for {task_id}",
                artifact_path or task_id,
                run_id=run_id,
            ))
        elif event_type == "needs_human_review":
            mapped.append(trace_event(
                "reviewer",
                "review.needs_human_review",
                "needs_review",
                f"Reviewer escalated {task_id} to human review",
                artifact_path or task_id,
                run_id=run_id,
            ))
        elif event_type == "accepted":
            mapped.append(trace_event(
                "reviewer",
                "review.accepted",
                "done",
                f"Reviewer accepted {task_id}",
                artifact_path or task_id,
                run_id=run_id,
            ))
        elif event_type == "synthesis":
            mapped.append(trace_event(
                "synthesis_agent",
                "synthesis.completed",
                "done",
                "Runtime synthesis artifact written",
                artifact_path or run_id,
                run_id=run_id,
            ))
    return mapped


def run_workspace_research(
    run_id: str,
    task_specs: list[dict[str, Any]],
    *,
    update_run_fn: Callable[[dict[str, Any]], None],
    upsert_evidence_fn: Callable[[dict[str, Any]], None],
    draft_fn: Callable[[RuntimeTask, str], Any],
    review_fn: Callable[[RuntimeTask, Any, str], Any],
    repair_fn: Callable[[RuntimeTask, Any, Any, str], Any],
    workspace_root: Path,
    read_skill_fn: Callable[[str], str],
) -> dict[str, Any]:
    from workspace_core import ensure_workspace

    workspace = ensure_workspace(workspace_root, run_id)
    trace_events = [
        trace_event("parent", "workspace.booting", "running", "Booting workspace runtime", run_id, run_id=run_id),
        trace_event("parent", "parent.planning", "running", "Planning runtime tasks", run_id, run_id=run_id),
    ]
    update_run_fn({
        "status": "running",
        "trace_events": trace_events,
        "workspace_prefix": run_id,
        "artifact_index": [],
    })

    try:
        tasks = [_runtime_task_from_spec(task_spec) for task_spec in task_specs]
        bundles = []
        for task in tasks:
            skill_text = read_skill_fn(task.skill_id or "")
            rulebook = build_rulebook(task, skill_text)
            review = run_task_with_review(
                task,
                workspace,
                rulebook,
                draft_fn=draft_fn,
                review_fn=review_fn,
                repair_fn=repair_fn,
            )
            bundle = evidence_bundle_from_review(task, review, workspace)
            upsert_evidence_fn(bundle)
            bundles.append(bundle)
            trace_events = trace_events[:2] + _trace_events_from_timeline(workspace, run_id)
            update_run_fn({
                "status": "running",
                "trace_events": trace_events,
                "workspace_prefix": run_id,
                "artifact_index": _artifact_index(workspace),
            })

        synthesis = synthesize_runtime_artifacts(run_id, tasks, workspace)
        trace_events = trace_events[:2] + _trace_events_from_timeline(workspace, run_id)
        trace_events.append(trace_event(
            "synthesis_agent",
            "bundles.complete",
            "done",
            "Runtime evidence rows are written; synthesis artifact is available",
            run_id,
            run_id=run_id,
        ))
        artifacts = _artifact_index(workspace)
        update_run_fn({
            "status": "bundles_complete",
            "trace_events": trace_events,
            "workspace_prefix": run_id,
            "artifact_index": artifacts,
        })
        return {
            "run_id": run_id,
            "written": len(bundles),
            "workspace_prefix": run_id,
            "artifact_index": artifacts,
            "trace_events": trace_events,
            "bundles": bundles,
            "synthesis": synthesis,
        }
    except Exception as exc:
        try:
            trace_events = trace_events[:2] + _trace_events_from_timeline(workspace, run_id)
        except Exception:
            trace_events = trace_events[:2]
        trace_events.append(trace_event(
            "parent",
            "runtime.failed",
            "failed",
            f"Workspace runtime failed: {exc}",
            run_id,
            run_id=run_id,
        ))
        try:
            artifacts = _artifact_index(workspace)
        except Exception:
            artifacts = []
        update_run_fn({
            "status": "failed",
            "trace_events": trace_events,
            "workspace_prefix": run_id,
            "artifact_index": artifacts,
        })
        raise


@app.function(image=image, secrets=[
    modal.Secret.from_name("permitpilot-openai"),
    modal.Secret.from_name("permitpilot-supabase"),
], timeout=3600)
def research_run(run_id: str, task_specs: list) -> dict:
    sb = _supabase()
    workspace_root = Path("/tmp/permitpilot-runs")

    def draft_with_context(task: RuntimeTask, rulebook: str):
        return run_worker_draft(task, rulebook, {"run_id": run_id, "workspace_prefix": str(workspace_root / run_id)})

    return run_workspace_research(
        run_id,
        task_specs,
        update_run_fn=lambda payload: _update_run(sb, run_id, payload),
        upsert_evidence_fn=lambda bundle: _write_bundle(sb, run_id, bundle),
        draft_fn=draft_with_context,
        review_fn=run_review,
        repair_fn=run_worker_repair,
        workspace_root=workspace_root,
        read_skill_fn=_read_skill_fn,
    )


@app.function(image=image, secrets=[
    modal.Secret.from_name("permitpilot-research"),
], timeout=60)
@modal.fastapi_endpoint(method="POST")
def start_run(payload: dict) -> dict:
    expected = os.environ.get("RESEARCH_TOKEN", "")
    if not expected or payload.get("token") != expected:
        return {"error": "unauthorized"}
    run_id = payload.get("run_id")
    task_specs = payload.get("task_specs") or []
    if not run_id:
        return {"error": "missing run_id"}
    research_run.spawn(run_id, task_specs)
    return {"run_id": run_id, "status": "queued"}


@app.local_entrypoint()
def main(task_json: str) -> None:
    result = research_task.remote(json.loads(task_json))
    sys.stdout.write("PERMITPILOT_BUNDLE_JSON " + json.dumps(result) + "\n")
    sys.stdout.flush()
