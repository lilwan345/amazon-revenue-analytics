"""Layer 1 data loader for Amazon Revenue Analytics.

Three entry points used everywhere downstream:

  * load_survey()       -> Polars DataFrame of survey.csv (5,027 x 23)
  * load_purchases()    -> Polars DataFrame of amazon-purchases.csv (~1.05M rows)
  * get_duckdb_conn()   -> DuckDB connection with both CSVs registered as views
                          (so sql/*.sql can `SELECT ... FROM purchases / survey` directly)

Plus a diagnostic:

  * probe_date_format() -> prints raw Order Date format and parse-rate tests
                          for three candidate formats. Used once during setup to
                          decide whether sql/*.sql needs STRPTIME or plain CAST.

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

# Candidate Order Date formats (Polars chrono / DuckDB STRPTIME both accept these).
# Probed in this order; first format with >=95% parse rate wins for the loader's
# print message. Authoritative format selection still happens in the date-format review.
_DATE_FORMAT_CANDIDATES: Final[list[tuple[str, str]]] = [
    ("%-m/%-d/%y", "M/D/YY"),
    ("%-m/%-d/%Y", "M/D/YYYY"),
    ("%Y-%m-%d", "YYYY-MM-DD (ISO)"),
]


def load_survey() -> pl.DataFrame:
    """Read survey.csv. All columns are categorical strings."""
    df = pl.read_csv(SURVEY_PATH)
    print(f"survey.csv loaded: {df.height:,} rows x {df.width} cols")
    return df


def load_purchases(sample: bool = False, n: int = 10_000) -> pl.DataFrame:
    """Read amazon-purchases.csv as Polars.

    Order Date is kept as Utf8 string -- downstream code parses with the format
    locked in by the date-format review (either inside SQL via STRPTIME, or via an explicit
    Polars cast after this loader). Keeping it raw here avoids committing to a
    format before the probe confirms one.

    Args:
        sample: If True, return a deterministic random sample of n rows (seed=42).
        n: Sample size when sample=True.
    """
    df = pl.read_csv(
        PURCHASES_PATH,
        schema_overrides={
            "Order Date": pl.Utf8,
            "Purchase Price Per Unit": pl.Float64,
            "Quantity": pl.Int64,
        },
    )
    if sample:
        df = df.sample(n=n, seed=SEED)

    n_households = df["Survey ResponseID"].n_unique()
    date_min, date_max, fmt_label = _best_effort_date_range(df["Order Date"])

    msg = (
        f"amazon-purchases.csv loaded: {df.height:,} rows, "
        f"{n_households:,} unique households"
    )
    if fmt_label is not None:
        msg += f", date range {date_min} -> {date_max} (parsed via {fmt_label})"
    else:
        msg += ", date range PENDING (no candidate format parsed >=95% — run probe_date_format())"
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


def probe_date_format() -> None:
    """Diagnostic: print Order Date raw samples + parse rates for 3 candidate formats.

    Used once during setup. After Leo confirms which format is correct, the
    chosen STRPTIME format string is wired into sql/01_user_gmv_capped.sql (and
    any future SQL that filters or aggregates on Order Date).
    """
    bar = "=" * 72
    print(bar)
    print("Order Date format probe -- amazon-purchases.csv")
    print(bar)

    # [1] Raw first-10 strings (read as Utf8, no parsing).
    raw = pl.read_csv(PURCHASES_PATH, schema_overrides={"Order Date": pl.Utf8}, n_rows=10)
    print("\n[1] First 10 raw 'Order Date' values (Utf8, no parsing):")
    for v in raw["Order Date"].to_list():
        print(f"      {v!r}")

    # [2] DuckDB native CAST AS DATE + [3] STRPTIME parse-rates on first 1000 rows.
    # Force Order Date to VARCHAR so strptime sees the raw string; otherwise
    # read_csv_auto's date sniffer pre-types the column as DATE and strptime errors.
    con = duckdb.connect()
    sample_size = 1000
    probe_sql = f"""
        WITH s AS (
            SELECT "Order Date" AS od
            FROM read_csv_auto('{PURCHASES_PATH}', types={{'Order Date': 'VARCHAR'}})
            LIMIT {sample_size}
        )
        SELECT
            COUNT(*)                                            AS total,
            COUNT(TRY_CAST(od AS DATE))                         AS cast_ok,
            COUNT(TRY_STRPTIME(od, '%-m/%-d/%y'))               AS fmt_m_d_yy,
            COUNT(TRY_STRPTIME(od, '%-m/%-d/%Y'))               AS fmt_m_d_yyyy,
            COUNT(TRY_STRPTIME(od, '%Y-%m-%d'))                 AS fmt_iso,
            MIN(od)                                             AS lex_min,
            MAX(od)                                             AS lex_max
        FROM s
    """
    row = con.sql(probe_sql).fetchone()
    total, cast_ok, fmt_2y, fmt_4y, fmt_iso, lex_min, lex_max = row

    def pct(x: int) -> str:
        return f"{x:>4}/{total} ({100 * x / total:5.1f}%)"

    print(f"\n[2] DuckDB CAST AS DATE (no format hint) on first {total} rows:")
    print(f"      parsed OK:                              {pct(cast_ok)}")
    print(f"\n[3] DuckDB TRY_STRPTIME parse rates on first {total} rows:")
    print(f"      '%-m/%-d/%y'  (M/D/YY,   2-digit year): {pct(fmt_2y)}")
    print(f"      '%-m/%-d/%Y'  (M/D/YYYY, 4-digit year): {pct(fmt_4y)}")
    print(f"      '%Y-%m-%d'    (ISO):                    {pct(fmt_iso)}")
    print(f"\n      Lexicographic min/max of raw strings (sanity check):")
    print(f"        min: {lex_min!r}")
    print(f"        max: {lex_max!r}")

    # Full-file parse-rate for the winning format, to surface any tail-row format drift.
    winners = [
        ("%-m/%-d/%y", fmt_2y),
        ("%-m/%-d/%Y", fmt_4y),
        ("%Y-%m-%d", fmt_iso),
    ]
    best_fmt, best_count = max(winners, key=lambda t: t[1])
    if best_count == total:
        full_sql = f"""
            SELECT
                COUNT(*)                                  AS total,
                COUNT(TRY_STRPTIME("Order Date", '{best_fmt}')) AS parsed,
                MIN(TRY_STRPTIME("Order Date", '{best_fmt}'))   AS dt_min,
                MAX(TRY_STRPTIME("Order Date", '{best_fmt}'))   AS dt_max
            FROM read_csv_auto('{PURCHASES_PATH}', types={{'Order Date': 'VARCHAR'}})
        """
        total_full, parsed_full, dt_min, dt_max = con.sql(full_sql).fetchone()
        print(f"\n[4] Full-file parse with leading candidate {best_fmt!r}:")
        print(
            f"      parsed: {parsed_full:,}/{total_full:,} "
            f"({100 * parsed_full / total_full:.2f}%); "
            f"date range: {dt_min} -> {dt_max}"
        )

    con.close()
    print("\n" + bar)
    print("Decision needed: pick the STRPTIME format for sql/01_user_gmv_capped.sql.")
    print("Do NOT edit sql/ files or load_purchases() parsing until Leo confirms.")
    print(bar)


def _best_effort_date_range(
    col: pl.Series,
) -> tuple[str | None, str | None, str | None]:
    """Try candidate formats on a Utf8 date column. Return (min, max, label) or (None, None, None)."""
    if col.dtype != pl.Utf8 or col.len() == 0:
        return None, None, None
    for fmt, label in _DATE_FORMAT_CANDIDATES:
        try:
            parsed = col.str.strptime(pl.Date, format=fmt, strict=False)
            non_null = parsed.drop_nulls()
            if non_null.len() / col.len() >= 0.95:
                return str(non_null.min()), str(non_null.max()), label
        except Exception:
            continue
    return None, None, None
