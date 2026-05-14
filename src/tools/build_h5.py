from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path
from typing import Dict

import h5py
import numpy as np

from core.modal_db import (
    DEFAULT_H5_PATH,
    DEFAULT_ORIGIN_DIR,
    DEFAULT_RENAME_LOG,
    discover_xls_files,
    read_xls_wave,
)


def load_rename_map(log_path: Path) -> Dict[str, str]:
    if not log_path.exists():
        return {}
    result: Dict[str, str] = {}
    with log_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            old_name = (row.get("old_name") or "").strip()
            new_name = (row.get("new_name") or "").strip()
            if old_name and new_name:
                result[new_name] = old_name
    return result


def compute_rfft(time_arr: np.ndarray, signal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(time_arr) < 2:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)
    dt_value = float(np.median(np.diff(time_arr)))
    if dt_value <= 0:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)
    freq = np.fft.rfftfreq(len(signal), d=dt_value).astype(np.float32)
    mag = np.abs(np.fft.rfft(signal)).astype(np.float32)
    return freq, mag


def write_h5(origin_dir: Path, h5_path: Path, rename_log_path: Path, compute_spectrum: bool) -> None:
    origin_dir.mkdir(parents=True, exist_ok=True)
    h5_path.parent.mkdir(parents=True, exist_ok=True)
    files = discover_xls_files(origin_dir)
    rename_map = load_rename_map(rename_log_path)

    with h5py.File(h5_path, "w") as h5:
        h5.attrs["schema_version"] = "1.0"
        h5.attrs["created_at"] = dt.datetime.now().isoformat(timespec="seconds")
        h5.attrs["source_dir"] = str(origin_dir)
        root = h5.create_group("experiments")

        for fp in files:
            original = rename_map.get(fp.name, fp.name)
            wave = read_xls_wave(fp, original_name=original)
            exp_group = root.create_group(wave.exp_id)
            exp_group.attrs["exp_id"] = wave.exp_id
            exp_group.attrs["original_filename"] = wave.original_filename
            exp_group.attrs["current_filename"] = wave.current_filename
            exp_group.attrs["sample_rate"] = wave.sample_rate
            exp_group.attrs["dt"] = wave.dt
            exp_group.attrs["duration"] = wave.duration
            exp_group.attrs["rows"] = wave.signals.shape[0]
            exp_group.attrs["channel_count"] = wave.signals.shape[1]
            exp_group.attrs["support_type"] = wave.support_type
            exp_group.attrs["component_id"] = wave.component_id
            exp_group.attrs["direction"] = wave.direction

            exp_group.create_dataset("time", data=wave.time, compression="gzip")
            exp_group.create_dataset(
                "channel_ids",
                data=np.asarray(wave.channel_labels, dtype="S16"),
                compression="gzip",
            )
            exp_group.create_dataset(
                "channel_brackets",
                data=np.asarray(wave.bracket_labels, dtype="S16"),
                compression="gzip",
            )

            channels = exp_group.create_group("channels")
            for i, ch_id in enumerate(wave.channel_labels):
                ch_group = channels.create_group(ch_id)
                ch_group.attrs["index"] = i + 1
                ch_group.attrs["label"] = wave.bracket_labels[i]
                signal = wave.signals[:, i]
                ch_group.create_dataset("signal", data=signal, compression="gzip")
                ch_group.create_dataset(
                    "freq_peaks",
                    data=np.zeros(0, dtype=np.float32),
                    maxshape=(None,),
                    compression="gzip",
                )
                if compute_spectrum:
                    freq, mag = compute_rfft(wave.time, signal)
                    spec = ch_group.create_group("spectrum")
                    spec.create_dataset("freq", data=freq, compression="gzip")
                    spec.create_dataset("mag", data=mag, compression="gzip")

    print(f"Wrote {len(files)} experiments into {h5_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build modal H5 database from XLS files.")
    parser.add_argument("--origin-dir", type=Path, default=DEFAULT_ORIGIN_DIR)
    parser.add_argument("--h5-path", type=Path, default=DEFAULT_H5_PATH)
    parser.add_argument("--rename-log", type=Path, default=DEFAULT_RENAME_LOG)
    parser.add_argument(
        "--skip-spectrum",
        action="store_true",
        help="Do not precompute and cache FFT spectrum.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    write_h5(
        origin_dir=args.origin_dir,
        h5_path=args.h5_path,
        rename_log_path=args.rename_log,
        compute_spectrum=not args.skip_spectrum,
    )


if __name__ == "__main__":
    main()
