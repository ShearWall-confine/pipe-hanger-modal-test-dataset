from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
from scipy.stats import gaussian_kde

from tools.paper_figure_style import SUPPORT_COLORS, SUPPORT_MARKERS, support_marker_handles

GROUP_COLORS = SUPPORT_COLORS

MODE_ORDER = ["radial", "axial", "planar_rotation"]
MODE_TITLES = {
    "radial": "(a) Radial",
    "axial": "(b) Axial",
    "planar_rotation": "(c) In-plane rotation",
}


def _apply_pub_axis_style(ax) -> None:
    for spine in ax.spines.values():
        spine.set_linewidth(1.2)
    ax.tick_params(direction="in", length=4, width=1.2)
    ax.grid(False)


def _iter_filtered_rows(rows_by_mode, mode):
    rows = rows_by_mode.get(mode, [])
    for r in rows:
        if (
            r.get("valid") is True
            and r.get("drift_valid") is True
            and float(r.get("drift_r_squared", 0) or 0) >= 0.05
        ):
            yield r


def _group_name(exp_id: str) -> str:
    return str(exp_id).split("_")[0]


def _row_length_m(row: dict) -> float:
    try:
        val = float(row.get("l_m", np.nan))
    except Exception:
        val = np.nan
    return val if np.isfinite(val) else np.nan


def _length_norm(rows_by_mode) -> Normalize | None:
    vals = []
    for mode in MODE_ORDER:
        for r in _iter_filtered_rows(rows_by_mode, mode):
            l_val = _row_length_m(r)
            if np.isfinite(l_val):
                vals.append(l_val)
    if not vals:
        return None
    arr = np.asarray(vals, dtype=np.float64)
    vmin = float(np.min(arr))
    vmax = float(np.max(arr))
    if not np.isfinite(vmin) or not np.isfinite(vmax):
        return None
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1e-9
    return Normalize(vmin=vmin, vmax=vmax)


def _group_rgba(group: str, alpha: float) -> tuple[float, float, float, float]:
    alpha = float(np.clip(alpha, 0.08, 1.0))
    import matplotlib.colors as mcolors

    rgb = mcolors.to_rgb(GROUP_COLORS[group])
    return (rgb[0], rgb[1], rgb[2], alpha)


def _collect_grouped_xy(rows_by_mode, mode):
    grouped_zeta = {k: [] for k in GROUP_COLORS.keys()}
    grouped_drift = {k: [] for k in GROUP_COLORS.keys()}

    for r in _iter_filtered_rows(rows_by_mode, mode):
        grp = _group_name(r.get("exp_id", ""))
        if grp not in grouped_zeta:
            continue
        try:
            zeta = float(r.get("zeta_hilbert", np.nan))
            drift = float(r.get("drift_ratio", np.nan))
        except Exception:
            continue
        if np.isfinite(zeta) and np.isfinite(drift):
            grouped_zeta[grp].append(zeta)
            grouped_drift[grp].append(drift)

    return (
        {k: np.asarray(v, dtype=np.float64) for k, v in grouped_zeta.items()},
        {k: np.asarray(v, dtype=np.float64) for k, v in grouped_drift.items()},
    )


def _collect_mode_stats(rows_by_mode, mode):
    stats = {}
    for grp in ["TB", "CA", "CSB", "CSBD"]:
        vals = []
        for r in _iter_filtered_rows(rows_by_mode, mode):
            if _group_name(r.get("exp_id", "")) != grp:
                continue
            try:
                zeta = float(r.get("zeta_hilbert", np.nan))
            except Exception:
                zeta = np.nan
            if np.isfinite(zeta):
                vals.append(zeta)
        arr = np.asarray(vals, dtype=np.float64)
        stats[grp] = {
            "n": int(arr.size),
            "median": float(np.median(arr)) if arr.size else np.nan,
        }
    return stats


def plot_frequency_drift_kde(
    rows_by_mode,
    out_path: str | Path | None = None,
    dpi: int = 400,
):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    legend_handles = []
    legend_labels = []

    for ax, mode in zip(axes, MODE_ORDER):
        grouped = {k: [] for k in GROUP_COLORS.keys()}
        for r in _iter_filtered_rows(rows_by_mode, mode):
            grp = _group_name(r.get("exp_id", ""))
            if grp not in grouped:
                continue
            try:
                val = float(r.get("drift_ratio", np.nan))
            except Exception:
                val = np.nan
            if np.isfinite(val):
                grouped[grp].append(val)

        grouped = {k: np.asarray(v, dtype=np.float64) for k, v in grouped.items() if len(v) > 1}
        all_vals = np.concatenate(list(grouped.values())) if grouped else np.array([], dtype=np.float64)
        if all_vals.size > 0:
            x_lo = float(np.min(all_vals))
            x_hi = float(np.max(all_vals))
            pad = max(0.02 * (x_hi - x_lo), 1e-4)
            x_grid = np.linspace(x_lo - pad, x_hi + pad, 400)
        else:
            x_grid = np.linspace(-0.05, 0.05, 400)

        for grp in ["CA", "TB", "CSBD", "CSB"]:
            vals = grouped.get(grp)
            if vals is None or vals.size < 2:
                continue
            kde = gaussian_kde(vals)
            y = kde(x_grid)
            line, = ax.plot(x_grid, y, color=GROUP_COLORS[grp], lw=2.0)
            ax.fill_between(x_grid, y, 0, color=GROUP_COLORS[grp], alpha=0.3)
            if grp not in legend_labels:
                legend_handles.append(line)
                legend_labels.append(grp)

        ax.axvline(0, color="k", linestyle="--", lw=1.5)
        ax.set_title(MODE_TITLES.get(mode, mode), fontsize=11)
        ax.set_xlabel(r"Normalized Frequency-Amplitude Sensitivity ($(1/f_n)\,df/dv_a$)")
        ax.set_yticks([])
        _apply_pub_axis_style(ax)

    axes[0].set_ylabel("Probability Density")
    fig.suptitle("Normalized Frequency-Amplitude Sensitivity KDE by Support Type and Mode", fontsize=11, fontweight="bold", y=0.975)
    fig.legend(legend_handles, legend_labels, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.92))
    fig.subplots_adjust(left=0.055, right=0.985, bottom=0.16, top=0.78, wspace=0.14)

    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    return fig, axes


def plot_damping_drift_correlation(
    rows_by_mode,
    out_path: str | Path | None = None,
    dpi: int = 400,
    enhanced: bool = False,
):
    fig, axes = plt.subplots(1, 3, figsize=(11.0, 4.3), sharey=True)
    norm = _length_norm(rows_by_mode)
    marker_map = SUPPORT_MARKERS
    all_zeta_values = []
    all_drift_values = []

    for mode in MODE_ORDER:
        for row in _iter_filtered_rows(rows_by_mode, mode):
            try:
                zeta = float(row.get("zeta_hilbert", np.nan))
                drift = float(row.get("drift_ratio", np.nan))
            except Exception:
                continue
            if np.isfinite(zeta) and np.isfinite(drift):
                all_zeta_values.append(zeta)
                all_drift_values.append(drift)

    x_limits = (-0.2, 0.05)

    y_limits = None
    if len(all_zeta_values) > 1:
        all_zeta = np.asarray(all_zeta_values, dtype=np.float64)
        y_lo = float(np.min(all_zeta))
        y_hi = float(np.max(all_zeta))
        pad = max(0.05 * (y_hi - y_lo), 1e-4)
        y_limits = (max(0.0, y_lo - pad), y_hi + pad)

    for idx, (ax, mode) in enumerate(zip(axes, MODE_ORDER)):
        grouped_zeta, grouped_drift = _collect_grouped_xy(rows_by_mode, mode)

        for grp in ["CA", "TB", "CSBD", "CSB"]:
            rows = [r for r in _iter_filtered_rows(rows_by_mode, mode) if _group_name(r.get("exp_id", "")) == grp]
            if not rows:
                continue
            x = []
            y = []
            colors = []
            for r in rows:
                try:
                    zeta = float(r.get("zeta_hilbert", np.nan))
                    drift = float(r.get("drift_ratio", np.nan))
                except Exception:
                    continue
                l_val = _row_length_m(r)
                if np.isfinite(zeta) and np.isfinite(drift):
                    if norm is not None and np.isfinite(l_val):
                        alpha = 0.22 + 0.73 * float(norm(l_val))
                    else:
                        alpha = 0.68
                    x.append(drift)
                    y.append(zeta)
                    colors.append(_group_rgba(grp, alpha))
            if not x:
                continue
            ax.scatter(
                np.asarray(x, dtype=np.float64),
                np.asarray(y, dtype=np.float64),
                c=colors,
                s=30,
                marker=marker_map.get(grp, "o"),
                edgecolors="white",
                linewidths=0.4,
            )

        ax.axvline(0, color="k", linestyle="--", lw=1.5)
        ax.set_title(MODE_TITLES.get(mode, mode), fontsize=11, pad=7)
        ax.set_xlabel("")
        if idx == 0:
            ax.set_ylabel(r"Equivalent Damping Ratio ($\zeta$)", fontsize=11, labelpad=7)
        else:
            ax.set_ylabel("")
            ax.tick_params(axis="y", labelleft=False)
        if y_limits is not None:
            ax.set_ylim(*y_limits)
        if x_limits is not None:
            ax.set_xlim(*x_limits)
        _apply_pub_axis_style(ax)
        ax.set_box_aspect(0.72)

        # Top horizontal marginal KDE of normalized frequency-amplitude sensitivity.
        # It spans the full panel width so the beta density aligns strictly with
        # the main scatter x positions.
        ax_kde_x = ax.inset_axes([0.00, 0.84, 1.00, 0.16], sharex=ax)
        if x_limits is not None:
            x_grid = np.linspace(x_limits[0], x_limits[1], 300)
            max_density_x = 0.0
            density_curves_x = []
            for grp in ["CA", "TB", "CSBD", "CSB"]:
                vals = grouped_drift.get(grp, np.array([], dtype=np.float64))
                if vals.size < 2:
                    continue
                kde = gaussian_kde(vals)
                dens = kde(x_grid)
                density_curves_x.append((grp, dens))
                max_density_x = max(max_density_x, float(np.max(dens)))

            if max_density_x > 0:
                for grp, dens in density_curves_x:
                    ax_kde_x.plot(x_grid, dens, color=GROUP_COLORS[grp], lw=1.4, alpha=0.95)
                    ax_kde_x.fill_between(x_grid, 0, dens, color=GROUP_COLORS[grp], alpha=0.18)
                ax_kde_x.set_ylim(max_density_x * 1.08, 0)

        ax_kde_x.set_facecolor("none")
        ax_kde_x.set_yticks([])
        ax_kde_x.tick_params(axis="x", which="both", bottom=False, top=False, labelbottom=False, labeltop=False)
        ax_kde_x.spines["left"].set_visible(False)
        ax_kde_x.spines["right"].set_visible(False)
        ax_kde_x.spines["bottom"].set_visible(False)
        ax_kde_x.spines["top"].set_visible(True)
        ax_kde_x.spines["top"].set_linewidth(1.0)
        ax_kde_x.spines["top"].set_color("#444444")
        ax_kde_x.margins(x=0.0)

        # Left-side vertical marginal KDE of equivalent damping ratio.
        # It spans the full panel height so the zeta density aligns strictly with
        # the main scatter y positions.
        ax_kde = ax.inset_axes([0.00, 0.00, 0.20, 1.00], sharey=ax)
        if y_limits is not None:
            y_grid = np.linspace(y_limits[0], y_limits[1], 300)
            max_density = 0.0
            density_curves = []
            for grp in ["CA", "TB", "CSBD", "CSB"]:
                vals = grouped_zeta.get(grp, np.array([], dtype=np.float64))
                if vals.size < 2:
                    continue
                kde = gaussian_kde(vals)
                dens = kde(y_grid)
                density_curves.append((grp, dens))
                max_density = max(max_density, float(np.max(dens)))

            if max_density > 0:
                for grp, dens in density_curves:
                    ax_kde.plot(dens, y_grid, color=GROUP_COLORS[grp], lw=1.4, alpha=0.95)
                    ax_kde.fill_betweenx(y_grid, 0, dens, color=GROUP_COLORS[grp], alpha=0.18)
                ax_kde.set_xlim(0, max_density * 1.08)

        ax_kde.set_facecolor("none")
        ax_kde.set_xticks([])
        ax_kde.tick_params(axis="y", which="both", left=False, right=False, labelleft=False, labelright=False)
        ax_kde.spines["left"].set_visible(True)
        ax_kde.spines["left"].set_linewidth(1.0)
        ax_kde.spines["left"].set_color("#444444")
        ax_kde.spines["top"].set_visible(False)
        ax_kde.spines["bottom"].set_visible(False)
        ax_kde.spines["right"].set_visible(False)
        ax_kde.margins(x=0.0)

        if enhanced:
            mode_stats = _collect_mode_stats(rows_by_mode, mode)
            lines = []
            for grp in ["TB", "CA", "CSB", "CSBD"]:
                s = mode_stats.get(grp, {})
                n = int(s.get("n", 0) or 0)
                med = float(s.get("median", np.nan))
                if n >= 2 and np.isfinite(med):
                    lines.append(f"{grp}: $\\zeta_{{med}}$={med:.3f}, n={n}")
                elif n == 1:
                    lines.append(f"{grp}: n=1 (insufficient)")
            if lines:
                ax.text(
                    0.03,
                    0.79,
                    "\n".join(lines),
                    transform=ax.transAxes,
                    fontsize=7,
                    va="top",
                    ha="left",
                    bbox=dict(
                        boxstyle="round,pad=0.35",
                        facecolor="white",
                        edgecolor="gray",
                        alpha=0.85,
                    ),
                    fontfamily="monospace",
                    zorder=8,
                )

    legend_handles = support_marker_handles(("CA", "TB", "CSBD", "CSB"), markersize=6.5)
    axes[-1].legend(
        legend_handles,
        ["CA", "TB", "CSBD", "CSB"],
        loc="upper left",
        ncol=2,
        frameon=False,
        fontsize=8,
        columnspacing=0.9,
        handletextpad=0.45,
        borderaxespad=0.45,
    )
    fig.suptitle(r"Normalized Frequency-Amplitude Sensitivity ($\beta$) vs Equivalent Damping Ratio", fontsize=12, fontweight="bold", y=0.965)
    axes[1].set_xlabel(r"$\beta$", fontsize=11, fontweight="normal", labelpad=8)
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.15, top=0.86, wspace=0.20)

    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    return fig, axes
