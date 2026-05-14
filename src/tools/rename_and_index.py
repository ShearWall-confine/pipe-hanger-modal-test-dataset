from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List

from core.modal_db import DEFAULT_ORIGIN_DIR, DEFAULT_RENAME_LOG, discover_xls_files


@dataclass
class RenameEntry:
    old_name: str
    new_name: str
    status: str
    message: str = ""


def convert_prefix(name: str) -> str:
    if name.startswith("TR_"):
        return "CSBD_" + name[len("TR_") :]
    if name.startswith("CS_"):
        return "CSB_" + name[len("CS_") :]
    return name


def rename_files(origin_dir: Path) -> List[RenameEntry]:
    files = discover_xls_files(origin_dir)
    entries: List[RenameEntry] = []
    planned = {}

    for src in files:
        target_name = convert_prefix(src.name)
        planned[src.name] = target_name

    duplicates = {}
    for old_name, new_name in planned.items():
        duplicates.setdefault(new_name.lower(), []).append(old_name)
    conflicts = {k: v for k, v in duplicates.items() if len(v) > 1}
    if conflicts:
        for _, names in conflicts.items():
            for old_name in names:
                entries.append(
                    RenameEntry(
                        old_name=old_name,
                        new_name=planned[old_name],
                        status="error",
                        message="target collision",
                    )
                )
        return entries

    for src in files:
        new_name = planned[src.name]
        if new_name == src.name:
            entries.append(RenameEntry(src.name, new_name, "skipped", "prefix unchanged"))
            continue
        dst = src.with_name(new_name)
        if dst.exists():
            entries.append(RenameEntry(src.name, new_name, "error", "target already exists"))
            continue
        src.rename(dst)
        entries.append(RenameEntry(src.name, new_name, "renamed", ""))
    return entries


def write_log(entries: List[RenameEntry], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["old_name", "new_name", "status", "message"])
        for e in entries:
            writer.writerow([e.old_name, e.new_name, e.status, e.message])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rename XLS prefixes: TR->CSBD, CS->CSB.")
    parser.add_argument("--origin-dir", type=Path, default=DEFAULT_ORIGIN_DIR)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_RENAME_LOG)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    entries = rename_files(args.origin_dir)
    write_log(entries, args.log_path)
    renamed = sum(1 for e in entries if e.status == "renamed")
    skipped = sum(1 for e in entries if e.status == "skipped")
    errors = sum(1 for e in entries if e.status == "error")
    print(f"Total entries: {len(entries)}")
    print(f"Renamed: {renamed}, Skipped: {skipped}, Errors: {errors}")
    print(f"Log: {args.log_path}")


if __name__ == "__main__":
    main()
