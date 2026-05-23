"""Render the Layer 4 static dashboard mockup (2x2) from the Tableau extracts.

This is the README preview AND the assembly target the user matches against in
Tableau Public. Not the live dashboard — see tableau/LAYER4_BUILD_GUIDE.md.

Run:  .venv/bin/python src/build_layer4_mockup.py
"""
from pathlib import Path
import polars as pl
import matplotlib.pyplot as plt

import viz_utils as vu

ROOT = Path(__file__).resolve().parent.parent
TBL = ROOT / "tableau"
OUTDIR = ROOT / "outputs" / "figures" / "layer4"
OUTDIR.mkdir(parents=True, exist_ok=True)

vu.set_finance_style()
QUAD_COLOR = {
    "INVEST": "#1f4e79", "BET-small": "#2e86c1", "MAINTAIN": "#7f8c8d",
    "HARVEST": "#c0392b", "Boundary": "#bdc3c7",
}


def so_what(ax, text):
    ax.text(0.0, -0.16, text, transform=ax.transAxes, fontsize=9.5,
            style="italic", color=vu.COLOR_MUTED, va="top", wrap=True)


def panel_concentration(ax):
    lz = pl.read_csv(TBL / "lorenz_points.csv")
    ax.plot(lz["cum_population_pct"], lz["cum_gmv_pct"], color=vu.COLOR_PRIMARY, lw=2.2)
    ax.plot(lz["cum_population_pct"], lz["equality_pct"], color=vu.COLOR_NEUTRAL,
            ls="--", lw=1.0)
    ax.fill_between(lz["cum_population_pct"], lz["cum_gmv_pct"], lz["equality_pct"],
                    color=vu.COLOR_PRIMARY, alpha=0.06)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.set_xlabel("Cumulative % of households"); ax.set_ylabel("Cumulative % of GMV")
    ax.set_title("Revenue Concentration  ·  Lorenz + Gini", loc="left", fontweight="bold")
    ax.annotate("Top decile = 36.2% of GMV\nGini = 0.529", xy=(90, 64), xytext=(40, 78),
                fontsize=9, color=vu.COLOR_ACCENT,
                arrowprops=dict(arrowstyle="->", color=vu.COLOR_ACCENT, lw=1))
    so_what(ax, "So what: concentration sits at the top — but the long tail still matters "
                "(top 20% = 55%, not 80%).")


def panel_demographic(ax):
    d = (pl.read_csv(TBL / "demographic_overindex.csv")
         .filter(pl.col("significant") & pl.col("included_in_report"))
         .sort("over_index_pct", descending=True).head(6).sort("over_index_pct"))
    labels = [l.replace("order_freq: ", "").replace("hh_income: ", "")
              .replace("More than 10 times per month", ">10 orders/month")
              for l in d["label"]]
    colors = [vu.COLOR_ACCENT if v == d["over_index_pct"].max() else vu.COLOR_PRIMARY
              for v in d["over_index_pct"]]
    ax.barh(labels, d["over_index_pct"], color=colors)
    for y, v in enumerate(d["over_index_pct"]):
        ax.text(v + 8, y, f"+{v:.0f}%", va="center", fontsize=8.5, color=vu.COLOR_TEXT)
    ax.set_xlabel("Top-decile over-index vs panel (%)")
    ax.set_title("Demographic Over-Index  ·  Top 10% vs panel", loc="left", fontweight="bold")
    ax.margins(x=0.18)
    so_what(ax, "So what: heavy cadence (>10x/mo) over-indexes +387% — engagement, "
                "not affluence, defines the top decile.")


def panel_rar(ax):
    r = pl.read_csv(TBL / "rar_by_decile.csv").sort("decile")
    colors = [vu.COLOR_ACCENT if 6 <= dd <= 9 else vu.COLOR_PRIMARY for dd in r["decile"]]
    ax.bar(r["decile"], r["panel_share_pct"], color=colors)
    ax.set_xticks(range(1, 11))
    ax.set_xlabel("GMV decile (1 = top spenders)"); ax.set_ylabel("% of panel revenue-at-risk")
    ax.set_title("Revenue-at-Risk by Decile  ·  Q3 drop-off", loc="left", fontweight="bold")
    ax.annotate("Mid-deciles 6-9\n= 65% of RaR", xy=(7.5, r.filter(pl.col("decile") == 8)["panel_share_pct"][0]),
                xytext=(2.4, r["panel_share_pct"].max() * 0.8), fontsize=9, color=vu.COLOR_ACCENT,
                arrowprops=dict(arrowstyle="->", color=vu.COLOR_ACCENT, lw=1))
    so_what(ax, "So what: revenue is concentrated at the top, but risk is in the middle — "
                "65% of RaR on 13% of GMV.")


def panel_scale_growth(ax):
    c = pl.read_csv(TBL / "category_scale_growth.csv")
    med_s = c["median_scale"][0] / 1000; med_g = c["median_cagr_pct"][0]
    ax.axvline(med_s, color=vu.COLOR_NEUTRAL, ls="--", lw=1.0)
    ax.axhline(med_g, color=vu.COLOR_NEUTRAL, ls="--", lw=1.0)
    for r in c.iter_rows(named=True):
        x = r["scale_2022_gmv"] / 1000
        ax.scatter(x, r["cagr_pct"], s=20 + r["n_households"] / 18,
                   color=QUAD_COLOR[r["quadrant"]], alpha=0.8, edgecolor="white", lw=0.6, zorder=3)
        ax.annotate(r["super_category"].split(",")[0].split(" & ")[0], (x, r["cagr_pct"]),
                    fontsize=7.5, color=vu.COLOR_TEXT, xytext=(4, 3), textcoords="offset points")
    ax.set_xlabel("2022 GMV scale ($K)"); ax.set_ylabel("4-year CAGR (%)")
    ax.set_title("Growth Allocation  ·  Scale x Growth", loc="left", fontweight="bold")
    ax.text(med_s + 12, ax.get_ylim()[1] * 0.97, f"median ${med_s:.0f}K", fontsize=7.5,
            color=vu.COLOR_MUTED, va="top")
    so_what(ax, "So what: Home & H&PC are the cleanest INVEST — high growth that new "
                "customers actually enter through.")


def main():
    fig, axes = plt.subplots(2, 2, figsize=(15.5, 11.5))
    panel_concentration(axes[0, 0])
    panel_demographic(axes[0, 1])
    panel_rar(axes[1, 0])
    panel_scale_growth(axes[1, 1])
    fig.suptitle("Revenue Concentration, Revenue-at-Risk & Growth Allocation",
                 fontsize=17, fontweight="bold", color=vu.COLOR_PRIMARY, x=0.012, ha="left", y=0.985)
    fig.text(0.012, 0.952, "Finance Review Dashboard  ·  Q3 2022 Snapshot  ·  2,846 U.S. households "
             "(consenting panel)", fontsize=10.5, color=vu.COLOR_MUTED, ha="left")
    fig.text(0.012, 0.012, "Static mockup of the Tableau dashboard — build steps in "
             "tableau/LAYER4_BUILD_GUIDE.md; live interactive version linked in README.",
             fontsize=8, color=vu.COLOR_MUTED, ha="left", style="italic")
    fig.tight_layout(rect=[0, 0.025, 1, 0.94], h_pad=4.5, w_pad=3.5)
    out = OUTDIR / "dashboard_mockup.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    print(f"wrote {out}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
