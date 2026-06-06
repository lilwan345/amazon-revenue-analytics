-- sql/01_user_gmv_cohort_dated.sql
--
-- User-level GMV aggregation with cohort DATE cap at 2023-01-01.
-- ("cohort_dated", not "capped" — the cap is a date filter, NOT GMV-value
-- winsorization. No per-user GMV winsorization is applied anywhere in this
-- pipeline; headline concentration metrics measure the actual tail.)
--
-- Expects a `purchases` view (registered by src.data_loader.get_duckdb_conn():
-- CREATE VIEW purchases AS SELECT * FROM
-- read_csv_auto('data/raw/amazon-purchases.csv')
-- ). When inspecting this file outside the notebook, run the CREATE VIEW above
-- in any DuckDB session and this query becomes self-contained.
--
-- Cohort cap rationale: 2023+ data is sparse (~2% of rows) due to participant
-- attrition. Including post-2023 data would right-censor users who simply
-- stopped reporting purchases, biasing the concentration analysis.
--
-- Date parsing: raw "Order Date" is ISO 8601 (YYYY-MM-DD, e.g. 2018-12-04).
-- We parse it with an explicit STRPTIME format string rather than leaning on
-- read_csv_auto's type sniffer, so the parse is self-documenting and stable
-- across DuckDB versions. (The `purchases` view keeps "Order Date" as VARCHAR
-- for exactly this reason -- see src/data_loader.get_duckdb_conn.)

WITH user_orders AS (
 SELECT
 "Survey ResponseID" AS household_id,
 STRPTIME("Order Date", '%Y-%m-%d') AS order_date,
 "Purchase Price Per Unit" * "Quantity" AS line_gmv
 FROM purchases
 -- Defensive NULL / non-positive filters: the current raw data has zero such
 -- rows (verified across all transactions), but guarding here prevents
 -- silent row corruption if the upstream dataset changes between releases.
 WHERE STRPTIME("Order Date", '%Y-%m-%d') < TIMESTAMP '2023-01-01'
   AND "Purchase Price Per Unit" IS NOT NULL AND "Purchase Price Per Unit" > 0
   AND "Quantity" IS NOT NULL AND "Quantity" > 0
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
