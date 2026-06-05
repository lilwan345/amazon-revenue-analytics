"""Data-provenance preflight for Amazon Revenue Analytics.

Run this BEFORE any layer notebook. It answers one question the rest of the
pipeline takes on faith: *is the raw purchases file the complete published
dataset, or a silently truncated copy?*

Why this exists: the source file `amazon-purchases.csv` is a CSV. If it is ever
opened and re-saved in Excel / Google Sheets / Numbers, those tools cap a sheet
at 1,048,576 rows (2^20) and drop everything past it WITHOUT warning. Because the
file is grouped by `Survey ResponseID`, such a truncation does not clip a clean
date tail -- it deletes whole households from the end of the user list, biasing
every concentration / revenue-at-risk / growth figure downstream.

Ground truth (Open e-commerce 1.0; Berke, Calacci, Mahari, Yabe, Larson,
Pentland. *Scientific Data*, 2024; Harvard Dataverse doi:10.7910/DVN/YGLYDY):
  * 5,027 surveyed U.S. participants
  * > 1.8 million purchase transactions
  * amazon-purchases.csv published size ~= 313 MB (Dataverse file id 7616235)

Usage:
    python src/validate_data.py          # prints report, exits 1 if data is bad
    from validate_data import validate    # validate(strict=True) raises on failure
"""
from __future__ import annotations

from pathlib import Path
from typing import Final

import polars as pl

# Path anchors -- mirror data_loader.py so this runs standalone as a preflight,
# without importing the rest of src (project root is two levels above this file).
_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_DATA_DIR: Final[Path] = _PROJECT_ROOT / "data" / "raw"
SURVEY_PATH: Final[Path] = _DATA_DIR / "survey.csv"
PURCHASES_PATH: Final[Path] = _DATA_DIR / "amazon-purchases.csv"

# Published ground truth (see module docstring for citation).
EXPECTED_USERS: Final[int] = 5_027
EXPECTED_MIN_PURCHASES: Final[int] = 1_800_000
EXPECTED_PURCHASES_BYTES: Final[int] = 313_070_173  # Dataverse file 7616235

# The spreadsheet truncation tell: a max-row export lands at exactly 2^20 physical
# lines = 1 header + (2^20 - 1) data rows.
SPREADSHEET_ROW_CAP: Final[int] = 1_048_576
TRUNCATION_DATA_ROWS: Final[int] = SPREADSHEET_ROW_CAP - 1  # 1,048,575

# Where to re-acquire a clean copy if validation fails.
DATAVERSE_DOI: Final[str] = "doi:10.7910/DVN/YGLYDY"
DATAVERSE_PURCHASES_URL: Final[str] = (
    "https://dataverse.harvard.edu/api/access/datafile/7616235"
)
DATAVERSE_SURVEY_URL: Final[str] = (
    "https://dataverse.harvard.edu/api/access/datafile/7616231"
)


class DataIntegrityError(RuntimeError):
    """Raised by validate(strict=True) when the raw data fails a hard check."""


def _report(checks: list[tuple[str, str, str]]) -> bool:
    """Print a status table. Each check is (level, name, detail). Return True if no FAIL."""
    bar = "=" * 72
    print(bar)
    print("Data-provenance preflight -- amazon-purchases.csv / survey.csv")
    print(bar)
    icon = {"PASS": "  ok ", "WARN": " warn", "FAIL": "FAIL "}
    for level, name, detail in checks:
        print(f"[{icon[level]}] {name}")
        print(f"          {detail}")
    ok = not any(level == "FAIL" for level, _, _ in checks)
    print(bar)
    print("VERDICT: " + ("PASS -- data looks complete." if ok else "FAIL -- data is incomplete/truncated."))
    if not ok:
        print(
            "\nRe-acquire the ORIGINAL bytes (do NOT open the CSV in Excel/Sheets/Numbers,\n"
            "which re-truncates on save). From Harvard Dataverse " + DATAVERSE_DOI + ":\n"
            f'  curl -L "{DATAVERSE_PURCHASES_URL}" -o "{PURCHASES_PATH}"\n'
            f'  curl -L "{DATAVERSE_SURVEY_URL}"    -o "{SURVEY_PATH}"\n'
            "Then re-run this preflight; it should print PASS."
        )
    print(bar)
    return ok


def validate(strict: bool = False) -> bool:
    """Validate the raw data files. Print a report; return True iff all hard checks pass.

    Args:
        strict: If True, raise DataIntegrityError instead of returning False on failure.
                Use strict=True at the top of a notebook so the run aborts on bad data.
    """
    checks: list[tuple[str, str, str]] = []

    # Files present?
    for label, path in (("survey.csv", SURVEY_PATH), ("amazon-purchases.csv", PURCHASES_PATH)):
        if not path.exists():
            checks.append(("FAIL", f"{label} present", f"missing at {path}"))
    if any(level == "FAIL" for level, _, _ in checks):
        ok = _report(checks)
        if strict and not ok:
            raise DataIntegrityError("raw data files missing")
        return ok

    # Load only the household-id column of the purchases file (cheap; ~1M short strings).
    ids = pl.read_csv(PURCHASES_PATH, columns=["Survey ResponseID"])["Survey ResponseID"]
    n_rows = ids.len()
    n_users = ids.n_unique()
    survey_users = pl.read_csv(SURVEY_PATH)["Survey ResponseID"].n_unique()
    size_bytes = PURCHASES_PATH.stat().st_size

    # 1) The 2^20-1 truncation signature -- the single most important check.
    if n_rows == TRUNCATION_DATA_ROWS:
        checks.append((
            "FAIL", "row count != spreadsheet limit",
            f"{n_rows:,} data rows == 2^20 - 1 exactly: the Excel/Sheets/Numbers "
            f"truncation signature. The file was almost certainly clipped on a "
            f"spreadsheet save and is NOT the full dataset.",
        ))
    elif n_rows < EXPECTED_MIN_PURCHASES:
        checks.append((
            "FAIL", "purchase count >= published total",
            f"{n_rows:,} data rows < expected >{EXPECTED_MIN_PURCHASES:,} "
            f"(published as '>1.8M purchases'). File looks incomplete.",
        ))
    else:
        checks.append((
            "PASS", "purchase count >= published total",
            f"{n_rows:,} data rows (>= expected {EXPECTED_MIN_PURCHASES:,}).",
        ))

    # 2) All surveyed users represented? Truncation drops whole users off the tail.
    if n_users < survey_users:
        checks.append((
            "FAIL", "all surveyed households present",
            f"only {n_users:,} of {survey_users:,} surveyed households appear in "
            f"purchases ({survey_users - n_users:,} households have ZERO rows). "
            f"Any analytic 'cohort size' is then an artifact of the cutoff, not a "
            f"sampling decision.",
        ))
    else:
        checks.append((
            "PASS", "all surveyed households present",
            f"{n_users:,} households in purchases vs {survey_users:,} surveyed.",
        ))

    # 3) Survey row count sanity (should be the full panel).
    level = "PASS" if survey_users == EXPECTED_USERS else "WARN"
    checks.append((
        level, "survey panel size",
        f"{survey_users:,} surveyed households (expected {EXPECTED_USERS:,}).",
    ))

    # 4) File size sanity -- a coarse, fast corroborating signal.
    if size_bytes < EXPECTED_PURCHASES_BYTES * 0.8:
        checks.append((
            "WARN", "file size near published",
            f"{size_bytes / 1e6:.0f} MB vs published ~{EXPECTED_PURCHASES_BYTES / 1e6:.0f} MB "
            f"-- noticeably smaller, consistent with missing rows.",
        ))
    else:
        checks.append((
            "PASS", "file size near published",
            f"{size_bytes / 1e6:.0f} MB (~{EXPECTED_PURCHASES_BYTES / 1e6:.0f} MB published).",
        ))

    # 5) Grouping diagnostic (not pass/fail): explains WHAT a truncation removed.
    #    If rows are grouped by household, #contiguous-blocks == #distinct-users.
    blocks = 1 + (ids != ids.shift(1)).sum()  # transitions + 1
    grouped = blocks == n_users
    checks.append((
        "PASS", "row ordering (diagnostic)",
        (f"grouped by household ({blocks:,} contiguous blocks == {n_users:,} users): "
         f"a truncation removes whole households off the end of the user list."
         if grouped else
         f"not strictly grouped by household ({blocks:,} blocks vs {n_users:,} users)."),
    ))

    ok = _report(checks)
    if strict and not ok:
        raise DataIntegrityError(
            "raw purchases data failed provenance validation -- see report above"
        )
    return ok


def main() -> None:
    import sys

    sys.exit(0 if validate(strict=False) else 1)


if __name__ == "__main__":
    main()
