-- sql/06_q3_outcome.sql
--
-- Outcome variable for the Layer 2 propensity model (Task 7.2).
--
-- Definition: is_dropoff_q3 = 1 if a household made ZERO orders in 2022-Q3
-- (Jul 1 -- Sep 30, 2022 inclusive), else 0.
--
-- "Drop-off" is intentional vocabulary -- NOT "churn". A single-quarter
-- absence is not permanent attrition; calling it churn would over-claim.
--
-- Positive class = drop-off (the rarer event). Pre-flight measured the panel's
-- 2022-Q3 active rate at 87.3%, so ~12.7% of households (~361 of 2,845) have
-- is_dropoff_q3 = 1.
--
-- This is the ONLY query in Layer 2 that reads purchases with Order Date
-- >= 2022-07-01. Every feature aggregation (sql/05_household_features.sql)
-- strictly precedes the cutoff. Together they enforce walk-forward validation.
--
-- All 2,845 panel households are returned (LEFT JOIN from cohort). Households
-- with NO Q3 order get is_dropoff_q3 = 1.

WITH q3_active AS (
    -- Distinct households that placed at least one order in 2022-Q3.
    SELECT DISTINCT "Survey ResponseID" AS household_id
    FROM purchases
    WHERE STRPTIME("Order Date", '%-m/%-d/%y') >= TIMESTAMP '2022-07-01'
      AND STRPTIME("Order Date", '%-m/%-d/%y') <  TIMESTAMP '2022-10-01'
),
all_panel AS (
    -- All 2,845 cohort-capped households carried forward from Layer 1.
    SELECT household_id
    FROM read_parquet('outputs/tables/user_gmv_deciles.parquet')
)
SELECT
    a.household_id,
    CASE WHEN q.household_id IS NULL THEN 1 ELSE 0 END AS is_dropoff_q3
FROM all_panel a
LEFT JOIN q3_active q ON a.household_id = q.household_id;
