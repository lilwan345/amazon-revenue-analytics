# Methodology Notes

*Companion to the [main README](README.md). How each layer was built, and the honest caveats behind the headline numbers. Written to be readable, not exhaustive.*

---

## Layer 0: data provenance

- **The raw file is checked before any analysis runs.** `src/validate_data.py` confirms the raw `amazon-purchases.csv` matches the published Open e-commerce 1.0 source (Berke et al., *Scientific Data* 2024; Harvard Dataverse `doi:10.7910/DVN/YGLYDY`): 5,027 households, >1.8M transactions. It specifically flags the **1,048,575-row signature**, the exact point where Excel / Google Sheets / Numbers silently cut a CSV when you save it. An earlier copy of this file had been through a spreadsheet and was truncated to that many rows (only 2,846 of 5,027 households), with the dates reformatted along the way. I re-downloaded the full file from Dataverse and the check now passes (1,850,717 rows, 5,027 households). The lesson is the point: check where a number came from before trusting it.

## Layer 1: concentration

- **Two engines, cross-checked.** Each core total is computed in SQL (DuckDB, in `sql/`) and again in Polars (in the notebook), and the two are compared before anything is saved. If they disagree, something is wrong, so it doubles as a sanity check.
- **Bootstrap confidence intervals on the headline numbers.** The main ratios (e.g. the top-decile share) carry a bootstrap 95% CI (1,000 resamples, fixed seed) rather than a bare point estimate. Bootstrap is used because it assumes nothing about the shape of the data (which matters here, since spending is heavily skewed), and because the panel is a sample (n = 5,026), not all of Amazon.
- **Frequency vs. basket.** The top decile's GMV lead splits into "how often they buy" and "how much per order." Here it is ~95% the first and ~5% the second, so the top decile is defined by buying *more often*, not by bigger baskets.
- **Deciles are cut on pre-Q3 spend.** Households are ranked into deciles using only their spend through 2022-06-30, the same cut-off the Layer 2 risk model uses. This matters: if deciles were cut on full-period spend, Q3 2022 (the thing Layer 2 is trying to predict) would help decide which decile a household lands in, which would bias the Layer 2 result. Cutting deciles before Q3 keeps the two layers honest.

## Layer 2: revenue-at-risk

- **What it is.** A logistic-regression model scores each household's chance of going inactive in Q3 2022 from its behaviour through mid-2022 (recency, frequency, category breadth, spend trend). Revenue-at-risk for a household = that chance × its expected Q3 spend; summed by segment, it shows where next-quarter exposure sits.
- **Why it's a real test, not hindsight.** The model is trained only on data through 2022-06-30 and then scored against what actually happened in Q3, a walk-forward backtest. Because the inputs can't see past the cut-off, the model isn't "peeking" at the answer, so its ranking accuracy (it sorts at-risk vs. safe households well, AUC ≈ 0.90) is real signal rather than leakage.
- **"Q3 drop-off," not "churn."** The outcome is simply "no purchase in 2022-Q3." It is *not* permanent churn. A quick check found ~28% of households silent for a full year buy again within a quarter, so the wording stays "drop-off" throughout to keep that honest.
- **Logistic regression on purpose.** A simple, interpretable model is the right tool here: finance stakeholders need to see *why* a household is flagged, which a black-box model wouldn't show, and the accuracy given up versus a fancier model is tiny.

## Layer 3: growth allocation

- **The category grouping.** Claude (Opus 4.7) rolled up the 1,871 raw Amazon category labels into 11 super-categories plus an explicit `Other / Unknown` bucket, using a keyword dictionary committed at `outputs/tables/category_taxonomy.json` (so the grouping is fixed and reproducible, not re-guessed each run). Coverage: ~89% of GMV maps to a named category, ~5% has a missing raw label (kept visible, not dropped), ~6% is long-tail leftovers. A 50-row spot-check caught and fixed 3 mis-labels before committing. Read the per-category numbers as ±2–3 points, not exact.
- **4-year growth, not 2-year.** Growth is the 4-year CAGR, `(2022 / 2018)^(1/4) − 1`, rather than a 2-year rate. 2020 was already COVID-lifted in this panel, so using 2020 as the baseline would understate growth for categories that surged early in COVID. The 4-year window smooths that out. Each category's scale and growth also carries a bootstrap 95% CI, wider for small-buyer-pool categories like Pet, so those are read as directional.
- **The cross-layer join is the point.** Folding Layer 1 (which decile a category's GMV comes from) and Layer 2 (its households' risk) back into the category view is what turns a generic Scale × Growth chart into something useful:
  - **Pet** is concentrated in top-decile households (≈39% of Pet GMV) and new customers adopt it slowly, so it reads as loyalty among existing heavy buyers, not a place to chase new customers. *(Caveat: a heavy top-decile share could also just mean a small, niche buyer pool; telling loyalty and niche-ness apart would need repeat-purchase detail I didn't compute, so treat this as directional.)*
  - **Books** has the broadest reach (≈88% of households) and the *least* top-decile concentration, closer to broad retention than a "harvest and forget" category. Cutting it would hit the mid-tier households Layer 2 flagged as most at-risk.
- **New-customer adoption: ranking, not level.** Every category's "new-customer adoption" score is below 1.0, simply because households that joined after 2020 have had less time to branch out than long-time ones. So the useful signal is the *ranking* (Electronics / Apparel / Home / Health adopt fastest, Pet / Gift Cards slowest), not the absolute number.
- **What's out of scope.** The 11 groups are coarse (Health & Personal Care lumps medication in with cosmetics, which behave differently), and there's no cost or margin data, so this is a revenue-side view only. Finer sub-categories are the natural next step but aren't done here.
