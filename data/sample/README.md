# Sample data and expected results

All files in this folder are **synthetic**. Names, IDs, addresses and orders are invented;
e-mail addresses use the reserved `example.com` domain. No real person, client or company
is represented.

| File | Purpose |
| --- | --- |
| `customers_raw.csv` | Main CSV example: 15 customer rows with typical quality problems |
| `orders_raw.xlsx` | Excel example (sheet `Orders`; sheet `Read me` is a note). Built by `scripts/build_sample_xlsx.py` |
| `invalid/` | Inputs the tool must refuse (see below) |
| `expected/` | **Hand-written** expected outputs, derived from the rules below before the tool was run. Tests compare the tool's actual output against these files; they are never copied from tool output |

The outputs actually produced by the tool are in [`reports/examples/`](../../reports/examples/).

Row numbers below are line numbers in the CSV (header = line 1) or row numbers in the
worksheet; the tool uses the same numbers in its reports.

## customers_raw.csv with `config/customers_config.json`

```bash
data-clean clean data/sample/customers_raw.csv output/customers_clean.csv --config config/customers_config.json
```

Expected result: execution **success**, data quality **issues found** (exit code 3);
15 rows in, **11 cleaned**, 1 removed (exact duplicate), 3 quarantined.

### Transformations that should happen

| Row | Column | Before | After | Rule |
| --- | --- | --- | --- | --- |
| header | all | `Customer ID`, ` Full Name `, `Annual  Spend`, ... | `customer_id`, `full_name`, `annual_spend`, ... | snake_case column names |
| 3 | full_name | `  ben   okafor ` | `ben okafor` | trim + collapse spaces (case deliberately kept) |
| 3 | email | `BEN.OKAFOR@EXAMPLE.COM` | `ben.okafor@example.com` | lower case (explicit choice in this config) |
| 3, 4, 5 | city | ` new york`, `NEW YORK`, `NYC` | `New York` | explicit category mapping |
| 13 | city | `seattle` | `Seattle` | explicit category mapping |
| 3, 5 | status | `Active`, `ACTIVE` | `active` | explicit category mapping |
| 3 | signup_date | `15/03/2024` | `2024-03-15` | only DD/MM/YYYY fits (15 cannot be a month) |
| 5 | signup_date | `03/15/2024` | `2024-03-15` | only MM/DD/YYYY fits |
| 2 | annual_spend | `1,200.50` | `1200.5` | thousands separator `,` |
| 3 | annual_spend | `$950` | `950` | `$` removed by `strip_chars` |
| 4, 13, 16 | annual_spend | `N/A`, `NULL`, `   ` | empty | configured missing tokens / whitespace-only |
| 10 | (row) | identical to row 9 | removed, saved in `_removed_rows` | `remove_exact: true`, first occurrence kept |

### Values that must stay unchanged (and be reported)

| Row | Column | Value | Why it is not corrected automatically |
| --- | --- | --- | --- |
| 4 | signup_date | `03/04/2024` | Ambiguous: 3 April or 4 March. Both configured formats fit with different results. |
| 6 | signup_date | `2024-02-30` | Not a real date; no correct value can be inferred. |
| 5 | annual_spend | `1.234,50` | European format, but this column's rule is `.` decimal / `,` thousands. Guessing could be wrong by a factor of 1000. |
| 6 | annual_spend | `-50` | Looks wrong (negative spend) but could be a refund: business decision. Reported by `spend_non_negative`. |
| 6 | postal_code | `2108` | Looks like `02108` with a lost leading zero, but padding is a guess. Reported by `postal_code_5_digits`. |
| 14 | annual_spend | `0` | Zero is a real value, not missing. |
| 13 | signup_date | `2031-01-01` | A valid date, but outside the allowed range; reported by `signup_in_range`. |
| 16 | city | `Bostn` | Probably a typo for Boston, but not in the mapping: left unchanged, listed as unmapped. |
| 7, 8 | customer_id | `000106` twice | Same ID, different e-mail/date/spend: could be two real records. Kept, reported as a key duplicate and by `id_unique`. |
| all | customer_id, postal_code | `000101`, `02108`, ... | Identifiers keep their leading zeros (never converted to numbers). |

### Rows quarantined (moved to `_quarantine`, with reason)

| Row | Reason |
| --- | --- |
| 11 | `[id_present] 'customer_id' is missing` |
| 12 | `[status_allowed] 'on hold' is not an allowed value` |
| 15 | `[status_allowed] 'unknown' is not an allowed value` ("unknown" is a value, not missing) |

### Expected report figures

- Missing values before → after: customer_id 1 → 0, email 1 → 1, annual_spend 3 → 3.
- Conversion failures: 5 (rows 4, 6, 12 in signup_date; rows 5, 12 in annual_spend); 3 of them are in the cleaned output.
- Validation: `required_columns` passes; failures: id_present 1, id_unique 2, email_present 1, email_format 1,
  status_allowed 2, signup_is_iso_date 3, signup_in_range 4, spend_non_negative 3, postal_code_5_digits 1.
- 11 unresolved anomaly types, 22 occurrences.

## orders_raw.xlsx (sheet Orders) with `config/orders_config.json`

```bash
data-clean clean data/sample/orders_raw.xlsx output/orders_clean.xlsx --sheet Orders --config config/orders_config.json
```

Expected result: success, issues found (exit 3); 8 rows in, **6 cleaned**, 1 removed, 1 quarantined.

| Row | What happens |
| --- | --- |
| 2, 3 | Real Excel date cells are read as `2024-03-01`; row 3 SKU ` ab-002` → `AB-002`, channel `online` → `Online` |
| 4 | Text date `01.03.2024` → `2024-03-01`; price `12.50` → `12.5`; **customer ID `101` stays `101`**: it was stored as a number in Excel and its leading zeros are already lost; it is reported by `customer_id_6_digits`, not padded |
| 5 | Quantity `two` is not converted (reported), so the quantity column stays text; `STORE ` → `Store` |
| 6 | Exact duplicate of row 5: removed and saved to `_removed_rows` |
| 7 | `2024-13-01` (month 13) kept and reported; quantity `0` kept and reported by `quantity_at_least_1`; missing price stays empty |
| 8 | Missing order ID and channel `Fax`: quarantined with both reasons |
| 9 | `2024-03-06 14:30:00` has a time of day that no configured format accepts: kept unchanged (not truncated to a date) and reported |

Unit prices all convert, so they are written as **numeric** Excel cells. Customer IDs and quantities are written as text.

## Invalid inputs (`invalid/`): the tool must refuse them

| File | Expected behaviour |
| --- | --- |
| `column_collision.csv` + `config/invalid/collision_config.json` | `Order ID` and `order_id` would both become `order_id`: the run fails (exit 1), a failure report is written, **no data file** is produced |
| `ragged_rows.csv` | Line 3 has 2 fields instead of 3: rejected with the line number, nothing written |
| `duplicate_headers.csv` | Two columns named `amount`: rejected |
| `empty.csv` | 0 bytes: rejected |
| `header_only.csv` | Header but no data rows: rejected |
| `config/invalid/typo_config.json` | Unknown key `missing_value` (typo): rejected before reading any data |

These expectations are checked by `tests/test_samples.py`.
