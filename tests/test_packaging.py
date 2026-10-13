"""Consistency of the packaging metadata and dependency files."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import data_cleaning
from data_cleaning import cli

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _requirements(name: str) -> list[str]:
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    return [line.split("#")[0].strip() for line in lines if line.split("#")[0].strip()]


def _normalize(spec: str) -> tuple[str, frozenset[str]]:
    name, constraints = re.match(r"([A-Za-z0-9_.-]+)\s*(.*)", spec).groups()
    return name.lower(), frozenset(c.strip() for c in constraints.split(",") if c.strip())


def test_requirements_txt_matches_pyproject_dependencies():
    declared = {_normalize(s) for s in PYPROJECT["project"]["dependencies"]}
    assert {_normalize(s) for s in _requirements("requirements.txt")} == declared


def test_requirements_dev_matches_the_dev_extra():
    lines = _requirements("requirements-dev.txt")
    assert "-r requirements.txt" in lines
    dev = {_normalize(s) for s in PYPROJECT["project"]["optional-dependencies"]["dev"]}
    assert {_normalize(s) for s in lines if not s.startswith("-r")} == dev


def test_runtime_dependencies_are_only_what_the_code_imports():
    names = {_normalize(s)[0] for s in PYPROJECT["project"]["dependencies"]}
    assert names == {"pandas", "openpyxl"}
    imported = set()
    for path in (ROOT / "src" / "data_cleaning").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add(node.module.split(".")[0])
    third_party = imported - set(sys.stdlib_module_names) - {"__future__"}
    assert third_party == names


def test_build_backend_supports_the_spdx_license_field():
    # `license = "MIT"` (PEP 639) is rejected by setuptools < 77 (verified with 69.5.1 in Stage 5).
    assert PYPROJECT["project"]["license"] == "MIT"
    assert "setuptools>=77" in PYPROJECT["build-system"]["requires"]


def test_version_and_console_script_are_consistent():
    assert PYPROJECT["project"]["version"] == data_cleaning.__version__
    assert PYPROJECT["project"]["scripts"]["data-clean"] == "data_cleaning.cli:main"
    assert callable(cli.main)
