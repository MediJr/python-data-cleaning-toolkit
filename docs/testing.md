# Testing and verification

## Running the tests

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

Tests use pytest's temporary directories and the synthetic files in `data/sample/`. They do
not need network access and do not modify repository files. One test (an output file held
open by another program) runs only on Windows and is skipped elsewhere.

## What the suite covers

| File | Focus |
| --- | --- |
| `test_io.py` | CSV/XLSX reading (encodings, delimiters, quoting, ragged rows, duplicate headers, empty and header-only files, corrupt workbooks, sheet selection, formulas with and without saved values), writing, verification by reopening (including an export that does not read back identically), overwrite protection, protection of the input path, permission errors, formula-like text staying text in Excel |
| `test_cleaning.py` | Every transformation: column names and collisions, missing values, text, category mappings, dates (ambiguous, invalid, `set_missing`), numbers (separators, currency, leading zeros, precision), exact and key duplicates |
| `test_validation_and_profiling.py` | Each validation rule with the exact failing rows, quarantine, invalid rule definitions, profiling figures |
| `test_config.py` | Defaults, 30 invalid configurations each rejected with a precise message, JSON syntax errors |
| `test_pipeline.py` | End-to-end runs: exact output files, report figures against the written files, statuses and exit codes, determinism of repeated runs, failure reports, input-modification detection, unexpected-error handling |
| `test_cli.py` | Help text, exit codes, profile and clean commands, error messages, `python -m data_cleaning` in a subprocess |
| `test_samples.py` | The sample workflows against **hand-written** expected outputs, invalid samples, committed examples equal to a fresh run, sample generator, legacy console encoding |
| `test_packaging.py` | `pyproject.toml` and `requirements*.txt` agree; runtime dependencies match the imports; build-backend minimum |
| `test_docs.py` | README and docs: relative links resolve, every documented `data-clean` command is valid for the real parser and refers to existing files, the README quick-start commands give the documented exit codes |
| `test_benchmark_scripts.py` | The benchmark generator is deterministic, and its independent verifier accepts real outputs and rejects an altered one (2,000-row datasets) |

Tests assert concrete outcomes (cell values, row numbers, counts, file contents), not just
that code runs. During development, safeguards were deliberately disabled one at a time in
a scratch copy (leading-zero guard, ambiguous-date guard, overwrite protection, output
pre-check, input fingerprint check, data-quality status, unknown-key rejection); each
change made at least one test fail. The same check was repeated on the final code (see
below).

## Independent verification of the samples

The expected outputs in `data/sample/expected/` were written by hand from the rules,
before running the tool on the samples, and are documented row by row in
[`data/sample/README.md`](../data/sample/README.md). They are not copies of tool output.

In the verification stage, a separate script that does **not** import the toolkit (only
`csv`, `openpyxl` and `hashlib`) recomputed the report figures from the raw inputs and the
written files: row and column counts, conservation of rows (cleaned + removed +
quarantined = input), missing values per column, changed cells per column, identifier
preservation, cell types in the Excel output, validation counts, quarantine reasons and
input fingerprints. All 81 checks passed for both `data-clean` and `python -m
data_cleaning`, and the script itself was checked by confirming it detects deliberately
altered outputs. That script was a one-off verification aid and is not part of the
repository; the same expectations are enforced by `tests/test_samples.py`.

## Clean-environment check

The files that would be committed were copied to a separate folder and installed into
new virtual environments with `--no-cache-dir` (all packages downloaded fresh):

- `pip install -e ".[dev]"` then the full test suite: all tests passed;
- `pip install .` (normal install, no test packages) then `data-clean` and
  `python -m data_cleaning` run from outside the source folder on both samples, with the
  outputs checked by the independent script.

Environment: Windows 11 (10.0.26300), Python 3.14.7, pandas 3.0.6, numpy 2.5.4,
openpyxl 3.1.5, pytest 9.1.1. No other operating system or Python version was tested.

## Performance benchmark

A deterministic 100,000-row benchmark of both workflows, with an independent verification
of every output, is documented in [performance.md](performance.md); its scripts are in
[`scripts/benchmark/`](../scripts/benchmark/).

## Regenerating the examples

`reports/examples/` contains real tool output. After a change that affects outputs or
reports:

```bash
python scripts/regenerate_examples.py
```

`test_samples.py::test_committed_examples_match_a_fresh_run` fails until the examples are
regenerated, so they cannot silently drift from the tool's behaviour.
