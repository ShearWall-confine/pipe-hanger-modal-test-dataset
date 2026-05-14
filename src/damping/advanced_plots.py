from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

import h5py
import numpy as np
from matplotlib.figure import Figure
from scipy import signal
from scipy.signal import find_peaks

from damping.amplitude_anomaly import filter_result_rows_for_amplitude
from damping.signal_access import load_preferred_signal
from damping.damping_h5_schema import read_cycle_damping, read_damping_results
from tools.paper_figure_style import SUPPORT_COLORS, SUPPORT_MARKERS, support_marker_handles


DEFAULT_SUPPORTS = ["CA", "TB", "CSBD", "CSB"]
DEFAULT_SUPPORT_COLORS = SUPPORT_COLORS
MODE_ORDER = ["radial", "axial", "planar_rotation"]
MODE_TITLES = {
    "radial": "(a) Radial",
    "axial": "(b) Axial",
    "planar_rotation": "(c) In-plane rotation",
}

DEFAULT_BACKBONE_FREQ_RANGE = (0.1, 1.0)


def _to_float(value) -> float:
    try:
        out = float(value)
    except Exception:
        return float("nan")
    return out if np.isfinite(out) else float("nan")


def _butter_bandpass(sig: np.ndarray, dt: float, f0: float, bw_pct: float = 15.0, order: int = 4) -> np.ndarray:
    fs = 1.0 / dt
    nyq = 0.5 * fs
    lo = max(0.05, f0 * (1.0 - bw_pct / 100.0))
    hi = min(nyq * 0.98, f0 * (1.0 + bw_pct / 100.0))
    if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo):
        return sig.copy()
    b, a = signal.butter(order, [lo / nyq, hi / nyq], btype="band")
    return signal.filtfilt(b, a, sig)


def _iter_valid_rows(h5_path: Path) -> list[dict]:
    rows_by_exp = read_damping_results(h5_path, exp_id=None)
    rows: list[dict] = []
    for eid, subrows in rows_by_exp.items():
        for row in subrows:
            rr = dict(row)
            if not str(rr.get("exp_id", "")).strip():
                rr["exp_id"] = str(eid)
            if bool(rr.get("valid", False)) and bool(rr.get("drift_valid", False)):
                rows.append(rr)
    return rows


def _iter_all_rows(h5_path: Path) -> list[dict]:
    rows_by_exp = read_damping_results(h5_path, exp_id=None)
    rows: list[dict] = []
    for eid, subrows in rows_by_exp.items():
        for row in subrows:
            rr = dict(row)
            if not str(rr.get("exp_id", "")).strip():
                rr["exp_id"] = str(eid)
            rows.append(rr)
    return rows


def _row_priority(row: dict) -> tuple[float, float, float, float]:
    return (
        _to_float(row.get("drift_r_squared")),
        _to_float(row.get("r_squared")),
        _to_float(row.get("peak_count")),
        _to_float(row.get("freq_target")),
    )


def _select_representative_rows(rows: Iterable[dict]) -> list[dict]:
    bucket: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        key = (str(row.get("exp_id", "")), str(row.get("channel_id", "")))
        if all(key):
            bucket[key].append(row)

    chosen: list[dict] = []
    for subrows in bucket.values():
        best = max(subrows, key=_row_priority)
        chosen.append(best)
    return chosen


def collect_nli_points(
    h5_path: Path,
    bandwidth_pct: float = 15.0,
    butter_order: int = 4,
    min_freq_ratio: float = 0.2,
    min_abs_freq_hz: float = 0.1,
    amplitude_floor_ratio: float = 0.05,
    nli_hard_cap: float = 100.0,
    window_cycles: float = 3.0,
    span_percentiles: tuple[float, float] = (25.0, 75.0),
    exclude_amp_anomalies: bool = False,
) -> tuple[list[tuple[str, float, float]], dict[str, int]]:
    rows = _iter_valid_rows(h5_path)
    if exclude_amp_anomalies:
        rows = filter_result_rows_for_amplitude(rows, h5_path)
    selected_rows = _select_representative_rows(rows)
    nli_pts: list[tuple[str, float, float]] = []
    stats = {
        "all_valid_rows": len(rows),
        "selected_channels": len(selected_rows),
        "used_windows": 0,
        "skipped_low_amp": 0,
        "skipped_low_freq": 0,
        "skipped_extreme_nli": 0,
        "skipped_bad_signal": 0,
    }

    with h5py.File(h5_path, "r") as h5:
        exps = h5["experiments"]
        for row in selected_rows:
            exp_id = str(row["exp_id"])
            ch = str(row["channel_id"])
            if exp_id not in exps:
                stats["skipped_bad_signal"] += 1
                continue
            group = exps[exp_id]
            if "time" not in group or "channels" not in group or ch not in group["channels"]:
                stats["skipped_bad_signal"] += 1
                continue

            t = np.asarray(group["time"][:], dtype=np.float64)
            x = load_preferred_signal(group["channels"][ch])
            if t.size < 64 or x.size != t.size:
                stats["skipped_bad_signal"] += 1
                continue

            dt = float(np.median(np.diff(t)))
            f0 = _to_float(row.get("freq_target"))
            if not (np.isfinite(dt) and dt > 0 and np.isfinite(f0) and f0 > 0):
                stats["skipped_bad_signal"] += 1
                continue

            try:
                xf = _butter_bandpass(x, dt, f0, bw_pct=bandwidth_pct, order=butter_order)
                analytic = signal.hilbert(xf)
                env = np.abs(analytic)
                phase = np.unwrap(np.angle(analytic))
                finst = np.diff(phase) / (2.0 * np.pi * dt)
                env2 = env[1:]
            except Exception:
                stats["skipped_bad_signal"] += 1
                continue

            if finst.size < 16 or env2.size != finst.size:
                stats["skipped_bad_signal"] += 1
                continue

            fs = 1.0 / dt
            win = int(max(24, round((window_cycles / max(f0, 0.2)) * fs)))
            step = max(8, win // 2)
            amp_floor = max(0.0, float(np.nanpercentile(env2, 95)) * amplitude_floor_ratio)
            freq_floor = max(min_abs_freq_hz, min_freq_ratio * f0)

            for i0 in range(0, max(1, len(finst) - win + 1), step):
                fseg = finst[i0 : i0 + win]
                aseg = env2[i0 : i0 + win]
                if fseg.size < 8:
                    continue
                amp = float(np.nanmedian(aseg))
                if not np.isfinite(amp) or amp < amp_floor:
                    stats["skipped_low_amp"] += 1
                    continue
                medf = float(np.nanmedian(fseg))
                if not np.isfinite(medf) or abs(medf) < freq_floor:
                    stats["skipped_low_freq"] += 1
                    continue
                q_lo, q_hi = span_percentiles
                f_lo = float(np.nanpercentile(fseg, q_lo))
                f_hi = float(np.nanpercentile(fseg, q_hi))
                nli = (f_hi - f_lo) / abs(medf) * 100.0
                if not np.isfinite(nli) or nli < 0 or nli > nli_hard_cap:
                    stats["skipped_extreme_nli"] += 1
                    continue
                nli_pts.append((str(row.get("support_type", "")), amp, nli))
                stats["used_windows"] += 1

    return nli_pts, stats


def plot_nli_applicability(
    h5_path: Path,
    fig: Figure,
    bandwidth_pct: float = 15.0,
    butter_order: int = 4,
    support_colors: dict[str, str] | None = None,
    supports: list[str] | None = None,
    min_freq_ratio: float = 0.2,
    min_abs_freq_hz: float = 0.1,
    amplitude_floor_ratio: float = 0.05,
    nli_hard_cap: float = 100.0,
    window_cycles: float = 3.0,
    span_percentiles: tuple[float, float] = (25.0, 75.0),
    exclude_amp_anomalies: bool = False,
    applicability_bins: int = 150,
) -> dict[str, int]:
    support_colors = support_colors or DEFAULT_SUPPORT_COLORS
    supports = supports or DEFAULT_SUPPORTS
    nli_pts, stats = collect_nli_points(
        h5_path=h5_path,
        bandwidth_pct=bandwidth_pct,
        butter_order=butter_order,
        min_freq_ratio=min_freq_ratio,
        min_abs_freq_hz=min_abs_freq_hz,
        amplitude_floor_ratio=amplitude_floor_ratio,
        nli_hard_cap=nli_hard_cap,
        window_cycles=window_cycles,
        span_percentiles=span_percentiles,
        exclude_amp_anomalies=exclude_amp_anomalies,
    )

    ax = fig.subplots(1, 1)
    draw_order = [sup for sup in ("TB", "CA", "CSBD", "CSB") if sup in supports]
    for sup in draw_order:
        pts = [(a, n) for s, a, n in nli_pts if s == sup]
        if not pts:
            continue
        arr = np.asarray(pts, dtype=np.float64)
        rare_support = len(pts) < 250
        common_ca = sup == "CA"
        ax.scatter(
            arr[:, 0],
            arr[:, 1],
            s=18 if rare_support else 10,
            alpha=0.62 if rare_support else (0.50 if common_ca else 0.36),
            color=support_colors[sup],
            marker=SUPPORT_MARKERS.get(sup, "o"),
            edgecolors="white" if rare_support else "none",
            linewidths=0.25 if rare_support else 0.0,
            label=sup,
            rasterized=True,
            zorder=4 if rare_support else (3 if common_ca else 2),
        )

    ax.axhline(5.0, color="#d00000", lw=1.6, ls="--", zorder=1)

    ratio_color = "#5c6770"
    ax2 = None

    if len(nli_pts) > 30:
        arr = np.asarray([(a, n) for _, a, n in nli_pts], dtype=np.float64)
        amps = arr[:, 0]
        nli = arr[:, 1]
        a_min = max(0.0, float(np.nanmin(amps)))
        a_max = float(np.nanmax(amps))
        if np.isfinite(a_min) and np.isfinite(a_max) and a_max > a_min:
            edges = np.linspace(a_min, a_max, max(6, int(applicability_bins)) + 1)
        else:
            edges = np.array([0.0, 1.0], dtype=np.float64)
        xc = []
        yc = []
        for i in range(len(edges) - 1):
            mask = (amps >= edges[i]) & (amps <= edges[i + 1] if i == len(edges) - 2 else amps < edges[i + 1])
            if int(np.sum(mask)) < 8:
                continue
            width = float(edges[i + 1] - edges[i])
            xc.append(float(edges[i + 1] - 0.15 * width))
            yc.append(float(np.mean(nli[mask] < 5.0) * 100.0))
        if xc:
            ax2 = ax.twinx()
            ax2.plot(xc, yc, color=ratio_color, lw=1.2, marker="o", ms=2.5, alpha=0.9, zorder=2)
            ax2.axhline(100.0, color="black", lw=0.7, alpha=0.85, zorder=1)
            ax2.set_ylabel("Applicability Ratio (%)", color=ratio_color, fontsize=11, labelpad=6)
            ax2.set_ylim(0, 105)
            ax2.tick_params(axis="y", colors=ratio_color, labelsize=9)
            ax2.spines["right"].set_color(ratio_color)

    fig.subplots_adjust(left=0.07, right=0.955, bottom=0.26, top=0.82)
    fig.suptitle("Equivalent Linearization Applicability (NLI)", y=0.985, fontsize=12)
    ax.set_xlabel("Amplitude (mm/s)", fontsize=11, labelpad=7)
    ax.set_ylabel("NLI (%)", fontsize=11, labelpad=7)
    ax.grid(False)
    ax.set_box_aspect(0.30)
    ax.set_ylim(0, 30)
    ax.set_xlim(left=0)
    ax.margins(x=0.0)
    ax.tick_params(labelsize=9)
    x_right = ax.get_xlim()[1]
    ax.text(
        x_right * 0.965,
        5.35,
        "5% relative frequency-variation threshold",
        ha="right",
        va="bottom",
        fontsize=7.2,
        color="#b00000",
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.75, pad=0.35),
        zorder=5,
    )
    legend_supports = [sup for sup in supports if any(s == sup for s, _, _ in nli_pts)]
    ax.legend(
        support_marker_handles(legend_supports, markersize=5.8),
        legend_supports,
        frameon=True,
        ncol=1,
        fontsize=7.0,
        loc="center right",
        bbox_to_anchor=(0.985, 0.60),
        borderaxespad=0.25,
        facecolor="white",
        edgecolor="none",
        framealpha=0.78,
        handlelength=1.5,
        labelspacing=0.25,
    )
    if ax2 is not None:
        ax2.set_zorder(0)
        ax.patch.set_alpha(0.0)
    return stats


def _extract_backbone_trace(
    h5,
    exp_id: str,
    channel_id: str,
    f0: float,
    bandwidth_pct: float,
    butter_order: int,
    amp_floor_ratio: float,
    freq_range: tuple[float, float],
) -> dict | None:
    exps = h5["experiments"]
    if exp_id not in exps or channel_id not in exps[exp_id]["channels"]:
        return None
    group = exps[exp_id]
    if "time" not in group:
        return None

    t = np.asarray(group["time"][:], dtype=np.float64)
    x = load_preferred_signal(group["channels"][channel_id])
    if t.size < 64 or x.size != t.size:
        return None

    dt = float(np.median(np.diff(t)))
    if not (np.isfinite(dt) and dt > 0 and np.isfinite(f0) and f0 > 0):
        return None

    try:
        xf = _butter_bandpass(x, dt, f0, bw_pct=bandwidth_pct, order=butter_order)
        analytic = signal.hilbert(xf)
        env = np.abs(analytic)
        phase = np.unwrap(np.angle(analytic))
        finst = np.diff(phase) / (2.0 * np.pi * dt)
        amp = env[1:]
    except Exception:
        return None

    if finst.size < 32 or amp.size != finst.size:
        return None

    amp_max = float(np.nanmax(amp)) if np.any(np.isfinite(amp)) else np.nan
    if not np.isfinite(amp_max) or amp_max <= 0:
        return None

    amp_floor = amp_floor_ratio * amp_max
    f_lo, f_hi = freq_range

    raw_mask = np.isfinite(finst) & np.isfinite(amp) & (amp > 0)
    n_raw = int(np.sum(raw_mask))
    if n_raw < 32:
        return None

    keep_mask = raw_mask & (amp >= amp_floor) & (finst >= f_lo) & (finst <= f_hi)
    keep_ratio = float(np.sum(keep_mask) / max(n_raw, 1))
    if np.sum(keep_mask) < 24:
        return {
            "valid": False,
            "keep_ratio": keep_ratio,
            "amp_span": 0.0,
            "n_points": int(np.sum(keep_mask)),
        }

    amp_keep = amp[keep_mask]
    finst_keep = finst[keep_mask]
    order = np.argsort(amp_keep)[::-1]
    amp_keep = amp_keep[order]
    finst_keep = finst_keep[order]

    if amp_keep.size > 4000:
        idx = np.linspace(0, amp_keep.size - 1, 4000).astype(int)
        amp_keep = amp_keep[idx]
        finst_keep = finst_keep[idx]

    amp_span = float(np.nanmax(amp_keep) - np.nanmin(amp_keep)) if amp_keep.size else 0.0
    return {
        "valid": keep_ratio >= 0.80 and amp_span > max(amp_floor, 1e-9),
        "keep_ratio": keep_ratio,
        "amp_span": amp_span,
        "n_points": int(amp_keep.size),
        "amp": amp_keep,
        "finst": finst_keep,
    }


def _extract_decay_envelope_trace(
    h5,
    exp_id: str,
    channel_id: str,
    f0: float,
    t_start: float,
    t_end: float,
    bandwidth_pct: float,
    butter_order: int,
) -> dict | None:
    exps = h5["experiments"]
    if exp_id not in exps or channel_id not in exps[exp_id]["channels"]:
        return None
    group = exps[exp_id]
    if "time" not in group:
        return None

    t = np.asarray(group["time"][:], dtype=np.float64)
    x = load_preferred_signal(group["channels"][channel_id])
    if t.size < 64 or x.size != t.size:
        return None

    dt = float(np.median(np.diff(t)))
    if not (np.isfinite(dt) and dt > 0 and np.isfinite(f0) and f0 > 0):
        return None

    try:
        xf = _butter_bandpass(x, dt, f0, bw_pct=bandwidth_pct, order=butter_order)
        env = np.abs(signal.hilbert(xf))
    except Exception:
        return None

    if env.size != t.size or env.size < 32:
        return None

    mask = (t >= t_start) & (t <= t_end)
    if int(np.sum(mask)) < 16:
        return None

    tt = t[mask]
    ee = env[mask]
    peak = float(np.nanmax(ee)) if np.any(np.isfinite(ee)) else np.nan
    if not np.isfinite(peak) or peak <= 0:
        return None

    x_cycles = (tt - float(t_start)) * float(f0)
    y_norm = ee / peak
    finite = np.isfinite(x_cycles) & np.isfinite(y_norm)
    if int(np.sum(finite)) < 16:
        return None

    return {
        "x_cycles": np.asarray(x_cycles[finite], dtype=np.float64),
        "y_norm": np.asarray(y_norm[finite], dtype=np.float64),
        "peak": peak,
    }


def _extract_decay_frequency_check(
    h5,
    exp_id: str,
    channel_id: str,
    f0: float,
    t_start: float,
    t_end: float,
    bandwidth_pct: float,
    butter_order: int,
) -> dict | None:
    exps = h5["experiments"]
    if exp_id not in exps or channel_id not in exps[exp_id]["channels"]:
        return None
    group = exps[exp_id]
    if "time" not in group:
        return None

    t = np.asarray(group["time"][:], dtype=np.float64)
    x = load_preferred_signal(group["channels"][channel_id])
    if t.size < 64 or x.size != t.size:
        return None

    dt = float(np.median(np.diff(t)))
    if not (np.isfinite(dt) and dt > 0 and np.isfinite(f0) and f0 > 0):
        return None

    try:
        xf = _butter_bandpass(x, dt, f0, bw_pct=bandwidth_pct, order=butter_order)
        env = np.abs(signal.hilbert(xf))
    except Exception:
        return None

    mask = (t >= t_start) & (t <= t_end)
    if int(np.sum(mask)) < 16:
        return None

    tt = np.asarray(t[mask], dtype=np.float64)
    xx = np.asarray(xf[mask], dtype=np.float64)
    ee = np.asarray(env[mask], dtype=np.float64)
    if tt.size < 16:
        return None

    peak_amp = float(np.nanmax(np.abs(xx))) if np.any(np.isfinite(xx)) else np.nan
    if not np.isfinite(peak_amp) or peak_amp <= 0:
        return None

    # Positive peaks on filtered waveform approximate manual "counting peaks".
    min_distance = max(1, int(round((1.0 / f0) / dt * 0.5)))
    prominence = max(peak_amp * 0.05, 1e-12)
    peaks, props = find_peaks(xx, distance=min_distance, prominence=prominence)
    if peaks.size < 3:
        peaks, props = find_peaks(np.abs(xx), distance=min_distance, prominence=prominence)

    freq_peak = float("nan")
    period_mean = float("nan")
    peak_count = int(peaks.size)
    if peaks.size >= 2:
        peak_times = tt[peaks]
        diffs = np.diff(peak_times)
        diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
        if diffs.size > 0:
            period_mean = float(np.mean(diffs))
            freq_peak = float(1.0 / period_mean) if period_mean > 0 else float("nan")
    else:
        peak_times = np.asarray([], dtype=np.float64)

    return {
        "t_rel": tt - float(t_start),
        "sig_norm": xx / peak_amp,
        "env_norm": ee / max(float(np.nanmax(ee)), 1e-12),
        "peak_t_rel": peak_times - float(t_start),
        "peak_y_norm": (xx[peaks] / peak_amp) if peaks.size > 0 else np.asarray([], dtype=np.float64),
        "freq_peakcount": freq_peak,
        "period_mean": period_mean,
        "peak_count": peak_count,
    }


def plot_backbone_examples(
    h5_path: Path,
    fig: Figure,
    bandwidth_pct: float = 15.0,
    butter_order: int = 4,
    supports: list[str] | None = None,
    support_colors: dict[str, str] | None = None,
    amp_floor_ratio: float = 0.08,
    freq_range: tuple[float, float] = DEFAULT_BACKBONE_FREQ_RANGE,
    min_keep_ratio: float = 0.80,
    exclude_amp_anomalies: bool = True,
) -> dict[str, str]:
    supports = supports or DEFAULT_SUPPORTS
    support_colors = support_colors or DEFAULT_SUPPORT_COLORS

    rows = _iter_valid_rows(h5_path)
    if exclude_amp_anomalies:
        rows = filter_result_rows_for_amplitude(rows, h5_path)

    by_support: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if np.isfinite(_to_float(row.get("freq_target"))):
            by_support[str(row.get("support_type", ""))].append(row)

    fig.clear()
    axs = np.asarray(fig.subplots(2, 2)).reshape(-1)
    notes: dict[str, str] = {}

    with h5py.File(h5_path, "r") as h5:
        for i, support in enumerate(supports):
            ax = axs[i]
            candidates = sorted(
                by_support.get(support, []),
                key=lambda r: (
                    _to_float(r.get("amplitude_at_start")),
                    _to_float(r.get("drift_r_squared")),
                    _to_float(r.get("r_squared")),
                ),
                reverse=True,
            )

            picked = None
            picked_note = "No high-quality record"
            fallback = None
            for row in candidates:
                exp_id = str(row.get("exp_id", ""))
                ch = str(row.get("channel_id", ""))
                f0 = _to_float(row.get("freq_target"))
                trace = _extract_backbone_trace(
                    h5=h5,
                    exp_id=exp_id,
                    channel_id=ch,
                    f0=f0,
                    bandwidth_pct=bandwidth_pct,
                    butter_order=butter_order,
                    amp_floor_ratio=amp_floor_ratio,
                    freq_range=freq_range,
                )
                if trace is None:
                    continue
                if fallback is None and trace.get("n_points", 0) > 0:
                    fallback = (row, trace)
                if trace.get("valid", False) and trace.get("keep_ratio", 0.0) >= min_keep_ratio:
                    picked = (row, trace)
                    picked_note = (
                        f"{exp_id} | {ch} | kept {trace['keep_ratio']*100:.1f}% "
                        f"| amp>{amp_floor_ratio*100:.0f}% max | f in [{freq_range[0]:.1f}, {freq_range[1]:.1f}] Hz"
                    )
                    break

            if picked is None and fallback is not None:
                row, trace = fallback
                picked = fallback
                picked_note = (
                    f"{row['exp_id']} | {row['channel_id']} | low-quality fallback "
                    f"(kept {trace['keep_ratio']*100:.1f}%)"
                )

            if picked is None:
                ax.text(0.5, 0.5, f"{support}\nNo usable backbone record", ha="center", va="center", transform=ax.transAxes)
                ax.set_title(support)
                ax.grid(False)
                notes[support] = "No usable record"
                continue

            row, trace = picked
            ax.plot(trace["amp"], trace["finst"], color=support_colors[support], alpha=0.85, lw=1.4)
            ax.set_title(f"{support} | {row['exp_id']} | {row['channel_id']}")
            ax.set_xlabel("Instantaneous Amplitude (mm/s)")
            ax.set_ylabel("Instantaneous Frequency (Hz)")
            ax.set_ylim(*freq_range)
            ax.set_xlim(left=0)
            ax.grid(False)
            notes[support] = picked_note

    fig.suptitle("Backbone Examples (quality-filtered single-decay instantaneous frequency vs amplitude)", y=0.98)
    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.95))
    return notes


def plot_decay_envelope_examples(
    h5_path: Path,
    fig: Figure,
    support_filter: str | None = None,
    exclude_supports: list[str] | None = None,
    max_examples: int = 4,
    bandwidth_pct: float = 15.0,
    butter_order: int = 4,
    exclude_amp_anomalies: bool = False,
    title: str | None = None,
) -> list[str]:
    exclude_supports = exclude_supports or []
    rows = _iter_all_rows(h5_path)
    if exclude_amp_anomalies:
        rows = filter_result_rows_for_amplitude(rows, h5_path)

    candidates: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        support = str(row.get("support_type", ""))
        if support_filter and support != support_filter:
            continue
        if support in exclude_supports:
            continue

        key = (str(row.get("exp_id", "")), str(row.get("channel_id", "")), str(row.get("mode", "")))
        if key in seen:
            continue
        seen.add(key)

        f0 = _to_float(row.get("freq_target"))
        t_start = _to_float(row.get("t_start"))
        t_end = _to_float(row.get("t_end"))
        amp0 = _to_float(row.get("amplitude_at_start"))
        if not (np.isfinite(f0) and f0 > 0 and np.isfinite(t_start) and np.isfinite(t_end) and t_end > t_start and np.isfinite(amp0) and amp0 > 0):
            continue

        decay_cycles = (t_end - t_start) * f0
        if not np.isfinite(decay_cycles) or decay_cycles <= 0:
            continue

        rr = dict(row)
        rr["decay_cycles"] = float(decay_cycles)
        candidates.append(rr)

    candidates.sort(
        key=lambda r: (
            _to_float(r.get("decay_cycles")),
            -_to_float(r.get("amplitude_at_start")),
            _to_float(r.get("r_squared")),
        )
    )
    selected = candidates[: max(1, int(max_examples))]

    fig.clear()
    axs = np.asarray(fig.subplots(2, 2)).reshape(-1)
    notes: list[str] = []
    x_max = 0.0
    traces: list[tuple] = []

    with h5py.File(h5_path, "r") as h5:
        for row in selected:
            trace = _extract_decay_envelope_trace(
                h5=h5,
                exp_id=str(row["exp_id"]),
                channel_id=str(row["channel_id"]),
                f0=float(row["freq_target"]),
                t_start=float(row["t_start"]),
                t_end=float(row["t_end"]),
                bandwidth_pct=bandwidth_pct,
                butter_order=butter_order,
            )
            traces.append((row, trace))
            if trace is not None and trace["x_cycles"].size:
                x_max = max(x_max, float(np.nanmax(trace["x_cycles"])))

    x_lim_hi = max(3.0, min(20.0, x_max * 1.05 if x_max > 0 else 8.0))

    for ax, item in zip(axs, traces):
        row, trace = item
        support = str(row.get("support_type", ""))
        color = DEFAULT_SUPPORT_COLORS.get(support, "#495057")
        exp_id = str(row.get("exp_id", ""))
        ch = str(row.get("channel_id", ""))
        mode = str(row.get("mode", ""))
        decay_cycles = float(row.get("decay_cycles", np.nan))
        reject_reason = str(row.get("reject_reason", ""))
        valid = bool(row.get("valid", False))

        if trace is None:
            ax.text(0.5, 0.5, f"{exp_id}\n{ch} | {mode}\ntrace unavailable", ha="center", va="center", transform=ax.transAxes)
        else:
            ax.plot(trace["x_cycles"], trace["y_norm"], color=color, lw=1.6, alpha=0.95)
            ax.axhline(0.05, color="#6c757d", lw=0.8, ls="--", alpha=0.9)
            ax.axvline(decay_cycles, color="#343a40", lw=0.9, ls=":")
            ax.set_xlim(0, x_lim_hi)
            ax.set_ylim(0, 1.05)

        status = "valid" if valid else reject_reason
        ax.set_title(f"{support} | {mode}\n{exp_id} | {ch}", fontsize=9)
        ax.text(
            0.98,
            0.96,
            f"{decay_cycles:.2f} cycles\n{status}",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=7,
            bbox=dict(facecolor="white", alpha=0.82, edgecolor="none", pad=1.2),
        )
        ax.set_xlabel("Decay Window Length (cycles)")
        ax.set_ylabel("Normalized Envelope")
        ax.grid(False)
        notes.append(f"{support}: {exp_id} | {ch} | {mode} | {decay_cycles:.2f} cycles | {status}")

    for ax in axs[len(traces) :]:
        ax.axis("off")

    fig.suptitle(title or "Fast-Decay Envelope Examples", y=0.98)
    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.95))
    return notes


def plot_selected_fast_decay_frequency_check(
    h5_path: Path,
    fig: Figure,
    exp_ids: list[str],
    bandwidth_pct: float = 15.0,
    butter_order: int = 4,
    show_case_legend: bool = False,
    ax=None,
) -> list[dict]:
    rows = _iter_all_rows(h5_path)
    wanted = set(exp_ids)
    by_exp: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        exp_id = str(row.get("exp_id", ""))
        if exp_id in wanted:
            by_exp[exp_id].append(row)

    selected: list[dict] = []
    support_order = {name: idx for idx, name in enumerate(DEFAULT_SUPPORTS)}
    mode_order = {"radial": 0, "axial": 1, "planar_rotation": 2}
    for exp_id in exp_ids:
        candidates = []
        for row in by_exp.get(exp_id, []):
            f0 = _to_float(row.get("freq_target"))
            t_start = _to_float(row.get("t_start"))
            t_end = _to_float(row.get("t_end"))
            amp0 = _to_float(row.get("amplitude_at_start"))
            if not (np.isfinite(f0) and f0 > 0 and np.isfinite(t_start) and np.isfinite(t_end) and t_end > t_start and np.isfinite(amp0) and amp0 > 0):
                continue
            rr = dict(row)
            rr["decay_cycles"] = float((t_end - t_start) * f0)
            candidates.append(rr)
        candidates.sort(
            key=lambda r: (
                _to_float(r.get("decay_cycles")),
                -_to_float(r.get("amplitude_at_start")),
                _to_float(r.get("r_squared")),
            )
        )
        if candidates:
            selected.append(candidates[0])

    selected.sort(
        key=lambda r: (
            support_order.get(str(r.get("support_type", "")), 99),
            mode_order.get(str(r.get("mode", "")), 99),
            str(r.get("exp_id", "")),
            str(r.get("channel_id", "")),
        )
    )

    from matplotlib.lines import Line2D

    standalone = ax is None
    if standalone:
        fig.clear()
        ax = fig.subplots(1, 1)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#fbfbfd")
    reports: list[dict] = []
    x_max = 0.0
    mode_linestyle = {
        "radial": "-",
        "axial": "--",
        "planar_rotation": ":",
    }
    case_handles = []
    case_labels = []

    with h5py.File(h5_path, "r") as h5:
        traces = []
        for row in selected:
            exp_id = str(row["exp_id"])
            ch = str(row["channel_id"])
            mode = str(row["mode"])
            support = str(row.get("support_type", ""))
            f0 = float(row["freq_target"])
            t_start = float(row["t_start"])
            t_end = float(row["t_end"])
            trace = _extract_decay_frequency_check(
                h5=h5,
                exp_id=exp_id,
                channel_id=ch,
                f0=f0,
                t_start=t_start,
                t_end=t_end,
                bandwidth_pct=bandwidth_pct,
                butter_order=butter_order,
            )
            env_trace = _extract_decay_envelope_trace(
                h5=h5,
                exp_id=exp_id,
                channel_id=ch,
                f0=f0,
                t_start=t_start,
                t_end=t_end,
                bandwidth_pct=bandwidth_pct,
                butter_order=butter_order,
            )
            traces.append((row, trace, env_trace))
            if env_trace is not None and env_trace["x_cycles"].size:
                x_max = max(x_max, float(np.nanmax(env_trace["x_cycles"])))

        x_lim_hi = max(3.0, min(12.0, x_max * 1.04 if x_max > 0 else 6.0))
        marker_band_hi = 0.055
        marker_band_y = 0.032
        ax.axhspan(0.0, marker_band_hi, color="#eef2f6", alpha=0.82, zorder=0)
        ax.axhline(0.05, color="#7a7a7a", lw=0.9, ls="--", alpha=0.85, zorder=1)

        for row, trace, env_trace in traces:
            exp_id = str(row["exp_id"])
            ch = str(row["channel_id"])
            mode = str(row["mode"])
            support = str(row.get("support_type", ""))
            f0 = float(row["freq_target"])
            color = DEFAULT_SUPPORT_COLORS.get(support, "#495057")
            linestyle = mode_linestyle.get(mode, "-")

            freq_peak = float("nan")
            period_mean = float("nan")
            peak_count = 0
            rel_diff_pct = float("nan")

            if trace is not None:
                freq_peak = _to_float(trace.get("freq_peakcount"))
                period_mean = _to_float(trace.get("period_mean"))
                peak_count = int(trace.get("peak_count", 0))
                if np.isfinite(freq_peak) and f0 > 0:
                    rel_diff_pct = float((freq_peak - f0) / f0 * 100.0)

            if env_trace is not None:
                ax.plot(
                    env_trace["x_cycles"],
                    env_trace["y_norm"],
                    color="white",
                    lw=3.4,
                    ls=linestyle,
                    alpha=0.95,
                    zorder=2,
                )
                line, = ax.plot(
                    env_trace["x_cycles"],
                    env_trace["y_norm"],
                    color=color,
                    lw=1.85,
                    ls=linestyle,
                    alpha=0.96,
                    zorder=3,
                )
                ax.scatter(
                    [env_trace["x_cycles"][-1]],
                    [env_trace["y_norm"][-1]],
                    s=20,
                    marker="o",
                    color=color,
                    edgecolors="white",
                    linewidths=0.4,
                    zorder=4,
                )
                if trace is not None and trace["peak_t_rel"].size > 0:
                    peak_x = trace["peak_t_rel"] * f0
                    mask = np.isfinite(peak_x) & (peak_x >= 0) & (peak_x <= x_lim_hi)
                    if int(np.sum(mask)) > 0:
                        ax.scatter(
                            peak_x[mask],
                            np.full(int(np.sum(mask)), marker_band_y),
                            s=18,
                            marker="v",
                            color=color,
                            alpha=0.9,
                            zorder=5,
                            edgecolors="white",
                            linewidths=0.35,
                        )
                diff_txt = f"{rel_diff_pct:+.0f}%" if np.isfinite(rel_diff_pct) else "NA"
                case_handles.append(line)
                case_labels.append(f"{support} | {exp_id} | {mode} | Δf={diff_txt}")

            reports.append(
                {
                    "exp_id": exp_id,
                    "support_type": support,
                    "channel_id": ch,
                    "mode": mode,
                    "valid": bool(row.get("valid", False)),
                    "reject_reason": str(row.get("reject_reason", "")),
                    "decay_cycles": float(row.get("decay_cycles", np.nan)),
                    "freq_auto_hz": f0,
                    "freq_peakcount_hz": freq_peak,
                    "period_peakcount_s": period_mean,
                    "peak_count": peak_count,
                    "rel_diff_pct": rel_diff_pct,
                }
            )

    ax.set_title("Fast-decay frequency check", fontsize=8.6, pad=9)
    ax.set_xlim(0, x_lim_hi)
    ax.set_ylim(0.0, 1.02)
    ax.set_xlabel("Decay window length (cycles, based on $f_{auto}$)", fontsize=8.8, labelpad=7)
    ax.set_ylabel("Normalized Hilbert Envelope", fontsize=8.8, labelpad=8)
    ax.grid(axis="x", color="#d8dee9", alpha=0.55, linewidth=0.7, linestyle=":")
    ax.tick_params(direction="in", length=2.8, width=0.85, labelsize=7.6)
    ax.set_yticks(np.linspace(0.0, 1.0, 5))
    for spine in ax.spines.values():
        spine.set_linewidth(0.95)
    peak_marker_text = ax.text(
        0.995,
        0.05,
        "Peak-count markers",
        transform=ax.get_yaxis_transform(),
        ha="right",
        va="bottom",
        fontsize=6.5 if standalone else 4.6,
        color="#5f6b7a",
    )
    peak_marker_text.set_gid("keep-fontsize")

    finite_diffs = np.asarray(
        [float(r["rel_diff_pct"]) for r in reports if np.isfinite(_to_float(r.get("rel_diff_pct")))],
        dtype=np.float64,
    )
    if finite_diffs.size > 0:
        summary_txt = (
            f"n={len(reports)}\n"
            f"mean |Δf| = {float(np.mean(np.abs(finite_diffs))):.1f}%\n"
            f"median |Δf| = {float(np.median(np.abs(finite_diffs))):.1f}%"
        )
    else:
        summary_txt = f"n={len(reports)}\npeak-count frequency unavailable"
    info_fontsize = 5.7 if not standalone else 7.0
    info_box = ax.inset_axes([0.565, 0.675, 0.405, 0.285] if not standalone else [0.67, 0.70, 0.30, 0.23])
    info_box.set_gid("keep-local-fontsizes")
    info_box.set_facecolor((1.0, 1.0, 1.0, 0.92))
    for spine in info_box.spines.values():
        spine.set_edgecolor("#d7dde5")
        spine.set_linewidth(0.9)
    info_box.set_xticks([])
    info_box.set_yticks([])
    info_box.set_xlim(0.0, 1.0)
    info_box.set_ylim(0.0, 1.0)

    left_entries = [
        ("line", DEFAULT_SUPPORT_COLORS["CA"], "-", "CA"),
        ("line", DEFAULT_SUPPORT_COLORS["TB"], "-", "TB"),
        ("line", DEFAULT_SUPPORT_COLORS["CSBD"], "-", "CSBD"),
        ("line", DEFAULT_SUPPORT_COLORS["CSB"], "-", "CSB"),
    ]
    right_entries = [
        ("line", "#222222", "-", "Radial"),
        ("line", "#222222", "--", "Axial"),
        ("line", "#222222", ":", "In-plane rotation"),
        ("marker", "#444444", "v", "Peak-count"),
    ]

    def _legend_item(x0: float, y0: float, kind: str, color: str, style: str, label: str) -> None:
        if kind == "line":
            info_box.plot([x0, x0 + 0.09], [y0, y0], color=color, lw=1.65, ls=style, solid_capstyle="butt")
        else:
            info_box.plot([x0 + 0.045], [y0], marker=style, color=color, markerfacecolor=color, markersize=4.8, lw=0)
        text = info_box.text(x0 + 0.105, y0, label, ha="left", va="center", fontsize=info_fontsize, color="#111111")
        text.set_gid("keep-fontsize")

    header_color = "#4b5563"
    support_header = info_box.text(0.06, 0.91, "Support type", ha="left", va="center", fontsize=info_fontsize, color=header_color)
    support_header.set_gid("keep-fontsize")
    mode_header = info_box.text(0.54, 0.91, "Mode / marker", ha="left", va="center", fontsize=info_fontsize, color=header_color)
    mode_header.set_gid("keep-fontsize")

    y_rows = (0.78, 0.67, 0.56, 0.45)
    for x0, entries in ((0.06, left_entries), (0.54, right_entries)):
        for y0, (kind, color, style, label) in zip(y_rows, entries):
            _legend_item(x0, y0, kind, color, style, label)

    info_box.plot([0.06, 0.94], [0.34, 0.34], color="#e5e7eb", lw=0.75)
    summary_text = info_box.text(
        0.94,
        0.23,
        summary_txt,
        ha="right",
        va="center",
        fontsize=info_fontsize,
        linespacing=1.10,
        color="#111111",
    )
    summary_text.set_gid("keep-fontsize")
    if show_case_legend and case_handles:
        ax.legend(
            case_handles,
            case_labels,
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
            frameon=False,
            fontsize=6.4,
            title="Selected cases",
            title_fontsize=7.0,
            ncol=1,
        )
    if standalone:
        fig.suptitle(
            "Rapidly Decaying Cases: Envelope Collapse and Peak-Count Δf",
            x=0.06,
            y=0.975,
            ha="left",
            fontsize=9.8,
            fontweight="bold",
        )
        right_margin = 0.82 if show_case_legend else 0.985
        fig.tight_layout(rect=(0.045, 0.08, right_margin, 0.90))
    return reports


def collect_cycle_energy_dissipation_rows(
    h5_path: Path,
    supports: list[str] | None = None,
    exclude_amp_anomalies: bool = True,
) -> list[tuple[str, str, float, float]]:
    supports = supports or DEFAULT_SUPPORTS
    rows_by_exp = read_damping_results(h5_path, exp_id=None)
    ede_rows: list[tuple[str, str, float, float]] = []

    for exp_id, rs in rows_by_exp.items():
        work_rows = rs
        if exclude_amp_anomalies:
            work_rows = filter_result_rows_for_amplitude(work_rows, h5_path)
        for row in work_rows:
            rr = dict(row)
            if not str(rr.get("exp_id", "")).strip():
                rr["exp_id"] = str(exp_id)
            if not bool(rr.get("valid", False)):
                continue
            sup = str(rr.get("support_type", ""))
            mode = str(rr.get("mode", ""))
            if sup not in supports:
                continue
            if mode not in MODE_ORDER:
                continue
            cyc = read_cycle_damping(h5_path, rr["exp_id"], str(rr["channel_id"]), str(rr["mode"]))
            if cyc is None:
                continue
            amp = np.asarray(cyc[0], dtype=np.float64)
            if amp.size < 3:
                continue
            a1 = amp[:-1]
            a2 = amp[1:]
            mask = np.isfinite(a1) & np.isfinite(a2) & (a1 > 0) & (a2 >= 0)
            if int(np.sum(mask)) == 0:
                continue
            de = 1.0 - (a2[mask] / a1[mask]) ** 2
            amid = 0.5 * (a1[mask] + a2[mask])
            for ai, di in zip(amid, de):
                if np.isfinite(ai) and np.isfinite(di) and 0.0 <= di < 1.0:
                    ede_rows.append((sup, mode, float(ai), float(di)))
    return ede_rows


def _clean_ede_rows_iqr(ede_rows: list[tuple[str, str, float, float]]) -> list[tuple[str, str, float, float]]:
    bucket: dict[tuple[str, str], list[float]] = defaultdict(list)
    for sup, mode, amp, de in ede_rows:
        if np.isfinite(amp) and np.isfinite(de) and 0.0 <= de < 1.0:
            bucket[(sup, mode)].append(de)

    bounds: dict[tuple[str, str], tuple[float, float]] = {}
    for key, values in bucket.items():
        arr = np.asarray(values, dtype=np.float64)
        if arr.size >= 8:
            q1, q3 = np.quantile(arr, [0.25, 0.75])
            iqr = q3 - q1
            bounds[key] = (max(0.0, q1 - 1.5 * iqr), min(1.0, q3 + 1.5 * iqr))
        else:
            bounds[key] = (0.0, 1.0)

    out: list[tuple[str, str, float, float]] = []
    for sup, mode, amp, de in ede_rows:
        if not (np.isfinite(amp) and np.isfinite(de) and 0.0 <= de < 1.0):
            continue
        lo, hi = bounds.get((sup, mode), (0.0, 1.0))
        if lo <= de <= hi:
            out.append((sup, mode, amp, de))
    return out


def _binned_median_curve(x: np.ndarray, y: np.ndarray, bins: int = 16) -> tuple[np.ndarray, np.ndarray]:
    if x.size < 12:
        return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
    x_min = max(0.0, float(np.nanmin(x)))
    x_max = float(np.nanmax(x))
    if not (np.isfinite(x_min) and np.isfinite(x_max) and x_max > x_min):
        return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
    edges = np.linspace(x_min, x_max, bins + 1)
    xc = []
    yc = []
    for i in range(len(edges) - 1):
        mask = (x >= edges[i]) & (x <= edges[i + 1] if i == len(edges) - 2 else x < edges[i + 1])
        if int(np.sum(mask)) < 8:
            continue
        xc.append(float(0.5 * (edges[i] + edges[i + 1])))
        yc.append(float(np.median(y[mask])))
    return np.asarray(xc, dtype=np.float64), np.asarray(yc, dtype=np.float64)


def _binned_percentile_curves(
    x: np.ndarray,
    y: np.ndarray,
    bins: int = 16,
    percentiles: tuple[float, float, float] = (25.0, 50.0, 75.0),
) -> tuple[np.ndarray, dict[float, np.ndarray]]:
    if x.size < 12:
        return np.asarray([], dtype=np.float64), {p: np.asarray([], dtype=np.float64) for p in percentiles}
    x_min = max(0.0, float(np.nanmin(x)))
    x_max = float(np.nanmax(x))
    if not (np.isfinite(x_min) and np.isfinite(x_max) and x_max > x_min):
        return np.asarray([], dtype=np.float64), {p: np.asarray([], dtype=np.float64) for p in percentiles}
    edges = np.linspace(x_min, x_max, bins + 1)
    centers: list[float] = []
    curves: dict[float, list[float]] = {p: [] for p in percentiles}
    for i in range(len(edges) - 1):
        mask = (x >= edges[i]) & (x <= edges[i + 1] if i == len(edges) - 2 else x < edges[i + 1])
        if int(np.sum(mask)) < 8:
            continue
        centers.append(float(0.5 * (edges[i] + edges[i + 1])))
        for p in percentiles:
            curves[p].append(float(np.percentile(y[mask], p)))
    return (
        np.asarray(centers, dtype=np.float64),
        {p: np.asarray(v, dtype=np.float64) for p, v in curves.items()},
    )


def plot_cycle_energy_dissipation(
    h5_path: Path,
    fig: Figure,
    supports: list[str] | None = None,
    support_colors: dict[str, str] | None = None,
    exclude_amp_anomalies: bool = True,
    bins: int = 16,
    zoom_ylim: tuple[float, float] | None = None,
    enhanced: bool = False,
) -> dict[str, int]:
    supports = supports or DEFAULT_SUPPORTS
    support_colors = support_colors or DEFAULT_SUPPORT_COLORS

    raw_rows = collect_cycle_energy_dissipation_rows(
        h5_path=h5_path,
        supports=supports,
        exclude_amp_anomalies=exclude_amp_anomalies,
    )
    ede_rows = _clean_ede_rows_iqr(raw_rows)

    fig.clear()
    axs = fig.subplots(1, len(MODE_ORDER), squeeze=False, sharey=True).flatten()
    stats: dict[str, int] = {}
    all_amp_values: list[float] = []
    all_de_values: list[float] = []
    for _sup, _mode, amp, de in ede_rows:
        all_amp_values.append(float(amp))
        all_de_values.append(float(de))

    x_limits = None
    if len(all_amp_values) > 1:
        amp_arr = np.asarray(all_amp_values, dtype=np.float64)
        x_lo = float(np.min(amp_arr))
        x_hi = float(np.max(amp_arr))
        pad = max(0.05 * (x_hi - x_lo), 1e-4)
        x_limits = (max(0.0, x_lo - pad), x_hi + pad)

    y_limits = zoom_ylim
    if y_limits is None and len(all_de_values) > 1:
        de_arr = np.asarray(all_de_values, dtype=np.float64)
        y_lo = float(np.min(de_arr))
        y_hi = float(np.max(de_arr))
        pad = max(0.05 * (y_hi - y_lo), 1e-4)
        y_limits = (max(0.0, y_lo - pad), min(1.0, y_hi + pad))

    for idx, (ax, mode) in enumerate(zip(axs, MODE_ORDER)):
        points_by_support: dict[str, list[tuple[float, float]]] = {k: [] for k in supports}
        for sup, mode_name, amp, de in ede_rows:
            if mode_name != mode:
                continue
            points_by_support.setdefault(sup, []).append((float(amp), float(de)))

        stats[mode] = sum(len(v) for v in points_by_support.values())
        support_keys = [k for k in supports if points_by_support.get(k)]
        if not support_keys:
            ax.text(
                0.5,
                0.54,
                "Insufficient usable cycle data",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=9,
                bbox=dict(facecolor="white", edgecolor="#d7dde5", alpha=0.9, boxstyle="round,pad=0.25"),
            )
            ax.set_title(MODE_TITLES.get(mode, mode), fontsize=11, pad=8)
            ax.grid(False)
            ax.set_xlim(0, 1)
            ax.set_box_aspect(0.72)
            continue

        interleaved_support: list[str] = []
        interleaved_amp: list[float] = []
        interleaved_de: list[float] = []
        idx_map = {k: 0 for k in support_keys}
        remaining = True
        while remaining:
            remaining = False
            for sup in support_keys:
                j = idx_map[sup]
                pts = points_by_support.get(sup, [])
                if j < len(pts):
                    a, de = pts[j]
                    interleaved_support.append(sup)
                    interleaved_amp.append(a)
                    interleaved_de.append(de)
                    idx_map[sup] = j + 1
                    remaining = True

        draw_order = [sup for sup in ("TB", "CA", "CSBD", "CSB") if sup in support_keys]
        for sup in draw_order:
            indices = [i for i, s in enumerate(interleaved_support) if s == sup]
            if not indices:
                continue
            arr_x = np.asarray([interleaved_amp[i] for i in indices], dtype=np.float64)
            arr_y = np.asarray([interleaved_de[i] for i in indices], dtype=np.float64)
            rare_support = len(indices) < 250
            common_ca = sup == "CA"
            ax.scatter(
                arr_x,
                arr_y,
                s=18 if rare_support else 10,
                alpha=0.62 if rare_support else (0.50 if common_ca else 0.36),
                color=support_colors.get(sup, "#6c757d"),
                marker=SUPPORT_MARKERS.get(sup, "o"),
                edgecolors="white" if rare_support else "none",
                linewidths=0.25 if rare_support else 0.0,
                rasterized=True,
                zorder=4 if rare_support else (3 if common_ca else 2),
            )

        for sup in support_keys:
            pts = points_by_support.get(sup, [])
            if len(pts) < 8:
                continue
            arr = np.asarray(pts, dtype=np.float64)
            if enhanced and sup != "CSBD":
                xc, curves = _binned_percentile_curves(arr[:, 0], arr[:, 1], bins=bins)
                if xc.size >= 3:
                    ax.fill_between(
                        xc,
                        curves[25.0],
                        curves[75.0],
                        color=support_colors.get(sup, "#6c757d"),
                        alpha=0.10,
                        zorder=3,
                    )
                    ax.plot(xc, curves[50.0], color=support_colors.get(sup, "#6c757d"), lw=1.8, alpha=0.85, zorder=6)
                    continue
            xc, yc = _binned_median_curve(arr[:, 0], arr[:, 1], bins=bins)
            if xc.size:
                ax.plot(xc, yc, color=support_colors.get(sup, "#6c757d"), lw=1.8)

        ax.set_title(MODE_TITLES.get(mode, mode), fontsize=11, pad=8)
        ax.set_xlabel("")
        if idx == 0:
            ax.set_ylabel("Dissipation, $\\Delta E / E$", fontsize=11, labelpad=7)
        else:
            ax.set_ylabel("")
            ax.tick_params(axis="y", labelleft=False)
        if x_limits is not None:
            ax.set_xlim(*x_limits)
        else:
            ax.set_xlim(left=0)
        if y_limits is not None:
            ax.set_ylim(*y_limits)
        ax.grid(False)
        ax.set_box_aspect(0.72)

    from matplotlib.lines import Line2D

    support_handles = support_marker_handles(supports, markersize=6.8)
    if axs.size > 0:
        axs[-1].legend(
        support_handles,
        supports,
        loc="upper right",
        ncol=1,
        fontsize=7.5,
        frameon=False,
        labelspacing=0.25,
        handletextpad=0.35,
        borderaxespad=0.45,
        )
    if axs.size > 1:
        axs[1].set_xlabel("Amplitude (mm/s)", fontsize=11, fontweight="normal", labelpad=8)
    fig.suptitle("Cycle Energy Dissipation ($\\Delta E / E$) vs Amplitude (mm/s)", fontsize=12, fontweight="bold", y=0.965)
    fig.tight_layout(rect=(0.03, 0.06, 0.98, 0.94), w_pad=1.1)
    return {"raw_points": len(raw_rows), "clean_points": len(ede_rows), **stats}
