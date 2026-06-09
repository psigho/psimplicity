"""Offline tests for the 3-layer JSON recovery — the docstring's garbage cases."""
import pytest

from modules.json_repair import extract_json, _fix_unescaped_newlines


def test_clean_json():
    assert extract_json('{"a": 1, "b": "two"}') == {"a": 1, "b": "two"}


def test_markdown_fence_json():
    assert extract_json('```json\n{"x": true}\n```') == {"x": True}


def test_markdown_fence_no_lang():
    assert extract_json('```\n{"x": 1}\n```') == {"x": 1}


def test_trailing_commas():
    assert extract_json('{"a": 1, "b": [1, 2, 3,],}') == {"a": 1, "b": [1, 2, 3]}


def test_literal_newlines_in_string_gemini_quirk():
    # raw newline inside a string value would break json.loads("Unterminated string")
    raw = '{"feedback": "line one\nline two"}'
    assert extract_json(raw) == {"feedback": "line one\nline two"}


def test_bom_and_zero_width_prefix():
    assert extract_json('﻿​{"ok": 1}') == {"ok": 1}


def test_stray_wrapper_text_layer2():
    raw = 'Sure! Here is the JSON you asked for:\n{"score": 8}\nHope that helps.'
    assert extract_json(raw) == {"score": 8}


def test_nested_object_survives():
    raw = '```json\n{"scores": {"a": 1, "b": 2}, "passed": true,}\n```'
    assert extract_json(raw) == {"scores": {"a": 1, "b": 2}, "passed": True}


def test_empty_raises():
    with pytest.raises(ValueError):
        extract_json("")
    with pytest.raises(ValueError):
        extract_json("   \n  ")


def test_unrecoverable_raises():
    with pytest.raises(Exception):
        extract_json("this is not json at all, no braces here")


def test_fix_unescaped_newlines_preserves_structure():
    # newline OUTSIDE strings (between members) must be left alone
    assert _fix_unescaped_newlines('{"a": 1,\n"b": 2}') == '{"a": 1,\n"b": 2}'
    # newline INSIDE a string must be escaped
    assert _fix_unescaped_newlines('{"a": "x\ny"}') == '{"a": "x\\ny"}'
