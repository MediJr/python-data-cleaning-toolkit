# Example outputs

Every file in this folder (except this README) was produced by running the toolkit's CLI on
the synthetic samples in `data/sample/`. None is edited by hand. To regenerate them:

```bash
python scripts/regenerate_examples.py
```

which runs:

```bash
data-clean profile data/sample/customers_raw.csv --config config/customers_config.json --report-dir reports/examples --overwrite
data-clean clean data/sample/customers_raw.csv reports/examples/customers_clean.csv --config config/customers_config.json --overwrite
data-clean clean data/sample/orders_raw.xlsx reports/examples/orders_clean.xlsx --sheet Orders --config config/orders_config.json --overwrite
data-clean clean data/sample/invalid/column_collision.csv reports/examples/column_collision_clean.csv --config config/invalid/collision_config.json --overwrite
```

| Files | Run |
| --- | --- |
| `customers_raw_profile.*` | Read-only profile of the raw customers file |
| `customers_clean*` | Customers cleaning: cleaned data, quarantined rows, removed duplicate, JSON + Markdown report |
| `orders_clean*` | Excel orders cleaning (same set of files, in `.xlsx`) |
| `column_collision_clean_report.*` | A run that is **refused** (column-name collision): failure report only, no data file |

`tests/test_samples.py::test_committed_examples_match_a_fresh_run` fails if these files no
longer match what the tool produces (only the generation timestamp may differ).
