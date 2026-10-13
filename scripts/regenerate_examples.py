"""Regenerate ``reports/examples/`` by running the real CLI on the sample data.

Every file in ``reports/examples/`` is produced by the commands below; none is
edited by hand. ``tests/test_samples.py`` checks that the committed examples
still match a fresh run.

Usage (from the project root, with the package installed):
    python scripts/regenerate_examples.py
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = "reports/examples"

#: (arguments after ``python -m data_cleaning``, expected exit code)
COMMANDS: list[tuple[list[str], int]] = [
    (["profile", "data/sample/customers_raw.csv", "--config", "config/customers_config.json", "--report-dir", EXAMPLES, "--overwrite"], 0),
    (["clean", "data/sample/customers_raw.csv", f"{EXAMPLES}/customers_clean.csv", "--config", "config/customers_config.json", "--overwrite"], 3),
    (["clean", "data/sample/orders_raw.xlsx", f"{EXAMPLES}/orders_clean.xlsx", "--sheet", "Orders", "--config", "config/orders_config.json", "--overwrite"], 3),
    (["clean", "data/sample/invalid/column_collision.csv", f"{EXAMPLES}/column_collision_clean.csv", "--config", "config/invalid/collision_config.json", "--overwrite"], 1),
]


def main() -> int:
    failures = 0
    for arguments, expected in COMMANDS:
        command = [sys.executable, "-m", "data_cleaning", *arguments]
        print("$ data-clean " + shlex.join(arguments))
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env)
        status = "ok" if completed.returncode == expected else "UNEXPECTED"
        print(f"  exit code {completed.returncode} (expected {expected}): {status}")
        if completed.returncode != expected:
            failures += 1
            print(completed.stdout + completed.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
