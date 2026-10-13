# Data cleaning report: customers_raw.csv

Generated 2026-10-13T09:24:29+00:00 by python-data-cleaning-toolkit 0.1.0.

| Check | Result |
| --- | --- |
| Execution status | SUCCESS |
| Data-quality status | ISSUES FOUND |
| Input file unchanged | yes (SHA-256 identical before and after) |

**Summary:** Execution succeeded, but 11 type(s) of unresolved issue (22 occurrence(s)) remain. Review them before using the data.

> The data-quality status reflects only the configured rules and the toolkit's built-in checks. It is not a certification that the data is correct or complete.

## Files

| Role | File | Format | Rows | Columns | Status |
| --- | --- | --- | --- | --- | --- |
| Input | customers_raw.csv | csv | 15 | 8 | source (read-only) |
| Cleaned output | customers_clean.csv | csv | 11 | 8 | reopened and verified |
| Quarantined rows | customers_clean_quarantine.csv | csv | 3 | 9 | reopened and verified |
| Removed rows | customers_clean_removed_rows.csv | csv | 1 | 9 | reopened and verified |

Input read as utf-8 with delimiter ',' (detected).

## Dimensions

|  | Rows | Columns |
| --- | --- | --- |
| Before | 15 | 8 |
| After | 11 | 8 |

- Rows removed (duplicates, saved to the removed-rows file): 1
- Rows quarantined (saved to the quarantine file): 3
- Completely empty rows skipped on import: 0

## Cleaning operations (in order)

| # | Operation | Cells changed | Rows removed | Problems |
| --- | --- | --- | --- | --- |
| 1 | Column names: strip=True, collapse_whitespace=True, style=snake_case; 8 renamed | 0 | 0 | 0 |
| 2 | Missing values: empty and whitespace-only cells plus tokens ['N/A', 'NULL'] marked missing (no imputation) | 3 | 0 | 0 |
| 3 | Text trim, collapse spaces on ['full_name', 'city', 'status'] | 2 | 0 | 0 |
| 4 | Text trim, lower case on ['email'] | 1 | 0 | 0 |
| 5 | Category mapping on 'city' (7 explicit label(s), case_insensitive=True) | 4 | 0 | 0 |
| 6 | Category mapping on 'status' (3 explicit label(s), case_insensitive=True) | 2 | 0 | 0 |
| 7 | Dates in 'signup_date': formats ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'] -> %Y-%m-%d; failures kept | 2 | 0 | 3 |
| 8 | Numbers in 'annual_spend': decimal '.', thousands ',', strip '$'; failures kept | 2 | 0 | 2 |
| 9 | Exact duplicates: 1 detected, 1 removed (first occurrence kept) | 0 | 1 | 0 |
| 10 | Key duplicates on ['customer_id']: 1 group(s), kept (removal not requested) | 0 | 0 | 0 |

## Renamed columns

| Original | New |
| --- | --- |
| 'Customer ID' | 'customer_id' |
| ' Full Name ' | 'full_name' |
| 'Email' | 'email' |
| 'City' | 'city' |
| 'Signup Date' | 'signup_date' |
| 'Annual  Spend' | 'annual_spend' |
| 'Status' | 'status' |
| 'Postal Code' | 'postal_code' |

## Changed cells by column

Cells of the cleaned output whose value differs from the input (removed and quarantined rows excluded):

| Column | Cells changed |
| --- | --- |
| full_name | 1 |
| email | 1 |
| city | 4 |
| signup_date | 2 |
| annual_spend | 5 |
| status | 2 |

Examples (row = row/line number in the input file):

| Column | Row | Before | After |
| --- | --- | --- | --- |
| annual_spend | 4 | N/A |  |
| annual_spend | 13 | NULL |  |
| full_name | 3 |   ben   okafor  | ben okafor |
| city | 3 |  new york | new york |
| email | 3 | BEN.OKAFOR@EXAMPLE.COM | ben.okafor@example.com |
| city | 3 | new york | New York |
| city | 4 | NEW YORK | New York |
| status | 3 | Active | active |
| status | 5 | ACTIVE | active |
| signup_date | 3 | 15/03/2024 | 2024-03-15 |
| signup_date | 5 | 03/15/2024 | 2024-03-15 |
| annual_spend | 2 | 1,200.50 | 1200.5 |
| annual_spend | 3 | $950 | 950 |

## Missing values

| Column | Before | After |
| --- | --- | --- |
| customer_id | 1 | 0 |
| email | 1 | 1 |
| annual_spend | 3 | 3 |

Missing values are never filled in automatically.

## Conversion failures

| Row | Column | Value | Reason | In cleaned output |
| --- | --- | --- | --- | --- |
| 4 | signup_date | 03/04/2024 | ambiguous date: %d/%m/%Y -> 2024-04-03, %m/%d/%Y -> 2024-03-04 | yes |
| 6 | signup_date | 2024-02-30 | does not match any configured date format (or is not a real calendar date) | yes |
| 12 | signup_date | yesterday | does not match any configured date format (or is not a real calendar date) | no (removed/quarantined) |
| 5 | annual_spend | 1.234,50 | not a number in the configured format | yes |
| 12 | annual_spend | twelve hundred | not a number in the configured format | no (removed/quarantined) |

## Duplicates

- Exact duplicate rows: 1 detected, 1 removed. Rule: identical values in every column (after the cleaning steps above); the first occurrence is kept.
- Key duplicates on ['customer_id']: 1 group(s) covering 2 row(s), 1 with conflicting values; 0 row(s) removed (removal not requested).

| Key | Rows | Columns that differ |
| --- | --- | --- |
| {'customer_id': '000106'} | [7, 8] | email, signup_date, annual_spend |

## Validation

| Rule | Check | Action | Status | Failures |
| --- | --- | --- | --- | --- |
| required_columns | required_columns(customer_id, email, signup_date) | report | passed | 0 |
| id_present | not_null(customer_id) | quarantine | failed | 1 |
| id_unique | unique(customer_id) | report | failed | 2 |
| email_present | not_null(email) | report | failed | 1 |
| email_format | pattern(email) | report | failed | 1 |
| status_allowed | allowed_values(status) | quarantine | failed | 2 |
| signup_is_iso_date | type(signup_date) | report | failed | 3 |
| signup_in_range | date_range(signup_date) | report | failed | 4 |
| spend_non_negative | range(annual_spend) | report | failed | 3 |
| postal_code_5_digits | pattern(postal_code) | report | failed | 1 |

18 validation issue(s) affecting 9 distinct row(s) of the input (one row can fail several rules, so failure counts can add up to more than the number of rows).

| Rule | Row | Column | Value | Problem |
| --- | --- | --- | --- | --- |
| id_present | 11 | customer_id |  | 'customer_id' is missing |
| id_unique | 7 | customer_id | {'customer_id': '000106'} | value(s) {'customer_id': '000106'} are not unique |
| id_unique | 8 | customer_id | {'customer_id': '000106'} | value(s) {'customer_id': '000106'} are not unique |
| email_present | 7 | email |  | 'email' is missing |
| email_format | 12 | email | ivan.petrov@example | 'ivan.petrov@example' does not match the pattern [^@\s]+@[^@\s]+\.[^@\s]+ |
| status_allowed | 12 | status | on hold | 'on hold' is not an allowed value |
| status_allowed | 15 | status | unknown | 'unknown' is not an allowed value |
| signup_is_iso_date | 4 | signup_date | 03/04/2024 | '03/04/2024' is not a date in format %Y-%m-%d |
| signup_is_iso_date | 6 | signup_date | 2024-02-30 | '2024-02-30' is not a date in format %Y-%m-%d |
| signup_is_iso_date | 12 | signup_date | yesterday | 'yesterday' is not a date in format %Y-%m-%d |
| signup_in_range | 4 | signup_date | 03/04/2024 | '03/04/2024' is not a date in format %Y-%m-%d; range cannot be checked |
| signup_in_range | 6 | signup_date | 2024-02-30 | '2024-02-30' is not a date in format %Y-%m-%d; range cannot be checked |
| signup_in_range | 12 | signup_date | yesterday | 'yesterday' is not a date in format %Y-%m-%d; range cannot be checked |
| signup_in_range | 13 | signup_date | 2031-01-01 | 2031-01-01 is after 2026-12-31 |
| spend_non_negative | 5 | annual_spend | 1.234,50 | '1.234,50' is not a number; range cannot be checked |
| spend_non_negative | 6 | annual_spend | -50 | -50 is below the minimum 0 |
| spend_non_negative | 12 | annual_spend | twelve hundred | 'twelve hundred' is not a number; range cannot be checked |
| postal_code_5_digits | 6 | postal_code | 2108 | '2108' does not match the pattern \d{5} |

## Unresolved anomalies

- 3 date/number value(s) in the cleaned output could not be converted (2 more in rows that were removed or quarantined) (see conversion failures).
- 1 key value(s) in ['customer_id'] appear on several rows (1 with conflicting values); rows were kept.
- Rule id_present (not_null(customer_id)): 1 failure(s), action = quarantine
- Rule id_unique (unique(customer_id)): 2 failure(s), action = report
- Rule email_present (not_null(email)): 1 failure(s), action = report
- Rule email_format (pattern(email)): 1 failure(s), action = report
- Rule status_allowed (allowed_values(status)): 2 failure(s), action = quarantine
- Rule signup_is_iso_date (type(signup_date)): 3 failure(s), action = report
- Rule signup_in_range (date_range(signup_date)): 4 failure(s), action = report
- Rule spend_non_negative (range(annual_spend)): 3 failure(s), action = report
- Rule postal_code_5_digits (pattern(postal_code)): 1 failure(s), action = report

## Warnings

- Column 'city': 1 distinct value(s) are not covered by the category mapping and were left unchanged (e.g. 'Bostn').
- Column 'status': 2 distinct value(s) are not covered by the category mapping and were left unchanged (e.g. 'on hold', 'unknown').
- Column 'signup_date': 3 date value(s) could not be converted and were left unchanged.
- Column 'annual_spend': 2 value(s) could not be converted and were left unchanged; the column is kept as text.
- 1 row(s) have a missing value in ['customer_id'] and were excluded from key-duplicate checks.
- 1 key value(s) in ['customer_id'] appear on more than one row (1 with differing values in other columns); rows were kept (removal not requested).

## Input integrity

- SHA-256 before: `220b8b8dc8bdcb31e19587e6e5d1cf4d463402425d30070fc4d2117e208f5e7c`
- SHA-256 after: `220b8b8dc8bdcb31e19587e6e5d1cf4d463402425d30070fc4d2117e208f5e7c`

The complete configuration, per-step details and before/after profiles are in the JSON report.
