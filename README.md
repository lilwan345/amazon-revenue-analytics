# Amazon Revenue Analytics

[![tests](https://github.com/lilwan345/amazon-revenue-analytics/actions/workflows/tests.yml/badge.svg)](https://github.com/lilwan345/amazon-revenue-analytics/actions/workflows/tests.yml)
[![Tableau Public](https://img.shields.io/badge/Tableau%20Public-live%20dashboard-e97627)](https://public.tableau.com/app/profile/leo.wan3084/viz/AmazonFinanceReviewDashboardQ32022/Dashboard1)
[![MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

The question I wanted to answer was pretty simple. Where does an online
store's money actually come from, which part of it might go quiet next
quarter, and where should the next budget dollar go? I used SQL and Python on
**1.85M real Amazon purchases from 5,026 U.S. households (2018–2022)** and put
everything on one [Tableau dashboard](https://public.tableau.com/app/profile/leo.wan3084/viz/AmazonFinanceReviewDashboardQ32022/Dashboard1).

[![The finance review dashboard: concentration, who the top spenders are, revenue-at-risk by decile, and category size vs. growth](outputs/figures/layer4/dashboard_mockup.png)](https://public.tableau.com/app/profile/leo.wan3084/viz/AmazonFinanceReviewDashboardQ32022/Dashboard1)

*This is a static preview, click it to open the live one.*

## What I found

1. **Revenue is concentrated, but it's not 80/20.** The top 10% of households
   spend 36% of all the money (the top 20% spend 55%). What makes them
   different is mostly how often they order. They order about 11× as often as
   the bottom half, but each order is only about 1.1× bigger. Ordering more
   than 10 times a month turned out to be a way better sign of a top household
   than having a high income.
2. **The risk isn't at the top, it's in the middle.** Households in deciles
   6–9 hold **64% of next quarter's revenue-at-risk** but only 14% of the
   spending. The top 10% hold just 0.7% of it. Which kind of makes sense, people
   who buy every week don't just suddenly stop.
3. **Fast growth and new customers aren't the same thing.** Home and Apparel
   are growing *and* they're where new households start buying. Pet is growing
   too, but mostly because people who already buy a lot are buying more. Books
   is shrinking, but 88% of households still buy books, so cutting it would hit
   exactly the shaky middle group from #2.

So if I was on the finance team I'd split the budget three ways: keep the top
households, protect the middle, and bring new people in through the everyday
categories they start with.

[![Revenue-at-risk by decile: the top decile holds 0.7%, deciles 6 to 9 hold 64%](outputs/figures/layer2/decile_rar_ladder.png)](outputs/figures/layer2/decile_rar_ladder.png)

## Quick glossary

I use a few terms a lot, so here's what they mean:

- **GMV** - gross merchandise value, basically the total money spent.
- **Decile** - rank all households by spending and cut them into 10 equal
  groups. Decile 1 is the top 10%, decile 10 is the bottom 10%.
- **Revenue-at-risk** - a household's chance of buying nothing next quarter ×
  what it would normally spend in a quarter. Add that up and you get how much
  spending could go quiet.
- **Gini** - one number for how concentrated spending is. 0 means everyone
  spends the same, 1 means one household spends everything. It's 0.528 here.
- **AUC** - how good a model is at ranking risky households above safe ones.
  0.5 is a coin flip, 1.0 is perfect.
- **CAGR** - average growth per year, here from 2018 to 2022.

## The data

It's the public [Open e-commerce 1.0](https://doi.org/10.7910/DVN/YGLYDY)
dataset (Berke et al., *Scientific Data* 2024): 5,027 U.S. households who agreed
to share their Amazon order history, hosted on Harvard Dataverse. I only keep
purchases before 2023. After that a lot of people stopped reporting, and if I
kept it their silence would look like they stopped buying. That leaves 5,026
households and about 1.85M purchases.

One thing to keep in mind: these are volunteers, not a random sample of Amazon
customers. So every number here really means "in this panel", not "across all
of Amazon".

## How it works

0. **Is the data even complete?** `src/validate_data.py` compares the raw
   file's size, row count and household count to the published source before
   anything else runs. (There's a story behind this one, see below.)
1. **Where's the revenue?** (`notebooks/01_layer1_concentration.ipynb`) SQL
   (DuckDB) ranks households into deciles, then a Lorenz curve and the Gini
   show how concentrated it is. I also split the top-vs-bottom gap into "orders
   more often" vs "spends more per order".
2. **What's at risk next quarter?** (`notebooks/02_layer2_rar.ipynb`) A
   logistic regression gives each household a chance of buying nothing in Q3
   2022, using only what it did up to June 30, 2022. Chance × expected Q3 spend
   = revenue-at-risk.
3. **Where should the budget go?** (`notebooks/03_layer3_allocation.ipynb`)
   There are 1,816 raw category labels, which is way too many, so I had Claude
   help me group them into 11 categories. The mapping is saved in the repo and I
   spot-checked it by hand. Each category then gets its size and 4-year growth,
   and I join the deciles and the risk from steps 1 and 2 back in.
4. **Can finance see it on one screen?** That's the
   [Tableau dashboard](https://public.tableau.com/app/profile/leo.wan3084/viz/AmazonFinanceReviewDashboardQ32022/Dashboard1),
   one panel per finding.

I went with a plain logistic regression on purpose. If you're on a finance team
you want to see *why* a household got flagged, and a black-box model won't
really tell you that. The reasoning behind every step (and the numbers for each
category) is in [METHODOLOGY.md](METHODOLOGY.md).

## How I know the numbers are right

- **I check the raw file first, because I got burned.** My first copy had been
  opened in a spreadsheet, which quietly cut it off at 1,048,576 rows. I lost
  43% of the data (only 2,846 of 5,027 households) and didn't notice right
  away. I re-downloaded the full file, re-ran everything, and now the pipeline
  just refuses to start on a partial file.
  [METHODOLOGY.md](METHODOLOGY.md#layer-0-data-provenance) lists which findings
  held up and which ones moved.
- **Same inputs every time.** The first notebook re-hashes the raw files
  against [MANIFEST.md](MANIFEST.md) and stops if even one byte is different.
- **Everything gets calculated twice.** Each core table is computed in SQL and
  then again in Python (Polars), and the two have to agree on all 5,026
  households.
- **The risk model can't peek at the answer.** Its inputs stop at June 30, 2022
  (that's enforced in the SQL), and the Q3 outcome is read separately. On
  households it never saw it gets **AUC 0.90** (5-fold cross-validation:
  0.902 ± 0.011). Trained on shuffled outcomes it drops to 0.53, basically a
  coin flip, so the 0.90 is real signal. To be honest though, "days since last
  purchase" alone already gets 0.86, so most of the accuracy is just that
  next-quarter drop-off is pretty predictable.
- **Margins of error.** The key results have bootstrap 95% confidence intervals
  (1,000 resamples), so you get a range and not just one number.
- **Tests.** 26 tests run the real SQL files on a tiny made-up dataset where I
  worked out the answers by hand, plus the stats helpers and the data check.
  They run on every push.

## Limitations

- **It's a volunteer panel.** These households chose to share their data and
  they're more engaged than the average Amazon customer (87% bought something
  in Q3), so anything about engagement is probably a bit on the high side.
- **Revenue-at-risk only covers one quarter.** "Drop-off" means no purchase that
  quarter, not a lost customer. About 28% of households that were silent for a
  whole year came back within a quarter.
- **Demographics are from 2021.** Income and household size were asked once, so
  if someone's income changed between 2018 and 2022 they still get labeled with
  their 2021 answer.
- **Revenue only.** There's no cost or margin data, so "where should the budget
  go" is about revenue, not profit.

## Run it

```bash
git clone https://github.com/lilwan345/amazon-revenue-analytics.git
cd amazon-revenue-analytics
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Download amazon-purchases.csv, survey.csv and fields.csv from
# Harvard Dataverse (doi:10.7910/DVN/YGLYDY) into data/raw/.
# don't open them in Excel or Sheets first, they cut files at 2^20 rows
python src/validate_data.py         # 1. check the raw data is complete

jupyter notebook notebooks/         # 2. run notebooks 01, 02, 03 in order

python -m src.robustness_checks     # 3. held-out model checks and confidence intervals
python src/build_tableau_extracts.py   # 4. refresh the dashboard's CSVs
python src/build_layer4_mockup.py      #    and the static preview above

python -m pytest tests/             # tests (no raw data needed)
```

On the full data notebook 01 takes about 30 seconds and notebook 02 about 45
seconds on my M-series Mac.

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

## About me

I'm **Leo Wan** (Liyuan Wan), I study Artificial Intelligence for Business at
USC Marshall and Viterbi. This was my first end-to-end BI project. Honestly the
part that taught me the most wasn't the model, it was finding out halfway
through that my raw file had been cut short and then having to re-check every
single number. If you spot something off feel free to open an issue.
