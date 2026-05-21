"""Finance-clean matplotlib styling for Layer 1 visualizations.

Helpers here are reused across the Lorenz curve, the decile bar
chart, and any later figure. Keep this module style-only -- do not
embed chart logic; chart logic belongs in the notebook so each layer's figure
can be read end-to-end.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# Locked palette so every figure carries the same visual brand.
COLOR_PRIMARY = "#1f4e79"   # deep blue   -- main data line / bars
COLOR_ACCENT = "#c0392b"    # deep red    -- callout points / highlights
COLOR_NEUTRAL = "#7f8c8d"   # mid gray    -- reference lines, annotations
COLOR_LIGHT = "#cccccc"     # light gray  -- axis spines
COLOR_TEXT = "#2c3e50"      # dark slate  -- labels
COLOR_MUTED = "#555555"     # mid gray    -- subtitles, tick labels


def set_finance_style() -> None:
    """Apply finance-clean rcParams: white background, no chart junk, subtle grid."""
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": COLOR_LIGHT,
        "axes.labelcolor": COLOR_TEXT,
        "axes.titlecolor": COLOR_PRIMARY,
        "axes.titleweight": "bold",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": False,
        "xtick.color": COLOR_MUTED,
        "ytick.color": COLOR_MUTED,
        "font.family": "sans-serif",
        "font.size": 10,
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
        "savefig.dpi": 300,
    })


def dollar_millions_formatter() -> FuncFormatter:
    """Matplotlib axis formatter that prints values as `$X.XM`."""
    return FuncFormatter(lambda x, _: f"${x / 1_000_000:.1f}M")
