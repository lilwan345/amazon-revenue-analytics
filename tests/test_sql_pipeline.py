"""
Runs the real sql/ files on a small synthetic panel whose answers are known by
hand, so the pipeline logic is checked without the 313 MB Dataverse download.

What it pins down: the 2023 cohort cap, the bad-row filters, decile order and
sizes, the pre-cutoff decile ranking, the Layer 2 walk-forward guard (no
feature may see 2022-07-01 or later), and the Q3 drop-off label.
"""

import datetime as dt
import shutil
from pathlib import Path

import polars as pl
import pytest

import build_sql_inputs
import data_loader
import robustness_checks

ROOT = Path(__file__).resolve().parent.parent

# 20 households. Household h{i} spends (i + 1) * $10 per order on six dates
# spread over 2018-2022, so a higher index means a bigger spender. Every other
# household also buys in Q3 2022 (active), the rest don't (drop-off).
DATES = ["2018-03-01", "2019-05-10", "2020-08-15", "2021-02-01", "2021-09-30", "2022-06-30"]


def _rows():
    rows = []
    for i in range(20):
        hh = f"h{i:02d}"
        for d in DATES:
            rows.append((hh, d, (i + 1) * 10.0, 1.0, "BOOK"))
        if i % 2 == 0:
            rows.append((hh, "2022-08-01", 5.0, 1.0, "PET_FOOD"))   # Q3 2022: active
    rows += [
        ("h00", "2023-02-01", 999.0, 1.0, "BOOK"),   # after the 2023-01-01 cohort cap
        ("h01", "2021-01-01", 0.0, 1.0, "BOOK"),     # zero price: filtered
        ("h01", "2021-01-02", 50.0, None, "BOOK"),   # missing quantity: filtered
        ("h02", "2022-12-31", 40.0, 2.0, "TOY"),     # in the cohort, after the Layer 2 cutoff
        ("late", "2023-03-01", 100.0, 1.0, "BOOK"),  # only buys after the cap: not in panel
    ]
    return pl.DataFrame(
        rows,
        schema={"Survey ResponseID": pl.Utf8, "Order Date": pl.Utf8,
                "Purchase Price Per Unit": pl.Float64, "Quantity": pl.Float64,
                "Category": pl.Utf8},
        orient="row",
    )


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """Run sql/01-06 in build_sql_inputs' order inside a scratch project dir."""
    shutil.copytree(ROOT / "sql", tmp_path / "sql")
    (tmp_path / "outputs" / "tables").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)  # the SQL reads outputs/tables/*.parquet relative to cwd

    # Same views the real run uses (data_loader.get_duckdb_conn), on synthetic CSVs.
    purchases = _rows()
    purchases.write_csv(tmp_path / "amazon-purchases.csv")
    pl.DataFrame({"Survey ResponseID": purchases["Survey ResponseID"].unique()}).write_csv(
        tmp_path / "survey.csv")
    monkeypatch.setattr(data_loader, "PURCHASES_PATH", tmp_path / "amazon-purchases.csv")
    monkeypatch.setattr(data_loader, "SURVEY_PATH", tmp_path / "survey.csv")
    con = data_loader.get_duckdb_conn()

    out = {}
    for sql_file, out_name in build_sql_inputs.PIPELINE:
        df = con.sql((tmp_path / "sql" / sql_file).read_text()).pl()
        df.write_parquet(tmp_path / "outputs" / "tables" / out_name)
        out[out_name.removesuffix(".parquet")] = df
    out["purchases"] = purchases
    out["con"] = con
    yield out
    con.close()


def test_cohort_cap_and_bad_rows(pipeline):
    gmv = pipeline["user_gmv"]
    assert gmv.height == 20                       # "late" only bought after the cap
    h00 = gmv.filter(pl.col("household_id") == "h00").row(0, named=True)
    assert h00["total_gmv"] == pytest.approx(6 * 10 + 5)   # 2023 order excluded
    h01 = gmv.filter(pl.col("household_id") == "h01").row(0, named=True)
    assert h01["n_line_items"] == 6               # zero-price and null-quantity rows dropped
    h02 = gmv.filter(pl.col("household_id") == "h02").row(0, named=True)
    assert h02["total_gmv"] == pytest.approx(6 * 30 + 5 + 80)
    assert h02["pre_cutoff_gmv"] == pytest.approx(6 * 30)  # nothing from 2022-07-01 on


def test_sql_matches_an_independent_polars_rollup(pipeline):
    p = pipeline["purchases"]
    polars_gmv = (
        p.with_columns(pl.col("Order Date").str.strptime(pl.Date, "%Y-%m-%d"))
        .filter((pl.col("Order Date") < dt.date(2023, 1, 1))
                & (pl.col("Purchase Price Per Unit") > 0) & pl.col("Quantity").is_not_null())
        .group_by("Survey ResponseID")
        .agg((pl.col("Purchase Price Per Unit") * pl.col("Quantity")).sum().alias("gmv"))
        .sort("Survey ResponseID")
    )
    sql_gmv = pipeline["user_gmv"].sort("household_id")
    assert sql_gmv["household_id"].to_list() == polars_gmv["Survey ResponseID"].to_list()
    assert sql_gmv["total_gmv"].to_list() == pytest.approx(polars_gmv["gmv"].to_list())


def test_deciles_are_equal_sized_and_ranked_on_pre_cutoff_spend(pipeline):
    d = pipeline["user_gmv_deciles"]
    assert d.group_by("decile").len()["len"].to_list() == [2] * 10
    top = set(d.filter(pl.col("decile") == 1)["household_id"])
    bottom = set(d.filter(pl.col("decile") == 10)["household_id"])
    assert top == {"h19", "h18"} and bottom == {"h00", "h01"}


def test_decile_contribution_adds_up(pipeline):
    c = pipeline["decile_contribution"].sort("decile")
    assert c["pct_of_total_gmv"].sum() == pytest.approx(1.0)
    assert c["cumulative_pct"][-1] == pytest.approx(1.0)
    assert c["pct_of_total_gmv"].to_list() == sorted(c["pct_of_total_gmv"].to_list(), reverse=True)


def test_layer2_features_never_see_the_outcome_window(pipeline):
    f = pipeline["household_features"]
    assert f.height == 20
    assert f["last_order_date"].max() < dt.date(2022, 7, 1)
    h02 = f.filter(pl.col("household_id") == "h02").row(0, named=True)
    # trailing 12m = [2021-07-01, 2022-07-01): the 2021-09-30 and 2022-06-30 orders only
    assert h02["gmv_trailing_12m"] == pytest.approx(2 * 30)
    assert h02["line_items_trailing_12m"] == 2
    # lagged window = [2020-07-01, 2021-07-01): 2020-08-15 and 2021-02-01
    assert h02["gmv_trailing_24m_lag12m"] == pytest.approx(2 * 30)


def test_q3_dropoff_label(pipeline):
    q3 = dict(pipeline["q3_outcome"].iter_rows())
    assert len(q3) == 20
    assert all(q3[f"h{i:02d}"] == (0 if i % 2 == 0 else 1) for i in range(20))


def test_robustness_date_shift_moves_every_window():
    sql = (ROOT / "sql" / "05_household_features.sql").read_text()
    base = dt.date(2022, 7, 1)
    cutoff = dt.date(2022, 4, 1)
    mapping = {str(base): cutoff,
               str(robustness_checks._months(base, -12)): robustness_checks._months(cutoff, -12),
               str(robustness_checks._months(base, -24)): robustness_checks._months(cutoff, -24)}
    shifted = robustness_checks._shift_dates(sql, mapping)
    assert "TIMESTAMP '2022-07-01'" not in shifted
    for date in ("2022-04-01", "2021-04-01", "2020-04-01"):
        assert f"TIMESTAMP '{date}'" in shifted


@pytest.mark.parametrize("start, k, expected", [
    (dt.date(2022, 7, 1), -12, dt.date(2021, 7, 1)),
    (dt.date(2022, 7, 1), 3, dt.date(2022, 10, 1)),
    (dt.date(2022, 1, 1), -1, dt.date(2021, 12, 1)),
])
def test_month_arithmetic(start, k, expected):
    assert robustness_checks._months(start, k) == expected
