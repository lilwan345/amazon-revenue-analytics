-- sql/05_household_features.sql
--
-- Per-household feature panel as-of 2022-06-30 (Layer 2).
--
-- WALK-FORWARD LEAKAGE GUARD:
--   The first CTE `walk_forward_filter` enforces `Order Date < 2022-07-01`
--   at the SQL level. Every downstream aggregation reads from this CTE only.
--   Any feature aggregate that bypasses this layer is a leakage bug by
--   construction. Validation: a post-load Polars assertion confirms
--   `features['last_order_date'].max() < pl.date(2022, 7, 1)`.
--
-- Date parsing: raw "Order Date" is M/D/YY. Always use
--   STRPTIME("Order Date", '%-m/%-d/%y')
-- not implicit CAST AS DATE (which silently NULLs ~71% of rows).
--
-- Output columns (5 SQL-side features + last_order_date for downstream recency):
--   household_id
--   gmv_trailing_12m                     -- recent  (2021-07-01, 2022-06-30]
--   gmv_trailing_24m_lag12m              -- historical (2020-07-01, 2021-06-30]
--   line_items_trailing_12m
--   aov_trailing_12m
--   n_distinct_categories_trailing_12m
--   last_order_date                      -- for recency_days computation in Polars
--
-- The 3 derived features (gmv_trend, recency_days, aov_slope) are computed
-- in Polars after loading this table -- they require log / date arithmetic /
-- trimmed linear regression respectively, which are cleaner in dataframe code.
--
-- All 2,845 panel households are returned (LEFT JOIN against the cohort).
-- Households inactive in a window have COALESCE'd zeros (by project lock:
-- panel-internal inactivity treated as legitimate zero by cohort definition).

WITH walk_forward_filter AS (
    -- The single leakage guard. Every aggregate below reads from this CTE.
    -- Defensive NULL / non-positive filters mirror sql/01 (zero such rows in
    -- current data; guards prevent silent corruption if upstream changes).
    SELECT
        "Survey ResponseID"                       AS household_id,
        STRPTIME("Order Date", '%-m/%-d/%y')      AS order_date,
        "Purchase Price Per Unit" * "Quantity"    AS line_gmv,
        "Category"                                AS category
    FROM purchases
    WHERE STRPTIME("Order Date", '%-m/%-d/%y') < TIMESTAMP '2022-07-01'
      AND "Purchase Price Per Unit" IS NOT NULL AND "Purchase Price Per Unit" > 0
      AND "Quantity" IS NOT NULL AND "Quantity" > 0
),
trailing_12m AS (
    -- Recent window: [2021-07-01, 2022-07-01) — left-closed, right-open
    -- (12 calendar months; right edge inherited from walk_forward_filter cutoff).
    SELECT
        household_id,
        SUM(line_gmv)                  AS gmv_trailing_12m,
        -- COUNT(*) counts purchase line items (one row per product purchased);
        -- raw data has no order_id to dedupe carts, so this is line-item count.
        COUNT(*)                       AS line_items_trailing_12m,
        SUM(line_gmv) / NULLIF(COUNT(*), 0) AS aov_trailing_12m,
        COUNT(DISTINCT category)       AS n_distinct_categories_trailing_12m
    FROM walk_forward_filter
    WHERE order_date >= TIMESTAMP '2021-07-01'
    GROUP BY household_id
),
trailing_24m_lag12m AS (
    -- Historical window: (2020-07-01, 2021-06-30]
    SELECT
        household_id,
        SUM(line_gmv) AS gmv_trailing_24m_lag12m
    FROM walk_forward_filter
    WHERE order_date >= TIMESTAMP '2020-07-01'
      AND order_date <  TIMESTAMP '2021-07-01'
    GROUP BY household_id
),
last_order AS (
    -- Most-recent order date per household, over all panel-internal history.
    SELECT
        household_id,
        MAX(order_date)::DATE AS last_order_date
    FROM walk_forward_filter
    GROUP BY household_id
),
all_households AS (
    -- All 2,845 Layer 1 cohort households -- LEFT JOIN to retain inactive ones.
    SELECT household_id
    FROM read_parquet('outputs/tables/user_gmv_deciles.parquet')
)
SELECT
    a.household_id,
    COALESCE(t12.gmv_trailing_12m,                       0.0) AS gmv_trailing_12m,
    COALESCE(t12.line_items_trailing_12m,                0)   AS line_items_trailing_12m,
    COALESCE(t12.aov_trailing_12m,                       0.0) AS aov_trailing_12m,
    COALESCE(t12.n_distinct_categories_trailing_12m,     0)   AS n_distinct_categories_trailing_12m,
    COALESCE(t24.gmv_trailing_24m_lag12m,                0.0) AS gmv_trailing_24m_lag12m,
    lo.last_order_date
FROM all_households       a
LEFT JOIN trailing_12m         t12 ON a.household_id = t12.household_id
LEFT JOIN trailing_24m_lag12m  t24 ON a.household_id = t24.household_id
LEFT JOIN last_order           lo  ON a.household_id = lo.household_id;
