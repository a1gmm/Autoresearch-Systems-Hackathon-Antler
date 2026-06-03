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


def test_web_fetch_rejects_disallowed_hosts(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = web_fetch(policy, "https://aqmd.gov.evil.example/docs/rule.pdf")

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "host_not_allowed"


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
                return FakeResponse(url, 302, "https://evil.example/payload")
            raise AssertionError(f"Unexpected request to {url}")

    fake_httpx = ModuleType("httpx")
    fake_httpx.Client = FakeClient
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = web_fetch(policy, "https://www.aqmd.gov/start")

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "redirect_host_not_allowed"
    assert result["blocked_url"] == "https://evil.example/payload"
    assert requested_urls == ["https://www.aqmd.gov/start"]


def test_web_search_returns_unavailable_without_optional_dependency(tmp_path: Path):
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


def test_browser_use_rejects_disallowed_hosts(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = browser_use(policy, "https://evil.example")

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "host_not_allowed"


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
                FakeRoute("https://evil.example/popup"),
                FakeRequest("https://evil.example/popup"),
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
    assert result["error"]["code"] == "resource_host_not_allowed"
    assert ("new_context", "block") in actions
    assert ("abort", "https://evil.example/popup") in actions
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


def test_submit_finding_rejects_lookalike_source_host_with_uppercase_scheme(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = submit_finding(
        policy,
        title="Bad source",
        summary="Should be blocked.",
        sources=["HTTPS://aqmd.gov.evil.example/rule.pdf"],
        confidence=0.5,
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "host_not_allowed"


def test_submit_finding_rejects_lookalike_source_host_with_leading_whitespace(tmp_path: Path):
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = submit_finding(
        policy,
        title="Bad source",
        summary="Should be blocked.",
        sources=["  https://aqmd.gov.evil.example/rule.pdf"],
        confidence=0.5,
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "host_not_allowed"


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
