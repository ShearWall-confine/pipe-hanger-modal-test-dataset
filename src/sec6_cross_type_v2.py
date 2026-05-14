from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "derived"
RESIDUAL_CSV = PROCESSED_DIR / "sec6_cross_type_v2_residuals.csv"

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("USERPROFILE", str(PROJECT_ROOT))
os.environ.setdefault("HOME", str(PROJECT_ROOT))
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".mplconfig"))
(PROJECT_ROOT / ".mplconfig").mkdir(parents=True, exist_ok=True)

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

MODES = ("radial", "axial", "planar_rotation")
MODE_TITLE = {
    "radial": "(a) Radial",
    "axial": "(b) Axial",
    "planar_rotation": "(c) In-plane rotation",
}
SUPPORTS = ("TB", "CSB", "CSBD")
SUPPORT_STYLE = {
    "TB": {"color": "#2166AC", "marker": "o", "filled": True, "size": 25},
    "CSB": {"color": "#B2182B", "marker": "^", "filled": False, "size": 45},
    "CSBD": {"color": "#4DAF4A", "marker": "s", "filled": False, "size": 45},
}


def _prepare_runtime() -> None:
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("USERPROFILE", str(PROJECT_ROOT))
    os.environ.setdefault("HOME", str(PROJECT_ROOT))
    os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".mplconfig"))
    (PROJECT_ROOT / ".mplconfig").mkdir(parents=True, exist_ok=True)
    os.chdir(CODE_ROOT)
    if str(CODE_ROOT) not in sys.path:
        sys.path.insert(0, str(CODE_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Section 6.2 cross-type validation in frequency space.")
    return parser.parse_args()


def enrich_row(row: dict, workbench, a_all: float, b_all: float) -> dict | None:
    if not (
        np.isfinite(row.get("m", np.nan))
        and np.isfinite(row.get("l", np.nan))
        and np.isfinite(row.get("r", np.nan))
        and np.isfinite(row.get("f_exp", np.nan))
    ):
        return None
    if row["m"] <= 0 or row["l"] <= 0 or row["r"] <= 0 or row["f_exp"] <= 0:
        return None

    rr = dict(row)
    rr["support_type"] = workbench.get_support_group(rr["exp_id"])
    if rr["support_type"] not in SUPPORTS:
        return None
    rr["pi_l"] = rr["l"] / rr["r"]
    rr["pi_k_pred"] = a_all * (rr["pi_l"] ** b_all)
    rr["k_fit"] = rr["pi_k_pred"] * rr["m"] * workbench.G_ACCEL * rr["r"]
    rr["f_pred"] = workbench._calc_mode_f_fit(rr["mode"], rr["m"], rr["l"], rr["k_fit"])
    rr["rel_error"] = (rr["f_pred"] - rr["f_exp"]) / rr["f_exp"] if rr["f_exp"] != 0 else np.nan
    if not (np.isfinite(rr["pi_l"]) and rr["pi_l"] > 0 and np.isfinite(rr["f_pred"])):
        return None
    return rr


def compute_mode_r2(rows: list[dict]) -> float:
    y_true = np.asarray([float(row["f_exp"]) for row in rows], dtype=np.float64)
    y_pred = np.asarray([float(row["f_pred"]) for row in rows], dtype=np.float64)
    good = np.isfinite(y_true) & np.isfinite(y_pred)
    if np.count_nonzero(good) < 2:
        return np.nan
    y_true = y_true[good]
    y_pred = y_pred[good]
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan


def plot_support_scatter(ax, xs: np.ndarray, ys: np.ndarray, style: dict) -> None:
    if style["filled"]:
        ax.scatter(xs, ys, s=style["size"], marker=style["marker"], color=style["color"], alpha=0.9, zorder=3)
    else:
        ax.scatter(
            xs,
            ys,
            s=style["size"],
            marker=style["marker"],
            facecolors="none",
            edgecolors=style["color"],
            linewidths=1.2,
            alpha=0.95,
            zorder=3,
        )


def plot_panel(
    fig,
    spec,
    rows: list[dict],
    mode: str,
    r2_text: float,
    *,
    annotate_formula: bool = False,
    top_limits: tuple[float, float] | None = None,
    bottom_x_limits: tuple[float, float] | None = None,
    bottom_y_limit: float | None = None,
    share_top_with: plt.Axes | None = None,
    share_bot_with: plt.Axes | None = None,
) -> tuple[plt.Axes, plt.Axes]:
    sub = spec.subgridspec(2, 1, height_ratios=[7.4, 3], hspace=0.52)
    if share_top_with is None:
        ax_top = fig.add_subplot(sub[0, 0])
    else:
        ax_top = fig.add_subplot(sub[0, 0], sharex=share_top_with, sharey=share_top_with)
    if share_bot_with is None:
        ax_bot = fig.add_subplot(sub[1, 0])
    else:
        ax_bot = fig.add_subplot(sub[1, 0], sharex=share_bot_with, sharey=share_bot_with)

    f_exp_all = np.asarray([float(row["f_exp"]) for row in rows], dtype=np.float64)
    f_pred_all = np.asarray([float(row["f_pred"]) for row in rows], dtype=np.float64)
    pi_l_all = np.asarray([float(row["pi_l"]) for row in rows], dtype=np.float64)
    rel_all = np.asarray([float(row["rel_error"]) for row in rows], dtype=np.float64)

    if top_limits is None:
        f_min = float(min(np.nanmin(f_exp_all), np.nanmin(f_pred_all)))
        f_max = float(max(np.nanmax(f_exp_all), np.nanmax(f_pred_all)))
        pad = 0.04 * (f_max - f_min if f_max > f_min else max(f_max, 1.0))
        lo = max(0.0, f_min - pad)
        hi = f_max + pad
    else:
        lo, hi = top_limits
    line = np.linspace(lo, hi, 200)

    ax_top.fill_between(line, 0.95 * line, 1.05 * line, color="#D9D9D9", alpha=0.3, zorder=0)
    ax_top.plot(line, line, color="black", lw=1.1, zorder=1)
    ax_top.plot(line, 1.10 * line, color="#7F7F7F", lw=0.9, ls="--", zorder=1)
    ax_top.plot(line, 0.90 * line, color="#7F7F7F", lw=0.9, ls="--", zorder=1)

    for support in SUPPORTS:
        s_rows = [row for row in rows if row["support_type"] == support]
        if not s_rows:
            continue
        xs = np.asarray([row["f_exp"] for row in s_rows], dtype=np.float64)
        ys = np.asarray([row["f_pred"] for row in s_rows], dtype=np.float64)
        plot_support_scatter(ax_top, xs, ys, SUPPORT_STYLE[support])

    ax_top.set_xlim(lo, hi)
    ax_top.set_ylim(lo, hi)
    ax_top.set_aspect("equal", adjustable="box")
    locator = MaxNLocator(nbins=5)
    tick_vals = locator.tick_values(lo, hi)
    tick_vals = tick_vals[(tick_vals >= lo - 1e-12) & (tick_vals <= hi + 1e-12)]
    ax_top.set_xticks(tick_vals)
    ax_top.set_yticks(tick_vals)
    ax_top.set_title(MODE_TITLE[mode], fontsize=8, pad=3)
    ax_top.set_xlabel("")
    ax_top.set_ylabel(r"$f_{\mathrm{pred}}$  (Hz)", fontsize=8)
    ax_top.tick_params(labelsize=7, direction="in")
    ax_top.grid(False)
    ax_top.text(
        0.04,
        0.95,
        rf"$R^2 = {r2_text:.3f}$" + f"\n" + f"n = {len(rows)}",
        transform=ax_top.transAxes,
        ha="left",
        va="top",
        fontsize=7,
        bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "none", "pad": 1.8},
    )

    ax_bot.axhspan(-0.05, 0.05, color="#D9D9D9", alpha=0.3, zorder=0)
    ax_bot.axhline(0.0, color="black", lw=0.9, ls="--", zorder=1)
    ax_bot.axhline(0.10, color="#7F7F7F", lw=0.8, ls="--", zorder=1)
    ax_bot.axhline(-0.10, color="#7F7F7F", lw=0.8, ls="--", zorder=1)

    for support in SUPPORTS:
        s_rows = [row for row in rows if row["support_type"] == support]
        if not s_rows:
            continue
        xs = np.asarray([row["pi_l"] for row in s_rows], dtype=np.float64)
        ys = np.asarray([row["rel_error"] for row in s_rows], dtype=np.float64)
        plot_support_scatter(ax_bot, xs, ys, SUPPORT_STYLE[support])

    if bottom_x_limits is None:
        pi_l_lo = float(np.nanmin(pi_l_all))
        pi_l_hi = float(np.nanmax(pi_l_all))
        xpad = 0.04 * (pi_l_hi - pi_l_lo if pi_l_hi > pi_l_lo else max(pi_l_hi, 1.0))
        x_lo, x_hi = pi_l_lo - xpad, pi_l_hi + xpad
    else:
        x_lo, x_hi = bottom_x_limits
    ax_bot.set_xlim(x_lo, x_hi)
    if bottom_y_limit is None:
        rel_max = float(np.nanmax(np.abs(rel_all))) if np.any(np.isfinite(rel_all)) else 0.1
        rel_lim = max(0.12, min(0.40, rel_max * 1.10))
    else:
        rel_lim = bottom_y_limit
    ax_bot.set_ylim(-rel_lim, rel_lim)
    ax_bot.set_xlabel("")
    ax_bot.set_ylabel("Relative error", fontsize=8)
    ax_bot.tick_params(labelsize=7, direction="in")
    ax_bot.grid(False)
    if annotate_formula:
        ax_bot.text(
            0.03,
            0.95,
            r"$e=(f_{\mathrm{pred}}-f_{\mathrm{exp}})/f_{\mathrm{exp}}$",
            transform=ax_bot.transAxes,
            ha="left",
            va="top",
            fontsize=6,
            color="black",
        )

    return ax_top, ax_bot


def save_figure(fig, workbench) -> None:
    out_base = workbench.WORKBENCH_OUT_DIR / "13_cross_type_validation"
    workbench.style_figure(fig, theme=workbench.WORD_THEME, grid=False)
    workbench.apply_insert_text_style_for_figure(fig, latex_text_width_in=6.45, pad_inches=0.0)
    workbench.save_figure_bundle(
        fig,
        out_base,
        formats=("png", "tiff", "pdf"),
        dpi=600,
        split_format_dirs=True,
        bbox_inches="tight",
    )
    workbench._remove_legacy_figure_outputs("13_cross_type_validation")


def align_bottom_axes_to_top_width(fig, top_axes: list[plt.Axes], bottom_axes: list[plt.Axes]) -> None:
    """Match lower residual-panel widths to the equal-aspect upper panels."""
    fig.canvas.draw()
    for ax_top, ax_bot in zip(top_axes, bottom_axes):
        top_pos = ax_top.get_position()
        bot_pos = ax_bot.get_position()
        ax_bot.set_position([top_pos.x0, bot_pos.y0, top_pos.width, bot_pos.height])


def main() -> None:
    parse_args()
    _prepare_runtime()

    import logic.paper_plot_workbench as workbench

    ctx = workbench.prepare_dimscaling_context()
    rows_by_mode = ctx["rows_by_mode"]
    stats_by_mode = ctx["stats_by_mode"]

    csv_rows: list[dict] = []
    panel_payload: dict[str, list[dict]] = {}

    for mode in MODES:
        rows_mode = rows_by_mode.get(mode, [])
        oth_stats = stats_by_mode[mode]["OTHERS"]
        a_all = float(oth_stats.A)
        b_all = float(oth_stats.B)

        mode_rows = []
        for row in rows_mode:
            if workbench.get_fit_group(row["exp_id"]) != "OTHERS":
                continue
            enriched = enrich_row(row, workbench, a_all, b_all)
            if enriched is None:
                continue
            mode_rows.append(enriched)
            csv_rows.append(
                {
                    "mode": mode,
                    "support_type": enriched["support_type"],
                    "exp_id": enriched["exp_id"],
                    "f_exp": enriched["f_exp"],
                    "f_pred": enriched["f_pred"],
                    "rel_error": enriched["rel_error"],
                    "pi_l": enriched["pi_l"],
                }
            )
        panel_payload[mode] = mode_rows

    RESIDUAL_CSV.parent.mkdir(parents=True, exist_ok=True)
    with RESIDUAL_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["mode", "support_type", "exp_id", "f_exp", "f_pred", "rel_error", "pi_l"],
        )
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"[DONE] wrote {RESIDUAL_CSV}")

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "mathtext.default": "it",
            "font.size": 7,
            "axes.labelsize": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
        }
    )

    mm_to_in = 1.0 / 25.4
    fig = plt.figure(figsize=(180.0 * mm_to_in, 105.0 * mm_to_in), dpi=600)
    fig.subplots_adjust(left=0.08, right=0.995, top=0.91, bottom=0.18, wspace=0.20)
    gs = fig.add_gridspec(1, 3, wspace=0.20)

    all_f = []
    all_pi_l = []
    all_rel = []
    for mode in MODES:
        rows = panel_payload[mode]
        all_f.extend(float(row["f_exp"]) for row in rows)
        all_f.extend(float(row["f_pred"]) for row in rows)
        all_pi_l.extend(float(row["pi_l"]) for row in rows)
        all_rel.extend(float(row["rel_error"]) for row in rows if np.isfinite(row["rel_error"]))

    f_arr = np.asarray(all_f, dtype=np.float64)
    f_min = float(np.nanmin(f_arr))
    f_max = float(np.nanmax(f_arr))
    f_pad = 0.04 * (f_max - f_min if f_max > f_min else max(f_max, 1.0))
    shared_top_limits = (max(0.0, f_min - f_pad), f_max + f_pad)

    pi_l_arr = np.asarray(all_pi_l, dtype=np.float64)
    pi_l_min = float(np.nanmin(pi_l_arr))
    pi_l_max = float(np.nanmax(pi_l_arr))
    pi_l_pad = 0.04 * (pi_l_max - pi_l_min if pi_l_max > pi_l_min else max(pi_l_max, 1.0))
    shared_bottom_x_limits = (pi_l_min - pi_l_pad, pi_l_max + pi_l_pad)

    rel_arr = np.asarray(all_rel, dtype=np.float64)
    rel_max = float(np.nanmax(np.abs(rel_arr))) if rel_arr.size else 0.1
    shared_bottom_y_limit = max(0.12, min(0.40, rel_max * 1.10))

    r2_report_lines = []
    top_axes = []
    bottom_axes = []
    for idx, mode in enumerate(MODES):
        rows = panel_payload[mode]
        ax_top, ax_bot = plot_panel(
            fig,
            gs[0, idx],
            rows,
            mode,
            float(stats_by_mode[mode]["OTHERS"].r2),
            annotate_formula=(idx == 0),
            top_limits=shared_top_limits,
            bottom_x_limits=shared_bottom_x_limits,
            bottom_y_limit=shared_bottom_y_limit,
            share_top_with=(top_axes[0] if top_axes else None),
            share_bot_with=(bottom_axes[0] if bottom_axes else None),
        )
        if idx > 0:
            ax_top.set_ylabel("")
            ax_top.tick_params(axis="y", labelleft=False)
        top_axes.append(ax_top)
        bottom_axes.append(ax_bot)
        r2_actual = compute_mode_r2(rows)
        r2_reported = float(stats_by_mode[mode]["OTHERS"].r2)
        r2_report_lines.append((mode, len(rows), r2_actual, r2_reported))

    for idx, ax in enumerate(bottom_axes):
        if idx > 0:
            ax.set_ylabel("")
            ax.tick_params(axis="y", labelleft=False)

    top_axes[1].set_xlabel(r"$f_{\mathrm{exp}}$  (Hz)", fontsize=8, labelpad=7)
    bottom_axes[1].set_xlabel(r"Length ratio, $l/r$", fontsize=8, labelpad=4)

    legend_handles = []
    for support in SUPPORTS:
        style = SUPPORT_STYLE[support]
        if style["filled"]:
            legend_handles.append(
                Line2D(
                    [0],
                    [0],
                    marker=style["marker"],
                    color="none",
                    markerfacecolor=style["color"],
                    markeredgecolor=style["color"],
                    markersize=5.5,
                    label=support,
                )
            )
        else:
            legend_handles.append(
                Line2D(
                    [0],
                    [0],
                    marker=style["marker"],
                    color="none",
                    markerfacecolor="white",
                    markeredgecolor=style["color"],
                    markeredgewidth=1.2,
                    markersize=6.0,
                    label=support,
                )
            )
    legend_handles.append(Line2D([0], [0], color="black", lw=1.1, label="SR fit"))
    legend_handles.append(Patch(facecolor="#D9D9D9", edgecolor="none", alpha=0.3, label="±5%"))
    legend_handles.append(Line2D([0], [0], color="#7F7F7F", lw=0.9, ls="--", label="±10%"))
    top_axes[0].legend(
        handles=legend_handles,
        loc="lower right",
        ncol=1,
        frameon=False,
        fontsize=6.5,
        bbox_to_anchor=(0.98, 0.02),
        borderaxespad=0.0,
        handlelength=1.4,
        handletextpad=0.5,
        labelspacing=0.25,
    )

    align_bottom_axes_to_top_width(fig, top_axes, bottom_axes)
    save_figure(fig, workbench)
    plt.close(fig)
    print("[DONE] saved Figure 13 to workbench_ordered/pdf|png|tiff")
    for mode, n_rows, r2_actual, r2_reported in r2_report_lines:
        print(f"[R2] mode={mode} n={n_rows} actual={r2_actual:.12f} reported={r2_reported:.12f}")


if __name__ == "__main__":
    main()
