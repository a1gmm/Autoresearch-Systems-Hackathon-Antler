from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable

from runtime_models import ReviewResult, RuntimeTask, WorkerDraft
from workspace_core import append_event, write_json


def _artifact_path(workspace_root: Path, artifact_path: str) -> Path:
    workspace = workspace_root.resolve()
    path = Path(artifact_path)
    if path.is_absolute():
        raise ValueError(f"Artifact path must be relative: {artifact_path}")
    resolved = (workspace / path).resolve()
    if resolved != workspace and workspace not in resolved.parents:
        raise ValueError(f"Artifact path escapes workspace: {artifact_path}")
    return resolved


def _write_artifact(workspace_root: Path, artifact_path: str, payload: object) -> None:
    write_json(_artifact_path(workspace_root, artifact_path), asdict(payload))


def run_task_with_review(
    task: RuntimeTask,
    workspace_root: Path,
    rulebook: str,
    draft_fn: Callable[[RuntimeTask, str], WorkerDraft],
    review_fn: Callable[[RuntimeTask, WorkerDraft, str], ReviewResult],
    repair_fn: Callable[[RuntimeTask, WorkerDraft, ReviewResult, str], WorkerDraft],
    max_repairs: int = 2,
) -> ReviewResult:
    repairs = 0
    draft = draft_fn(task, rulebook)
    _write_artifact(workspace_root, draft.artifact_path, draft)
    append_event(workspace_root, {
        "type": "draft",
        "task_id": task.task_id,
        "artifact_path": draft.artifact_path,
    })

    while True:
        review = review_fn(task, draft, rulebook)
        _write_artifact(workspace_root, review.artifact_path, review)
        append_event(workspace_root, {
            "type": "review",
            "task_id": task.task_id,
            "decision": review.decision,
            "artifact_path": review.artifact_path,
        })

        if review.decision == "accepted":
            append_event(workspace_root, {
                "type": "accepted",
                "task_id": task.task_id,
                "artifact_path": review.artifact_path,
            })
            return review

        if review.decision == "needs_human_review" or repairs >= max_repairs:
            final = ReviewResult(
                task_id=review.task_id,
                decision="needs_human_review",
                findings=review.findings,
                accepted_evidence_ids=review.accepted_evidence_ids,
                artifact_path=review.artifact_path,
            )
            append_event(workspace_root, {
                "type": "needs_human_review",
                "task_id": task.task_id,
                "artifact_path": final.artifact_path,
            })
            return final

        repairs += 1
        draft = repair_fn(task, draft, review, rulebook)
        _write_artifact(workspace_root, draft.artifact_path, draft)
        append_event(workspace_root, {
            "type": "repair",
            "task_id": task.task_id,
            "attempt": repairs,
            "artifact_path": draft.artifact_path,
        })
