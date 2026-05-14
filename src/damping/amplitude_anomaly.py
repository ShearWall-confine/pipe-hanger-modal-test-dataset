from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable
import re

import h5py
import numpy as np


LOW_ROW_MAX_THRESHOLD = 20.0
EXEMPT_ROW_INDEX = 1


def _decode_arr(arr) -> list[str]:
    out: list[str] = []
    for x in arr:
        if isinstance(x, bytes):
            out.append(x.decode("utf-8", errors="ignore"))
        else:
            out.append(str(x))
    return out


def _parse_row_index(label: str) -> int | None:
    m = re.match(r"\s*(\d+)\s*#", str(label))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


@lru_cache(maxsize=8)
def load_low_amplitude_row_channels(h5_path_str: str) -> dict[str, set[str]]:
    h5_path = Path(h5_path_str)
    flagged: dict[str, set[str]] = {}
    with h5py.File(h5_path, "r") as h5:
        for exp_id, group in h5["experiments"].items():
            if "channel_ids" not in group or "channel_brackets" not in group or "channels" not in group:
                continue
            ch_ids = _decode_arr(group["channel_ids"][:])
            ch_labels = _decode_arr(group["channel_brackets"][:])
            row_channels: dict[int, list[str]] = {}
            row_max_abs: dict[int, float] = {}
            for ch_id, label in zip(ch_ids, ch_labels):
                row_idx = _parse_row_index(label)
                if row_idx is None:
                    continue
                sig = np.asarray(group["channels"][ch_id]["signal"][:], dtype=np.float64)
                finite = np.abs(sig[np.isfinite(sig)])
                max_abs = float(np.max(finite)) if finite.size else 0.0
                row_channels.setdefault(row_idx, []).append(ch_id)
                row_max_abs[row_idx] = max(row_max_abs.get(row_idx, 0.0), max_abs)
            for row_idx, max_abs in row_max_abs.items():
                if row_idx == EXEMPT_ROW_INDEX:
                    continue
                if max_abs < LOW_ROW_MAX_THRESHOLD:
                    flagged.setdefault(exp_id, set()).update(row_channels.get(row_idx, []))
    return flagged


def is_amplitude_anomalous(
    h5_path: Path,
    exp_id: str,
    channel_id: str | None = None,
) -> bool:
    low_row_flags = load_low_amplitude_row_channels(str(h5_path.resolve()))
    if channel_id:
        return channel_id in low_row_flags.get(exp_id, set())
    return bool(low_row_flags.get(exp_id))


def filter_result_rows_for_amplitude(rows: Iterable[dict], h5_path: Path) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        exp_id = str(row.get("exp_id", ""))
        channel_id = str(row.get("channel_id", ""))
        if is_amplitude_anomalous(h5_path, exp_id, channel_id):
            continue
        out.append(row)
    return out
