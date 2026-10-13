"""Configurable validation rules.

Validation never changes values. Each rule produces issues (one per failing
cell or row) and declares an ``action``:

* ``"report"`` (default): the row stays in the cleaned output; the issue is reported.
* ``"quarantine"``: the row is moved to a separate quarantine file with the reason,
  so that nothing is deleted silently.

Missing values are ignored by every rule except ``not_null``, so that "missing"
and "invalid" are reported separately.

Supported rules (``rule`` key) and their parameters:

=================  ============================================================
``required_columns``  ``columns``: list of column names that must exist
``not_null``          ``column``
``type``              ``column``, ``expected``: ``integer`` | ``number`` | ``date``,
                      optional ``format`` for dates (default ``%Y-%m-%d``)
``allowed_values``    ``column``, ``values``, optional ``case_sensitive`` (default true)
``range``             ``column``, ``min`` and/or ``max`` (inclusive, numeric)
``date_range``        ``column``, ``min`` and/or ``max`` (dates in ``format``),
                      optional ``format`` (default ``%Y-%m-%d``)
``pattern``           ``column``, ``regex`` (must match the whole value)
``unique``            ``columns``: list; rows sharing a non-missing combination fail
=================  ============================================================
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

import pandas as pd

from .errors import ConfigError
from .models import to_plain

ACTIONS = ("report", "quarantine")
QUARANTINE_REASON_COLUMN = "quarantine_reason"

_RULE_PARAMETERS: dict[str, tuple[set[str], set[str]]] = {
    # rule: (required parameters, optional parameters)
    "required_columns": ({"columns"}, set()),
    "not_null": ({"column"}, set()),
    "type": ({"column", "expected"}, {"format"}),
    "allowed_values": ({"column", "values"}, {"case_sensitive"}),
    "range": ({"column"}, {"min", "max"}),
    "date_range": ({"column"}, {"min", "max", "format"}),
    "pattern": ({"column", "regex"}, set()),
    "unique": ({"columns"}, set()),
}
_COMMON_PARAMETERS = {"rule", "id", "action", "description"}
_EXPECTED_TYPES = ("integer", "number", "date")


@dataclass
class Rule:
    """A parsed, validated rule definition."""

    id: str
    rule: str
    params: dict[str, Any]
    action: str = "report"
    description: str | None = None

    @property
    def columns(self) -> list[str]:
        if "column" in self.params:
            return [self.params["column"]]
        return list(self.params.get("columns", []))

    def label(self) -> str:
        return self.description or f"{self.rule}({', '.join(self.columns)})"


@dataclass
class ValidationResult:
    """Issues found by the rules plus a per-rule summary."""

    rules: list[Rule]
    issues: list[dict[str, Any]] = field(default_factory=list)
    rule_status: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(status["status"] == "passed" for status in self.rule_status.values())

    def quarantine_reasons(self) -> dict[int, list[str]]:
        """Map each source row to quarantine to the messages that caused it."""
        reasons: dict[int, list[str]] = {}
        for issue in self.issues:
            if issue["action"] == "quarantine" and issue["source_row"] is not None:
                reasons.setdefault(issue["source_row"], []).append(f"[{issue['rule_id']}] {issue['message']}")
        return reasons

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "rules": list(self.rule_status.values()),
            "issue_count": len(self.issues),
            # One row can fail several rules, so issue_count can exceed the number of affected rows.
            "rows_with_issues": len({i["source_row"] for i in self.issues if i["source_row"] is not None}),
            "issues": list(self.issues),
        }


def parse_rules(definitions: Sequence[Mapping[str, Any]]) -> list[Rule]:
    """Validate raw rule dictionaries (e.g. from a JSON config) and build ``Rule`` objects.

    Raises:
        ConfigError: Unknown rule type, unknown/missing parameters, bad values or duplicate ids.
    """
    rules: list[Rule] = []
    seen_ids: set[str] = set()
    for position, definition in enumerate(definitions, start=1):
        where = f"Validation rule #{position}"
        if not isinstance(definition, Mapping):
            raise ConfigError(f"{where} must be an object.")
        kind = definition.get("rule")
        if kind not in _RULE_PARAMETERS:
            raise ConfigError(f"{where}: unknown rule {kind!r}. Known rules: {', '.join(_RULE_PARAMETERS)}")
        required, optional = _RULE_PARAMETERS[kind]
        params = {k: v for k, v in definition.items() if k not in _COMMON_PARAMETERS}
        unknown = set(params) - required - optional
        if unknown:
            raise ConfigError(f"{where} ({kind}): unknown parameter(s) {sorted(unknown)}.")
        absent = required - set(params)
        if absent:
            raise ConfigError(f"{where} ({kind}): missing parameter(s) {sorted(absent)}.")
        action = definition.get("action", "report")
        if action not in ACTIONS:
            raise ConfigError(f"{where} ({kind}): action must be one of {ACTIONS}, got {action!r}.")
        rule_id = str(definition.get("id", f"R{position}"))
        if rule_id in seen_ids:
            raise ConfigError(f"{where}: duplicate rule id {rule_id!r}.")
        seen_ids.add(rule_id)
        _check_params(kind, params, where)
        rules.append(Rule(rule_id, kind, params, action, definition.get("description")))
    return rules


def _check_params(kind: str, params: dict[str, Any], where: str) -> None:
    if "columns" in params and (
        not isinstance(params["columns"], list) or not params["columns"] or not all(isinstance(c, str) for c in params["columns"])
    ):
        raise ConfigError(f"{where} ({kind}): 'columns' must be a non-empty list of column names.")
    if "column" in params and not isinstance(params["column"], str):
        raise ConfigError(f"{where} ({kind}): 'column' must be a column name.")
    if kind == "type" and params["expected"] not in _EXPECTED_TYPES:
        raise ConfigError(f"{where}: 'expected' must be one of {_EXPECTED_TYPES}.")
    if kind == "allowed_values" and (not isinstance(params["values"], list) or not params["values"]):
        raise ConfigError(f"{where}: 'values' must be a non-empty list.")
    if kind in ("range", "date_range") and "min" not in params and "max" not in params:
        raise ConfigError(f"{where} ({kind}): set 'min', 'max' or both.")
    if kind == "range":
        for bound in ("min", "max"):
            if bound in params and (isinstance(params[bound], bool) or not isinstance(params[bound], (int, float))):
                raise ConfigError(f"{where}: '{bound}' must be a number.")
    if kind == "date_range":
        fmt = params.get("format", "%Y-%m-%d")
        for bound in ("min", "max"):
            if bound in params:
                try:
                    dt.datetime.strptime(str(params[bound]), fmt)
                except ValueError as exc:
                    raise ConfigError(f"{where}: '{bound}' {params[bound]!r} does not match format {fmt!r}.") from exc
    if kind == "pattern":
        try:
            re.compile(params["regex"])
        except (re.error, TypeError) as exc:
            raise ConfigError(f"{where}: invalid regular expression {params['regex']!r}: {exc}") from exc


def validate(data: pd.DataFrame, rules: Sequence[Rule]) -> ValidationResult:
    """Evaluate ``rules`` against ``data`` without modifying it.

    A rule that refers to a missing column is marked ``not_evaluated`` and counts as
    a failure: it is never silently skipped.
    """
    result = ValidationResult(list(rules))
    for rule in rules:
        missing_columns = [c for c in rule.columns if c not in data.columns]
        status = {"id": rule.id, "rule": rule.rule, "label": rule.label(), "columns": rule.columns, "action": rule.action}
        if rule.rule == "required_columns":
            for column in missing_columns:
                _add(result, rule, None, column, None, f"required column {column!r} is missing")
            status.update(status="failed" if missing_columns else "passed", failures=len(missing_columns))
            result.rule_status[rule.id] = status
            continue
        if missing_columns:
            message = f"rule not evaluated: column(s) {missing_columns} not found"
            _add(result, rule, None, missing_columns[0], None, message)
            status.update(status="not_evaluated", failures=None, message=message)
            result.rule_status[rule.id] = status
            continue
        before = len(result.issues)
        _CHECKS[rule.rule](data, rule, result)
        failures = len(result.issues) - before
        status.update(status="failed" if failures else "passed", failures=failures)
        result.rule_status[rule.id] = status
    return result


def split_quarantine(data: pd.DataFrame, result: ValidationResult) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate rows flagged by ``quarantine`` rules.

    Returns:
        ``(kept_rows, quarantined_rows)``; quarantined rows get an extra
        ``quarantine_reason`` column listing every rule they failed.
    """
    reasons = result.quarantine_reasons()
    if QUARANTINE_REASON_COLUMN in data.columns:
        raise ConfigError(f"The dataset already has a column named {QUARANTINE_REASON_COLUMN!r}; rename it before quarantining.")
    flagged = data.index.isin(list(reasons))
    quarantined = data[flagged].copy()
    quarantined[QUARANTINE_REASON_COLUMN] = pd.Series(
        ["; ".join(reasons[int(row)]) for row in quarantined.index], index=quarantined.index, dtype="string"
    )
    return data[~flagged].copy(), quarantined


# --------------------------------------------------------------------------- rule checks


def _add(result: ValidationResult, rule: Rule, row: Any, column: str | None, value: Any, message: str) -> None:
    result.issues.append(
        {
            "rule_id": rule.id,
            "rule": rule.rule,
            "column": column,
            "source_row": None if row is None else int(row),
            "value": to_plain(value),
            "message": message,
            "action": rule.action,
        }
    )


def _present(data: pd.DataFrame, column: str) -> pd.Series:
    return data[column][data[column].notna()]


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    if hasattr(value, "item"):
        return _as_decimal(value.item())
    text = str(value).strip()
    if not re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)", text):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _check_not_null(data: pd.DataFrame, rule: Rule, result: ValidationResult) -> None:
    column = rule.params["column"]
    for row in data.index[data[column].isna()]:
        _add(result, rule, row, column, None, f"{column!r} is missing")


def _check_type(data: pd.DataFrame, rule: Rule, result: ValidationResult) -> None:
    column, expected = rule.params["column"], rule.params["expected"]
    fmt = rule.params.get("format", "%Y-%m-%d")
    for row, value in _present(data, column).items():
        if expected == "date":
            try:
                dt.datetime.strptime(str(value).strip(), fmt)
                continue
            except ValueError:
                message = f"{value!r} is not a date in format {fmt}"
        else:
            number = _as_decimal(value)
            if number is not None and (expected == "number" or number == number.to_integral_value()):
                continue
            message = f"{value!r} is not {'an integer' if expected == 'integer' else 'a number'}"
        _add(result, rule, row, column, value, message)


def _check_allowed_values(data: pd.DataFrame, rule: Rule, result: ValidationResult) -> None:
    column = rule.params["column"]
    allowed = [str(v) for v in rule.params["values"]]
    case_sensitive = rule.params.get("case_sensitive", True)
    allowed_set = set(allowed) if case_sensitive else {v.casefold() for v in allowed}
    for row, value in _present(data, column).items():
        text = str(value) if case_sensitive else str(value).casefold()
        if text not in allowed_set:
            _add(result, rule, row, column, value, f"{value!r} is not an allowed value")


def _check_range(data: pd.DataFrame, rule: Rule, result: ValidationResult) -> None:
    column = rule.params["column"]
    low, high = rule.params.get("min"), rule.params.get("max")
    for row, value in _present(data, column).items():
        number = _as_decimal(value)
        if number is None:
            _add(result, rule, row, column, value, f"{value!r} is not a number; range cannot be checked")
        elif low is not None and number < _as_decimal(low):
            _add(result, rule, row, column, value, f"{value} is below the minimum {low}")
        elif high is not None and number > _as_decimal(high):
            _add(result, rule, row, column, value, f"{value} is above the maximum {high}")


def _check_date_range(data: pd.DataFrame, rule: Rule, result: ValidationResult) -> None:
    column = rule.params["column"]
    fmt = rule.params.get("format", "%Y-%m-%d")
    low = dt.datetime.strptime(str(rule.params["min"]), fmt) if "min" in rule.params else None
    high = dt.datetime.strptime(str(rule.params["max"]), fmt) if "max" in rule.params else None
    for row, value in _present(data, column).items():
        try:
            date = dt.datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            _add(result, rule, row, column, value, f"{value!r} is not a date in format {fmt}; range cannot be checked")
            continue
        if low is not None and date < low:
            _add(result, rule, row, column, value, f"{value} is before {rule.params['min']}")
        elif high is not None and date > high:
            _add(result, rule, row, column, value, f"{value} is after {rule.params['max']}")


def _check_pattern(data: pd.DataFrame, rule: Rule, result: ValidationResult) -> None:
    column = rule.params["column"]
    regex = re.compile(rule.params["regex"])
    for row, value in _present(data, column).items():
        if not regex.fullmatch(str(value)):
            _add(result, rule, row, column, value, f"{value!r} does not match the pattern {rule.params['regex']}")


def _check_unique(data: pd.DataFrame, rule: Rule, result: ValidationResult) -> None:
    columns = rule.params["columns"]
    complete = data[data[columns].notna().all(axis=1)]
    duplicated = complete.duplicated(subset=columns, keep=False)
    for row in complete.index[duplicated]:
        values = {c: to_plain(data.at[row, c]) for c in columns}
        _add(result, rule, row, ", ".join(columns), values, f"value(s) {values} are not unique")


_CHECKS = {
    "not_null": _check_not_null,
    "type": _check_type,
    "allowed_values": _check_allowed_values,
    "range": _check_range,
    "date_range": _check_date_range,
    "pattern": _check_pattern,
    "unique": _check_unique,
}
