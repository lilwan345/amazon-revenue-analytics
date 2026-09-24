"""MANIFEST helpers: input hashing and a read-only check against MANIFEST.md.

MANIFEST.md is a committed document (inputs, output schemas, runtime, changelog).
Notebooks never rewrite it; they call `verify_inputs()` to confirm the raw CSVs
are byte-identical to the ones the documented results came from.

Per standard audit-trail practice: only hash INPUTS, never outputs. Parquet is
binary non-deterministic; hashing outputs would be wrong and would break reruns.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Final

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MANIFEST_PATH: Final[Path] = _PROJECT_ROOT / "MANIFEST.md"

# One row of the MANIFEST "Inputs" table:
# | label | `data/raw/x.csv` | rows | size | `<64-hex sha256>` |
_INPUT_ROW: Final[re.Pattern[str]] = re.compile(
    r"^\|[^|]*\| `([^`]+)` \|[^|]*\|[^|]*\| `([0-9a-f]{64})` \|$", flags=re.M
)


def file_sha256(path: Path) -> str:
    """SHA256 hex digest of a file, streamed (same digest as `shasum -a 256`)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def recorded_hashes() -> dict[str, str]:
    """Map each input path in MANIFEST.md's Inputs table to its recorded SHA256."""
    return dict(_INPUT_ROW.findall(MANIFEST_PATH.read_text()))


def verify_inputs(strict: bool = True) -> bool:
    """Recompute each raw input's SHA256 and compare it with MANIFEST.md.

    Prints one line per input. With strict=True (the notebook default) a missing
    or changed file raises, so a run on different bytes cannot silently proceed.
    """
    recorded = recorded_hashes()
    if not recorded:
        raise RuntimeError(f"no input hashes found in {MANIFEST_PATH.name}")
    ok = True
    for rel, expected in recorded.items():
        path = _PROJECT_ROOT / rel
        if not path.exists():
            status = "MISSING"
        else:
            status = "ok" if file_sha256(path) == expected else "MISMATCH"
        ok &= status == "ok"
        print(f"  [{status:>8}] {rel}  sha256={expected[:16]}...")
    if strict and not ok:
        raise RuntimeError(
            "raw inputs differ from MANIFEST.md -- results would not match the documented run"
        )
    return ok
