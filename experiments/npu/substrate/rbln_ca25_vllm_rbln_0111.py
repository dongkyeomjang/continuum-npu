#!/usr/bin/env python3
"""Measured substrate: RBLN CA25 + vllm-rbln 0.11.1 + optimum-rbln 0.11.1.

This is one *instance*. Every constant below was measured on `atom-max8` with
the `Qwen3-4B-rbln-b8-s8192-d4-mb` artifact; none of them may be carried to a
different accelerator, stack version, or compile configuration. The shapes
they instantiate live in `src/continuum/substrate/descriptor.py`.

Run this file to print the descriptor and its layer summary.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from continuum.substrate import (  # noqa: E402
    HitFormula,
    Provenance,
    StepCostModel,
    SubstrateDescriptor,
)

# Bucket-determined part of a decode step: model forward p50 + sampler p50,
# both measured per bucket in TASK13. Values in seconds.
_FIXED_S_BY_BUCKET = {
    1: (9.51 + 0.36) / 1000.0,
    2: (10.05 + 0.37) / 1000.0,
    4: (10.355 + 0.47) / 1000.0,
    8: (12.4025 + 0.5675) / 1000.0,
}

STEP_COST = StepCostModel(
    fixed_s_by_bucket=_FIXED_S_BY_BUCKET,
    # Least-squares slope of the residual (end-to-end ITL minus the two spans
    # above) against actual request count, TASK13.
    marginal_s_per_request=0.0413 / 1000.0,
    intercept_s=0.501 / 1000.0,
)

HIT_FORMULA = HitFormula(block_tokens=128, reserve_last_query_token=True)

RBLN_CA25_VLLM_RBLN_0111 = SubstrateDescriptor(
    name="RBLN-CA25 / vllm-rbln 0.11.1 / Qwen3-4B b8 s8192 d4 multi-bucket",
    bucket_sizes=(1, 2, 4, 8),
    step_cost_model=STEP_COST,
    outer_slot_count=8,
    outer_slot_tokens=8192,
    inner_block_tokens=128,
    inner_block_count=512,
    outer_eviction_policy="fifo",
    inner_eviction_policy="lru",
    hit_formula=HIT_FORMULA,
    kv_pool_tokens=8 * 8192,
    provenance={
        "bucket_sizes": Provenance(
            "stack", "TASK13", "measured",
            "decoder_batch_sizes=[8,4,2,1] at compile; mapping 1->1 2->2 3->4 "
            "4->4 5->8 6->8 7->8 8->8 observed over 4,088 decode steps",
        ),
        "step_cost_model": Provenance(
            "silicon", "TASK13", "measured",
            "model+sampler p50 per bucket; residual slope 0.0413 ms/request. "
            "Absolute values are hardware and model specific",
        ),
        "outer_slot_count": Provenance(
            "stack", "TASK14", "source-read",
            "num_ob = ceil((num_gpu_blocks-1) / block_ratio) = ceil(512/64); "
            "derived from compile batch_size, so it changes with the artifact",
        ),
        "outer_slot_tokens": Provenance(
            "stack", "TASK08", "source-read",
            "kvcache_block_size defaults to max_seq_len for eager attention",
        ),
        "inner_block_tokens": Provenance(
            "stack", "TASK08", "source-read",
            "cache_config.block_size = prefill_chunk_size = 128 on non-CR NPUs",
        ),
        "inner_block_count": Provenance(
            "stack", "TASK14", "source-read",
            "num_gpu_blocks - 1; the null block is reserved",
        ),
        "outer_eviction_policy": Provenance(
            "stack", "TASK14", "source-read",
            "FIFOEvictionPolicy is hardcoded; LRUEvictionPolicy exists unused",
        ),
        "inner_eviction_policy": Provenance(
            "class", "TASK14", "source-read",
            "vLLM FreeKVCacheBlockQueue LRU ordering; shared by every vLLM build",
        ),
        "hit_formula": Provenance(
            "class", "TASK11", "measured",
            "floor(min(shared, query-1)/128)*128 matched 10/10 conditions. The "
            "shape is vLLM's; the block size is instance level",
        ),
        "kv_pool_tokens": Provenance(
            "stack", "TASK14", "derived",
            "outer_slot_count * outer_slot_tokens. vLLM separately reports "
            "'GPU KV cache size: 65,664 tokens', which is "
            "max_concurrency * max_model_len and not the physical pool",
        ),
    },
    notes=(
        "Reuse cliff observed at background_requests = 7 and reproduced 12/12 "
        "in TASK15; survives_gap() encodes the law candidate that explains it.",
        "vllm:prefix_cache_hits_total reports the inner-block layer and can "
        "overstate actual reuse by 100%. Use vllm:prompt_tokens_cached_total "
        "or vllm:request_prefill_kv_computed_tokens for the outer layer.",
        "Measured with the TASK12 observation-only patch applied "
        "(model_base.py sha256 70942d16...).",
    ),
)


# TASK13 observed median end-to-end ITL per actual request count, in ms.
# Kept here so the descriptor stays falsifiable: if a future edit drifts from
# what was measured, main() shows it.
_OBSERVED_ITL_MS = {
    1: 10.379, 2: 10.975, 3: 11.482, 4: 11.569,
    5: 13.632, 6: 13.696, 7: 13.785, 8: 13.795,
}

# TASK14/TASK15 observed gap survival by background request count.
_OBSERVED_SURVIVAL = {0: True, 3: True, 5: True, 6: True, 7: False, 8: False}


def main() -> int:
    d = RBLN_CA25_VLLM_RBLN_0111
    print(f"substrate: {d.name}")
    print(f"  buckets            : {d.bucket_sizes}")
    print(f"  outer slots        : {d.outer_slot_count} x {d.outer_slot_tokens} tokens")
    print(f"  inner blocks       : {d.inner_block_count} x {d.inner_block_tokens} tokens")
    print(f"  block ratio        : {d.block_ratio}")
    print(f"  eviction           : outer={d.outer_eviction_policy} inner={d.inner_eviction_policy}")
    print(f"  kv pool            : {d.kv_pool_tokens:,} tokens")
    print(f"  min prefix for hit : {d.hit_formula.min_prefix_for_any_hit()} tokens")
    print()
    print(f"{'actual':>7} {'bucket':>7} {'padding':>8} {'model (ms)':>11} "
          f"{'observed':>9} {'resid':>7} {'crossing (ms)':>14}")
    worst = 0.0
    for actual in range(1, d.bucket_sizes[-1] + 1):
        predicted = d.step_time_s(actual) * 1000
        observed = _OBSERVED_ITL_MS[actual]
        resid = predicted - observed
        worst = max(worst, abs(resid))
        print(f"{actual:>7} {d.bucket_for(actual):>7} {d.padding_slots(actual):>8} "
              f"{predicted:>11.3f} {observed:>9.3f} {resid:>7.3f} "
              f"{d.bucket_crossing_cost_s(actual) * 1000:>14.3f}")
    print(f"  worst |residual| = {worst:.3f} ms")
    print()
    print("gap survival (target 2000 tok, resume 2008 tok):")
    for b in range(0, 9):
        live = d.survives_gap(background_requests=b, target_tokens=2000, resume_tokens=2008)
        obs = _OBSERVED_SURVIVAL.get(b)
        mark = "" if obs is None else ("  ok" if obs == live else "  MISMATCH")
        print(f"  B={b}: model={'live' if live else 'dead':<4}"
              f" observed={'-' if obs is None else ('live' if obs else 'dead'):<4}{mark}")
    print()
    print("layer summary:")
    for layer, names in d.layer_summary().items():
        print(f"  {layer:<9}: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
