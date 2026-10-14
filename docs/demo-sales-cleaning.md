# Demo: cleaning a monthly sales export

A complete, reproducible scenario on **synthetic data**: 16 order lines for September 2026,
with anomalies planted on purpose. Every number on this page comes from a real run of the
toolkit; the outputs are committed in [reports/examples/](../reports/examples/README.md)
and a test (`tests/test_samples.py::test_sales_demo_matches_the_scenario_design`) checks
them against the scenario design below.

| | File |
| --- | --- |
| Raw data | [data/sample/sales_raw.csv](../data/sample/sales_raw.csv) |
| Rules | [config/sales_config.json](../config/sales_config.json) |
| Outputs | `reports/examples/sales_clean*.csv`, `sales_clean_report.md` / `.json` |

## Run it

From the project folder, after [installation](../README.md#installation):

```bash
data-clean clean data/sample/sales_raw.csv output/sales_clean.csv --config config/sales_config.json
```

```text
Execution: SUCCESS
Data quality: ISSUES FOUND - Execution succeeded, but 13 type(s) of unresolved issue (19 occurrence(s)) remain. Review them before using the data.
Rows: 16 -> 13 (removed 1, quarantined 2); columns: 8 -> 8
Wrote cleaned: output/sales_clean.csv (13 rows, verified)
Wrote quarantine: output/sales_clean_quarantine.csv (2 rows, verified)
Wrote removed_rows: output/sales_clean_removed_rows.csv (1 rows, verified)
Report: output/sales_clean_report.json
Report: output/sales_clean_report.md
6 warning(s); see the report.
```

Exit code `3`: the run succeeded, but some values need a human decision. Running the
command again fails until `--overwrite` is added (existing files are never replaced
silently).

## 1. Raw data (excerpt)

Line numbers as in the file (header = line 1):

```text
 1  Order ID,Order Date, Region ,Channel,SKU,Quantity,Unit Price,Sales  Rep
 3  SO-1002,2026-09-02, north ,online,00456,1,$89.90,  Ana   Silva
 4  SO-1003,15/09/2026,NORTH,Web,00123,5,"$1,250.00",Ana Silva
 5  SO-1004,05/09/2026,South,Store,00789,3,$15.00,Ben Osei
 6  SO-1005,2026-09-31,South,STORE,00456,1,$89.90,Ben Osei
 7  SO-1006,2026-09-12,Sth,Store,00789,N/A,$15.00,Ben Osei
 9  SO-1008,2026-09-14,East,Phone,00456,4,"12,5",Chen Li
12  SO-1009,2026-09-20,West,Online,00789,10,$15.00,Dara Kim     (same as line 11)
13  ,2026-09-21,West,Online,00123,1,"$1,250.00",Dara Kim
14  SO-1011,2026-09-22,West,Fax,00456,2,$89.90,Dara Kim
```

## 2. Rules applied

| Rule in `sales_config.json` | Effect |
| --- | --- |
| `column_names: snake_case` | ` Region ` → `region`, `Sales  Rep` → `sales_rep` |
| `missing_values: N/A, NULL` | these tokens become empty (never filled in) |
| `text` | trim; collapse repeated spaces in `sales_rep` |
| `categories` (explicit mappings, case-insensitive) | `north`/`NORTH` → `North`; `online`/`Web` → `Online`; `STORE` → `Store` |
| `dates` `%Y-%m-%d`, `%d/%m/%Y`, `%m/%d/%Y` | converted to ISO only when exactly one reading exists |
| `numbers` `unit_price`: thousands `,`, strip `$` | `$1,250.00` → `1250` |
| `duplicates`: remove exact, report keys `order_id + sku` | exact copy removed and saved; same key with different values kept and reported |
| 11 `validation` rules | two quarantine rows (missing order ID, unknown channel); the others report |

## 3. What the toolkit did

| Line | Before | After | Why |
| --- | --- | --- | --- |
| 3 | ` north `, `online`, `  Ana   Silva ` | `North`, `Online`, `Ana Silva` | explicit mappings, trimming |
| 4 | `15/09/2026`, `Web` | `2026-09-15`, `Online` | only one date reading possible; explicit mapping |
| 2, 4, 8, 13, 15 | `$1,250.00` | `1250` | configured currency symbol and thousands separator |
| 7 | quantity `N/A` | empty | configured missing token |
| 16 | region `NULL` | empty | configured missing token |
| 12 | exact copy of line 11 | removed, saved in `sales_clean_removed_rows.csv` | `remove_exact` |
| 13 | missing `order_id` | moved to `sales_clean_quarantine.csv` | `order_id_present` (quarantine) |
| 14 | channel `Fax` | moved to `sales_clean_quarantine.csv` | `channel_allowed` (quarantine) |

## 4. What it deliberately did **not** change (reported instead)

| Line | Value | Reported as |
| --- | --- | --- |
| 5 | `05/09/2026` | ambiguous date (5 September or 9 May) |
| 6 | `2026-09-31` | not a real date |
| 9 | `12,5` | not a number in the configured format (decimal comma?) |
| 7 | region `Sth` | not in the mapping (probably South: a person decides) |
| 8 | quantity `-2` | below the minimum 1 (a return?) |
| 9, 10 | `SO-1008` + `00456` twice, different quantity and price | key duplicate, both rows kept |
| 15 | SKU `0123`, date `2026-10-02` | not 5 digits; outside September |
| all | SKU `00123`, `00456`, ... | kept as text: leading zeros preserved |

## 5. Results (observed)

From [reports/examples/sales_clean_report.md](../reports/examples/sales_clean_report.md):

| Measure | Value |
| --- | --- |
| Rows in the raw file | 16 |
| Rows in the cleaned file | 13 |
| Rows removed (exact duplicate) | 1 |
| Rows quarantined | 2 |
| Cells changed in the cleaned file | 21 (region 3, channel 3, order date 1, quantity 1, unit price 12, sales rep 1) |
| Conversion failures kept and reported | 3 (2 dates, 1 price) |
| Validation failures | 15, on 10 distinct input rows (11 rules) |
| Unresolved issue types / occurrences | 13 / 19 |
| Output files reopened and verified | 3 of 3 |
| Input file unchanged | yes (same SHA-256 before and after) |
| Exit code | 3 (success, issues to review) |

Final file, first rows ([reports/examples/sales_clean.csv](../reports/examples/sales_clean.csv)):

```text
order_id,order_date,region,channel,sku,quantity,unit_price,sales_rep
SO-1001,2026-09-01,North,Online,00123,2,1250,Ana Silva
SO-1002,2026-09-02,North,Online,00456,1,89.9,Ana Silva
SO-1003,2026-09-15,North,Online,00123,5,1250,Ana Silva
SO-1004,05/09/2026,South,Store,00789,3,15,Ben Osei
SO-1005,2026-09-31,South,Store,00456,1,89.9,Ben Osei
```

The `unit_price` column stays **text** in this run because one value (`12,5`) could not be
converted; converted values are written in canonical form (`1250`, `89.9`). Once the
remaining issues are fixed at the source, the column becomes numeric.

## 6. Reports

- [sales_clean_report.md](../reports/examples/sales_clean_report.md): statuses, files,
  every operation with its change count, before/after examples, conversion failures,
  duplicates, validation failures row by row, warnings and the input fingerprint.
- [sales_clean_report.json](../reports/examples/sales_clean_report.json): the same plus
  the full configuration and the profiles before and after.

## Regenerate and verify

```bash
python scripts/regenerate_examples.py
python -m pytest -q tests/test_samples.py
```

The script reruns every example command; the tests fail if a committed output differs
from a fresh run (only the report timestamp may differ) or if the results no longer match
the scenario above.
