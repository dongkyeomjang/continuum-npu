"""Versioned accelerator-neutral observation record."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "continuum-observation-v1"
RESUME_SOURCES = {
    "LOCAL_KV_HIT",
    "PREFIX_CACHE_HIT",
    "LOCAL_OR_PREFIX_HIT",
    "HOST_RELOAD",
    "PEER_NPU_RELOAD",
    "RECOMPUTE_OR_REPREFILL",
    "PARTIAL",
    "UNKNOWN",
}

REQUIRED_FIELDS = (
    "schema_version",
    "request_id",
    "logical_session_id",
    "trial_id",
    "arm",
    "prompt_tokens",
    "output_tokens",
    "tool_start_ts",
    "tool_return_ts",
    "enqueue_ts",
    "first_token_ts",
    "completion_ts",
    "tool_return_to_enqueue_s",
    "enqueue_to_first_token_s",
    "tool_return_to_first_token_s",
    "accelerator_kv_usage_ratio",
    "kv_pool_capacity_bytes",
    "kv_usage_source",
    "device_scope",
    "local_cached_tokens",
    "subblock_cached_tokens",
    "external_cached_tokens",
    "computed_tokens",
    "resume_source",
    "resume_evidence",
    "classification_confidence",
    "actual_decode_batch_size",
    "selected_decoder_bucket",
    "decoder_bucket_utilization",
    "requested_condition",
    "observed_condition",
    "condition_reached",
)


def empty_record() -> dict[str, Any]:
    record = {key: None for key in REQUIRED_FIELDS}
    record.update(
        {
            "schema_version": SCHEMA_VERSION,
            "resume_source": "UNKNOWN",
            "resume_evidence": [],
            "classification_confidence": "UNKNOWN",
        }
    )
    return record


def validate_record(record: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_FIELDS if key not in record]
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    if record["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {record['schema_version']!r}")
    if record["resume_source"] not in RESUME_SOURCES:
        raise ValueError(f"invalid resume_source: {record['resume_source']!r}")

    actual = record["actual_decode_batch_size"]
    selected = record["selected_decoder_bucket"]
    if actual is not None and selected is not None:
        if actual < 0 or selected <= 0 or selected < actual:
            raise ValueError(
                f"invalid decoder batch: actual={actual}, selected={selected}"
            )
        expected = actual / selected
        observed = record["decoder_bucket_utilization"]
        if observed is not None and abs(observed - expected) > 1e-9:
            raise ValueError("decoder_bucket_utilization does not match batch sizes")

    prompt_tokens = record["prompt_tokens"]
    if prompt_tokens is not None:
        for field in (
            "local_cached_tokens",
            "subblock_cached_tokens",
            "external_cached_tokens",
            "computed_tokens",
        ):
            value = record[field]
            if value is not None and (value < 0 or value > prompt_tokens):
                raise ValueError(
                    f"{field}={value} exceeds prompt_tokens={prompt_tokens}"
                )
