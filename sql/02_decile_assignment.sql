-- sql/02_decile_assignment.sql
--
-- Decile assignment using NTILE(10) on PRE-CUTOFF user-level GMV (pre_cutoff_gmv,
-- summed only through 2022-06-30). Decile 1 = top 10%; decile 10 = bottom 10%.
-- Reads the cohort-date-capped per-household table from sql/01_user_gmv_cohort_dated.sql.
--
-- Why pre_cutoff_gmv (not total_gmv): Layer 2 RaR groups Q3 2022 results by these
-- deciles. Using full-period total_gmv to assign deciles would let Q3 2022 spend
-- (the outcome window) partly determine segment membership, biasing the decile-
-- RaR relationship. Cutting on pre_cutoff_gmv uses the SAME temporal scope as the
-- Layer 2 feature window (sql/05), so the decile is a forward-looking-equivalent
-- ranking and the RaR ladder is leakage-safe.
--
-- Tiebreaker household_id: ensures deterministic NTILE at decile boundaries
-- (multiple households at the same pre_cutoff_gmv get a stable order).
--
-- Why NTILE: equal-count buckets match how finance reports VIP segments.
-- ORDER BY pre_cutoff_gmv DESC so decile 1 = highest-GMV households (finance convention).

SELECT
    household_id,
    total_gmv,
    pre_cutoff_gmv,
    n_line_items,
    avg_order_value,
    first_purchase_date,
    last_purchase_date,
    NTILE(10) OVER (ORDER BY pre_cutoff_gmv DESC, household_id) AS decile
FROM read_parquet('outputs/tables/user_gmv.parquet');
