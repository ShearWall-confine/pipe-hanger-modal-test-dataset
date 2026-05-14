"""CLI progress wrapper for batch damping extraction."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from damping.damping_batch import batch_extract_damping
from core.modal_db import DEFAULT_H5_PATH


def _bar(pct: float, width: int = 40) -> str:
    filled = int(width * max(0.0, min(1.0, pct)))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch damping extraction with progress bar.")
    parser.add_argument("--h5-path", type=Path, default=DEFAULT_H5_PATH)
    parser.add_argument("--bandwidth-pct", type=float, default=15.0)
    parser.add_argument("--butter-order", type=int, default=4)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    t0 = time.time()

    def cb(exp_id: str, current: int, total: int) -> None:
        pct = (current / total) if total > 0 else 0.0
        elapsed = time.time() - t0
        eta = (elapsed / max(current, 1)) * (total - current) if current > 0 else 0.0
        line = (
            f"\r{_bar(pct, 48)} {pct*100:6.2f}% "
            f"({current:>3}/{total:<3}) "
            f"EXP={exp_id:<30} "
            f"elapsed={elapsed:7.1f}s eta={eta:7.1f}s"
        )
        print(line, end="", flush=True)

    print("Running damping batch extraction...")
    summary = batch_extract_damping(
        h5_path=args.h5_path,
        bandwidth_pct=args.bandwidth_pct,
        butter_order=args.butter_order,
        workers=args.workers,
        overwrite=args.overwrite,
        progress_callback=cb,
    )
    print()
    print("Batch summary:", summary)


if __name__ == "__main__":
    main()
