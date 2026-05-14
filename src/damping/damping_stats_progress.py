"""CLI progress wrapper for damping statistics plotting."""

from __future__ import annotations

import argparse
from pathlib import Path

from matplotlib.figure import Figure

from damping.damping_stats import (
    compute_damping_statistics,
    plot_damping_summary_by_support,
    plot_drift_ratio_summary,
    plot_xi_amplitude,
)
from core.modal_db import DEFAULT_H5_PATH


def _save_png(fig: Figure, out_base: Path) -> None:
    fig.savefig(out_base.with_suffix(".png"), dpi=320)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate damping figures with progress output.")
    parser.add_argument("--h5-path", type=Path, default=DEFAULT_H5_PATH)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("[stats 1/4] damping_summary (png)...", flush=True)
    fig1 = Figure(figsize=(12, 8))
    plot_damping_summary_by_support(args.h5_path, fig1)
    _save_png(fig1, args.out_dir / "damping_summary")

    print("[stats 2/4] damping_xi_amplitude (png)...", flush=True)
    fig2 = Figure(figsize=(12, 4))
    plot_xi_amplitude(args.h5_path, fig2)
    _save_png(fig2, args.out_dir / "damping_xi_amplitude")

    print("[stats 3/4] damping_freq_drift (png)...", flush=True)
    fig3 = Figure(figsize=(12, 8))
    plot_drift_ratio_summary(args.h5_path, fig3)
    _save_png(fig3, args.out_dir / "damping_freq_drift")

    print("[stats 4/4] computing grouped statistics...", flush=True)
    stats_dict = compute_damping_statistics(args.h5_path)
    print(f"[stats done] groups={len(stats_dict)}", flush=True)


if __name__ == "__main__":
    main()
