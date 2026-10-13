"""Run both benchmark workflows through the installed `data-clean` command and record measurements.

Windows only (memory is measured with a Job Object, see measure.py).

Usage (after generate_data.py):
    python scripts/benchmark/run_benchmark.py WORKDIR [--repeats 3] [--warmup] [--exe PATH]

Each run writes into a new folder WORKDIR/runs/<workflow>/run<N>/ (an existing folder stops
the script) and the measurements go to WORKDIR/results.json. Runs are interleaved
(customers 1, orders 1, customers 2, ...) to limit the effect of drifting machine load.
With --warmup, each workflow first runs once into runs/<workflow>/warmup/; that run is
reported but excluded from results.json (the first run in a fresh environment can be much
slower, for example while security software scans newly installed libraries).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
from pathlib import Path

from measure import run_measured

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("workdir", type=Path, help="folder containing data/ from generate_data.py")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--exe", help="data-clean executable (default: found on PATH)")
    parser.add_argument("--warmup", action="store_true", help="run each workflow once first, excluded from the results")
    args = parser.parse_args()
    exe = args.exe or shutil.which("data-clean")
    if not exe:
        parser.error("data-clean was not found on PATH; install the package or pass --exe")
    workdir = args.workdir.resolve()
    manifest = json.loads((workdir / "data" / "manifest.json").read_text(encoding="utf-8"))
    workflows = {
        "customers": [manifest["customers"]["file"], "customers_clean.csv", "--config", str(ROOT / "config" / "customers_config.json")],
        "orders": [manifest["orders"]["file"], "orders_clean.xlsx", "--sheet", "Orders", "--config", str(ROOT / "config" / "orders_config.json")],
    }
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    results = []
    runs = (["warmup"] if args.warmup else []) + list(range(1, args.repeats + 1))
    for n in runs:
        for name, (source, output, *options) in workflows.items():
            out_dir = workdir / "runs" / name / (n if n == "warmup" else f"run{n}")
            out_dir.mkdir(parents=True, exist_ok=False)
            argv = ["clean", str(workdir / "data" / source), str(out_dir / output), *options]
            with (out_dir / "console.txt").open("w", encoding="utf-8") as log:
                measured = run_measured([exe, *argv], cwd=workdir, stdout=log, stderr=log, env=env)
            peak_ws = max(measured["peak_working_set_bytes_by_process"].values(), default=0)
            if n != "warmup":
                results.append({"workflow": name, "run": n, "command": "data-clean " + " ".join(argv), **measured, "peak_working_set_bytes": peak_ws})
            print(
                f"{name} {'warm-up run (not recorded)' if n == 'warmup' else f'run {n}'}: exit {measured['exit_code']}, {measured['wall_seconds']:.2f} s, "
                f"peak working set {peak_ws / 2**20:.1f} MiB, peak commit {measured['peak_process_commit_bytes'] / 2**20:.1f} MiB",
                flush=True,
            )
    (workdir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    for name in workflows:
        rows = [r for r in results if r["workflow"] == name]
        wall = [r["wall_seconds"] for r in rows]
        print(
            f"{name}: median {statistics.median(wall):.2f} s (min {min(wall):.2f}, max {max(wall):.2f}); "
            f"median peak working set {statistics.median(r['peak_working_set_bytes'] for r in rows) / 2**20:.1f} MiB; "
            f"median peak commit {statistics.median(r['peak_process_commit_bytes'] for r in rows) / 2**20:.1f} MiB"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
