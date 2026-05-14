from __future__ import annotations

import h5py
import numpy as np


def load_preferred_signal(channel_group: h5py.Group) -> np.ndarray:
    """Load adjusted signal when available, otherwise fall back to raw signal."""
    key = "signal_adjusted" if "signal_adjusted" in channel_group else "signal"
    return np.asarray(channel_group[key][:], dtype=np.float64)
