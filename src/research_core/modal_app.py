from __future__ import annotations

from typing import Any

from research_core.orchestrator import resume_research_sync, run_research_sync
from research_core.store import store_from_env


def start_run(input_payload: dict[str, Any]) -> dict[str, Any]:
    return _create_queued_run(input_payload)


def _create_queued_run(input_payload: dict[str, Any]) -> dict[str, Any]:
    store = store_from_env()
    record = store.create_run(input_payload)
    return {"run_id": record["run_id"], "status": record["status"]}


def run_sync(input_payload: dict[str, Any]) -> dict[str, Any]:
    return run_research_sync(input_payload, store=store_from_env()).model_dump(mode="json")


def resume_run(run_id: str) -> dict[str, Any]:
    return resume_research_sync(run_id, store=store_from_env()).model_dump(mode="json")


def get_run(run_id: str) -> dict[str, Any] | None:
    return store_from_env().get_run(run_id)


def research_run(
    run_or_payload: str | dict[str, Any],
    input_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(run_or_payload, str):
        store = store_from_env()
        if input_payload is not None:
            return run_research_sync(
                input_payload,
                run_id=run_or_payload,
                store=store,
            ).model_dump(mode="json")
        record = store.get_run(run_or_payload)
        if record is None:
            raise KeyError(f"run {run_or_payload!r} was not found")
        return run_research_sync(
            record["input"],
            run_id=run_or_payload,
            store=store,
        ).model_dump(mode="json")
    return run_sync(run_or_payload)


def modal_app() -> Any | None:
    return app


def _build_modal_app() -> Any | None:
    try:
        import modal
    except ModuleNotFoundError:
        return None
    modal_app_instance = modal.App("permitpilot-python-research")
    _register_modal_functions(modal_app_instance, modal)
    return modal_app_instance


def _register_modal_functions(modal_app_instance: Any, modal: Any) -> None:
    endpoint = _endpoint_decorator(modal)

    def _background(function):
        function._permitpilot_background = True
        return function

    @modal_app_instance.function()
    @_background
    def research_run(
        run_or_payload: str | dict[str, Any],
        input_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return globals()["research_run"](run_or_payload, input_payload)

    @modal_app_instance.function()
    @endpoint(method="POST")
    def start_run(input_payload: dict[str, Any]) -> dict[str, Any]:
        response = _create_queued_run(input_payload)
        research_run.spawn(response["run_id"], input_payload)
        return response

    @modal_app_instance.function()
    @endpoint(method="POST")
    def run_sync(input_payload: dict[str, Any]) -> dict[str, Any]:
        return globals()["run_sync"](input_payload)

    @modal_app_instance.function()
    @endpoint(method="POST")
    def resume_run(run_id: str) -> dict[str, Any]:
        return globals()["resume_run"](run_id)

    @modal_app_instance.function()
    @endpoint(method="GET")
    def get_run(run_id: str) -> dict[str, Any] | None:
        return globals()["get_run"](run_id)


def _endpoint_decorator(modal: Any):
    decorator = (
        getattr(modal, "fastapi_endpoint", None)
        or getattr(modal, "web_endpoint", None)
    )
    if decorator is not None:
        return decorator

    def identity_endpoint(*args: Any, **kwargs: Any):
        def decorate(function):
            return function

        return decorate

    return identity_endpoint


app = _build_modal_app()
