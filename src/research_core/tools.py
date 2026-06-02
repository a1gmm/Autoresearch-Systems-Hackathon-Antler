from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


DEFAULT_ALLOWED_HOSTS = (
    "aqmd.gov",
    "scaqmd.gov",
    "arb.ca.gov",
    "ca.gov",
    "epa.gov",
    "osha.gov",
    "govinfo.gov",
    "ecfr.gov",
    "law.cornell.edu",
)
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
MAX_REDIRECT_HOPS = 5


@dataclass(frozen=True)
class SandboxPolicy:
    run_id: str
    artifact_root: Path
    allowed_hosts: tuple[str, ...] = field(default_factory=lambda: DEFAULT_ALLOWED_HOSTS)
    allow_network: bool = True
    allow_browser: bool = True
    timeout_seconds: float = 15.0
    search_endpoint: str | None = None


def _normalize_host(host: str | None) -> str:
    return (host or "").strip().rstrip(".").lower()


def host_allowed(url: str, allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    host = _normalize_host(parsed.hostname)
    if not host or parsed.scheme not in {"http", "https"}:
        return False

    for allowed in allowed_hosts:
        allowed_host = _normalize_host(allowed)
        if host == allowed_host or host.endswith(f".{allowed_host}"):
            return True
    return False


def _error(status: str, code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "status": status,
        "error": {"code": code, "message": message},
    }
    payload.update(extra)
    return payload


def _success(status: str, **payload: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": True, "status": status}
    result.update(payload)
    return result


def _exception_error(
    code: str,
    exc: Exception,
    status: str = "error",
    **extra: Any,
) -> dict[str, Any]:
    return _error(status, code, str(exc), exception_type=exc.__class__.__name__, **extra)


def _invalid_argument(argument: str, expected: str, value: Any = None) -> dict[str, Any]:
    return _error(
        "error",
        "invalid_argument",
        f"{argument} must be {expected}.",
        argument=argument,
        received_type=type(value).__name__,
    )


def _safe_run_workspace(policy: SandboxPolicy) -> Path:
    root = Path(policy.artifact_root).expanduser().resolve()
    workspace = (root / policy.run_id).resolve()
    if root != workspace and root not in workspace.parents:
        raise ValueError("run workspace is outside artifact root")
    return workspace


def _resolve_workspace_path(policy: SandboxPolicy, relative_path: str | Path) -> Path:
    workspace = _safe_run_workspace(policy)
    if not isinstance(relative_path, (str, Path)):
        raise TypeError("workspace path must be a string or Path")
    path = Path(relative_path)
    if path.is_absolute():
        raise ValueError("workspace path must be relative")
    resolved = (workspace / path).resolve()
    if resolved == workspace or workspace in resolved.parents:
        return resolved
    raise ValueError("workspace path escapes run workspace")


def _resolve_artifact_path(policy: SandboxPolicy, relative_path: str | Path) -> Path:
    return _resolve_workspace_path(policy, relative_path)


def _header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", {})
    return headers.get(name) or headers.get(name.lower()) or headers.get(name.title())


def _is_redirect(response: Any) -> bool:
    return getattr(response, "status_code", None) in REDIRECT_STATUS_CODES and bool(_header(response, "location"))


def _guarded_get(
    policy: SandboxPolicy,
    client: Any,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> tuple[Any | None, dict[str, Any] | None, list[dict[str, Any]]]:
    current_url = url
    redirect_chain: list[dict[str, Any]] = []
    context = context or {}

    for hop in range(MAX_REDIRECT_HOPS + 1):
        response = client.get(current_url, params=params if hop == 0 else None)
        status_code = getattr(response, "status_code", None)
        chain_entry = {"url": current_url, "status_code": status_code}
        redirect_chain.append(chain_entry)

        if not _is_redirect(response):
            return response, None, redirect_chain

        raw_location = _header(response, "location")
        next_url = urljoin(str(getattr(response, "url", current_url)), raw_location or "")
        chain_entry["location"] = next_url
        if not host_allowed(next_url, policy.allowed_hosts):
            return (
                None,
                _error(
                    "blocked",
                    "redirect_host_not_allowed",
                    "Redirect target is outside sandbox policy.",
                    redirect_chain=redirect_chain,
                    blocked_url=next_url,
                    **context,
                ),
                redirect_chain,
            )
        current_url = next_url

    return (
        None,
        _error(
            "error",
            "redirect_limit_exceeded",
            "Redirect hop limit exceeded.",
            redirect_chain=redirect_chain,
            **context,
        ),
        redirect_chain,
    )


def web_fetch(policy: SandboxPolicy, url: str) -> dict[str, Any]:
    if not isinstance(url, str):
        return _invalid_argument("url", "a string", url)
    if not policy.allow_network:
        return _error("blocked", "network_disabled", "Network access is disabled by sandbox policy.", url=url)
    if not host_allowed(url, policy.allowed_hosts):
        return _error("blocked", "host_not_allowed", "URL host is not allowed by sandbox policy.", url=url)

    try:
        import httpx
    except ImportError:
        return _error("unavailable", "dependency_missing", "httpx is not installed.", dependency="httpx")

    try:
        with httpx.Client(follow_redirects=False, timeout=policy.timeout_seconds) as client:
            response, redirect_error, redirect_chain = _guarded_get(policy, client, url, context={"url": url})
        if redirect_error is not None:
            return redirect_error
        final_url = str(response.url)
        if not host_allowed(final_url, policy.allowed_hosts):
            return _error(
                "blocked",
                "redirect_host_not_allowed",
                "Fetch redirected to a host outside sandbox policy.",
                url=url,
                final_url=final_url,
            )
        content_type = response.headers.get("content-type")
        text = response.text if response.is_success else ""
        return _success(
            "fetched" if response.is_success else "http_error",
            url=url,
            final_url=final_url,
            status_code=response.status_code,
            content_type=content_type,
            text=text,
            headers=dict(response.headers),
            redirect_chain=redirect_chain,
        )
    except Exception as exc:
        return _exception_error("fetch_failed", exc, url=url)


def web_search(policy: SandboxPolicy, query: str, *, limit: int = 5) -> dict[str, Any]:
    if not isinstance(query, str):
        return _invalid_argument("query", "a string", query)
    if not isinstance(limit, int) or isinstance(limit, bool):
        return _invalid_argument("limit", "an integer", limit)
    if not policy.allow_network:
        return _error("blocked", "network_disabled", "Network access is disabled by sandbox policy.", query=query)
    if not query.strip():
        return _error("error", "empty_query", "Search query must not be empty.", query=query)
    if policy.search_endpoint is None:
        return _error(
            "unavailable",
            "search_provider_unavailable",
            "No sandbox web search provider is configured.",
            query=query,
            limit=limit,
        )
    if not isinstance(policy.search_endpoint, str):
        return _invalid_argument("search_endpoint", "a string", policy.search_endpoint)
    if not host_allowed(policy.search_endpoint, policy.allowed_hosts):
        return _error(
            "blocked",
            "host_not_allowed",
            "Search endpoint host is not allowed by sandbox policy.",
            endpoint=policy.search_endpoint,
        )

    try:
        import httpx
    except ImportError:
        return _error("unavailable", "dependency_missing", "httpx is not installed.", dependency="httpx")

    try:
        with httpx.Client(follow_redirects=False, timeout=policy.timeout_seconds) as client:
            response, redirect_error, redirect_chain = _guarded_get(
                policy,
                client,
                policy.search_endpoint,
                params={"q": query, "limit": limit},
                context={"query": query, "endpoint": policy.search_endpoint},
            )
        if redirect_error is not None:
            return redirect_error
        final_url = str(response.url)
        if not host_allowed(final_url, policy.allowed_hosts):
            return _error(
                "blocked",
                "redirect_host_not_allowed",
                "Search redirected to a host outside sandbox policy.",
                endpoint=policy.search_endpoint,
                final_url=final_url,
            )

        content_type = response.headers.get("content-type", "")
        results: Any
        if "json" in content_type:
            results = response.json()
        else:
            results = response.text
        return _success(
            "searched" if response.is_success else "http_error",
            query=query,
            endpoint=policy.search_endpoint,
            final_url=final_url,
            status_code=response.status_code,
            results=results,
            redirect_chain=redirect_chain,
        )
    except Exception as exc:
        return _exception_error("search_failed", exc, query=query, endpoint=policy.search_endpoint)


def write_artifact(policy: SandboxPolicy, relative_path: str | Path, contents: str | bytes) -> dict[str, Any]:
    if not isinstance(relative_path, (str, Path)):
        return _invalid_argument("relative_path", "a string or Path", relative_path)
    if not isinstance(contents, (str, bytes)):
        return _invalid_argument("contents", "a string or bytes", contents)
    try:
        workspace = _safe_run_workspace(policy)
        path = _resolve_artifact_path(policy, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, bytes):
            path.write_bytes(contents)
            bytes_written = len(contents)
        else:
            path.write_text(contents)
            bytes_written = len(contents.encode())
        return _success(
            "written",
            path=str(path),
            workspace=str(workspace),
            bytes_written=bytes_written,
        )
    except TypeError as exc:
        return _error("error", "invalid_argument", str(exc), path=str(relative_path))
    except ValueError as exc:
        return _error("error", "path_traversal", str(exc), path=str(relative_path))
    except Exception as exc:
        return _exception_error("artifact_write_failed", exc, path=str(relative_path))


def submit_finding(
    policy: SandboxPolicy,
    *,
    title: str,
    summary: str,
    sources: list[str],
    confidence: float,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(title, str):
        return _invalid_argument("title", "a string", title)
    if not isinstance(summary, str):
        return _invalid_argument("summary", "a string", summary)
    if not isinstance(sources, list):
        return _invalid_argument("sources", "a list of strings", sources)
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        return _invalid_argument("confidence", "a number between 0 and 1", confidence)
    if metadata is not None and not isinstance(metadata, dict):
        return _invalid_argument("metadata", "a dictionary", metadata)
    if not title.strip():
        return _error("error", "missing_title", "Finding title must not be empty.")
    if not summary.strip():
        return _error("error", "missing_summary", "Finding summary must not be empty.")
    if confidence < 0 or confidence > 1:
        return _error("error", "invalid_confidence", "Finding confidence must be between 0 and 1.")

    source_error = _validate_sources(sources, policy)
    if source_error is not None:
        return source_error

    finding = {
        "run_id": policy.run_id,
        "title": title,
        "summary": summary,
        "sources": list(sources),
        "confidence": confidence,
        "metadata": metadata or {},
        "submitted_at": datetime.now(UTC).isoformat(),
    }
    artifact = write_artifact(policy, f"findings/{_slug(title)}.json", json.dumps(finding, indent=2, sort_keys=True))
    if not artifact["ok"]:
        return artifact
    return _success("submitted", finding=finding, artifact_path=artifact["path"])


def _validate_sources(sources: list[str], policy: SandboxPolicy) -> dict[str, Any] | None:
    disallowed = []
    malformed = []
    for source in sources:
        if not isinstance(source, str):
            return _invalid_argument("sources", "a list of strings", source)
        trimmed = source.strip()
        parsed = urlparse(trimmed)
        scheme = parsed.scheme.lower()
        if scheme in {"http", "https"}:
            if not parsed.hostname:
                malformed.append(source)
            elif not host_allowed(trimmed, policy.allowed_hosts):
                disallowed.append(source)
        elif parsed.netloc:
            malformed.append(source)
        elif scheme:
            continue
        elif trimmed.lower().startswith(("http:", "https:")):
            malformed.append(source)

    if malformed:
        return _error(
            "error",
            "source_url_invalid",
            "One or more finding sources are malformed HTTP(S) URLs.",
            sources=malformed,
        )
    if disallowed:
        return _error(
            "blocked",
            "host_not_allowed",
            "One or more finding sources are outside sandbox policy.",
            sources=disallowed,
        )
    return None


def _slug(value: str) -> str:
    chars = [char.lower() if char.isalnum() else "-" for char in value.strip()]
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "finding"


def browser_use(policy: SandboxPolicy, url: str, **kwargs: Any) -> dict[str, Any]:
    from research_core.browser import browser_use as _browser_use

    return _browser_use(policy, url, **kwargs)


def read_pdf(policy: SandboxPolicy, path: str | Path) -> dict[str, Any]:
    from research_core.documents import read_pdf as _read_pdf

    return _read_pdf(policy, path)


def read_docx(policy: SandboxPolicy, path: str | Path) -> dict[str, Any]:
    from research_core.documents import read_docx as _read_docx

    return _read_docx(policy, path)


def read_spreadsheet(policy: SandboxPolicy, path: str | Path) -> dict[str, Any]:
    from research_core.documents import read_spreadsheet as _read_spreadsheet

    return _read_spreadsheet(policy, path)
