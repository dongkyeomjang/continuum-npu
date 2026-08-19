#!/usr/bin/env python3
"""Stage 0 step 1 — download the pre-registered Hugging Face model snapshot.

Downloads weights only. Performs no compilation and no device access.
Records revision, wall-clock, and measured on-disk size as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone


def dir_bytes(root: Path) -> int:
    """Sum of regular-file sizes, following symlinks once (HF cache uses blobs)."""
    total = 0
    seen: set[tuple[int, int]] = set()
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            try:
                stat = path.stat()  # follows symlink into the blob store
            except OSError:
                continue
            key = (stat.st_dev, stat.st_ino)
            if key in seen:
                continue
            seen.add(key)
            total += stat.st_size
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    from huggingface_hub import snapshot_download
    import huggingface_hub

    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    snapshot_path = snapshot_download(repo_id=args.model_id)
    wall_clock_s = time.perf_counter() - t0
    finished_at = datetime.now(timezone.utc)

    snapshot = Path(snapshot_path).resolve()
    revision = snapshot.name  # HF cache lays snapshots out under the commit sha

    record = {
        "model_id": args.model_id,
        "revision": revision,
        "snapshot_path": str(snapshot),
        "download_wall_clock_s": wall_clock_s,
        "measured_bytes": dir_bytes(snapshot),
        "file_count": sum(1 for _ in snapshot.rglob("*") if _.is_file()),
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "huggingface_hub_version": huggingface_hub.__version__,
        "hf_home": os.environ.get("HF_HOME"),
    }

    files = subprocess.run(
        ["ls", "-la", str(snapshot)], text=True, stdout=subprocess.PIPE, check=False
    ).stdout
    (output_dir / "download.json").write_text(json.dumps(record, indent=2) + "\n")
    (output_dir / "snapshot-listing.txt").write_text(files)
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
