"""Batch damping extraction with parallel read/compute and single-writer H5 commit."""

from __future__ import annotations

import argparse
import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import h5py
import numpy as np

from damping.damping_core import CycleDamping, DampingResult, compute_cycle_damping, extract_damping_single
from damping.damping_h5_schema import _write_damping_results_to_group
from damping.signal_access import load_preferred_signal
from core.modal_db import DEFAULT_H5_PATH

LOGGER = logging.getLogger(__name__)


def _decode_arr(arr: np.ndarray) -> List[str]:
    out: List[str] = []
    for x in arr:
        if isinstance(x, bytes):
            out.append(x.decode("utf-8", errors="ignore"))
        else:
            out.append(str(x))
    return out


def _extract_mode_freq_pairs(exp_group: h5py.Group) -> List[Tuple[str, float]]:
    if "modal_freq_modes" in exp_group and "modal_freq_values" in exp_group:
        modes = _decode_arr(exp_group["modal_freq_modes"][:])
        vals = [float(v) for v in np.asarray(exp_group["modal_freq_values"][:], dtype=np.float64)]
        pairs = list(zip(modes, vals))
    elif "freq_peaks" in exp_group:
        vals = [float(v) for v in np.asarray(exp_group["freq_peaks"][:], dtype=np.float64)]
        pairs = [("unknown", v) for v in vals]
    else:
        pairs = []

    seen = set()
    uniq: List[Tuple[str, float]] = []
    for m, f in pairs:
        key = (m, round(float(f), 8))
        if key in seen:
            continue
        seen.add(key)
        uniq.append((m, float(f)))
    return uniq


def _compute_experiment_task(
    h5_path_str: str,
    exp_id: str,
    channel_filter: List[str] | None,
    bandwidth_pct: float,
    butter_order: int,
    min_cycles: int,
) -> dict:
    """Worker task: read one experiment (read-only), compute damping outputs."""
    with h5py.File(h5_path_str, "r") as h5:
        exp_group = h5["experiments"][exp_id]
        mode_freq_pairs = _extract_mode_freq_pairs(exp_group)
        time_arr = np.asarray(exp_group["time"][:], dtype=np.float64)
        fs = float(exp_group.attrs.get("sample_rate", 0.0))
        if fs <= 0 and time_arr.size >= 2:
            dt = float(np.median(np.diff(time_arr)))
            fs = 1.0 / dt if dt > 0 else 0.0
        channel_ids = _decode_arr(exp_group["channel_ids"][:])
        if channel_filter:
            chf = set(channel_filter)
            channel_ids = [c for c in channel_ids if c in chf]
        channels_group = exp_group["channels"]

        results: List[DampingResult] = []
        cycle_data: Dict[str, List[CycleDamping]] = {}
        for ch_id in channel_ids:
            sig = np.asarray(load_preferred_signal(channels_group[ch_id]), dtype=np.float64)
            for mode, freq in mode_freq_pairs:
                r = extract_damping_single(
                    time=time_arr,
                    signal=sig,
                    freq_target=freq,
                    channel_id=ch_id,
                    mode=mode,
                    fs=fs,
                    bandwidth_pct=bandwidth_pct,
                    butter_order=butter_order,
                    min_cycles=min_cycles,
                )
                results.append(r)
                cycle_key = f"{ch_id}_{mode}"
                if r.valid:
                    cycle_data[cycle_key] = compute_cycle_damping(
                        envelope_time=r.envelope_time,
                        envelope_amplitude=r.envelope_amplitude,
                        freq_target=freq,
                    )
                else:
                    cycle_data[cycle_key] = []
                # minimize IPC payload size: these arrays are not needed for H5 write schema
                r.envelope_time = np.asarray([], dtype=np.float64)
                r.envelope_amplitude = np.asarray([], dtype=np.float64)

    return {"exp_id": exp_id, "results": results, "cycle_data": cycle_data}


def batch_extract_damping(
    h5_path: Path,
    bandwidth_pct: float = 15.0,
    butter_order: int = 4,
    min_cycles: int = 5,
    exp_filter: List[str] | None = None,
    channel_filter: List[str] | None = None,
    overwrite: bool = False,
    progress_callback: Callable[[str, int, int], None] | None = None,
    workers: int | None = None,
) -> dict:
    """Parallel read/compute, single-writer H5 commit."""
    processed = 0
    skipped = 0
    skipped_ids: List[str] = []
    total_results = 0
    valid_results = 0
    invalid_results = 0

    # Pre-scan: decide jobs and immediate skips
    with h5py.File(h5_path, "r") as h5:
        experiments = h5["experiments"]
        exp_ids = sorted(experiments.keys())
        if exp_filter:
            filt = set(exp_filter)
            exp_ids = [eid for eid in exp_ids if eid in filt]

        total_events = len(exp_ids)
        completed_events = 0
        jobs: List[str] = []
        for exp_id in exp_ids:
            exp_group = experiments[exp_id]
            if "damping" in exp_group and not overwrite:
                skipped += 1
                skipped_ids.append(exp_id)
                completed_events += 1
                if progress_callback:
                    progress_callback(exp_id, completed_events, total_events)
                continue
            mode_freq_pairs = _extract_mode_freq_pairs(exp_group)
            if not mode_freq_pairs:
                skipped += 1
                skipped_ids.append(exp_id)
                completed_events += 1
                if progress_callback:
                    progress_callback(exp_id, completed_events, total_events)
                continue
            time_arr = np.asarray(exp_group["time"][:], dtype=np.float64)
            fs = float(exp_group.attrs.get("sample_rate", 0.0))
            if fs <= 0 and time_arr.size >= 2:
                dt = float(np.median(np.diff(time_arr)))
                fs = 1.0 / dt if dt > 0 else 0.0
            if fs <= 0:
                skipped += 1
                skipped_ids.append(exp_id)
                completed_events += 1
                if progress_callback:
                    progress_callback(exp_id, completed_events, total_events)
                continue
            channel_ids = _decode_arr(exp_group["channel_ids"][:])
            if channel_filter:
                chf = set(channel_filter)
                channel_ids = [c for c in channel_ids if c in chf]
            if not channel_ids:
                skipped += 1
                skipped_ids.append(exp_id)
                completed_events += 1
                if progress_callback:
                    progress_callback(exp_id, completed_events, total_events)
                continue
            jobs.append(exp_id)

    params = {
        "bandwidth_pct": float(bandwidth_pct),
        "butter_order": int(butter_order),
        "min_cycles": int(min_cycles),
    }
    h5_path_str = str(h5_path)

    # Phase 1: parallel read + compute (no writer open)
    if workers is None:
        cpu_n = os.cpu_count() or 2
        workers = max(1, cpu_n - 1)
    workers = max(1, int(workers))

    computed_payloads: Dict[str, dict] = {}
    if workers == 1:
        for exp_id in jobs:
            payload = _compute_experiment_task(
                h5_path_str=h5_path_str,
                exp_id=exp_id,
                channel_filter=channel_filter,
                bandwidth_pct=bandwidth_pct,
                butter_order=butter_order,
                min_cycles=min_cycles,
            )
            computed_payloads[exp_id] = payload
            completed_events += 1
            if progress_callback:
                progress_callback(exp_id, completed_events, total_events)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            fut_map = {
                ex.submit(
                    _compute_experiment_task,
                    h5_path_str,
                    exp_id,
                    channel_filter,
                    bandwidth_pct,
                    butter_order,
                    min_cycles,
                ): exp_id
                for exp_id in jobs
            }
            for fut in as_completed(fut_map):
                exp_id = fut_map[fut]
                payload = fut.result()
                computed_payloads[exp_id] = payload
                completed_events += 1
                if progress_callback:
                    progress_callback(exp_id, completed_events, total_events)

    # Phase 2: single-writer commit
    with h5py.File(h5_path, "a") as h5w:
        for exp_id in jobs:
            payload = computed_payloads.get(exp_id)
            if payload is None:
                continue
            exp_group = h5w["experiments"][exp_id]
            _write_damping_results_to_group(exp_group, payload["results"], payload["cycle_data"], params)
            processed += 1
            total_results += len(payload["results"])
            valid_results += sum(1 for r in payload["results"] if r.valid)
            invalid_results += sum(1 for r in payload["results"] if not r.valid)

    return {
        "processed": processed,
        "skipped": skipped,
        "skipped_ids": skipped_ids,
        "total_results": total_results,
        "valid_results": valid_results,
        "invalid_results": invalid_results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch damping extraction into H5.")
    parser.add_argument("--h5-path", type=Path, default=DEFAULT_H5_PATH)
    parser.add_argument("--bandwidth-pct", type=float, default=15.0)
    parser.add_argument("--butter-order", type=int, default=4)
    parser.add_argument("--min-cycles", type=int, default=5)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    summary = batch_extract_damping(
        h5_path=args.h5_path,
        bandwidth_pct=args.bandwidth_pct,
        butter_order=args.butter_order,
        min_cycles=args.min_cycles,
        overwrite=args.overwrite,
        workers=args.workers,
    )
    LOGGER.info("Batch summary: %s", summary)


if __name__ == "__main__":
    main()
