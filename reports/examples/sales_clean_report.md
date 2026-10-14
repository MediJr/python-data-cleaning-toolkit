# Data cleaning report: sales_raw.csv

Generated 2026-10-14T14:48:47+00:00 by python-data-cleaning-toolkit 0.1.0.

| Check | Result |
| --- | --- |
| Execution status | SUCCESS |
| Data-quality status | ISSUES FOUND |
| Input file unchanged | yes (SHA-256 identical before and after) |

**Summary:** Execution succeeded, but 13 type(s) of unresolved issue (19 occurrence(s)) remain. Review them before using the data.

> The data-quality status reflects only the configured rules and the toolkit's built-in checks. It is not a certification that the data is correct or complete.

## Files

| Role | File | Format | Rows | Columns | Status |
| --- | --- | --- | --- | --- | --- |
| Input | sales_raw.csv | csv | 16 | 8 | source (read-only) |
| Cleaned output | sales_clean.csv | csv | 13 | 8 | reopened and verified |
| Quarantined rows | sales_clean_quarantine.csv | csv | 2 | 9 | reopened and verified |
| Removed rows | sales_clean_removed_rows.csv | csv | 1 | 9 | reopened and verified |

Input read as utf-8 with delimiter ',' (detected).

## Dimensions

|  | Rows | Columns |
| --- | --- | --- |
| Before | 16 | 8 |
| After | 13 | 8 |

- Rows removed (duplicates, saved to the removed-rows file): 1
- Rows quarantined (saved to the quarantine file): 2
- Completely empty rows skipped on import: 0

## Cleaning operations (in order)

| # | Operation | Cells changed | Rows removed | Problems |
| --- | --- | --- | --- | --- |
| 1 | Column names: strip=True, collapse_whitespace=True, style=snake_case; 8 renamed | 0 | 0 | 0 |
| 2 | Missing values: empty and whitespace-only cells plus tokens ['N/A', 'NULL'] marked missing (no imputation) | 2 | 0 | 0 |
| 3 | Text trim, collapse spaces on ['sales_rep'] | 1 | 0 | 0 |
| 4 | Text trim on ['region', 'channel'] | 1 | 0 | 0 |
| 5 | Category mapping on 'region' (4 explicit label(s), case_insensitive=True) | 2 | 0 | 0 |
| 6 | Category mapping on 'channel' (4 explicit label(s), case_insensitive=True) | 3 | 0 | 0 |
| 7 | Dates in 'order_date': formats ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'] -> %Y-%m-%d; failures kept | 1 | 0 | 2 |
| 8 | Numbers in 'quantity': decimal '.', thousands None; failures kept | 0 | 0 | 0 |
| 9 | Numbers in 'unit_price': decimal '.', thousands ',', strip '$'; failures kept | 15 | 0 | 1 |
| 10 | Exact duplicates: 1 detected, 1 removed (first occurrence kept) | 0 | 1 | 0 |
| 11 | Key duplicates on ['order_id', 'sku']: 1 group(s), kept (removal not requested) | 0 | 0 | 0 |

## Renamed columns

| Original | New |
| --- | --- |
| 'Order ID' | 'order_id' |
| 'Order Date' | 'order_date' |
| ' Region ' | 'region' |
| 'Channel' | 'channel' |
| 'SKU' | 'sku' |
| 'Quantity' | 'quantity' |
| 'Unit Price' | 'unit_price' |
| 'Sales  Rep' | 'sales_rep' |

## Changed cells by column

Cells of the cleaned output whose value differs from the input (removed and quarantined rows excluded):

| Column | Cells changed |
| --- | --- |
| order_date | 1 |
| region | 3 |
| channel | 3 |
| quantity | 1 |
| unit_price | 12 |
| sales_rep | 1 |

Examples (row = row/line number in the input file):

| Column | Row | Before | After |
| --- | --- | --- | --- |
| region | 16 | NULL |  |
| quantity | 7 | N/A |  |
| sales_rep | 3 |   Ana   Silva  | Ana Silva |
| region | 3 |  north  | north |
| region | 3 | north | North |
| region | 4 | NORTH | North |
| channel | 3 | online | Online |
| channel | 4 | Web | Online |
| order_date | 4 | 15/09/2026 | 2026-09-15 |
| unit_price | 2 | $1,250.00 | 1250 |
| unit_price | 3 | $89.90 | 89.9 |

## Missing values

| Column | Before | After |
| --- | --- | --- |
| order_id | 1 | 0 |
| region | 1 | 1 |
| quantity | 1 | 1 |

Missing values are never filled in automatically.

## Conversion failures

| Row | Column | Value | Reason | In cleaned output |
| --- | --- | --- | --- | --- |
| 5 | order_date | 05/09/2026 | ambiguous date: %d/%m/%Y -> 2026-09-05, %m/%d/%Y -> 2026-05-09 | yes |
| 6 | order_date | 2026-09-31 | does not match any configured date format (or is not a real calendar date) | yes |
| 9 | unit_price | 12,5 | not a number in the configured format | yes |

## Duplicates

- Exact duplicate rows: 1 detected, 1 removed. Rule: identical values in every column (after the cleaning steps above); the first occurrence is kept.
- Key duplicates on ['order_id', 'sku']: 1 group(s) covering 2 row(s), 1 with conflicting values; 0 row(s) removed (removal not requested).

| Key | Rows | Columns that differ |
| --- | --- | --- |
| {'order_id': 'SO-1008', 'sku': '00456'} | [9, 10] | quantity, unit_price |

## Validation

| Rule | Check | Action | Status | Failures |
| --- | --- | --- | --- | --- |
| order_id_present | not_null(order_id) | quarantine | failed | 1 |
| channel_allowed | allowed_values(channel) | quarantine | failed | 1 |
| region_present | not_null(region) | report | failed | 1 |
| region_allowed | allowed_values(region) | report | failed | 1 |
| order_date_is_iso_date | type(order_date) | report | failed | 2 |
| order_date_in_september | date_range(order_date) | report | failed | 3 |
| quantity_present | not_null(quantity) | report | failed | 1 |
| quantity_at_least_1 | range(quantity) | report | failed | 1 |
| unit_price_is_number | type(unit_price) | report | failed | 1 |
| sku_5_digits | pattern(sku) | report | failed | 1 |
| order_line_unique | unique(order_id, sku) | report | failed | 2 |

15 validation issue(s) affecting 10 distinct row(s) of the input (one row can fail several rules, so failure counts can add up to more than the number of rows).

| Rule | Row | Column | Value | Problem |
| --- | --- | --- | --- | --- |
| order_id_present | 13 | order_id |  | 'order_id' is missing |
| channel_allowed | 14 | channel | Fax | 'Fax' is not an allowed value |
| region_present | 16 | region |  | 'region' is missing |
| region_allowed | 7 | region | Sth | 'Sth' is not an allowed value |
| order_date_is_iso_date | 5 | order_date | 05/09/2026 | '05/09/2026' is not a date in format %Y-%m-%d |
| order_date_is_iso_date | 6 | order_date | 2026-09-31 | '2026-09-31' is not a date in format %Y-%m-%d |
| order_date_in_september | 5 | order_date | 05/09/2026 | '05/09/2026' is not a date in format %Y-%m-%d; range cannot be checked |
| order_date_in_september | 6 | order_date | 2026-09-31 | '2026-09-31' is not a date in format %Y-%m-%d; range cannot be checked |
| order_date_in_september | 15 | order_date | 2026-10-02 | 2026-10-02 is after 2026-09-30 |
| quantity_present | 7 | quantity |  | 'quantity' is missing |
| quantity_at_least_1 | 8 | quantity | -2 | -2 is below the minimum 1 |
| unit_price_is_number | 9 | unit_price | 12,5 | '12,5' is not a number |
| sku_5_digits | 15 | sku | 0123 | '0123' does not match the pattern [0-9]{5} |
| order_line_unique | 9 | order_id, sku | {'order_id': 'SO-1008', 'sku': '00456'} | value(s) {'order_id': 'SO-1008', 'sku': '00456'} are not unique |
| order_line_unique | 10 | order_id, sku | {'order_id': 'SO-1008', 'sku': '00456'} | value(s) {'order_id': 'SO-1008', 'sku': '00456'} are not unique |

## Unresolved anomalies

- 3 date/number value(s) in the cleaned output could not be converted (see conversion failures).
- 1 key value(s) in ['order_id', 'sku'] appear on several rows (1 with conflicting values); rows were kept.
- Rule order_id_present (not_null(order_id)): 1 failure(s), action = quarantine
- Rule channel_allowed (allowed_values(channel)): 1 failure(s), action = quarantine
- Rule region_present (not_null(region)): 1 failure(s), action = report
- Rule region_allowed (allowed_values(region)): 1 failure(s), action = report
- Rule order_date_is_iso_date (type(order_date)): 2 failure(s), action = report
- Rule order_date_in_september (date_range(order_date)): 3 failure(s), action = report
- Rule quantity_present (not_null(quantity)): 1 failure(s), action = report
- Rule quantity_at_least_1 (range(quantity)): 1 failure(s), action = report
- Rule unit_price_is_number (type(unit_price)): 1 failure(s), action = report
- Rule sku_5_digits (pattern(sku)): 1 failure(s), action = report
- Rule order_line_unique (unique(order_id, sku)): 2 failure(s), action = report

## Warnings

- Column 'region': 1 distinct value(s) are not covered by the category mapping and were left unchanged (e.g. 'Sth').
- Column 'channel': 1 distinct value(s) are not covered by the category mapping and were left unchanged (e.g. 'Fax').
- Column 'order_date': 2 date value(s) could not be converted and were left unchanged.
- Column 'unit_price': 1 value(s) could not be converted and were left unchanged; the column is kept as text.
- 1 row(s) have a missing value in ['order_id', 'sku'] and were excluded from key-duplicate checks.
- 1 key value(s) in ['order_id', 'sku'] appear on more than one row (1 with differing values in other columns); rows were kept (removal not requested).

## Input integrity

- SHA-256 before: `356b7d1daf036cffbe29dbf0065fc8ad7198db4d3fa80d9f24f7c6aef220249f`
- SHA-256 after: `356b7d1daf036cffbe29dbf0065fc8ad7198db4d3fa80d9f24f7c6aef220249f`

The complete configuration, per-step details and before/after profiles are in the JSON report.
