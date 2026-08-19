#!/usr/bin/env python3
"""Stage 0 step 3 — one single-request inference on a compiled RBLN artifact.

Fail-loud. Asserts the source-isolation invariant, loads the pre-compiled
optimum-rbln artifact through vLLM, runs exactly one request with batch = 1,
and writes observation + provenance JSON. Runs no sweep and makes no
statistical claim: a single latency value is recorded as a raw observation.
"""

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
import time
from datetime import datetime, timezone

EXPECTED_VLLM_VERSION = "0.22.0+cpu"
EXPECTED_VLLM_RBLN_VERSION = "0.11.1"


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run(*cmd: str) -> str:
    result = subprocess.run(
        list(cmd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
    )
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--tokenizer", default=None)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--max-tokens", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    import torch
    import vllm
    import vllm_rbln

    vllm_file = Path(vllm.__file__).resolve()
    vllm_dist = package_version("vllm")
    vllm_rbln_dist = package_version("vllm-rbln")
    repo_root = Path(os.environ["VLLM_CONTINUUM_REPO_ROOT"]).resolve()

    isolation = {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "vllm_file": str(vllm_file),
        "vllm_attr_version": getattr(vllm, "__version__", None),
        "vllm_distribution": vllm_dist,
        "vllm_rbln_file": str(Path(vllm_rbln.__file__).resolve()),
        "vllm_rbln_distribution": vllm_rbln_dist,
        "repo_local_vllm_exists": (repo_root / "vllm").exists(),
    }
    # Fail loud: the installed substrate must be the one under test.
    assert not isolation["repo_local_vllm_exists"], "repository-local vllm/ fork present"
    assert repo_root not in vllm_file.parents, f"vllm resolved inside repo: {vllm_file}"
    assert vllm_dist == EXPECTED_VLLM_VERSION, f"vllm distribution: {vllm_dist}"
    assert vllm_rbln_dist == EXPECTED_VLLM_RBLN_VERSION, (
        f"vllm-rbln distribution: {vllm_rbln_dist}"
    )
    isolation["source_isolation"] = "PASS"

    prompt = args.prompt_file.read_text()
    if prompt.endswith("\n"):
        prompt = prompt[:-1]

    from vllm import LLM, SamplingParams

    smi_before = run("rbln-smi")
    (output_dir / "rbln-smi-before.txt").write_text(smi_before)

    load_t0 = time.perf_counter()
    llm = LLM(
        model=str(args.model_dir),
        tokenizer=args.tokenizer or str(args.model_dir),
        seed=args.seed,
    )
    load_wall_clock_s = time.perf_counter() - load_t0

    smi_loaded = run("rbln-smi")
    (output_dir / "rbln-smi-after-load.txt").write_text(smi_loaded)

    sampling = SamplingParams(temperature=0.0, top_p=1.0, max_tokens=args.max_tokens)

    infer_started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    outputs = llm.generate([prompt], sampling)
    e2e_latency_s = time.perf_counter() - t0
    infer_finished_at = datetime.now(timezone.utc)

    smi_after = run("rbln-smi")
    (output_dir / "rbln-smi-after-inference.txt").write_text(smi_after)

    assert len(outputs) == 1, f"expected exactly 1 output, got {len(outputs)}"
    out = outputs[0]
    completion = out.outputs[0]

    vllm_config = llm.llm_engine.vllm_config
    resolved = {
        "model": vllm_config.model_config.model,
        "max_model_len": vllm_config.model_config.max_model_len,
        "dtype": str(vllm_config.model_config.dtype),
        "max_num_seqs": vllm_config.scheduler_config.max_num_seqs,
        "max_num_batched_tokens": vllm_config.scheduler_config.max_num_batched_tokens,
        "block_size": vllm_config.cache_config.block_size,
        "num_gpu_blocks": vllm_config.cache_config.num_gpu_blocks,
        "enable_prefix_caching": vllm_config.cache_config.enable_prefix_caching,
        "tensor_parallel_size": vllm_config.parallel_config.tensor_parallel_size,
        "world_size": vllm_config.parallel_config.world_size,
    }

    record = {
        "isolation": isolation,
        "provenance": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "packages": {
                name: package_version(name)
                for name in (
                    "vllm",
                    "vllm-rbln",
                    "optimum-rbln",
                    "rebel-compiler",
                    "torch-rbln",
                    "torch",
                    "transformers",
                    "huggingface_hub",
                )
            },
            "torch_version": torch.__version__,
            "git_commit": run("git", "-C", str(repo_root), "rev-parse", "HEAD").strip(),
            "git_dirty": bool(
                run("git", "-C", str(repo_root), "status", "--porcelain").strip()
            ),
            "rbln_devices_env": os.environ.get("RBLN_DEVICES"),
            "vllm_rbln_env": {
                k: v for k, v in sorted(os.environ.items()) if k.startswith("VLLM_RBLN")
            },
        },
        "requested": {
            "model_dir": str(args.model_dir),
            "tokenizer": args.tokenizer or str(args.model_dir),
            "prompt": prompt,
            "max_tokens": args.max_tokens,
            "temperature": 0.0,
            "seed": args.seed,
            "num_requests": 1,
        },
        "resolved_config": resolved,
        "observation": {
            "prompt_token_ids_len": len(out.prompt_token_ids),
            "output_token_ids_len": len(completion.token_ids),
            "finish_reason": completion.finish_reason,
            "output_text": completion.text,
            "output_text_len_chars": len(completion.text),
            "load_wall_clock_s": load_wall_clock_s,
            "e2e_latency_s": e2e_latency_s,
            "inference_started_at_utc": infer_started_at.isoformat(),
            "inference_finished_at_utc": infer_finished_at.isoformat(),
        },
    }

    (output_dir / "inference.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
