from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "derived"
ASYM_CSV = PROCESSED_DIR / "sec6_asymptotic_ci.csv"
TABLE7_CSV = PROCESSED_DIR / "sec6_table7_eta_deltaf.csv"
TABLE8_CSV = PROCESSED_DIR / "sec6_table8_critical_lr.csv"

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("USERPROFILE", str(PROJECT_ROOT))
os.environ.setdefault("HOME", str(PROJECT_ROOT))
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".mplconfig"))
(PROJECT_ROOT / ".mplconfig").mkdir(parents=True, exist_ok=True)

import matplotlib.pyplot as plt
import numpy as np

ETA_VALUES = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
MODES = ("radial", "axial")
MODE_TITLE = {
    "radial": "(a) Radial",
    "axial": "(b) Axial",
}
GROUP_STYLE = {
    "CA": {"color": "#C43C39", "fill": "#EEC8C6"},
    "OTHERS": {"color": "#2166AC", "fill": "#C7D8EE"},
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
    parser = argparse.ArgumentParser(description="Section 6.3 eta and critical rod geometry.")
    return parser.parse_args()


def load_asymptotic_rows() -> dict[tuple[str, str], dict]:
    rows = {}
    with ASYM_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["fit_group"], row["mode"])
            rows[key] = {
                "fit_group": row["fit_group"],
                "mode": row["mode"],
                "A": float(row["A"]),
                "B": float(row["B"]),
                "SE_A": float(row["SE_A"]),
                "SE_B": float(row["SE_B"]),
                "corr_AB": float(row["corr_AB"]),
                "n_rows": int(row["n_rows"]),
            }
    return rows


def eta_deltaf_rows() -> list[dict]:
    out = []
    for eta in ETA_VALUES:
        delta_f_pct = (math.sqrt(1.0 + eta) - 1.0) * 100.0
        out.append({"eta": eta, "delta_f_pct": delta_f_pct})
    return out


def critical_lr(a_val: float, b_val: float) -> float:
    return float((0.1 / a_val) ** (1.0 / (b_val - 1.0)))


def critical_lr_variance(a_val: float, b_val: float, se_a: float, se_b: float, corr_ab: float) -> tuple[float, float]:
    def g(aa: float, bb: float) -> float:
        return critical_lr(aa, bb)

    eps_a = max(1e-6, abs(a_val) * 1e-6)
    eps_b = 1e-6
    dg_dA = (g(a_val + eps_a, b_val) - g(a_val - eps_a, b_val)) / (2.0 * eps_a)
    dg_dB = (g(a_val, b_val + eps_b) - g(a_val, b_val - eps_b)) / (2.0 * eps_b)

    var_a = se_a ** 2
    var_b = se_b ** 2
    cov_ab = corr_ab * se_a * se_b
    var_g = dg_dA ** 2 * var_a + dg_dB ** 2 * var_b + 2.0 * dg_dA * dg_dB * cov_ab
    return dg_dA, max(var_g, 0.0)


def eta_value(a_val: float, b_val: float, x_val: np.ndarray | float) -> np.ndarray | float:
    return a_val * np.power(x_val, b_val - 1.0)


def eta_band(a_val: float, b_val: float, se_a: float, se_b: float, corr_ab: float, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    eta = eta_value(a_val, b_val, x)
    d_eta_dA = np.power(x, b_val - 1.0)
    d_eta_dB = a_val * np.power(x, b_val - 1.0) * np.log(x)
    cov_ab = corr_ab * se_a * se_b
    var_eta = d_eta_dA ** 2 * se_a ** 2 + d_eta_dB ** 2 * se_b ** 2 + 2.0 * d_eta_dA * d_eta_dB * cov_ab
    var_eta = np.maximum(var_eta, 0.0)
    sigma = np.sqrt(var_eta)
    eta_lo = np.maximum(eta - 1.96 * sigma, 1e-12)
    eta_hi = np.maximum(eta + 1.96 * sigma, 1e-12)
    return eta, eta_lo, eta_hi


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_frequency_error_figure(workbench) -> None:
    eta = np.logspace(np.log10(0.005), np.log10(5.0), 500)
    delta_f_pct = (np.sqrt(1.0 + eta) - 1.0) * 100.0
    points = np.array([0.01, 0.05, 0.10, 0.25, 0.50, 1.00, 5.00])
    point_delta = (np.sqrt(1.0 + points) - 1.0) * 100.0

    mm_to_in = 1.0 / 25.4
    fig, ax = plt.subplots(figsize=(145.0 * mm_to_in, 58.0 * mm_to_in), dpi=600)

    bands = [
        (0.005, 0.10, "#e8f4ea", "Negligible"),
        (0.10, 0.25, "#fff4d6", "Non-negligible"),
        (0.25, 0.50, "#fde8d7", "Significant"),
        (0.50, 1.00, "#f7d6d6", "Severe"),
        (1.00, 5.00, "#eadcf5", "Dominant"),
    ]
    band_label_y = 137.0
    for x0, x1, color, label in bands:
        ax.axvspan(x0, x1, color=color, alpha=0.72, lw=0)
        ax.text(
            math.sqrt(x0 * x1),
            band_label_y,
            label,
            ha="center",
            va="center",
            color="#333333",
        )

    ax.plot(eta, delta_f_pct, color="#222222", lw=1.8, zorder=3)
    ax.scatter(points, point_delta, s=18, color="#222222", zorder=4)

    eta_crit = 0.10
    delta_crit = (math.sqrt(1.0 + eta_crit) - 1.0) * 100.0
    ax.axvline(eta_crit, color="#C1121F", lw=1.2, ls="--", zorder=2)
    ax.axhline(delta_crit, color="#C1121F", lw=1.2, ls="--", zorder=2)
    ax.annotate(
        r"recommended threshold: $\eta_{\mathrm{crit}}=0.1$",
        xy=(eta_crit, delta_crit),
        xytext=(0.017, 34),
        textcoords="data",
        arrowprops=dict(arrowstyle="->", color="#C1121F", lw=0.9),
        color="#8F0D18",
        ha="left",
        va="center",
    )

    ax.set_xscale("log")
    ax.set_xlim(0.005, 5.0)
    ax.set_ylim(0.0, 155.0)
    ax.set_xlabel(r"Stiffness contribution ratio, $\eta$")
    ax.set_ylabel(r"Frequency underestimation, $\delta f$ (%)")
    ax.set_xticks([0.01, 0.05, 0.10, 0.25, 0.50, 1.00, 5.00])
    ax.set_xticklabels(["0.01", "0.05", "0.10", "0.25", "0.50", "1.0", "5.0"])
    ax.set_yticks([0, 5, 25, 50, 100, 150])
    ax.grid(axis="y", color="#D0D0D0", lw=0.5, alpha=0.7)
    ax.grid(axis="x", which="major", color="#E0E0E0", lw=0.4, alpha=0.45)
    fig.tight_layout(pad=0.25)
    workbench.style_figure(fig, theme=workbench.WORD_THEME, grid=False)
    workbench.apply_insert_text_style_for_figure(
        fig,
        latex_width_fraction=0.86,
        latex_text_width_in=6.45,
        pad_inches=0.0,
    )
    ax.tick_params(axis="both", which="major", direction="in")
    ax.tick_params(axis="both", which="minor", direction="in", length=2.0, width=0.7)
    workbench.save_figure_bundle(
        fig,
        workbench.WORKBENCH_OUT_DIR / "19_eta_frequency_error_threshold",
        formats=("png", "tiff", "pdf"),
        dpi=600,
        split_format_dirs=True,
        bbox_inches="tight",
    )
    plt.close(fig)


def save_figure(fig, workbench) -> None:
    out_base = workbench.WORKBENCH_OUT_DIR / "20_eta_vs_lr"
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
    for out_dir, ext in [
        (workbench.WORKBENCH_PNG_OUT_DIR, ".png"),
        (workbench.WORKBENCH_TIFF_OUT_DIR, ".tiff"),
        (workbench.WORKBENCH_PDF_OUT_DIR, ".pdf"),
    ]:
        for legacy_name in ("17_eta_vs_lr", "19_eta_vs_lr"):
            legacy_path = out_dir / f"{legacy_name}{ext}"
            if legacy_path.exists():
                legacy_path.unlink()


def main() -> None:
    parse_args()
    _prepare_runtime()

    import logic.paper_plot_workbench as workbench

    asym = load_asymptotic_rows()

    table7_rows = eta_deltaf_rows()
    write_csv(TABLE7_CSV, ["eta", "delta_f_pct"], table7_rows)
    print("[Table 7] eta -> delta_f")
    for row in table7_rows:
        print(f"eta = {row['eta']:.2f} -> delta_f = {row['delta_f_pct']:.1f}%")
    print(f"[DONE] wrote {TABLE7_CSV}")
    save_frequency_error_figure(workbench)
    print("[DONE] saved Figure 19 to workbench_ordered/pdf|png|tiff")

    table8_rows: list[dict] = []
    print()
    print("[Table 8] critical l/r")
    for fit_group in ("CA", "OTHERS"):
        for mode in MODES:
            row = asym[(fit_group, mode)]
            a_val = row["A"]
            b_val = row["B"]
            se_a = row["SE_A"]
            se_b = row["SE_B"]
            corr_ab = row["corr_AB"]

            lr_crit_val = critical_lr(a_val, b_val)
            _, var_lr = critical_lr_variance(a_val, b_val, se_a, se_b, corr_ab)
            sigma_lr = math.sqrt(max(var_lr, 0.0))
            lr_crit = lr_crit_val
            lr_lo = max(lr_crit_val - 1.96 * sigma_lr, 0.0)
            lr_hi = lr_crit_val + 1.96 * sigma_lr
            notes = "eta threshold at eta=0.1 (delta_f approx 5%)"
            trend = "decreasing" if (b_val - 1.0) < 0 else "increasing"
            print(
                f"{fit_group:>6} | {mode:<16} | A={a_val:.6g} | B={b_val:.6g} | "
                f"B-1={b_val - 1.0:.6g} | lr_crit={lr_crit_val:.6g} [{lr_lo:.6g}, {lr_hi:.6g}] | "
                f"eta {trend} with l/r"
            )

            table8_rows.append(
                {
                    "fit_group": fit_group,
                    "mode": mode,
                    "A": a_val,
                    "B": b_val,
                    "B_minus_1": b_val - 1.0,
                    "lr_crit": lr_crit,
                    "lr_crit_ci_lo": lr_lo,
                    "lr_crit_ci_hi": lr_hi,
                    "notes": notes,
                }
            )

    write_csv(
        TABLE8_CSV,
        ["fit_group", "mode", "A", "B", "B_minus_1", "lr_crit", "lr_crit_ci_lo", "lr_crit_ci_hi", "notes"],
        table8_rows,
    )
    print(f"[DONE] wrote {TABLE8_CSV}")

    empirical_l_crit_m = 0.739
    empirical_r_m = 0.0137
    empirical_lr = empirical_l_crit_m / empirical_r_m
    others_radial = next(r for r in table8_rows if r["fit_group"] == "OTHERS" and r["mode"] == "radial")
    print()
    print("[Cross-check] Section 5.2.3 empirical comparison")
    print(
        f"Section 5.2.3 empirical: l_crit = {empirical_l_crit_m:.3f} m, r = {empirical_r_m:.4f} m -> l/r = {empirical_lr:.3f}"
    )
    print(
        f"Section 6.3 OTHERS radial model: l/r_crit = {float(others_radial['lr_crit']):.6g} "
        f"[{float(others_radial['lr_crit_ci_lo']):.6g}, {float(others_radial['lr_crit_ci_hi']):.6g}]"
    )
    print(
        "Note: Section 5.2.3 uses r = 13.7 mm, while DimScaling OTHERS mixes TB (8 mm), CSBD (12.5 mm), and CSB (18 mm); "
        "the empirical l/r may therefore reflect an effective clamp radius rather than any one support family's raw r."
    )

    x = np.linspace(10.0, 350.0, 700)
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "mathtext.default": "it",
            "font.size": 8.4,
            "axes.labelsize": 9.2,
            "xtick.labelsize": 8.1,
            "ytick.labelsize": 8.1,
            "legend.fontsize": 7.6,
        }
    )
    mm_to_in = 1.0 / 25.4
    fig = plt.figure(figsize=(130.0 * mm_to_in, 60.0 * mm_to_in), dpi=600)
    fig.subplots_adjust(left=0.065, right=0.99, top=0.86, bottom=0.18, wspace=0.27)
    gs = fig.add_gridspec(1, 2, wspace=0.27)

    legend_handles = []
    axes = []
    for idx, mode in enumerate(MODES):
        if idx == 0:
            ax = fig.add_subplot(gs[0, idx])
        else:
            ax = fig.add_subplot(gs[0, idx], sharey=axes[0])
        axes.append(ax)
        ax.set_title(MODE_TITLE[mode], fontsize=9.0, pad=5)

        for fit_group in ("CA", "OTHERS"):
            row = asym[(fit_group, mode)]
            style = GROUP_STYLE[fit_group]
            eta_mid, eta_lo, eta_hi = eta_band(row["A"], row["B"], row["SE_A"], row["SE_B"], row["corr_AB"], x)
            ax.fill_between(x, eta_lo, eta_hi, color=style["fill"], alpha=0.15, zorder=1)
            ax.plot(x, eta_mid, color=style["color"], lw=1.4, zorder=2)
            if idx == 0:
                legend_handles.append(plt.Line2D([0], [0], color=style["color"], lw=1.4, label=GROUP_LABEL[fit_group]))

        eta_reference_labels = [
            (0.05, r"$\Delta f$ = 2.5%"),
            (0.1, r"$\Delta f$ = 5%"),
            (1.0, r"$\Delta f$ = 41%"),
        ]
        for eta_ref, label in eta_reference_labels:
            ax.axhline(eta_ref, color="#8F8F8F", lw=0.8, ls="--", zorder=0)
            ax.text(
                338,
                eta_ref * 1.03,
                label,
                fontsize=7.0,
                color="#6F6F6F",
                ha="right",
                va="bottom",
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.70, pad=0.4),
                zorder=4,
            )

        for x_ref, txt in [(51.0, "l = 0.7 m"), (95.0, "l = 1.3 m")]:
            ax.axvline(x_ref, color="#9A9A9A", lw=0.8, ls=":", zorder=0)
            ax.text(
                x_ref + 2.5,
                0.012,
                txt,
                fontsize=7.0,
                color="#7A7A7A",
                ha="left",
                va="bottom",
                rotation=45,
            )

        ax.set_xlim(10, 350)
        ax.set_yscale("log")
        ax.set_ylim(0.01, 20.0)
        ax.set_xlabel("")
        if idx == 0:
            ax.set_ylabel(r"$\eta = A\,(l/r)^{B-1}$", fontsize=9.2)
        else:
            ax.set_ylabel("")
            ax.tick_params(axis="y", labelleft=False)
        ax.grid(False)
        ax.tick_params(axis="both", which="major", labelsize=8.1, direction="in")
        ax.tick_params(axis="both", which="minor", direction="in")

    fig.supxlabel(r"Length ratio, $l/r$", fontsize=8.4, y=0.04)

    legend_handles.extend(
        [
            plt.Line2D([0], [0], color="#8F8F8F", lw=0.8, ls="--", label=r"$\eta$ reference"),
            plt.Line2D([0], [0], color="#9A9A9A", lw=0.8, ls=":", label="test l/r"),
        ]
    )
    axes[0].legend(
        handles=legend_handles,
        loc="upper right",
        ncol=1,
        frameon=True,
        fontsize=7.4,
        bbox_to_anchor=(0.98, 0.98),
        borderaxespad=0.0,
        handlelength=1.6,
        handletextpad=0.5,
        labelspacing=0.25,
        facecolor="white",
        edgecolor="none",
        framealpha=0.78,
    )

    save_figure(fig, workbench)
    plt.close(fig)
    print()
    print("[DONE] saved Figure 20 to workbench_ordered/pdf|png|tiff")


if __name__ == "__main__":
    main()
