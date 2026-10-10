"""Pool-relative score normalization and blending (spec §8).

CLAP cosine scores cluster tightly (~0.0-0.5), so both the CLAP term and the
brain term are min-max normalized *within the candidate pool* before blending.
Without that, the brain term is numerically irrelevant — the spec's #1 trap.

Degenerate pools (every score equal) return DEGENERATE_NORM, never NaN.
"""

from __future__ import annotations

import numpy as np

from core.types import DEGENERATE_NORM

EPSILON = 1e-9


def minmax_normalize(values, *, degenerate: float = DEGENERATE_NORM) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return values
    low = float(values.min())
    high = float(values.max())
    if high - low < EPSILON:
        return np.full(values.shape, degenerate, dtype=np.float64)
    return (values - low) / (high - low)


def blend(clap_norm, brain_norm, alpha: float) -> np.ndarray:
    alpha = max(0.0, min(1.0, float(alpha)))
    return alpha * np.asarray(clap_norm, dtype=np.float64) + (1.0 - alpha) * np.asarray(
        brain_norm, dtype=np.float64
    )
