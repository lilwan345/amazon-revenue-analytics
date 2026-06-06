# MANIFEST — Amazon Revenue Analytics

> Generated and updated incrementally by each layer's notebook.
> Last updated: 2026-06-06 12:22:16 UTC
> Project commit: (uncommitted)

## Inputs

| File | Path | Rows | Size | SHA256 |
|---|---|---|---|---|
| Purchase transactions | `data/raw/amazon-purchases.csv` | 1,850,718 | 298.57 MB | `6efb098a6e01a9acb6e215402a450f4a848ed1b102ca016f9be6c4f03c585e1e` |
| Survey data | `data/raw/survey.csv` | 5,028 | 1.28 MB | `ac9c733b2948daeeb35638ab2771ae9f3c5055b8a1d224c19308a8d768c7d103` |
| Field dictionary | `data/raw/fields.csv` | 36 | 0.00 MB | `efc8cd46cb8508cdeb41b908cf6964ca953755e7d1b339e1ccadc839b62f636e` |

Hashes computed via `hashlib.sha256(path.read_bytes()).hexdigest()` -- see
`src/manifest_utils.py::file_sha256`.

## Outputs — Layer 1

### Tables (`outputs/tables/`)

| File | Rows | Cols | Schema | Source |
|---|---|---|---|---|
| `user_gmv.parquet` | 5,026 | 7 | household_id, total_gmv, pre_cutoff_gmv, n_line_items, first_purchase_date, last_purchase_date, avg_order_value | sql/01_user_gmv_cohort_dated.sql |
| `user_gmv_deciles.parquet` | 5,026 | 8 | household_id, total_gmv, pre_cutoff_gmv, n_line_items, avg_order_value, first_purchase_date, last_purchase_date, decile | sql/02_decile_assignment.sql |
| `decile_contribution.parquet` | 10 | 5 | decile, user_count, decile_gmv, pct_of_total_gmv, cumulative_pct | sql/03_decile_contribution.sql |
| `concentration_drivers.parquet` | 3 | 5 | metric, top_decile_value, bottom50_value, ratio, log_share | notebook cell (Polars) |
| `demographic_overindex_with_ci.parquet` | 42 | 10 | dimension, value, pct_in_top10, pct_in_sample, sample_n, overindex_ratio, ci_lower, ci_upper, significant, included_in_report | notebook cell (Polars + NumPy bootstrap) |

### Figures (`outputs/figures/`)

| File | DPI | Size | Purpose |
|---|---|---|---|
| `lorenz_curve.png` | 300 | 262 KB | Layer 1 hero |
| `decile_contribution_bar.png` | 300 | 221 KB | Layer 1 supporting |
| `concentration_over_time.png` | 300 | 272 KB | Layer 1 conditional time-series |

## Outputs — Layer 2

### Tables (`outputs/tables/`)

| File | Rows | Cols | Schema | Source |
|---|---|---|---|---|
| `household_features.parquet` | 5,026 | 9 | household_id, gmv_trailing_12m, gmv_trailing_24m_lag12m, gmv_trend, line_items_trailing_12m, aov_trailing_12m, recency_days, n_distinct_categories_trailing_12m, aov_slope | sql/05_household_features.sql |
| `q3_outcome.parquet` | 5,026 | 2 | household_id, is_dropoff_q3 | sql/06_q3_outcome.sql |
| `model_coefficients.parquet` | 8 | 9 | feature, coefficient, ci_lower, ci_upper, actual_sign, expected_sign, expected_note, sign_consistent, ci_crosses_zero | notebook cell (sklearn + bootstrap) |
| `rar_per_household.parquet` | 5,026 | 6 | household_id, prob_dropoff_q3, prob_active_q3, expected_q3_gmv, dollar_at_risk, decile | notebook cell (Polars) |
| `rar_by_segment_with_ci.parquet` | 52 | 8 | dimension, value, n_households, rar_total, rar_per_household, rar_share, ci_lower, ci_upper | notebook cell (Polars + bootstrap) |

### Figures (`outputs/figures/`)

| File | DPI | Size | Purpose |
|---|---|---|---|
| `decile_rar_ladder.png` | 300 | 203 KB | Layer 2 hero — embedded in README |
| `coefficient_chart.png` | 300 | 195 KB | Layer 2 model interpretability |
| `calibration_curve.png` | 300 | 220 KB | Layer 2 model trustworthiness |
| `roc_curve.png` | 300 | 202 KB | Layer 2 ROC supporting visual |

## Code artifacts (both layers)

| File | Purpose |
|---|---|
| `sql/01_user_gmv_cohort_dated.sql` | Layer 1: user-level GMV, STRPTIME cohort cap |
| `sql/02_decile_assignment.sql` | Layer 1: NTILE(10) decile assignment |
| `sql/03_decile_contribution.sql` | Layer 1: decile rollup with running cumulative |
| `sql/04_demographic_join.sql` | Layer 1: decile ⨝ survey demographics |
| `sql/05_household_features.sql` | Layer 2: 5 SQL feature aggregates + walk-forward leakage guard |
| `sql/06_q3_outcome.sql` | Layer 2: `is_dropoff_q3` outcome variable |
| `src/data_loader.py` | Polars / DuckDB loaders, Order Date format probe |
| `src/manifest_utils.py` | SHA256 hashing, MANIFEST writer |
| `src/stats_utils.py` | Gini, Lorenz, bootstrap over-index CI |
| `src/viz_utils.py` | Finance-clean matplotlib styling and locked palette |
| `notebooks/01_layer1_concentration.ipynb` | Layer 1 main analysis notebook |
| `notebooks/02_layer2_rar.ipynb` | Layer 2 main analysis notebook |

## Expected Runtime (clean kernel, M-series Mac)

| Notebook | Wall time (observed) | Memory peak |
|---|---|---|
| `01_layer1_concentration.ipynb` | ~30 sec | ~3 GB (Polars peak during 1.85M-row CSV load) |
| `02_layer2_rar.ipynb` | ~45 sec | ~3 GB (Polars peak during 1.85M-row CSV load) |

Bootstrap iteration counts:
- Layer 1 over-index CI: 1,000 iter × 42 (dim, value) pairs = 42K resamples, ~0.5 sec.
- Layer 2 AUC + coefficient CIs: 1,000 iter × full LR re-fit per iter = 1K LR fits, ~2.5 sec.
- Layer 2 shuffle-label diagnostic: 50 iter × full LR re-fit per iter, ~0.1 sec.
- Layer 2 segment-RaR CIs: 1,000 iter × 51 segments = 51K resamples, ~0.2 sec.

## Reproducibility Notes

- **Random seeds:** All stochastic operations seed=42 (bootstrap, shuffles, model training). Shuffle-label diagnostic uses seed=123 to differentiate from main bootstrap.
- **Dependency pinning:** See `requirements.txt`. Critical versions: DuckDB ≥ 1.0, Polars ≥ 1.0, scikit-learn ≥ 1.5.
- **Python version:** 3.11+ (developed on 3.13.9).
- **Order Date parsing:** Raw is ISO 8601 (`YYYY-MM-DD`); all SQL parses it with an explicit `STRPTIME("Order Date", '%Y-%m-%d')` rather than the `read_csv_auto` sniffer, so the parse format is auditable in the SQL itself.
- **Raw-data provenance:** `src/validate_data.py` validates the raw inputs against the published Open e-commerce 1.0 source (5,027 households, >1.8M transactions) and flags the 2^20-1-row spreadsheet-truncation signature; run it before any layer.
- **Walk-forward boundary:** Layer 2 features in `sql/05_household_features.sql` are filtered at the SQL level to `Order Date < 2022-07-01`. Outcome in `sql/06_q3_outcome.sql` reads strictly post-cutoff data. The two files are the only places that touch their respective time windows. Shuffle-label diagnostic empirically validates no leakage (median AUC = 0.53, max = 0.55 across 50 shuffles, well below the 0.60 leakage-suspicion threshold).
- **Data versioning:** Source CSVs are not committed (gitignored).

## Changelog

| Date | Layer | Change |
|---|---|---|
| 2026-05-17 | 1 | Initial MANIFEST: input CSVs hashed during the setup sanity check |
| 2026-05-17 | 1 | Added Layer 1 outputs section: 5 parquet tables, 3 figures |
| 2026-05-18 | 1 | MIT LICENSE added; repo pushed to GitHub |
| 2026-06-06 | 2 | Added Layer 2 outputs section: 5 parquet tables, 4 figures, 2 new SQL files |
| 2026-06-06 | 0 | Re-ran full pipeline on the complete Open e-commerce 1.0 file (5,026 cohort households / 1.85M tx) after the prior raw CSV was found spreadsheet-truncated to 2^20-1 rows; added provenance preflight; migrated date parsing M/D/YY -> ISO |
