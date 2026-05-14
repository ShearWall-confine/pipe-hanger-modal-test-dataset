from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook

from logic.paper_plot_workbench import prepare_dimscaling_context


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_DIR = CODE_ROOT.parent
OUT_DIR = PROJECT_DIR / "data" / "derived"
CHANNEL_CSV = OUT_DIR / "Table_X_frequency_identification_summary.csv"
OUT_XLSX = OUT_DIR / "Table_X_frequency_identification_summary.xlsx"


def write_channel_sheet(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "channel_level"
    with CHANNEL_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            ws.append(row)


def write_condition_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("condition_level")
    ws.append(
        [
            "exp_id",
            "mode",
            "fit_group",
            "f_exp_hz",
            "f_pend_hz",
            "f_fit_hz",
            "fit_used",
            "A",
            "B",
        ]
    )

    ctx = prepare_dimscaling_context()
    rows = []
    for mode, mode_rows in ctx["rows_by_mode"].items():
        for row in mode_rows:
            rows.append(
                {
                    "exp_id": row["exp_id"],
                    "mode": mode,
                    "fit_group": row.get("fit_group", ""),
                    "f_exp_hz": row.get("f_exp", ""),
                    "f_pend_hz": row.get("f_pend", ""),
                    "f_fit_hz": row.get("f_fit", ""),
                    "fit_used": row.get("fit_used", ""),
                    "A": row.get("A", ""),
                    "B": row.get("B", ""),
                }
            )

    mode_rank = {"radial": 0, "axial": 1, "planar_rotation": 2}
    rows.sort(key=lambda r: (r["exp_id"], mode_rank.get(str(r["mode"]), 99)))

    for row in rows:
        ws.append(
            [
                row["exp_id"],
                row["mode"],
                row["fit_group"],
                row["f_exp_hz"],
                row["f_pend_hz"],
                row["f_fit_hz"],
                row["fit_used"],
                row["A"],
                row["B"],
            ]
        )


def autosize_columns(wb: Workbook) -> None:
    for ws in wb.worksheets:
        for col_cells in ws.columns:
            max_len = 0
            col_letter = col_cells[0].column_letter
            for cell in col_cells:
                value = "" if cell.value is None else str(cell.value)
                if len(value) > max_len:
                    max_len = len(value)
            ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 28)


def main() -> None:
    if not CHANNEL_CSV.exists():
        raise FileNotFoundError(f"Missing source CSV: {CHANNEL_CSV}")

    wb = Workbook()
    write_channel_sheet(wb)
    write_condition_sheet(wb)
    autosize_columns(wb)
    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT_XLSX)
    print(f"wrote workbook: {OUT_XLSX}")


if __name__ == "__main__":
    main()
