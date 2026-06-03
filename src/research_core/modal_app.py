from __future__ import annotations

import os
from typing import Any

from research_core.orchestrator import ResearchDeps
from research_core.orchestrator import resume_research_sync, run_research_sync
from research_core.store import store_from_env


DEPS_MODE_ENV = "RESEARCH_CORE_DEPS_MODE"
MODAL_SECRET_NAMES = (
    "permitpilot-openai",
    "permitpilot-research",
    "permitpilot-supabase",
)
MODAL_PIP_PACKAGES = (
    "modal",
    "openai",
    "openai-agents",
    "pydantic>=2,<3",
    "supabase",
    "httpx>=0.28,<1",
    "beautifulsoup4>=4,<5",
    "pymupdf>=1.24,<2",
    "python-docx>=1.1,<2",
    "openpyxl>=3.1,<4",
    "playwright>=1.56,<2",
)


def start_run(input_payload: dict[str, Any]) -> dict[str, Any]:
    return _create_queued_run(input_payload)


def _create_queued_run(input_payload: dict[str, Any]) -> dict[str, Any]:
    store = store_from_env()
    record = store.create_run(input_payload)
    return {"run_id": record["run_id"], "status": record["status"]}


def run_sync(input_payload: dict[str, Any]) -> dict[str, Any]:
    return run_research_sync(
        input_payload,
        deps=_deps_from_env(),
        store=store_from_env(),
    ).model_dump(mode="json")


def resume_run(run_id: str) -> dict[str, Any]:
    return resume_research_sync(
        run_id,
        deps=_deps_from_env(),
        store=store_from_env(),
    ).model_dump(mode="json")


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
                deps=_deps_from_env(),
                run_id=run_or_payload,
                store=store,
            ).model_dump(mode="json")
        record = store.get_run(run_or_payload)
        if record is None:
            raise KeyError(f"run {run_or_payload!r} was not found")
        return run_research_sync(
            record["input"],
            deps=_deps_from_env(),
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
    function_options = _modal_function_options(modal)
    # research_run runs every hypothesis sequentially -> needs a larger ceiling.
    research_run_options = {**function_options, "timeout": MODAL_RESEARCH_RUN_TIMEOUT_SECONDS}

    def _background(function):
        function._permitpilot_background = True
        return function

    @modal_app_instance.function(**research_run_options)
    @_background
    def research_run(
        run_or_payload: str | dict[str, Any],
        input_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return globals()["research_run"](run_or_payload, input_payload)

    @modal_app_instance.function(**function_options)
    @endpoint(method="POST")
    def start_run(input_payload: dict[str, Any]) -> dict[str, Any]:
        response = _create_queued_run(input_payload)
        research_run.spawn(response["run_id"], input_payload)
        return response

    @modal_app_instance.function(**function_options)
    @endpoint(method="POST")
    def run_sync(input_payload: dict[str, Any]) -> dict[str, Any]:
        return globals()["run_sync"](input_payload)

    @modal_app_instance.function(**function_options)
    @endpoint(method="POST")
    def resume_run(run_id: str) -> dict[str, Any]:
        return globals()["resume_run"](run_id)

    @modal_app_instance.function(**function_options)
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


def _deps_from_env() -> ResearchDeps:
    mode = os.environ.get(DEPS_MODE_ENV, "live").strip().lower()
    if mode in {"fake", "offline"}:
        return ResearchDeps(mode=mode)
    return ResearchDeps(mode="live")


# Production, not demo: each hypothesis gets up to ~60 min of durable research (the
# per-hypothesis agent budget is 3600s). Modal's default function timeout is 300s,
# which would cut real research off. Endpoints get 60 min; the background research_run
# runs every hypothesis SEQUENTIALLY, so it gets a generous ceiling (6h) so a real
# multi-hypothesis run is never truncated.
MODAL_FUNCTION_TIMEOUT_SECONDS = 3600
MODAL_RESEARCH_RUN_TIMEOUT_SECONDS = 21600


def _modal_function_options(modal: Any) -> dict[str, Any]:
    options: dict[str, Any] = {"timeout": MODAL_FUNCTION_TIMEOUT_SECONDS}
    image = _modal_image(modal)
    if image is not None:
        options["image"] = image
    secrets = _modal_secrets(modal)
    if secrets:
        options["secrets"] = secrets
    return options


def _modal_image(modal: Any) -> Any | None:
    image_class = getattr(modal, "Image", None)
    if image_class is None or not hasattr(image_class, "debian_slim"):
        return None
    image = image_class.debian_slim(python_version="3.12").pip_install(*MODAL_PIP_PACKAGES)
    add_local_dir = getattr(image, "add_local_dir", None)
    if callable(add_local_dir):
        image = image.add_local_dir("src/research_core", remote_path="/root/research_core")
        image = image.add_local_dir("src/lib/research/skills", remote_path="/root/src/lib/research/skills")
    return image


def _modal_secrets(modal: Any) -> list[Any]:
    secret_class = getattr(modal, "Secret", None)
    if secret_class is None or not hasattr(secret_class, "from_name"):
        return []
    return [secret_class.from_name(name) for name in MODAL_SECRET_NAMES]


app = _build_modal_app()
