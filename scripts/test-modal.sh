#!/usr/bin/env bash
set -euo pipefail
echo "Running Python research-core tests for the Modal-backed runtime contract..."
npm run py:test

echo "Deploy/smoke Modal with: modal deploy src/research_core/modal_app.py"
