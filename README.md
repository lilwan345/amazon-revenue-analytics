# Amazon Revenue Analytics

[![tests](https://github.com/lilwan345/amazon-revenue-analytics/actions/workflows/tests.yml/badge.svg)](https://github.com/lilwan345/amazon-revenue-analytics/actions/workflows/tests.yml)
[![Tableau Public](https://img.shields.io/badge/Tableau%20Public-live%20dashboard-e97627)](https://public.tableau.com/app/profile/leo.wan3084/viz/AmazonFinanceReviewDashboardQ32022/Dashboard1)
[![MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Where does an online store's revenue come from, which part of it could
disappear next quarter, and where should the next budget dollar go? I answer
those three questions with SQL and Python on **1.85M real Amazon purchases
from 5,026 U.S. households (2018–2022)**, then put the answers on one
[Tableau dashboard](https://public.tableau.com/app/profile/leo.wan3084/viz/AmazonFinanceReviewDashboardQ32022/Dashboard1).

[![The finance review dashboard: concentration, who the top spenders are, revenue-at-risk by decile, and category size vs. growth](outputs/figures/layer4/dashboard_mockup.png)](https://public.tableau.com/app/profile/leo.wan3084/viz/AmazonFinanceReviewDashboardQ32022/Dashboard1)

*Static preview of the dashboard. Click it for the live, interactive version.*

## What I found

1. **Revenue is concentrated, but not 80/20.** The top 10% of households
   account for 36% of all spending (the top 20% for 55%). What sets them apart
   is how often they order, about 11× as often as the bottom half, not how
   much each order costs (about 1.1×). Ordering more than 10 times a month is
   a much stronger marker of a top household than high income.
2. **The risk is in the middle, not at the top.** Households in deciles 6–9
   hold **64% of next quarter's revenue-at-risk** but only 14% of spending.
   The top 10% hold just 0.7% of it: people who buy steadily rarely stop.
3. **A fast-growing category is not always where new customers come from.**
   Home and Apparel grow *and* are where new households start buying. Pet
   grows mostly because existing heavy buyers spend more. Books is shrinking
   but reaches 88% of households, so cutting it would hit exactly the
   at-risk middle from finding 2.

So the budget question has three parts: keep the top households, protect the
middle, and win new customers through the everyday categories they start with.

[![Revenue-at-risk by decile: the top decile holds 0.7%, deciles 6 to 9 hold 64%](outputs/figures/layer2/decile_rar_ladder.png)](outputs/figures/layer2/decile_rar_ladder.png)

## Words used here

| Term | Meaning |
|---|---|
| **GMV** | Gross merchandise value: total money spent. |
| **Decile** | Rank households by spending and cut them into 10 equal groups. Decile 1 is the top 10%, decile 10 the bottom 10%. |
| **Revenue-at-risk** | A household's chance of buying nothing next quarter × what it would normally spend that quarter. Added up, it says how much spending could go quiet. |
| **Gini** | One number for concentration: 0 means everyone spends the same, 1 means one household spends everything. Here it is 0.528. |
| **AUC** | How well a model ranks risky households above safe ones: 0.5 is a coin flip, 1.0 is perfect. |
| **CAGR** | Average yearly growth rate, here over 2018–2022. |

## The data

The public [Open e-commerce 1.0](https://doi.org/10.7910/DVN/YGLYDY) dataset
(Berke et al., *Scientific Data* 2024): 5,027 U.S. households who agreed to
share their Amazon purchase history, hosted on Harvard Dataverse. I keep
purchases before 2023, because after that many people stopped reporting and
their silence would look like they stopped buying. That leaves 5,026
households and about 1.85M purchases.

These are volunteers, not a random sample of Amazon customers, so every number
here means "in this panel," not "across Amazon."

## How it works

| Step | Question | How | Where |
|---|---|---|---|
| 0 | Is the data complete? | Check the raw file's size, row count and household count against the published source before anything else runs. | `src/validate_data.py` |
| 1 | Where is revenue concentrated? | SQL (DuckDB) ranks households into deciles; a Lorenz curve and the Gini measure concentration; the top-vs-bottom gap is split into "orders more often" vs. "spends more per order." | `notebooks/01_layer1_concentration.ipynb` |
| 2 | What is at risk next quarter? | A logistic regression scores each household's chance of buying nothing in Q3 2022, using only its behavior up to June 30, 2022. Chance × expected Q3 spend = revenue-at-risk. | `notebooks/02_layer2_rar.ipynb` |
| 3 | Where should budget go? | Claude helped group 1,816 raw category labels into 11 categories (the mapping is saved in the repo and was spot-checked by hand). Each category gets its size and 4-year growth, then the deciles and risk from steps 1–2 are joined back in. | `notebooks/03_layer3_allocation.ipynb` |
| 4 | Can finance see it on one screen? | A Tableau dashboard with one panel per finding. | [Tableau Public](https://public.tableau.com/app/profile/leo.wan3084/viz/AmazonFinanceReviewDashboardQ32022/Dashboard1) |

I chose a simple logistic regression on purpose: a finance team needs to see
*why* a household is flagged, and a black-box model wouldn't show that.
[METHODOLOGY.md](METHODOLOGY.md) has the full reasoning for every step,
including the category-by-category numbers.

## How I know the numbers are right

- **The raw file is checked first.** This check exists because it happened to
  me: my first copy had been opened in a spreadsheet, which silently cut it at
  1,048,576 rows and lost 43% of the data (only 2,846 of 5,027 households). I
  re-downloaded the full file, re-ran everything, and now the pipeline refuses
  to start on a partial file. [METHODOLOGY.md](METHODOLOGY.md#layer-0-data-provenance)
  lists which findings held and which moved.
- **Same inputs every time.** The first notebook re-hashes the raw files
  against [MANIFEST.md](MANIFEST.md) and stops if a single byte differs.
- **Two independent calculations.** Every core table is computed in SQL and
  again in Python (Polars); the two must agree on all 5,026 households.
- **The risk model can't see the answer.** Its inputs stop at June 30, 2022
  (enforced in the SQL), and the Q3 outcome is read separately. On households
  it never saw, it scores **AUC 0.90** (5-fold cross-validation: 0.902 ± 0.011).
  Trained on shuffled outcomes it drops to 0.53, close to a coin flip, so the
  0.90 is real signal. One honest caveat: "days since last purchase" alone
  already reaches 0.86, so most of the accuracy comes from how predictable
  next-quarter drop-off is.
- **Margins of error.** Key results carry bootstrap 95% confidence intervals
  (1,000 resamples), so each number comes with a range, not just a point.
- **Automated tests.** 26 tests run the real SQL files on a small made-up
  dataset whose answers I worked out by hand, plus the statistics helpers and
  the data check. They run on every push.

## Limitations

- **A volunteer panel.** The households chose to share their data and are more
  engaged than Amazon's average customer (87% bought something in Q3), so
  engagement-type numbers are probably on the high side.
- **Revenue-at-risk covers one quarter.** "Drop-off" means no purchase that
  quarter, not a lost customer: about 28% of households that were silent for a
  full year bought again within a quarter.
- **Demographics are a 2021 snapshot.** Income and household size were asked
  once, so a household whose income changed over 2018–2022 is labeled by its
  2021 answer.
- **Revenue only.** There is no cost or margin data, so "where should budget
  go" is about revenue, not profit.

## Run it

```bash
git clone https://github.com/lilwan345/amazon-revenue-analytics.git
cd amazon-revenue-analytics
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Download amazon-purchases.csv, survey.csv and fields.csv from
# Harvard Dataverse (doi:10.7910/DVN/YGLYDY) into data/raw/.
# Don't open them in Excel or Sheets first: they cut files at 2^20 rows.
python src/validate_data.py         # 1. check the raw data is complete

jupyter notebook notebooks/         # 2. run notebooks 01, 02, 03 in order

python -m src.robustness_checks     # 3. held-out model checks and confidence intervals
python src/build_tableau_extracts.py   # 4. refresh the dashboard's CSVs
python src/build_layer4_mockup.py      #    and the static preview above

python -m pytest tests/             # tests (no raw data needed)
```

On the full data, notebook 01 takes about 30 seconds and notebook 02 about 45
seconds on an M-series Mac.

## What's in the repo

```
sql/          the SQL behind every table (DuckDB)
notebooks/    01 concentration · 02 revenue-at-risk · 03 categories
src/          data check, loaders, statistics helpers, build scripts
tests/        pytest suite (runs in CI)
tableau/      the dashboard's data extracts and build guide
outputs/      charts (by step) and the category mapping
METHODOLOGY.md   every method decision and caveat, step by step
MANIFEST.md      input file hashes, output tables, runtimes
```

## About

Built by **Leo Wan** (Liyuan Wan), studying Artificial Intelligence for
Business at USC Marshall and Viterbi. This was my first end-to-end BI project.
The part that taught me the most wasn't the model: it was finding out midway
that my raw file had been silently cut short, and re-checking every number
afterward. Feedback is welcome via issues.
