"""Out-of-sample checks for Layer 2 and uncertainty on the Layer 1 headline.

Notebook 02 reports the drop-off model's AUC in-sample (fit and scored on the
same Q3 2022 labels). This script adds the held-out views:

  [1] Held-out households on the Q3 2022 panel: 5-fold stratified
      cross-validation (also repeated 10x) and one 80/20 stratified holdout.
      Winsorize caps and z-scores are fit on the training part only, so no
      held-out information reaches preprocessing.
  [2] A true walk-forward backtest: fit on Q2 2022 (features as of 2022-03-31,
      outcome = no purchase in Apr-Jun), then score Q3 2022 (features as of
      2022-06-30, outcome = no purchase in Jul-Sep).
  [3] Bootstrap 95% CIs (1,000 household resamples) on the Gini coefficient
      and the top-decile share of GMV.

Features are rebuilt from sql/05 + notebook 02's derived-feature code with
only the dates shifted, and the 2022-06-30 build is checked against notebook
02's household_features.parquet before anything is reported.

Run after notebooks 01 + 02 (needs data/raw/ and outputs/tables/):
    python -m src.robustness_checks
Writes outputs/robustness_checks.json.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import (RepeatedStratifiedKFold, StratifiedKFold, cross_val_score,
                                     train_test_split)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import get_duckdb_conn  # noqa: E402
from stats_utils import compute_gini  # noqa: E402

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
TBL: Final[Path] = ROOT / "outputs" / "tables"
SEED: Final[int] = 42
B: Final[int] = 1000
FEATURE_COLS: Final[list[str]] = [          # same order as notebook 02
    "gmv_trailing_12m", "gmv_trailing_24m_lag12m", "gmv_trend",
    "line_items_trailing_12m", "aov_trailing_12m", "recency_days",
    "n_distinct_categories_trailing_12m", "aov_slope",
]


class Winsorize(BaseEstimator, TransformerMixin):
    """Clip each feature to its 1st/99th percentile, learned on the fit data only."""

    def fit(self, X, y=None):
        self.lo_ = np.percentile(X, 1, axis=0)
        self.hi_ = np.percentile(X, 99, axis=0)
        return self

    def transform(self, X):
        return np.clip(X, self.lo_, self.hi_)


def model():
    """Notebook 02's pipeline: winsorize 1/99 -> z-score -> L2 logistic regression."""
    return make_pipeline(Winsorize(), StandardScaler(),
                         LogisticRegression(C=1.0, max_iter=2000, random_state=SEED))


def _months(d: dt.date, k: int) -> dt.date:
    m = d.month - 1 + k
    return dt.date(d.year + m // 12, m % 12 + 1, d.day)


def _shift_dates(sql: str, mapping: dict[str, dt.date]) -> str:
    """Replace the TIMESTAMP 'YYYY-MM-DD' literals in a sql/ file."""
    def sub(m):
        return f"TIMESTAMP '{mapping.get(m.group(1), m.group(1))}'"
    return re.sub(r"TIMESTAMP '(\d{4}-\d{2}-\d{2})'", sub, sql)


def _trimmed_slope(monthly_values) -> float:
    # Verbatim from notebook 02 (aov_slope).
    if monthly_values is None or len(monthly_values) < 3:
        return 0.0
    arr = np.asarray(monthly_values, dtype=np.float64)
    lo, hi = np.percentile(arr, [5, 95])
    arr_kept = arr[(arr >= lo) & (arr <= hi)]
    if arr_kept.size < 3:
        return 0.0
    x = np.arange(arr_kept.size, dtype=np.float64)
    num = ((x - x.mean()) * (arr_kept - arr_kept.mean())).sum()
    den = ((x - x.mean()) ** 2).sum()
    return float(num / den) if den > 0 else 0.0


def panel_as_of(con, purchases: pl.DataFrame, cutoff: dt.date) -> pl.DataFrame:
    """household_id + the 8 features as of `cutoff` + drop-off in the next quarter."""
    base = dt.date(2022, 7, 1)                  # the dates written in sql/05 and sql/06
    feat_sql = _shift_dates((ROOT / "sql" / "05_household_features.sql").read_text(), {
        str(base): cutoff, str(_months(base, -12)): _months(cutoff, -12),
        str(_months(base, -24)): _months(cutoff, -24)})
    out_sql = _shift_dates((ROOT / "sql" / "06_q3_outcome.sql").read_text(), {
        str(base): cutoff, str(_months(base, 3)): _months(cutoff, 3)})
    feats = con.sql(feat_sql).pl()
    outcome = con.sql(out_sql).pl()

    last_day = cutoff - dt.timedelta(days=1)
    filt = (purchases
            .with_columns(pl.col("Order Date").str.strptime(pl.Datetime, format="%Y-%m-%d", strict=True).alias("order_date"),
                          (pl.col("Purchase Price Per Unit") * pl.col("Quantity")).alias("line_gmv"))
            .filter(pl.col("order_date") < pl.datetime(cutoff.year, cutoff.month, cutoff.day))
            .rename({"Survey ResponseID": "household_id"}))
    slope = (filt.with_columns(pl.col("order_date").dt.truncate("1mo").alias("month"))
             .group_by(["household_id", "month"])
             .agg((pl.col("line_gmv").sum() / pl.len()).alias("monthly_aov"))
             .sort(["household_id", "month"])
             .group_by("household_id")
             .agg(pl.col("monthly_aov").alias("lst"))
             .with_columns(pl.col("lst").map_elements(_trimmed_slope, return_dtype=pl.Float64).alias("aov_slope"))
             .select(["household_id", "aov_slope"]))
    feats = (feats
             .with_columns(
                 ((pl.col("gmv_trailing_12m") + 1.0).log()
                  - (pl.col("gmv_trailing_24m_lag12m") + 1.0).log()).alias("gmv_trend"),
                 pl.min_horizontal((pl.lit(last_day) - pl.col("last_order_date")).dt.total_days(),
                                   pl.lit(365)).cast(pl.Int64).alias("recency_days"))
             .join(slope, on="household_id", how="left")
             .with_columns(pl.col("aov_slope").fill_null(0.0),
                           pl.col("recency_days").fill_null(365))   # no purchase yet: max recency
             .select(["household_id"] + FEATURE_COLS))
    return feats.join(outcome, on="household_id", how="inner").sort("household_id")


def _xy(df: pl.DataFrame):
    return (df.select(FEATURE_COLS).to_numpy().astype(np.float64),
            df["is_dropoff_q3"].to_numpy().astype(np.int64))


def main() -> None:
    from data_loader import load_purchases

    con = get_duckdb_conn()
    purchases = load_purchases()
    q3 = panel_as_of(con, purchases, dt.date(2022, 7, 1))
    q2 = panel_as_of(con, purchases, dt.date(2022, 4, 1))
    con.close()

    # Guard: the rebuilt Q3 features must be notebook 02's features.
    nb = TBL / "household_features.parquet"
    if nb.exists() and set(FEATURE_COLS) <= set(pl.read_parquet(nb).columns):
        ref = pl.read_parquet(nb).sort("household_id")
        mine = q3.filter(pl.col("household_id").is_in(ref["household_id"].to_list()))
        assert (mine["household_id"] == ref["household_id"]).all()
        for c in FEATURE_COLS:
            np.testing.assert_allclose(mine[c].to_numpy(), ref[c].to_numpy(), rtol=1e-9, atol=1e-9,
                                       err_msg=f"{c} differs from notebook 02")
        print(f"  rebuilt Q3 features match notebook 02 ({ref.height:,} households x {len(FEATURE_COLS)} features)")
    else:
        print("  note: notebook 02's household_features.parquet not found, feature check skipped")

    X, y = _xy(q3)
    in_sample = roc_auc_score(y, model().fit(X, y).predict_proba(X)[:, 1])
    cv = cross_val_score(model(), X, y, scoring="roc_auc",
                         cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED))
    rep = cross_val_score(model(), X, y, scoring="roc_auc",
                          cv=RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=SEED))

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=SEED)
    holdout = roc_auc_score(y_te, model().fit(X_tr, y_tr).predict_proba(X_te)[:, 1])

    X2, y2 = _xy(q2)
    backtest = roc_auc_score(y, model().fit(X2, y2).predict_proba(X)[:, 1])

    deciles = pl.read_parquet(TBL / "user_gmv_deciles.parquet")
    gmv = deciles["total_gmv"].to_numpy()
    pre = deciles["pre_cutoff_gmv"].to_numpy()
    n = gmv.size
    k = -(-n // 10)                              # NTILE(10): decile 1 holds ceil(n/10)
    top_share = lambda g, p: g[np.argsort(-p, kind="stable")[:k]].sum() / g.sum()  # noqa: E731
    idx = np.random.default_rng(SEED).integers(0, n, size=(B, n))
    gini_b = np.array([compute_gini(gmv[i]) for i in idx])
    share_b = np.array([top_share(gmv[i], pre[i]) for i in idx])
    ci = lambda a: [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]  # noqa: E731

    res = {
        "q3_dropoff_rate": float(y.mean()), "q2_dropoff_rate": float(y2.mean()),
        "auc_in_sample": float(in_sample),
        # "±" is the SD across folds (numpy default, ddof=0)
        "auc_cv5_mean": float(cv.mean()), "auc_cv5_std": float(cv.std()),
        "auc_cv5_folds": [float(a) for a in cv],
        "auc_cv5x10_mean": float(rep.mean()), "auc_cv5x10_std": float(rep.std()),
        "auc_cv5x10_min": float(rep.min()), "auc_cv5x10_max": float(rep.max()),
        "auc_holdout_80_20": float(holdout), "holdout_n": int(len(y_te)),
        "auc_walk_forward_q2_to_q3": float(backtest),
        "gini": float(compute_gini(gmv)), "gini_ci95": ci(gini_b),
        "top_decile_gmv_share": float(top_share(gmv, pre)), "top_decile_gmv_share_ci95": ci(share_b),
    }
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / "robustness_checks.json").write_text(json.dumps(res, indent=2) + "\n")

    print()
    print("Layer 2 drop-off model, AUC")
    print(f"  in-sample, full Q3 panel (notebook 02):    {in_sample:.4f}")
    print(f"  5-fold stratified CV, held-out folds:      {res['auc_cv5_mean']:.4f} ± {res['auc_cv5_std']:.4f}"
          f"   (folds: {', '.join(f'{a:.3f}' for a in cv)})")
    print(f"  5-fold CV repeated 10x:                    {res['auc_cv5x10_mean']:.4f} ± {res['auc_cv5x10_std']:.4f}"
          f"   (min {rep.min():.3f}, max {rep.max():.3f})")
    print(f"  {f'80/20 held-out households (n={len(y_te):,}):':<43}{holdout:.4f}")
    print(f"  walk-forward: fit Q2 2022 -> score Q3 2022: {backtest:.4f}"
          f"   (drop-off rate Q2 {y2.mean():.1%}, Q3 {y.mean():.1%})")
    print()
    print("Layer 1 concentration, bootstrap 95% CI (1,000 household resamples)")
    print(f"  Gini:                  {res['gini']:.3f}  [{res['gini_ci95'][0]:.3f}, {res['gini_ci95'][1]:.3f}]")
    print(f"  top-decile GMV share:  {res['top_decile_gmv_share']:.1%}  "
          f"[{res['top_decile_gmv_share_ci95'][0]:.1%}, {res['top_decile_gmv_share_ci95'][1]:.1%}]")
    print()
    print("wrote outputs/robustness_checks.json")


if __name__ == "__main__":
    main()
