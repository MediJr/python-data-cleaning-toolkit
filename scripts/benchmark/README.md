# Benchmark scripts

These scripts reproduce the measurements in [docs/performance.md](../../docs/performance.md).
They use only the project's dependencies (pandas is not imported by the verifier; it uses
`csv` and `openpyxl`). The datasets and outputs are large (about 95 MB), so **use a working
folder outside the repository**.

| Script | Purpose | Platform |
| --- | --- | --- |
| `generate_data.py` | Deterministic synthetic data (seed 20261013): `customers_100k.csv`, `orders_100k.xlsx` and `manifest.json` (expected outcomes and input fingerprints) | any |
| `measure.py` | Time and peak memory of a command including its child processes (Windows Job Object). Run it directly to calibrate. | Windows only |
| `run_benchmark.py` | Runs both workflows N times through the installed `data-clean` command and writes `results.json` | Windows only |
| `verify_outputs.py` | Checks one run's outputs and reports without importing the toolkit | any |

From the project root, with the package installed (`python -m pip install .`) and a working
folder such as `..\dct-benchmark`:

```powershell
python scripts/benchmark/generate_data.py ..\dct-benchmark
python scripts/benchmark/measure.py
python scripts/benchmark/run_benchmark.py ..\dct-benchmark --repeats 3 --warmup
python scripts/benchmark/verify_outputs.py ..\dct-benchmark customers 1
python scripts/benchmark/verify_outputs.py ..\dct-benchmark orders 1
```

`--warmup` runs each workflow once more first, reported but excluded from `results.json` (the
first run in a fresh environment was much slower in the published measurements).
`run_benchmark.py` refuses to reuse an existing `runs/` folder; delete it (or use a new
working folder) before a new series. `generate_data.py --rows N` (N ≥ 2000) produces smaller
datasets with the same proportions; `tests/test_benchmark_scripts.py` uses it to check that the
scripts keep working.
