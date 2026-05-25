# Amazon Revenue Analytics — Interview-Grade Review

> **Handoff context for the next Claude Code session.** This is a critical review of Leo Wan's portfolio repo, conducted from the perspective of a Google Finance DnA hiring manager / senior BI interviewer. Use this document as input when continuing the polish work in another session.

---

## What was reviewed

- **Repo:** https://github.com/lilwan34345/amazon-revenue-analytics (public, MIT)
- **Owner:** Leo Wan (USC BUAI, targeting Summer 2027 BI intern roles at Google Finance DnA)
- **Reviewed commit:** latest `main` as of 2026-05-25
- **Local clone used for review:** `/tmp/amazon-revenue-analytics/` (ephemeral — re-clone if needed)
- **Scope:** Layer 1 (concentration), Layer 2 (RaR), Layer 3 (allocation) — all 3 notebooks, 7 SQL files, `src/`, README, METHODOLOGY, MANIFEST, tableau extracts
- **Sample:** 2,846 U.S. Amazon households, 2018–2022, sourced from a Prolific consumer panel

## How the review was conducted

Four parallel review agents, each with an independent lens:
1. **README / narrative** — front-door first-impression, voice discipline (descriptive vs prescriptive, BI-finance vocab vs ML/DS leak)
2. **METHODOLOGY / data quality** — generalizability, selection bias, capping, decile honesty, RaR definition, survivorship, sub-cut sample sizes
3. **SQL / reproducibility** — correctness bugs, join logic, NTILE ties, runnability from a clean clone
4. **Notebooks / figures** — story arc, markdown:code ratio, chart honesty (axis truncation, missing baselines), voice violations in cells

Voice constraints used as fatal triggers (these are Leo's hard rules, not defaults):
- **Finance-BI vocabulary only** (no DS/ML framing)
- **Descriptive, never prescriptive** ("the data suggests" ✅; "Amazon should" / "we recommend" ❌)
- **English only** for GitHub-facing artifacts (README, MANIFEST, notebooks, sql/, src/)
- **Honest scope** — never generalize beyond "this panel of households" without explicit caveat
- **Data skepticism first** — flag data-quality risks at the start of every analysis
- **Surprising findings = BA insights only** (audit/engineering wins route to Methodology/Limitations, not headlines)

---

# 🔴 Fatal Issues (these must be fixed before sending to final rounds)

## F1 — Decile information leakage (largest risk in the entire portfolio)

**WHERE:** `sql/01_user_gmv_capped.sql:27` + `sql/02_decile_assignment.sql` + Layer 2 RaR ladder

**WHAT:** Layer 1 deciles are assigned over **full 2018–2022 GMV**. Layer 2 RaR uses features `< 2022-07-01` with outcome in **2022 Q3**. The RaR ladder (README headline: "top decile 0.5% RaR, bottom 10.4%, mid-deciles 65%") then groups Layer 2 RaR results by Layer 1 deciles — but a household's Layer 1 decile membership is partly determined by its own Q3 2022 spend.

**WHY FATAL:** Outcome-period spend is embedded in the segment definition. A household that dropped off in Q3 mechanically has lower total GMV → mechanically sorted into a lower decile → "risk concentrates in low/mid deciles" is guaranteed by construction. A senior Google reviewer's first probe: *"Deciles built over which window?"* That single question collapses the Layer 2 headline.

**FIX:**
1. Patch `sql/02_decile_assignment.sql` to cut deciles only on pre-feature-window GMV:
   ```sql
   WITH pre_cutoff_gmv AS (
       SELECT household_id, SUM(line_gmv) AS total_gmv
       FROM purchases_clean
       WHERE order_date < TIMESTAMP '2022-07-01'   -- same cutoff as Layer 2 features
       GROUP BY 1
   )
   SELECT
       household_id, total_gmv,
       NTILE(10) OVER (ORDER BY total_gmv DESC, household_id) AS decile
   FROM pre_cutoff_gmv;
   ```
2. Re-run the Layer 2 RaR ladder.
3. Add to README: *"Deciles assigned on pre-2022-Q3 GMV to prevent outcome-window leakage; original full-window decile ladder differs by Δ = X pp."*
4. If the finding weakens — **say so**. Epistemic honesty about a softer finding is worth more than pretending the original headline held.

---

## F2 — `01_user_gmv_capped.sql` does no GMV capping

**WHERE:** `sql/01_user_gmv_capped.sql` (whole file)

**WHAT:** Filename says `_capped`; the file only applies a 2023-01-01 **date filter**. No `LEAST(SUM, threshold)`, no p99 clip, no winsorization.

**WHY FATAL:** "Capped GMV" in finance/BI = winsorization (standard defense against heavy-tailed revenue distributions). A reviewer opening this file expects outlier handling and finds a date filter — two interpretations, both negative:
- Naming imprecision (basic-skills concern)
- Doesn't know that long-tailed concentration metrics require winsorization (worse)

The Prolific panel makes this worse: one anomalous $25K business order in 1.05M rows can swing the top-decile share by multiple points. Headline `36.2%` top-decile share and `Gini=0.529` currently sit unprotected.

**FIX (Path A — recommended):** Implement actual winsorization:
```sql
WITH user_gmv_raw AS (
    SELECT household_id, SUM(line_gmv) AS gmv_raw
    FROM purchases_clean
    WHERE order_date < TIMESTAMP '2023-01-01'
    GROUP BY 1
),
p99 AS (SELECT QUANTILE_CONT(gmv_raw, 0.99) AS cap FROM user_gmv_raw)
SELECT
    household_id,
    LEAST(gmv_raw, (SELECT cap FROM p99)) AS gmv_capped,
    gmv_raw
FROM user_gmv_raw;
```
Then add a sensitivity table to METHODOLOGY:

| Cap policy | Top-decile share | Gini |
|---|---|---|
| No cap | 36.2% | 0.529 |
| p99 winsorize | X% | Y |
| p99.5 winsorize | … | … |

**FIX (Path B — minimum):** Rename file to `01_user_gmv_cohort_dated.sql` and add to METHODOLOGY: *"No per-user GMV winsorization applied; headline concentration is sensitive to single-household outliers."*

Path A is worth significantly more than Path B (disclosure is fine; analyst skill is better).

---

## F3 — `sql/07_category_rollup.sql` replicates the silent-NULL date bug Leo warned about

**WHERE:** `sql/07_category_rollup.sql:21-26`

**WHAT:**
```sql
"Order Date"        AS order_date,
EXTRACT(YEAR FROM "Order Date") AS yr,
...
WHERE "Order Date" < DATE '2023-01-01'
```
Files 01 and 05 explicitly document that `"Order Date"` is M/D/YY VARCHAR, and that direct `CAST AS DATE` silently NULLs ~71% of rows. File 07 does both an implicit CAST inside `EXTRACT` and a string-vs-DATE inequality — the exact bug Leo's own comments warn against. This file feeds all of Layer 3 (CAGR, scale, allocation matrix).

**WHY FATAL:** Correctness bug, not style. If a reviewer diffs Layer 1 panel GMV vs Layer 3 aggregate totals, they won't reconcile.

**FIX:**
```sql
WITH purchases_capped AS (
    SELECT
        "Survey ResponseID" AS household_id,
        STRPTIME("Order Date", '%-m/%-d/%y') AS order_date,
        EXTRACT(YEAR FROM STRPTIME("Order Date", '%-m/%-d/%y')) AS yr,
        "Category" AS raw_category,
        "Purchase Price Per Unit" * "Quantity" AS line_gmv
    FROM purchases   -- ← use the registered view, NOT hardcoded read_csv_auto path
    WHERE STRPTIME("Order Date", '%-m/%-d/%y') < TIMESTAMP '2023-01-01'
)
```
After fix: cross-check Layer 1 total panel GMV against Layer 3 aggregate — they must match. If not, dig deeper.

---

## F4 — "Revenue at Risk" name doesn't match its definition

**WHERE:** `README.md:76`, `METHODOLOGY.md`, all of nb02, all Layer 2 chart titles

**WHAT:** Defined as `RaR = P(Q3 inactive) × E[Q3 GMV]`. In finance, "at risk" implies a **distributional tail** (VaR / CVaR / Expected Shortfall). What Leo built is **expected exposure** (P × E), not tail risk.

**WHY FATAL:** A Google Finance DnA reviewer's first question is *"Is this VaR, CVaR, ES, or expected loss?"* The honest answer is "none of those" — and expected loss is a legitimate metric, but it's being given the wrong name. In finance vocabulary, this is terminology malpractice.

**FIX:** Global rename. Suggested replacements (in order of "sounds like a real Google Finance internal term"):
1. **Expected Q3 Revenue Exposure (EQRE)** — most accurate
2. **Expected Loss from Q3 Inactivity (ELQI)** — also accurate
3. **Forward Revenue Exposure** — most BI-friendly

Add to METHODOLOGY: *"This is an expected-loss construction (P × E), not a VaR-tail metric. A true Q3 revenue VaR would require a forward GMV distribution per household, out of scope here."*

---

## F5 — Prescriptive language violates Leo's own voice rule (3 documented locations)

The hard rule: BI Analyst **describes**, never **prescribes**. Each violation below reads as "doesn't know the BI / strategy boundary":

| File | Original | Replacement |
|---|---|---|
| `README.md:57` | "The data suggests a **reallocation of retention budget** from VIP defense to mid-tier engagement." | "The data shows mid-tier RaR exposure is materially larger than top-tier on a panel-share basis." |
| `notebooks/02_layer2_rar.ipynb` cell 55 | "The asymmetry **justifies a reallocation** of retention budget..." | "The asymmetry is consistent with mid-decile exposure exceeding top-decile exposure; the reallocation decision sits with Finance." |
| `notebooks/03_layer3_allocation.ipynb` MD cell 19 | "For Finance: customer-acquisition budget **should follow** the broad-utility surface..." | "The data places the acquisition surface in broad-utility categories; how Finance maps that to budget is outside this analysis." |

**Ironic note:** nb03 cell 0 contains a vocabulary-discipline preamble that explicitly bans "we recommend / investment priority" — and cell 19 violates it. A reviewer who reads top-to-bottom will notice.

---

## F6 — Two charts have truncated axes that exaggerate findings

### F6a — `outputs/figures/layer3/category_gateway_lift.png` (nb03 cell 15)
```python
ax.set_xlim(0.3, 1.15)   # ← x does not start at 0
```
Bars start visually at 0.3, making Pet (0.51) look ~40% of Electronics (0.865) when it's actually ~59%. **The core comparison is visually exaggerated by ~2×.**

**FIX:** `ax.set_xlim(0, 1.15)`

### F6b — `outputs/figures/layer1/concentration_over_time.png` (nb01 cell 52)
```python
ax.set_ylim(bottom=0.535, top=0.605)
```
Gini moves 0.582 → 0.544 (Δ=0.038). On the truncated axis this fills half the chart; on a 0–1 Gini scale it's barely visible. The narrative ("COVID-era concentration fell") **depends on the visual exaggeration**.

**FIX:** Either change to `ax.set_ylim(0, 1.0)` (more honest, weaker visual) or keep truncation but add to subtitle: *"y-axis truncated; absolute range 0.535–0.605 of 0–1 Gini scale."*

---

# 🟡 Serious Issues (won't fail screens, but cost interview points)

| # | Location | Problem | Fix |
|---|---|---|---|
| S1 | nb01 + nb02 throughout | `"Interview defense:"` callouts baked into notebook outputs | **Delete all of them.** Deliverables don't narrate their own defensibility — the work speaks for itself. Reads as performance anxiety. |
| S2 | `README.md:224` Tech Stack + nb02 cells 22, 23, 33 | "**Stats / ML:**" label + "model calibration / probability bins / shuffle-label diagnostic / Brier / leakage-suspicion threshold" — ML vocab dominates | Change to "**Stats:**"; relocate ML terms to a Methodology Appendix; in main text use "calibration check / drop-off rate by probability bin / trust gates" |
| S3 | `sql/02_decile_assignment.sql:19` | `NTILE(10) OVER (ORDER BY total_gmv DESC)` — tie handling undefined at decile boundaries | Add deterministic tiebreaker: `ORDER BY total_gmv DESC, household_id` |
| S4 | `sql/05_household_features.sql:48` | `COUNT(*) AS orders_trailing_12m` counts line items, not orders. AOV (line 49) has the same bug. | Rename to `line_items_trailing_12m`, or use `COUNT(DISTINCT order_id)` if an order-id field exists |
| S5 | METHODOLOGY + README | Prolific = paid survey panel; selection bias is much stronger than Nielsen-style. README only says "people who consent may differ." | Add: *"Prolific respondents skew younger, more digitally engaged, lower-median-income than Amazon's customer base — over-index figures are panel-internal, not extrapolable."* |
| S6 | README demographic over-index callouts | "+387% over-index [CI: …]" gives CI but **never gives cell N** | Add `n=XX` after every over-index claim. +387% on n=40 vs n=400 are different stories. |
| S7 | `sql/05_household_features.sql:31` | Comment says "panel-internal inactivity treated as legitimate zero" — but panel attrition vs purchase attrition aren't separable | Add Limitations bullet: *"Panel attrition vs purchase attrition is not separable; both manifest as zero GMV."* |
| S8 | nb01 + nb02 | Markdown ratio 26% / 30% (nb03 is 46%) — reads as code log with narrative dumped at the end | Insert "Surprising Findings" blocks **immediately after** the relevant calculation, not at end-of-notebook. nb03 is the template. |
| S9 | `sql/01_user_gmv_capped.sql:25`, `05:38` | `"Purchase Price Per Unit" * "Quantity"` has no NULL/negative guard — silent row loss on NULL, returns reduce GMV without disclosure | Add `WHERE "Purchase Price Per Unit" IS NOT NULL AND "Quantity" > 0`, log dropped row count |
| S10 | `sql/05_household_features.sql:48` window comment | Header says `(2021-07-01, 2022-06-30]` (left-open) but SQL uses `>= '2021-07-01'` (left-closed) → actual window is `[2021-07-01, 2022-07-01)` | Fix comment to match SQL |

---

# 🟠 Reproducibility gaps (a recruiter who clones can't run this)

- `sql/02–07` depend on `outputs/tables/user_gmv_deciles.parquet` and similar intermediate files, which are gitignored and produced inside notebook cells. After a fresh clone, the SQL is non-runnable.
- **FIX:** Extract intermediate-parquet generation into `src/build_sql_inputs.py`. Add to README:
  ```bash
  python -m src.build_sql_inputs   # generates outputs/tables/*.parquet from raw data
  jupyter notebook notebooks/01_layer1_concentration.ipynb
  ```
- README "How to Run" never mentions SQL files at all. Add an example:
  ```bash
  python -c "from src.data_loader import get_duckdb_conn; \
             con = get_duckdb_conn(); \
             print(con.sql(open('sql/01_user_gmv_capped.sql').read()).df())"
  ```
- `requirements.txt`: tighten `duckdb>=1.0` to `duckdb>=1.0,<2.0` and note tested version.

---

# 🔵 Polish Wins (each < 10 min, high signal)

1. **Swap README hero image** from Lorenz curve to **Layer 2 decile RaR ladder** or **Layer 3 allocation matrix** — Lorenz is supporting evidence; the non-obvious findings are the differentiated hook.
2. **Add CI to README headline 36.2%** — MANIFEST already has 41K bootstrap resamples, so the CI exists.
3. **Delete nb01 cell 62 "Differentiation pillar checklist"** — self-grading reads as insecurity.
4. **Normalize SQL indentation** across all 7 files (currently mixes 1-space and 4-space).
5. **Remove `🔗` emoji from README** (Leo's voice rule = no emojis).
6. **Add MANIFEST reconciliation note** for 2,845 vs 2,846 (one excluded household `R_1d1fnT4sjZABBwe`).
7. **Hardcoded Lorenz annotation coords in nb01 cell 32** (`top10_x, top10_y = 0.90, 1.0 - 0.3618`) — read from `decile_contribution` DataFrame instead, so refreshing data doesn't desync the annotation.

---

# ✅ What's genuinely strong (do not change)

These are the elements that get Leo to final rounds:

- **"Concentration at the top, revenue-at-risk in the middle"** — counterintuitive, panel-bounded, dollar-quantified. The most valuable sentence in the portfolio. (Re-check this claim survives the F1 fix.)
- **"The Question / The Answer / The Method / The Caveat"** narrative scaffold — most undergrad portfolios don't have this structure.
- **Shuffle-label leakage diagnostic** (median AUC 0.54 across 50 shuffles) — proactively answers "is this leaking?"
- **Recency-only baseline at AUC 0.86, model adds only +0.046** — proactively disarms "AUC suspiciously high."
- **STRPTIME 28.6% / 71% pre-flight discovery** — documented data-quality instinct.
- **MANIFEST with SHA-256 hashes + row counts + seed=42/123 dual seed** — reproducibility hygiene rarely seen in undergrad work.
- **Layer 3 cross-layer "naïve Scale × Growth lies → overlay reframe"** — signals "could sit in a planning meeting."
- **Pet bullet with simultaneous loyalty read + niche alt-explanation** — grad-level epistemic honesty.
- **The Caveat as a first-class section, not a footnote** — signals awareness that finance partners ask about limitations first.
- **`src/stats_utils.py` Gini and Lorenz implementations** — correct Sen 1973 trapezoidal form, properly anchored, vectorized bootstrap with seed control.
- **LEFT JOIN to `all_households` / `all_panel` in sql/05 and sql/06** — correctly preserves inactive households as legitimate zeros, and the choice is disclosed.

---

# Recommended fix order

If time is constrained, work in this order — earlier fixes unblock later ones:

1. **F1 (decile leakage)** — Must come first. If the headline changes, README narrative downstream also changes.
2. **F3 (File 07 date bug)** — One-line fix, but affects every Layer 3 number.
3. **F5 (prescriptive language)** — 5 find-and-replace edits, ~10 min.
4. **F2 (GMV cap)** — Path A with sensitivity table.
5. **F6 (axis truncation)** — Two charts, ~30 min.
6. **F4 (RaR rename)** — Global replace, ~1 hour.
7. **Reproducibility (`src/build_sql_inputs.py`)** — Without this, recruiters can't run the SQL after cloning.
8. Then sweep S1–S10.

After F1–F7 + reproducibility, this portfolio moves from "would get cut mid-screen" to "would get forwarded to the panel."

---

# Voice rules reference (for the next session)

When making any edit, enforce these:

1. **Finance-BI vocabulary only.** No "model accuracy", "training set", "feature importance for prediction", "ROC", "predictive model". Use: concentration, contribution, decile, exposure, allocation, segment, cohort, mix, attribution, variance.
2. **Descriptive, never prescriptive.** "The data suggests / indicates / is consistent with" ✅. "Amazon should / we recommend / the company must / next steps for the business" ❌.
3. **English only** in all GitHub-facing files (README, MANIFEST, METHODOLOGY, notebooks/, sql/, src/, tableau/).
4. **No generalization beyond panel** without explicit caveat. Always say "this 2,846-household U.S. panel" — never "Amazon customers" or "Amazon revenue" uncaveated.
5. **Surprising findings = BA insights about the business pattern.** Engineering / audit wins (e.g., "caught SQL bug via Polars cross-check") belong in Methodology or Limitations, not in the headlines section.
6. **No emojis** in any committed file unless explicitly requested.
