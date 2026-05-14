from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate paper figure exports.")
    parser.add_argument(
        "--target",
        choices=["all", "dimscaling", "damping"],
        default="all",
        help="Which figure group to export.",
    )
    parser.add_argument(
        "--skip-table-x",
        action="store_true",
        help="Do not export the Table X workbook after dimscaling.",
    )
    return parser.parse_args()


def prepare_runtime() -> None:
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("USERPROFILE", str(REPO_ROOT))
    os.environ.setdefault("HOME", str(REPO_ROOT))
    os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / ".mplconfig"))
    os.chdir(SRC_ROOT)
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    (REPO_ROOT / ".mplconfig").mkdir(parents=True, exist_ok=True)


def export_table_x_if_available() -> None:
    channel_csv = REPO_ROOT / "data" / "derived" / "Table_X_frequency_identification_summary.csv"
    if not channel_csv.exists():
        print(f"[SKIP] Table X workbook not exported because source CSV is missing: {channel_csv}")
        return
    from export_table_x_frequency_workbook import main as export_table_x_main

    print("[RUN] Exporting Table X workbook...")
    export_table_x_main()


def main() -> None:
    args = parse_args()
    prepare_runtime()

    import matplotlib.pyplot as plt
    import logic.paper_plot_workbench as workbench

    plt.show = lambda *args, **kwargs: None
    workbench.display = lambda *args, **kwargs: None

    print(f"[INFO] repo_root = {REPO_ROOT}")
    print(f"[INFO] src_root = {SRC_ROOT}")
    print(f"[INFO] target = {args.target}")

    if args.target in {"all", "dimscaling"}:
        print("[RUN] Starting dimscaling export...")
        workbench.run_all_dimscaling()
        if not args.skip_table_x:
            export_table_x_if_available()

    if args.target in {"all", "damping"}:
        print("[RUN] Starting damping export...")
        workbench.run_all_damping()

    print("[DONE] Paper figure export finished.")


if __name__ == "__main__":
    main()
