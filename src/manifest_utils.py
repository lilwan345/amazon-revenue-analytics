"""MANIFEST helpers — input hashing, row counts, manifest writer.

Used by Task 6.2 (init) and Task 6.11 (append Layer 1 outputs). The manifest
lives at the project root as MANIFEST.md; this module never writes anything
inside outputs/ -- only the top-level audit doc.

Per standard audit-trail practice: only hash INPUTS, never outputs. Parquet is
binary non-deterministic; hashing outputs would be wrong and would break reruns.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MANIFEST_PATH: Final[Path] = _PROJECT_ROOT / "MANIFEST.md"


def file_sha256(path: Path) -> str:
    """Return the SHA256 hex digest of a file (read whole file -- fine up to ~1 GB)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_size_mb(path: Path) -> float:
    return path.stat().st_size / 1024 / 1024


def count_lines(path: Path) -> int:
    """Count physical lines including the header line."""
    with path.open("rb") as f:
        return sum(1 for _ in f)


@dataclass(frozen=True)
class InputFile:
    label: str
    path: Path
    rows: int  # caller decides whether this is rows-incl-header or data-rows

    @property
    def rel_path(self) -> str:
        return self.path.relative_to(_PROJECT_ROOT).as_posix()


def init_manifest(inputs: list[InputFile]) -> Path:
    """Write the initial MANIFEST.md at project root. Returns the path written.

    Idempotent: overwrites any existing MANIFEST.md. Outputs section is left as
    a placeholder for Task 6.11 (Layer 1) and subsequent layers.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    input_rows = "\n".join(
        f"| {f.label} | `{f.rel_path}` | {f.rows:,} | {file_size_mb(f.path):.2f} MB "
        f"| `{file_sha256(f.path)}` |"
        for f in inputs
    )

    body = f"""# MANIFEST — Amazon Revenue Analytics

> Generated and updated incrementally by each layer's notebook.
> Last updated: {timestamp}
> Project commit: (uncommitted)

## Inputs

| File | Path | Rows | Size | SHA256 |
|---|---|---|---|---|
{input_rows}

Hashes computed via `hashlib.sha256(path.read_bytes()).hexdigest()` — see
`src/manifest_utils.py::file_sha256`.

## Outputs — Layer 1

*(Populated by Task 6.11 after Layer 1 outputs land in `outputs/tables/` and `outputs/figures/`.)*

## Expected Runtime (clean kernel, M-series Mac)

*(Populated by Task 6.11 after the full notebook runs once from a clean kernel.)*

## Reproducibility Notes

- **Random seeds:** All stochastic operations seed=42 (bootstrap, samplings, model training).
- **Dependency pinning:** See `requirements.txt`. Critical versions: DuckDB ≥ 1.0, Polars ≥ 1.0.
- **Python version:** 3.11+ (developed on 3.13.9).
- **Data versioning:** Source CSVs are not committed (gitignored). Hashes above let consumers verify they have the right file.
- **Determinism check:** Re-running the full notebook should produce byte-identical `user_gmv.parquet` columns; if not, investigate before proceeding.

## Changelog

| Date | Layer | Change |
|---|---|---|
| {timestamp[:10]} | 1 | Initial MANIFEST: input CSVs hashed during Task 6.2 sanity check |
"""

    MANIFEST_PATH.write_text(body)
    return MANIFEST_PATH
