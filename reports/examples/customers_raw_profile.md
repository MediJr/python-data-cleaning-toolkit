# Data profile: customers_raw.csv

Generated 2026-10-13T09:24:26+00:00. Profiling is read-only; no value was changed.

- Format: csv, encoding utf-8, delimiter ','
- Rows: 15, columns: 8
- Missing cells: 5 (empty, whitespace-only, or one of ['N/A', 'NULL'])
- Exact duplicate rows (extra copies): 1
- Completely empty rows skipped on import: 0

## Columns

| Column | Looks like | Missing | Distinct | Flags | Sample values |
| --- | --- | --- | --- | --- | --- |
| Customer ID | integer | 1 | 12 | 14 with leading zeros | 000101, 000102, 000103, 000104, 000105 |
|  Full Name  | text | 0 | 13 | 1 with surrounding spaces; 1 with repeated spaces | Ana Kovač,   ben   okafor , Chloé Martin, Dev Patel, Elif Demir |
| Email | text | 1 | 13 |  | ana.kovac@example.com, BEN.OKAFOR@EXAMPLE.COM, chloe.martin@example.com, dev.... |
| City | text | 0 | 10 | 1 with surrounding spaces | New York,  new york, NEW YORK, NYC, Boston |
| Signup Date | mixed | 0 | 14 | 1 ambiguous dates | 2024-01-15, 15/03/2024, 03/04/2024, 03/15/2024, 2024-02-30 |
| Annual  Spend | mixed | 3 | 11 |  | 1,200.50, $950, 1.234,50, -50, 300 |
| Status | text | 0 | 7 |  | active, Active, inactive, ACTIVE, closed |
| Postal Code | integer | 0 | 13 | 4 with leading zeros | 02108, 10001, 00501, 30301, 2108 |

## Exact duplicate groups (row numbers)

- [9, 10]

"Looks like" describes the values; nothing is converted unless a cleaning rule is configured.
