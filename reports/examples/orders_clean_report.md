# Data cleaning report: orders_raw.xlsx

Generated 2026-10-13T09:24:31+00:00 by python-data-cleaning-toolkit 0.1.0.

| Check | Result |
| --- | --- |
| Execution status | SUCCESS |
| Data-quality status | ISSUES FOUND |
| Input file unchanged | yes (SHA-256 identical before and after) |

**Summary:** Execution succeeded, but 6 type(s) of unresolved issue (10 occurrence(s)) remain. Review them before using the data.

> The data-quality status reflects only the configured rules and the toolkit's built-in checks. It is not a certification that the data is correct or complete.

## Files

| Role | File | Format | Rows | Columns | Status |
| --- | --- | --- | --- | --- | --- |
| Input | orders_raw.xlsx | xlsx | 8 | 7 | source (read-only) |
| Cleaned output | orders_clean.xlsx | xlsx | 6 | 7 | reopened and verified |
| Quarantined rows | orders_clean_quarantine.xlsx | xlsx | 1 | 8 | reopened and verified |
| Removed rows | orders_clean_removed_rows.xlsx | xlsx | 1 | 8 | reopened and verified |

Input sheet: 'Orders' (available: Read me, Orders).

## Dimensions

|  | Rows | Columns |
| --- | --- | --- |
| Before | 8 | 7 |
| After | 6 | 7 |

- Rows removed (duplicates, saved to the removed-rows file): 1
- Rows quarantined (saved to the quarantine file): 1
- Completely empty rows skipped on import: 0

## Cleaning operations (in order)

| # | Operation | Cells changed | Rows removed | Problems |
| --- | --- | --- | --- | --- |
| 1 | Column names: strip=True, collapse_whitespace=True, style=snake_case; 7 renamed | 0 | 0 | 0 |
| 2 | Missing values: empty and whitespace-only cells, no extra tokens marked missing (no imputation) | 0 | 0 | 0 |
| 3 | Text trim, upper case on ['sku'] | 1 | 0 | 0 |
| 4 | Text trim on ['channel'] | 2 | 0 | 0 |
| 5 | Category mapping on 'channel' (3 explicit label(s), case_insensitive=True) | 4 | 0 | 0 |
| 6 | Dates in 'order_date': formats ['%Y-%m-%d', '%d.%m.%Y'] -> %Y-%m-%d; failures kept | 3 | 0 | 2 |
| 7 | Numbers in 'quantity': decimal '.', thousands None; failures kept | 0 | 0 | 2 |
| 8 | Numbers in 'unit_price': decimal '.', thousands None; failures kept | 4 | 0 | 0 |
| 9 | Exact duplicates: 1 detected, 1 removed (first occurrence kept) | 0 | 1 | 0 |
| 10 | Key duplicates on ['order_id', 'sku']: 0 group(s), kept (removal not requested) | 0 | 0 | 0 |

## Renamed columns

| Original | New |
| --- | --- |
| 'Order ID' | 'order_id' |
| 'Order Date' | 'order_date' |
| 'Customer ID' | 'customer_id' |
| 'SKU' | 'sku' |
| 'Quantity' | 'quantity' |
| 'Unit Price' | 'unit_price' |
| 'Channel' | 'channel' |

## Changed cells by column

Cells of the cleaned output whose value differs from the input (removed and quarantined rows excluded):

| Column | Cells changed |
| --- | --- |
| order_date | 2 |
| sku | 1 |
| unit_price | 2 |
| channel | 3 |

Examples (row = row/line number in the input file):

| Column | Row | Before | After |
| --- | --- | --- | --- |
| sku | 3 |  ab-002 | AB-002 |
| channel | 5 | STORE  | STORE |
| channel | 6 | STORE  | STORE |
| channel | 3 | online | Online |
| channel | 5 | STORE | Store |
| order_date | 4 | 01.03.2024 | 2024-03-01 |
| order_date | 5 | 02.03.2024 | 2024-03-02 |
| unit_price | 3 | 5 | 5.0 |
| unit_price | 4 | 12.50 | 12.5 |

## Missing values

| Column | Before | After |
| --- | --- | --- |
| order_id | 1 | 0 |
| unit_price | 1 | 1 |

Missing values are never filled in automatically.

## Conversion failures

| Row | Column | Value | Reason | In cleaned output |
| --- | --- | --- | --- | --- |
| 7 | order_date | 2024-13-01 | does not match any configured date format (or is not a real calendar date) | yes |
| 9 | order_date | 2024-03-06 14:30:00 | does not match any configured date format (or is not a real calendar date) | yes |
| 5 | quantity | two | not a number in the configured format | yes |
| 6 | quantity | two | not a number in the configured format | no (removed/quarantined) |

## Duplicates

- Exact duplicate rows: 1 detected, 1 removed. Rule: identical values in every column (after the cleaning steps above); the first occurrence is kept.
- Key duplicates on ['order_id', 'sku']: 0 group(s) covering 0 row(s), 0 with conflicting values; 0 row(s) removed (removal not requested).

## Validation

| Rule | Check | Action | Status | Failures |
| --- | --- | --- | --- | --- |
| order_id_present | not_null(order_id) | quarantine | failed | 1 |
| customer_id_6_digits | pattern(customer_id) | report | failed | 1 |
| quantity_at_least_1 | range(quantity) | report | failed | 2 |
| channel_allowed | allowed_values(channel) | quarantine | failed | 1 |
| order_date_is_iso_date | type(order_date) | report | failed | 2 |

7 validation issue(s) affecting 5 distinct row(s) of the input (one row can fail several rules, so failure counts can add up to more than the number of rows).

| Rule | Row | Column | Value | Problem |
| --- | --- | --- | --- | --- |
| order_id_present | 8 | order_id |  | 'order_id' is missing |
| customer_id_6_digits | 4 | customer_id | 101 | '101' does not match the pattern \d{6} |
| quantity_at_least_1 | 5 | quantity | two | 'two' is not a number; range cannot be checked |
| quantity_at_least_1 | 7 | quantity | 0 | 0 is below the minimum 1 |
| channel_allowed | 8 | channel | Fax | 'Fax' is not an allowed value |
| order_date_is_iso_date | 7 | order_date | 2024-13-01 | '2024-13-01' is not a date in format %Y-%m-%d |
| order_date_is_iso_date | 9 | order_date | 2024-03-06 14:30:00 | '2024-03-06 14:30:00' is not a date in format %Y-%m-%d |

## Unresolved anomalies

- 3 date/number value(s) in the cleaned output could not be converted (1 more in rows that were removed or quarantined) (see conversion failures).
- Rule order_id_present (not_null(order_id)): 1 failure(s), action = quarantine
- Rule customer_id_6_digits (pattern(customer_id)): 1 failure(s), action = report
- Rule quantity_at_least_1 (range(quantity)): 2 failure(s), action = report
- Rule channel_allowed (allowed_values(channel)): 1 failure(s), action = quarantine
- Rule order_date_is_iso_date (type(order_date)): 2 failure(s), action = report

## Warnings

- Column 'channel': 1 distinct value(s) are not covered by the category mapping and were left unchanged (e.g. 'Fax').
- Column 'order_date': 2 date value(s) could not be converted and were left unchanged.
- Column 'quantity': 2 value(s) could not be converted and were left unchanged; the column is kept as text.
- 1 row(s) have a missing value in ['order_id', 'sku'] and were excluded from key-duplicate checks.

## Input integrity

- SHA-256 before: `83bac20784ee097c5402846a166c3a7397537b4f33089b06d33c70697458f704`
- SHA-256 after: `83bac20784ee097c5402846a166c3a7397537b4f33089b06d33c70697458f704`

The complete configuration, per-step details and before/after profiles are in the JSON report.
