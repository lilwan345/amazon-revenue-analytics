# Amazon Revenue Analytics
*Concentration, Forward-Looking Revenue-at-Risk, and Growth Allocation*

**A BI framework for finance decision support, built on 2,846 U.S. Amazon households (2018–2022).**

[![Lorenz curve preview](outputs/figures/layer1/lorenz_curve.png)](outputs/figures/layer1/lorenz_curve.png)

---

## Contents

- [The Question](#the-question)
- [The Answer](#the-answer)
- [The Method](#the-method)
- [The Caveat](#the-caveat)
- [Methodology Notes](#methodology-notes)
- [Layer 3 — Category Allocation Matrix](#layer-3--category-allocation-matrix-deep-dive)
- [Limitations](#limitations)
- [Repository Structure](#repository-structure)
- [Tech Stack](#tech-stack)
- [How to Run](#how-to-run)
- [Analytical Layers](#analytical-layers)
- [About](#about)

---

## The Question

The Amazon Retail Finance team needs to understand three things to inform next-quarter resource allocation:

1. Where is revenue concentrated, and is concentration growing?
2. Which customer segments represent the largest forward-looking revenue-at-risk in the next quarter?
3. Which categories deserve priority investment given current growth × scale dynamics?

This project answers each question with a dedicated analytical layer.

## The Answer

**Layer 1 — concentration.** Within this 2,846-household consenting panel, **the top decile drives 36.2% of GMV** (top 20%: 55.2%; Gini = 0.529). Decomposition reveals the gap is **~94% purchase-frequency, only ~6% basket size** — top-decile households order 11.0× more often (1,222 vs 111 orders) but spend just 1.18× more per order. The strongest demographic signal is heavy cadence — households shopping more than 10 times per month over-index **+387% [CI: +324%, +457%]**, dwarfing $150K+ income (+154%). Concentration actually *fell* during COVID (Δ Gini = -0.039) while panel GMV nearly doubled — mass-market expansion, not VIP-only concentration. The data suggests engagement-cadence levers would address this driver more directly than premium-tier upsell — premium strategies would close only ~6% of the per-household gap.

**Layer 2 — revenue concentration is at the top, but revenue-at-risk is in the middle.** Top decile drives 36.2% of GMV but only **0.5% of forward-looking RaR** ($143 of $29,148 panel total). Bottom decile contributes 0.5% of GMV but carries **10.4% of RaR** ($3,021) — a **21x asymmetry** between best-and-worst-case forward stability. Mid-deciles (6-9) carry **65% of RaR while accounting for only 13% of GMV** (5x amplification). The data suggests a reallocation of retention budget from VIP defense to mid-tier engagement.

[![Decile RaR ladder preview](outputs/figures/layer2/decile_rar_ladder.png)](outputs/figures/layer2/decile_rar_ladder.png)

**Layer 3 — naive Scale × Growth lies; the Layer 1+2 cross-layer lens reframes allocation.** Twelve super-categories rolled up from 1,816 raw Amazon browse-node labels (Claude Opus 4.7 taxonomy, 89% specific-mapped, audit JSON committed). A naive Scale × Growth quadrant would label Pet/Health "INVEST" and Books "MAINTAIN" — both are operationally misleading once the cross-layer crosswalk is applied: **Pet is VIP retention** (D1 share = 40% of Pet GMV, lowest mid-decile share at 9.6%, lowest acquisition-gateway lift at 0.51), not RaR mitigation. **Books is broad-base retention infrastructure** (D1 share = 27%, lowest of any super-category; 88% panel breadth; mid-decile GMV share = 19%) — harvesting would worsen Layer 2's mid-decile RaR concentration. **The acquisition surface is broad-utility commodity categories** (Electronics 0.87 / Apparel 0.85 / Home 0.84 / H&PC 0.83), not specialty verticals. The data suggests segmenting allocation into three lanes (top-decile retention, mid-decile RaR mitigation, customer acquisition) rather than one growth bet per category.

[![Category allocation matrix preview](outputs/figures/layer3/category_allocation_matrix.png)](outputs/figures/layer3/category_allocation_matrix.png)

## The Method

SQL-first analysis (DuckDB) on ~1.05M Amazon transactions, cohort-capped at 2023-01-01 due to post-2023 participant attrition. **Layer 1:** NTILE(10) decile assignment; Lorenz + Gini for concentration shape; log-decomposition for the frequency-vs-basket driver split; bootstrap 95% CIs (B=1000, seed=42) on demographic over-index ratios. **Layer 2:** walk-forward validated logistic regression (features as-of 2022-06-30, validated against 2022-Q3 actuals); SQL-level leakage guard + shuffle-label diagnostic (median AUC 0.54 on shuffled labels, max 0.57 — below the 0.60 leakage-suspicion threshold); bootstrap CIs on AUC, coefficients, and segment-level RaR; calibration verified via reliability diagram across 10 quantile bins. **Layer 3:** Claude Opus 4.7 generates a deterministic 1,816→12 super-category taxonomy (audit JSON committed, 89% specific-mapped + 50-row spot-check); 4-year CAGR (`(2022/2018)^(1/4) − 1`) over raw growth-rate to avoid COVID-baseline distortion; bootstrap CIs on every metric; cross-layer crosswalk joins Layer 1 decile structure + Layer 2 RaR per household into the allocation matrix. Every core aggregation is cross-validated against a Polars equivalent for byte equality.

## The Caveat

The 2,846 households are a **consenting subsample** of 5,027 Prolific prescreen respondents — not a random sample of Amazon's broader customer base. The panel's 87% Q3 activity rate is a **selection-bias upper bound** on engagement; Layer 2 RaR magnitudes should be read as upper bounds, with the analytical framework (propensity model + segment-level aggregation + bootstrap CIs) generalizing but absolute dollars requiring re-validation on production cohorts before downstream use. Demographics are a 2021 snapshot, not a time series.

---

## Methodology Notes

**Layer 1 (concentration analysis):**

- **`Order Date` raw format is `M/D/YY`.** Implicit `CAST("Order Date" AS DATE)` parses only **28.6%** of these strings; the other 71% silently NULL. All SQL in `sql/` uses explicit `STRPTIME("Order Date", '%-m/%-d/%y')`. Using CAST would have understated Layer 1 GMV by ~70%.
- **Cross-validation discipline.** Every core aggregation in Layers 1–2 has a SQL implementation (under `sql/`, the artifact a recruiter screenshots) and a Polars implementation (the dataframe code in the notebook). The two are asserted byte-equal (or float-equal within FP tolerance) before any parquet is saved. Divergence would surface silent aggregation bugs — the most notable catch in this project was a `n_distinct_categories_trailing_12m` mismatch where Polars's `n_unique()` counted NULL as a distinct value while SQL's `COUNT(DISTINCT)` does not (1,684-household discrepancy on the same feature).
- **Confidence intervals on all reported ratios.** No headline number is reported as a point estimate alone. Bootstrap is non-parametric (B=1000, seed=42), so it makes no normality assumption — appropriate for the heavy-tailed GMV distribution. Findings whose 95% CIs cross zero are recorded but excluded from the headline.
- **Audit-trail manifest.** `MANIFEST.md` at project root carries SHA256 hashes of the three input CSVs, schemas + row counts of every output `.parquet`, dimensions of every output figure, and observed runtime. A reviewer can verify input integrity via `shasum -a 256 data/raw/*.csv`.

**Layer 2 (forward-looking RaR):**

- **Outlier treatment evolution (R13 bilateral revision).** Numeric features are winsorized at the 1st and 99th percentiles (bilateral) before z-score standardization. The original Layer 2 plan called for single-tail (99th-percentile only); symmetric-tail features (`aov_slope`, `gmv_trend`) in the 8-feature mix would have produced max |z| = 21.6 on the negative `aov_slope` tail under the single-tail form. A safety-threshold assertion caught this mid-Task-7.3, and the bilateral extension preserves the original intent while accommodating the actual feature distribution. The winsorize-then-z-score order is locked — applying z-score first would leave heavy-tail leverage in the fit; winsorize first removes extreme rows before standardization measures dispersion.
- **Feature leakage defense (SQL guard + empirical validation).** `sql/05_household_features.sql` wraps every feature aggregation in an outer-CTE filter on `Order Date < 2022-07-01`, blocking post-cutoff data at the SQL level. A shuffle-label diagnostic then permuted `is_dropoff_q3` 50 times and refit the full pipeline: median shuffled AUC was 0.54, max 0.57 — well below the 0.60 leakage-suspicion threshold and near the 0.50 random baseline. The real-label AUC of 0.9052 reflects genuine signal from pre-cutoff features, not accidentally leaked information from post-cutoff data. The SQL guard is the structural defense; the shuffle-label diagnostic is the empirical validation that the guard worked.
- **Calibration & STOP rule revision.** Logistic regression calibration was evaluated across 10 probability quantile bins (~284 households per bin). Nine bins fell within ±0.05 of perfect; bin 9 (predicted ≈ 28%, 284 households) showed actual drop-off of 37% — a 9.3pp underestimate. RaR estimates concentrated in this probability range carry a known ~25% systematic downward bias and are reported as lower bounds. Brier-score information gain over baseline is 32% (model 0.0755 vs no-skill 0.1108), above the locked 10% threshold. The STOP rule was revised mid-Layer-2 from binary halt to flag-and-disclose: isotonic recalibration would have closed the bin-9 gap but obscured a signal finance reviewers should see.
- **Sanity band & three RaR metrics.** Original sanity band implied panel-total RaR in $150K-$500K under an independence assumption (`panel_size × mean(prob_dropoff) × mean(expected_q3_gmv)`). Actual is $29,148 — 15% of baseline. A correlation diagnostic surfaced strong negative correlation between drop-off probability and expected revenue (r = -0.46): high-spenders are stable; low-spenders carry drop-off mass at tiny dollar exposure. The revised band ($25K-$100K) is consistent with observed behavior and produces Layer 2's headline narrative. Three RaR metrics are computed per segment: **panel-share** (fraction of total panel RaR — drives budget allocation, used in headline), **internal fragility** (fraction of segment's own expected revenue — appendix context), and **per-household mean** (average dollar exposure — dominated by the same negative-correlation effect).
- **Recency cap interpretability trade-off.** `recency_days` is capped at 365 — every ≥365-day customer maps to the same z-score, preserving a human-readable feature scale for stakeholder review. The trade-off: recency lost fine-grained discrimination at the long tail, dropping from anticipated strongest predictor to 3rd position in the standardized coefficient ranking (|β| = 0.54 vs 1.79 for category breadth and 1.64 for trailing-12m GMV). We accept this trade-off as alignment with stakeholder need for human-readable feature scales over predictive maximization.
- **Coefficient ≠ AUC contribution under multi-collinearity.** Coefficient magnitude does not equal AUC contribution under multi-collinearity. `n_distinct_categories_trailing_12m` carries the largest standardized coefficient (|β| = 1.79) but per-feature ablation shows `recency_days` is the sole non-redundant AUC contributor — removing it drops AUC by 0.0113 while removing any other single feature drops AUC by less than 0.002. The two metrics measure different things: coefficient reflects in-model signal weight under ridge regularization; ablation reflects out-of-model substitutability. Both rankings are reported honestly — coefficient drives the category-breadth surprising finding; ablation grounds the predictive-importance defense.

**Layer 3 (growth allocation matrix):**

- **LLM-generated taxonomy with audit JSON.** Used Claude Opus 4.7 to roll up 1,816 raw browse-node leaves into 12 super-categories via priority-ordered keyword matching + explicit category-name lookups. Mapping committed at `outputs/tables/category_taxonomy.json` (and flattened CSV at `outputs/tables/category_taxonomy_mapping.csv` for SQL JOINs). Coverage: 89.0% of GMV mapped to a specific super-category, 5.4% in an explicit NULL bucket (raw `Category` field is NULL in 50,694 transactions — observable missing data, not silently dropped), 5.7% in `Other / Unknown` (specialized long-tail leaves like `HEAT_PRESS`, `BUILDING_HARDWARE` that don't cleanly map). A 50-row random spot-check audit caught 3 false positives (`ABIS_DRUGSTORE` → Books, `TREE_SKIRT` → Apparel, `TEAPOT` → Grocery) that were patched before commit; the audit pattern is reproducible by re-running the spot-check on the committed JSON.
- **4-year CAGR over 2-year growth rate.** Growth metric is `(2022 GMV / 2018 GMV)^(1/4) − 1`, not `(2022 − 2020) / 2020`. Rationale: 2020 was already COVID-lifted in this panel (panel GMV jumped $3.6M → $5.3M from 2019 → 2020). Using 2020 as denominator suppresses growth signal for categories that surged early in COVID. The full 4-year window captures secular trend; the 2-year baseline is reported as `growth_2020` in the parquet for sensitivity but is not the headline.
- **Bootstrap CIs on every metric — same n=2,846 panel logic as Layers 1/2.** Scale, CAGR, per-household scale, gateway lift — each carries bootstrap household-resample 95% CIs (B=1000, seed=42). Categories with small `n_households_buying` (Pet 1,350; Gift Cards 1,200) get wider CIs honestly.
- **Cross-layer crosswalk is the Layer 3 differentiator.** Without joining Layer 1 deciles + Layer 2 per-household RaR back into the category aggregates, Layer 3 would be a generic Scale × Growth matrix — the same one any retail-strategy textbook generates. The crosswalk is what surfaces the "Pet is VIP retention, not RaR mitigation" and "Books is broad-base retention infrastructure" findings; both are direct consequences of folding the prior layers in.
- **Cohort gateway interpretation: ranking matters, absolute lift doesn't.** All super-categories show lift < 1.0 (new-cohort penetration is below established-cohort penetration for every category), because new cohort (n=196, post-2020 joiners) has had less time to explore Amazon's category surface than established cohort (n=2,649). The relative ranking — Electronics/Apparel/Home/H&PC tier at 0.83-0.87 vs Pet/Gift Cards at 0.51-0.58 — is what defines "acquisition gateway" vs "loyalty surface". Absolute lift of any single category is not the headline number.
- **Sub-category granularity is out of scope.** The 12 super-categories collapse meaningful within-category variance — Health & Personal Care lumps medication (FDA-regulated, repeat-buy) with cosmetics (impulse, brand-driven). Sub-category Scale × Growth analysis is the natural next step; in this panel it would require either domain-knowledge rollup of the ~700 still-mappable health leaves or a second-pass Claude taxonomy. Out of scope here; flagged for downstream work.

## Layer 3 — Category Allocation Matrix (Deep Dive)

### The question

> *Which categories deserve priority investment given current growth × scale dynamics?*

### Taxonomy — 1,816 raw browse-node leaves → 11 super-categories

Used Claude Opus 4.7 to roll up 1,816 raw Amazon browse-node leaf categories into **11 specific super-categories** plus 1 explicit `Other / Unknown` bucket (89.0% of cohort-capped GMV maps to a specific super-category; 5.4% NULL bucket; 5.7% long-tail). Deterministic mapping committed at `outputs/tables/category_taxonomy.json`; a 50-row spot-check audit caught and patched 3 false positives before commit. Full coverage table + audit trail in Methodology Notes (Layer 3 — *LLM-generated taxonomy with audit JSON*).

### Scale × Growth dimensions

- **Scale** = 2022 GMV per super-category (current footprint within this panel).
- **Growth** = 4-year CAGR, `(2022 GMV / 2018 GMV)^(1/4) − 1`. The 4-year window normalizes through COVID distortion (2020 is already COVID-lifted in this panel); see Methodology Notes for the rationale vs a 2-year YoY baseline.
- **Panel median scale**: **$369K** (Toys); **panel median CAGR**: **24.8%** (Apparel). These define the quadrant split below.

Each metric carries a bootstrap 95% CI (B=1000, seed=42, household-resample) — smaller buying populations (Pet ≈ 1,350 households; Gift Cards ≈ 1,200) report wider CIs.

### Category growth ranking

[![Category growth ranking](outputs/figures/layer3/category_ranking_table.png)](outputs/figures/layer3/category_ranking_table.png)

Ranked by 4-year CAGR: Grocery & Food & Beverage leads at **34.3%**, followed by Pet (27.2%) and Home, Kitchen & Bath (26.3%); the floor is Books & Media (**1.5%**), Gift Cards & Digital (9.3%), and Electronics & Accessories (14.7%). The full 11-category ranking with bootstrap 95% CIs is in the figure above; each category's scale and CAGR are tabled in the quadrant readout below.

### BCG-style quadrant readout

[![Category allocation matrix](outputs/figures/layer3/category_allocation_matrix.png)](outputs/figures/layer3/category_allocation_matrix.png)

Splitting the 11 super-categories along the median scale ($369K) and median CAGR (24.8%) lines:

| Quadrant | n | Super-categories (scale, CAGR) |
|---|---|---|
| **INVEST** — high growth × high scale | 3 | Grocery ($507K, 34.3%) · Home, Kitchen & Bath ($1,101K, 26.3%) · Health, Beauty & Personal Care ($777K, 25.0%) |
| **BET-small** — high growth × low scale | 2 | Pet ($291K, 27.2%) · Auto, Tools & Outdoor ($251K, 26.2%) |
| **MAINTAIN** — low growth × high scale | 1 | Electronics & Accessories ($970K, 14.7%) |
| **HARVEST** — low growth × low scale | 3 | Office, Stationery & Crafts ($154K, 23.4%) · Gift Cards & Digital ($250K, 9.3%) · Books & Media ($191K, 1.5%) |
| At median boundary | 2 | Apparel & Footwear ($763K, 24.8% — at median CAGR) · Toys, Games & Hobbies ($369K, 21.4% — at median scale) |

### The differentiator — high growth ≠ acquisition gateway

A naïve BCG read would say "invest in INVEST, harvest HARVEST." Layer 3 layers a second lens on top: **cohort-based acquisition gateway lift** (new cohort = 196 households joining ≥ 2020-01-01; established cohort = 2,649). Lift ratio = new-cohort category penetration / established-cohort penetration. Every value is < 1.0 in this panel — new cohort has had less time to expand category exploration — so the **relative ranking is the signal**, not the absolute level.

[![Category adoption speed](outputs/figures/layer3/category_gateway_lift.png)](outputs/figures/layer3/category_gateway_lift.png)

| Tier | Lift range | Categories |
|---|---|---|
| Fast-adoption (top 4 by rank) | 0.83–0.87 | Electronics (0.87) · Apparel (0.85) · Home, Kitchen & Bath (0.84) · Health, Beauty & Personal Care (0.83) |
| Neutral mid-tier (rank 5–8) | 0.63–0.73 | Toys (0.73) · Grocery (0.70) · Office (0.64) · Books (0.63) |
| Loyalty / repeat-purchase (bottom 3) | 0.51–0.61 | Auto (0.61) · Gift Cards (0.58) · Pet (0.51) |

**Cross-tabbing the BCG quadrant and the adoption-speed tier produces the operational allocation insight:**

- **Double signal — INVEST × fast-adoption.** Home, Kitchen & Bath (26.3% CAGR, 0.84 lift) and Health, Beauty & Personal Care (25.0%, 0.83): high growth that is structurally durable because new customers enter via these categories, not just existing ones spending more. The cleanest INVEST candidates.
- **Loyalty-depth growth — INVEST/BET × low gateway.** Grocery (34.3%, 0.70), Pet (27.2%, 0.51), Auto (26.2%, 0.61): strong secular growth but weak new-cohort penetration. The data suggests existing-customer deepening, not new-household acquisition — retention budget framing, not acquisition.
- **Stalled acquisition surface — MAINTAIN × fast-adoption.** Electronics (0.87 lift, highest of any super-category; 14.7% CAGR, below the 24.8% median): a traditional first-purchase category whose growth has plateaued — defensive margin maintenance, not growth bet.
- **Pure defensive — HARVEST × neutral/low gateway.** Books (1.5% CAGR, 0.63 lift), Gift Cards (9.3%, 0.58), Office (23.4%, 0.64). Books is the cleanest structural-decline read — low growth, low scale, neither acquisition surface nor loyalty anchor.

### Layer 1+2 cross-layer crosswalk

The cross-layer crosswalk (per-super-category D1 GMV share, mid-decile RaR share, household breadth) is what makes the matrix actionable rather than a generic Scale × Growth read. Specifically:

- **Pet** has the highest D1 GMV concentration (39.9% from top decile) and lowest mid-decile RaR exposure (9.6%). With its 0.51 gateway lift, the data suggests Pet is a VIP-anchored loyalty category — not a RaR-mitigation target, despite landing in BET-small on Scale × Growth alone.
- **Books** has the lowest D1 GMV concentration (26.8%) and broadest panel reach (87.7% of households). It's the closest super-category to a broad-base retention anchor — so the naïve "HARVEST Books" read would hit mid-decile households Layer 2 flagged as carrying 65% of panel RaR.

Full cross-layer crosswalk parquet + audit trail in Methodology Notes (Layer 3). Layer 3-specific limitations (sub-category granularity, gateway lift < 1.0 by construction, no cost-side data) fold into the main Limitations + Methodology Notes below.

---

## Limitations

- **Consenting subsample, not Amazon's customer base.** All concentration and RaR numbers should be read as "within this 2,846-household panel," never "across Amazon's customers." Selection bias is plausible — people who consent to share purchase data may differ from those who don't. The panel's 87% Q3 activity rate is direct evidence of this selection-bias direction: the panel is more engaged than the broader Amazon population.
- **Single-quarter outcome window.** Layer 2's `is_dropoff_q3` measures absence of any purchase in 2022-Q3. This is *not* permanent churn — Task 7.2 diagnostics surfaced that ~30% of households silent for the trailing 12 months reactivate within the next quarter. The terminology used throughout Layer 2 is "Q3 drop-off" or "Q3 inactivity," never "churn," to preserve this distinction.
- **Cohort cap at 2023-01-01.** Post-2023 data is sparse (22,569 of 1,048,575 rows, ~2.2%) due to participant attrition. Including post-2023 data would right-censor users who simply stopped reporting purchases. **One household excluded:** `R_1d1fnT4sjZABBwe`, single $1.84 order on 2024-08-15 — clearly a late panel joiner with no 2018–2022 activity.
- **Demographics are a 2021 snapshot.** Income, state, household size are recorded once at survey time. They are not a time series; a household whose income changed between 2018 and 2024 will be misclassified along that dimension.

---

## Repository structure

```
amazon-revenue-analytics/
├── README.md                              ← you are here
├── MANIFEST.md                            ← input hashes, output schemas, runtime
├── LICENSE                                ← MIT
├── requirements.txt
├── data/raw/                              ← source CSVs (gitignored)
│   ├── amazon-purchases.csv               ← 1,048,575 transactions, 173 MB
│   ├── survey.csv                         ← 5,027 respondents × 23 demographics
│   └── fields.csv                         ← survey column dictionary
├── sql/                                   ← canonical SQL aggregations (first-class)
│   ├── 01_user_gmv_capped.sql             ← Layer 1: user-level GMV, STRPTIME cohort cap
│   ├── 02_decile_assignment.sql           ← Layer 1: NTILE(10) window function
│   ├── 03_decile_contribution.sql         ← Layer 1: decile × GMV percent rollup
│   ├── 04_demographic_join.sql            ← Layer 1: decile-tagged table ⨝ survey demographics
│   ├── 05_household_features.sql          ← Layer 2: 8 features + R12 walk-forward leakage guard
│   ├── 06_q3_outcome.sql                  ← Layer 2: `is_dropoff_q3` outcome variable
│   └── 07_category_rollup.sql             ← Layer 3: super-category × year rollup (joins taxonomy JSON)
├── src/                                   ← reusable Python helpers
│   ├── data_loader.py                     ← Polars / DuckDB loaders + date probe
│   ├── stats_utils.py                     ← Gini, Lorenz points, bootstrap over-index CI
│   ├── viz_utils.py                       ← finance-clean matplotlib styling
│   └── manifest_utils.py                  ← SHA256 + MANIFEST writer
├── notebooks/
│   ├── 01_layer1_concentration.ipynb      ← Layer 1 main analysis
│   ├── 02_layer2_rar.ipynb                ← Layer 2 main analysis (forward-looking RaR)
│   └── 03_layer3_allocation.ipynb         ← Layer 3 main analysis (growth allocation matrix)
└── outputs/
    ├── tables/                            ← 10 parquet tables (gitignored — regenerable)
    └── figures/                           ← 10 PNG figures @ 300 dpi (committed), organized by layer
        ├── layer1/                         ← lorenz_curve, decile_contribution_bar, concentration_over_time
        ├── layer2/                         ← decile_rar_ladder (hero), coefficient_chart, calibration_curve, roc_curve
        └── layer3/                         ← category_allocation_matrix (hero), category_ranking_table, category_gateway_lift
```

## Tech stack

- **SQL:** DuckDB (in-process, reads CSV / Parquet directly — no separate database)
- **Python:** Polars (1M-row aggregation), Pandas (survey-side joins), NumPy (bootstrap)
- **Stats / ML:** NumPy (Lorenz, Gini, bootstrap CIs); scikit-learn (logistic regression, ROC, calibration)
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
jupyter notebook notebooks/01_layer1_concentration.ipynb   # then 02_layer2_rar.ipynb
```

Observed runtime: **~5 sec** for Layer 1, **~7 sec** for Layer 2 (both on M-series Mac). Layer 2's full bootstrap pipeline — 1,000 LR re-fits for AUC + coefficient CIs, 50 shuffle-label refits, 51,000 segment-RaR resamples — completes in ~3 sec combined via vectorised NumPy.

## Analytical Layers

| Layer | Question | Status | Notebook |
|---|---|---|---|
| 1 | Where is revenue concentrated? | ✅ Done | `notebooks/01_layer1_concentration.ipynb` |
| 2 | What revenue is at risk next quarter? | ✅ Done | `notebooks/02_layer2_rar.ipynb` |
| 3 | Which categories to invest in? | ✅ Done | `notebooks/03_layer3_allocation.ipynb` |

## About

Built by **Leo Wan**, BUAI (Business of Artificial Intelligence) program — USC Marshall School of Business & Viterbi School of Engineering. Targeting Summer 2027 BI/DA Analyst internships.
