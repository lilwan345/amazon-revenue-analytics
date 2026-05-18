-- sql/04_demographic_join.sql
--
-- Left-join the cohort-capped decile-tagged per-household table to the survey
-- demographics. The survey has 5,027 prescreen respondents; the decile table
-- has 2,845 (consenting + cohort-capped). The join key is `Survey ResponseID`
-- which is unique on the survey side, so this produces exactly 2,845 rows.
--
-- Survey demographic columns are 100% populated,
-- so no rows should have NULL demographics after the join.
--
-- Race is preserved as raw multi-select VARCHAR (comma-separated). The notebook
-- parses it into 6 multi-hot booleans (is_white / is_asian / is_black / is_amerindian
-- / is_pacific_islander / is_other_race) before computing over-index, because
-- treating each comma-combination as its own category would shatter sample sizes.

SELECT
 d.household_id,
 d.total_gmv,
 d.n_orders,
 d.avg_order_value,
 d.decile,
 s."Q-demos-age" AS age,
 s."Q-demos-income" AS income,
 s."Q-demos-gender" AS gender,
 s."Q-demos-education" AS education,
 s."Q-demos-state" AS state,
 s."Q-amazon-use-how-oft" AS order_freq,
 s."Q-amazon-use-hh-size" AS hh_size,
 s."Q-demos-race" AS race_multi
FROM read_parquet('outputs/tables/user_gmv_deciles.parquet') d
LEFT JOIN survey s ON d.household_id = s."Survey ResponseID";
