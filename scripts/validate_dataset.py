from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import h5py


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_H5 = REPO_ROOT / "data" / "derived" / "modal_db.h5"
RELEASE_H5 = REPO_ROOT / "release_assets" / "modal_db_v1.0.h5"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_h5(path: Path) -> dict:
    support_counts: dict[str, int] = {}
    direction_counts: dict[str, int] = {}
    missing: list[str] = []
    with h5py.File(path, "r") as h5:
        experiments = h5["experiments"]
        for exp_id in sorted(experiments.keys()):
            group = experiments[exp_id]
            support = str(group.attrs.get("support_type", ""))
            direction = str(group.attrs.get("direction", ""))
            support_counts[support] = support_counts.get(support, 0) + 1
            direction_counts[direction] = direction_counts.get(direction, 0) + 1
            if "time" not in group or "channels" not in group or "channel_ids" not in group:
                missing.append(exp_id)
                continue
            channels = group["channels"]
            if len(channels.keys()) != int(group.attrs.get("channel_count", 0)):
                missing.append(exp_id)
                continue
            for ch_id in channels.keys():
                if "signal" not in channels[ch_id]:
                    missing.append(exp_id)
                    break
        return {
            "schema_version": h5.attrs.get("schema_version", ""),
            "experiment_count": len(experiments.keys()),
            "support_counts": support_counts,
            "direction_counts": direction_counts,
            "missing_or_incomplete": sorted(set(missing)),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the public modal-test dataset package.")
    parser.add_argument("--h5", type=Path, default=DEFAULT_H5)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    raw_xls_count = len(list((REPO_ROOT / "data" / "raw_xls").glob("*.XLS")))
    h5_path = args.h5 if args.h5.exists() else RELEASE_H5
    report = {
        "raw_xls_count": raw_xls_count,
        "h5_path": str(h5_path),
        "h5_size_bytes": h5_path.stat().st_size if h5_path.exists() else None,
        "h5_sha256": sha256(h5_path) if h5_path.exists() else None,
        "h5": validate_h5(h5_path) if h5_path.exists() else None,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("raw_xls_count=", report["raw_xls_count"])
        print("h5_path=", report["h5_path"])
        print("h5_size_bytes=", report["h5_size_bytes"])
        print("h5_sha256=", report["h5_sha256"])
        print("h5=", report["h5"])


if __name__ == "__main__":
    main()
