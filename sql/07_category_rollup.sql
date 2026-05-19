-- sql/07_category_rollup.sql
--
-- Layer 3 — roll up 1,816 raw Amazon browse-node leaf categories into 12
-- super-categories via the deterministic taxonomy JSON committed to
-- outputs/tables/category_taxonomy.json (flattened to CSV at
-- outputs/tables/category_taxonomy_mapping.csv for SQL JOIN-friendliness).
--
-- Output: super-category × year aggregates over the cohort-capped panel
-- (2018-2022, project rule "cohort cap at 2023-01-01"). Layer 3 metrics
-- (scale, growth, volatility, per-household scale) are all derived from
-- this rollup parquet — see notebooks/03_layer3_allocation.ipynb Task 8.3.
--
-- NULL raw category (4.8% of cohort-capped rows, 5.4% of GMV) is mapped
-- to "Other / Unknown" via the LEFT JOIN + COALESCE on super_category.
-- This is intentional: NULL is treated as its own observable "missing-data"
-- super-category so Layer 3 GMV totals reconcile against Layer 1 panel-GMV.

WITH purchases_capped AS (
    SELECT
        "Survey ResponseID" AS household_id,
        "Order Date"        AS order_date,
        EXTRACT(YEAR FROM "Order Date") AS yr,
        "Category"          AS raw_category,
        "Purchase Price Per Unit" * "Quantity" AS line_gmv
    FROM read_csv_auto('data/raw/amazon-purchases.csv')
    WHERE "Order Date" < DATE '2023-01-01'
),
taxonomy AS (
    SELECT raw_category, super_category
    FROM read_csv_auto('outputs/tables/category_taxonomy_mapping.csv')
),
joined AS (
    SELECT
        p.household_id,
        p.yr,
        p.raw_category,
        p.line_gmv,
        COALESCE(t.super_category, 'Other / Unknown') AS super_category
    FROM purchases_capped p
    LEFT JOIN taxonomy t USING (raw_category)
)
SELECT
    super_category,
    yr AS year,
    COUNT(*)                          AS n_tx,
    SUM(line_gmv)                     AS total_gmv,
    COUNT(DISTINCT household_id)      AS n_households,
    SUM(line_gmv) / NULLIF(COUNT(DISTINCT household_id), 0) AS gmv_per_household
FROM joined
GROUP BY super_category, year
ORDER BY super_category, year;
