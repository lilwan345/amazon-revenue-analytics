"""
Unit tests for the statistics helpers, the data-provenance preflight, and the
MANIFEST hash check. Synthetic inputs only; no Dataverse download needed.
"""

import hashlib

import numpy as np
import polars as pl
import pytest

import manifest_utils
import validate_data
from stats_utils import bootstrap_overindex_ci, compute_gini, lorenz_points


# ---------------------------------------------------------------- Gini / Lorenz

def test_gini_is_zero_when_everyone_spends_the_same():
    assert compute_gini(np.full(100, 42.0)) == pytest.approx(0.0)


def test_gini_when_one_household_has_everything():
    n = 10
    values = np.zeros(n)
    values[3] = 500.0
    assert compute_gini(values) == pytest.approx((n - 1) / n)


def test_gini_matches_the_mean_absolute_difference_definition():
    rng = np.random.default_rng(0)
    x = rng.lognormal(mean=3, sigma=1.2, size=400)
    mad = np.abs(x[:, None] - x[None, :]).mean()
    assert compute_gini(x) == pytest.approx(mad / (2 * x.mean()))


def test_gini_ignores_order_and_scale():
    x = np.array([1.0, 5.0, 2.0, 9.0])
    assert compute_gini(x) == pytest.approx(compute_gini(x[::-1] * 1000))


def test_gini_rejects_negative_values():
    with pytest.raises(ValueError):
        compute_gini(np.array([1.0, -1.0]))


def test_lorenz_curve_shape():
    x, y = lorenz_points(np.array([1.0, 1.0, 2.0, 6.0]))
    assert (x[0], y[0], x[-1], y[-1]) == (0.0, 0.0, 1.0, 1.0)
    assert y.tolist() == pytest.approx([0, 0.1, 0.2, 0.4, 1.0])
    assert np.all(y <= x + 1e-12)  # never above the equality line


# ------------------------------------------------------------ bootstrap over-index

def test_overindex_point_estimate_and_ci():
    rng = np.random.default_rng(1)
    n = 2000
    in_top = rng.random(n) < 0.1
    # The trait is 3x as common in the top group (30% vs ~10%), so over-index ~ +1.9
    has_trait = np.where(in_top, rng.random(n) < 0.30, rng.random(n) < 0.08)
    point, lo, hi = bootstrap_overindex_ci(in_top, has_trait)
    expected = has_trait[in_top].mean() / has_trait.mean() - 1
    assert point == pytest.approx(expected)
    assert lo < point < hi
    assert lo > 0  # clearly over-indexed, so the CI excludes zero


def test_overindex_bootstrap_is_reproducible():
    rng = np.random.default_rng(2)
    a, b = rng.random(500) < 0.1, rng.random(500) < 0.5
    assert bootstrap_overindex_ci(a, b) == bootstrap_overindex_ci(a, b)


def test_overindex_handles_an_absent_value():
    point, lo, hi = bootstrap_overindex_ci(np.array([True, False]), np.array([False, False]))
    assert np.isnan(point) and np.isnan(lo) and np.isnan(hi)


# ------------------------------------------------------------- provenance preflight

@pytest.fixture
def raw_files(tmp_path, monkeypatch):
    """Point validate_data at tiny files, with thresholds scaled down to match."""
    purchases, survey = tmp_path / "amazon-purchases.csv", tmp_path / "survey.csv"
    monkeypatch.setattr(validate_data, "PURCHASES_PATH", purchases)
    monkeypatch.setattr(validate_data, "SURVEY_PATH", survey)
    monkeypatch.setattr(validate_data, "EXPECTED_USERS", 4)
    monkeypatch.setattr(validate_data, "EXPECTED_MIN_PURCHASES", 10)
    monkeypatch.setattr(validate_data, "EXPECTED_PURCHASES_BYTES", 1)
    pl.DataFrame({"Survey ResponseID": ["a", "b", "c", "d"]}).write_csv(survey)

    def write_purchases(ids):
        pl.DataFrame({"Survey ResponseID": ids, "Order Date": ["2020-01-01"] * len(ids)}).write_csv(purchases)

    return write_purchases


def test_preflight_passes_on_a_complete_file(raw_files, capsys):
    raw_files(["a"] * 4 + ["b"] * 4 + ["c"] * 4 + ["d"] * 4)
    assert validate_data.validate() is True
    assert "PASS -- data looks complete" in capsys.readouterr().out


def test_preflight_catches_the_spreadsheet_row_limit(raw_files, monkeypatch, capsys):
    ids = ["a"] * 5 + ["b"] * 5 + ["c"] * 5 + ["d"] * 5
    monkeypatch.setattr(validate_data, "TRUNCATION_DATA_ROWS", len(ids))  # pretend 20 = 2^20 - 1
    raw_files(ids)
    assert validate_data.validate() is False
    assert "truncation signature" in capsys.readouterr().out


def test_preflight_catches_missing_households(raw_files, capsys):
    raw_files(["a"] * 6 + ["b"] * 6)  # c and d were cut off the end
    with pytest.raises(validate_data.DataIntegrityError):
        validate_data.validate(strict=True)
    assert "2 households have ZERO rows" in capsys.readouterr().out


def test_preflight_reports_missing_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(validate_data, "PURCHASES_PATH", tmp_path / "nope.csv")
    monkeypatch.setattr(validate_data, "SURVEY_PATH", tmp_path / "nope2.csv")
    assert validate_data.validate() is False
    assert "missing at" in capsys.readouterr().out


# ------------------------------------------------------------------ MANIFEST hashes

def test_manifest_lists_all_three_inputs():
    recorded = manifest_utils.recorded_hashes()
    assert set(recorded) == {"data/raw/amazon-purchases.csv", "data/raw/survey.csv",
                             "data/raw/fields.csv"}
    assert all(len(h) == 64 for h in recorded.values())


def test_file_sha256_matches_hashlib(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"hello" * 300_000)  # bigger than one 1 MiB read chunk
    assert manifest_utils.file_sha256(f) == hashlib.sha256(f.read_bytes()).hexdigest()


def test_verify_inputs_flags_changed_bytes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(manifest_utils, "_PROJECT_ROOT", tmp_path)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    for rel in manifest_utils.recorded_hashes():
        (tmp_path / rel).write_text("not the real data")
    with pytest.raises(RuntimeError, match="differ from MANIFEST"):
        manifest_utils.verify_inputs(strict=True)
    assert "MISMATCH" in capsys.readouterr().out
