"""End-to-end cleaning workflow.

Processing order (fixed and documented, so results are reproducible):

1. Plan every output path and refuse to start if any would overwrite a file
   without permission or touch the input file.
2. Fingerprint (SHA-256) and read the input file as text.
3. Profile the raw data.
4. Column names -> missing values -> text -> category mappings -> dates -> numbers
   -> exact duplicates -> key duplicates -> validation -> quarantine.
5. Export the cleaned data, quarantined rows and removed rows (each verified by
   reopening), profile the result, confirm the input fingerprint is unchanged.
6. Write the JSON and Markdown reports.

If a step fails after the input was read, a report with ``execution.status =
"failed"`` is still written, listing the files that were (or were not) produced.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from . import __version__
from .cleaning import (
    handle_exact_duplicates,
    handle_key_duplicates,
    map_categories,
    normalize_column_names,
    normalize_text,
    parse_dates,
    parse_numbers,
    standardize_missing,
)
from .config import default_config, referenced_columns
from .errors import ConfigError, DataCleaningError, ExportError, MissingColumnError
from .io import (
    SUPPORTED_FORMATS,
    ExportResult,
    LoadedTable,
    check_output_path,
    read_table,
    render_text,
    write_table,
    write_text_file,
)
from .models import StepReport
from .profiling import profile_dataframe
from .validation import ValidationResult, parse_rules, split_quarantine, validate

logger = logging.getLogger(__name__)

REMOVAL_REASON_COLUMN = "removal_reason"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_QUALITY_ISSUES = 3


@dataclass
class OutputPlan:
    """All files a cleaning run may write."""

    output: Path
    quarantine: Path
    removed_rows: Path
    report_json: Path
    report_markdown: Path

    def all_paths(self) -> list[Path]:
        return [self.output, self.quarantine, self.removed_rows, self.report_json, self.report_markdown]


def plan_outputs(output_path: str | os.PathLike[str], report_dir: str | os.PathLike[str] | None = None) -> OutputPlan:
    """Derive companion file names from the output path.

    ``cleaned.csv`` gives ``cleaned_quarantine.csv``, ``cleaned_removed_rows.csv``,
    ``cleaned_report.json`` and ``cleaned_report.md`` (reports go to ``report_dir``
    when given, otherwise next to the output).
    """
    output = Path(output_path)
    if output.suffix.lower() not in SUPPORTED_FORMATS:
        raise ExportError(f"Unsupported output type '{output.suffix or '(none)'}' for {output.name}. Use .csv or .xlsx.")
    reports = Path(report_dir) if report_dir is not None else output.parent
    stem, suffix = output.stem, output.suffix
    return OutputPlan(
        output=output,
        quarantine=output.with_name(f"{stem}_quarantine{suffix}"),
        removed_rows=output.with_name(f"{stem}_removed_rows{suffix}"),
        report_json=reports / f"{stem}_report.json",
        report_markdown=reports / f"{stem}_report.md",
    )


@dataclass
class RunContext:
    """Everything collected during a run; consumed by :mod:`data_cleaning.reporting`."""

    input_path: Path
    plan: OutputPlan
    config: dict[str, Any]
    overrides: dict[str, Any] = field(default_factory=dict)
    overwrite: bool = False
    tool_version: str = __version__
    input_sha256_before: str | None = None
    input_sha256_after: str | None = None
    table: LoadedTable | None = None
    profile_before: dict[str, Any] | None = None
    profile_after: dict[str, Any] | None = None
    column_mapping: dict[str, str] = field(default_factory=dict)
    steps: list[StepReport] = field(default_factory=list)
    validation: ValidationResult | None = None
    rows_quarantined: int = 0
    rows_removed: int = 0
    exports: dict[str, ExportResult] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    error_type: str | None = None
    final_shape: tuple[int, int] | None = None
    final_rows: set[int] = field(default_factory=set)
    cells_differing: dict[str, int] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass
class RunResult:
    """Outcome returned to the caller (e.g. the CLI)."""

    context: RunContext
    report: dict[str, Any]
    report_files: list[Path]
    exit_code: int


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_cleaning(
    input_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    config: dict[str, Any] | None = None,
    sheet: str | None = None,
    encoding: str | None = None,
    delimiter: str | None = None,
    remove_exact_duplicates: bool = False,
    overwrite: bool = False,
    report_dir: str | os.PathLike[str] | None = None,
) -> RunResult:
    """Run the full cleaning workflow and write the cleaned file and reports.

    Args:
        input_path: CSV or XLSX file to clean (never modified).
        output_path: Destination ``.csv`` or ``.xlsx``.
        config: Validated configuration (see :mod:`data_cleaning.config`); defaults if ``None``.
        sheet, encoding, delimiter: Input options overriding ``config["input"]``.
        remove_exact_duplicates: Remove exact duplicate rows (also enabled by
            ``duplicates.remove_exact`` in the configuration).
        overwrite: Allow replacing existing output and report files.
        report_dir: Directory for the reports (default: next to the output).

    Raises:
        DataCleaningError: Before any processing, if the outputs cannot be planned
            safely or the input cannot be read. Errors after the input has been read
            are captured in the report instead (``exit_code`` 1).
    """
    from .reporting import build_report, render_markdown  # reporting imports RunContext

    config = copy.deepcopy(config) if config is not None else default_config()
    overrides: dict[str, Any] = {}
    for key, value in (("sheet", sheet), ("encoding", encoding), ("delimiter", delimiter)):
        if value is not None:
            config["input"][key] = value
            overrides[f"input.{key}"] = value
    if remove_exact_duplicates:
        config["duplicates"]["remove_exact"] = True
        overrides["duplicates.remove_exact"] = True
    if overwrite:
        overrides["overwrite"] = True

    source = Path(input_path)
    plan = plan_outputs(output_path, report_dir)
    problems: list[DataCleaningError] = []
    for path in plan.all_paths():
        try:
            check_output_path(path, overwrite=overwrite, protected_paths=[source])
        except DataCleaningError as exc:
            problems.append(exc)
    if len(problems) == 1:
        raise problems[0]
    if problems:
        raise ExportError("Planned output files cannot be written:\n  - " + "\n  - ".join(map(str, problems)))

    ctx = RunContext(input_path=source, plan=plan, config=config, overrides=overrides, overwrite=overwrite)
    ctx.input_sha256_before = file_sha256(source) if source.is_file() else None
    table = read_table(
        source,
        sheet=config["input"]["sheet"],
        encoding=config["input"]["encoding"],
        delimiter=config["input"]["delimiter"],
    )
    ctx.table = table
    ctx.warnings.extend(table.warnings)

    unexpected: Exception | None = None
    try:
        _process(ctx, table.data)
    except DataCleaningError as exc:
        ctx.error = str(exc)
        ctx.error_type = type(exc).__name__
        logger.info("Cleaning failed: %s", exc)
    except Exception as exc:  # a bug: record it in the report, then re-raise below
        unexpected = exc
        ctx.error = f"Unexpected internal error: {exc!r}. Outputs from this run must not be used."
        ctx.error_type = type(exc).__name__
    finally:
        if source.exists():
            ctx.input_sha256_after = file_sha256(source)
    if ctx.input_sha256_after != ctx.input_sha256_before:
        # This must never happen; treat it as a hard failure rather than a warning.
        ctx.error = (ctx.error + "; " if ctx.error else "") + "the input file changed during the run"
        ctx.error_type = ctx.error_type or "InputModified"

    report = build_report(ctx)
    report_files = [
        write_text_file(plan.report_json, _to_json(report), overwrite=overwrite, protected_paths=[source]),
        write_text_file(plan.report_markdown, render_markdown(report), overwrite=overwrite, protected_paths=[source]),
    ]
    if unexpected is not None:
        raise unexpected
    if not ctx.succeeded:
        exit_code = EXIT_ERROR
    elif report["data_quality"]["status"] == "issues_found":
        exit_code = EXIT_QUALITY_ISSUES
    else:
        exit_code = EXIT_OK
    return RunResult(ctx, report, report_files, exit_code)


def _process(ctx: RunContext, raw: pd.DataFrame) -> None:
    config = ctx.config
    missing_cfg = config["missing_values"]
    ctx.profile_before = profile_dataframe(
        raw,
        missing_tokens=missing_cfg["tokens"],
        tokens_case_sensitive=missing_cfg["case_sensitive"],
        whitespace_as_missing=missing_cfg["whitespace_as_missing"],
    )
    rules = parse_rules(config["validation"])

    names = config["column_names"]
    data, step = normalize_column_names(
        raw, strip=names["strip"], collapse_whitespace=names["collapse_whitespace"], style=names["style"], rename=names["rename"]
    )
    ctx.steps.append(step)
    ctx.column_mapping = step.details["mapping"]
    _check_referenced_columns(config, data, step.details["renamed"])

    data, step = standardize_missing(
        data,
        tokens=missing_cfg["tokens"],
        case_sensitive=missing_cfg["case_sensitive"],
        whitespace_as_missing=missing_cfg["whitespace_as_missing"],
    )
    ctx.steps.append(step)

    for rule in config["text"]:
        data, step = normalize_text(
            data, rule["columns"], strip=rule["strip"], collapse_whitespace=rule["collapse_whitespace"], case=rule["case"]
        )
        ctx.steps.append(step)
    for rule in config["categories"]:
        data, step = map_categories(data, rule["column"], rule["mapping"], case_insensitive=rule["case_insensitive"])
        ctx.steps.append(step)
    for rule in config["dates"]:
        data, step = parse_dates(
            data, rule["column"], rule["formats"], output_format=rule["output_format"], on_error=rule["on_error"]
        )
        ctx.steps.append(step)
    for rule in config["numbers"]:
        data, step = parse_numbers(
            data,
            rule["column"],
            decimal=rule["decimal"],
            thousands=rule["thousands"],
            strip_chars=rule["strip_chars"],
            allow_leading_zeros=rule["allow_leading_zeros"],
            on_error=rule["on_error"],
        )
        ctx.steps.append(step)

    removed_parts: list[pd.DataFrame] = []
    duplicates = config["duplicates"]
    data, removed, step = handle_exact_duplicates(data, remove=duplicates["remove_exact"])
    ctx.steps.append(step)
    if not removed.empty:
        kept_for = {row: group["source_rows"][0] for group in step.details["groups"] for row in group["source_rows"][1:]}
        removed_parts.append(_with_reason(removed, [f"exact duplicate of row {kept_for[int(r)]}" for r in removed.index]))
    if duplicates["key_columns"]:
        keys = duplicates["key_columns"]
        data, removed, step = handle_key_duplicates(
            data, keys, remove=duplicates["remove_key_duplicates"], keep=duplicates["keep"]
        )
        ctx.steps.append(step)
        if not removed.empty:
            kept_for = {}
            for group in step.details["groups"]:
                rows = group["source_rows"]
                kept = rows[0] if duplicates["keep"] == "first" else rows[-1]
                kept_for.update({row: kept for row in rows if row != kept})
            removed_parts.append(
                _with_reason(removed, [f"duplicate of row {kept_for[int(r)]} on key {keys} (keep={duplicates['keep']})" for r in removed.index])
            )

    ctx.validation = validate(data, rules)
    data, quarantined = split_quarantine(data, ctx.validation)
    ctx.rows_quarantined = len(quarantined)
    removed_rows = pd.concat(removed_parts) if removed_parts else None
    ctx.rows_removed = 0 if removed_rows is None else len(removed_rows)
    ctx.final_shape = (int(data.shape[0]), int(data.shape[1]))
    ctx.final_rows = {int(r) for r in data.index}
    ctx.cells_differing = _cells_differing(raw.rename(columns=ctx.column_mapping), data)

    out = config["output"]
    export_options = {
        "overwrite": ctx.overwrite,
        "protected_paths": [ctx.input_path],
        "csv_encoding": out["csv_encoding"],
        "csv_delimiter": out["csv_delimiter"],
        "sheet_name": out["sheet_name"],
    }
    ctx.exports["cleaned"] = write_table(data, ctx.plan.output, **export_options)
    if len(quarantined):
        ctx.exports["quarantine"] = write_table(quarantined, ctx.plan.quarantine, **export_options)
    if removed_rows is not None:
        ctx.exports["removed_rows"] = write_table(removed_rows, ctx.plan.removed_rows, **export_options)
    for name in ("quarantine", "removed_rows"):
        stale = getattr(ctx.plan, name)
        if name not in ctx.exports and stale.exists():
            ctx.warnings.append(f"{stale.name} exists from an earlier run and was left untouched; it does not belong to this run.")
    for export in ctx.exports.values():
        ctx.warnings.extend(export.warnings)

    ctx.profile_after = profile_dataframe(data, whitespace_as_missing=missing_cfg["whitespace_as_missing"])


def _check_referenced_columns(config: dict[str, Any], data: pd.DataFrame, renamed: dict[str, str]) -> None:
    """Fail early, listing every configured column that does not exist."""
    missing = [(section, column) for section, column in referenced_columns(config) if column not in data.columns]
    if not missing:
        return
    lines = []
    for section, column in missing:
        hint = f" (renamed to {renamed[column]!r} by column-name normalization)" if column in renamed else ""
        lines.append(f"{section}: {column!r}{hint}")
    raise MissingColumnError(
        "Configured column(s) not found after column-name normalization: "
        + "; ".join(lines)
        + f". Available columns: {', '.join(repr(str(c)) for c in data.columns)}"
    )


def _cells_differing(original: pd.DataFrame, final: pd.DataFrame) -> dict[str, int]:
    """Per column, how many cells of the final output differ from the input as written.

    Empty and missing compare equal (both are written as an empty cell).
    """
    rendered = render_text(final).fillna("")
    counts = {}
    for column in final.columns:
        before = original.loc[final.index, column].astype("string").fillna("")
        count = int(before.ne(rendered[column]).sum())
        if count:
            counts[str(column)] = count
    return counts


def _with_reason(rows: pd.DataFrame, reasons: list[str]) -> pd.DataFrame:
    if REMOVAL_REASON_COLUMN in rows.columns:
        raise ConfigError(f"The dataset already has a column named {REMOVAL_REASON_COLUMN!r}; rename it before removing rows.")
    result = rows.copy()
    result[REMOVAL_REASON_COLUMN] = pd.Series(reasons, index=rows.index, dtype="string")
    return result


def _to_json(report: dict[str, Any]) -> str:
    import json

    return json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n"
