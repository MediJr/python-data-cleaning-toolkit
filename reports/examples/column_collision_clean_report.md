# Data cleaning report: column_collision.csv

Generated 2026-10-13T09:24:34+00:00 by python-data-cleaning-toolkit 0.1.0.

| Check | Result |
| --- | --- |
| Execution status | FAILED |
| Data-quality status | NOT ASSESSED (execution failed) |
| Input file unchanged | yes (SHA-256 identical before and after) |

**Summary:** Execution failed, so data quality was not assessed. No cleaned output should be used from this run.

> The data-quality status reflects only the configured rules and the toolkit's built-in checks. It is not a certification that the data is correct or complete.

**Error (ColumnCollisionError):** Column-name normalization would merge distinct columns: 'Order ID' / 'order_id' -> 'order_id'. Add explicit renames for these columns or disable the conflicting option.

## Files

| Role | File | Format | Rows | Columns | Status |
| --- | --- | --- | --- | --- | --- |
| Input | column_collision.csv | csv | 2 | 3 | source (read-only) |
| Cleaned output | reports/examples/column_collision_clean.csv |  |  |  | NOT WRITTEN |

Input read as utf-8 with delimiter ',' (detected).

## Dimensions

|  | Rows | Columns |
| --- | --- | --- |
| Before | 2 | 3 |
| After |  |  |

- Rows removed (duplicates, saved to the removed-rows file): 0
- Rows quarantined (saved to the quarantine file): 0
- Completely empty rows skipped on import: 0

## Missing values

No missing values detected.

## Validation

Validation did not run.

## Unresolved anomalies

None detected by the configured checks.

## Warnings

None.

## Input integrity

- SHA-256 before: `c4e2e7979a0e31abdfe0ec0b871ca16ae2e7eaa733db52d194b744e0570ef882`
- SHA-256 after: `c4e2e7979a0e31abdfe0ec0b871ca16ae2e7eaa733db52d194b744e0570ef882`

The complete configuration, per-step details and before/after profiles are in the JSON report.
