"""Loading and strict validation of the JSON cleaning configuration.

Every key is optional; omitted keys take the documented defaults below. Unknown
keys, wrong types and invalid values raise :class:`ConfigError` so that a typo
can never cause a requested operation to be silently skipped.

Column names in ``text``, ``categories``, ``dates``, ``numbers``, ``duplicates`` and
``validation`` refer to the names **after** column-name normalization.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .cleaning import (
    COLUMN_NAME_STYLES,
    DECIMAL_SEPARATORS,
    KEEP_OPTIONS,
    ON_ERROR_OPTIONS,
    TEXT_CASES,
    THOUSANDS_SEPARATORS,
)
from .errors import ConfigError
from .validation import parse_rules

#: Defaults applied when a key is omitted. Lists of rules default to empty (no operation).
DEFAULTS: dict[str, Any] = {
    "description": None,
    "input": {"sheet": None, "encoding": None, "delimiter": None},
    "output": {"csv_encoding": "utf-8", "csv_delimiter": ",", "sheet_name": "cleaned"},
    "column_names": {"strip": True, "collapse_whitespace": True, "style": None, "rename": {}},
    "missing_values": {"tokens": [], "case_sensitive": False, "whitespace_as_missing": True},
    "text": [],
    "categories": [],
    "dates": [],
    "numbers": [],
    "duplicates": {"remove_exact": False, "key_columns": [], "remove_key_duplicates": False, "keep": "first"},
    "validation": [],
}

_TEXT_DEFAULTS = {"strip": True, "collapse_whitespace": False, "case": None}
_CATEGORY_DEFAULTS = {"case_insensitive": False}
_DATE_DEFAULTS = {"output_format": "%Y-%m-%d", "on_error": "keep"}
_NUMBER_DEFAULTS = {"decimal": ".", "thousands": None, "strip_chars": "", "allow_leading_zeros": False, "on_error": "keep"}


def default_config() -> dict[str, Any]:
    """Return a fresh copy of the default configuration."""
    return copy.deepcopy(DEFAULTS)


def load_config(path: str | os.PathLike[str] | None) -> dict[str, Any]:
    """Load and validate a JSON configuration file (``None`` gives the defaults)."""
    if path is None:
        return default_config()
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"Configuration file not found: {config_path}")
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path.name} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"Cannot read configuration file {config_path}: {exc}") from exc
    return validate_config(raw)


def validate_config(raw: Any) -> dict[str, Any]:
    """Validate a configuration object and return it with all defaults filled in."""
    if not isinstance(raw, Mapping):
        raise ConfigError("The configuration must be a JSON object.")
    _no_unknown_keys(raw, DEFAULTS, "configuration")
    config = default_config()

    if "description" in raw:
        config["description"] = _string(raw["description"], "description", allow_none=True)

    section = _section(raw, "input")
    config["input"].update(section)
    for key in ("sheet", "encoding"):
        _string(config["input"][key], f"input.{key}", allow_none=True)
    _single_char(config["input"]["delimiter"], "input.delimiter", allow_none=True)

    section = _section(raw, "output")
    config["output"].update(section)
    _string(config["output"]["csv_encoding"], "output.csv_encoding")
    _single_char(config["output"]["csv_delimiter"], "output.csv_delimiter")
    sheet_name = _string(config["output"]["sheet_name"], "output.sheet_name")
    if not sheet_name or len(sheet_name) > 31 or any(ch in sheet_name for ch in "[]:*?/\\"):
        raise ConfigError("output.sheet_name must be 1-31 characters and must not contain []:*?/\\")

    section = _section(raw, "column_names")
    config["column_names"].update(section)
    names = config["column_names"]
    _bool(names["strip"], "column_names.strip")
    _bool(names["collapse_whitespace"], "column_names.collapse_whitespace")
    _choice(names["style"], COLUMN_NAME_STYLES, "column_names.style", allow_none=True)
    _string_map(names["rename"], "column_names.rename", allow_empty=True)

    section = _section(raw, "missing_values")
    config["missing_values"].update(section)
    missing = config["missing_values"]
    tokens = _string_list(missing["tokens"], "missing_values.tokens", allow_empty=True)
    if any(t.strip() == "" for t in tokens):
        raise ConfigError("missing_values.tokens must not contain empty or whitespace-only strings.")
    _bool(missing["case_sensitive"], "missing_values.case_sensitive")
    _bool(missing["whitespace_as_missing"], "missing_values.whitespace_as_missing")

    config["text"] = [_text_rule(item, f"text[{i}]") for i, item in enumerate(_list(raw, "text"))]
    config["categories"] = [_category_rule(item, f"categories[{i}]") for i, item in enumerate(_list(raw, "categories"))]
    config["dates"] = [_date_rule(item, f"dates[{i}]") for i, item in enumerate(_list(raw, "dates"))]
    config["numbers"] = [_number_rule(item, f"numbers[{i}]") for i, item in enumerate(_list(raw, "numbers"))]

    section = _section(raw, "duplicates")
    config["duplicates"].update(section)
    duplicates = config["duplicates"]
    _bool(duplicates["remove_exact"], "duplicates.remove_exact")
    _string_list(duplicates["key_columns"], "duplicates.key_columns", allow_empty=True)
    _bool(duplicates["remove_key_duplicates"], "duplicates.remove_key_duplicates")
    _choice(duplicates["keep"], KEEP_OPTIONS, "duplicates.keep")
    if duplicates["remove_key_duplicates"] and not duplicates["key_columns"]:
        raise ConfigError("duplicates.remove_key_duplicates requires duplicates.key_columns.")

    if "validation" in raw:
        if not isinstance(raw["validation"], list):
            raise ConfigError("validation must be a list of rules.")
        parse_rules(raw["validation"])  # raises ConfigError on any invalid rule
        config["validation"] = copy.deepcopy(raw["validation"])

    _no_conflicting_columns(config)
    return config


def referenced_columns(config: Mapping[str, Any]) -> list[tuple[str, str]]:
    """``(section, column)`` pairs that must exist after column-name normalization.

    Validation rules are excluded: a missing column there is reported by the rule
    itself (``required_columns`` or ``not_evaluated``) instead of aborting the run.
    """
    pairs: list[tuple[str, str]] = []
    for i, rule in enumerate(config["text"]):
        pairs += [(f"text[{i}]", c) for c in rule["columns"]]
    for section in ("categories", "dates", "numbers"):
        pairs += [(f"{section}[{i}]", rule["column"]) for i, rule in enumerate(config[section])]
    pairs += [("duplicates.key_columns", c) for c in config["duplicates"]["key_columns"]]
    return pairs


# --------------------------------------------------------------------------- rule sections


def _text_rule(item: Any, where: str) -> dict[str, Any]:
    rule = _rule(item, where, required={"columns"}, defaults=_TEXT_DEFAULTS)
    columns = _string_list(rule["columns"], f"{where}.columns")
    if len(set(columns)) != len(columns):
        raise ConfigError(f"{where}.columns lists a column more than once.")
    _bool(rule["strip"], f"{where}.strip")
    _bool(rule["collapse_whitespace"], f"{where}.collapse_whitespace")
    _choice(rule["case"], TEXT_CASES, f"{where}.case", allow_none=True)
    if not (rule["strip"] or rule["collapse_whitespace"] or rule["case"]):
        raise ConfigError(f"{where} enables no operation; set strip, collapse_whitespace or case.")
    return rule


def _category_rule(item: Any, where: str) -> dict[str, Any]:
    rule = _rule(item, where, required={"column", "mapping"}, defaults=_CATEGORY_DEFAULTS)
    _string(rule["column"], f"{where}.column")
    _string_map(rule["mapping"], f"{where}.mapping")
    _bool(rule["case_insensitive"], f"{where}.case_insensitive")
    if rule["case_insensitive"]:
        targets: dict[str, str] = {}
        for source, target in rule["mapping"].items():
            key = source.strip().casefold()
            if targets.setdefault(key, target) != target:
                raise ConfigError(f"{where}.mapping is contradictory for {source!r} when matching case-insensitively.")
    return rule


def _date_rule(item: Any, where: str) -> dict[str, Any]:
    rule = _rule(item, where, required={"column", "formats"}, defaults=_DATE_DEFAULTS)
    _string(rule["column"], f"{where}.column")
    for fmt in _string_list(rule["formats"], f"{where}.formats") + [_string(rule["output_format"], f"{where}.output_format")]:
        if "%" not in fmt:
            raise ConfigError(f"{where}: {fmt!r} is not a strptime format (use codes such as %Y-%m-%d).")
    _choice(rule["on_error"], ON_ERROR_OPTIONS, f"{where}.on_error")
    return rule


def _number_rule(item: Any, where: str) -> dict[str, Any]:
    rule = _rule(item, where, required={"column"}, defaults=_NUMBER_DEFAULTS)
    _string(rule["column"], f"{where}.column")
    _choice(rule["decimal"], DECIMAL_SEPARATORS, f"{where}.decimal")
    _choice(rule["thousands"], THOUSANDS_SEPARATORS, f"{where}.thousands", allow_none=True)
    if rule["thousands"] == rule["decimal"]:
        raise ConfigError(f"{where}: decimal and thousands separators must differ.")
    strip_chars = _string(rule["strip_chars"], f"{where}.strip_chars")
    if any(ch.isdigit() or ch in "+-" + rule["decimal"] for ch in strip_chars):
        raise ConfigError(f"{where}.strip_chars must not contain digits, signs or the decimal separator.")
    _bool(rule["allow_leading_zeros"], f"{where}.allow_leading_zeros")
    _choice(rule["on_error"], ON_ERROR_OPTIONS, f"{where}.on_error")
    return rule


def _no_conflicting_columns(config: dict[str, Any]) -> None:
    seen: dict[str, str] = {}
    for section in ("dates", "numbers"):
        for i, rule in enumerate(config[section]):
            where = f"{section}[{i}]"
            if rule["column"] in seen:
                raise ConfigError(f"Column {rule['column']!r} is configured in both {seen[rule['column']]} and {where}.")
            seen[rule["column"]] = where
    text_seen: dict[str, str] = {}
    for i, rule in enumerate(config["text"]):
        for column in rule["columns"]:
            if column in text_seen:
                raise ConfigError(f"Column {column!r} appears in both {text_seen[column]} and text[{i}].")
            text_seen[column] = f"text[{i}]"
    category_seen: set[str] = set()
    for i, rule in enumerate(config["categories"]):
        if rule["column"] in category_seen:
            raise ConfigError(f"Column {rule['column']!r} has more than one category mapping (categories[{i}]); merge them.")
        category_seen.add(rule["column"])


# --------------------------------------------------------------------------- primitive checks


def _no_unknown_keys(obj: Mapping[str, Any], allowed: Mapping[str, Any] | set[str], where: str) -> None:
    unknown = sorted(set(obj) - set(allowed))
    if unknown:
        raise ConfigError(f"Unknown key(s) in {where}: {', '.join(unknown)}. Allowed: {', '.join(sorted(allowed))}")


def _section(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, Mapping):
        raise ConfigError(f"{name} must be an object.")
    _no_unknown_keys(value, DEFAULTS[name], name)
    return dict(value)


def _list(raw: Mapping[str, Any], name: str) -> list[Any]:
    value = raw.get(name, [])
    if not isinstance(value, list):
        raise ConfigError(f"{name} must be a list.")
    return value


def _rule(item: Any, where: str, *, required: set[str], defaults: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ConfigError(f"{where} must be an object.")
    _no_unknown_keys(item, set(required) | set(defaults), where)
    absent = sorted(required - set(item))
    if absent:
        raise ConfigError(f"{where} is missing required key(s): {', '.join(absent)}")
    rule = dict(defaults)
    rule.update(copy.deepcopy(dict(item)))
    return rule


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{where} must be true or false, got {value!r}.")
    return value


def _string(value: Any, where: str, *, allow_none: bool = False) -> Any:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{where} must be a string, got {value!r}.")
    return value


def _single_char(value: Any, where: str, *, allow_none: bool = False) -> Any:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or len(value) != 1:
        raise ConfigError(f"{where} must be a single character, got {value!r}.")
    return value


def _choice(value: Any, allowed: tuple, where: str, *, allow_none: bool = False) -> Any:
    if value is None and allow_none:
        return None
    if value not in allowed:
        options = ", ".join(repr(a) for a in allowed) + (", null" if allow_none else "")
        raise ConfigError(f"{where} must be one of {options}; got {value!r}.")
    return value


def _string_list(value: Any, where: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where} must be a list of strings.")
    if not value and not allow_empty:
        raise ConfigError(f"{where} must not be empty.")
    return value


def _string_map(value: Any, where: str, *, allow_empty: bool = False) -> dict[str, str]:
    if not isinstance(value, Mapping) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise ConfigError(f"{where} must be an object mapping strings to strings.")
    if not value and not allow_empty:
        raise ConfigError(f"{where} must not be empty.")
    return dict(value)
