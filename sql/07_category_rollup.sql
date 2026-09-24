-- sql/07_category_rollup.sql
--
-- Layer 3 — roll up 1,816 raw Amazon category labels into 11 (+ Other/Unknown)
-- super-categories via the deterministic taxonomy JSON committed to
-- outputs/tables/category_taxonomy.json (flattened to CSV at
-- outputs/tables/category_taxonomy_mapping.csv for SQL JOIN-friendliness).
--
-- Expects the `purchases` view registered by src.data_loader.get_duckdb_conn()
-- (same as sql/01 and sql/05). Run from the project root so the taxonomy CSV
-- path resolves.
--
-- Output: super-category × year aggregates over the cohort-capped panel
-- (2018-2022, project rule "cohort cap at 2023-01-01"). Layer 3 metrics
-- (scale, growth, volatility, per-household scale) are all derived from
-- this rollup; src/build_layer3.py computes the same rollup (category_yearly)
-- and notebook 03 asserts the total reconciles to Layer 1's panel GMV.
--
-- A NULL raw category (~5% of GMV), or a raw label the taxonomy does not list,
-- is mapped to "Other / Unknown" via the LEFT JOIN + COALESCE on super_category.
-- This is intentional: missing data stays visible as its own bucket instead of
-- being dropped, so Layer 3 GMV totals reconcile against Layer 1 panel GMV.

WITH purchases_capped AS (
    -- Same cohort cap and defensive filters as sql/01.
    SELECT
        "Survey ResponseID"                                       AS household_id,
        EXTRACT(YEAR FROM STRPTIME("Order Date", '%Y-%m-%d'))     AS yr,
        "Category"                                                AS raw_category,
        "Purchase Price Per Unit" * "Quantity"                    AS line_gmv
    FROM purchases
    WHERE STRPTIME("Order Date", '%Y-%m-%d') < TIMESTAMP '2023-01-01'
      AND "Purchase Price Per Unit" IS NOT NULL AND "Purchase Price Per Unit" > 0
      AND "Quantity" IS NOT NULL AND "Quantity" > 0
),
taxonomy AS (
    SELECT raw_category, super_category
    FROM read_csv_auto('outputs/tables/category_taxonomy_mapping.csv')
),
joined AS (
    SELECT
        p.household_id,
        p.yr,
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
