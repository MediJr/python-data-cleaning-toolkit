"""Tests for validation rules, quarantine and profiling."""

from __future__ import annotations

import pandas as pd
import pytest

from data_cleaning.errors import ConfigError
from data_cleaning.profiling import classify_value, is_ambiguous_date, profile_dataframe
from data_cleaning.validation import QUARANTINE_REASON_COLUMN, parse_rules, split_quarantine, validate
from conftest import make_frame


@pytest.fixture
def people():
    frame = make_frame(
        {
            "id": ["001", "002", "002", "004", None],
            "status": ["active", "Active", "closed", "unknown", "active"],
            "age": ["34", "-1", "151", "abc", None],
            "joined": ["2024-01-05", "2019-12-31", "2024-02-30", None, "2025-06-01"],
            "zip": ["01234", "1234", "98765", "ABCDE", "00000"],
        }
    )
    return frame


def _issues(result, rule_id):
    return [(i["source_row"], i["value"]) for i in result.issues if i["rule_id"] == rule_id]


def test_each_rule_reports_the_exact_failing_rows(people):
    rules = parse_rules(
        [
            {"rule": "required_columns", "columns": ["id", "email"], "id": "cols"},
            {"rule": "not_null", "column": "id", "id": "id_present"},
            {"rule": "unique", "columns": ["id"], "id": "id_unique"},
            {"rule": "allowed_values", "column": "status", "values": ["active", "closed"], "id": "status"},
            {"rule": "range", "column": "age", "min": 0, "max": 120, "id": "age"},
            {"rule": "type", "column": "age", "expected": "integer", "id": "age_int"},
            {"rule": "date_range", "column": "joined", "min": "2020-01-01", "max": "2025-12-31", "id": "joined"},
            {"rule": "pattern", "column": "zip", "regex": r"\d{5}", "id": "zip"},
        ]
    )
    result = validate(people, rules)
    assert not result.passed
    assert [i["column"] for i in result.issues if i["rule_id"] == "cols"] == ["email"]
    assert _issues(result, "id_present") == [(6, None)]
    assert [r for r, _ in _issues(result, "id_unique")] == [3, 4]
    assert _issues(result, "status") == [(3, "Active"), (5, "unknown")]
    assert _issues(result, "age") == [(3, "-1"), (4, "151"), (5, "abc")]
    assert _issues(result, "age_int") == [(5, "abc")]
    assert _issues(result, "joined") == [(3, "2019-12-31"), (4, "2024-02-30")]
    assert _issues(result, "zip") == [(3, "1234"), (5, "ABCDE")]
    assert result.rule_status["age"]["failures"] == 3


def test_missing_values_are_not_reported_by_value_rules(people):
    result = validate(people, parse_rules([{"rule": "range", "column": "age", "min": 0}]))
    assert None not in [i["value"] for i in result.issues]


def test_case_insensitive_allowed_values(people):
    rules = parse_rules([{"rule": "allowed_values", "column": "status", "values": ["ACTIVE", "closed"], "case_sensitive": False}])
    result = validate(people, rules)
    assert [i["value"] for i in result.issues] == ["unknown"]


def test_numeric_columns_are_validated_by_value():
    frame = make_frame({"x": ["a", "b"]})
    frame["n"] = pd.array([5, 500], dtype="Int64")
    result = validate(frame, parse_rules([{"rule": "range", "column": "n", "max": 100}, {"rule": "type", "column": "n", "expected": "integer"}]))
    assert [(i["rule_id"], i["value"]) for i in result.issues] == [("R1", 500)]


def test_rule_on_missing_column_is_not_silently_skipped(people):
    result = validate(people, parse_rules([{"rule": "not_null", "column": "email"}]))
    assert result.rule_status["R1"]["status"] == "not_evaluated"
    assert not result.passed


def test_passing_rules(people):
    result = validate(people, parse_rules([{"rule": "not_null", "column": "status"}]))
    assert result.passed and result.issues == []


def test_quarantine_moves_rows_with_reasons_and_report_rows_stay(people):
    rules = parse_rules(
        [
            {"rule": "range", "column": "age", "min": 0, "max": 120, "action": "quarantine", "id": "age"},
            {"rule": "allowed_values", "column": "status", "values": ["active", "closed"], "id": "status"},
        ]
    )
    result = validate(people, rules)
    kept, quarantined = split_quarantine(people, result)
    assert kept.index.tolist() == [2, 6]
    assert quarantined.index.tolist() == [3, 4, 5]
    assert quarantined.at[3, QUARANTINE_REASON_COLUMN] == "[age] -1 is below the minimum 0"
    assert len(kept) + len(quarantined) == len(people)
    assert list(quarantined.columns)[:-1] == list(people.columns)


@pytest.mark.parametrize(
    "definition, message",
    [
        ({"rule": "nonsense", "column": "a"}, "unknown rule"),
        ({"rule": "not_null"}, "missing parameter"),
        ({"rule": "not_null", "column": "a", "colour": "red"}, "unknown parameter"),
        ({"rule": "not_null", "column": "a", "action": "delete"}, "action must be"),
        ({"rule": "range", "column": "a"}, "set 'min', 'max'"),
        ({"rule": "range", "column": "a", "min": "zero"}, "must be a number"),
        ({"rule": "pattern", "column": "a", "regex": "("}, "invalid regular expression"),
        ({"rule": "date_range", "column": "a", "min": "01/01/2020"}, "does not match format"),
        ({"rule": "type", "column": "a", "expected": "float"}, "'expected'"),
        ({"rule": "unique", "columns": []}, "non-empty list"),
    ],
)
def test_invalid_rule_definitions_are_rejected(definition, message):
    with pytest.raises(ConfigError, match=message):
        parse_rules([definition])


def test_duplicate_rule_ids_are_rejected():
    with pytest.raises(ConfigError, match="duplicate rule id"):
        parse_rules([{"rule": "not_null", "column": "a", "id": "x"}, {"rule": "not_null", "column": "b", "id": "x"}])


# --------------------------------------------------------------------------- profiling


@pytest.mark.parametrize(
    "value, kind",
    [("42", "integer"), ("00123", "integer"), ("1,234.5", "numeric-like"), ("2024-01-05", "date-like"),
     ("05/01/2024", "date-like"), ("yes", "boolean-like"), ("New York", "text"), ("1.2.3.4", "text")],
)
def test_classify_value(value, kind):
    assert classify_value(value) == kind


def test_ambiguous_date_detection():
    assert is_ambiguous_date("03/04/2024")
    assert not is_ambiguous_date("25/04/2024")
    assert not is_ambiguous_date("04/04/2024")
    assert not is_ambiguous_date("2024-03-04")


def test_profile_counts_shape_missing_duplicates_and_flags():
    frame = make_frame(
        {
            "id": ["001", "002", "002", "010"],
            "city": [" Paris", "N/A", "N/A", ""],
            "when": ["03/04/2024", "2024-01-01", "2024-01-01", "x"],
        }
    )
    profile = profile_dataframe(frame, missing_tokens=["N/A"])
    assert (profile["rows"], profile["columns"]) == (4, 3)
    assert profile["missing_by_column"] == {"id": 0, "city": 3, "when": 0}
    assert profile["exact_duplicate_rows"] == 1
    assert profile["exact_duplicate_groups"] == [[3, 4]]
    ids = profile["column_profiles"]["id"]
    assert ids["inferred_type"] == "integer" and ids["leading_zero_values"] == 4
    assert profile["column_profiles"]["city"]["values_with_surrounding_whitespace"] == 1
    when = profile["column_profiles"]["when"]
    assert when["inferred_type"] == "mixed" and when["ambiguous_date_values"] == 1


def test_profile_without_tokens_does_not_treat_na_text_as_missing():
    profile = profile_dataframe(make_frame({"v": ["N/A", "0", "unknown"]}))
    assert profile["missing_by_column"] == {"v": 0}


def test_profiling_does_not_modify_data():
    frame = make_frame({"v": [" a ", ""]})
    snapshot = frame.copy()
    profile_dataframe(frame, missing_tokens=["a"])
    pd.testing.assert_frame_equal(frame, snapshot)
