# Make `src` importable as a package, and its modules importable the way the
# scripts import each other (robustness_checks does `from data_loader import ...`).
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
