# Architecture

The toolkit is a small Python package (`src/data_cleaning/`) with one responsibility per
module and a command-line interface on top. Every cleaning function is a pure
transformation (new DataFrame in, new DataFrame + report out), so the same logic is used
by the CLI, by the pipeline and by the tests, without duplication.

## Workflow

```text
             data-clean clean INPUT OUTPUT --config rules.json
                                   │
 cli.py ── parse arguments ── config.py: load + validate JSON (reject unknown keys)
                                   │
 pipeline.py
   1. plan all output paths; refuse if any exists (without --overwrite) or is the input
   2. SHA-256 of the input; io.read_table (every cell as text)
   3. profiling.profile_dataframe (raw data)
   4. cleaning.*: column names → missing values → text → categories → dates → numbers
                  → exact duplicates → key duplicates
   5. validation.validate → split_quarantine
   6. io.write_table for cleaned / quarantine / removed rows
         (temporary file → reopen → compare cell by cell → move into place)
   7. profile the result, SHA-256 of the input again (must be unchanged)
   8. reporting.build_report → JSON + Markdown (written even if a step failed)
                                   │
 exit code: 0 ok · 1 error · 2 usage · 3 success with data-quality issues
```

## Modules

| Module | Responsibility |
| --- | --- |
| `cli.py` | `argparse` interface (`profile`, `clean`), console summary, exit codes. Contains no cleaning logic. |
| `__main__.py` | Makes `python -m data_cleaning` equivalent to `data-clean`. |
| `config.py` | Loads the JSON file, rejects unknown keys and invalid values, fills defaults (`DEFAULTS`), checks conflicts, lists the columns the rules refer to. |
| `io.py` | Reads CSV (encoding/delimiter detection, strict field-count check via the `csv` module) and XLSX (openpyxl, typed cells converted to text without loss; a scan of the sheet XML counts formulas without a saved value, which openpyxl cannot distinguish from empty cells). Writes CSV/XLSX atomically, verifies by reopening, refuses to overwrite or to touch the input. |
| `profiling.py` | Read-only description: inferred value kinds, missing counts, duplicates, leading zeros, ambiguous dates, stray spaces. |
| `cleaning.py` | The transformations. Each returns the new data and a `StepReport` (changed cells, examples, values it could not process, warnings). Row-removing functions also return the removed rows. |
| `validation.py` | Parses rule definitions, evaluates them without changing data, separates quarantined rows. |
| `pipeline.py` | Orders the steps, collects results in a `RunContext`, handles failures (report still written), checks the input fingerprint. |
| `reporting.py` | Builds the JSON report and renders Markdown; computes the execution and data-quality statuses and the list of unresolved anomalies. |
| `models.py` | `StepReport` and helpers shared by the modules (NA-aware change counting). |
| `errors.py` | Exception hierarchy (`DataCleaningError` and subclasses) used for expected, explainable failures. |

## Key design decisions

| Decision | Reason |
| --- | --- |
| Read every cell as text (pandas `string` dtype) and convert only on explicit rules | Prevents silent loss of leading zeros, unwanted date parsing and float rounding. |
| Parse CSV with Python's `csv` module, then build the DataFrame | pandas pads short rows with missing values; the toolkit must reject them instead. |
| Keep the source row number as the DataFrame index | Every report, quarantine reason and removed-row reason can point to the original line. |
| No "delete" validation action; removed rows are saved | Information is moved, never discarded. |
| Ambiguity is reported, not resolved | A wrong guess (day/month order, decimal separator) is worse than an unchanged value that is flagged. |
| Write to a temporary file, verify, then `os.replace` | A failed or unverifiable export never appears under the final name. |
| Separate execution status and data-quality status | "The program ran" must not be read as "the data is valid". |
| JSON for configuration | Standard library only; YAML would add a dependency for little benefit. |
| Dates written as ISO text | Unambiguous in every tool; Excel date cells would depend on display formats. |

## Dependencies

| Package | Why |
| --- | --- |
| pandas (>=3.0, <4) | Tabular operations; brings numpy. |
| openpyxl (>=3.1, <4) | Reading and writing `.xlsx` with control over cell types. |
| pytest (>=8, <10), dev only | Test suite. |

Declared in `pyproject.toml` and mirrored in `requirements.txt` / `requirements-dev.txt`;
`tests/test_packaging.py` checks that the files agree and that the runtime dependencies are
exactly the third-party packages the code imports. Building requires setuptools 77 or
newer (needed for the `license = "MIT"` field; setuptools 69.5.1 was verified to fail).

## Data model

- Input data: a DataFrame of `string` columns; index `source_row`.
- After number conversion: `Int64` or `Float64` columns (nullable), or text when some
  values could not be converted and `on_error` is `keep`.
- Missing values: `pd.NA`, written as empty cells.
- `render_text()` in `io.py` defines the canonical text form of every value (e.g.
  `1200.5`, not `1200.50`); it is used both for CSV output and for verifying exports.
