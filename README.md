# Amazon Revenue Analytics
*Concentration, Forward-Looking Revenue-at-Risk, and Growth Allocation*

**A BI framework for finance decision support, built on 2,846 U.S. Amazon households (2018–2022).**

[![Lorenz curve preview](outputs/figures/lorenz_curve.png)](outputs/figures/lorenz_curve.png)

---

## The Question

The Amazon Retail Finance team needs to understand three things to inform next-quarter resource allocation:

1. Where is revenue concentrated, and is concentration growing?
2. Which customer segments represent the largest forward-looking revenue-at-risk in the next quarter?
3. Which categories deserve priority investment given current growth × scale dynamics?

This project answers each question with a dedicated analytical layer.

## The Answer — Layer 1 headline

Within this 2,846-household consenting panel, **the top decile drives 36.2% of GMV** (top 20%: 55.2%; Gini = 0.529). Decomposition reveals the gap is **~94% purchase-frequency, only ~6% basket size** — top-decile households order 11.0× more often (1,222 vs 111 orders over 2018–2022) but spend just 1.18× more per order. The strongest demographic signal in the panel is heavy cadence — households shopping more than 10 times per month over-index **+387% [CI: +324%, +457%]**, dwarfing the next-strongest signal ($150K+ income, +154%). Concentration actually *fell* during COVID (Δ Gini = −0.04 from 2018-19 to 2020-22) while panel GMV nearly doubled — mass-market expansion, not VIP-only concentration. **The data suggests engagement-cadence levers (Prime stickiness, push frequency) would address this concentration driver more directly than premium-tier upsell would — premium-tier strategies would close only ~6% of the per-household gap.**

## The Method

SQL-first analysis (DuckDB) on ~1.05M Amazon transactions, cohort-capped at 2023-01-01 due to post-2023 participant attrition. NTILE(10) for decile assignment; Lorenz curve + Gini for concentration shape; bootstrap 95% CIs (B=1000, seed=42) on demographic over-index ratios. Every core aggregation is cross-validated against a Polars equivalent for byte equality.

## The Caveat

The 2,846 households are a **consenting subsample** of 5,027 Prolific prescreen respondents on the MIT Media Lab dataset — not a random sample of Amazon's broader customer base. Findings reflect this panel only. Demographics are a 2021 snapshot, not a time series.

---

## Methodology notes (data-quality landmines worth flagging)

- **`Order Date` raw format is `M/D/YY`.** Implicit `CAST("Order Date" AS DATE)` parses only **28.6%** of these strings; the other 71% silently NULL. All SQL in `sql/` uses explicit `STRPTIME("Order Date", '%-m/%-d/%y')`. Using CAST would have understated Layer 1 GMV by ~70%. (Caught via Task 6.1 format probe; documented and inlined in `sql/01_user_gmv_capped.sql` header comments.)
- **Cross-validation discipline.** Every core aggregation in Layers 1–3 has a SQL implementation (under `sql/`, the artifact a recruiter screenshots) and a Polars implementation (the dataframe code in the notebook). The two are asserted byte-equal (or float-equal within FP tolerance) before the result is saved. Divergence would surface silent aggregation bugs.
- **Confidence intervals on all reported ratios.** No headline number is reported as a point estimate alone. Bootstrap is non-parametric (B=1000, seed=42), so it makes no normality assumption — appropriate for the heavy-tailed GMV distribution. Findings whose 95% CIs cross zero are recorded in `outputs/tables/demographic_overindex_with_ci.parquet` (column `significant = false`) but excluded from the headline.
- **Audit-trail manifest.** `MANIFEST.md` at project root carries SHA256 hashes of the three input CSVs, schemas + row counts of every output `.parquet`, dimensions of every output figure, and observed runtime. A reviewer can verify input integrity via `shasum -a 256 data/raw/*.csv`.

## Limitations

- **Consenting subsample, not Amazon's customer base.** All concentration numbers should be read as "within this 2,846-household panel," never "across Amazon's customers." Selection bias is plausible — people who consent to share purchase data may differ from those who don't.
- **Cohort cap at 2023-01-01.** Post-2023 data is sparse (22,569 of 1,048,575 rows, ~2.2%) due to participant attrition. Including post-2023 data would right-censor users who simply stopped reporting purchases. **One household excluded:** `R_1d1fnT4sjZABBwe`, single $1.84 order on 2024-08-15 — clearly a late panel joiner with no 2018–2022 activity.
- **Demographics are a 2021 snapshot.** Income, state, household size are recorded once at survey time. They are not a time series; a household whose income changed between 2018 and 2024 will be misclassified along that dimension.
- **State columns differ between datasets.** `Q-demos-state` (survey) uses full state names ("California"); `Shipping Address State` (purchases) uses 2-letter codes ("CA"). Layer 1 uses only the survey-side state.

---

## Repository structure

```
amazon-revenue-analytics/
├── README.md                              ← you are here
├── MANIFEST.md                            ← input hashes, output schemas, runtime
├── requirements.txt
├── data/raw/                              ← source CSVs (gitignored)
│   ├── amazon-purchases.csv               ← 1,048,575 transactions, 173 MB
│   ├── survey.csv                         ← 5,027 respondents × 23 demographics
│   └── fields.csv                         ← survey column dictionary
├── sql/                                   ← canonical SQL aggregations (first-class)
│   ├── 01_user_gmv_capped.sql             ← user-level GMV with STRPTIME cohort cap
│   ├── 02_decile_assignment.sql           ← NTILE(10) window function
│   ├── 03_decile_contribution.sql         ← decile × GMV percent rollup
│   └── 04_demographic_join.sql            ← decile-tagged table ⨝ survey demographics
├── src/                                   ← reusable Python helpers
│   ├── data_loader.py                     ← Polars / DuckDB loaders + date probe
│   ├── stats_utils.py                     ← Gini, Lorenz points, bootstrap over-index CI
│   ├── viz_utils.py                       ← finance-clean matplotlib styling
│   └── manifest_utils.py                  ← SHA256 + MANIFEST writer
├── notebooks/
│   └── 01_layer1_concentration.ipynb      ← Layer 1 main analysis
└── outputs/
    ├── tables/                            ← 5 parquet tables (gitignored — regenerable)
    └── figures/                           ← 3 PNG figures @ 300 dpi (committed)
```

## Tech stack

- **SQL:** DuckDB (in-process, reads CSV / Parquet directly — no separate database)
- **Python:** Polars (1M-row aggregation), Pandas (survey-side joins), NumPy (bootstrap)
- **Stats:** NumPy (Lorenz, Gini, bootstrap CIs — non-parametric throughout)
- **Viz:** matplotlib + seaborn (finance-clean styling, locked palette in `src/viz_utils.py`)
- **Notebooks:** Jupyter (deliverable format)

Why parquet and not CSV for outputs: columnar, 5–10× smaller, no float-precision loss, standard in BI workflows.

## How to Run

```bash
git clone <repo>
cd amazon-revenue-analytics
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Place amazon-purchases.csv, survey.csv, fields.csv in data/raw/
# Verify hashes against MANIFEST.md if reproducing exact numbers.
jupyter notebook notebooks/01_layer1_concentration.ipynb
```

Observed runtime on Layer 1 notebook: **~5 seconds** on M-series Mac (the bootstrap step alone — 41,000 vectorised NumPy resamples — completes in 0.46 sec).

## Analytical Layers

| Layer | Question | Status | Notebook |
|---|---|---|---|
| 1 | Where is revenue concentrated? | ✅ Done | `notebooks/01_layer1_concentration.ipynb` |
| 2 | What revenue is at risk next quarter? | ⏳ Planned | `notebooks/02_layer2_rar.ipynb` |
| 3 | Which categories to invest in? | ⏳ Planned | `notebooks/03_layer3_allocation.ipynb` |

Layer 2 will produce a walk-forward-validated revenue-at-risk model (as-of 2022-06-30 → predict 2022-Q3) with bootstrap CIs on per-segment risk. Layer 3 will use an LLM-assisted rollup of the 1,816 raw categories to ~15 super-categories, then plot growth × scale to surface allocation candidates.

## About

Built by **Leo Wan**, BUAI (Business of Artificial Intelligence) program — USC Marshall School of Business & Viterbi School of Engineering. Targeting Summer 2027 BI/DA Analyst internships.
