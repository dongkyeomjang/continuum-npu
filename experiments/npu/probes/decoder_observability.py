#!/usr/bin/env python3
"""Record exact installed source locations for decoder bucket observation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re

PATTERNS = {
    "actual_num_reqs": re.compile(r"num_reqs\s*=\s*len\(.*requests"),
    "bucket_selection": re.compile(r"find_decode_batch_bucket|decode_batch_bucket"),
    "compiled_bucket_configuration": re.compile(r"decoder_batch_sizes|decode_batch_sizes"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    dist = importlib.metadata.distribution("vllm-rbln")
    root = Path(dist.locate_file("vllm_rbln")).resolve()
    target_names = ("rbln_model_runner.py", "optimum_model_runner.py", "bucket.py")
    targets = [path for path in root.rglob("*.py") if path.name in target_names]
    files = []
    for path in sorted(targets):
        lines = path.read_text(encoding="utf-8").splitlines()
        matches = []
        for line_number, line in enumerate(lines, 1):
            names = [name for name, pattern in PATTERNS.items() if pattern.search(line)]
            if names:
                matches.append(
                    {
                        "line": line_number,
                        "signals": names,
                        "source": line.strip(),
                    }
                )
        files.append(
            {
                "path": str(path),
                "sha256": sha256(path),
                "matches": matches,
            }
        )

    payload = {
        "record_type": "decoder_observability_source_map",
        "vllm_rbln_version": dist.version,
        "installed_root": str(root),
        "files": files,
        "semantics_modified": False,
        "site_packages_modified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
