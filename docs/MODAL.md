# Modal Runtime Notes

The old TypeScript research pool and per-task Modal bridge have been retired.
Modal now hosts the Python research runtime in `src/research_core/modal_app.py`.

Python owns:

- scope parsing and jurisdiction enrichment
- registry planning and discovery candidates
- OpenAI Agents SDK workers
- sandboxed web/document/browser/file tools
- verification, bounded repair, and distrust explanations
- synthesis, run persistence, and Raindrop Workshop trace events

Next.js only proxies `run_sync`, `start_run`, and `get_run`, then adapts Python
payloads for the UI. See [Modal Deployment](./MODAL_DEPLOYMENT.md) for deploy
commands and endpoint environment variables.
