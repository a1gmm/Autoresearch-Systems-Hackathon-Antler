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


def _extract_main_text(html: str) -> str:
    """Extract the main readable content from an HTML page: strip nav/chrome, prefer
    <main>/<article>, fall back to the full de-chromed page. Live gov rules/guidance
    are HTML, so handing the agent the raw page (tags, scripts, menus) buries the
    requirement text. Graceful no-op (returns input) if BeautifulSoup is unavailable."""
    try:
        import re

        from bs4 import BeautifulSoup
    except ImportError:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "button"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"})
    text = main.get_text("\n", strip=True) if main else ""
    if len(text) < 400:
        text = (soup.body or soup).get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)


# Exact unit constants for VOC/ROC threshold math (NIST): 1 lb = 453.59237 g,
# 1 US gallon = 3.785411784 L, so 1 lb/gal = 119.826427 g/L.
_G_PER_LB = 453.59237
_L_PER_GAL = 3.785411784
_G_PER_L_PER_LB_PER_GAL = _G_PER_LB / _L_PER_GAL  # 119.826427...

# Mass-per-volume units (VOC concentration OR material density) -> lb/gal multiplier.
_MASS_PER_VOLUME_TO_LB_PER_GAL = {
    "lb/gal": 1.0,
    "lbs/gal": 1.0,
    "lb/gallon": 1.0,
    "g/l": 1.0 / _G_PER_L_PER_LB_PER_GAL,
    "mg/l": 0.001 / _G_PER_L_PER_LB_PER_GAL,
    "kg/l": 1000.0 / _G_PER_L_PER_LB_PER_GAL,
    "g/ml": 1000.0 / _G_PER_L_PER_LB_PER_GAL,
    "g/cm3": 1000.0 / _G_PER_L_PER_LB_PER_GAL,
    "g/cc": 1000.0 / _G_PER_L_PER_LB_PER_GAL,
}
_FRACTION_UNITS = {"weight_fraction": 1.0, "mass_fraction": 1.0, "fraction": 1.0}
_PERCENT_UNITS = {"weight_percent": 0.01, "wt%": 0.01, "wt %": 0.01, "percent": 0.01, "%": 0.01}
_GALLON_UNITS = {"gal", "gallon", "gallons", "us_gal"}
_LITER_UNITS = {"l", "liter", "liters", "litre", "litres"}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def compute_voc_threshold(
    *,
    voc_content: float,
    voc_content_unit: str = "weight_percent",
    density: float | None = None,
    density_unit: str = "lb/gal",
    mass_limit_lb: float | None = None,
    usage: float | None = None,
    usage_unit: str = "gal",
    control_efficiency: float = 0.0,
) -> dict[str, Any]:
    """Deterministic VOC/ROC permit-threshold calculator. Two uses, both off the same
    physics (VOC mass per volume of material = content x density):

      * Mass limit -> usage limit: a rule caps VOC/ROC mass per period (e.g. VCAPCD
        Rule 23 exempts graphic arts < 200 lb ROC / 12 months). Given the material's
        VOC content and density, returns the equivalent material-usage limit in gallons
        (and liters) -- the actionable number the ALG memo computes (~29 gal/yr).
      * Usage -> emissions: given how much material is used, returns the VOC/ROC mass
        emitted (optionally after a capture/control efficiency), to compare to a limit.

    VOC content may be a weight fraction/percent (then `density` is required) or a
    concentration already expressed as mass/volume (g/L, lb/gal, ...). Pure math: no
    network or filesystem; the verifier still gates the rule limit's source."""
    if not _is_number(voc_content):
        return _invalid_argument("voc_content", "a number", voc_content)
    if not _is_number(control_efficiency):
        return _invalid_argument("control_efficiency", "a number between 0 and 1", control_efficiency)
    if control_efficiency < 0 or control_efficiency > 1:
        return _error("error", "invalid_argument", "control_efficiency must be between 0 and 1.", argument="control_efficiency")

    formula: list[str] = []
    unit = str(voc_content_unit).strip().lower()
    if unit in _MASS_PER_VOLUME_TO_LB_PER_GAL:
        voc_lb_per_gal = voc_content * _MASS_PER_VOLUME_TO_LB_PER_GAL[unit]
        formula.append(f"VOC concentration {voc_content} {voc_content_unit} = {voc_lb_per_gal:.4g} lb VOC/gal")
    elif unit in _FRACTION_UNITS or unit in _PERCENT_UNITS:
        scale = _FRACTION_UNITS.get(unit, _PERCENT_UNITS.get(unit, 1.0))
        fraction = voc_content * scale
        if not _is_number(density):
            return _error(
                "error",
                "density_required",
                "A material density is required to convert a weight fraction/percent to VOC mass per volume.",
                argument="density",
            )
        dunit = str(density_unit).strip().lower()
        if dunit not in _MASS_PER_VOLUME_TO_LB_PER_GAL:
            return _error("error", "unknown_unit", f"Unknown density unit: {density_unit!r}.", argument="density_unit")
        density_lb_per_gal = density * _MASS_PER_VOLUME_TO_LB_PER_GAL[dunit]
        voc_lb_per_gal = fraction * density_lb_per_gal
        formula.append(
            f"VOC mass/vol = {fraction:g} (fraction) x {density_lb_per_gal:.4g} lb/gal density = {voc_lb_per_gal:.4g} lb VOC/gal"
        )
    else:
        return _error("error", "unknown_unit", f"Unknown voc_content_unit: {voc_content_unit!r}.", argument="voc_content_unit")

    if voc_lb_per_gal <= 0:
        return _error("error", "invalid_argument", "Computed VOC mass per volume must be positive.", argument="voc_content")

    control_factor = 1.0 - control_efficiency
    effective = voc_lb_per_gal * control_factor

    result: dict[str, Any] = {
        "voc_mass_per_volume": {
            "lb_per_gal": round(voc_lb_per_gal, 4),
            "g_per_l": round(voc_lb_per_gal * _G_PER_L_PER_LB_PER_GAL, 2),
        },
        "control_efficiency": control_efficiency,
        "effective_voc_lb_per_gal": round(effective, 4),
        "inputs": {
            "voc_content": voc_content,
            "voc_content_unit": voc_content_unit,
            "density": density,
            "density_unit": density_unit if density is not None else None,
            "mass_limit_lb": mass_limit_lb,
            "usage": usage,
            "usage_unit": usage_unit if usage is not None else None,
        },
    }

    if mass_limit_lb is not None:
        if not _is_number(mass_limit_lb) or mass_limit_lb <= 0:
            return _invalid_argument("mass_limit_lb", "a positive number", mass_limit_lb)
        usage_limit_gal = mass_limit_lb / effective
        result["usage_limit"] = {
            "gal": round(usage_limit_gal, 2),
            "l": round(usage_limit_gal * _L_PER_GAL, 2),
        }
        ctl = f" x (1 - {control_efficiency} control)" if control_efficiency else ""
        formula.append(
            f"usage_limit = {mass_limit_lb} lb / ({voc_lb_per_gal:.4g} lb/gal{ctl}) = {usage_limit_gal:.2f} gal per period"
        )

    if usage is not None:
        if not _is_number(usage) or usage < 0:
            return _invalid_argument("usage", "a non-negative number", usage)
        uunit = str(usage_unit).strip().lower()
        if uunit in _GALLON_UNITS:
            usage_gal = float(usage)
        elif uunit in _LITER_UNITS:
            usage_gal = usage / _L_PER_GAL
        else:
            return _error("error", "unknown_unit", f"Unknown usage_unit: {usage_unit!r}.", argument="usage_unit")
        emissions_lb = usage_gal * effective
        result["emissions"] = {
            "lb": round(emissions_lb, 2),
            "usage_gal": round(usage_gal, 4),
        }
        ctl = f" x (1 - {control_efficiency} control)" if control_efficiency else ""
        formula.append(
            f"emissions = {usage_gal:.4g} gal x {voc_lb_per_gal:.4g} lb/gal{ctl} = {emissions_lb:.2f} lb VOC/ROC"
        )

    result["formula"] = formula
    return _success("computed", **result)


def _extract_pdf_text(data: bytes) -> str | None:
    """Extract text from in-memory PDF bytes (a PDF fetched over HTTP, e.g. an ARB or
    air-district rule PDF). web_fetch otherwise hands the agent decoded PDF bytes as
    'text' — unreadable garbage — so the agent can never quote the rule. Returns the
    joined page text, or None if PyMuPDF is unavailable or the bytes are not a parseable
    PDF (caller then treats the response as non-PDF)."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        return None
    try:
        import fitz
    except ImportError:
        return None
    try:
        with fitz.open(stream=bytes(data), filetype="pdf") as document:
            text = "\n".join(page.get_text("text") for page in document)
        return text or None
    except Exception:  # noqa: BLE001 — not a parseable PDF; let caller fall back
        return None


_BOT_BLOCK_STATUS = {403, 429, 503}
_BOT_BLOCK_BODY_MARKERS = (
    "just a moment",
    "cf-browser-verification",
    "challenge-platform",
    "attention required",
    "enable javascript and cookies",
    "_cf_chl",
)


def _looks_bot_blocked(response: Any) -> bool:
    """A plain HTTP client (httpx, no JS) often gets bounced by bot protection
    (Cloudflare's 'Just a moment…' interstitial) on legitimate agency sites like
    vcapcd.org. Detect that so web_fetch can retry through a real browser, which runs
    the JS challenge. Conservative: only non-success statuses with a Cloudflare/challenge
    signature, so ordinary 403/404s do not trigger a (slow) browser fallback."""
    if getattr(response, "status_code", None) not in _BOT_BLOCK_STATUS:
        return False
    headers = {str(k).lower(): str(v).lower() for k, v in dict(getattr(response, "headers", {})).items()}
    if "cf-ray" in headers or "cf-mitigated" in headers or "cloudflare" in headers.get("server", ""):
        return True
    try:
        body = (response.text or "")[:4000].lower()
    except Exception:  # noqa: BLE001 — binary/undecodable body is not a challenge page
        return False
    return any(marker in body for marker in _BOT_BLOCK_BODY_MARKERS)


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


def host_fetchable(url: str) -> bool:
    """The sandbox NETWORK boundary (a safety gate, not a content allowlist):
    allow any public http(s) host so the subagent can do broad, durable research,
    but block SSRF-dangerous targets (localhost, private/loopback/link-local nets,
    cloud metadata). Authority of a source is judged downstream by the verifier
    (authority_rank), not by restricting which official sites may be read."""
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = _normalize_host(parsed.hostname)
    if not host:
        return False
    if host == "localhost" or host.endswith((".localhost", ".internal", ".local")):
        return False
    try:
        import ipaddress

        ip = ipaddress.ip_address(host)
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    except ValueError:
        pass  # a hostname, not a raw IP -> allowed
    return True


_CA_AUTHORITY_HOSTS: frozenset[str] | None = None


def _ca_authority_hosts() -> frozenset[str]:
    """The hostnames of California EHS authorities the system already knows about
    (the jurisdiction registry's air districts — VCAPCD, BAAQMD, SJVAPCD, etc.).
    These live on mixed TLDs (.org/.us/.net/.com, not just .gov), so the verifier's
    authority tier must recognize them rather than assume government TLDs. Lazily
    derived from the single source of truth (jurisdiction_registry); cached."""
    global _CA_AUTHORITY_HOSTS
    if _CA_AUTHORITY_HOSTS is None:
        hosts: set[str] = set(DEFAULT_ALLOWED_HOSTS)
        try:
            from research_core.jurisdiction_registry import AIR_DISTRICTS

            for district in AIR_DISTRICTS:
                host = _normalize_host(urlparse(district.website).hostname)
                if host:
                    hosts.add(host[4:] if host.startswith("www.") else host)
        except Exception:  # noqa: BLE001 — never let registry import break authority ranking
            pass
        _CA_AUTHORITY_HOSTS = frozenset(hosts)
    return _CA_AUTHORITY_HOSTS


def _host_in(host: str, allowed: frozenset[str] | tuple[str, ...]) -> bool:
    return any(host == a or host.endswith("." + a) for a in allowed)


def source_authority_rank(url: str, allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS) -> int:
    """Authority tier for a fetched source, consumed by the verifier's authority
    gate (which requires rank <= 2):
      1 = a known EHS authority — curated allowlist OR a jurisdiction-registry
          authority host (air districts, incl. .org/.us/.net like vcapcd.org)
      2 = other government / official source (*.gov, *.mil)
      3 = other public source -> fails the verifier's authority gate (fail-closed)."""
    host = _normalize_host(urlparse(url).hostname)
    if not host:
        return 3
    if host_allowed(url, allowed_hosts) or _host_in(host, _ca_authority_hosts()):
        return 1
    # Suffix-only (never a substring): a spoof like aqmd.gov.evil.example must NOT
    # be treated as government — it ends in .example, so it stays rank 3.
    if host == "gov" or host == "mil" or host.endswith((".gov", ".mil")):
        return 2
    return 3


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
        if not host_fetchable(next_url):
            return (
                None,
                _error(
                    "blocked",
                    "redirect_blocked",
                    "Redirect target is not a fetchable public host (SSRF guard).",
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


def _browser_fallback(
    policy: SandboxPolicy,
    url: str,
    *,
    redirect_chain: list[dict[str, Any]],
    original_url: str,
) -> dict[str, Any] | None:
    """Re-fetch a bot-blocked URL through the headless browser (runs JS, clears the
    Cloudflare challenge). Returns a web_fetch-shaped success on success, or None so the
    caller falls through to its normal http_error response."""
    try:
        result = browser_use(policy, url)
    except Exception:  # noqa: BLE001 — browser is best-effort; fall through on any error
        return None
    if not isinstance(result, dict) or not result.get("ok"):
        return None
    snapshot = result.get("snapshot") or {}
    return _success(
        "fetched",
        url=original_url,
        final_url=snapshot.get("url", url),
        status_code=snapshot.get("status_code"),
        content_type=snapshot.get("content_type", "text/html"),
        text=snapshot.get("text", ""),
        via="browser_fallback",
        redirect_chain=redirect_chain,
    )


def web_fetch(policy: SandboxPolicy, url: str) -> dict[str, Any]:
    if not isinstance(url, str):
        return _invalid_argument("url", "a string", url)
    if not policy.allow_network:
        return _error("blocked", "network_disabled", "Network access is disabled by sandbox policy.", url=url)
    # Open content gate: fetch any public source for durable research; only block
    # SSRF-dangerous targets. Source AUTHORITY is judged by the verifier, not here.
    if not host_fetchable(url):
        return _error("blocked", "host_not_fetchable", "URL is not a fetchable public host (SSRF guard).", url=url)

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
        if not host_fetchable(final_url):
            return _error(
                "blocked",
                "redirect_blocked",
                "Fetch redirected to a non-fetchable public host (SSRF guard).",
                url=url,
                final_url=final_url,
            )
        content_type = response.headers.get("content-type")
        ctype = (content_type or "").lower()

        # Bot-protection (Cloudflare interstitial) blocks the plain HTTP client on
        # legitimate agency sites. Retry through a real browser, which runs the JS
        # challenge, before giving up. (Only when the policy allows the browser.)
        if not response.is_success and policy.allow_browser and _looks_bot_blocked(response):
            fallback = _browser_fallback(policy, final_url, redirect_chain=redirect_chain, original_url=url)
            if fallback is not None:
                return fallback

        # PDF served over HTTP: extract the rule text so the agent can quote it. Detect
        # by content-type or the %PDF magic bytes (agency PDFs are often served as
        # application/octet-stream). Falls through to text handling if not parseable.
        body_bytes = response.content if response.is_success else b""
        is_pdf = ("pdf" in ctype) or (body_bytes[:5].startswith(b"%PDF"))
        if is_pdf and body_bytes:
            extracted = _extract_pdf_text(body_bytes)
            if extracted is not None:
                return _success(
                    "fetched",
                    url=url,
                    final_url=final_url,
                    status_code=response.status_code,
                    content_type=content_type or "application/pdf",
                    text=extracted,
                    extracted_format="pdf",
                    headers=dict(response.headers),
                    redirect_chain=redirect_chain,
                )

        raw = response.text if response.is_success else ""
        # Extract readable main content for HTML so the agent reads the rule, not the
        # nav/chrome. Non-HTML (JSON, plain) passes through unchanged.
        is_html = "html" in ctype or (raw[:512].lstrip().lower().startswith(("<!doctype html", "<html")))
        text = _extract_main_text(raw) if (is_html and raw) else raw
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


def _openai_web_search(query: str, *, limit: int = 5) -> dict[str, Any]:
    """Real open web discovery via the OpenAI Responses API web_search tool. Returns
    broad results (title/url/snippet) with no host restriction — the agent chooses the
    authoritative source and the verifier gates it. Fails closed to 'unavailable' when
    openai or the API key are absent."""
    import os

    try:
        from openai import OpenAI
    except ImportError:
        return _error("unavailable", "search_dependency_missing", "openai is not installed.", query=query)
    if not os.environ.get("OPENAI_API_KEY"):
        return _error("unavailable", "search_provider_unavailable", "No OPENAI_API_KEY configured for web search.", query=query)

    model = os.environ.get("RESEARCH_CORE_AGENT_MODEL") or "gpt-5.5"
    instruction = (
        "Find official primary sources that answer this California EHS permit question. "
        "Prefer government/authority sites. Question: " + query
    )
    resp = None
    client = OpenAI(timeout=45.0, max_retries=1)
    for tool_type in ("web_search", "web_search_preview"):
        try:
            resp = client.responses.create(model=model, tools=[{"type": tool_type}], input=instruction)
            break
        except Exception:  # noqa: BLE001 — try the other tool name, else report unavailable
            resp = None
    if resp is None:
        return _error("unavailable", "search_failed", "Web search call failed.", query=query)

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in (getattr(resp, "output", None) or []):
        for content in (getattr(item, "content", None) or []):
            for ann in (getattr(content, "annotations", None) or []):
                url = getattr(ann, "url", None)
                if not url or url in seen or not host_fetchable(url):
                    continue
                seen.add(url)
                results.append({
                    "url": url,
                    "title": getattr(ann, "title", "") or "",
                    "authority_rank": source_authority_rank(url),
                })
                if len(results) >= max(1, limit):
                    break
    return _success("searched", query=query, results=results)


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
        # No configured proxy -> do REAL open web discovery via the OpenAI Responses
        # API web_search tool (uses the model's own search; the agent then fetches the
        # best official result and the verifier gates authority). Returns "unavailable"
        # if openai/key are absent (e.g. offline tests).
        return _openai_web_search(query, limit=limit)
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
            elif not host_fetchable(trimmed):
                # Only block SSRF-dangerous sources here. Whether a public source is
                # AUTHORITATIVE is the verifier's job (authority_rank), not this gate —
                # otherwise the agent can't even cite the correct rule (e.g. vcapcd.org).
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
