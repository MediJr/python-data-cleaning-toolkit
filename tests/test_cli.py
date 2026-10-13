"""Tests for the command-line interface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from data_cleaning.cli import main

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    path = tmp_path / "raw.csv"
    path.write_text("id;city\n001; Paris \n002;N/A\n002;N/A\n", encoding="utf-8")
    return path


def test_help_texts_include_examples_and_exit_codes(capsys):
    for argv in (["--help"], ["clean", "--help"], ["profile", "--help"]):
        with pytest.raises(SystemExit) as exit_info:
            main(argv)
        assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert "exit codes: 0 success, 1 error, 2 usage error, 3 success with unresolved data-quality issues" in out
    assert "--drop-exact-duplicates" in out and "--overwrite" in out and "--sheet" in out
    assert "the input file is never modified" in out


def test_usage_error_exits_with_2(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["clean", "only-input.csv"])
    assert exit_info.value.code == 2


def test_profile_prints_summary_and_changes_nothing(raw, capsys):
    before = raw.read_bytes()
    assert main(["profile", str(raw), "--missing-token", "N/A"]) == 0
    out = capsys.readouterr().out
    assert "Rows: 3, columns: 2" in out
    assert "Exact duplicate rows (extra copies): 1" in out
    assert "| id | integer | 0 | 2 | 3 with leading zeros |" in out
    assert raw.read_bytes() == before


def test_profile_reports_are_written_and_protected(raw, tmp_path, capsys):
    reports = tmp_path / "reports"
    assert main(["profile", str(raw), "--report-dir", str(reports)]) == 0
    data = json.loads((reports / "raw_profile.json").read_text(encoding="utf-8"))
    assert data["report_type"] == "profile" and data["profile"]["rows"] == 3
    assert (reports / "raw_profile.md").read_text(encoding="utf-8").startswith("# Data profile: raw.csv")
    assert main(["profile", str(raw), "--report-dir", str(reports)]) == 1
    assert "already exists" in capsys.readouterr().err
    assert main(["profile", str(raw), "--report-dir", str(reports), "--overwrite"]) == 0


def test_clean_reports_statuses_and_exit_code(raw, tmp_path, capsys):
    code = main(["clean", str(raw), str(tmp_path / "out" / "clean.csv")])
    out = capsys.readouterr().out
    assert code == 3  # duplicates were detected but not removed
    assert "Execution: SUCCESS" in out and "Data quality: ISSUES FOUND" in out
    assert "Rows: 3 -> 3 (removed 0, quarantined 0)" in out
    assert (tmp_path / "out" / "clean_report.md").exists()


def test_clean_with_config_and_flags(raw, tmp_path, capsys):
    config = tmp_path / "cfg.json"
    config.write_text(json.dumps({"missing_values": {"tokens": ["N/A"]}, "text": [{"columns": ["city"]}]}), encoding="utf-8")
    code = main(
        ["clean", str(raw), str(tmp_path / "clean.csv"), "--config", str(config), "--drop-exact-duplicates", "--report-dir", str(tmp_path / "r")]
    )
    assert code == 0
    assert (tmp_path / "clean.csv").read_text(encoding="utf-8") == "id,city\n001,Paris\n002,\n"
    assert (tmp_path / "r" / "clean_report.json").exists()
    assert "Wrote removed_rows" in capsys.readouterr().out


def test_invalid_config_fails_before_any_file_is_written(raw, tmp_path, capsys):
    config = tmp_path / "cfg.json"
    config.write_text(json.dumps({"missing_value": {"tokens": ["N/A"]}}), encoding="utf-8")
    assert main(["clean", str(raw), str(tmp_path / "out" / "clean.csv"), "--config", str(config)]) == 1
    assert "Unknown key(s) in configuration: missing_value" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "argv_tail, message",
    [
        (["missing.csv", "out.csv"], "Input file not found"),
        (["{raw}", "out.json"], "Unsupported output type"),
        (["{raw}", "{raw}"], "input file"),
    ],
)
def test_clean_error_messages(raw, tmp_path, capsys, monkeypatch, argv_tail, message):
    monkeypatch.chdir(tmp_path)
    argv = ["clean"] + [a.format(raw=raw) for a in argv_tail]
    assert main(argv) == 1
    assert message in capsys.readouterr().err


def test_malformed_input_reports_the_line(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n3\n", encoding="utf-8")
    assert main(["clean", str(bad), str(tmp_path / "out.csv")]) == 1
    assert "line 3 (1 fields)" in capsys.readouterr().err
    assert not (tmp_path / "out.csv").exists()


def test_tab_delimiter_option(tmp_path, capsys):
    path = tmp_path / "tabs.csv"
    path.write_text("a\tb\n1\t2\n", encoding="utf-8")
    assert main(["clean", str(path), str(tmp_path / "out.csv"), "--delimiter", "\\t"]) == 0
    assert (tmp_path / "out.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"


def test_module_entry_point_runs_in_a_subprocess(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "data_cleaning", "--version"],
        capture_output=True, text=True, cwd=PROJECT_ROOT, env={**__import__("os").environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
    )
    assert completed.returncode == 0 and completed.stdout.strip() == "data-clean 0.1.0"
