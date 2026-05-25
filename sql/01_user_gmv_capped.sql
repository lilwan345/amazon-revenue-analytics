-- sql/01_user_gmv_capped.sql
--
-- User-level GMV aggregation with cohort cap at 2023-01-01.
--
-- Expects a `purchases` view (registered by src.data_loader.get_duckdb_conn():
-- CREATE VIEW purchases AS SELECT * FROM
-- read_csv_auto('data/raw/amazon-purchases.csv')
-- ). When inspecting this file outside the notebook, run the CREATE VIEW above
-- in any DuckDB session and this query becomes self-contained.
--
-- Cohort cap rationale: 2023+ data is sparse (22,569 of 1,048,575 rows, ~2.2%)
-- due to participant attrition. Including post-2023 data would right-censor
-- users who simply stopped reporting purchases, biasing the concentration
-- analysis.
--
-- Date parsing: raw "Order Date" is M/D/YY (e.g. 12/4/18, 2/18/19, 12/22/18).
-- MUST use STRPTIME, NOT `CAST AS DATE`: DuckDB's implicit CAST parses only
-- 28.6% of these strings (verified on a 1000-row probe) and silently returns
-- NULL for the rest. Using CAST would understate Layer 1 GMV by ~70%.

WITH user_orders AS (
 SELECT
 "Survey ResponseID" AS household_id,
 STRPTIME("Order Date", '%-m/%-d/%y') AS order_date,
 "Purchase Price Per Unit" * "Quantity" AS line_gmv
 FROM purchases
 WHERE STRPTIME("Order Date", '%-m/%-d/%y') < TIMESTAMP '2023-01-01'
)
SELECT
 household_id,
 SUM(line_gmv) AS total_gmv,
 -- pre_cutoff_gmv: GMV summed only up to the Layer 2 feature cutoff (2022-07-01).
 -- Used by sql/02 for decile assignment to prevent outcome-window leakage:
 -- assigning deciles on full-period total_gmv would let Q3 2022 spending (the
 -- Layer 2 outcome window) partly determine segment membership.
 SUM(CASE WHEN order_date < TIMESTAMP '2022-07-01' THEN line_gmv ELSE 0 END)
 AS pre_cutoff_gmv,
 -- n_line_items: the raw data is one row per purchased product, so COUNT(*)
 -- counts line items, not distinct shopping carts. Renamed from n_orders for
 -- accuracy (the source data does not carry an order_id field to dedupe carts).
 COUNT(*) AS n_line_items,
 MIN(order_date) AS first_purchase_date,
 MAX(order_date) AS last_purchase_date,
 -- avg_order_value: kept as the recognizable AOV metric name; granularity here
 -- is per line-item (see n_line_items note above).
 SUM(line_gmv) / NULLIF(COUNT(*), 0) AS avg_order_value
FROM user_orders
GROUP BY 1
ORDER BY total_gmv DESC;
