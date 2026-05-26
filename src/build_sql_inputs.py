"""Generate the intermediate parquet files that SQL files 02+ depend on.

Post-clone reproducibility entry point. After this runs, every `sql/*.sql`
in this repo can be executed standalone via DuckDB (or any SQL client).

Run from the project root:

    python -m src.build_sql_inputs

Pipeline (dependency-ordered):

    sql/01_user_gmv_cohort_dated.sql  →  outputs/tables/user_gmv.parquet
    sql/02_decile_assignment.sql      →  outputs/tables/user_gmv_deciles.parquet
    sql/03_decile_contribution.sql    →  outputs/tables/decile_contribution.parquet
    sql/05_household_features.sql     →  outputs/tables/household_features.parquet
    sql/06_q3_outcome.sql             →  outputs/tables/q3_outcome.parquet

`sql/04_demographic_join.sql` and `sql/07_category_rollup.sql` produce
notebook-inline aggregations rather than persisted parquet intermediates,
so they are not re-written here — but both become runnable as a side-effect
of the registered `purchases`/`survey` views and the deciles parquet above.

This script intentionally only writes the SQL-derived parquets. The
Polars-extras that the notebooks compute (concentration_drivers,
demographic_overindex_with_ci, rar_per_household, etc.) come from the
notebooks themselves.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_loader import get_duckdb_conn  # noqa: E402

SQL = ROOT / "sql"
OUT = ROOT / "outputs" / "tables"

PIPELINE = [
    ("01_user_gmv_cohort_dated.sql", "user_gmv.parquet"),
    ("02_decile_assignment.sql",     "user_gmv_deciles.parquet"),
    ("03_decile_contribution.sql",   "decile_contribution.parquet"),
    ("05_household_features.sql",    "household_features.parquet"),
    ("06_q3_outcome.sql",            "q3_outcome.parquet"),
]


def _preflight() -> None:
    """Fail fast with an actionable message if raw CSVs are missing."""
    raw = ROOT / "data" / "raw"
    needed = ["amazon-purchases.csv", "survey.csv"]
    missing = [f for f in needed if not (raw / f).exists()]
    if missing:
        sys.exit(
            f"ERROR: missing raw input(s) under data/raw/: {', '.join(missing)}.\n"
            f"Place the MIT Media Lab Amazon dataset CSVs there (paths + SHA-256\n"
            f"hashes are listed in MANIFEST.md) and re-run."
        )


def main() -> None:
    _preflight()
    OUT.mkdir(parents=True, exist_ok=True)
    con = get_duckdb_conn()

    print("Building SQL intermediate parquets in dependency order:")
    for sql_file, out_name in PIPELINE:
        sql_text = (SQL / sql_file).read_text()
        df = con.sql(sql_text).pl()
        out_path = OUT / out_name
        df.write_parquet(out_path, compression="zstd")
        size_kb = out_path.stat().st_size / 1024
        print(f"  {sql_file:42s} → {out_name:32s}  {df.height:>5,} rows · {size_kb:>6.1f} KB")

    con.close()
    print()
    print("Done. Every sql/*.sql in this repo is now runnable standalone via DuckDB:")
    print(f"  duckdb -c \"$(cat {SQL.relative_to(ROOT)}/02_decile_assignment.sql)\"")


if __name__ == "__main__":
    main()
