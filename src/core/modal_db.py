from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import xlrd


DEFAULT_BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ORIGIN_DIR = DEFAULT_BASE_DIR / "data" / "raw_xls"
DEFAULT_PROCESSED_DIR = DEFAULT_BASE_DIR / "data" / "derived"
DEFAULT_H5_PATH = DEFAULT_PROCESSED_DIR / "modal_db.h5"
DEFAULT_METADATA_DIR = DEFAULT_BASE_DIR / "data" / "metadata"
DEFAULT_RENAME_LOG = DEFAULT_METADATA_DIR / "rename_log.csv"
DEFAULT_FREQ_IMPORT_LOG = DEFAULT_METADATA_DIR / "freq_import_log.json"

CHANNEL_COUNT = 20
TIME_COL_IDX = 3
SIGNAL_START_COL_IDX = 4
SIGNAL_END_COL_IDX = 24

DIRECTION_TOKENS = {"AA", "AR", "RA", "RR", "A", "R"}
COMPONENT_PATTERN = re.compile(r"^(CA|TB|CSBD|CSB)_.+")


@dataclass
class WaveData:
    exp_id: str
    original_filename: str
    current_filename: str
    sample_rate: float
    dt: float
    duration: float
    time: np.ndarray
    signals: np.ndarray
    channel_labels: List[str]
    bracket_labels: List[str]
    support_type: str
    component_id: str
    direction: str


def normalize_exp_id_from_stem(stem: str) -> str:
    parts = stem.split("_")
    direction = ""
    for idx, token in enumerate(parts):
        if token in DIRECTION_TOKENS:
            direction = token
            component_parts = parts[:idx] + parts[idx + 1 :]
            component = "_".join(component_parts)
            return f"{component}_{direction}" if direction else component
    return stem


def parse_component_and_direction(exp_id: str) -> tuple[str, str, str]:
    parts = exp_id.split("_")
    if not parts:
        return "", exp_id, ""
    support_type = parts[0]
    direction = ""
    for token in reversed(parts):
        if token in DIRECTION_TOKENS:
            direction = token
            break
    if direction:
        idx = parts.index(direction)
        component_parts = parts[:idx] + parts[idx + 1 :]
        component_id = "_".join(component_parts)
    else:
        component_id = exp_id
    return support_type, component_id, direction


def extract_channel_labels(header_row: Sequence[object]) -> tuple[List[str], List[str]]:
    labels: List[str] = []
    bracket_labels: List[str] = []
    for idx in range(CHANNEL_COUNT):
        col_idx = SIGNAL_START_COL_IDX + idx
        raw = str(header_row[col_idx]) if col_idx < len(header_row) else f"ch_{idx + 1:02d}"
        m = re.search(r"\[(\d+#\d+)\]", raw)
        bracket = m.group(1) if m else f"CH{idx + 1:02d}"
        labels.append(f"ch_{idx + 1:02d}")
        bracket_labels.append(bracket)
    return labels, bracket_labels


def read_xls_wave(filepath: Path, original_name: str | None = None) -> WaveData:
    workbook = xlrd.open_workbook(str(filepath))
    sheet = workbook.sheet_by_index(0)
    header = sheet.row_values(0)
    data_rows = sheet.nrows - 1
    if data_rows <= 0:
        raise ValueError(f"{filepath.name}: empty data rows")

    time_arr = np.asarray(sheet.col_values(TIME_COL_IDX, start_rowx=1), dtype=np.float64)
    signals = np.zeros((data_rows, CHANNEL_COUNT), dtype=np.float32)
    for c in range(CHANNEL_COUNT):
        values = sheet.col_values(SIGNAL_START_COL_IDX + c, start_rowx=1)
        signals[:, c] = np.asarray(values, dtype=np.float32)

    if len(time_arr) >= 2:
        dt = float(np.median(np.diff(time_arr)))
        sample_rate = float(1.0 / dt) if dt > 0 else 0.0
    else:
        dt = 0.0
        sample_rate = 0.0
    duration = float(time_arr[-1] - time_arr[0]) if len(time_arr) >= 2 else 0.0

    stem = filepath.stem
    exp_id = normalize_exp_id_from_stem(stem)
    support_type, component_id, direction = parse_component_and_direction(exp_id)
    channel_labels, bracket_labels = extract_channel_labels(header)

    return WaveData(
        exp_id=exp_id,
        original_filename=original_name or filepath.name,
        current_filename=filepath.name,
        sample_rate=sample_rate,
        dt=dt,
        duration=duration,
        time=time_arr,
        signals=signals,
        channel_labels=channel_labels,
        bracket_labels=bracket_labels,
        support_type=support_type,
        component_id=component_id,
        direction=direction,
    )


def discover_xls_files(origin_dir: Path) -> List[Path]:
    files = sorted(origin_dir.glob("*.XLS")) + sorted(origin_dir.glob("*.xls"))
    unique: Dict[str, Path] = {}
    for f in files:
        unique[f.name.lower()] = f
    return sorted(unique.values(), key=lambda p: p.name.lower())
