from __future__ import annotations

import sys
from types import ModuleType
from pathlib import Path

from research_core.browser import browser_use
from research_core.documents import read_docx, read_pdf, read_spreadsheet
from research_core.tools import (
    SandboxPolicy,
    host_allowed,
    submit_finding,
    web_fetch,
    web_search,
    write_artifact,
)


def test_host_allowed_rejects_lookalike_domain():
    assert host_allowed("https://www.aqmd.gov/docs/rule.pdf") is True
    assert host_allowed("https://aqmd.gov.evil.example/docs/rule.pdf") is False


def test_host_allowed_accepts_allowed_host_suffixes():
    assert host_allowed("https://permits.scaqmd.gov/rules") is True
    assert host_allowed("https://www.arb.ca.gov/forms") is True
    assert host_allowed("https://example.com/aqmd.gov/rule") is False


def test_write_artifact_stays_inside_run_workspace(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)
    result = write_artifact(policy, "sources/rule.txt", "rule text")

    assert result["ok"] is True
    assert result["status"] == "written"
    path = Path(result["path"])
    assert path.read_text() == "rule text"
    assert tmp_path / "run_1" in path.parents
    assert result["workspace"] == str(tmp_path / "run_1")
    assert result["bytes_written"] == len("rule text")


def test_write_artifact_rejects_traversal(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = write_artifact(policy, "../outside.txt", "nope")

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "path_traversal"
    assert not (tmp_path / "outside.txt").exists()


def test_web_fetch_blocks_ssrf_but_authority_gate_catches_spoofs(tmp_path: Path):
    from research_core.tools import source_authority_rank

    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    # The content gate is open for durable research, but SSRF targets are blocked.
    result = web_fetch(policy, "http://169.254.169.254/latest/meta-data")
    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "host_not_fetchable"

    # A spoofed authority host is fetchable (public), but the verifier catches it via
    # authority_rank: a non-curated, non-.gov host is rank 3 (fails the rank<=2 gate).
    assert source_authority_rank("https://aqmd.gov.evil.example/docs/rule.pdf") == 3


def test_web_fetch_blocks_disallowed_redirect_before_fetching_it(tmp_path: Path, monkeypatch):
    requested_urls = []

    class FakeResponse:
        def __init__(self, url: str, status_code: int, location: str | None = None):
            self.url = url
            self.status_code = status_code
            self.headers = {"location": location} if location else {}
            self.text = ""

        @property
        def is_success(self):
            return 200 <= self.status_code < 300

    class FakeClient:
        def __init__(self, *, follow_redirects: bool, timeout: float):
            assert follow_redirects is False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def get(self, url: str, **kwargs):
            requested_urls.append(url)
            if url == "https://www.aqmd.gov/start":
                return FakeResponse(url, 302, "http://169.254.169.254/payload")
            raise AssertionError(f"Unexpected request to {url}")

    fake_httpx = ModuleType("httpx")
    fake_httpx.Client = FakeClient
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = web_fetch(policy, "https://www.aqmd.gov/start")

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "redirect_blocked"
    assert result["blocked_url"] == "http://169.254.169.254/payload"
    assert requested_urls == ["https://www.aqmd.gov/start"]


def test_web_search_returns_unavailable_without_optional_dependency(tmp_path: Path, monkeypatch):
    # Deterministic: no configured proxy AND no usable OpenAI fallback -> unavailable.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "openai", None)  # force ImportError in the fallback
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = web_search(policy, "coating rules")

    assert result["ok"] is False
    assert result["status"] in {"unavailable", "error"}
    assert "error" in result


def test_web_search_blocks_disallowed_configured_endpoint(tmp_path: Path):
    policy = SandboxPolicy(
        run_id="run_1",
        artifact_root=tmp_path,
        search_endpoint="https://aqmd.gov.evil.example/search",
    )

    result = web_search(policy, "coating rules")

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "host_not_allowed"


def test_web_search_rejects_non_string_query(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = web_search(policy, None)

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_argument"


def test_document_readers_return_structured_missing_file_errors(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    for reader in (read_pdf, read_docx, read_spreadsheet):
        result = reader(policy, "missing.pdf")
        assert result["ok"] is False
        assert result["status"] == "error"
        assert result["error"]["code"] == "file_not_found"


def test_document_readers_reject_absolute_paths(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = read_pdf(policy, tmp_path / "run_1" / "missing.pdf")

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "path_traversal"


def test_document_readers_reject_traversal(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = read_docx(policy, "../outside.docx")

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "path_traversal"


def test_document_readers_reject_symlink_escape(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)
    workspace = tmp_path / "run_1"
    workspace.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("a,b\n")
    (workspace / "escape.csv").symlink_to(outside)

    result = read_spreadsheet(policy, "escape.csv")

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "path_traversal"


def test_document_readers_reject_invalid_path_type(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = read_pdf(policy, 123)

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_argument"


def test_browser_use_blocks_ssrf_targets(tmp_path: Path):
    # Open content gate (any public page), but SSRF targets are still blocked.
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = browser_use(policy, "http://169.254.169.254/latest/meta-data")

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "host_not_fetchable"


def test_browser_use_installs_context_route_before_page_and_blocks_popup_request(tmp_path: Path, monkeypatch):
    actions = []

    class FakeRequest:
        def __init__(self, url: str):
            self.url = url
            self.resource_type = "document"

    class FakeRoute:
        def __init__(self, url: str):
            self.url = url

        def continue_(self):
            actions.append(("continue", self.url))

        def abort(self):
            actions.append(("abort", self.url))

    class FakeLocator:
        def count(self):
            return 1

        def inner_text(self, *, timeout: int):
            return "ok"

    class FakePage:
        url = "https://www.aqmd.gov/start"

        def goto(self, url: str, *, wait_until: str, timeout: int):
            actions.append(("goto", url))
            route_indices = [index for index, action in enumerate(actions) if action[0] == "context_route"]
            page_indices = [index for index, action in enumerate(actions) if action[0] == "new_page"]
            assert route_indices and page_indices and route_indices[0] < page_indices[0]
            self.context_handler(FakeRoute(url), FakeRequest(url))
            self.context_handler(
                FakeRoute("http://169.254.169.254/popup"),
                FakeRequest("http://169.254.169.254/popup"),
            )
            return type("Response", (), {"status": 200})()

        def title(self):
            return "title"

        def locator(self, selector: str):
            return FakeLocator()

    class FakeBrowserContext:
        def __init__(self):
            self.handler = None

        def route(self, pattern: str, handler):
            actions.append(("context_route", pattern))
            self.handler = handler

        def new_page(self):
            actions.append(("new_page", None))
            assert self.handler is not None
            page = FakePage()
            page.context_handler = self.handler
            return page

        def close(self):
            actions.append(("context_close", None))

    class FakeBrowser:
        def new_context(self, *, service_workers: str):
            actions.append(("new_context", service_workers))
            return FakeBrowserContext()

        def new_page(self):
            raise AssertionError("browser_use must create pages from the routed browser context")

        def close(self):
            actions.append(("browser_close", None))

    class FakeChromium:
        def launch(self, *, headless: bool):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeContext:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, traceback):
            return False

    fake_sync_api = ModuleType("playwright.sync_api")
    fake_sync_api.sync_playwright = lambda: FakeContext()
    monkeypatch.setitem(sys.modules, "playwright", ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = browser_use(policy, "https://www.aqmd.gov/start")

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "resource_blocked"
    assert ("new_context", "block") in actions
    assert ("abort", "http://169.254.169.254/popup") in actions
    assert ("context_close", None) in actions
    assert ("browser_close", None) in actions


def test_submit_finding_shape(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = submit_finding(
        policy,
        title="Rule 1113 applies",
        summary="VOC limits may apply to coatings.",
        sources=["https://www.aqmd.gov/docs/rule.pdf"],
        confidence=0.82,
        metadata={"family": "air"},
    )

    assert result["ok"] is True
    assert result["status"] == "submitted"
    assert result["finding"]["title"] == "Rule 1113 applies"
    assert result["finding"]["confidence"] == 0.82
    assert result["finding"]["sources"] == ["https://www.aqmd.gov/docs/rule.pdf"]


def test_submit_finding_rejects_non_string_title(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = submit_finding(
        policy,
        title=None,
        summary="x",
        sources=[],
        confidence=0.5,
    )

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_argument"


def test_submit_finding_rejects_non_list_sources(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = submit_finding(
        policy,
        title="x",
        summary="x",
        sources=None,
        confidence=0.5,
    )

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_argument"


def test_submit_finding_rejects_non_numeric_confidence(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = submit_finding(
        policy,
        title="x",
        summary="x",
        sources=[],
        confidence="high",
    )

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_argument"


def test_submit_finding_blocks_ssrf_source(tmp_path: Path):
    # submit_finding only blocks SSRF-dangerous sources; authority is the verifier's job.
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = submit_finding(
        policy,
        title="Bad source",
        summary="Should be blocked.",
        sources=["HTTP://169.254.169.254/rule.pdf"],
        confidence=0.5,
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] in {"host_not_allowed", "host_not_fetchable"}


def test_submit_finding_accepts_public_source_but_verifier_catches_spoof(tmp_path: Path):
    # A lookalike host is FETCHABLE (public) so submit_finding accepts it, but the
    # verifier catches it: source_authority_rank is 3 (fails the rank<=2 gate).
    from research_core.tools import source_authority_rank

    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)
    result = submit_finding(
        policy,
        title="Lookalike source",
        summary="Cited from a spoofed authority host.",
        sources=["  https://aqmd.gov.evil.example/rule.pdf"],
        confidence=0.5,
    )
    assert result["ok"] is True  # not blocked by the source gate
    assert source_authority_rank("https://aqmd.gov.evil.example/rule.pdf") == 3  # verifier rejects


def test_submit_finding_rejects_malformed_http_source(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = submit_finding(
        policy,
        title="Malformed source",
        summary="Should be blocked.",
        sources=["https:///aqmd.gov/rule.pdf"],
        confidence=0.5,
    )

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "source_url_invalid"


def test_submit_finding_rejects_protocol_relative_lookalike_source(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = submit_finding(
        policy,
        title="Protocol relative source",
        summary="Should be blocked.",
        sources=["//aqmd.gov.evil.example/path"],
        confidence=0.5,
    )

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "source_url_invalid"


def test_submit_finding_rejects_protocol_relative_allowed_source(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = submit_finding(
        policy,
        title="Protocol relative source",
        summary="Should be blocked.",
        sources=["//www.aqmd.gov/path"],
        confidence=0.5,
    )

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "source_url_invalid"


def test_web_fetch_extracts_main_content_from_html():
    from research_core.tools import _extract_main_text
    html = (
        "<html><head><script>junk()</script><style>x{}</style></head>"
        "<body><nav>MENU HOME ABOUT CONTACT</nav>"
        "<main><h1>Rule 201</h1><p>A permit to construct is required before installation of emitting equipment.</p></main>"
        "<footer>copyright 2026</footer></body></html>"
    )
    text = _extract_main_text(html)
    assert "A permit to construct is required" in text
    assert "MENU HOME ABOUT" not in text   # nav chrome stripped
    assert "junk()" not in text            # script stripped


def test_host_fetchable_allows_public_blocks_ssrf():
    from research_core.tools import host_fetchable
    # Public hosts (gov AND non-gov) are fetchable — content gate is open.
    assert host_fetchable("https://www.aqmd.gov/x")
    assert host_fetchable("https://www.sandiegocounty.gov/x")
    assert host_fetchable("https://example.com/x")
    # SSRF-dangerous targets are blocked.
    assert not host_fetchable("http://localhost/x")
    assert not host_fetchable("http://127.0.0.1/x")
    assert not host_fetchable("http://169.254.169.254/latest/meta-data")  # cloud metadata
    assert not host_fetchable("http://10.0.0.5/x")
    assert not host_fetchable("ftp://aqmd.gov/x")  # non-http scheme


def test_source_authority_rank_tiers():
    from research_core.tools import source_authority_rank
    assert source_authority_rank("https://www.aqmd.gov/x") == 1        # curated allowlist
    assert source_authority_rank("https://www.sandiegocounty.gov/x") == 2  # other gov
    assert source_authority_rank("https://example.com/x") == 3         # other -> fails verifier


def test_openai_web_search_filters_and_ranks_results(monkeypatch):
    from types import ModuleType, SimpleNamespace
    from research_core.tools import web_search

    # Fake OpenAI Responses API returning url-citation annotations (one public gov,
    # one SSRF target that must be dropped).
    ann_ok = SimpleNamespace(url="https://www.aqmd.gov/rule-201.pdf", title="Rule 201")
    ann_bad = SimpleNamespace(url="http://169.254.169.254/meta", title="metadata")
    content = SimpleNamespace(annotations=[ann_ok, ann_bad])
    item = SimpleNamespace(content=[content])
    resp = SimpleNamespace(output=[item])

    class FakeResponses:
        def create(self, **kwargs):
            return resp

    class FakeOpenAI:
        def __init__(self, *a, **k):
            self.responses = FakeResponses()

    fake = ModuleType("openai")
    fake.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    policy = SandboxPolicy(run_id="run_1", artifact_root=Path("/tmp"))  # no search_endpoint -> real path
    result = web_search(policy, "SCAQMD permit to construct spray booth")
    assert result["ok"] is True
    urls = [r["url"] for r in result["results"]]
    assert "https://www.aqmd.gov/rule-201.pdf" in urls
    assert "http://169.254.169.254/meta" not in urls  # SSRF dropped
    assert result["results"][0]["authority_rank"] == 1  # curated authority


def test_ca_air_district_hosts_are_authoritative():
    # The E2E gap: the agent found VCAPCD Rule 23 (vcapcd.org) but it was rejected.
    # Air districts live on mixed TLDs; the verifier's authority tier must recognize
    # the jurisdiction registry's authorities as rank 1 (not penalize .org).
    from research_core.tools import source_authority_rank, host_fetchable
    assert source_authority_rank("https://www.vcapcd.org/wp-content/uploads/Rulebook/Reg2/RULE%2023.pdf") == 1
    assert source_authority_rank("https://www.baaqmd.gov/rules") == 1
    assert source_authority_rank("https://www.valleyair.org/rules") == 1
    assert host_fetchable("https://www.vcapcd.org/x")  # and it's fetchable


# --- PDF-over-HTTP extraction + Cloudflare browser fallback --------------------

def _make_pdf_bytes(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_extract_pdf_text_reads_real_pdf_bytes():
    from research_core.tools import _extract_pdf_text

    data = _make_pdf_bytes("RULE 23 EXEMPTION THRESHOLD")
    extracted = _extract_pdf_text(data)
    assert extracted is not None
    assert "RULE 23 EXEMPTION THRESHOLD" in extracted


def test_extract_pdf_text_returns_none_on_garbage():
    from research_core.tools import _extract_pdf_text

    assert _extract_pdf_text(b"not a pdf at all") is None


class _PdfResponse:
    def __init__(self, url: str, content: bytes, content_type: str):
        self.url = url
        self.status_code = 200
        self.content = content
        self.headers = {"content-type": content_type}

    @property
    def is_success(self):
        return True

    @property
    def text(self):
        # Mimic httpx: decoding PDF bytes yields garbage, never the rule text.
        return self.content.decode("latin-1", errors="replace")


def _install_fake_httpx(monkeypatch, response):
    class FakeClient:
        def __init__(self, *, follow_redirects: bool, timeout: float):
            assert follow_redirects is False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def get(self, url: str, **kwargs):
            return response

    fake_httpx = ModuleType("httpx")
    fake_httpx.Client = FakeClient
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)


def test_web_fetch_extracts_pdf_text_from_pdf_response(tmp_path: Path, monkeypatch):
    pdf = _make_pdf_bytes("RULE 23 INKJET ROC THRESHOLD 29.44 GAL")
    response = _PdfResponse(
        "https://ww2.arb.ca.gov/rules/RuleID1061.pdf", pdf, "application/pdf"
    )
    _install_fake_httpx(monkeypatch, response)
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = web_fetch(policy, "https://ww2.arb.ca.gov/rules/RuleID1061.pdf")

    assert result["ok"] is True
    assert result["status"] == "fetched"
    assert result["extracted_format"] == "pdf"
    assert "RULE 23 INKJET ROC THRESHOLD 29.44 GAL" in result["text"]


def test_web_fetch_detects_pdf_by_magic_bytes_when_content_type_generic(tmp_path: Path, monkeypatch):
    pdf = _make_pdf_bytes("GRAPHIC ARTS RULE 74.19")
    response = _PdfResponse(
        "https://www.vcapcd.org/RULE%2074.19.pdf", pdf, "application/octet-stream"
    )
    _install_fake_httpx(monkeypatch, response)
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = web_fetch(policy, "https://www.vcapcd.org/RULE%2074.19.pdf")

    assert result["ok"] is True
    assert result["extracted_format"] == "pdf"
    assert "GRAPHIC ARTS RULE 74.19" in result["text"]


class _CloudflareResponse:
    def __init__(self, url: str):
        self.url = url
        self.status_code = 403
        self.content = b"<html><body>Just a moment...</body></html>"
        self.headers = {"content-type": "text/html", "cf-ray": "abc123", "server": "cloudflare"}

    @property
    def is_success(self):
        return False

    @property
    def text(self):
        return self.content.decode()


def test_web_fetch_falls_back_to_browser_on_cloudflare_block(tmp_path: Path, monkeypatch):
    _install_fake_httpx(monkeypatch, _CloudflareResponse("https://www.vcapcd.org/rule23"))

    def fake_browser_use(policy, url, **kwargs):
        return {
            "ok": True,
            "status": "navigated",
            "snapshot": {
                "url": url,
                "title": "Rule 23",
                "text": "RULE 23 full rule text via browser",
                "status_code": 200,
            },
        }

    monkeypatch.setattr("research_core.tools.browser_use", fake_browser_use)
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = web_fetch(policy, "https://www.vcapcd.org/rule23")

    assert result["ok"] is True
    assert result["via"] == "browser_fallback"
    assert "RULE 23 full rule text via browser" in result["text"]


def test_web_fetch_does_not_fall_back_when_browser_disabled(tmp_path: Path, monkeypatch):
    _install_fake_httpx(monkeypatch, _CloudflareResponse("https://www.vcapcd.org/rule23"))

    def fail_browser(policy, url, **kwargs):
        raise AssertionError("browser_use must not run when allow_browser is False")

    monkeypatch.setattr("research_core.tools.browser_use", fail_browser)
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path, allow_browser=False)

    result = web_fetch(policy, "https://www.vcapcd.org/rule23")

    assert result["ok"] is True
    assert result["status"] == "http_error"
    assert result.get("via") != "browser_fallback"


def test_browser_use_extracts_pdf_text_for_pdf_navigation(tmp_path: Path, monkeypatch):
    # The combined Cloudflare+PDF case (e.g. vcapcd.org RULE 23.pdf): the browser clears
    # the JS challenge, then we pull the PDF bytes via the browser's request context and
    # extract the rule text (a rendered PDF viewer would yield empty body text).
    pdf = _make_pdf_bytes("RULE 23 VCAPCD EXEMPTION FULL TEXT")

    class FakeApiResponse:
        def body(self):
            return pdf

    class FakeRequestContext:
        def get(self, url: str):
            return FakeApiResponse()

    class FakeResponse:
        status = 200
        headers = {"content-type": "application/pdf"}

    class FakeLocator:
        def count(self):
            return 1

        def inner_text(self, *, timeout: int):
            return ""

    class FakePage:
        url = "https://www.vcapcd.org/RULE%2023.pdf"

        def goto(self, url: str, *, wait_until: str, timeout: int):
            self.context_handler(_NoopRoute(url), _NoopRequest(url))
            return FakeResponse()

        def title(self):
            return "RULE 23.pdf"

        def locator(self, selector: str):
            return FakeLocator()

    class FakeBrowserContext:
        request = FakeRequestContext()

        def route(self, pattern: str, handler):
            self.handler = handler

        def new_page(self):
            page = FakePage()
            page.context_handler = self.handler
            return page

        def close(self):
            pass

    class FakeBrowser:
        def new_context(self, *, service_workers: str):
            return FakeBrowserContext()

        def close(self):
            pass

    class FakeChromium:
        def launch(self, *, headless: bool):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeCtx:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, *a):
            return False

    fake_sync_api = ModuleType("playwright.sync_api")
    fake_sync_api.sync_playwright = lambda: FakeCtx()
    monkeypatch.setitem(sys.modules, "playwright", ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = browser_use(policy, "https://www.vcapcd.org/RULE%2023.pdf")

    assert result["ok"] is True
    assert result["snapshot"]["content_type"] == "application/pdf"
    assert "RULE 23 VCAPCD EXEMPTION FULL TEXT" in result["snapshot"]["text"]


class _NoopRoute:
    def __init__(self, url: str):
        self.url = url

    def continue_(self):
        pass

    def abort(self):
        pass


class _NoopRequest:
    def __init__(self, url: str):
        self.url = url
        self.resource_type = "document"


def test_cap_text_truncates_oversize_tool_output_with_marker(monkeypatch):
    from research_core.tools import _cap_text
    monkeypatch.setenv("RESEARCH_CORE_MAX_TOOL_CHARS", "1000")
    big = "X" * 5000
    out = _cap_text(big)
    assert len(out) < 5000
    assert "truncated" in out
    # small inputs pass through unchanged
    assert _cap_text("short") == "short"


def test_web_fetch_caps_huge_response_text(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RESEARCH_CORE_MAX_TOOL_CHARS", "2000")
    huge = "<html><body>" + ("A" * 50000) + "</body></html>"

    class _Resp:
        url = "https://www.arb.ca.gov/big"
        status_code = 200
        content = huge.encode()
        headers = {"content-type": "text/html"}

        @property
        def is_success(self):
            return True

        @property
        def text(self):
            return huge

    _install_fake_httpx(monkeypatch, _Resp())
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)
    result = web_fetch(policy, "https://www.arb.ca.gov/big")
    assert result["ok"] is True
    assert len(result["text"]) < 5000  # capped, not the full 50k
    assert "truncated" in result["text"]
