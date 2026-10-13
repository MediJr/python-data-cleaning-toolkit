"""The documentation must match the real tool: links, commands, outputs and versions."""

from __future__ import annotations

import re
import shlex
import shutil
from pathlib import Path

import pytest

import data_cleaning
from data_cleaning.cli import build_parser, main

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS = [README, *sorted((ROOT / "docs").glob("*.md")), ROOT / "data/sample/README.md", ROOT / "reports/examples/README.md"]
COMMAND_PREFIXES = ("data-clean ", "python -m data_cleaning ")


def _slug(heading: str) -> str:
    """GitHub-style anchor for a Markdown heading."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    return {_slug(m) for m in re.findall(r"^#{1,6} (.+)$", text, flags=re.M)}


def _code_blocks(path: Path, language: str) -> list[str]:
    return re.findall(rf"```{language}\n(.*?)```", path.read_text(encoding="utf-8"), flags=re.S)


def _documented_commands() -> list[tuple[str, str]]:
    commands = []
    for doc in DOCS:
        for block in _code_blocks(doc, "(?:bash|powershell)"):
            for line in block.splitlines():
                if line.startswith(COMMAND_PREFIXES):
                    commands.append((doc.relative_to(ROOT).as_posix(), line))
    return commands


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_and_anchors_resolve(doc):
    text = re.sub(r"```.*?```", "", doc.read_text(encoding="utf-8"), flags=re.S)
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path_part, _, anchor = target.partition("#")
        resolved = (doc.parent / path_part).resolve() if path_part else doc
        assert resolved.exists(), f"{doc.name}: broken link {target}"
        if anchor:
            assert anchor in _anchors(resolved), f"{doc.name}: missing anchor #{anchor} in {resolved.name}"


def test_documented_commands_are_valid_for_the_real_parser():
    commands = _documented_commands()
    assert len(commands) >= 10
    parser = build_parser()
    for doc, line in commands:
        argv = shlex.split(line.split(" ", 1)[1] if line.startswith("data-clean ") else line.split(" ", 3)[3])
        try:
            args = parser.parse_args(argv)
        except SystemExit as exit_info:  # --version / --help exit successfully; anything else is an error
            assert exit_info.code == 0, f"{doc}: invalid command: {line}"
            continue
        for value in (getattr(args, "input", None), getattr(args, "config", None)):
            if value is not None and str(value).startswith(("data/", "config/")):
                assert (ROOT / value).exists(), f"{doc}: {line} refers to missing file {value}"


def test_readme_states_the_real_version_and_dependencies():
    text = README.read_text(encoding="utf-8")
    assert f"data-clean {data_cleaning.__version__}" in text
    assert f"version {data_cleaning.__version__}" in text
    assert "Windows 11" in text and "3.14.7" in text
    for package in ("pandas", "openpyxl"):
        assert package in text


def _quick_start() -> list[tuple[str, str | None]]:
    """(command, documented output or None) pairs from the README Quick start section."""
    text = README.read_text(encoding="utf-8")
    section = text.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    pairs: list[tuple[str, str | None]] = []
    for kind, body in re.findall(r"```(bash|text)\n(.*?)```", section, flags=re.S):
        if kind == "bash":
            pairs.append((body.strip(), None))
        elif pairs and pairs[-1][1] is None and body.lstrip().startswith(("Execution", "data-clean")):
            pairs[-1] = (pairs[-1][0], body)
    return pairs


def test_readme_quick_start_runs_with_documented_results(tmp_path, monkeypatch, capsys):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    shutil.copytree(ROOT / "config", tmp_path / "config")
    monkeypatch.chdir(tmp_path)
    expected_exit = {"--version": 0, "profile": 0, "customers_clean.csv": 3, "orders_clean.xlsx": 3, "customers_defaults.csv": 0}
    pairs = _quick_start()
    assert len(pairs) == 6
    for command, documented in pairs:
        argv = shlex.split(command)
        argv = argv[1:] if argv[0] == "data-clean" else argv[3:]
        key = next(k for k in expected_exit if k in command)
        if argv == ["--version"]:
            with pytest.raises(SystemExit) as exit_info:
                main(argv)
            code = exit_info.value.code
        else:
            code = main(argv)
        output = capsys.readouterr()
        assert code == expected_exit[key], command
        if documented:
            actual = (output.out + output.err).splitlines()
            lines = [l for l in documented.strip().splitlines() if l.strip() != "..."]
            position = 0
            for line in lines:  # documented lines must appear in the real output, in order
                assert line in actual[position:], f"{command}: documented line not produced: {line}"
                position = actual.index(line, position) + 1
    assert (tmp_path / "output/customers_clean.csv").read_bytes() == (ROOT / "data/sample/expected/customers_clean.csv").read_bytes()


def test_readme_before_after_excerpt_matches_real_files():
    text = README.read_text(encoding="utf-8")
    section = text.split("## Before and after", 1)[1].split("\n## ", 1)[0]
    raw_block, clean_block = _code_blocks_in(section)
    raw_lines = (ROOT / "data/sample/customers_raw.csv").read_text(encoding="utf-8").splitlines()
    clean_lines = (ROOT / "reports/examples/customers_clean.csv").read_text(encoding="utf-8").splitlines()
    assert all(line in raw_lines for line in raw_block), "README input excerpt differs from customers_raw.csv"
    assert all(line in clean_lines for line in clean_block), "README output excerpt differs from the real output"


def _code_blocks_in(section: str) -> list[list[str]]:
    return [body.strip().splitlines() for body in re.findall(r"```text\n(.*?)```", section, flags=re.S)]


def test_readme_report_excerpt_matches_the_committed_report():
    text = README.read_text(encoding="utf-8")
    section = text.split("## Sample report", 1)[1].split("\n## ", 1)[0]
    report = (ROOT / "reports/examples/customers_clean_report.md").read_text(encoding="utf-8")
    for line in _code_blocks_in(section)[0]:
        if line.startswith("|"):
            assert line in report, f"README report excerpt line not in the real report: {line}"
