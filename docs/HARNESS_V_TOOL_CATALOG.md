# Python Sandbox Tool Catalog

The executable tool catalog now lives in Python under `src/research_core/`.
Next.js keeps only UI types and adapters.

## Runtime Tool Boundaries

| Python module | Responsibility |
| --- | --- |
| `research_core.tools` | Policy-checked web fetch/search, artifact writing, finding submission |
| `research_core.documents` | PDF, DOCX, spreadsheet, and text extraction helpers |
| `research_core.browser` | Browser-use style page interaction wrapper |
| `research_core.agents` | OpenAI Agents SDK agent definitions and tool wiring |
| `research_core.planner` | Task-level allowed/blocked tool ids |
| `research_core.verifier` | Mechanical verification and repair-ticket generation |

Regulatory workers may use web/document/browser/file tools inside the sandbox,
but final determinations are still gated by verifier checks. Missing facts,
stale currency, unsupported quotes, missing source URLs, or unresolved repair
work become `needs_information` or `needs_review`.

## Universal Tool Expectations

Every agent context should be able to:

- emit trace/workshop events,
- write structured artifacts,
- validate JSON-like artifacts,
- submit bounded findings,
- request information or review when confidence remains low.

The UI receives these through Python run payloads and `pythonRunAdapter.ts`; it
does not execute regulatory tools itself.
