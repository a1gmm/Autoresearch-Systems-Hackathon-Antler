from __future__ import annotations

from typing import Any

from research_core.tools import (
    SandboxPolicy,
    _error,
    _exception_error,
    _invalid_argument,
    _success,
    host_allowed,
)


def browser_use(policy: SandboxPolicy, url: str, *, wait_until: str = "domcontentloaded") -> dict[str, Any]:
    if not isinstance(url, str):
        return _invalid_argument("url", "a string", url)
    if not policy.allow_browser:
        return _error("blocked", "browser_disabled", "Browser access is disabled by sandbox policy.", url=url)
    if not host_allowed(url, policy.allowed_hosts):
        return _error("blocked", "host_not_allowed", "URL host is not allowed by sandbox policy.", url=url)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _error("unavailable", "dependency_missing", "playwright is not installed.", dependency="playwright")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = None
            try:
                blocked_requests: list[dict[str, Any]] = []

                def guard_route(route: Any, request: Any) -> None:
                    request_url = getattr(request, "url", "")
                    if host_allowed(request_url, policy.allowed_hosts):
                        route.continue_()
                        return
                    blocked_requests.append(
                        {
                            "url": request_url,
                            "resource_type": getattr(request, "resource_type", None),
                        }
                    )
                    route.abort()

                context = browser.new_context(service_workers="block")
                context.route("**/*", guard_route)
                page = context.new_page()
                try:
                    response = page.goto(url, wait_until=wait_until, timeout=int(policy.timeout_seconds * 1000))
                except Exception:
                    if blocked_requests:
                        return _error(
                            "blocked",
                            "resource_host_not_allowed",
                            "Browser blocked a request outside sandbox policy.",
                            url=url,
                            blocked_url=blocked_requests[0]["url"],
                            blocked_requests=blocked_requests,
                        )
                    raise
                if blocked_requests:
                    return _error(
                        "blocked",
                        "resource_host_not_allowed",
                        "Browser blocked a request outside sandbox policy.",
                        url=url,
                        blocked_url=blocked_requests[0]["url"],
                        blocked_requests=blocked_requests,
                    )
                final_url = page.url
                if not host_allowed(final_url, policy.allowed_hosts):
                    return _error(
                        "blocked",
                        "redirect_host_not_allowed",
                        "Browser navigation reached a host outside sandbox policy.",
                        url=url,
                        final_url=final_url,
                    )
                body = page.locator("body")
                snapshot = {
                    "url": final_url,
                    "title": page.title(),
                    "text": body.inner_text(timeout=int(policy.timeout_seconds * 1000)) if body.count() else "",
                    "status_code": response.status if response is not None else None,
                }
            finally:
                if context is not None:
                    context.close()
                browser.close()
        return _success("navigated", snapshot=snapshot)
    except Exception as exc:
        return _exception_error("browser_failed", exc, url=url)
