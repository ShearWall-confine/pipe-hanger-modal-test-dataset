"""Core damping extraction algorithms.

This module is the numerical core used by:
- damping_batch.py for batch extraction
- damping_stats.py for diagnostics and advanced plots
- modal_h5_viewer.py damping tab integration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

import numpy as np
from scipy.signal import butter, find_peaks, hilbert, medfilt, savgol_filter, sosfiltfilt
from scipy.stats import linregress

LOGGER = logging.getLogger(__name__)
EPS = 1e-12
BAND_REJECTION_MIN_DB = 20.0


@dataclass
class DampingResult:
    """Single-channel, single-mode damping extraction output."""

    channel_id: str
    mode: str
    freq_target: float
    zeta_hilbert: float
    zeta_log_dec: float
    r_squared: float
    band_rejection_db: float
    peak_count: int
    t_start: float
    t_end: float
    amplitude_at_start: float
    envelope_time: np.ndarray
    envelope_amplitude: np.ndarray
    backbone: BackboneMetric
    valid: bool
    reject_reason: str


@dataclass
class CycleDamping:
    """Local damping estimated over one cycle-length envelope window."""

    amplitude: float
    zeta_local: float
    t_mid: float


@dataclass
class BackboneMetric:
    """Single-channel, single-mode frequency-amplitude sensitivity metric."""

    channel_id: str
    mode: str
    freq_target: float
    drift_ratio: float
    drift_slope: float
    amplitude_range: float
    r_squared: float
    valid: bool
    reject_reason: str


def _safe_polyfit_r2(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if x.size < 2 or y.size < 2:
        return np.nan, np.nan
    coef = np.polyfit(x, y, 1)
    y_hat = np.polyval(coef, x)
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / max(ss_tot, EPS)
    return float(coef[0]), float(r2)


def _invalid_backbone(channel_id: str, mode: str, freq_target: float, reason: str) -> BackboneMetric:
    return BackboneMetric(
        channel_id=channel_id,
        mode=mode,
        freq_target=float(freq_target),
        drift_ratio=np.nan,
        drift_slope=np.nan,
        amplitude_range=np.nan,
        r_squared=np.nan,
        valid=False,
        reject_reason=reason,
    )


def compute_backbone_metric(
    envelope_time: np.ndarray,
    envelope_amplitude: np.ndarray,
    inst_frequency: np.ndarray,
    freq_target: float,
    channel_id: str,
    mode: str,
    freq_band_factor: float = 0.20,
) -> BackboneMetric:
    """Compute normalized frequency-amplitude slope from a single decay curve."""
    n = int(min(envelope_amplitude.size, inst_frequency.size))
    if n < 20 or freq_target <= 0:
        return _invalid_backbone(channel_id, mode, freq_target, "insufficient_points")

    amp = np.asarray(envelope_amplitude[:n], dtype=np.float64)
    freq = np.asarray(inst_frequency[:n], dtype=np.float64)

    finite_mask = np.isfinite(amp) & np.isfinite(freq)
    amp = amp[finite_mask]
    freq = freq[finite_mask]
    if amp.size < 20:
        return _invalid_backbone(channel_id, mode, freq_target, "insufficient_points")

    k = 5 if amp.size >= 5 else 3
    if k % 2 == 0:
        k += 1
    if k > 3:
        freq = medfilt(freq, kernel_size=k)

    low = freq_target * (1.0 - freq_band_factor)
    high = freq_target * (1.0 + freq_band_factor)
    band_mask = (freq >= low) & (freq <= high)
    amp = amp[band_mask]
    freq = freq[band_mask]
    if amp.size < 20:
        return _invalid_backbone(channel_id, mode, freq_target, "insufficient_points")

    reg = linregress(amp, freq)
    slope = float(reg.slope)
    r2 = float(reg.rvalue * reg.rvalue)
    a_range = float(np.max(amp) - np.min(amp))
    # Normalize the frequency-amplitude slope by the target frequency so records
    # with different amplitude ranges remain comparable.
    drift_ratio = float(slope / max(freq_target, EPS))

    if r2 < 0.05:
        return BackboneMetric(
            channel_id=channel_id,
            mode=mode,
            freq_target=float(freq_target),
            drift_ratio=drift_ratio,
            drift_slope=slope,
            amplitude_range=a_range,
            r_squared=r2,
            valid=False,
            reject_reason="no_trend",
        )
    return BackboneMetric(
        channel_id=channel_id,
        mode=mode,
        freq_target=float(freq_target),
        drift_ratio=drift_ratio,
        drift_slope=slope,
        amplitude_range=a_range,
        r_squared=r2,
        valid=True,
        reject_reason="ok",
    )


def _bandpass_butter(
    signal: np.ndarray,
    fs: float,
    f_center: float,
    bandwidth_pct: float,
    order: int,
) -> tuple[np.ndarray, float, float, bool]:
    nyq = 0.5 * fs
    bw = max(bandwidth_pct, 0.1) / 100.0
    low = f_center * (1.0 - bw)
    high = f_center * (1.0 + bw)
    clipped = False

    if low <= 0:
        low = max(0.01, f_center * 0.1)
        clipped = True
    if high >= nyq:
        high = nyq * 0.98
        clipped = True
    if low >= high:
        low = max(0.01, min(f_center * 0.5, nyq * 0.4))
        high = min(max(f_center * 1.5, low * 1.2), nyq * 0.98)
        clipped = True

    wn = [low / nyq, high / nyq]
    sos = butter(order, wn, btype="bandpass", output="sos")
    y = sosfiltfilt(sos, signal)
    return y, low, high, clipped


def _band_rejection_db(filtered_signal: np.ndarray, fs: float, low: float, high: float) -> float:
    n = filtered_signal.size
    if n < 8:
        return -np.inf
    freq = np.fft.rfftfreq(n, d=1.0 / fs)
    mag = np.abs(np.fft.rfft(filtered_signal))
    in_band = (freq >= low) & (freq <= high)
    if not np.any(in_band):
        return -np.inf
    target_peak = float(np.max(mag[in_band]))
    out_peak = float(np.max(mag[~in_band])) if np.any(~in_band) else 0.0
    if out_peak <= EPS:
        return 120.0
    return float(20.0 * np.log10(max(target_peak, EPS) / max(out_peak, EPS)))


def extract_damping_single(
    time: np.ndarray,
    signal: np.ndarray,
    freq_target: float,
    channel_id: str,
    mode: str,
    fs: float,
    bandwidth_pct: float = 15.0,
    butter_order: int = 4,
    min_cycles: int = 5,
    envelope_tail_threshold: float = 0.05,
    band_rejection_min_db: float = BAND_REJECTION_MIN_DB,
) -> DampingResult:
    """Extract damping ratio using Hilbert envelope and log decrement checks."""
    # ── Step 0: Input guards ─────────────────────────────────────────────────────
    valid = True
    reject_reason = ""
    warning_notes: List[str] = []
    zeta_hilbert = np.nan
    zeta_log_dec = np.nan
    r_squared = np.nan
    band_db = -np.inf
    peak_count = 0

    if time.size != signal.size or time.size < 8 or fs <= 0 or freq_target <= 0:
        return DampingResult(
            channel_id=channel_id,
            mode=mode,
            freq_target=float(freq_target),
            zeta_hilbert=zeta_hilbert,
            zeta_log_dec=zeta_log_dec,
            r_squared=r_squared,
            band_rejection_db=band_db,
            peak_count=peak_count,
            t_start=float(time[0]) if time.size else 0.0,
            t_end=float(time[-1]) if time.size else 0.0,
            amplitude_at_start=np.nan,
            envelope_time=np.asarray([], dtype=np.float64),
            envelope_amplitude=np.asarray([], dtype=np.float64),
            backbone=_invalid_backbone(channel_id, mode, freq_target, "invalid_input"),
            valid=False,
            reject_reason="invalid_input",
        )

    # ── Step 1: Butterworth bandpass (zero-phase) ───────────────────────────────
    try:
        sig_filt, low, high, clipped = _bandpass_butter(signal, fs, freq_target, bandwidth_pct, butter_order)
    except Exception as exc:
        LOGGER.warning("Bandpass failed for %s/%s: %s", channel_id, mode, exc)
        return DampingResult(
            channel_id=channel_id,
            mode=mode,
            freq_target=float(freq_target),
            zeta_hilbert=np.nan,
            zeta_log_dec=np.nan,
            r_squared=np.nan,
            band_rejection_db=-np.inf,
            peak_count=0,
            t_start=float(time[0]),
            t_end=float(time[-1]),
            amplitude_at_start=np.nan,
            envelope_time=np.asarray([], dtype=np.float64),
            envelope_amplitude=np.asarray([], dtype=np.float64),
            backbone=_invalid_backbone(channel_id, mode, freq_target, "filter_failed"),
            valid=False,
            reject_reason="filter_failed",
        )
    if clipped:
        warning_notes.append("frequency_clipped")

    # ── Step 2: Band rejection quality check ─────────────────────────────────────
    band_db = _band_rejection_db(sig_filt, fs, low, high)
    if band_db < band_rejection_min_db:
        valid = False
        reject_reason = "poor_band_rejection"

    # ── Step 3: Hilbert transform (envelope + instantaneous frequency) ──────────
    analytic = hilbert(sig_filt)
    envelope = np.abs(analytic)
    phase = np.unwrap(np.angle(analytic))
    dt = float(np.median(np.diff(time)))
    inst_frequency_full = np.diff(phase) / (2.0 * np.pi * dt)
    inst_time_full = time[1:]

    # ── Step 4: Automatic decay window detection ─────────────────────────────────
    idx_peak = int(np.argmax(envelope))
    env_peak = float(envelope[idx_peak])
    threshold = envelope_tail_threshold * env_peak
    tail_idx = None
    for idx in range(idx_peak, envelope.size):
        if envelope[idx] <= threshold:
            tail_idx = idx
            break
    if tail_idx is None:
        tail_idx = envelope.size - 1

    t_start_raw = float(time[idx_peak])
    t_end_raw = float(time[tail_idx])

    trim = 0.5 / max(freq_target, EPS)
    t_start_fit = t_start_raw + trim
    t_end_fit = t_end_raw - trim
    if t_end_fit <= t_start_fit:
        t_start_fit = t_start_raw
        t_end_fit = t_end_raw

    fit_mask = (time >= t_start_fit) & (time <= t_end_fit)
    decay_mask = (time >= t_start_raw) & (time <= t_end_raw)
    if np.sum(fit_mask) < 8 or (t_end_fit - t_start_fit) * freq_target < min_cycles:
        valid = False
        reject_reason = "too_short"

    envelope_time = time[decay_mask]
    envelope_amp = envelope[decay_mask]
    inst_decay_mask = (inst_time_full >= t_start_raw) & (inst_time_full <= t_end_raw)
    inst_frequency = inst_frequency_full[inst_decay_mask]

    # ── Step 5: Hilbert envelope exponential fit ─────────────────────────────────
    env_fit = envelope[fit_mask]
    t_fit = time[fit_mask]
    pos_mask = env_fit > EPS
    if np.sum(pos_mask) >= 8:
        y = np.log(env_fit[pos_mask])
        x = t_fit[pos_mask]
        slope, r_squared = _safe_polyfit_r2(x, y)
        zeta_hilbert = float(-slope / (2.0 * np.pi * freq_target))
    else:
        valid = False
        reject_reason = "too_short"

    # ── Step 6: Log decrement cross-check ────────────────────────────────────────
    sig_decay = sig_filt[fit_mask]
    peaks_idx, _ = find_peaks(sig_decay)
    if peaks_idx.size < 3:
        peaks_idx, _ = find_peaks(np.abs(sig_decay))
    if peaks_idx.size >= 3:
        amps = np.abs(sig_decay[peaks_idx])
        amps = amps[amps > EPS]
        if amps.size >= 3:
            delta = np.log(amps[:-1] / amps[1:])
            delta = delta[np.isfinite(delta)]
            if delta.size > 0:
                d_mean = float(np.mean(delta))
                zeta_log_dec = float(d_mean / np.sqrt(4.0 * np.pi * np.pi + d_mean * d_mean))
                peak_count = int(amps.size)

    # ── Step 7: Composite validity rules ─────────────────────────────────────────
    if np.isfinite(r_squared) and r_squared < 0.90:
        valid = False
        reject_reason = "low_r_squared"
    if np.isfinite(zeta_hilbert) and (zeta_hilbert < 0.0 or zeta_hilbert > 0.3):
        valid = False
        reject_reason = "unrealistic_zeta"
    if np.isfinite(zeta_hilbert) and np.isfinite(zeta_log_dec) and abs(zeta_hilbert) > EPS:
        rel = abs(zeta_hilbert - zeta_log_dec) / abs(zeta_hilbert)
        if rel > 0.3:
            valid = False
            reject_reason = "method_disagreement"
    elif not np.isfinite(zeta_log_dec):
        valid = False
        if not reject_reason:
            reject_reason = "insufficient_peaks"

    if valid and warning_notes:
        reject_reason = f"warning:{'|'.join(warning_notes)}"

    backbone_metric = compute_backbone_metric(
        envelope_time=envelope_time,
        envelope_amplitude=envelope_amp,
        inst_frequency=inst_frequency,
        freq_target=freq_target,
        channel_id=channel_id,
        mode=mode,
    )

    return DampingResult(
        channel_id=channel_id,
        mode=mode,
        freq_target=float(freq_target),
        zeta_hilbert=float(zeta_hilbert) if np.isfinite(zeta_hilbert) else np.nan,
        zeta_log_dec=float(zeta_log_dec) if np.isfinite(zeta_log_dec) else np.nan,
        r_squared=float(r_squared) if np.isfinite(r_squared) else np.nan,
        band_rejection_db=float(band_db),
        peak_count=int(peak_count),
        t_start=float(t_start_raw),
        t_end=float(t_end_raw),
        amplitude_at_start=float(env_peak),
        envelope_time=np.asarray(envelope_time, dtype=np.float64),
        envelope_amplitude=np.asarray(envelope_amp, dtype=np.float64),
        backbone=backbone_metric,
        valid=bool(valid),
        reject_reason=reject_reason if reject_reason else "ok",
    )


def compute_cycle_damping(
    envelope_time: np.ndarray,
    envelope_amplitude: np.ndarray,
    freq_target: float,
    window_cycles: float = 4.0,
    overlap: float = 0.5,
    sg_cycles: float = 2.5,
    sg_polyorder: int = 2,
    min_r2: float = 0.7,
) -> List[CycleDamping]:
    """Compute local damping using 3-5 cycle sliding windows with overlap."""
    if envelope_time.size < 8 or envelope_amplitude.size < 8 or freq_target <= 0:
        return []

    # ── Step 1: Savitzky-Golay smoothing on envelope ─────────────────────────────
    dt = float(np.median(np.diff(envelope_time)))
    if dt <= 0:
        return []
    period = 1.0 / freq_target
    sg_n = int(max(5, round((sg_cycles * period) / dt)))
    if sg_n % 2 == 0:
        sg_n += 1
    if sg_n >= envelope_amplitude.size:
        sg_n = envelope_amplitude.size - 1 if envelope_amplitude.size % 2 == 0 else envelope_amplitude.size
    if sg_n < 5:
        return []
    env_smooth = savgol_filter(envelope_amplitude, window_length=sg_n, polyorder=min(sg_polyorder, sg_n - 1), mode="interp")
    env_smooth = np.clip(env_smooth, EPS, None)

    # ── Step 2: 3~5 cycle sliding window with 50% overlap ───────────────────────
    win_len = max(3.0, min(5.0, float(window_cycles))) * period
    step = max(win_len * (1.0 - overlap), period * 0.5)
    t0 = float(envelope_time[0])
    t1 = float(envelope_time[-1])
    cycles: List[CycleDamping] = []
    w_start = t0
    while w_start + win_len <= t1 + EPS:
        w_end = w_start + win_len
        mask = (envelope_time >= w_start) & (envelope_time <= w_end)
        if np.sum(mask) >= 6:
            t_win = envelope_time[mask]
            a_win = env_smooth[mask]
            pos = a_win > EPS
            if np.sum(pos) >= 6:
                slope, r2 = _safe_polyfit_r2(t_win[pos], np.log(a_win[pos]))
                zeta_local = float(-slope / (2.0 * np.pi * freq_target))
                # ── Step 3: reject low quality windows ───────────────────────────
                if np.isfinite(r2) and r2 >= min_r2 and zeta_local >= 0.0:
                    cycles.append(
                        CycleDamping(
                            amplitude=float(np.mean(a_win[pos])),
                            zeta_local=zeta_local,
                            t_mid=float(0.5 * (w_start + w_end)),
                        )
                    )
        w_start += step
    return cycles
