#!/usr/bin/env bash
set -euo pipefail
echo "Running Python research-core tests for the Modal-backed runtime contract..."
PATH="${PWD}/.venv/bin:${PATH}" npm run py:test

echo "Deploy/smoke Modal with: modal deploy src/research_core/modal_app.py"
echo "Modal live runs expect permitpilot-openai, permitpilot-research, and permitpilot-supabase secrets."
