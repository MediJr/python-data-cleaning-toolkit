# Known limitations

This is a version 0.1.0 personal portfolio project. The limitations below are known and
deliberate or not yet addressed.

## Tested environment

- Tested **only on Windows 11 with Python 3.14.7** (pandas 3.0.6, openpyxl 3.1.5; numpy
  2.5.3 in the development environment and 2.5.4 in fresh installations).
- `pyproject.toml` declares `requires-python >= 3.11` because pandas 3 requires it, and a
  static check found no syntax newer than Python 3.11. **Python 3.11-3.13 have not been
  run.**
- **macOS and Linux have not been tested.** The code uses only portable standard-library
  features, but that is not a substitute for running the tests there.
- Error messages show paths in the operating system's style (`output\file.csv` on
  Windows); reports always use forward slashes.

## Input files

- Supported: `.csv` and `.xlsx`. Rejected with a message: `.xls`, `.xlsm`, `.xlsb`, `.ods`.
- One worksheet per run. Workbooks with several related sheets must be processed sheet by
  sheet.
- Formulas are read as the value last saved by Excel. A workbook created by a program
  and never recalculated has formulas without a saved value: the toolkit cannot compute
  them, so they are read as empty, but they are counted, reported in a warning and as an
  `uncalculated_formulas` anomaly (data-quality status `issues_found`). Open and save such
  a file in Excel first.
- Excel error values (`#N/A`, `#DIV/0!`, ...) are read as text and counted in a warning.
- **Password-protected workbooks have not been tested.** An encrypted `.xlsx` is not a
  regular zip file, so it is expected to be rejected with the "could not be opened as an
  .xlsx workbook ... may be corrupt, password-protected ..." message, but this has not been
  verified with a real encrypted file.
- Whole files are loaded into memory. One size was measured (100,000 rows, see
  [performance.md](performance.md)): about 0.3 GiB of RAM for the CSV workflow and about
  0.5 GiB for the XLSX workflow on the test machine. Larger files have not been measured,
  and no linear scaling should be assumed.
- `.xlsx` processing is markedly slower than CSV (about 2 minutes versus about 30 seconds
  for 100,000 rows); the share of each phase has not been measured.
- CSV encoding detection tries UTF-8, then UTF-16 (BOM only), then Windows-1252 with a
  warning. Other encodings must be given with `--encoding`.
- Rows in which every cell is empty are skipped on import; their number is reported.
- Duplicate column names in the input are rejected rather than renamed.

## Transformations

- Dates are written as ISO text (`2024-03-15`), not as Excel date cells.
- Numbers in scientific notation (`1e5`) are not parsed. A column with any unconvertible
  value (with `on_error: keep`) stays text.
- In `.xlsx` input, numeric cells are read with `.` as the decimal point, so a `numbers`
  rule with `decimal: ","` would reject them; such columns need `decimal: "."`.
- Title case is naive (`McDonald` → `Mcdonald`).
- No fuzzy matching: similar labels are merged only through explicit mappings.
- No imputation of missing values (by design).

## Reports and statuses

- The JSON report lists every individual issue and conversion failure, so its size grows
  with the number of anomalies (about 10 MB for the 100,000-row benchmark file with
  roughly 30,000 issue occurrences). The Markdown report shows at most 20 entries per list.

- With no validation rules, the data-quality status is `no_rules_configured` and the exit
  code can be `0`. This means the data was **not** checked against acceptance criteria.
- Validation failure counts can overlap: one row can fail several rules. The report gives
  both the number of issues and the number of distinct rows.
- Rule statuses describe the rows present at validation time, including rows that are
  then quarantined.
- Files from an earlier run that the current run does not produce are left untouched
  (with a warning), not deleted.
- If an export fails after the cleaned file was written, that file remains; the report
  marks the execution as failed and lists what was written.

## Windows application control blocking numpy

On the development machine, Windows' application control policy (a security feature such
as Smart App Control) once refused to load a DLL of a freshly installed numpy 2.5.4:

```text
ImportError: DLL load failed while importing mtrand: ... application control policy ...
```

This is a property of that machine's security policy, not of this project. In later fresh
installations on the same machine numpy 2.5.4 loaded normally; the exact cause was not
established. If it happens, options are to retry later, to install the numpy version
already used elsewhere on the machine (e.g. `python -m pip install "numpy==2.5.3"` in the
virtual environment), or to adjust the policy if you administer the machine. The project
does not pin numpy, so this workaround is local to the affected environment.

## Out of scope

Legacy and macro-enabled Excel formats, multi-sheet processing, databases, APIs, web
scraping, scheduled runs, cloud deployment, a graphical interface.
