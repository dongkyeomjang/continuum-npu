#!/usr/bin/env bash
# Drive one (arm, N, block) combination end to end and leave its artifacts on
# disk before returning, so a long sweep can be stopped and resumed without
# losing or half-writing a combination.
#
#   run_sweep.sh <RUN_DIR> <ARM_LABEL> <N> <BLOCK> <GAP_MODE>
#
# GAP_MODE: none | zero | sync   (none = keep the drawn gaps)
set -uo pipefail

RUN="$1"; ARM="$2"; N="$3"; BLOCK="$4"; MODE="$5"
REPO=/home/rebel/continuum-npu
cd "$REPO"

# The plan seed and block id are per-experiment, not per-script: override them
# so one runner can serve different preregistered experiments without editing.
BASE_SEED="${SWEEP_BASE_SEED:-20260830}"
ARTIFACT="${SWEEP_ARTIFACT:-$REPO/models/Qwen3-4B-rbln-b8-s8192-d4-mb}"
BLOCK_PREFIX="${SWEEP_BLOCK_PREFIX:-n${N}b}"
# Return-holding policy. The default reproduces every run before TASK28: no
# policy object is built at all, so the client path is byte-identical.
POLICY="${SWEEP_POLICY:-immediate}"
BUDGET="${SWEEP_BUDGET:-0}"
BUCKETS="${SWEEP_BUCKETS:-1,2,4,8}"
TAG="${ARM}.n${N}.b${BLOCK}"
BLOCK_ID="${BLOCK_PREFIX}${BLOCK}"
DONE_MARK="$RUN/done.${TAG}"

if [ -f "$DONE_MARK" ]; then
  echo "$TAG already done, skipping"
  exit 0
fi

case "$MODE" in
  none) EXTRA="" ;;
  zero) EXTRA="--zero-gaps" ;;
  sync) EXTRA="--sync-gaps" ;;
  *) echo "$TAG: unknown gap mode $MODE"; exit 64 ;;
esac

env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG VLLM_RBLN_METRICS=1 \
  vllm serve "$ARTIFACT" \
  --host 127.0.0.1 --port 8000 \
  --enable-prefix-caching --enable-prompt-tokens-details \
  > "$RUN/server-${TAG}.log" 2>&1 &
SRV=$!

code=""
for i in $(seq 1 300); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health 2>/dev/null)
  [ "$code" = "200" ] && break
  kill -0 "$SRV" 2>/dev/null || { echo "$TAG: server died"; exit 1; }
  sleep 1
done
[ "$code" = "200" ] || { echo "$TAG: health timeout"; kill -TERM "$SRV"; exit 1; }

env -u PYTHONPATH "$REPO/experiments/npu/launch/run_isolated_python.sh" \
  experiments/npu/stage2/session_runner.py \
  --base-url http://127.0.0.1:8000 \
  --tokenizer-dir "$ARTIFACT" \
  --arm "$ARM" --sessions "$N" --turns 2 \
  --first-segment uniform:800:1600 --later-segment fixed:8 \
  --generation uniform:32:256 --gap uniform:1:5 $EXTRA \
  --base-seed "$BASE_SEED" --block-id "$BLOCK_ID" --sampling-seed 20260819 \
  --return-policy "$POLICY" --return-budget-s "$BUDGET" --buckets "$BUCKETS" \
  --output-dir "$REPO/$RUN/probe" > "$RUN/probe-${TAG}.log" 2>&1
PE=$?

curl -s http://127.0.0.1:8000/metrics > "$RUN/metrics-${TAG}.prom"

# Shut down *this* run's server by the pid we started, not by pattern: if a
# previous combination ever leaks a server, a pattern match would kill the
# wrong one and every later combination would fail in a cascade.
kill -TERM "$SRV" 2>/dev/null
for i in $(seq 1 60); do kill -0 "$SRV" 2>/dev/null || break; sleep 1; done
if kill -0 "$SRV" 2>/dev/null; then
  kill -KILL "$SRV" 2>/dev/null
  sleep 5
  echo "$TAG: server needed SIGKILL"
fi
wait "$SRV" 2>/dev/null

# session_runner writes requests.<arm>.<block_id>.jsonl; give it the combination
# name so combinations never collide in the probe directory.
mv "$RUN/probe/requests.${ARM}.${BLOCK_ID}.jsonl" "$RUN/probe/requests.${TAG}.jsonl" 2>/dev/null
mv "$RUN/probe/meta.${ARM}.${BLOCK_ID}.json" "$RUN/probe/meta.${TAG}.json" 2>/dev/null

[ "$PE" -eq 0 ] && date -Is > "$DONE_MARK"
echo "$TAG done (probe exit $PE)"
