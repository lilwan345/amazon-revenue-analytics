"""Statistical helpers used across Layer 1 analyses.

Provides:
  * compute_gini(values)              -- discrete Gini coefficient
  * lorenz_points(values)             -- (cum_share_users, cum_share_gmv) for plotting
  * bootstrap_overindex_ci(...)       -- 95% bootstrap CI on demographic over-index ratio
"""
from __future__ import annotations

import numpy as np


def bootstrap_overindex_ci(
    in_top_mask: np.ndarray,
    in_value_mask: np.ndarray,
    n_iter: int = 1000,
    seed: int = 42,
    ci_level: float = 0.95,
) -> tuple[float, float, float]:
    """95% bootstrap CI on the over-index ratio (pct_in_top / pct_in_sample - 1).

    Resamples *household indices* with replacement (preserving the joint
    distribution of "is in top decile" and "has this category value"), then
    recomputes the over-index ratio per iteration. Returns the percentile-based
    CI bounds plus the analytical point estimate.

    Args:
        in_top_mask:   boolean array, length n (n = number of households);
                       True if the household is in the top decile.
        in_value_mask: boolean array, length n; True if the household has the
                       category value being tested (e.g., income = "$150K+").
        n_iter: number of bootstrap resamples (default 1000).
        seed: numpy random seed (default 42, project-wide constant).
        ci_level: confidence level (default 0.95 -> 2.5th/97.5th percentiles).

    Returns:
        (point_estimate, ci_lower, ci_upper) as floats. Returns (nan, nan, nan)
        if the value mask is all False (no households have this value at all).
    """
    if in_top_mask.shape != in_value_mask.shape:
        raise ValueError("masks must have the same shape")
    if in_top_mask.dtype != bool or in_value_mask.dtype != bool:
        raise ValueError("masks must be boolean arrays")

    n = in_top_mask.size
    if n == 0 or in_value_mask.sum() == 0:
        return (float("nan"), float("nan"), float("nan"))

    # Analytical point estimate.
    p_value_given_top = in_value_mask[in_top_mask].mean() if in_top_mask.any() else 0.0
    p_value_in_sample = in_value_mask.mean()
    point = float(p_value_given_top / p_value_in_sample - 1.0)

    # Vectorised bootstrap: (n_iter, n) index matrix.
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_iter, n))
    top_b = in_top_mask[idx]
    val_b = in_value_mask[idx]

    val_and_top = (val_b & top_b).sum(axis=1).astype(np.float64)
    top_count = top_b.sum(axis=1).astype(np.float64)
    p_top_b = np.divide(val_and_top, top_count, out=np.zeros_like(val_and_top), where=top_count > 0)
    p_sample_b = val_b.mean(axis=1)

    ratios = np.where(p_sample_b > 0, p_top_b / p_sample_b - 1.0, np.nan)

    alpha = (1.0 - ci_level) / 2.0
    ci_lower = float(np.nanpercentile(ratios, alpha * 100))
    ci_upper = float(np.nanpercentile(ratios, (1.0 - alpha) * 100))
    return point, ci_lower, ci_upper


def compute_gini(values: np.ndarray) -> float:
    """Discrete Gini coefficient on a 1D array of non-negative values.

    Returns a value in [0, 1] where 0 = perfect equality and 1 = all value
    concentrated in a single household. Formula (Sen 1973, the algebraic form
    of the trapezoidal Lorenz area):

        G = sum_i ((2i - n - 1) * x_(i)) / (n * sum_i x_(i))

    where x_(i) is the i-th smallest value (1-indexed) and n is the population.
    """
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return 0.0
    if (arr < 0).any():
        raise ValueError("compute_gini expects non-negative values")
    sorted_v = np.sort(arr)
    n = sorted_v.size
    total = sorted_v.sum()
    if total == 0.0:
        return 0.0
    indices = np.arange(1, n + 1, dtype=np.float64)
    return float(((2 * indices - n - 1) * sorted_v).sum() / (n * total))


def lorenz_points(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (x, y) points for a Lorenz curve.

    x = cumulative share of population (0..1), with households sorted ascending
        by their value.
    y = cumulative share of total value (0..1).
    The curve includes (0, 0) and (1, 1) as endpoints, so the returned arrays
    have length n + 1.
    """
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return np.array([0.0, 1.0]), np.array([0.0, 1.0])
    if (arr < 0).any():
        raise ValueError("lorenz_points expects non-negative values")
    sorted_v = np.sort(arr)
    n = sorted_v.size
    total = sorted_v.sum()
    cum_share_users = np.linspace(0.0, 1.0, n + 1)
    if total == 0.0:
        # Degenerate: everyone has zero -- Lorenz collapses to the equality line.
        return cum_share_users, cum_share_users.copy()
    cum_share_value = np.concatenate(([0.0], np.cumsum(sorted_v) / total))
    return cum_share_users, cum_share_value
