from __future__ import annotations

import json

import pytest

from research_core.cli import main


@pytest.fixture(autouse=True)
def _no_env_pollution(monkeypatch):
    # main() autoloads .env.local into os.environ; stub it so CLI tests never leak the
    # real key/model into the rest of the suite.
    monkeypatch.setattr("research_core.cli._load_env_local", lambda: None)


def test_cli_fake_run_renders_report(capsys):
    code = main([
        "coating shop adds spray booth, 200 gal solvent, hazardous waste",
        "--county", "Ventura", "--city", "Oxnard", "--mode", "fake", "--no-color",
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert "PermitPilot research" in out
    assert "Coverage families" in out
    assert "Determinations" in out


def test_cli_json_mode_emits_valid_json(capsys):
    code = main(["a coating shop with solvent", "--mode", "fake", "--json", "--no-color"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert "status" in data and "verdicts" in data


def test_cli_live_without_key_errors(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    code = main(["something", "--mode", "live", "--no-color"])
    assert code == 2
    assert "OPENAI_API_KEY" in capsys.readouterr().err
