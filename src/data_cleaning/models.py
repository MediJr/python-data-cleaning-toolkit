"""Shared result structures used by the cleaning, validation and reporting modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

#: Name of the DataFrame index that carries the row number in the original file.
#: For CSV it is the physical line number where the record starts (header = line 1);
#: for XLSX it is the worksheet row number.
SOURCE_ROW = "source_row"

#: Maximum number of before/after examples kept per column in a step report.
MAX_EXAMPLES = 5


@dataclass
class StepReport:
    """Record of what one processing step did.

    Attributes:
        step: Machine-readable step name, e.g. ``"normalize_text"``.
        rule: The parameters the step was run with (copied into reports).
        cells_changed: Number of changed cells per column.
        rows_removed: Source row numbers of rows removed by this step.
        examples: Up to ``MAX_EXAMPLES`` before/after examples per column.
        issues: Values the step could not process, one dict per value
            (``source_row``, ``column``, ``value``, ``reason``).
        warnings: Human-readable warnings.
        details: Step-specific extra information (e.g. column-name mapping).
    """

    step: str
    rule: dict[str, Any] = field(default_factory=dict)
    cells_changed: dict[str, int] = field(default_factory=dict)
    rows_removed: list[int] = field(default_factory=list)
    examples: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def total_cells_changed(self) -> int:
        return sum(self.cells_changed.values())

    def record_changes(self, column: str, before: pd.Series, after: pd.Series) -> None:
        """Count cells that differ between ``before`` and ``after`` and keep examples.

        Missing values compare equal to each other; a missing value and a present
        value compare different.
        """
        mask = changed_mask(before, after)
        count = int(mask.sum())
        if count == 0:
            return
        self.cells_changed[column] = self.cells_changed.get(column, 0) + count
        kept = self.examples.setdefault(column, [])
        for row in before.index[mask]:
            if len(kept) >= MAX_EXAMPLES:
                break
            kept.append(
                {
                    "source_row": int(row),
                    "before": to_plain(before.at[row]),
                    "after": to_plain(after.at[row]),
                }
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "rule": self.rule,
            "cells_changed": dict(self.cells_changed),
            "total_cells_changed": self.total_cells_changed,
            "rows_removed": list(self.rows_removed),
            "examples": self.examples,
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "details": self.details,
        }


def changed_mask(before: pd.Series, after: pd.Series) -> pd.Series:
    """Boolean mask of positions where two aligned Series differ (NA-aware)."""
    before_text = before.astype("string")
    after_text = after.astype("string")
    differs = before_text.ne(after_text).fillna(False)
    return (differs | (before_text.isna() ^ after_text.isna())).astype(bool)


def to_plain(value: Any) -> Any:
    """Convert pandas/numpy scalars to JSON-friendly Python values (NA -> None)."""
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value
