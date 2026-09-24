"""Data loaders for Amazon Revenue Analytics.

Three entry points used everywhere downstream:

  * load_survey()       -> Polars DataFrame of survey.csv (5,027 x 23)
  * load_purchases()    -> Polars DataFrame of amazon-purchases.csv (~1.85M rows)
  * get_duckdb_conn()   -> DuckDB connection with both CSVs registered as views
                          (so sql/*.sql can `SELECT ... FROM purchases / survey` directly)

Paths are anchored to the project root via Path(__file__).resolve().parent.parent
so the loader keeps working if the project is moved.
"""
from __future__ import annotations

from pathlib import Path
from typing import Final

import duckdb
import polars as pl

# Path anchors -- project root is two levels above this file (src/data_loader.py).
_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_DATA_DIR: Final[Path] = _PROJECT_ROOT / "data" / "raw"
SURVEY_PATH: Final[Path] = _DATA_DIR / "survey.csv"
PURCHASES_PATH: Final[Path] = _DATA_DIR / "amazon-purchases.csv"

SEED: Final[int] = 42


def load_survey() -> pl.DataFrame:
    """Read survey.csv. All columns are categorical strings."""
    df = pl.read_csv(SURVEY_PATH)
    print(f"survey.csv loaded: {df.height:,} rows x {df.width} cols")
    return df


def load_purchases(sample: bool = False, n: int = 10_000) -> pl.DataFrame:
    """Read amazon-purchases.csv as Polars.

    Order Date is kept as a Utf8 string; downstream code parses it explicitly as
    ISO 8601 (STRPTIME in SQL, or str.strptime in Polars), so the format is
    visible at every use site.

    Args:
        sample: If True, return a deterministic random sample of n rows (seed=42).
        n: Sample size when sample=True.
    """
    df = pl.read_csv(
        PURCHASES_PATH,
        schema_overrides={
            "Order Date": pl.Utf8,
            "Purchase Price Per Unit": pl.Float64,
            # Quantity is whole-valued but stored as "1.0" in the source CSV,
            # so read as Float64 (an Int64 override would fail to parse "1.0").
            "Quantity": pl.Float64,
        },
    )
    if sample:
        df = df.sample(n=n, seed=SEED)

    n_households = df["Survey ResponseID"].n_unique()
    msg = (
        f"amazon-purchases.csv loaded: {df.height:,} rows, "
        f"{n_households:,} unique households"
    )
    date_range = _iso_date_range(df["Order Date"])
    if date_range is not None:
        msg += f", date range {date_range[0]} -> {date_range[1]} (parsed via YYYY-MM-DD (ISO))"
    else:
        msg += ", date range UNKNOWN (Order Date is not ISO YYYY-MM-DD -- run src/validate_data.py)"
    print(msg)
    return df


def get_duckdb_conn() -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection with `purchases` and `survey` views registered.

    SQL files in sql/ can `SELECT * FROM purchases` directly. CSVs are read in
    place via read_csv_auto -- no separate database file is created.

    `Order Date` is force-typed VARCHAR so downstream SQL must parse it via
    explicit STRPTIME. If we let read_csv_auto's sniffer pre-type it as DATE,
    every `STRPTIME("Order Date", ...)` call in sql/ would raise a binder
    error (DATE is not VARCHAR), and we would lose the auditable parse step
    in the SQL itself.
    """
    con = duckdb.connect()
    con.sql(
        f"CREATE VIEW purchases AS SELECT * FROM read_csv_auto("
        f"'{PURCHASES_PATH}', types={{'Order Date': 'VARCHAR'}})"
    )
    con.sql(
        f"CREATE VIEW survey AS SELECT * FROM read_csv_auto('{SURVEY_PATH}')"
    )
    return con


def _iso_date_range(col: pl.Series) -> tuple[str, str] | None:
    """(min, max) of an ISO-date Utf8 column, or None if <95% of values parse."""
    if col.dtype != pl.Utf8 or col.len() == 0:
        return None
    parsed = col.str.strptime(pl.Date, format="%Y-%m-%d", strict=False).drop_nulls()
    if parsed.len() / col.len() < 0.95:
        return None
    return str(parsed.min()), str(parsed.max())
