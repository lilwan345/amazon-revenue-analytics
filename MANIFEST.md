# MANIFEST — Amazon Revenue Analytics

Audit trail for inputs, output tables, figures, code artifacts, and runtime metadata across Layer 1, Layer 2, and Layer 3.

**Generated:** 2026-05-19T22:23:10

## Inputs (data/raw/, gitignored)

| File | SHA-256 | Size |
|---|---|---|
| `data/raw/amazon-purchases.csv` | `ab901175e049c729a85583755428310d72c1a191341cdc0e5b2af3b0364d7286` | 173,255,517 B |
| `data/raw/survey.csv` | `ac9c733b2948daeeb35638ab2771ae9f3c5055b8a1d224c19308a8d768c7d103` | 1,342,356 B |
| `data/raw/fields.csv` | `efc8cd46cb8508cdeb41b908cf6964ca953755e7d1b339e1ccadc839b62f636e` | 2,532 B |

## Output tables (outputs/tables/, gitignored — regenerable from notebooks)

| File | Source | Rows | Schema (n cols) |
|---|---|---|---|
| `outputs/tables/user_gmv.parquet` | `sql/01_user_gmv_capped.sql` | 2,845 | 6 |
| `outputs/tables/user_gmv_deciles.parquet` | `sql/02_decile_assignment.sql` | 2,845 | 7 |
| `outputs/tables/decile_contribution.parquet` | `sql/03_decile_contribution.sql` | 10 | 5 |
| `outputs/tables/concentration_drivers.parquet` | `Layer 1 — log decomposition` | 3 | 5 |
| `outputs/tables/demographic_overindex_with_ci.parquet` | `sql/04_demographic_join.sql + bootstrap CI` | 41 | 10 |
| `outputs/tables/household_features.parquet` | `sql/05_household_features.sql` | 2,845 | 9 |
| `outputs/tables/q3_outcome.parquet` | `sql/06_q3_outcome.sql` | 2,845 | 2 |
| `outputs/tables/model_coefficients.parquet` | `Layer 2 — coefficient + bootstrap CI` | 8 | 9 |
| `outputs/tables/rar_per_household.parquet` | `Layer 2 — RaR = P × E[GMV]` | 2,845 | 6 |
| `outputs/tables/rar_by_segment_with_ci.parquet` | `Layer 2 — segment-level RaR + bootstrap` | 51 | 8 |
| `outputs/tables/category_taxonomy.json` | `Layer 3 — Claude Opus 4.7 taxonomy` | 1,817 | — |
| `outputs/tables/category_taxonomy_mapping.csv` | `Layer 3 — flattened taxonomy for SQL JOIN` | 1,816 | 2 |
| `outputs/tables/category_yearly.parquet` | `sql/07_category_rollup.sql` | 60 | 6 |
| `outputs/tables/category_scale_growth.parquet` | `Layer 3 — scale + CAGR + bootstrap CI` | 12 | 13 |
| `outputs/tables/category_layer_crosswalk.parquet` | `Layer 3 — Layer 1 deciles + Layer 2 RaR overlay` | 12 | 8 |
| `outputs/tables/category_cohort_gateway.parquet` | `Layer 3 — new vs established cohort lift` | 12 | 8 |

## Output figures (outputs/figures/, committed @ 300 DPI, organized by layer)

### Layer 1 — `outputs/figures/layer1/`

| File | DPI | Size | Purpose |
|---|---|---|---|
| `layer1/lorenz_curve.png` | 300 | 262 KB | Layer 1 hero — Lorenz + Gini = 0.529 |
| `layer1/decile_contribution_bar.png` | 300 | 216 KB | Layer 1 supporting — decile GMV % |
| `layer1/concentration_over_time.png` | 300 | 287 KB | Layer 1 conditional — dual axis Gini + GMV |

### Layer 2 — `outputs/figures/layer2/`

| File | DPI | Size | Purpose |
|---|---|---|---|
| `layer2/decile_rar_ladder.png` | 300 | 206 KB | Layer 2 hero — RaR by decile |
| `layer2/coefficient_chart.png` | 300 | 194 KB | Layer 2 model interpretability |
| `layer2/calibration_curve.png` | 300 | 219 KB | Layer 2 model trustworthiness — bin-numbered |
| `layer2/roc_curve.png` | 300 | 200 KB | Layer 2 ROC supporting |

### Layer 3 — `outputs/figures/layer3/`

| File | DPI | Size | Purpose |
|---|---|---|---|
| `layer3/category_allocation_matrix.png` | 300 | 391 KB | Layer 3 hero — 4-D Scale × Growth × bubble × color |
| `layer3/category_ranking_table.png` | 300 | 345 KB | Layer 3 supporting — CAGR ranking with bootstrap CI |
| `layer3/category_gateway_lift.png` | 300 | 283 KB | Layer 3 supporting — new vs established cohort lift |

## Code artifacts

| File | Purpose |
|---|---|
| `sql/01_user_gmv_capped.sql` | Layer 1: user-level GMV with STRPTIME cohort cap |
| `sql/02_decile_assignment.sql` | Layer 1: NTILE(10) decile assignment |
| `sql/03_decile_contribution.sql` | Layer 1: decile percent rollup |
| `sql/04_demographic_join.sql` | Layer 1: decile × demographic over-index |
| `sql/05_household_features.sql` | Layer 2: 8 features + walk-forward leakage guard |
| `sql/06_q3_outcome.sql` | Layer 2: is_dropoff_q3 outcome variable |
| `sql/07_category_rollup.sql` | Layer 3: super-category × year rollup (taxonomy JOIN) |
| `src/data_loader.py` | Polars / DuckDB loaders + date probe |
| `src/stats_utils.py` | Gini, Lorenz, bootstrap over-index CI |
| `src/viz_utils.py` | Finance-clean matplotlib styling + lock palette |
| `src/manifest_utils.py` | SHA256 + MANIFEST writer |

## Runtime characteristics

- Layer 1 over-index CI: 1,000 iter × 41 (dim, value) pairs = 41K resamples, ~0.5 sec.
- Layer 2 AUC + coefficient CIs: 1,000 iter × full LR re-fit per iter = 1K LR fits, ~2.5 sec.
- Layer 2 shuffle-label diagnostic: 50 iter × full LR re-fit per iter, ~0.1 sec.
- Layer 2 segment-RaR CIs: 1,000 iter × 51 segments = 51K resamples, ~0.2 sec.
- Layer 3 scale/CAGR/per-hh CIs: 1,000 iter × 12 super-categories, ~7 sec.
- Layer 3 cohort-gateway CIs: 1,000 iter × 12 super-categories, ~3 sec.

## Reproducibility Notes

- **Random seeds:** All stochastic operations seed=42 (bootstrap, shuffles, model training). Shuffle-label diagnostic uses seed=123 to differentiate from main bootstrap.
- **Dependency pinning:** See `requirements.txt`. Critical versions: DuckDB ≥ 1.0, Polars ≥ 1.0, scikit-learn ≥ 1.5.
- **Python version:** 3.11+ (developed on 3.13.9).
- **Order Date parsing:** Raw is `M/D/YY`; all SQL uses `STRPTIME("Order Date", '%-m/%-d/%y')`. Implicit `CAST AS DATE` would silently NULL 71% of rows.
- **Walk-forward boundary:** Layer 2 features in `sql/05_household_features.sql` are filtered at the SQL level to `Order Date < 2022-07-01`. Outcome in `sql/06_q3_outcome.sql` reads strictly post-cutoff data. Shuffle-label diagnostic empirically validates no leakage (median AUC = 0.54, max = 0.57 across 50 shuffles, well below the 0.60 leakage-suspicion threshold).
- **Layer 3 taxonomy:** `outputs/tables/category_taxonomy.json` (Claude Opus 4.7) commits both `raw_to_super` and `super_to_raw` dicts + a `coverage_summary`. 89.0% of GMV mapped to specific super-category; 5.4% NULL bucket (observable missing); 5.7% `Other / Unknown` long-tail. 50-row spot-check audit caught 3 false positives, patched before commit.
- **Data versioning:** Source CSVs are not committed (gitignored).

## Changelog

- 2026-05-19 — Figure reorg: 10 PNGs moved into outputs/figures/{layer1,layer2,layer3}/ subdirs. Calibration curve bin labels added. Layer 3 figure label/whisker overlaps fixed.
- 2026-05-19 — Layer 3 shipped: taxonomy + 6 parquets + 3 figures + sql/07 + notebook 03 + README integration
- 2026-05-19 — Layer 2 polish (figure aspect, CI determinism, narrative audit pass)
- 2026-05-18 — Layer 2 shipped: notebook 02 + 5 figures + sql/05 + sql/06 + 5 parquets
- 2026-05-18 — Layer 1 shipped: notebook 01 + 3 figures + sql/01-04 + 5 parquets
