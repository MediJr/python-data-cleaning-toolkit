"""Cleaning transformations.

Every function in this module:

* takes a DataFrame and returns a **new** DataFrame (the input is never mutated);
* only touches the columns it is explicitly given;
* returns a :class:`~data_cleaning.models.StepReport` that counts each changed
  cell, keeps before/after examples, and lists values it could not process.

Functions that remove rows also return the removed rows so that the caller can
save them instead of discarding information.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

import pandas as pd

from .errors import ColumnCollisionError, ConfigError, MissingColumnError
from .io import render_text
from .models import StepReport, to_plain

TEXT_CASES = ("lower", "upper", "title")
COLUMN_NAME_STYLES = ("snake_case", "lower")
ON_ERROR_OPTIONS = ("keep", "set_missing")
DECIMAL_SEPARATORS = (".", ",")
THOUSANDS_SEPARATORS = (",", ".", " ", "'")
KEEP_OPTIONS = ("first", "last")

_SPACE_VARIANTS = "   "
_INT64_MIN, _INT64_MAX = -(2**63), 2**63 - 1


def require_columns(data: pd.DataFrame, columns: Iterable[str], context: str) -> None:
    """Raise ``MissingColumnError`` if any of ``columns`` is absent from ``data``."""
    missing = [c for c in columns if c not in data.columns]
    if missing:
        raise MissingColumnError(
            f"{context}: column(s) not found: {', '.join(repr(c) for c in missing)}. "
            f"Available columns: {', '.join(repr(str(c)) for c in data.columns)}"
        )


def _check_option(name: str, value: object, allowed: Sequence[object]) -> None:
    if value not in allowed:
        raise ConfigError(f"Invalid {name} {value!r}; expected one of: {', '.join(repr(a) for a in allowed)}")


# --------------------------------------------------------------------------- column names


def normalize_column_names(
    data: pd.DataFrame,
    *,
    strip: bool = True,
    collapse_whitespace: bool = True,
    style: str | None = None,
    rename: Mapping[str, str] | None = None,
) -> tuple[pd.DataFrame, StepReport]:
    """Normalize column names and keep a mapping from original to new names.

    Args:
        strip: Remove leading/trailing whitespace.
        collapse_whitespace: Replace runs of whitespace inside names by one space.
        style: ``"snake_case"`` (lowercase ASCII, non-alphanumerics -> ``_``),
            ``"lower"``, or ``None`` to keep the case.
        rename: Explicit ``{original_name: new_name}`` renames; these take precedence
            over the automatic normalization for the listed columns.

    Raises:
        ColumnCollisionError: Two distinct columns would end up with the same name,
            or a name would become empty. Nothing is renamed silently in that case.
    """
    if style is not None:
        _check_option("column name style", style, COLUMN_NAME_STYLES)
    rename = dict(rename or {})
    require_columns(data, rename, "Column rename")
    report = StepReport(
        "normalize_column_names",
        rule={"strip": strip, "collapse_whitespace": collapse_whitespace, "style": style, "rename": rename},
    )

    mapping: dict[str, str] = {}
    for original in data.columns:
        name = str(original)
        if original in rename:
            new = str(rename[original])
        else:
            new = name
            if strip:
                new = new.strip()
            if collapse_whitespace:
                new = re.sub(r"\s+", " ", new)
            if style == "snake_case":
                new = _snake_case(new)
            elif style == "lower":
                new = new.lower()
        if new.strip() == "":
            raise ColumnCollisionError(f"Column {name!r} would get an empty name after normalization.")
        mapping[original] = new

    targets: dict[str, list[str]] = {}
    for original, new in mapping.items():
        targets.setdefault(new, []).append(str(original))
    collisions = {new: originals for new, originals in targets.items() if len(originals) > 1}
    if collisions:
        listed = "; ".join(f"{' / '.join(repr(o) for o in originals)} -> {new!r}" for new, originals in collisions.items())
        raise ColumnCollisionError(
            f"Column-name normalization would merge distinct columns: {listed}. "
            "Add explicit renames for these columns or disable the conflicting option."
        )

    renamed = {str(o): n for o, n in mapping.items() if str(o) != n}
    report.details = {"mapping": {str(o): n for o, n in mapping.items()}, "renamed": renamed}
    report.cells_changed = {}
    return data.rename(columns=mapping), report


def _snake_case(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^0-9a-zA-Z]+", "_", ascii_name).strip("_").lower()


# --------------------------------------------------------------------------- missing values


def missing_mask(
    series: pd.Series,
    *,
    tokens: Sequence[str] = (),
    case_sensitive: bool = False,
    whitespace_as_missing: bool = True,
) -> pd.Series:
    """Boolean mask of missing cells.

    A cell is missing if it is NA, an empty string, whitespace-only (when
    ``whitespace_as_missing``), or equal to one of ``tokens`` after trimming.
    Values such as ``0``, ``"unknown"`` or ``"n/a"`` are *not* missing unless
    listed in ``tokens``.
    """
    mask = series.isna()
    if not (pd.api.types.is_string_dtype(series.dtype) or series.dtype == object):
        return mask.astype(bool)
    text = series.astype("string")
    stripped = text.str.strip()
    mask = mask | text.eq("").fillna(False)
    if whitespace_as_missing:
        mask = mask | stripped.eq("").fillna(False)
    if tokens:
        if case_sensitive:
            mask = mask | stripped.isin(list(tokens)).fillna(False)
        else:
            folded = {t.casefold() for t in tokens}
            mask = mask | stripped.str.casefold().isin(folded).fillna(False)
    return mask.astype(bool)


def standardize_missing(
    data: pd.DataFrame,
    *,
    tokens: Sequence[str] = (),
    case_sensitive: bool = False,
    whitespace_as_missing: bool = True,
    columns: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, StepReport]:
    """Mark missing cells as NA (written as empty cells on export).

    Empty strings are always treated as missing. Whitespace-only cells and the
    configured ``tokens`` (e.g. ``"N/A"``, ``"NULL"``) are converted to missing and
    each conversion is counted. No value is *imputed*: missing stays missing.
    """
    tokens = list(tokens)
    if any(not isinstance(t, str) or t.strip() == "" for t in tokens):
        raise ConfigError("Missing-value tokens must be non-empty strings.")
    selected = list(data.columns) if columns is None else list(columns)
    require_columns(data, selected, "Missing-value handling")
    report = StepReport(
        "standardize_missing",
        rule={
            "tokens": tokens,
            "case_sensitive": case_sensitive,
            "whitespace_as_missing": whitespace_as_missing,
            "columns": "all" if columns is None else selected,
        },
    )
    result = data.copy()
    breakdown: dict[str, dict[str, int]] = {}
    for column in selected:
        series = result[column]
        if not (pd.api.types.is_string_dtype(series.dtype) or series.dtype == object):
            continue
        base = series.mask(series.eq("").fillna(False), pd.NA)
        mask = missing_mask(base, tokens=tokens, case_sensitive=case_sensitive, whitespace_as_missing=whitespace_as_missing)
        new = base.mask(mask, pd.NA)
        report.record_changes(column, base, new)
        changed = mask & base.notna()
        stripped = base[changed].astype("string").str.strip()
        counts = {"empty": int(series.eq("").fillna(False).sum()), "whitespace_only": int(stripped.eq("").sum())}
        token_counts = stripped[stripped.ne("")].value_counts()
        counts.update({f"token:{value}": int(n) for value, n in token_counts.items()})
        counts["missing_after"] = int(new.isna().sum())
        breakdown[column] = counts
        result[column] = new
    report.details = {"by_column": breakdown}
    return result, report


# --------------------------------------------------------------------------- text


def normalize_text(
    data: pd.DataFrame,
    columns: Sequence[str],
    *,
    strip: bool = True,
    collapse_whitespace: bool = False,
    case: str | None = None,
) -> tuple[pd.DataFrame, StepReport]:
    """Trim, collapse whitespace and/or change letter case in the given text columns.

    Args:
        columns: Columns to normalize (must be text columns).
        strip: Remove leading/trailing whitespace (including non-breaking spaces).
        collapse_whitespace: Replace runs of internal whitespace by a single space.
        case: ``"lower"``, ``"upper"``, ``"title"`` or ``None`` (keep case). Title case
            can alter names such as "McDonald" -> "Mcdonald"; use it only where safe.
    """
    if case is not None:
        _check_option("text case", case, TEXT_CASES)
    require_columns(data, columns, "Text normalization")
    report = StepReport(
        "normalize_text",
        rule={"columns": list(columns), "strip": strip, "collapse_whitespace": collapse_whitespace, "case": case},
    )
    result = data.copy()
    for column in columns:
        series = result[column]
        if not (pd.api.types.is_string_dtype(series.dtype) or series.dtype == object):
            raise ConfigError(f"Text normalization: column {column!r} is not a text column ({series.dtype}).")
        new = series.astype("string")
        if strip:
            new = new.str.strip()
        if collapse_whitespace:
            new = new.str.replace(r"\s+", " ", regex=True)
        if case == "lower":
            new = new.str.lower()
        elif case == "upper":
            new = new.str.upper()
        elif case == "title":
            new = new.str.title()
        report.record_changes(column, series, new)
        result[column] = new
    return result, report


def map_categories(
    data: pd.DataFrame,
    column: str,
    mapping: Mapping[str, str],
    *,
    case_insensitive: bool = False,
) -> tuple[pd.DataFrame, StepReport]:
    """Replace category labels using an explicit ``{source_label: target_label}`` mapping.

    Only labels listed in ``mapping`` are changed; similar-looking labels are never
    merged automatically. With ``case_insensitive=True`` keys match regardless of
    case and surrounding whitespace. Labels not covered by the mapping are left
    unchanged and listed in the report so that the mapping can be extended.

    Raises:
        ConfigError: The mapping is empty, or two keys that match the same value
            (under case-insensitive matching) point to different targets.
    """
    if not mapping:
        raise ConfigError(f"Category mapping for column {column!r} is empty.")
    require_columns(data, [column], "Category mapping")
    lookup: dict[str, str] = {}
    for source, target in mapping.items():
        key = source.strip().casefold() if case_insensitive else source
        if key in lookup and lookup[key] != target:
            raise ConfigError(
                f"Category mapping for {column!r} is contradictory: {source!r} matches a key that "
                f"already maps to {lookup[key]!r}, but maps to {target!r}."
            )
        lookup[key] = target

    report = StepReport("map_categories", rule={"column": column, "mapping": dict(mapping), "case_insensitive": case_insensitive})
    series = data[column].astype("string")

    def convert(value: object) -> object:
        if pd.isna(value):
            return pd.NA
        key = str(value).strip().casefold() if case_insensitive else str(value)
        return lookup.get(key, value)

    new = series.map(convert).astype("string")
    report.record_changes(column, series, new)

    applied = (
        pd.DataFrame({"from": series, "to": new})[series.ne(new).fillna(False)]
        .value_counts()
        .reset_index(name="count")
    )
    targets = set(mapping.values())
    unmapped = new[new.notna() & series.eq(new).fillna(False) & ~new.isin(targets)].value_counts()
    report.details = {
        "replacements": [
            {"from": str(r["from"]), "to": str(r["to"]), "count": int(r["count"])} for _, r in applied.iterrows()
        ],
        "unmapped_values": {str(v): int(n) for v, n in unmapped.head(50).items()},
    }
    if len(unmapped):
        report.warnings.append(
            f"Column {column!r}: {len(unmapped)} distinct value(s) are not covered by the category "
            f"mapping and were left unchanged (e.g. {', '.join(repr(str(v)) for v in unmapped.index[:3])})."
        )
    result = data.copy()
    result[column] = new
    return result, report


# --------------------------------------------------------------------------- dates


def parse_dates(
    data: pd.DataFrame,
    column: str,
    formats: Sequence[str],
    *,
    output_format: str = "%Y-%m-%d",
    on_error: str = "keep",
) -> tuple[pd.DataFrame, StepReport]:
    """Convert date text to a single output format using explicitly configured input formats.

    Each value is tried against every format in ``formats``. A value is converted
    only if exactly one distinct date results. If two formats give different dates
    (for example ``03/04/2024`` with both ``%d/%m/%Y`` and ``%m/%d/%Y``), the value is
    reported as ambiguous and **not** converted. Impossible dates such as
    ``2024-02-30`` are reported as invalid.

    Args:
        formats: ``datetime.strptime`` formats, e.g. ``["%Y-%m-%d", "%d/%m/%Y"]``.
        output_format: ``strftime`` format for converted values (ISO 8601 by default).
        on_error: ``"keep"`` leaves unconvertible values unchanged (default);
            ``"set_missing"`` replaces them with missing values. Either way every
            failure is listed in the report with its original value.
    """
    formats = list(formats)
    if not formats:
        raise ConfigError(f"Date parsing for column {column!r} needs at least one input format.")
    _check_option("on_error", on_error, ON_ERROR_OPTIONS)
    require_columns(data, [column], "Date parsing")
    for fmt in formats + [output_format]:
        if "%" not in fmt:
            raise ConfigError(f"Invalid date format {fmt!r}: use strptime codes such as %Y-%m-%d.")

    report = StepReport(
        "parse_dates", rule={"column": column, "formats": formats, "output_format": output_format, "on_error": on_error}
    )
    if any("%y" in fmt for fmt in formats):
        report.warnings.append(
            f"Column {column!r}: two-digit years (%y) are interpreted by Python as 1969-2068; check old dates."
        )
    series = data[column].astype("string")
    converted: list[object] = []
    stats = {"converted": 0, "invalid": 0, "ambiguous": 0}
    for row, value in series.items():
        if pd.isna(value):
            converted.append(pd.NA)
            continue
        text = str(value).strip()
        results: dict[dt.datetime, str] = {}
        for fmt in formats:
            try:
                results.setdefault(dt.datetime.strptime(text, fmt), fmt)
            except ValueError:
                continue
        if len(results) == 1:
            converted.append(next(iter(results)).strftime(output_format))
            stats["converted"] += 1
            continue
        if results:
            readings = ", ".join(f"{fmt} -> {parsed.strftime(output_format)}" for parsed, fmt in results.items())
            reason = f"ambiguous date: {readings}"
            stats["ambiguous"] += 1
        else:
            reason = "does not match any configured date format (or is not a real calendar date)"
            stats["invalid"] += 1
        report.issues.append({"source_row": int(row), "column": column, "value": str(value), "reason": reason})
        converted.append(value if on_error == "keep" else pd.NA)

    new = pd.Series(converted, index=series.index, dtype="string")
    report.record_changes(column, series, new)
    report.details = stats
    failures = stats["invalid"] + stats["ambiguous"]
    if failures:
        action = "left unchanged" if on_error == "keep" else "set to missing"
        report.warnings.append(f"Column {column!r}: {failures} date value(s) could not be converted and were {action}.")
    result = data.copy()
    result[column] = new
    return result, report


# --------------------------------------------------------------------------- numbers


def parse_numbers(
    data: pd.DataFrame,
    column: str,
    *,
    decimal: str = ".",
    thousands: str | None = None,
    strip_chars: str = "",
    allow_leading_zeros: bool = False,
    on_error: str = "keep",
) -> tuple[pd.DataFrame, StepReport]:
    """Convert numeric text to numbers using explicit separator rules.

    Values must match the configured format exactly: with ``decimal=","`` and
    ``thousands="."``, ``"1.234,5"`` becomes 1234.5 while ``"1,234.5"`` is reported
    as a failure rather than guessed. Thousands separators must group digits by 3.

    Args:
        decimal: Decimal separator, ``"."`` or ``","``.
        thousands: Thousands separator (``","``, ``"."``, ``" "``, ``"'"``) or ``None``.
            ``" "`` also accepts non-breaking spaces.
        strip_chars: Characters removed before parsing, e.g. currency symbols ``"$€"``.
        allow_leading_zeros: By default values such as ``"007"`` are refused because
            converting them would lose the leading zeros (they are usually codes).
        on_error: ``"keep"`` (default) or ``"set_missing"``; see :func:`parse_dates`.

    The column becomes ``Int64`` if every converted value is a whole number, otherwise
    ``Float64``. If ``on_error="keep"`` and some values fail, the column stays text:
    converted values are written in canonical form and failures are left unchanged.
    """
    _check_option("decimal separator", decimal, DECIMAL_SEPARATORS)
    if thousands is not None:
        _check_option("thousands separator", thousands, THOUSANDS_SEPARATORS)
        if thousands == decimal:
            raise ConfigError("The decimal and thousands separators must be different.")
    _check_option("on_error", on_error, ON_ERROR_OPTIONS)
    if any(ch.isdigit() or ch in "+-" + decimal for ch in strip_chars):
        raise ConfigError(f"strip_chars {strip_chars!r} must not contain digits, signs or the decimal separator.")
    require_columns(data, [column], "Number parsing")

    group = "[" + re.escape(_SPACE_VARIANTS if thousands == " " else (thousands or "")) + "]"
    integer_part = rf"\d{{1,3}}(?:{group}\d{{3}})+|\d+" if thousands else r"\d+"
    pattern = re.compile(rf"(?P<sign>[+-])?(?P<int>{integer_part})?(?:{re.escape(decimal)}(?P<frac>\d+))?")
    report = StepReport(
        "parse_numbers",
        rule={
            "column": column,
            "decimal": decimal,
            "thousands": thousands,
            "strip_chars": strip_chars,
            "allow_leading_zeros": allow_leading_zeros,
            "on_error": on_error,
        },
    )
    series = data[column].astype("string")
    parsed: dict[object, Decimal] = {}
    for row, value in series.items():
        if pd.isna(value):
            continue
        text = str(value).strip()
        for ch in strip_chars:
            text = text.replace(ch, "")
        text = text.strip()
        match = pattern.fullmatch(text)
        reason = None
        if not match or not (match["int"] or match["frac"]):
            reason = "not a number in the configured format"
        else:
            digits = re.sub(r"\D", "", match["int"] or "")
            if not allow_leading_zeros and len(digits) > 1 and digits.startswith("0"):
                reason = "has leading zeros that would be lost (probably a code or identifier)"
            else:
                number = Decimal(f"{match['sign'] or ''}{digits or '0'}.{match['frac'] or '0'}")
                parsed[row] = number
                continue
        report.issues.append({"source_row": int(row), "column": column, "value": str(value), "reason": reason})

    all_integral = all(n == n.to_integral_value() for n in parsed.values())
    values: dict[object, int | float] = {}
    for row, number in parsed.items():
        if all_integral:
            as_int = int(number)
            if _INT64_MIN <= as_int <= _INT64_MAX:
                values[row] = as_int
                continue
            reason = "integer too large to store exactly"
        else:
            as_float = float(number)
            if Decimal(repr(as_float)) == number:
                values[row] = as_float
                continue
            reason = "too many significant digits to store exactly as a decimal number"
        report.issues.append({"source_row": int(row), "column": column, "value": str(series.at[row]), "reason": reason})

    failed_rows = {issue["source_row"] for issue in report.issues}
    dtype = "Int64" if all_integral else "Float64"
    numeric = pd.Series(pd.NA, index=series.index, dtype=dtype)
    for row, number in values.items():
        numeric.at[row] = number
    if failed_rows and on_error == "keep":
        canonical = render_text(numeric.to_frame(column))[column]
        new = canonical.where(numeric.notna(), series)
        report.warnings.append(
            f"Column {column!r}: {len(failed_rows)} value(s) could not be converted and were left unchanged; "
            "the column is kept as text."
        )
    else:
        new = numeric
        if failed_rows:
            report.warnings.append(f"Column {column!r}: {len(failed_rows)} value(s) could not be converted and were set to missing.")
    report.record_changes(column, series, new)
    report.details = {"converted": len(values), "failed": len(failed_rows), "result_dtype": str(new.dtype)}
    result = data.copy()
    result[column] = new
    return result, report


# --------------------------------------------------------------------------- duplicates


def handle_exact_duplicates(data: pd.DataFrame, *, remove: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, StepReport]:
    """Detect rows that are identical in every column and optionally remove the copies.

    The **first** occurrence of each group is kept; later copies are removed only
    when ``remove`` is True. Missing values compare equal to each other.

    Returns:
        ``(kept_rows, removed_rows, report)``.
    """
    report = StepReport("exact_duplicates", rule={"remove": remove, "keep": "first occurrence"})
    duplicated = data.duplicated(keep="first")
    groups = _groups(data, list(data.columns))
    report.details = {
        "duplicate_rows": int(duplicated.sum()),
        "groups": [{"source_rows": rows} for rows in groups],
    }
    if not remove:
        if duplicated.any():
            report.warnings.append(
                f"{int(duplicated.sum())} exact duplicate row(s) found and kept (removal was not requested)."
            )
        return data.copy(), data.iloc[0:0].copy(), report
    removed = data[duplicated]
    report.rows_removed = [int(r) for r in removed.index]
    return data[~duplicated].copy(), removed.copy(), report


def handle_key_duplicates(
    data: pd.DataFrame,
    keys: Sequence[str],
    *,
    remove: bool = False,
    keep: str = "first",
) -> tuple[pd.DataFrame, pd.DataFrame, StepReport]:
    """Detect rows sharing the same values in ``keys``; optionally keep one per key.

    Rows with a missing value in any key column are never treated as duplicates
    of each other. For each group the report says whether the rows are fully
    identical or which other columns differ, because rows that share an ID are not
    necessarily interchangeable (e.g. two legitimate orders by one customer).

    Args:
        keys: Key columns.
        remove: Remove all but one row per key. Off by default.
        keep: ``"first"`` or ``"last"`` (file order) -- the rule used to choose
            which row of a group is retained.

    Returns:
        ``(kept_rows, removed_rows, report)``.
    """
    keys = list(keys)
    if not keys:
        raise ConfigError("Key-based duplicate detection needs at least one key column.")
    _check_option("keep", keep, KEEP_OPTIONS)
    require_columns(data, keys, "Key-based duplicate detection")
    report = StepReport("key_duplicates", rule={"keys": keys, "remove": remove, "keep": keep})

    has_missing_key = data[keys].isna().any(axis=1)
    candidates = data[~has_missing_key]
    duplicated_any = candidates.duplicated(subset=keys, keep=False)
    others = [c for c in data.columns if c not in keys]
    groups = []
    conflicting = 0
    for rows in _groups(candidates[duplicated_any], keys):
        block = data.loc[rows, others]
        differing = [c for c in others if block[c].astype("string").fillna("\x00NA").nunique() > 1]
        conflicting += bool(differing)
        groups.append(
            {
                "key": {k: to_plain(data.at[rows[0], k]) for k in keys},
                "source_rows": rows,
                "identical": not differing,
                "differing_columns": differing,
            }
        )
    to_remove = candidates.duplicated(subset=keys, keep=keep)
    report.details = {
        "groups": groups,
        "duplicate_key_groups": len(groups),
        "rows_in_groups": int(duplicated_any.sum()),
        "groups_with_conflicting_values": conflicting,
        "rows_with_missing_key": int(has_missing_key.sum()),
    }
    if has_missing_key.any():
        report.warnings.append(
            f"{int(has_missing_key.sum())} row(s) have a missing value in {keys} and were excluded from key-duplicate checks."
        )
    if not remove:
        if groups:
            report.warnings.append(
                f"{len(groups)} key value(s) in {keys} appear on more than one row "
                f"({conflicting} with differing values in other columns); rows were kept (removal not requested)."
            )
        return data.copy(), data.iloc[0:0].copy(), report

    removed_index = to_remove[to_remove].index
    if conflicting:
        report.warnings.append(
            f"{conflicting} duplicate key group(s) had differing values in other columns; the {keep} row of each "
            "group was kept and the others were removed. Review the removed rows."
        )
    removed = data.loc[removed_index]
    report.rows_removed = [int(r) for r in removed_index]
    return data.drop(index=removed_index).copy(), removed.copy(), report


def _groups(data: pd.DataFrame, columns: list[str]) -> list[list[int]]:
    """Source rows of each group (size >= 2) sharing identical values in ``columns``."""
    groups: dict[tuple, list[int]] = {}
    for row, values in zip(data.index, data[columns].itertuples(index=False, name=None)):
        key = tuple("\x00NA" if pd.isna(v) else v for v in values)
        groups.setdefault(key, []).append(int(row))
    return [rows for rows in groups.values() if len(rows) > 1]
