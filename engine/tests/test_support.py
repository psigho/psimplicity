"""Offline tests for envutil, supports_vision, and the orchestrator cost helpers."""
import os

import pytest

from modules.envutil import resolve_env_text, resolve_env_obj
from modules.llm_gateway import supports_vision
from modules.orchestrator import _build_model_cost_table, _cost_of_call


# ── envutil ──────────────────────────────────────────────────────────────────
def test_resolve_env_text_resolved(monkeypatch):
    monkeypatch.setenv("PSIM_TEST_KEY", "secret123")
    assert resolve_env_text("k=${PSIM_TEST_KEY}") == "k=secret123"


def test_resolve_env_text_unset_blank_vs_keep(monkeypatch):
    monkeypatch.delenv("PSIM_MISSING", raising=False)
    assert resolve_env_text("k=${PSIM_MISSING}") == "k="                 # default: blank
    assert resolve_env_text("k=${PSIM_MISSING}", keep_unset=True) == "k=${PSIM_MISSING}"


def test_resolve_env_text_empty_passthrough():
    assert resolve_env_text("") == ""
    assert resolve_env_text(None) is None


def test_resolve_env_obj_nested(monkeypatch):
    monkeypatch.setenv("PSIM_A", "AA")
    obj = {"key": "${PSIM_A}", "list": ["${PSIM_A}", 5], "n": 1}
    assert resolve_env_obj(obj) == {"key": "AA", "list": ["AA", 5], "n": 1}


# ── supports_vision ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("model", [
    "gemini-2.5-pro", "gemini-3.1-pro-preview", "gpt-4o", "openai/gpt-4o-mini",
    "anthropic/claude-sonnet-4",
])
def test_supports_vision_true(model):
    assert supports_vision(model) is True


@pytest.mark.parametrize("model", [
    "deepseek/deepseek-r1", "qwen/qwen3-235b-a22b", "", "some-unknown-text-model",
])
def test_supports_vision_false(model):
    assert supports_vision(model) is False


# ── orchestrator cost helpers ────────────────────────────────────────────────
_CFG = {
    "available_models": {
        "parsers": [
            {"id": "gemini-2.5-pro", "usd_per_million_input_tokens": 1.25,
             "usd_per_million_output_tokens": 10.0},
            {"id": "openai/gpt-4o", "usd_per_million_input_tokens": 2.5,
             "usd_per_million_output_tokens": 10.0},
        ]
    }
}


def test_build_cost_table():
    table = _build_model_cost_table(_CFG)
    assert table["gemini-2.5-pro"] == {"in": 1.25, "out": 10.0}
    assert table["openai/gpt-4o"]["in"] == 2.5


def test_cost_of_call_basic():
    table = _build_model_cost_table(_CFG)
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}
    # 1.25 (in) + 10.0 (out) = 11.25
    assert _cost_of_call("gemini-2.5-pro", usage, table) == pytest.approx(11.25)


def test_cost_of_call_prefix_stripping():
    table = _build_model_cost_table(_CFG)
    usage = {"prompt_tokens": 500_000, "completion_tokens": 0}
    # 'google/gemini-2.5-pro' should fall back to the bare 'gemini-2.5-pro' row
    assert _cost_of_call("google/gemini-2.5-pro", usage, table) == pytest.approx(0.625)


def test_cost_of_call_unknown_model_zero():
    table = _build_model_cost_table(_CFG)
    usage = {"prompt_tokens": 9_999, "completion_tokens": 9_999}
    assert _cost_of_call("mystery-model", usage, table) == 0.0
