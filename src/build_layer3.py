"""Build the Layer 3 category aggregates (makes notebook 03 self-contained).

Regenerates the four Layer 3 parquets that `notebooks/03_layer3_allocation.ipynb`
reads, so the layer is reproducible from the committed repo (previously these
were produced by an un-committed scaffold script and could silently go stale).

Run AFTER Layer 1 + Layer 2 (needs their household-level outputs):
    python -m src.build_sql_inputs        # Layer 1/2 SQL parquets
    # ...run notebooks 01 + 02 (or their equivalents) for deciles + RaR...
    python -m src.build_layer3

Outputs (outputs/tables/):
    category_yearly.parquet           super_category × year GMV (= sql/07 rollup)
    category_scale_growth.parquet     scale / 4y-CAGR / volatility / per-hh + bootstrap CIs
    category_layer_crosswalk.parquet  D1/D10/mid-decile GMV share, mid-decile RaR share, breadth
    category_cohort_gateway.parquet   new-vs-established cohort category penetration + lift CIs

Metric definitions (validated to reproduce the prior outputs on the pre-fix data):
    cagr_4y       = (gmv_2022 / gmv_2018) ** (1/4) - 1
    growth_2020   = (gmv_2022 - gmv_2020) / gmv_2020
    volatility_cv = population std / mean of the five annual GMV points (ddof=0)
    gateway cohort: established = first-purchase year <= 2019; new = first-purchase year >= 2020
"""
from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

from data_loader import get_duckdb_conn

_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_TBL: Final[Path] = _ROOT / "outputs" / "tables"
_TAX_CSV: Final[Path] = _TBL / "category_taxonomy_mapping.csv"
SEED: Final[int] = 42
B: Final[int] = 1000
COHORT_CAP: Final[str] = "2023-01-01"


def _ci(samples: np.ndarray) -> tuple[float, float]:
    return float(np.nanpercentile(samples, 2.5)), float(np.nanpercentile(samples, 97.5))


def build_layer3() -> dict[str, Path]:
    con = get_duckdb_conn()
    con.execute(
        f"CREATE OR REPLACE VIEW _tax AS SELECT raw_category, super_category "
        f"FROM read_csv_auto('{_TAX_CSV.as_posix()}')"
    )

    # Household × super-category × year GMV (cohort-capped), NULL/unmapped -> Other/Unknown.
    hcy = con.sql(
        f"""
        WITH capped AS (
            SELECT "Survey ResponseID" AS household_id,
                   EXTRACT(YEAR FROM STRPTIME("Order Date", '%Y-%m-%d')) AS yr,
                   "Category" AS raw_category,
                   "Purchase Price Per Unit" * "Quantity" AS gmv
            FROM purchases
            WHERE STRPTIME("Order Date", '%Y-%m-%d') < TIMESTAMP '{COHORT_CAP}'
              AND "Purchase Price Per Unit" > 0 AND "Quantity" > 0
        )
        SELECT c.household_id, c.yr,
               COALESCE(t.super_category, 'Other / Unknown') AS super_category,
               SUM(c.gmv)::DOUBLE AS gmv
        FROM capped c LEFT JOIN _tax t ON c.raw_category = t.raw_category
        GROUP BY 1, 2, 3
        """
    ).pl()

    # ---- category_yearly (= sql/07 rollup, super_category × year) ----
    yearly = (
        hcy.group_by(["super_category", "yr"])
        .agg(
            pl.col("gmv").sum().alias("total_gmv"),
            pl.col("household_id").n_unique().alias("n_households"),
        )
        .rename({"yr": "year"})
        .with_columns((pl.col("total_gmv") / pl.col("n_households")).alias("gmv_per_household"))
        .sort(["super_category", "year"])
    )
    yearly.write_parquet(_TBL / "category_yearly.parquet")

    cats = sorted(hcy["super_category"].unique().to_list())

    # ---- category_scale_growth (with household-resample bootstrap CIs) ----
    # Pre-pivot per-household yearly GMV per category for fast bootstrap.
    rng = np.random.default_rng(SEED)
    households = hcy["household_id"].unique().to_list()
    hh_index = {h: i for i, h in enumerate(households)}
    n_hh = len(households)
    boot_idx = rng.integers(0, n_hh, size=(B, n_hh))  # shared resample across categories

    rows = []
    for cat in cats:
        sub = hcy.filter(pl.col("super_category") == cat)
        # per-household gmv by year (0 if absent)
        gmv_2018 = np.zeros(n_hh); gmv_2020 = np.zeros(n_hh); gmv_2022 = np.zeros(n_hh)
        for hh, yr, g in zip(sub["household_id"], sub["yr"], sub["gmv"]):
            i = hh_index[hh]
            if yr == 2018: gmv_2018[i] += g
            elif yr == 2020: gmv_2020[i] += g
            elif yr == 2022: gmv_2022[i] += g
        annual = {y: sub.filter(pl.col("yr") == y)["gmv"].sum() for y in range(2018, 2023)}
        vals = np.array([annual[y] for y in range(2018, 2023)], dtype=float)
        scale = float(annual[2022])
        cagr = (annual[2022] / annual[2018]) ** 0.25 - 1 if annual[2018] > 0 else float("nan")
        n_hh_2022 = int((gmv_2022 > 0).sum())
        per_hh = scale / n_hh_2022 if n_hh_2022 else float("nan")

        # bootstrap
        s_b = gmv_2022[boot_idx].sum(axis=1)
        g18_b = gmv_2018[boot_idx].sum(axis=1)
        cagr_b = np.where(g18_b > 0, (s_b / g18_b) ** 0.25 - 1, np.nan)
        nhh_b = (gmv_2022[boot_idx] > 0).sum(axis=1)
        per_hh_b = np.where(nhh_b > 0, s_b / nhh_b, np.nan)
        s_lo, s_hi = _ci(s_b); c_lo, c_hi = _ci(cagr_b); p_lo, p_hi = _ci(per_hh_b)

        rows.append({
            "super_category": cat, "scale_2022_gmv": scale,
            "scale_ci_low": s_lo, "scale_ci_high": s_hi,
            "cagr_4y": cagr, "cagr_ci_low": c_lo, "cagr_ci_high": c_hi,
            "growth_2020": (annual[2022] - annual[2020]) / annual[2020] if annual[2020] > 0 else float("nan"),
            "volatility_cv": float(vals.std() / vals.mean()) if vals.mean() else float("nan"),
            "n_households_2022": n_hh_2022, "per_hh_scale_2022": per_hh,
            "per_hh_ci_low": p_lo, "per_hh_ci_high": p_hi,
        })
    scale_growth = pl.DataFrame(rows)
    scale_growth.write_parquet(_TBL / "category_scale_growth.parquet")

    # ---- category_layer_crosswalk (folds Layer 1 deciles + Layer 2 RaR back in) ----
    deciles = pl.read_parquet(_TBL / "user_gmv_deciles.parquet").select(["household_id", "decile"])
    rar = pl.read_parquet(_TBL / "rar_per_household.parquet").select(["household_id", "dollar_at_risk"])
    total_cohort = deciles.height
    hh_cat = (
        hcy.group_by(["household_id", "super_category"]).agg(pl.col("gmv").sum().alias("cat_gmv"))
        .join(deciles, on="household_id", how="left")
        .join(rar, on="household_id", how="left")
    )
    cw = []
    for cat in cats:
        s = hh_cat.filter(pl.col("super_category") == cat)
        tot_gmv = s["cat_gmv"].sum()
        d1 = s.filter(pl.col("decile") == 1)["cat_gmv"].sum()
        d10 = s.filter(pl.col("decile") == 10)["cat_gmv"].sum()
        mid = s.filter(pl.col("decile").is_between(6, 9))["cat_gmv"].sum()
        rar_tot = s["dollar_at_risk"].sum()
        rar_mid = s.filter(pl.col("decile").is_between(6, 9))["dollar_at_risk"].sum()
        cw.append({
            "super_category": cat,
            "d1_gmv_share": d1 / tot_gmv if tot_gmv else float("nan"),
            "d10_gmv_share": d10 / tot_gmv if tot_gmv else float("nan"),
            "mid_decile_gmv_share": mid / tot_gmv if tot_gmv else float("nan"),
            "mid_decile_rar_share": (rar_mid / rar_tot) if rar_tot else float("nan"),
            "household_breadth": s.height / total_cohort,
            "n_households_buying": s.height,
            "total_category_rar": float(rar_tot) if rar_tot is not None else 0.0,
        })
    crosswalk = pl.DataFrame(cw)
    crosswalk.write_parquet(_TBL / "category_layer_crosswalk.parquet")

    # ---- category_cohort_gateway (new vs established cohort penetration) ----
    first_yr = (
        hcy.group_by("household_id").agg(pl.col("yr").min().alias("first_yr"))
        .with_columns((pl.col("first_yr") >= 2020).alias("is_new"))
    )
    new_ids = set(first_yr.filter(pl.col("is_new"))["household_id"].to_list())
    est_ids = set(first_yr.filter(~pl.col("is_new"))["household_id"].to_list())
    n_new, n_est = len(new_ids), len(est_ids)
    buyers = hcy.group_by(["super_category", "household_id"]).agg(pl.len()).select(["super_category", "household_id"])
    # bootstrap lift: resample within each cohort
    new_arr = np.array(list(new_ids)); est_arr = np.array(list(est_ids))
    gw_rows = []
    for cat in cats:
        cat_buyers = set(buyers.filter(pl.col("super_category") == cat)["household_id"].to_list())
        nb_ = sum(1 for h in new_ids if h in cat_buyers)
        eb_ = sum(1 for h in est_ids if h in cat_buyers)
        np_, ep_ = nb_ / n_new, eb_ / n_est
        lift = np_ / ep_ if ep_ else float("nan")
        # bootstrap households within each cohort
        new_mask = np.array([h in cat_buyers for h in new_arr])
        est_mask = np.array([h in cat_buyers for h in est_arr])
        nb_boot = new_mask[rng.integers(0, n_new, size=(B, n_new))].mean(axis=1)
        eb_boot = est_mask[rng.integers(0, n_est, size=(B, n_est))].mean(axis=1)
        lift_b = np.where(eb_boot > 0, nb_boot / eb_boot, np.nan)
        l_lo, l_hi = _ci(lift_b)
        gw_rows.append({
            "super_category": cat, "new_cohort_buyers": nb_, "established_cohort_buyers": eb_,
            "new_penetration": np_, "established_penetration": ep_,
            "gateway_lift": lift, "lift_ci_low": l_lo, "lift_ci_high": l_hi,
        })
    gateway = pl.DataFrame(gw_rows)
    gateway.write_parquet(_TBL / "category_cohort_gateway.parquet")

    print(f"Layer 3 build complete (cohort {total_cohort:,} hh; new {n_new} / established {n_est}):")
    for f in ("category_yearly", "category_scale_growth", "category_layer_crosswalk", "category_cohort_gateway"):
        print(f"  outputs/tables/{f}.parquet")
    return {"scale_growth": _TBL / "category_scale_growth.parquet"}


if __name__ == "__main__":
    build_layer3()
