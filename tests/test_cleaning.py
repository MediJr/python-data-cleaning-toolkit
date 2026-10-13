"""Tests for the cleaning transformations."""

from __future__ import annotations

import pandas as pd
import pytest

from data_cleaning.cleaning import (
    handle_exact_duplicates,
    handle_key_duplicates,
    map_categories,
    normalize_column_names,
    normalize_text,
    parse_dates,
    parse_numbers,
    standardize_missing,
)
from data_cleaning.errors import ColumnCollisionError, ConfigError, MissingColumnError
from conftest import make_frame

# --------------------------------------------------------------------------- column names


def test_column_names_are_trimmed_collapsed_and_mapping_is_kept():
    frame = make_frame({" Customer  ID ": ["1"], "Total": ["2"]})
    result, report = normalize_column_names(frame)
    assert list(result.columns) == ["Customer ID", "Total"]
    assert report.details["renamed"] == {" Customer  ID ": "Customer ID"}
    assert report.details["mapping"]["Total"] == "Total"


def test_snake_case_removes_accents_and_special_characters():
    frame = make_frame({"Prénom (client)": ["a"], "Order #": ["1"], "e-mail": ["x"]})
    result, _ = normalize_column_names(frame, style="snake_case")
    assert list(result.columns) == ["prenom_client", "order", "e_mail"]


def test_normalization_collision_raises_and_names_both_columns():
    frame = make_frame({"Order ID": ["1"], "order_id": ["2"]})
    with pytest.raises(ColumnCollisionError, match="'Order ID' / 'order_id' -> 'order_id'"):
        normalize_column_names(frame, style="snake_case")


def test_collision_with_untouched_column_is_detected():
    frame = make_frame({"Name ": ["a"], "Name": ["b"]})
    with pytest.raises(ColumnCollisionError):
        normalize_column_names(frame)


def test_explicit_rename_resolves_collision():
    frame = make_frame({"Order ID": ["1"], "order_id": ["2"]})
    result, report = normalize_column_names(frame, style="snake_case", rename={"order_id": "order_id_legacy"})
    assert list(result.columns) == ["order_id", "order_id_legacy"]
    assert report.details["renamed"] == {"Order ID": "order_id", "order_id": "order_id_legacy"}


def test_name_that_becomes_empty_is_rejected():
    with pytest.raises(ColumnCollisionError, match="empty name"):
        normalize_column_names(make_frame({"%%%": ["1"]}), style="snake_case")


def test_rename_of_unknown_column_is_rejected():
    with pytest.raises(MissingColumnError, match="'missing'"):
        normalize_column_names(make_frame({"a": ["1"]}), rename={"missing": "b"})


# --------------------------------------------------------------------------- missing values


def test_missing_defaults_only_cover_empty_and_whitespace():
    frame = make_frame({"v": ["", "   ", "0", "unknown", "N/A", "x"]})
    result, report = standardize_missing(frame)
    assert result["v"].isna().tolist() == [True, True, False, False, False, False]
    assert result["v"].tolist()[2:] == ["0", "unknown", "N/A", "x"]
    assert report.cells_changed == {"v": 1}  # whitespace-only became empty; "" was already empty
    assert report.details["by_column"]["v"]["missing_after"] == 2


def test_configured_tokens_are_case_insensitive_by_default_and_counted():
    frame = make_frame({"v": ["N/A", "n/a", " NULL ", "None", "0"]})
    result, report = standardize_missing(frame, tokens=["N/A", "NULL"])
    assert result["v"].isna().tolist() == [True, True, True, False, False]
    counts = report.details["by_column"]["v"]
    assert counts["token:N/A"] == 1 and counts["token:n/a"] == 1 and counts["token:NULL"] == 1
    assert report.cells_changed == {"v": 3}


def test_case_sensitive_tokens():
    frame = make_frame({"v": ["N/A", "n/a"]})
    result, _ = standardize_missing(frame, tokens=["N/A"], case_sensitive=True)
    assert result["v"].isna().tolist() == [True, False]


def test_whitespace_can_be_kept_as_a_value():
    frame = make_frame({"v": ["  ", "a"]})
    result, report = standardize_missing(frame, whitespace_as_missing=False)
    assert result["v"].tolist() == ["  ", "a"] and report.total_cells_changed == 0


def test_missing_handling_does_not_mutate_input():
    frame = make_frame({"v": ["N/A"]})
    standardize_missing(frame, tokens=["N/A"])
    assert frame["v"].tolist() == ["N/A"]


def test_empty_token_is_rejected():
    with pytest.raises(ConfigError):
        standardize_missing(make_frame({"v": ["a"]}), tokens=[" "])


# --------------------------------------------------------------------------- text


def test_text_strip_collapse_and_case_with_change_counts():
    frame = make_frame({"city": ["  new   york ", "Paris", None, "LONDON"], "other": [" keep ", "x", "y", "z"]})
    result, report = normalize_text(frame, ["city"], collapse_whitespace=True, case="title")
    assert result["city"].tolist()[:2] == ["New York", "Paris"]
    assert pd.isna(result["city"].iloc[2])
    assert result["city"].iloc[3] == "London"
    assert result["other"].tolist()[0] == " keep "  # untouched column
    assert report.cells_changed == {"city": 2}
    assert report.examples["city"][0] == {"source_row": 2, "before": "  new   york ", "after": "New York"}


def test_text_strip_handles_non_breaking_spaces():
    frame = make_frame({"v": [" abc "]})
    result, _ = normalize_text(frame, ["v"])
    assert result["v"].tolist() == ["abc"]


def test_text_normalization_rejects_numeric_column_and_bad_case():
    frame = make_frame({"v": ["1"]})
    frame["n"] = pd.array([1], dtype="Int64")
    with pytest.raises(ConfigError, match="not a text column"):
        normalize_text(frame, ["n"])
    with pytest.raises(ConfigError, match="text case"):
        normalize_text(frame, ["v"], case="sentence")


# --------------------------------------------------------------------------- categories


def test_category_mapping_only_changes_listed_labels():
    frame = make_frame({"city": ["new york", "NEW YORK", "New York", "NYC", "Newark", None]})
    mapping = {"new york": "New York", "NEW YORK": "New York"}
    result, report = map_categories(frame, "city", mapping)
    assert result["city"].tolist()[:5] == ["New York", "New York", "New York", "NYC", "Newark"]
    assert report.cells_changed == {"city": 2}
    assert report.details["unmapped_values"] == {"NYC": 1, "Newark": 1}
    assert report.warnings and "not covered" in report.warnings[0]


def test_category_mapping_case_insensitive_matching():
    frame = make_frame({"status": [" active", "ACTIVE", "Inactive", "pending"]})
    result, report = map_categories(frame, "status", {"active": "Active", "inactive": "Inactive"}, case_insensitive=True)
    assert result["status"].tolist() == ["Active", "Active", "Inactive", "pending"]
    assert report.cells_changed == {"status": 2}  # "Inactive" was already correct


def test_contradictory_case_insensitive_mapping_is_rejected():
    with pytest.raises(ConfigError, match="contradictory"):
        map_categories(make_frame({"s": ["a"]}), "s", {"ny": "New York", "NY": "Nyon"}, case_insensitive=True)


def test_category_mapping_on_missing_column():
    with pytest.raises(MissingColumnError):
        map_categories(make_frame({"s": ["a"]}), "t", {"a": "b"})


# --------------------------------------------------------------------------- dates


def test_dates_with_explicit_formats_are_converted_to_iso():
    frame = make_frame({"d": ["2024-03-15", "15/03/2024", "1/2/2024", None]})
    result, report = parse_dates(frame, "d", ["%Y-%m-%d", "%d/%m/%Y"])
    assert result["d"].tolist()[:3] == ["2024-03-15", "2024-03-15", "2024-02-01"]
    assert report.details == {"converted": 3, "invalid": 0, "ambiguous": 0}
    assert report.cells_changed == {"d": 2}


def test_ambiguous_dates_are_not_guessed():
    frame = make_frame({"d": ["03/04/2024", "25/04/2024", "04/04/2024"]})
    result, report = parse_dates(frame, "d", ["%d/%m/%Y", "%m/%d/%Y"])
    assert result["d"].tolist() == ["03/04/2024", "2024-04-25", "2024-04-04"]
    assert report.details["ambiguous"] == 1
    assert report.issues[0]["source_row"] == 2 and "ambiguous" in report.issues[0]["reason"]


def test_invalid_dates_are_kept_and_reported_by_default():
    frame = make_frame({"d": ["2024-02-30", "not a date", "2024-02-29"]})
    result, report = parse_dates(frame, "d", ["%Y-%m-%d"])
    assert result["d"].tolist() == ["2024-02-30", "not a date", "2024-02-29"]
    assert [i["value"] for i in report.issues] == ["2024-02-30", "not a date"]
    assert report.details["invalid"] == 2


def test_invalid_dates_can_be_set_missing_explicitly_and_originals_stay_in_report():
    frame = make_frame({"d": ["2024-13-01", "2024-01-31"]})
    result, report = parse_dates(frame, "d", ["%Y-%m-%d"], on_error="set_missing")
    assert pd.isna(result["d"].iloc[0]) and result["d"].iloc[1] == "2024-01-31"
    assert report.issues[0]["value"] == "2024-13-01"
    assert report.cells_changed == {"d": 1}


def test_date_configuration_errors():
    frame = make_frame({"d": ["x"]})
    with pytest.raises(ConfigError):
        parse_dates(frame, "d", [])
    with pytest.raises(ConfigError):
        parse_dates(frame, "d", ["YYYY-MM-DD"])
    with pytest.raises(ConfigError):
        parse_dates(frame, "d", ["%Y"], on_error="guess")


# --------------------------------------------------------------------------- numbers


def test_numbers_with_thousands_separator_become_float():
    frame = make_frame({"n": ["1,234.50", "12", "-0.5", None]})
    result, report = parse_numbers(frame, "n", thousands=",")
    assert str(result["n"].dtype) == "Float64"
    assert result["n"].tolist()[:3] == [1234.5, 12.0, -0.5]
    assert report.details["converted"] == 3 and report.details["failed"] == 0


def test_european_number_format():
    frame = make_frame({"n": ["1.234,5", "1 234,5", "0,25"]})
    result, report = parse_numbers(frame, "n", decimal=",", thousands=".")
    # The space-grouped value does not match the configured format, so the column stays text.
    assert result["n"].tolist() == ["1234.5", "1 234,5", "0.25"]
    assert [i["value"] for i in report.issues] == ["1 234,5"]
    result_space, report = parse_numbers(frame, "n", decimal=",", thousands=" ")
    assert result_space["n"].tolist()[1:] == ["1234.5", "0.25"]
    assert report.issues[0]["value"] == "1.234,5"  # '.' is not the configured separator
    clean = make_frame({"n": ["1.234,5", "0,25"]})
    numeric, _ = parse_numbers(clean, "n", decimal=",", thousands=".")
    assert str(numeric["n"].dtype) == "Float64" and numeric["n"].tolist() == [1234.5, 0.25]


def test_whole_numbers_become_int64():
    frame = make_frame({"n": ["10", "20.00", "+3"]})
    result, _ = parse_numbers(frame, "n")
    assert str(result["n"].dtype) == "Int64" and result["n"].tolist() == [10, 20, 3]


def test_wrongly_formatted_numbers_are_not_guessed_and_column_stays_text():
    frame = make_frame({"n": ["1,23", "4.5", "abc", "1,234"]})
    result, report = parse_numbers(frame, "n", thousands=",")
    assert result["n"].tolist() == ["1,23", "4.5", "abc", "1234"]
    assert str(result["n"].dtype) == "string"
    assert sorted(i["value"] for i in report.issues) == ["1,23", "abc"]
    assert report.cells_changed == {"n": 1}


def test_currency_symbols_are_removed_only_when_configured():
    frame = make_frame({"n": ["$1,200.00", "€ 15"]})
    _, strict = parse_numbers(frame, "n", thousands=",")
    assert strict.details["failed"] == 2
    result, _ = parse_numbers(frame, "n", thousands=",", strip_chars="$€")
    assert result["n"].tolist() == [1200, 15]


def test_leading_zero_codes_are_never_silently_converted():
    frame = make_frame({"code": ["00123", "0", "0.5", "123"]})
    result, report = parse_numbers(frame, "code")
    assert result["code"].tolist() == ["00123", "0", "0.5", "123"]
    assert report.issues[0]["value"] == "00123" and "leading zeros" in report.issues[0]["reason"]
    allowed, _ = parse_numbers(frame, "code", allow_leading_zeros=True)
    assert allowed["code"].tolist() == [123.0, 0.0, 0.5, 123.0]


def test_numbers_set_missing_on_error_gives_numeric_column():
    frame = make_frame({"n": ["5", "five"]})
    result, report = parse_numbers(frame, "n", on_error="set_missing")
    assert str(result["n"].dtype) == "Int64" and result["n"].iloc[0] == 5 and pd.isna(result["n"].iloc[1])
    assert report.issues[0]["value"] == "five"


def test_huge_and_overly_precise_numbers_are_reported_not_rounded():
    frame = make_frame({"n": ["99999999999999999999"]})
    _, report = parse_numbers(frame, "n")
    assert "too large" in report.issues[0]["reason"]
    precise = make_frame({"n": ["0.12345678901234567890", "1.5"]})
    result, report = parse_numbers(precise, "n")
    assert result["n"].tolist()[0] == "0.12345678901234567890"
    assert "significant digits" in report.issues[0]["reason"]


def test_number_configuration_errors():
    frame = make_frame({"n": ["1"]})
    with pytest.raises(ConfigError):
        parse_numbers(frame, "n", decimal=",", thousands=",")
    with pytest.raises(ConfigError):
        parse_numbers(frame, "n", decimal=";")
    with pytest.raises(ConfigError):
        parse_numbers(frame, "n", strip_chars="1")


# --------------------------------------------------------------------------- duplicates


@pytest.fixture
def orders():
    return make_frame(
        {
            "order_id": ["A1", "A1", "A2", "A3", "A3", None, None],
            "amount": ["10", "10", "5", "7", "9", "1", "1"],
        }
    )


def test_exact_duplicates_are_detected_but_kept_by_default(orders):
    kept, removed, report = handle_exact_duplicates(orders)
    assert len(kept) == 7 and removed.empty
    assert report.details["duplicate_rows"] == 2
    assert report.details["groups"] == [{"source_rows": [2, 3]}, {"source_rows": [7, 8]}]
    assert report.rows_removed == []


def test_exact_duplicate_removal_keeps_first_occurrence(orders):
    kept, removed, report = handle_exact_duplicates(orders, remove=True)
    assert kept.index.tolist() == [2, 4, 5, 6, 7]
    assert removed.index.tolist() == [3, 8]
    assert report.rows_removed == [3, 8]


def test_exact_duplicates_compare_after_previous_steps_only():
    frame = make_frame({"a": ["x ", "x"]})
    _, _, report = handle_exact_duplicates(frame, remove=True)
    assert report.details["duplicate_rows"] == 0


def test_key_duplicates_report_conflicts_and_ignore_missing_keys(orders):
    kept, removed, report = handle_key_duplicates(orders, ["order_id"])
    assert len(kept) == 7 and removed.empty
    groups = report.details["groups"]
    assert [g["source_rows"] for g in groups] == [[2, 3], [5, 6]]
    assert groups[0]["identical"] is True
    assert groups[1]["identical"] is False and groups[1]["differing_columns"] == ["amount"]
    assert report.details["rows_with_missing_key"] == 2


@pytest.mark.parametrize("keep, expected_removed", [("first", [3, 6]), ("last", [2, 5])])
def test_key_duplicate_removal_follows_keep_rule(orders, keep, expected_removed):
    kept, removed, report = handle_key_duplicates(orders, ["order_id"], remove=True, keep=keep)
    assert removed.index.tolist() == expected_removed
    assert len(kept) == 5
    assert any("differing values" in w for w in report.warnings)


def test_key_duplicate_configuration_errors(orders):
    with pytest.raises(ConfigError):
        handle_key_duplicates(orders, [])
    with pytest.raises(ConfigError):
        handle_key_duplicates(orders, ["order_id"], keep="random")
    with pytest.raises(MissingColumnError):
        handle_key_duplicates(orders, ["customer"])
