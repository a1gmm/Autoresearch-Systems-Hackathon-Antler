from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from research_core.tools import (
    BROWSER_USER_AGENT,
    SandboxPolicy,
    _cap_text,
    _error,
    _exception_error,
    _extract_pdf_text,
    _invalid_argument,
    _success,
    host_fetchable,
)


# Cloudflare / JS-challenge interstitials show one of these while the browser runs the
# challenge; once it clears we get the real page. Poll until they disappear.
_CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "verify you are human",
    "needs to review the security",
    "cf-chl",
    "challenge-platform",
    "attention required",
)


def _wait_out_challenge(page: Any, max_seconds: float) -> None:
    """A real browser clears a Cloudflare JS challenge in a few seconds; poll the title/body
    until the challenge markers disappear (or the budget runs out) so we read the actual page,
    not the 'Just a moment…' interstitial."""
    deadline_ms = int(max(3.0, min(max_seconds, 20.0)) * 1000)
    waited = 0
    while waited < deadline_ms:
        title = ""
        try:
            title = (page.title() or "").lower()
        except Exception:  # noqa: BLE001 — title not ready yet
            title = ""
        if not any(marker in title for marker in _CHALLENGE_MARKERS):
            body_text = ""
            try:
                body = page.locator("body")
                if body.count():
                    body_text = body.inner_text(timeout=1500).lower()[:600]
            except Exception:  # noqa: BLE001
                body_text = ""
            if not any(marker in body_text for marker in _CHALLENGE_MARKERS):
                return
        page.wait_for_timeout(1000)
        waited += 1000


def _pdf_text_via_browser(context: Any, response: Any, final_url: str) -> str | None:
    """When the browser lands on a PDF (e.g. an air-district rule PDF behind a JS
    bot-challenge), the rendered page body is empty — pull the PDF bytes through the
    browser's own request context (reusing its cleared-challenge cookies) and extract
    the text. Returns None when the target is not a PDF or extraction is not possible."""
    content_type = ""
    try:
        headers = getattr(response, "headers", None) or {}
        content_type = (headers.get("content-type") or "").lower()
    except Exception:  # noqa: BLE001 — header shape varies; fall back to URL sniffing
        content_type = ""
    path = final_url.lower().split("?", 1)[0]
    if "pdf" not in content_type and not path.endswith(".pdf"):
        return None
    try:
        api_response = context.request.get(final_url)
        data = api_response.body()
    except Exception:  # noqa: BLE001 — best-effort; caller falls back to rendered text
        return None
    return _extract_pdf_text(data)


def browser_use(policy: SandboxPolicy, url: str, *, wait_until: str = "domcontentloaded") -> dict[str, Any]:
    if not isinstance(url, str):
        return _invalid_argument("url", "a string", url)
    if not policy.allow_browser:
        return _error("blocked", "browser_disabled", "Browser access is disabled by sandbox policy.", url=url)
    if not host_fetchable(url):
        return _error("blocked", "host_not_fetchable", "URL is not a fetchable public host (SSRF guard).", url=url)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _error("unavailable", "dependency_missing", "playwright is not installed.", dependency="playwright")

    try:
        with sync_playwright() as playwright:
            # --disable-blink-features=AutomationControlled drops the automation flag Cloudflare
            # fingerprints; a real UA + headers + the webdriver mask below let the JS challenge
            # actually run and clear instead of being hard-blocked.
            browser = playwright.chromium.launch(
                headless=True, args=["--disable-blink-features=AutomationControlled"]
            )
            context = None
            try:
                blocked_requests: list[dict[str, Any]] = []

                def guard_route(route: Any, request: Any) -> None:
                    request_url = getattr(request, "url", "")
                    if host_fetchable(request_url):
                        route.continue_()
                        return
                    blocked_requests.append(
                        {
                            "url": request_url,
                            "resource_type": getattr(request, "resource_type", None),
                        }
                    )
                    route.abort()

                context = browser.new_context(
                    service_workers="block",
                    user_agent=BROWSER_USER_AGENT,
                    locale="en-US",
                    viewport={"width": 1280, "height": 800},
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                )
                # Hide the headless automation tell so Cloudflare serves the JS challenge
                # (which we then wait out) rather than a hard 403.
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )
                context.route("**/*", guard_route)
                page = context.new_page()

                # PDF URLs trigger a chromium DOWNLOAD (page.goto raises "Download is
                # starting"), so never navigate to one. Instead prime the Cloudflare
                # clearance by loading the site origin in the page, then pull the PDF bytes
                # through the browser's request context (which now carries the clearance
                # cookies). This is the path that lets us read agency rule PDFs behind a WAF.
                if url.lower().split("?", 1)[0].endswith(".pdf"):
                    timeout_ms = int(policy.timeout_seconds * 1000)
                    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
                    try:
                        page.goto(origin, wait_until="domcontentloaded", timeout=timeout_ms)
                        _wait_out_challenge(page, policy.timeout_seconds)
                    except Exception:  # noqa: BLE001 — origin may not render; still try the fetch
                        pass
                    if blocked_requests:
                        return _error(
                            "blocked", "resource_blocked",
                            "Browser blocked a request outside sandbox policy.",
                            url=url, blocked_url=blocked_requests[0]["url"], blocked_requests=blocked_requests,
                        )
                    try:
                        api = context.request.get(url)
                        data = api.body()
                        status = getattr(api, "status", None)
                    except Exception as exc:  # noqa: BLE001
                        return _exception_error("browser_failed", exc, url=url)
                    text = _extract_pdf_text(data)
                    if not text:
                        return _error(
                            "blocked", "pdf_fetch_failed",
                            f"Browser retrieved the PDF URL but no readable text (status {status}).",
                            url=url, status_code=status,
                        )
                    return _success("navigated", snapshot={
                        "url": url, "title": "", "text": _cap_text(text),
                        "status_code": status, "content_type": "application/pdf",
                    })

                try:
                    response = page.goto(url, wait_until=wait_until, timeout=int(policy.timeout_seconds * 1000))
                except Exception:
                    if blocked_requests:
                        return _error(
                            "blocked",
                            "resource_blocked",
                            "Browser blocked a request outside sandbox policy.",
                            url=url,
                            blocked_url=blocked_requests[0]["url"],
                            blocked_requests=blocked_requests,
                        )
                    raise
                if blocked_requests:
                    return _error(
                        "blocked",
                        "resource_blocked",
                        "Browser blocked a request outside sandbox policy.",
                        url=url,
                        blocked_url=blocked_requests[0]["url"],
                        blocked_requests=blocked_requests,
                    )
                final_url = page.url
                if not host_fetchable(final_url):
                    return _error(
                        "blocked",
                        "redirect_blocked",
                        "Browser navigation reached a host outside sandbox policy.",
                        url=url,
                        final_url=final_url,
                    )
                # Let any Cloudflare/JS challenge resolve (sets the clearance cookie) before
                # we read the page or pull the PDF bytes via the cleared request context.
                _wait_out_challenge(page, policy.timeout_seconds)
                pdf_text = _pdf_text_via_browser(context, response, final_url)
                if pdf_text:
                    snapshot = {
                        "url": final_url,
                        "title": page.title(),
                        "text": pdf_text,
                        "status_code": response.status if response is not None else None,
                        "content_type": "application/pdf",
                    }
                else:
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
