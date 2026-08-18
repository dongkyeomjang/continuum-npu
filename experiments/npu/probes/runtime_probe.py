#!/usr/bin/env python3
"""Fail-loud probe for the installed RBLN-compatible Python stack."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone

EXPECTED_VLLM_VERSION = "0.22.0+cpu"
EXPECTED_VLLM_RBLN_VERSION = "0.11.1"


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git_value(repo: Path, *args: str, allow_missing: bool = False) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=not allow_missing,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    repo = Path(os.environ["VLLM_CONTINUUM_REPO_ROOT"]).resolve()
    local_vllm = (repo / "vllm").resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = repo / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    import torch
    import vllm
    import vllm_rbln

    vllm_file = Path(vllm.__file__).resolve()
    vllm_rbln_file = Path(vllm_rbln.__file__).resolve()
    vllm_version = getattr(vllm, "__version__", None)
    vllm_distribution_version = package_version("vllm")
    rbln_version = package_version("vllm-rbln")

    errors: list[str] = []
    if vllm_file == local_vllm or local_vllm in vllm_file.parents:
        errors.append(f"repository-local vllm imported: {vllm_file}")
    if str(repo) in sys.path:
        errors.append(f"repository root leaked into sys.path: {repo}")
    if vllm_distribution_version != EXPECTED_VLLM_VERSION:
        errors.append(
            "vllm distribution version mismatch: "
            f"{vllm_distribution_version!r} != {EXPECTED_VLLM_VERSION!r}"
        )
    expected_module_version = EXPECTED_VLLM_VERSION.split("+", 1)[0]
    if vllm_version != expected_module_version:
        errors.append(
            f"vllm module version mismatch: {vllm_version!r} "
            f"!= {expected_module_version!r}"
        )
    if rbln_version != EXPECTED_VLLM_RBLN_VERSION:
        errors.append(
            "vllm-rbln version mismatch: "
            f"{rbln_version!r} != {EXPECTED_VLLM_RBLN_VERSION!r}"
        )

    dirty_lines = git_value(repo, "status", "--short").splitlines()
    environment = {
        "record_type": "rbln_source_isolation",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "status": "INVALID" if errors else "PASS",
        "errors": errors,
        "sys_executable": sys.executable,
        "cwd": os.getcwd(),
        "sys_path": sys.path,
        "repo_root": str(repo),
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "kernel": platform.release(),
        "python_version": platform.python_version(),
        "git_commit": git_value(repo, "rev-parse", "HEAD", allow_missing=True),
        "git_branch": git_value(repo, "branch", "--show-current"),
        "git_dirty": bool(dirty_lines),
        "git_status_short": dirty_lines,
        "packages": {
            "vllm": {
                "module_version": vllm_version,
                "distribution_version": vllm_distribution_version,
                "file": str(vllm_file),
            },
            "vllm-rbln": {"version": rbln_version, "file": str(vllm_rbln_file)},
            "optimum-rbln": {"version": package_version("optimum-rbln")},
            "rebel-compiler": {"version": package_version("rebel-compiler")},
            "torch-rbln": {"version": package_version("torch-rbln")},
            "torch": {
                "version": torch.__version__,
                "file": str(Path(torch.__file__).resolve()),
            },
        },
    }
    (output_dir / "environment.json").write_text(
        json.dumps(environment, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    metadata = {
        "stage": "source_isolation",
        "status": environment["status"],
        "git_commit": environment["git_commit"],
        "git_dirty": environment["git_dirty"],
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "resolved_config.json").write_text(
        json.dumps(
            {
                "expected_vllm_version": EXPECTED_VLLM_VERSION,
                "expected_vllm_rbln_version": EXPECTED_VLLM_RBLN_VERSION,
                "external_kv_connector": "disabled",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for name in ("raw_requests.jsonl", "derived_metrics.jsonl", "raw_server.log"):
        (output_dir / name).touch()

    human_lines = [
        f"sys.executable: {sys.executable}",
        f"cwd: {os.getcwd()}",
        "sys.path:",
        *[f"  {item}" for item in sys.path],
        f"vllm.__file__: {vllm_file}",
        f"vllm.__version__: {vllm_version}",
        f"vllm distribution version: {vllm_distribution_version}",
        f"vllm_rbln.__file__: {vllm_rbln_file}",
        f"vllm-rbln version: {rbln_version}",
        f"torch.__file__: {Path(torch.__file__).resolve()}",
        f"torch.__version__: {torch.__version__}",
        f"isolation invariant: {environment['status']}",
    ]
    human = "\n".join(human_lines) + "\n"
    print(human, end="")
    (output_dir / "runtime_probe.log").write_text(human, encoding="utf-8")

    if errors:
        raise RuntimeError("; ".join(errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
