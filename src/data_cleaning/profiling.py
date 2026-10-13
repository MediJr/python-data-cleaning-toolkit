"""Read-only data profiling: shape, inferred types, missing values and duplicates.

Profiling never modifies the data. Type inference is descriptive only: it tells
the user what the values *look like* so that conversion rules can be configured
deliberately; it is never used to convert data automatically.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Sequence

import pandas as pd

from .cleaning import missing_mask

_INTEGER = re.compile(r"[+-]?\d+")
_NUMERIC_LIKE = re.compile(r"[+-]?(?:\d{1,3}(?:[,.'   ]\d{3})+|\d+)?(?:[.,]\d+)?")
_DATE_LIKE = re.compile(r"(\d{1,4})([-/.])(\d{1,2})\2(\d{1,4})(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?")
_BOOLEAN_LIKE = {"true", "false", "yes", "no"}

MAX_SAMPLE_VALUES = 5


def classify_value(value: str) -> str:
    """Describe what a single text value looks like.

    Returns one of ``"integer"``, ``"date-like"``, ``"numeric-like"``,
    ``"boolean-like"`` or ``"text"``.
    """
    text = value.strip()
    if _INTEGER.fullmatch(text):
        return "integer"
    if _DATE_LIKE.fullmatch(text):
        return "date-like"
    if any(ch.isdigit() for ch in text) and _NUMERIC_LIKE.fullmatch(text):
        return "numeric-like"
    if text.casefold() in _BOOLEAN_LIKE:
        return "boolean-like"
    return "text"


def is_ambiguous_date(value: str) -> bool:
    """True for values such as ``03/04/2024`` where day and month could be swapped."""
    match = _DATE_LIKE.fullmatch(value.strip())
    if not match:
        return False
    first, _, second, third = match.groups()
    if len(first) == 4:  # year first: YYYY-MM-DD is the only common reading
        return False
    a, b = int(first), int(second)
    return a != b and 1 <= a <= 12 and 1 <= b <= 12


def has_leading_zero(value: str) -> bool:
    """True for digit strings such as ``00123`` whose leading zeros would be lost as a number."""
    text = value.strip().lstrip("+-")
    return len(text) > 1 and text.isdigit() and text.startswith("0")


def profile_column(series: pd.Series, missing: pd.Series) -> dict[str, Any]:
    """Profile one column; ``missing`` is the boolean mask of missing cells."""
    present = series[~missing]
    profile: dict[str, Any] = {
        "dtype": str(series.dtype),
        "non_missing": int(present.shape[0]),
        "missing": int(missing.sum()),
        "missing_pct": round(100 * float(missing.mean()), 2) if len(series) else 0.0,
        "distinct": int(present.nunique()),
    }
    if not (pd.api.types.is_string_dtype(series.dtype) or series.dtype == object):
        profile["inferred_type"] = "number" if pd.api.types.is_numeric_dtype(series.dtype) else str(series.dtype)
        profile["value_kinds"] = {profile["inferred_type"]: profile["non_missing"]}
        profile["sample_values"] = [_plain(v) for v in present.drop_duplicates().head(MAX_SAMPLE_VALUES)]
        return profile

    texts = present.astype(str)
    kinds = Counter(classify_value(value) for value in texts)
    profile["value_kinds"] = dict(kinds.most_common())
    if not kinds:
        profile["inferred_type"] = "empty"
    elif len(kinds) == 1:
        profile["inferred_type"] = next(iter(kinds))
    elif set(kinds) <= {"integer", "numeric-like"}:
        profile["inferred_type"] = "numeric-like"
    else:
        profile["inferred_type"] = "mixed"
    profile["leading_zero_values"] = int(sum(has_leading_zero(v) for v in texts))
    profile["ambiguous_date_values"] = int(sum(is_ambiguous_date(v) for v in texts))
    profile["values_with_surrounding_whitespace"] = int(sum(v != v.strip() for v in texts))
    profile["values_with_repeated_internal_spaces"] = int(sum("  " in v.strip() for v in texts))
    profile["sample_values"] = list(texts.drop_duplicates().head(MAX_SAMPLE_VALUES))
    return profile


def profile_dataframe(
    data: pd.DataFrame,
    *,
    missing_tokens: Sequence[str] = (),
    tokens_case_sensitive: bool = False,
    whitespace_as_missing: bool = True,
) -> dict[str, Any]:
    """Build a descriptive profile of ``data`` without modifying it.

    Args:
        data: The dataset to profile.
        missing_tokens: Extra values to count as missing (e.g. ``"N/A"``); empty by default.
        tokens_case_sensitive: Whether ``missing_tokens`` match case-sensitively.
        whitespace_as_missing: Count whitespace-only cells as missing.

    Returns:
        A JSON-friendly dictionary with dataset-level and per-column statistics.
    """
    columns: dict[str, Any] = {}
    missing_by_column: dict[str, int] = {}
    missing_frame = pd.DataFrame(index=data.index)
    for column in data.columns:
        missing = missing_mask(
            data[column],
            tokens=missing_tokens,
            case_sensitive=tokens_case_sensitive,
            whitespace_as_missing=whitespace_as_missing,
        )
        missing_frame[column] = missing
        columns[column] = profile_column(data[column], missing)
        missing_by_column[column] = columns[column]["missing"]

    duplicated = data.duplicated(keep="first")
    duplicate_groups = _exact_duplicate_groups(data)
    return {
        "rows": int(data.shape[0]),
        "columns": int(data.shape[1]),
        "column_names": [str(c) for c in data.columns],
        "missing_cells": int(sum(missing_by_column.values())),
        "missing_by_column": missing_by_column,
        "fully_missing_rows": int(missing_frame.all(axis=1).sum()) if data.shape[1] else 0,
        "exact_duplicate_rows": int(duplicated.sum()),
        "exact_duplicate_groups": duplicate_groups,
        "column_profiles": columns,
    }


def _exact_duplicate_groups(data: pd.DataFrame) -> list[list[int]]:
    """Source row numbers of each group of exactly identical rows (groups of 2+ only)."""
    if data.empty:
        return []
    mask = data.duplicated(keep=False)
    if not mask.any():
        return []
    subset = data[mask]
    groups: dict[tuple, list[int]] = {}
    for row_number, values in zip(subset.index, subset.itertuples(index=False, name=None)):
        key = tuple("\x00NA" if pd.isna(v) else v for v in values)
        groups.setdefault(key, []).append(int(row_number))
    return list(groups.values())


def _plain(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value
