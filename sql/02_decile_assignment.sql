-- sql/02_decile_assignment.sql
--
-- Decile assignment using NTILE(10) window function on user-level GMV.
-- Decile 1 = top 10% by total_gmv. Decile 10 = bottom 10%.
-- Reads the cohort-capped per-household table from sql/01_user_gmv_capped.sql.
--
-- Why NTILE: equal-count buckets match how finance reports VIP segments
-- (a manual percentile cut by value would give unequal-count buckets,
-- which is wrong for "top decile contribution" questions).
-- ORDER BY total_gmv DESC so decile 1 = highest-GMV households (finance convention).

SELECT
    household_id,
    total_gmv,
    n_orders,
    avg_order_value,
    first_purchase_date,
    last_purchase_date,
    NTILE(10) OVER (ORDER BY total_gmv DESC) AS decile
FROM read_parquet('outputs/tables/user_gmv.parquet');
