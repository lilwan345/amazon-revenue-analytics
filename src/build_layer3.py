"""Build the Layer 3 category aggregates (makes notebook 03 self-contained).

Regenerates the four Layer 3 parquets that `notebooks/03_layer3_allocation.ipynb`
reads, so the layer is reproducible from the committed repo.

Run AFTER Layer 1 + Layer 2 (needs their household-level outputs):
    python -m src.build_sql_inputs        # Layer 1/2 SQL parquets
    # ...run notebooks 01 + 02 for deciles + RaR...
    python -m src.build_layer3            # notebook 03 also calls this itself

Outputs (outputs/tables/):
    category_yearly.parquet           super_category × year GMV (= sql/07 rollup)
    category_scale_growth.parquet     scale / 4y-CAGR / volatility / per-hh + bootstrap CIs
    category_layer_crosswalk.parquet  D1/D10/mid-decile GMV share, mid-decile RaR share, breadth
    category_cohort_gateway.parquet   new-vs-established cohort category penetration + lift CIs

Metric definitions:
    cagr_4y       = (gmv_2022 / gmv_2018) ** (1/4) - 1
    growth_2020   = (gmv_2022 - gmv_2020) / gmv_2020
    volatility_cv = population std / mean of the five annual GMV points (ddof=0)
    gateway cohort: established = first-purchase year <= 2019; new = first-purchase year >= 2020

Bootstrap CIs resample households (B=1000, seed=42). Households are put in a fixed
(sorted) order before resampling, so the CIs come out identical on every run.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

# Works both as `python -m src.build_layer3` and from notebook 03 (src/ on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import get_duckdb_conn  # noqa: E402

_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_TBL: Final[Path] = _ROOT / "outputs" / "tables"
_TAX_CSV: Final[Path] = _TBL / "category_taxonomy_mapping.csv"
SEED: Final[int] = 42
B: Final[int] = 1000
COHORT_CAP: Final[str] = "2023-01-01"
YEARS: Final[range] = range(2018, 2023)


def _ci(samples: np.ndarray) -> tuple[float, float]:
    return float(np.nanpercentile(samples, 2.5)), float(np.nanpercentile(samples, 97.5))


def _household_category_year() -> pl.DataFrame:
    """Household × super-category × year GMV (cohort-capped); NULL/unmapped -> Other / Unknown."""
    con = get_duckdb_conn()
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
        ),
        tax AS (
            SELECT raw_category, super_category
            FROM read_csv_auto('{_TAX_CSV.as_posix()}')
        )
        SELECT c.household_id, c.yr,
               COALESCE(t.super_category, 'Other / Unknown') AS super_category,
               SUM(c.gmv)::DOUBLE AS gmv
        FROM capped c LEFT JOIN tax t ON c.raw_category = t.raw_category
        GROUP BY 1, 2, 3
        """
    ).pl()
    con.close()
    return hcy


def build_layer3() -> dict[str, Path]:
    hcy = _household_category_year()

    # Fixed household order -> integer index, so every bootstrap below is reproducible.
    households = sorted(hcy["household_id"].unique().to_list())
    n_hh = len(households)
    hcy = hcy.with_columns(
        pl.col("household_id")
        .replace_strict({h: i for i, h in enumerate(households)}, return_dtype=pl.Int64)
        .alias("hh_i")
    )
    cats = sorted(hcy["super_category"].unique().to_list())

    def per_household(cat: str, year: int) -> np.ndarray:
        """GMV per household (length n_hh, 0 if absent) for one category-year."""
        s = hcy.filter((pl.col("super_category") == cat) & (pl.col("yr") == year))
        return np.bincount(s["hh_i"].to_numpy(), weights=s["gmv"].to_numpy(), minlength=n_hh)

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

    # ---- category_scale_growth (household-resample bootstrap CIs) ----
    rng = np.random.default_rng(SEED)
    boot_idx = rng.integers(0, n_hh, size=(B, n_hh))  # shared resample across categories

    rows = []
    for cat in cats:
        annual = {
            y: float(yearly.filter((pl.col("super_category") == cat) & (pl.col("year") == y))["total_gmv"].sum())
            for y in YEARS
        }
        vals = np.array([annual[y] for y in YEARS])
        gmv_2018, gmv_2022 = per_household(cat, 2018), per_household(cat, 2022)
        scale = annual[2022]
        n_hh_2022 = int((gmv_2022 > 0).sum())

        s_b = gmv_2022[boot_idx].sum(axis=1)
        g18_b = gmv_2018[boot_idx].sum(axis=1)
        nhh_b = (gmv_2022[boot_idx] > 0).sum(axis=1)
        s_lo, s_hi = _ci(s_b)
        with np.errstate(divide="ignore", invalid="ignore"):
            c_lo, c_hi = _ci(np.where(g18_b > 0, (s_b / g18_b) ** 0.25 - 1, np.nan))
            p_lo, p_hi = _ci(np.where(nhh_b > 0, s_b / nhh_b, np.nan))

        rows.append({
            "super_category": cat, "scale_2022_gmv": scale,
            "scale_ci_low": s_lo, "scale_ci_high": s_hi,
            "cagr_4y": (scale / annual[2018]) ** 0.25 - 1 if annual[2018] > 0 else float("nan"),
            "cagr_ci_low": c_lo, "cagr_ci_high": c_hi,
            "growth_2020": (scale - annual[2020]) / annual[2020] if annual[2020] > 0 else float("nan"),
            "volatility_cv": float(vals.std() / vals.mean()) if vals.mean() else float("nan"),
            "n_households_2022": n_hh_2022,
            "per_hh_scale_2022": scale / n_hh_2022 if n_hh_2022 else float("nan"),
            "per_hh_ci_low": p_lo, "per_hh_ci_high": p_hi,
        })
    pl.DataFrame(rows).write_parquet(_TBL / "category_scale_growth.parquet")

    # ---- category_layer_crosswalk (folds Layer 1 deciles + Layer 2 RaR back in) ----
    deciles = pl.read_parquet(_TBL / "user_gmv_deciles.parquet").select(["household_id", "decile"])
    rar = pl.read_parquet(_TBL / "rar_per_household.parquet").select(["household_id", "dollar_at_risk"])
    total_cohort = deciles.height
    mid = pl.col("decile").is_between(6, 9)
    crosswalk = (
        hcy.group_by(["household_id", "super_category"]).agg(pl.col("gmv").sum().alias("cat_gmv"))
        .join(deciles, on="household_id", how="left")
        .join(rar, on="household_id", how="left")
        .group_by("super_category")
        .agg(
            pl.col("cat_gmv").sum().alias("_gmv"),
            pl.col("cat_gmv").filter(pl.col("decile") == 1).sum().alias("_d1"),
            pl.col("cat_gmv").filter(pl.col("decile") == 10).sum().alias("_d10"),
            pl.col("cat_gmv").filter(mid).sum().alias("_mid"),
            pl.col("dollar_at_risk").sum().alias("total_category_rar"),
            pl.col("dollar_at_risk").filter(mid).sum().alias("_rar_mid"),
            pl.len().alias("n_households_buying"),
        )
        .select(
            "super_category",
            (pl.col("_d1") / pl.col("_gmv")).alias("d1_gmv_share"),
            (pl.col("_d10") / pl.col("_gmv")).alias("d10_gmv_share"),
            (pl.col("_mid") / pl.col("_gmv")).alias("mid_decile_gmv_share"),
            pl.when(pl.col("total_category_rar") != 0)
              .then(pl.col("_rar_mid") / pl.col("total_category_rar"))
              .otherwise(float("nan")).alias("mid_decile_rar_share"),
            (pl.col("n_households_buying") / total_cohort).alias("household_breadth"),
            pl.col("n_households_buying").cast(pl.Int64),
            pl.col("total_category_rar").cast(pl.Float64),
        )
        .sort("super_category")
    )
    crosswalk.write_parquet(_TBL / "category_layer_crosswalk.parquet")

    # ---- category_cohort_gateway (new vs established cohort penetration) ----
    first_yr = (
        hcy.group_by("hh_i").agg(pl.col("yr").min().alias("first_yr")).sort("hh_i")
    )
    is_new = np.zeros(n_hh, dtype=bool)
    is_new[first_yr["hh_i"].to_numpy()] = first_yr["first_yr"].to_numpy() >= 2020
    n_new, n_est = int(is_new.sum()), int((~is_new).sum())

    gw_rows = []
    for cat in cats:
        bought = np.zeros(n_hh, dtype=bool)
        bought[hcy.filter(pl.col("super_category") == cat)["hh_i"].to_numpy()] = True
        new_mask, est_mask = bought[is_new], bought[~is_new]
        np_, ep_ = new_mask.mean(), est_mask.mean()
        # bootstrap households within each cohort
        nb_boot = new_mask[rng.integers(0, n_new, size=(B, n_new))].mean(axis=1)
        eb_boot = est_mask[rng.integers(0, n_est, size=(B, n_est))].mean(axis=1)
        l_lo, l_hi = _ci(np.where(eb_boot > 0, nb_boot / eb_boot, np.nan))
        gw_rows.append({
            "super_category": cat,
            "new_cohort_buyers": int(new_mask.sum()), "established_cohort_buyers": int(est_mask.sum()),
            "new_penetration": float(np_), "established_penetration": float(ep_),
            "gateway_lift": float(np_ / ep_) if ep_ else float("nan"),
            "lift_ci_low": l_lo, "lift_ci_high": l_hi,
        })
    pl.DataFrame(gw_rows).write_parquet(_TBL / "category_cohort_gateway.parquet")

    print(f"Layer 3 build complete (cohort {total_cohort:,} hh; new {n_new} / established {n_est}):")
    for f in ("category_yearly", "category_scale_growth", "category_layer_crosswalk", "category_cohort_gateway"):
        print(f"  outputs/tables/{f}.parquet")
    return {"scale_growth": _TBL / "category_scale_growth.parquet"}


if __name__ == "__main__":
    build_layer3()
