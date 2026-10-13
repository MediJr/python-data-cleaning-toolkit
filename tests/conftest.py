"""Shared test helpers. All files are created inside pytest's temporary directories."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from data_cleaning.models import SOURCE_ROW


def make_frame(columns: dict[str, list], first_row: int = 2) -> pd.DataFrame:
    """Build a text DataFrame like the one produced by ``read_table`` (header on row 1)."""
    frame = pd.DataFrame(columns, dtype="string")
    frame.index = pd.Index(range(first_row, first_row + len(frame)), name=SOURCE_ROW)
    return frame


@pytest.fixture
def write_text(tmp_path: Path):
    """Write a text file with an exact encoding and return its path."""

    def _write(name: str, content: str, encoding: str = "utf-8") -> Path:
        path = tmp_path / name
        path.write_bytes(content.encode(encoding))
        return path

    return _write
