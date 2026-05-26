# MANIFEST — Amazon Revenue Analytics

> Generated and updated incrementally by each layer's notebook.
> Last updated: 2026-05-26 02:33:06 UTC
> Project commit: (uncommitted)

## Inputs

| File | Path | Rows | Size | SHA256 |
|---|---|---|---|---|
| Purchase transactions | `data/raw/amazon-purchases.csv` | 1,048,576 | 165.23 MB | `ab901175e049c729a85583755428310d72c1a191341cdc0e5b2af3b0364d7286` |
| Survey data | `data/raw/survey.csv` | 5,028 | 1.28 MB | `ac9c733b2948daeeb35638ab2771ae9f3c5055b8a1d224c19308a8d768c7d103` |
| Field dictionary | `data/raw/fields.csv` | 36 | 0.00 MB | `efc8cd46cb8508cdeb41b908cf6964ca953755e7d1b339e1ccadc839b62f636e` |

Hashes computed via `hashlib.sha256(path.read_bytes()).hexdigest()` -- see
`src/manifest_utils.py::file_sha256`.

## Outputs — Layer 1

### Tables (`outputs/tables/`)

| File | Rows | Cols | Schema | Source |
|---|---|---|---|---|
| `user_gmv.parquet` | 2,845 | 7 | household_id, total_gmv, pre_cutoff_gmv, n_line_items, first_purchase_date, last_purchase_date, avg_order_value | sql/01_user_gmv_cohort_dated.sql |
| `user_gmv_deciles.parquet` | 2,845 | 8 | household_id, total_gmv, pre_cutoff_gmv, n_line_items, avg_order_value, first_purchase_date, last_purchase_date, decile | sql/02_decile_assignment.sql |
| `decile_contribution.parquet` | 10 | 5 | decile, user_count, decile_gmv, pct_of_total_gmv, cumulative_pct | sql/03_decile_contribution.sql |
| `concentration_drivers.parquet` | 3 | 5 | metric, top_decile_value, bottom50_value, ratio, log_share | notebook cell (Polars) |
| `demographic_overindex_with_ci.parquet` | 41 | 10 | dimension, value, pct_in_top10, pct_in_sample, sample_n, overindex_ratio, ci_lower, ci_upper, significant, included_in_report | notebook cell (Polars + NumPy bootstrap) |

> **Cohort reconciliation: 2,846 vs 2,845.** README/narrative reports the panel as *2,846 consenting households* (the raw join of the 5,027-row survey to households with at least one transaction). Layer 1 analysis operates on **2,845** after the 2023-01-01 cohort date cap: one household, `R_1d1fnT4sjZABBwe`, is excluded — it has a single $1.84 order on 2024-08-15 and no 2018–2022 activity, so it falls outside the cohort window. The audit query that surfaces this exclusion lives in `notebooks/01_layer1_concentration.ipynb` (cell 19).

### Figures (`outputs/figures/`)

| File | DPI | Size | Purpose |
|---|---|---|---|
| `lorenz_curve.png` | 300 | 262 KB | Layer 1 hero visual (README banner) |
| `decile_contribution_bar.png` | 300 | 218 KB | Decile GMV contribution bars |
| `concentration_over_time.png` | 300 | 299 KB | 2018-2022 Gini time series |

### Code artifacts

| File | Purpose |
|---|---|
| `sql/01_user_gmv_cohort_dated.sql` | User-level GMV with explicit STRPTIME cohort cap |
| `sql/02_decile_assignment.sql` | NTILE(10) decile assignment |
| `sql/03_decile_contribution.sql` | Decile percent rollup with running cumulative |
| `sql/04_demographic_join.sql` | Decile-tagged household table joined to survey demographics |
| `src/data_loader.py` | Polars / DuckDB loaders, Order Date format probe |
| `src/manifest_utils.py` | SHA256 hashing, input file dataclass, MANIFEST writer |
| `src/stats_utils.py` | Discrete Gini, Lorenz points, bootstrap over-index CI |
| `src/viz_utils.py` | Finance-clean matplotlib styling and locked palette |
| `notebooks/01_layer1_concentration.ipynb` | Layer 1 main analysis notebook |

## Expected Runtime (clean kernel, M-series Mac)

| Notebook | Wall time (observed) | Memory peak |
|---|---|---|
| `01_layer1_concentration.ipynb` | ~5 sec | ~2 GB (Polars peak during 1M-row CSV load) |

Bootstrap iteration count = 1,000 (seed=42); 41 (dimension, value) pairs x 1,000 iter = 41,000 resamples completed in ~0.5 sec via vectorised NumPy.

## Reproducibility Notes

- **Random seeds:** All stochastic operations seed=42.
- **Dependency pinning:** See `requirements.txt`. Critical versions: DuckDB >= 1.0, Polars >= 1.0.
- **Python version:** 3.11+ (developed on 3.13.9).
- **Order Date parsing:** Raw is `M/D/YY`; all SQL uses `STRPTIME("Order Date", '%-m/%-d/%y')`. Implicit `CAST AS DATE` would silently NULL 71% of rows.
- **Data versioning:** Source CSVs are not committed (gitignored).

## Changelog

| Date | Layer | Change |
|---|---|---|
| 2026-05-26 | 1 | Initial MANIFEST: input CSVs hashed during the setup sanity check |
| 2026-05-26 | 1 | Added Layer 1 outputs section: 5 parquet tables, 3 figures, 9 code artifacts |
