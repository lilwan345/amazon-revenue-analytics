"""Build Tableau-ready CSV extracts for Layer 4 (Finance Review Dashboard).

Reshapes the committed-pipeline parquet aggregates in outputs/tables/ into tidy CSVs,
one per dashboard panel. No new analysis — every number traces back to Layers 1-3.
Outputs land in tableau/ (small aggregates, safe to commit).

Run:  .venv/bin/python src/build_tableau_extracts.py
"""
from pathlib import Path
import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parent.parent
TBL = ROOT / "outputs" / "tables"
OUT = ROOT / "tableau"
OUT.mkdir(exist_ok=True)


def panel_concentration():
    """TL — Revenue concentration: Lorenz points + decile contribution bar."""
    hh = pl.read_parquet(TBL / "user_gmv_deciles.parquet")
    gmv = np.sort(hh["total_gmv"].to_numpy())
    n = gmv.size
    cum = np.concatenate([[0.0], np.cumsum(gmv)]) / gmv.sum()   # poorest-i cumulative share
    sel = np.linspace(0, n, 101).astype(int)
    lorenz = pl.DataFrame({
        "cum_population_pct": (sel / n * 100).round(4),
        "cum_gmv_pct": (cum[sel] * 100).round(4),
        "equality_pct": (sel / n * 100).round(4),   # 45-degree reference
    })
    lorenz.write_csv(OUT / "lorenz_points.csv")

    dec = (pl.read_parquet(TBL / "decile_contribution.parquet")
           .select([
               "decile", "user_count",
               (pl.col("pct_of_total_gmv") * 100).round(2).alias("gmv_pct"),
               (pl.col("cumulative_pct") * 100).round(2).alias("cumulative_gmv_pct"),
           ]))
    dec.write_csv(OUT / "decile_contribution.csv")
    return lorenz, dec


def panel_demographic():
    """TR — Demographic over-index of the top decile vs the full sample."""
    d = pl.read_parquet(TBL / "demographic_overindex_with_ci.parquet")
    out = (d.with_columns([
                (pl.col("dimension") + pl.lit(": ") + pl.col("value")).alias("label"),
                (pl.col("overindex_ratio") * 100).round(1).alias("over_index_pct"),
                (pl.col("ci_lower") * 100).round(1).alias("ci_low_pct"),
                (pl.col("ci_upper") * 100).round(1).alias("ci_high_pct"),
                (pl.col("pct_in_top10") * 100).round(1).alias("pct_in_top10"),
                (pl.col("pct_in_sample") * 100).round(1).alias("pct_in_sample"),
            ])
            .select(["label", "dimension", "value", "over_index_pct", "ci_low_pct",
                     "ci_high_pct", "pct_in_top10", "pct_in_sample", "significant",
                     "included_in_report"])
            .sort("over_index_pct", descending=True))
    out.write_csv(OUT / "demographic_overindex.csv")
    return out


def panel_rar():
    """BL — Revenue-at-Risk: decile ladder (primary) + segment table."""
    hh = pl.read_parquet(TBL / "rar_per_household.parquet")
    total = hh["dollar_at_risk"].sum()
    dec = (hh.group_by("decile")
             .agg([
                 pl.col("dollar_at_risk").sum().round(2).alias("rar_dollars"),
                 pl.col("prob_dropoff_q3").mean().alias("mean_prob_dropoff"),
                 pl.len().alias("n_households"),
             ])
             .with_columns([
                 (pl.col("rar_dollars") / total * 100).round(2).alias("panel_share_pct"),
                 (pl.col("mean_prob_dropoff") * 100).round(2).alias("mean_prob_dropoff_pct"),
             ])
             .sort("decile")
             .select(["decile", "rar_dollars", "panel_share_pct",
                      "mean_prob_dropoff_pct", "n_households"]))
    dec.write_csv(OUT / "rar_by_decile.csv")

    seg = (pl.read_parquet(TBL / "rar_by_segment_with_ci.parquet")
           .with_columns([
               (pl.col("dimension") + pl.lit(": ") + pl.col("value")).alias("label"),
               (pl.col("rar_share") * 100).round(2).alias("rar_share_pct"),
               pl.col("rar_total").round(2).alias("rar_dollars"),
               pl.col("rar_per_household").round(2).alias("rar_per_household"),
           ])
           .select(["label", "dimension", "value", "n_households", "rar_dollars",
                    "rar_per_household", "rar_share_pct"])
           .sort("rar_dollars", descending=True))
    seg.write_csv(OUT / "rar_by_segment.csv")
    return dec, seg


def panel_scale_growth():
    """BR — Growth allocation: Scale x Growth scatter (11 analytic super-categories)."""
    c = pl.read_parquet(TBL / "category_scale_growth.parquet")
    c = c.filter(pl.col("super_category") != "Other / Unknown")
    med_scale = float(c["scale_2022_gmv"].median())   # n=11 (odd) -> equals one category's value
    med_cagr = float(c["cagr_4y"].median())

    def quad(s, g):
        # Categories sitting exactly on a median split line (Toys = median scale,
        # Apparel = median CAGR) are reported as boundary cases, matching the README
        # BCG table. Compare UNROUNDED values; strict >/< otherwise.
        if abs(s - med_scale) < 1.0 or abs(g - med_cagr) < 1e-9:
            return "Boundary"
        hi_s, hi_g = s > med_scale, g > med_cagr
        return ("INVEST" if hi_s and hi_g else
                "BET-small" if (not hi_s) and hi_g else
                "MAINTAIN" if hi_s and (not hi_g) else "HARVEST")

    out = (c.with_columns(
                pl.struct(["scale_2022_gmv", "cagr_4y"]).map_elements(
                    lambda r: quad(r["scale_2022_gmv"], r["cagr_4y"]),
                    return_dtype=pl.String).alias("quadrant"))
            .select([
                "super_category",
                pl.col("scale_2022_gmv").round(0).alias("scale_2022_gmv"),
                (pl.col("cagr_4y") * 100).round(1).alias("cagr_pct"),
                pl.col("n_households_2022").alias("n_households"),
                "quadrant",
            ])
            .with_columns([
                pl.lit(round(med_scale, 0)).alias("median_scale"),
                pl.lit(round(med_cagr * 100, 1)).alias("median_cagr_pct"),
            ])
            .sort("cagr_pct", descending=True))
    out.write_csv(OUT / "category_scale_growth.csv")
    return out, med_scale, med_cagr


if __name__ == "__main__":
    lorenz, dec = panel_concentration()
    demo = panel_demographic()
    rar_dec, rar_seg = panel_rar()
    cat, med_scale, med_cagr = panel_scale_growth()

    print("=== Layer 4 Tableau extracts written to tableau/ ===")
    print(f"lorenz_points.csv          {lorenz.height} rows  (top decile GMV cumshare check: "
          f"{dec.filter(pl.col('decile') == 1)['gmv_pct'][0]}%)")
    print(f"decile_contribution.csv    {dec.height} rows")
    print(f"demographic_overindex.csv  {demo.height} rows  | top over-index: "
          f"{demo['label'][0]} = +{demo['over_index_pct'][0]}%")
    print(f"rar_by_decile.csv          {rar_dec.height} rows | mid-deciles 6-9 RaR share: "
          f"{round(rar_dec.filter(pl.col('decile').is_in([6,7,8,9]))['panel_share_pct'].sum(),1)}%")
    print(f"rar_by_segment.csv         {rar_seg.height} rows")
    print(f"category_scale_growth.csv  {cat.height} rows | median scale ${med_scale/1000:.0f}K, "
          f"median CAGR {med_cagr*100:.1f}%")
    print("quadrants:", cat.group_by("quadrant").len().sort("quadrant").to_dicts())
