-- sql/03_decile_contribution.sql
--
-- Per-decile contribution to total GMV, with running cumulative percent.
-- Reads the decile-tagged per-household table from sql/02_decile_assignment.sql.
--
-- Output columns:
-- decile 1..10 (1 = highest-GMV households)
-- user_count households in that decile (~10% of 2,845)
-- decile_gmv sum of total_gmv for those households
-- pct_of_total_gmv decile_gmv / panel total (this is the Pareto headline)
-- cumulative_pct running sum across deciles 1..d
--
-- Pareto sanity: decile 1 should land around 36%, top two
-- deciles cumulative around 55%. If decile 1 is far below 30% or above 45%,
-- something is wrong with NTILE sort direction or upstream GMV.

WITH decile_agg AS (
 SELECT
 decile,
 COUNT(*) AS user_count,
 SUM(total_gmv) AS decile_gmv
 FROM read_parquet('outputs/tables/user_gmv_deciles.parquet')
 GROUP BY decile
)
SELECT
 decile,
 user_count,
 decile_gmv,
 decile_gmv / SUM(decile_gmv) OVER () AS pct_of_total_gmv,
 SUM(decile_gmv) OVER (ORDER BY decile ROWS UNBOUNDED PRECEDING)
 / SUM(decile_gmv) OVER () AS cumulative_pct
FROM decile_agg
ORDER BY decile;
