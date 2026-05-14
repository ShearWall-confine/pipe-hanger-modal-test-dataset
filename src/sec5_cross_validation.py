from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "derived"
RESULT_CSV = PROCESSED_DIR / "sec5_cv_results.csv"

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("USERPROFILE", str(PROJECT_ROOT))
os.environ.setdefault("HOME", str(PROJECT_ROOT))
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".mplconfig"))
(PROJECT_ROOT / ".mplconfig").mkdir(parents=True, exist_ok=True)

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from scipy.optimize import curve_fit

GROUPS = ("CA", "OTHERS")
MODES = ("radial", "axial", "planar_rotation")
MODE_TITLE = {
    "radial": "(a) Radial",
    "axial": "(b) Axial",
    "planar_rotation": "(c) In-plane rotation",
}
GROUP_STYLE = {
    "CA": {"color": "#C43C39", "marker": "o", "size": 18},
    "OTHERS": {"color": "#2166AC", "marker": "s", "size": 18},
}
GROUP_LABEL = {
    "CA": "CA",
    "OTHERS": "SR",
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
    parser = argparse.ArgumentParser(description="Section 5 cross-validation for dimscaling power law.")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def power_law(pi_l: np.ndarray, a_val: float, b_val: float) -> np.ndarray:
    return a_val * np.power(pi_l, b_val)


def build_valid_group_rows(workbench, rows_mode: list[dict], fit_group: str) -> list[dict]:
    valid = []
    for row in rows_mode:
        if workbench.get_fit_group(row["exp_id"]) != fit_group:
            continue
        if not (
            np.isfinite(row.get("m", np.nan))
            and np.isfinite(row.get("l", np.nan))
            and np.isfinite(row.get("r", np.nan))
            and np.isfinite(row.get("f_exp", np.nan))
        ):
            continue
        if row["m"] <= 0 or row["l"] <= 0 or row["r"] <= 0 or row["f_exp"] <= 0:
            continue
        rr = dict(row)
        rr["pi_l"] = rr["l"] / rr["r"]
        rr["k_obs"] = workbench._calc_mode_k_obs(rr["mode"], rr["m"], rr["l"], rr["f_exp"])
        rr["pi_k"] = rr["k_obs"] / (rr["m"] * workbench.G_ACCEL * rr["r"])
        if np.isfinite(rr["pi_l"]) and np.isfinite(rr["pi_k"]) and rr["pi_l"] > 0:
            valid.append(rr)
    return valid


def fit_power_law_rows(rows: list[dict]) -> tuple[float, float]:
    x = np.asarray([row["pi_l"] for row in rows], dtype=np.float64)
    y = np.asarray([row["pi_k"] for row in rows], dtype=np.float64)
    a_init = float(np.nanmedian(y)) if y.size else 1.0
    if not np.isfinite(a_init) or a_init == 0:
        a_init = 1.0
    b_init = 0.5
    popt, _ = curve_fit(power_law, x, y, p0=[a_init, b_init], maxfev=50000)
    return float(popt[0]), float(popt[1])


def predict_freq(workbench, mode: str, m_val: float, l_val: float, r_val: float, a_val: float, b_val: float) -> float:
    pi_l = l_val / r_val
    pi_k_pred = a_val * (pi_l ** b_val)
    k_fit = pi_k_pred * m_val * workbench.G_ACCEL * r_val
    return float(workbench._calc_mode_f_fit(mode, m_val, l_val, k_fit))


def r2_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    ss_res = float(np.sum((y_pred - y_true) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    rmse = float(np.sqrt(np.mean((y_pred - y_true) ** 2)))
    return r2, rmse


def build_splits(n_samples: int, seed: int) -> list[tuple[np.ndarray, np.ndarray]]:
    indices = np.arange(n_samples, dtype=int)
    if n_samples < 10:
        return [(np.delete(indices, i), np.array([i], dtype=int)) for i in range(n_samples)]
    rng = np.random.default_rng(seed)
    shuffled = np.array(indices, copy=True)
    rng.shuffle(shuffled)
    folds = np.array_split(shuffled, 5)
    return [
        (
            np.concatenate([folds[j] for j in range(5) if j != i]).astype(int),
            np.asarray(folds[i], dtype=int),
        )
        for i in range(5)
    ]


def cv_one_group_mode(workbench, rows: list[dict], fit_group: str, mode: str, seed: int) -> dict:
    full_stats, _ = workbench.fit_mode(rows, outlier="none", fit_group=fit_group)
    a_full = float(full_stats.A)
    b_full = float(full_stats.B)
    f_exp = np.asarray([row["f_exp"] for row in rows], dtype=np.float64)
    f_pred_full = np.asarray(
        [predict_freq(workbench, mode, row["m"], row["l"], row["r"], a_full, b_full) for row in rows],
        dtype=np.float64,
    )
    full_r2, full_rmse = r2_rmse(f_exp, f_pred_full)
    f_pred_cv = np.full(len(rows), np.nan, dtype=np.float64)
    splits = build_splits(len(rows), seed)
    cv_scheme = "LOOCV" if len(rows) < 10 else "5-fold"
    for train_idx, test_idx in splits:
        train_rows = [rows[int(i)] for i in train_idx]
        a_cv, b_cv = fit_power_law_rows(train_rows)
        for idx in test_idx:
            row = rows[int(idx)]
            f_pred_cv[int(idx)] = predict_freq(workbench, mode, row["m"], row["l"], row["r"], a_cv, b_cv)
    cv_r2, cv_rmse = r2_rmse(f_exp, f_pred_cv)
    return {
        "group": fit_group,
        "mode": mode,
        "n_rows": len(rows),
        "cv_scheme": cv_scheme,
        "full_R2": full_r2,
        "cv_R2": cv_r2,
        "full_RMSE_Hz": full_rmse,
        "cv_RMSE_Hz": cv_rmse,
        "f_exp": f_exp,
        "f_pred_cv": f_pred_cv,
    }


def make_figure(results: dict[tuple[str, str], dict], workbench) -> None:
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
            "legend.fontsize": 6.5,
        }
    )
    all_vals = []
    for mode in MODES:
        for group in GROUPS:
            all_vals.extend(results[(group, mode)]["f_exp"].tolist())
            all_vals.extend(results[(group, mode)]["f_pred_cv"].tolist())
    arr = np.asarray(all_vals, dtype=np.float64)
    f_min = float(np.nanmin(arr))
    f_max = float(np.nanmax(arr))
    pad = 0.04 * (f_max - f_min if f_max > f_min else max(f_max, 1.0))
    lo = max(0.0, f_min - pad)
    hi = f_max + pad
    line = np.linspace(lo, hi, 200)

    mm_to_in = 1.0 / 25.4
    fig = plt.figure(figsize=(180.0 * mm_to_in, 62.0 * mm_to_in), dpi=600)
    fig.subplots_adjust(left=0.07, right=0.995, top=0.90, bottom=0.18, wspace=0.20)
    gs = fig.add_gridspec(1, 3, wspace=0.20)
    axes = []
    for idx, mode in enumerate(MODES):
        if idx == 0:
            ax = fig.add_subplot(gs[0, idx])
        else:
            ax = fig.add_subplot(gs[0, idx], sharex=axes[0], sharey=axes[0])
        axes.append(ax)
        ax.fill_between(line, 0.95 * line, 1.05 * line, color="#D9D9D9", alpha=0.3, zorder=0)
        ax.plot(line, line, color="black", lw=1.1, zorder=1)
        for group in GROUPS:
            res = results[(group, mode)]
            ax.scatter(
                res["f_exp"],
                res["f_pred_cv"],
                s=GROUP_STYLE[group]["size"],
                marker=GROUP_STYLE[group]["marker"],
                color=GROUP_STYLE[group]["color"],
                alpha=0.9,
                zorder=3,
            )
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(MODE_TITLE[mode], fontsize=8, pad=4)
        ax.set_xlabel("")
        ax.set_ylabel(r"$f_{\mathrm{pred,cv}}$  (Hz)" if idx == 0 else "", fontsize=8)
        ax.tick_params(labelsize=7, direction="in")
        if idx > 0:
            ax.tick_params(axis="y", labelleft=False)
        ca_res = results[("CA", mode)]
        oth_res = results[("OTHERS", mode)]
        ax.text(
            0.04,
            0.95,
            f"CA: $R^2_{{cv}}$ = {ca_res['cv_R2']:.3f}\nSR: $R^2_{{cv}}$ = {oth_res['cv_R2']:.3f}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=6.5,
            bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "none", "pad": 1.6},
        )
    handles = [
        Line2D([0], [0], marker="o", linestyle="None", color=GROUP_STYLE["CA"]["color"], markersize=5.5, label="CA"),
        Line2D([0], [0], marker="s", linestyle="None", color=GROUP_STYLE["OTHERS"]["color"], markersize=5.5, label=GROUP_LABEL["OTHERS"]),
        Line2D([0], [0], color="black", lw=1.1, label="45° line"),
        Line2D([0], [0], color="#D9D9D9", lw=6.0, alpha=0.6, label="±5%"),
    ]
    axes[0].legend(handles=handles, loc="lower right", frameon=False, bbox_to_anchor=(0.98, 0.02))
    axes[1].set_xlabel("Experimental frequency (Hz)", fontsize=8, fontweight="normal", labelpad=7)
    out_base = workbench.WORKBENCH_OUT_DIR / "12_cross_validation_predicted_vs_observed"
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
    workbench._remove_legacy_figure_outputs("12_cross_validation_predicted_vs_observed")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    _prepare_runtime()
    import logic.paper_plot_workbench as workbench

    ctx = workbench.prepare_dimscaling_context()
    rows_by_mode = ctx["rows_by_mode"]
    results: dict[tuple[str, str], dict] = {}
    csv_rows = []
    for group in GROUPS:
        for mode in MODES:
            group_rows = build_valid_group_rows(workbench, rows_by_mode[mode], group)
            res = cv_one_group_mode(workbench, group_rows, group, mode, seed=args.seed)
            results[(group, mode)] = res
            csv_rows.append(
                {
                    "group": group,
                    "mode": mode,
                    "n_rows": res["n_rows"],
                    "cv_scheme": res["cv_scheme"],
                    "full_R2": res["full_R2"],
                    "cv_R2": res["cv_R2"],
                    "full_RMSE_Hz": res["full_RMSE_Hz"],
                    "cv_RMSE_Hz": res["cv_RMSE_Hz"],
                }
            )
    RESULT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with RESULT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["group", "mode", "n_rows", "cv_scheme", "full_R2", "cv_R2", "full_RMSE_Hz", "cv_RMSE_Hz"],
        )
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"[DONE] wrote {RESULT_CSV}")
    for row in csv_rows:
        print(
            f"{row['group']:>6} | {row['mode']:<16} | n={row['n_rows']:<2} | {row['cv_scheme']:<5} | "
            f"full_R2={row['full_R2']:.6f} | cv_R2={row['cv_R2']:.6f} | "
            f"full_RMSE={row['full_RMSE_Hz']:.6f} Hz | cv_RMSE={row['cv_RMSE_Hz']:.6f} Hz"
        )
    make_figure(results, workbench)
    print("[DONE] saved cross-validation figure to workbench_ordered/pdf|png|tiff")


if __name__ == "__main__":
    main()
