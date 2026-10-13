"""Tests for strict configuration validation."""

from __future__ import annotations

import json

import pytest

from data_cleaning.config import DEFAULTS, default_config, load_config, referenced_columns, validate_config
from data_cleaning.errors import ConfigError


def test_no_config_and_empty_config_give_the_documented_defaults():
    assert load_config(None) == DEFAULTS
    assert validate_config({}) == DEFAULTS
    assert DEFAULTS["duplicates"]["remove_exact"] is False
    assert DEFAULTS["missing_values"]["tokens"] == []


def test_defaults_are_filled_in_for_partial_sections():
    config = validate_config(
        {
            "missing_values": {"tokens": ["N/A"]},
            "dates": [{"column": "d", "formats": ["%Y-%m-%d"]}],
            "numbers": [{"column": "n", "thousands": ","}],
        }
    )
    assert config["missing_values"] == {"tokens": ["N/A"], "case_sensitive": False, "whitespace_as_missing": True}
    assert config["dates"][0]["on_error"] == "keep" and config["dates"][0]["output_format"] == "%Y-%m-%d"
    assert config["numbers"][0]["decimal"] == "." and config["numbers"][0]["allow_leading_zeros"] is False


def test_validation_does_not_mutate_the_defaults():
    validate_config({"missing_values": {"tokens": ["X"]}})
    assert default_config()["missing_values"]["tokens"] == []


@pytest.mark.parametrize(
    "raw, message",
    [
        ({"dedupe": True}, "Unknown key\\(s\\) in configuration: dedupe"),
        ({"missing_values": {"token": ["N/A"]}}, "Unknown key\\(s\\) in missing_values: token"),
        ({"duplicates": {"remove_exacts": True}}, "remove_exacts"),
        ({"text": [{"columns": ["a"], "trim": True}]}, "Unknown key\\(s\\) in text\\[0\\]: trim"),
        ({"column_names": {"strip": "yes"}}, "column_names.strip must be true or false"),
        ({"column_names": {"style": "camelCase"}}, "column_names.style must be one of"),
        ({"missing_values": {"tokens": "N/A"}}, "list of strings"),
        ({"missing_values": {"tokens": [" "]}}, "empty or whitespace-only"),
        ({"text": [{"columns": []}]}, "must not be empty"),
        ({"text": [{"columns": ["a"], "strip": False}]}, "enables no operation"),
        ({"text": [{"columns": ["a"], "case": "sentence"}]}, "case must be one of"),
        ({"categories": [{"column": "a", "mapping": {}}]}, "must not be empty"),
        ({"categories": [{"column": "a", "mapping": {"x": 1}}]}, "mapping strings to strings"),
        ({"categories": [{"column": "a", "mapping": {"ny": "A", "NY": "B"}, "case_insensitive": True}]}, "contradictory"),
        ({"dates": [{"column": "d"}]}, "missing required key\\(s\\): formats"),
        ({"dates": [{"column": "d", "formats": ["YYYY-MM-DD"]}]}, "not a strptime format"),
        ({"dates": [{"column": "d", "formats": ["%Y"], "on_error": "drop"}]}, "on_error must be one of"),
        ({"numbers": [{"column": "n", "decimal": ",", "thousands": ","}]}, "must differ"),
        ({"numbers": [{"column": "n", "strip_chars": "0"}]}, "strip_chars"),
        ({"duplicates": {"remove_key_duplicates": True}}, "requires duplicates.key_columns"),
        ({"duplicates": {"keep": "newest"}}, "duplicates.keep must be one of"),
        ({"validation": [{"rule": "range", "column": "a"}]}, "set 'min', 'max'"),
        ({"validation": {"rule": "not_null"}}, "validation must be a list"),
        ({"output": {"sheet_name": "a/b"}}, "sheet_name"),
        ({"output": {"csv_delimiter": ";;"}}, "single character"),
        ({"input": {"delimiter": ""}}, "single character"),
        ({"dates": [{"column": "x", "formats": ["%Y"]}], "numbers": [{"column": "x"}]}, "configured in both"),
        ({"text": [{"columns": ["a"]}, {"columns": ["a"], "case": "lower"}]}, "appears in both"),
        ({"categories": [{"column": "a", "mapping": {"x": "y"}}, {"column": "a", "mapping": {"z": "y"}}]}, "more than one category mapping"),
        ([], "must be a JSON object"),
    ],
)
def test_invalid_configurations_are_rejected_with_a_precise_message(raw, message):
    with pytest.raises(ConfigError, match=message):
        validate_config(raw)


def test_config_file_errors(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text('{"text": [\n  {"columns": ["a"],}\n]}', encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON \\(line 2"):
        load_config(bad)


def test_config_file_with_utf8_bom_is_accepted(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_bytes(json.dumps({"missing_values": {"tokens": ["N/A"]}}).encode("utf-8-sig"))
    assert load_config(path)["missing_values"]["tokens"] == ["N/A"]


def test_referenced_columns_lists_every_cleaning_column_but_not_validation():
    config = validate_config(
        {
            "text": [{"columns": ["a", "b"]}],
            "categories": [{"column": "c", "mapping": {"x": "y"}}],
            "dates": [{"column": "d", "formats": ["%Y"]}],
            "numbers": [{"column": "n"}],
            "duplicates": {"key_columns": ["k"]},
            "validation": [{"rule": "not_null", "column": "v"}],
        }
    )
    assert [c for _, c in referenced_columns(config)] == ["a", "b", "c", "d", "n", "k"]
