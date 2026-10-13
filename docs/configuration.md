# Configuration reference

The cleaning rules are a JSON object passed with `--config FILE`. Every key is optional;
an omitted key takes the default shown below. The file is validated strictly before any
data is read:

- unknown keys are rejected (`Unknown key(s) in missing_values: token`), so a typo never
  silently disables a rule;
- wrong types and invalid values are rejected with the exact key name;
- contradictory rules are rejected (see [Conflicts](#conflicts-that-are-rejected)).

Column names used in `text`, `categories`, `dates`, `numbers`, `duplicates` and
`validation` are the names **after** column-name normalization. If a configured column
does not exist, the run stops and the error says whether the column was renamed (for
example `'Amount' (renamed to 'amount' by column-name normalization)`).

The defaults live in one place in the code: `DEFAULTS` in
[`src/data_cleaning/config.py`](../src/data_cleaning/config.py).

## Processing order

The order is fixed, so the same input and configuration always give the same result:

1. `column_names`
2. `missing_values`
3. `text` (each rule in order)
4. `categories` (each mapping in order)
5. `dates`
6. `numbers`
7. exact duplicates, then key duplicates (`duplicates`)
8. `validation`, then quarantine
9. export, verification, reports

Consequences worth knowing:

- duplicates are compared **after** normalization, so `"Paris "` and `"Paris"` rows can
  become exact duplicates; the raw duplicate count is also shown in the report's profile;
- conversion failures are recorded for every row, including rows later removed or
  quarantined; the report marks whether each failure is still in the cleaned output, and
  only those count as unresolved;
- validation runs on the rows that remain after duplicate removal.

## Top level

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `description` | string or null | `null` | Free text; copied into the JSON report |
| `input` | object | see below | How to read the input |
| `output` | object | see below | How to write CSV/XLSX output |
| `column_names` | object | see below | Column-name normalization |
| `missing_values` | object | see below | What counts as missing |
| `text` | list | `[]` | Text normalization rules |
| `categories` | list | `[]` | Explicit label mappings |
| `dates` | list | `[]` | Date conversions |
| `numbers` | list | `[]` | Number conversions |
| `duplicates` | object | see below | Duplicate handling |
| `validation` | list | `[]` | Validation rules |

## `input`

| Key | Default | Meaning |
| --- | --- | --- |
| `sheet` | `null` | Worksheet name for `.xlsx` (first sheet if null). `--sheet` overrides it. |
| `encoding` | `null` | CSV encoding. Null: UTF-8 (with or without BOM), UTF-16 if a UTF-16 BOM is present, otherwise Windows-1252 **with a warning**. `--encoding` overrides it. |
| `delimiter` | `null` | One CSV character. Null: detected among `,` `;` TAB `\|`; if detection is unreliable the run stops and asks for it. `--delimiter` overrides it. |

## `output`

| Key | Default | Meaning |
| --- | --- | --- |
| `csv_encoding` | `"utf-8"` | Encoding of CSV output. `"utf-8-sig"` helps Excel recognize UTF-8. |
| `csv_delimiter` | `","` | One character. |
| `sheet_name` | `"cleaned"` | Worksheet name of XLSX output (1-31 characters, none of `[]:*?/\`). |

## `column_names`

| Key | Default | Meaning |
| --- | --- | --- |
| `strip` | `true` | Remove spaces around names. |
| `collapse_whitespace` | `true` | `"Annual  Spend"` → `"Annual Spend"`. |
| `style` | `null` | `"snake_case"` (ASCII lower case, other characters → `_`, accents removed: `"Prénom (client)"` → `"prenom_client"`), `"lower"`, or `null`. |
| `rename` | `{}` | Explicit `{"original name": "new name"}`; takes precedence over `style` for those columns. |

If two different columns would end up with the same name, the run stops with a
`ColumnCollisionError` naming both. Use `rename` to resolve it.

## `missing_values`

| Key | Default | Meaning |
| --- | --- | --- |
| `tokens` | `[]` | Extra values meaning "missing", e.g. `["N/A", "NULL"]`. Compared after trimming spaces. |
| `case_sensitive` | `false` | Whether tokens must match case. |
| `whitespace_as_missing` | `true` | Whether whitespace-only cells are missing. |

Empty cells are always missing. Missing values are **never filled in**. `0`, `"unknown"`,
`"n/a"` and similar are ordinary values unless listed in `tokens`.

## `text` (list of rules)

| Key | Default | Meaning |
| --- | --- | --- |
| `columns` | required | Non-empty list of text columns. |
| `strip` | `true` | Remove leading/trailing spaces (including non-breaking spaces). |
| `collapse_whitespace` | `false` | Replace repeated internal spaces by one. |
| `case` | `null` | `"lower"`, `"upper"`, `"title"` or `null`. Title case can damage names (`McDonald` → `Mcdonald`); use it only where that is acceptable. |

A rule must enable at least one operation.

## `categories` (list of mappings)

| Key | Default | Meaning |
| --- | --- | --- |
| `column` | required | Column to map. |
| `mapping` | required | Non-empty `{"source label": "target label"}`. |
| `case_insensitive` | `false` | If true, keys match regardless of case and surrounding spaces. |

Only listed labels change. Labels not covered are left unchanged and listed in the
report's warnings (e.g. a typo such as `Bostn`), so the mapping can be extended
deliberately.

## `dates` (list of rules)

| Key | Default | Meaning |
| --- | --- | --- |
| `column` | required | Column to convert. |
| `formats` | required | Non-empty list of Python `strptime` formats, e.g. `["%Y-%m-%d", "%d/%m/%Y"]`. |
| `output_format` | `"%Y-%m-%d"` | `strftime` format of converted values. |
| `on_error` | `"keep"` | `"keep"` leaves unconvertible values unchanged; `"set_missing"` empties them. Both list every failure with its original value. |

A value is converted only if **exactly one** date results from all formats. If two
formats give different dates (`03/04/2024` with `%d/%m/%Y` and `%m/%d/%Y`) the value is
reported as ambiguous. Impossible dates (`2024-02-30`) are invalid. A value with a time
of day (`2024-03-06 14:30:00`) only converts if a format with a time is listed; it is never
truncated silently. `%y` (two-digit year) produces a warning. Dates are written as text,
not as Excel date cells.

Excel cells that contain real dates are read as `YYYY-MM-DD` (or `YYYY-MM-DD HH:MM:SS`),
so include `%Y-%m-%d` in `formats` for workbooks.

## `numbers` (list of rules)

| Key | Default | Meaning |
| --- | --- | --- |
| `column` | required | Column to convert. |
| `decimal` | `"."` | `"."` or `","`. |
| `thousands` | `null` | `","`, `"."`, `" "` (also accepts non-breaking spaces), `"'"` or `null`. Must differ from `decimal`. Groups must have exactly 3 digits. |
| `strip_chars` | `""` | Characters removed before parsing, e.g. `"$€"`. Must not contain digits, signs or the decimal separator. Removing `%` does **not** divide by 100. |
| `allow_leading_zeros` | `false` | By default `007` is refused, because it is probably a code. |
| `on_error` | `"keep"` | As for dates. |

Values must match the configured format exactly: with the default `.` decimal, `1,23` and
`1.234,50` are failures, not guesses. Scientific notation (`1e5`) is not accepted.

Result: if every value converts, the column becomes integer (all whole numbers) or decimal,
and XLSX output uses numeric cells. If some values fail and `on_error` is `"keep"`, the
column stays text: converted values are written in canonical form (`1,200.50` → `1200.5`)
and failures unchanged. Numbers that cannot be stored exactly (integers beyond 64 bits,
decimals with more than about 15 significant digits) are reported instead of rounded.

## `duplicates`

| Key | Default | Meaning |
| --- | --- | --- |
| `remove_exact` | `false` | Remove rows identical in every column; the first occurrence is kept. `--drop-exact-duplicates` sets it to true. |
| `key_columns` | `[]` | Columns that identify a record (e.g. `["order_id", "sku"]`). Duplicates on these columns are detected and reported, including which other columns differ. Rows with a missing key are excluded. |
| `remove_key_duplicates` | `false` | Keep one row per key. Requires `key_columns`. |
| `keep` | `"first"` | `"first"` or `"last"` (file order): which row of a key group is kept. |

Removed rows are written to `<output>_removed_rows` with a `removal_reason`. When removing
key duplicates whose other columns differ, a warning says how many groups were affected.

## `validation` (list of rules)

Common keys:

| Key | Default | Meaning |
| --- | --- | --- |
| `rule` | required | Rule type (below). |
| `id` | `"R1"`, `"R2"`, ... | Identifier used in reports and quarantine reasons. Must be unique. |
| `action` | `"report"` | `"report"` (row stays) or `"quarantine"` (row moved to `<output>_quarantine` with the reason). |
| `description` | `null` | Label used in reports instead of the default one. |

| `rule` | Parameters | Fails when |
| --- | --- | --- |
| `required_columns` | `columns` | a listed column does not exist |
| `not_null` | `column` | the value is missing |
| `type` | `column`, `expected` (`integer`, `number`, `date`), optional `format` (dates, default `%Y-%m-%d`) | the value is not of that type (numbers use `.` as decimal point) |
| `allowed_values` | `column`, `values`, optional `case_sensitive` (default `true`) | the value is not in the list |
| `range` | `column`, `min` and/or `max` (inclusive) | the value is outside the range or not a number |
| `date_range` | `column`, `min` and/or `max`, optional `format` | the date is outside the range or not a date in `format` |
| `pattern` | `column`, `regex` | the whole value does not match the regular expression |
| `unique` | `columns` | the combination of values appears on more than one row (rows with a missing value are ignored) |

Only `not_null` checks missing values; the others skip them. A rule whose column does not
exist is marked `not_evaluated` and counts as a failure; it is never skipped silently. One
row can fail several rules: the report gives the number of issues and the number of
distinct rows affected.

## Conflicts that are rejected

- the same column in two `dates`/`numbers` rules, or in both;
- the same column in two `text` rules;
- two `categories` mappings for the same column;
- a case-insensitive mapping whose keys collide with different targets (`"ny"` → `"New York"` and `"NY"` → `"Nyon"`);
- `remove_key_duplicates` without `key_columns`;
- a `text` rule that enables no operation.

## Complete examples

- [`config/customers_config.json`](../config/customers_config.json): CSV with mixed date
  formats, currency values, category mappings and ten validation rules.
- [`config/orders_config.json`](../config/orders_config.json): Excel orders with key
  duplicates on `order_id` + `sku`.
- [`config/invalid/`](../config/invalid/): configurations that must be refused or must
  fail (used in tests).
