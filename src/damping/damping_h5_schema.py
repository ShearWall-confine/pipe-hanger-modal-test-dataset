"""H5 schema helpers for damping analysis results."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Dict, List

import h5py
import numpy as np

from damping.damping_core import CycleDamping, DampingResult

DAMPING_RESULTS_DTYPE = np.dtype(
    [
        ("channel_id", "S8"),
        ("mode", "S20"),
        ("freq_target", "f8"),
        ("zeta_hilbert", "f8"),
        ("zeta_log_dec", "f8"),
        ("r_squared", "f8"),
        ("band_rejection_db", "f8"),
        ("peak_count", "i4"),
        ("t_start", "f8"),
        ("t_end", "f8"),
        ("amplitude_at_start", "f8"),
        ("valid", "?"),
        ("reject_reason", "S40"),
        ("drift_ratio", "f8"),
        ("drift_slope", "f8"),
        ("drift_amplitude_range", "f8"),
        ("drift_r_squared", "f8"),
        ("drift_valid", "?"),
    ]
)

CYCLE_DTYPE = np.dtype([("amplitude", "f8"), ("zeta_local", "f8"), ("t_mid", "f8")])


def _decode_str(v: bytes | str) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="ignore")
    return str(v)


def _ensure_damping_group(exp_group: h5py.Group, params: dict) -> h5py.Group:
    if "damping" in exp_group:
        del exp_group["damping"]
    damping = exp_group.create_group("damping")
    damping.attrs["method"] = "butterworth_hilbert_v2"
    damping.attrs["drift_metric"] = "normalized_freq_amplitude_slope = slope / freq_target"
    damping.attrs["analyzed_at"] = dt.datetime.now().isoformat(timespec="seconds")
    for k, v in params.items():
        damping.attrs[str(k)] = v
    return damping


def _write_damping_results_to_group(
    exp_group: h5py.Group,
    results: List[DampingResult],
    cycle_data: Dict[str, List[CycleDamping]],
    params: dict,
) -> None:
    damping = _ensure_damping_group(exp_group, params)

    rows = np.zeros(len(results), dtype=DAMPING_RESULTS_DTYPE)
    for i, r in enumerate(results):
        rows[i] = (
            r.channel_id.encode("utf-8"),
            r.mode.encode("utf-8"),
            float(r.freq_target),
            float(r.zeta_hilbert),
            float(r.zeta_log_dec),
            float(r.r_squared),
            float(r.band_rejection_db),
            int(r.peak_count),
            float(r.t_start),
            float(r.t_end),
            float(r.amplitude_at_start),
            bool(r.valid),
            str(r.reject_reason).encode("utf-8"),
            float(r.backbone.drift_ratio),
            float(r.backbone.drift_slope),
            float(r.backbone.amplitude_range),
            float(r.backbone.r_squared),
            bool(r.backbone.valid),
        )
    damping.create_dataset("results", data=rows, compression="gzip")

    cycle_group = damping.create_group("cycle_damping")

    for r in results:
        key = f"{r.channel_id}_{r.mode}"
        cycles = cycle_data.get(key, [])
        cycle_arr = np.zeros(len(cycles), dtype=CYCLE_DTYPE)
        for i, c in enumerate(cycles):
            cycle_arr[i] = (float(c.amplitude), float(c.zeta_local), float(c.t_mid))
        cycle_group.create_dataset(key, data=cycle_arr, compression="gzip")


def write_damping_results(
    h5_path: Path,
    exp_id: str,
    results: List[DampingResult],
    cycle_data: Dict[str, List[CycleDamping]],
    params: dict,
) -> None:
    """Write damping extraction outputs into /experiments/{exp_id}/damping."""
    with h5py.File(h5_path, "a") as h5:
        exp_group = h5["experiments"][exp_id]
        _write_damping_results_to_group(exp_group, results, cycle_data, params)


def read_damping_results(
    h5_path: Path,
    exp_id: str | None = None,
) -> Dict[str, List[dict]]:
    """Read damping compound rows with experiment metadata."""
    data: Dict[str, List[dict]] = {}
    with h5py.File(h5_path, "r") as h5:
        experiments = h5["experiments"]
        exp_ids = [exp_id] if exp_id else sorted(experiments.keys())
        for eid in exp_ids:
            if eid not in experiments:
                continue
            exp_group = experiments[eid]
            if "damping" not in exp_group or "results" not in exp_group["damping"]:
                data[eid] = []
                continue
            rows = exp_group["damping"]["results"][:]
            exp_meta = {
                "support_type": str(exp_group.attrs.get("support_type", "")),
                "component_id": str(exp_group.attrs.get("component_id", "")),
                "direction": str(exp_group.attrs.get("direction", "")),
            }
            out_rows: List[dict] = []
            for r in rows:
                item = {
                    "exp_id": str(eid),
                    "channel_id": _decode_str(r["channel_id"]),
                    "mode": _decode_str(r["mode"]),
                    "freq_target": float(r["freq_target"]),
                    "zeta_hilbert": float(r["zeta_hilbert"]),
                    "zeta_log_dec": float(r["zeta_log_dec"]),
                    "r_squared": float(r["r_squared"]),
                    "band_rejection_db": float(r["band_rejection_db"]),
                    "peak_count": int(r["peak_count"]),
                    "t_start": float(r["t_start"]),
                    "t_end": float(r["t_end"]),
                    "amplitude_at_start": float(r["amplitude_at_start"]),
                    "valid": bool(r["valid"]),
                    "reject_reason": _decode_str(r["reject_reason"]),
                    "drift_ratio": float(r["drift_ratio"]),
                    "drift_slope": float(r["drift_slope"]),
                    "drift_amplitude_range": float(r["drift_amplitude_range"]),
                    "drift_r_squared": float(r["drift_r_squared"]),
                    "drift_valid": bool(r["drift_valid"]),
                }
                item.update(exp_meta)
                out_rows.append(item)
            data[eid] = out_rows
    return data


def read_cycle_damping(
    h5_path: Path,
    exp_id: str,
    channel_id: str,
    mode: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Return cycle damping arrays: (amplitude, zeta_local, t_mid)."""
    key = f"{channel_id}_{mode}"
    with h5py.File(h5_path, "r") as h5:
        path = f"experiments/{exp_id}/damping/cycle_damping/{key}"
        if path not in h5:
            return None
        ds = h5[path][:]
        return ds["amplitude"], ds["zeta_local"], ds["t_mid"]
