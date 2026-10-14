"""JSON and Markdown reports.

Two statuses are always reported separately:

* **Execution status** -- did the tool run to completion and write verified files?
* **Data-quality status** -- what do the configured rules and built-in checks say
  about the data? ``accepted``, ``issues_found``, ``no_rules_configured`` or
  ``not_assessed`` (when execution failed). Even ``accepted`` only means that the
  configured checks passed; it is never a claim that the data is "clean".
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from . import __version__

if TYPE_CHECKING:  # pragma: no cover
    from .io import LoadedTable
    from .pipeline import RunContext

MAX_MARKDOWN_ROWS = 20
QUALITY_NOTE = (
    "The data-quality status reflects only the configured rules and the toolkit's built-in checks. "
    "It is not a certification that the data is correct or complete."
)
_CONVERSION_STEPS = ("parse_dates", "parse_numbers")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


# --------------------------------------------------------------------------- cleaning report


def build_report(ctx: "RunContext") -> dict[str, Any]:
    """Assemble the machine-readable report for a cleaning run."""
    steps = [step.to_dict() for step in ctx.steps]
    conversion_failures = [
        {"step": step.step, **issue} for step in ctx.steps if step.step in _CONVERSION_STEPS for issue in step.issues
    ]
    exact = next((s for s in ctx.steps if s.step == "exact_duplicates"), None)
    keys = next((s for s in ctx.steps if s.step == "key_duplicates"), None)
    validation = ctx.validation.to_dict() if ctx.validation is not None else None

    for failure in conversion_failures:
        failure["in_cleaned_output"] = failure["source_row"] in ctx.final_rows
    remaining = sum(f["in_cleaned_output"] for f in conversion_failures)
    anomalies: list[dict[str, Any]] = []
    if remaining:
        elsewhere = len(conversion_failures) - remaining
        anomalies.append(
            {
                "type": "conversion_failure",
                "count": remaining,
                "description": f"{remaining} date/number value(s) in the cleaned output could not be converted"
                + (f" ({elsewhere} more in rows that were removed or quarantined)" if elsewhere else "")
                + " (see conversion failures).",
            }
        )
    if exact is not None and exact.details["duplicate_rows"] and not exact.rule["remove"]:
        anomalies.append(
            {
                "type": "exact_duplicates_kept",
                "count": exact.details["duplicate_rows"],
                "description": f"{exact.details['duplicate_rows']} exact duplicate row(s) remain in the output (removal not requested).",
            }
        )
    if keys is not None and keys.details["duplicate_key_groups"] and not keys.rule["remove"]:
        anomalies.append(
            {
                "type": "key_duplicates_kept",
                "count": keys.details["duplicate_key_groups"],
                "description": (
                    f"{keys.details['duplicate_key_groups']} key value(s) in {keys.rule['keys']} appear on several rows "
                    f"({keys.details['groups_with_conflicting_values']} with conflicting values); rows were kept."
                ),
            }
        )
    if validation is not None:
        for rule in validation["rules"]:
            if rule["status"] != "passed":
                anomalies.append(
                    {
                        "type": "validation_" + rule["status"],
                        "rule_id": rule["id"],
                        "count": rule["failures"],
                        "description": f"Rule {rule['id']} ({rule['label']}): "
                        + (rule.get("message") or f"{rule['failures']} failure(s), action = {rule['action']}"),
                    }
                )

    uncalculated = ctx.table.uncalculated_formula_cells if ctx.table is not None else 0
    if uncalculated:
        anomalies.append(
            {
                "type": "uncalculated_formulas",
                "count": uncalculated,
                "description": f"{uncalculated} formula cell(s) in the input have no saved value and were read as empty.",
            }
        )

    rules_configured = bool(ctx.config["validation"])
    unresolved = sum(a["count"] or 1 for a in anomalies)
    if not ctx.succeeded:
        quality = "not_assessed"
        summary = "Execution failed, so data quality was not assessed. No cleaned output should be used from this run."
    elif anomalies:
        quality = "issues_found"
        summary = (
            f"Execution succeeded, but {len(anomalies)} type(s) of unresolved issue ({unresolved} occurrence(s)) remain. "
            "Review them before using the data."
        )
    elif rules_configured:
        quality = "accepted"
        summary = f"All {len(ctx.config['validation'])} configured validation rule(s) passed and no unresolved anomalies were detected."
    else:
        quality = "no_rules_configured"
        summary = (
            "No validation rules were configured, so the data was not checked against acceptance criteria. "
            "The built-in checks found no unresolved anomalies."
        )

    table = ctx.table
    initial = {"rows": int(table.data.shape[0]), "columns": int(table.data.shape[1])} if table is not None else None
    final = {"rows": ctx.final_shape[0], "columns": ctx.final_shape[1]} if ctx.final_shape and ctx.succeeded else None
    input_info = table.describe() if table is not None else {"path": ctx.input_path.as_posix(), "file_name": ctx.input_path.name}
    input_info.update(
        {
            "sha256_before": ctx.input_sha256_before,
            "sha256_after": ctx.input_sha256_after,
            "unchanged": ctx.input_sha256_before is not None and ctx.input_sha256_before == ctx.input_sha256_after,
        }
    )
    warnings = _dedupe(ctx.warnings + [w for step in ctx.steps for w in step.warnings])

    return {
        "report_type": "cleaning",
        "tool": {"name": "python-data-cleaning-toolkit", "version": ctx.tool_version},
        "generated_at": _now(),
        "execution": {
            "status": "success" if ctx.succeeded else "failed",
            "error": ctx.error,
            "error_type": ctx.error_type,
        },
        "data_quality": {
            "status": quality,
            "summary": summary,
            "note": QUALITY_NOTE,
            "unresolved_anomaly_types": len(anomalies),
            "unresolved_occurrences": unresolved,
        },
        "input": input_info,
        "outputs": {name: export.describe() for name, export in ctx.exports.items()},
        "planned_outputs": {
            "cleaned": ctx.plan.output.as_posix(),
            "quarantine": ctx.plan.quarantine.as_posix(),
            "removed_rows": ctx.plan.removed_rows.as_posix(),
            "report_json": ctx.plan.report_json.as_posix(),
            "report_markdown": ctx.plan.report_markdown.as_posix(),
        },
        "dimensions": {
            "initial": initial,
            "final": final,
            "rows_removed": ctx.rows_removed,
            "rows_quarantined": ctx.rows_quarantined,
            "blank_rows_skipped_on_import": table.skipped_blank_rows if table is not None else 0,
        },
        "missing_values": _missing_table(ctx),
        "columns": {
            "mapping": dict(ctx.column_mapping),
            "renamed": {o: n for o, n in ctx.column_mapping.items() if o != n},
            "cells_differing_from_input": dict(ctx.cells_differing),
            "changes_per_column_summed_over_steps": _cells_changed(ctx),
        },
        "operations": [_describe_step(step) for step in ctx.steps],
        "conversion_failures": conversion_failures,
        "duplicates": {
            "exact": exact.to_dict()["details"] | {"removed": len(exact.rows_removed)} if exact else None,
            "keys": keys.to_dict()["details"] | {"removed": len(keys.rows_removed), "rule": keys.rule} if keys else None,
        },
        "validation": validation,
        "anomalies": anomalies,
        "warnings": warnings,
        "steps": steps,
        "configuration": ctx.config,
        "overrides": ctx.overrides,
        "profile_before": ctx.profile_before,
        "profile_after": ctx.profile_after,
    }


def _missing_table(ctx: "RunContext") -> list[dict[str, Any]]:
    if ctx.profile_before is None:
        return []
    before = ctx.profile_before["missing_by_column"]
    after = ctx.profile_after["missing_by_column"] if ctx.profile_after else {}
    rows = []
    for original, count in before.items():
        new = ctx.column_mapping.get(original, original)
        rows.append({"column": new, "original_column": original, "before": count, "after": after.get(new)})
    return rows


def _cells_changed(ctx: "RunContext") -> dict[str, int]:
    totals: dict[str, int] = {}
    for step in ctx.steps:
        for column, count in step.cells_changed.items():
            totals[column] = totals.get(column, 0) + count
    return totals


def _describe_step(step: Any) -> dict[str, Any]:
    rule = step.rule
    name = step.step
    if name == "normalize_column_names":
        text = f"Column names: strip={rule['strip']}, collapse_whitespace={rule['collapse_whitespace']}, style={rule['style']}; {len(step.details['renamed'])} renamed"
    elif name == "standardize_missing":
        text = f"Missing values: empty and {'whitespace-only cells' if rule['whitespace_as_missing'] else 'no whitespace-only cells'}"
        text += f" plus tokens {rule['tokens']}" if rule["tokens"] else ", no extra tokens"
        text += " marked missing (no imputation)"
    elif name == "normalize_text":
        options = [o for o, on in (("trim", rule["strip"]), ("collapse spaces", rule["collapse_whitespace"])) if on]
        if rule["case"]:
            options.append(f"{rule['case']} case")
        text = f"Text {', '.join(options)} on {rule['columns']}"
    elif name == "map_categories":
        text = f"Category mapping on {rule['column']!r} ({len(rule['mapping'])} explicit label(s), case_insensitive={rule['case_insensitive']})"
    elif name == "parse_dates":
        text = f"Dates in {rule['column']!r}: formats {rule['formats']} -> {rule['output_format']}; failures {'kept' if rule['on_error'] == 'keep' else 'set missing'}"
    elif name == "parse_numbers":
        text = (
            f"Numbers in {rule['column']!r}: decimal {rule['decimal']!r}, thousands {rule['thousands']!r}"
            + (f", strip {rule['strip_chars']!r}" if rule["strip_chars"] else "")
            + f"; failures {'kept' if rule['on_error'] == 'keep' else 'set missing'}"
        )
    elif name == "exact_duplicates":
        text = f"Exact duplicates: {step.details['duplicate_rows']} detected, " + (
            f"{len(step.rows_removed)} removed (first occurrence kept)" if rule["remove"] else "kept (removal not requested)"
        )
    elif name == "key_duplicates":
        text = f"Key duplicates on {rule['keys']}: {step.details['duplicate_key_groups']} group(s), " + (
            f"{len(step.rows_removed)} row(s) removed (keep={rule['keep']})" if rule["remove"] else "kept (removal not requested)"
        )
    else:  # pragma: no cover - every step type is listed above
        text = name
    return {
        "step": name,
        "description": text,
        "cells_changed": step.total_cells_changed,
        "rows_removed": len(step.rows_removed),
        "issues": len(step.issues),
    }


# --------------------------------------------------------------------------- Markdown


def _cell(value: Any, limit: int | None = 80) -> str:
    if value is None:
        return ""
    text = str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    return text if limit is None or len(text) <= limit else text[: limit - 3] + "..."


def _table(headers: list[str], rows: list[list[Any]], limit: int | None = 80) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(v, limit) for v in row) + " |" for row in rows]
    return lines


def _truncated(items: list, what: str) -> tuple[list, list[str]]:
    if len(items) <= MAX_MARKDOWN_ROWS:
        return items, []
    return items[:MAX_MARKDOWN_ROWS], ["", f"_Showing {MAX_MARKDOWN_ROWS} of {len(items)} {what}; see the JSON report for all of them._"]


_QUALITY_LABELS = {
    "accepted": "ACCEPTED (configured checks passed)",
    "issues_found": "ISSUES FOUND",
    "no_rules_configured": "NOT ASSESSED (no validation rules configured)",
    "not_assessed": "NOT ASSESSED (execution failed)",
}


def render_markdown(report: dict[str, Any]) -> str:
    """Render the human-readable Markdown version of a cleaning report."""
    execution = report["execution"]
    quality = report["data_quality"]
    inp = report["input"]
    dims = report["dimensions"]
    lines = [
        f"# Data cleaning report: {inp.get('file_name')}",
        "",
        f"Generated {report['generated_at']} by {report['tool']['name']} {report['tool']['version']}.",
        "",
        *_table(
            ["Check", "Result"],
            [
                ["Execution status", execution["status"].upper()],
                ["Data-quality status", _QUALITY_LABELS[quality["status"]]],
                ["Input file unchanged", "yes (SHA-256 identical before and after)" if inp["unchanged"] else "NOT CONFIRMED"],
            ],
        ),
        "",
        f"**Summary:** {quality['summary']}",
        "",
        f"> {quality['note']}",
    ]
    if execution["error"]:
        lines += ["", f"**Error ({execution['error_type']}):** {execution['error']}"]

    lines += ["", "## Files", ""]
    file_rows = [["Input", inp.get("file_name"), inp.get("format"), inp.get("rows"), inp.get("columns"), "source (read-only)"]]
    labels = {"cleaned": "Cleaned output", "quarantine": "Quarantined rows", "removed_rows": "Removed rows"}
    for name, out in report["outputs"].items():
        file_rows.append([labels.get(name, name), out["file_name"], out["format"], out["rows"], out["columns"], "reopened and verified" if out["verified"] else "NOT verified"])
    if "cleaned" not in report["outputs"]:
        file_rows.append(["Cleaned output", report["planned_outputs"]["cleaned"], "", "", "", "NOT WRITTEN"])
    lines += _table(["Role", "File", "Format", "Rows", "Columns", "Status"], file_rows)
    if inp.get("format") == "csv":
        lines += ["", f"Input read as {inp.get('encoding')} with delimiter {inp.get('delimiter')!r}" + (" (detected)." if inp.get("delimiter_detected") else ".")]
    elif inp.get("sheet"):
        lines += ["", f"Input sheet: {inp['sheet']!r} (available: {', '.join(inp.get('available_sheets', []))})."]

    lines += ["", "## Dimensions", ""]
    initial, final = dims["initial"] or {}, dims["final"] or {}
    lines += _table(["", "Rows", "Columns"], [["Before", initial.get("rows"), initial.get("columns")], ["After", final.get("rows"), final.get("columns")]])
    lines += [
        "",
        f"- Rows removed (duplicates, saved to the removed-rows file): {dims['rows_removed']}",
        f"- Rows quarantined (saved to the quarantine file): {dims['rows_quarantined']}",
        f"- Completely empty rows skipped on import: {dims['blank_rows_skipped_on_import']}",
    ]

    if report["operations"]:
        lines += ["", "## Cleaning operations (in order)", ""]
        lines += _table(
            ["#", "Operation", "Cells changed", "Rows removed", "Problems"],
            [[i, op["description"], op["cells_changed"], op["rows_removed"], op["issues"]] for i, op in enumerate(report["operations"], 1)],
            limit=None,
        )

    if report["columns"]["renamed"]:
        lines += ["", "## Renamed columns", ""]
        lines += _table(["Original", "New"], [[repr(o), repr(n)] for o, n in report["columns"]["renamed"].items()])

    changed = report["columns"]["cells_differing_from_input"]
    if changed:
        lines += ["", "## Changed cells by column", ""]
        lines += ["Cells of the cleaned output whose value differs from the input (removed and quarantined rows excluded):", ""]
        lines += _table(["Column", "Cells changed"], [[c, n] for c, n in changed.items()])
        examples = [
            [column, e["source_row"], e["before"], e["after"]]
            for step in report["steps"]
            for column, items in step["examples"].items()
            for e in items[:2]
        ]
        shown, note = _truncated(examples, "examples")
        lines += ["", "Examples (row = row/line number in the input file):", ""]
        lines += _table(["Column", "Row", "Before", "After"], shown) + note

    missing = [m for m in report["missing_values"] if m["before"] or m["after"]]
    lines += ["", "## Missing values", ""]
    if missing:
        lines += _table(["Column", "Before", "After"], [[m["column"], m["before"], m["after"]] for m in missing])
        lines += ["", "Missing values are never filled in automatically."]
    else:
        lines += ["No missing values detected."]

    failures = report["conversion_failures"]
    if failures:
        lines += ["", "## Conversion failures", ""]
        shown, note = _truncated(failures, "failures")
        lines += _table(
            ["Row", "Column", "Value", "Reason", "In cleaned output"],
            [[f["source_row"], f["column"], f["value"], f["reason"], "yes" if f["in_cleaned_output"] else "no (removed/quarantined)"] for f in shown],
        ) + note

    dup = report["duplicates"]
    if dup["exact"] is not None:
        lines += ["", "## Duplicates", ""]
        lines.append(
            f"- Exact duplicate rows: {dup['exact']['duplicate_rows']} detected, {dup['exact']['removed']} removed. "
            "Rule: identical values in every column (after the cleaning steps above); the first occurrence is kept."
        )
        if dup["keys"] is not None:
            k = dup["keys"]
            lines.append(
                f"- Key duplicates on {k['rule']['keys']}: {k['duplicate_key_groups']} group(s) covering {k['rows_in_groups']} row(s), "
                f"{k['groups_with_conflicting_values']} with conflicting values; {k['removed']} row(s) removed"
                + (f" (keep = {k['rule']['keep']})." if k["rule"]["remove"] else " (removal not requested).")
            )
            conflicts = [g for g in k["groups"] if not g["identical"]]
            if conflicts:
                shown, note = _truncated(conflicts, "groups")
                lines += ["", *_table(["Key", "Rows", "Columns that differ"], [[g["key"], g["source_rows"], ", ".join(g["differing_columns"])] for g in shown]), *note]

    validation = report["validation"]
    lines += ["", "## Validation", ""]
    if validation is None:
        lines.append("Validation did not run.")
    elif not validation["rules"]:
        lines.append("No validation rules were configured.")
    else:
        lines += _table(
            ["Rule", "Check", "Action", "Status", "Failures"],
            [[r["id"], r["label"], r["action"], r["status"], r["failures"]] for r in validation["rules"]],
        )
        lines += [
            "",
            f"{validation['issue_count']} validation issue(s) affecting {validation['rows_with_issues']} distinct row(s) of the "
            "input (one row can fail several rules, so failure counts can add up to more than the number of rows).",
        ]
        if validation["issues"]:
            shown, note = _truncated(validation["issues"], "validation issues")
            lines += ["", *_table(["Rule", "Row", "Column", "Value", "Problem"], [[i["rule_id"], i["source_row"], i["column"], i["value"], i["message"]] for i in shown]), *note]

    lines += ["", "## Unresolved anomalies", ""]
    lines += [f"- {a['description']}" for a in report["anomalies"]] or ["None detected by the configured checks."]
    lines += ["", "## Warnings", ""]
    lines += [f"- {w}" for w in report["warnings"]] or ["None."]
    lines += [
        "",
        "## Input integrity",
        "",
        f"- SHA-256 before: `{inp.get('sha256_before')}`",
        f"- SHA-256 after: `{inp.get('sha256_after')}`",
        "",
        "The complete configuration, per-step details and before/after profiles are in the JSON report.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- profile report


def build_profile_report(table: "LoadedTable", profile: dict[str, Any], missing_tokens: list[str]) -> dict[str, Any]:
    """Machine-readable report for the ``profile`` command (no data is changed)."""
    return {
        "report_type": "profile",
        "tool": {"name": "python-data-cleaning-toolkit", "version": __version__},
        "generated_at": _now(),
        "input": table.describe(),
        "missing_tokens": list(missing_tokens),
        "profile": profile,
    }


def render_profile_markdown(report: dict[str, Any]) -> str:
    """Human-readable profile summary."""
    inp, profile = report["input"], report["profile"]
    lines = [
        f"# Data profile: {inp['file_name']}",
        "",
        f"Generated {report['generated_at']}. Profiling is read-only; no value was changed.",
        "",
        f"- Format: {inp['format']}"
        + (f", encoding {inp['encoding']}, delimiter {inp['delimiter']!r}" if inp["format"] == "csv" else f", sheet {inp['sheet']!r}"),
        f"- Rows: {profile['rows']}, columns: {profile['columns']}",
        f"- Missing cells: {profile['missing_cells']} (empty, whitespace-only"
        + (f", or one of {report['missing_tokens']}" if report["missing_tokens"] else "")
        + ")",
        f"- Exact duplicate rows (extra copies): {profile['exact_duplicate_rows']}",
        f"- Completely empty rows skipped on import: {inp['skipped_blank_rows']}",
        "",
        "## Columns",
        "",
    ]
    rows = []
    for name, col in profile["column_profiles"].items():
        flags = []
        if col.get("leading_zero_values"):
            flags.append(f"{col['leading_zero_values']} with leading zeros")
        if col.get("ambiguous_date_values"):
            flags.append(f"{col['ambiguous_date_values']} ambiguous dates")
        if col.get("values_with_surrounding_whitespace"):
            flags.append(f"{col['values_with_surrounding_whitespace']} with surrounding spaces")
        if col.get("values_with_repeated_internal_spaces"):
            flags.append(f"{col['values_with_repeated_internal_spaces']} with repeated spaces")
        rows.append([name, col["inferred_type"], col["missing"], col["distinct"], "; ".join(flags), ", ".join(map(str, col["sample_values"]))])
    lines += _table(["Column", "Looks like", "Missing", "Distinct", "Flags", "Sample values"], rows)
    if profile["exact_duplicate_groups"]:
        lines += ["", "## Exact duplicate groups (row numbers)", ""]
        lines += [f"- {group}" for group in profile["exact_duplicate_groups"][:MAX_MARKDOWN_ROWS]]
    if inp["warnings"]:
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in inp["warnings"]]
    lines += ["", "\"Looks like\" describes the values; nothing is converted unless a cleaning rule is configured.", ""]
    return "\n".join(lines)
