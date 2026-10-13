"""Command-line interface: ``data-clean profile`` and ``data-clean clean``.

Exit codes:
    0  success (and no unresolved data-quality issues)
    1  error: invalid input, configuration, or output; or the run failed
    2  invalid command-line usage
    3  the run succeeded but unresolved data-quality issues remain (see the report)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import load_config
from .errors import DataCleaningError
from .io import check_output_path, read_table, write_text_file
from .pipeline import EXIT_ERROR, EXIT_OK, run_cleaning
from .profiling import profile_dataframe
from .reporting import build_profile_report, render_profile_markdown

PROG = "data-clean"

_MAIN_EPILOG = f"""\
examples:
  {PROG} profile data/sample/customers_raw.csv --config config/customers_config.json
  {PROG} clean data/sample/customers_raw.csv output/customers_clean.csv --config config/customers_config.json
  {PROG} clean data/sample/orders_raw.xlsx output/orders_clean.xlsx --sheet Orders --config config/orders_config.json

exit codes: 0 success, 1 error, 2 usage error, 3 success with unresolved data-quality issues
"""

_CLEAN_EPILOG = f"""\
files written (for output path OUT.csv):
  OUT.csv                    cleaned data (verified by reopening it)
  OUT_quarantine.csv         rows failing rules with "action": "quarantine" (only if any)
  OUT_removed_rows.csv       duplicate rows removed, with the reason (only if any)
  OUT_report.json / .md      cleaning reports (next to OUT, or in --report-dir)

safety:
  - the input file is never modified (its SHA-256 is checked before and after);
  - existing files are never replaced unless --overwrite is given;
  - duplicate rows are only removed with --drop-exact-duplicates or the configuration;
  - values are never imputed, and ambiguous dates/numbers are reported, not guessed.

examples:
  {PROG} clean data/sample/customers_raw.csv output/customers_clean.csv --config config/customers_config.json
  {PROG} clean data/sample/customers_raw.csv output/customers_clean.xlsx --drop-exact-duplicates --report-dir output/reports
  {PROG} clean data/sample/orders_raw.xlsx output/orders_clean.csv --sheet Orders --config config/orders_config.json --overwrite
"""

_PROFILE_EPILOG = f"""\
examples:
  {PROG} profile data/sample/customers_raw.csv
  {PROG} profile data/sample/customers_raw.csv --missing-token N/A --missing-token NULL
  {PROG} profile data/sample/orders_raw.xlsx --sheet Orders --report-dir output/
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Rule-based, reported cleaning of CSV and XLSX files. The input file is never modified.",
        epilog=_MAIN_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="show progress messages")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    profile = commands.add_parser(
        "profile",
        help="describe a file (shape, types, missing values, duplicates) without changing anything",
        description="Describe a CSV/XLSX file without changing anything.",
        epilog=_PROFILE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    profile.add_argument("input", type=Path, help="input .csv or .xlsx file")
    _input_options(profile)
    profile.add_argument("--config", type=Path, help="JSON configuration (its input options and missing-value tokens are used)")
    profile.add_argument(
        "--missing-token", action="append", default=[], metavar="TOKEN",
        help="extra value to count as missing, e.g. N/A (repeatable; added to the configuration's tokens)",
    )
    profile.add_argument("--report-dir", type=Path, help="also write INPUT_profile.json and INPUT_profile.md to this directory")
    profile.add_argument("--overwrite", action="store_true", help="allow replacing existing profile reports")

    clean = commands.add_parser(
        "clean",
        help="apply configured cleaning rules and write the cleaned file plus reports",
        description="Apply configured cleaning rules, write a verified cleaned file and JSON/Markdown reports.",
        epilog=_CLEAN_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    clean.add_argument("input", type=Path, help="input .csv or .xlsx file (never modified)")
    clean.add_argument("output", type=Path, help="output .csv or .xlsx file")
    clean.add_argument("--config", type=Path, help="JSON cleaning configuration (default: only safe defaults, see docs)")
    _input_options(clean)
    clean.add_argument(
        "--drop-exact-duplicates", action="store_true",
        help="remove rows identical in every column (first occurrence kept; removed rows saved separately)",
    )
    clean.add_argument("--report-dir", type=Path, help="directory for the reports (default: next to the output)")
    clean.add_argument("--overwrite", action="store_true", help="allow replacing existing output and report files")
    return parser


def _input_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sheet", help="worksheet name for .xlsx input (default: first sheet)")
    parser.add_argument("--encoding", help="text encoding of .csv input (default: UTF-8, else Windows-1252 with a warning)")
    parser.add_argument("--delimiter", help="delimiter of .csv input (default: detected among , ; TAB |); use '\\t' for tab")


def _delimiter(value: str | None) -> str | None:
    return "\t" if value in ("\\t", "tab", "TAB") else value


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    for stream in (sys.stdout, sys.stderr):
        # A console or pipe in a legacy encoding (e.g. cp1252) must not crash the run on
        # characters such as "č"; files are always written in UTF-8 regardless.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        if args.command == "profile":
            return _profile(args)
        return _clean(args)
    except DataCleaningError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR


def _profile(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    tokens = list(dict.fromkeys(config["missing_values"]["tokens"] + args.missing_token))
    if any(t.strip() == "" for t in tokens):
        raise DataCleaningError("--missing-token values must not be empty.")
    paths = []
    if args.report_dir is not None:
        stem = args.input.stem
        paths = [args.report_dir / f"{stem}_profile.json", args.report_dir / f"{stem}_profile.md"]
        for path in paths:
            check_output_path(path, overwrite=args.overwrite, protected_paths=[args.input])
    table = read_table(
        args.input,
        sheet=args.sheet if args.sheet is not None else config["input"]["sheet"],
        encoding=args.encoding if args.encoding is not None else config["input"]["encoding"],
        delimiter=_delimiter(args.delimiter) if args.delimiter is not None else config["input"]["delimiter"],
    )
    profile = profile_dataframe(
        table.data,
        missing_tokens=tokens,
        tokens_case_sensitive=config["missing_values"]["case_sensitive"],
        whitespace_as_missing=config["missing_values"]["whitespace_as_missing"],
    )
    report = build_profile_report(table, profile, tokens)
    markdown = render_profile_markdown(report)
    if paths:  # write files before printing, so a console problem cannot prevent them
        write_text_file(paths[0], json.dumps(report, indent=2, ensure_ascii=False) + "\n", overwrite=args.overwrite, protected_paths=[args.input])
        write_text_file(paths[1], markdown, overwrite=args.overwrite, protected_paths=[args.input])
    print(markdown)
    if paths:
        print(f"Profile reports written: {paths[0].as_posix()}, {paths[1].as_posix()}")
    return EXIT_OK


def _clean(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = run_cleaning(
        args.input,
        args.output,
        config=config,
        sheet=args.sheet,
        encoding=args.encoding,
        delimiter=_delimiter(args.delimiter),
        remove_exact_duplicates=args.drop_exact_duplicates,
        overwrite=args.overwrite,
        report_dir=args.report_dir,
    )
    report = result.report
    dims = report["dimensions"]
    quality = report["data_quality"]
    stream = sys.stdout if result.context.succeeded else sys.stderr
    print(f"Execution: {report['execution']['status'].upper()}", file=stream)
    if report["execution"]["error"]:
        print(f"Error: {report['execution']['error']}", file=stream)
    print(f"Data quality: {quality['status'].upper().replace('_', ' ')} - {quality['summary']}", file=stream)
    initial, final = dims["initial"] or {}, dims["final"] or {}
    print(
        f"Rows: {initial.get('rows')} -> {final.get('rows', 'n/a')} "
        f"(removed {dims['rows_removed']}, quarantined {dims['rows_quarantined']}); "
        f"columns: {initial.get('columns')} -> {final.get('columns', 'n/a')}",
        file=stream,
    )
    for name, out in report["outputs"].items():
        print(f"Wrote {name}: {out['path']} ({out['rows']} rows, verified)", file=stream)
    for path in result.report_files:
        print(f"Report: {path.as_posix()}", file=stream)
    if report["warnings"]:
        print(f"{len(report['warnings'])} warning(s); see the report.", file=stream)
    return result.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
