#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
runtime_dir="$(mktemp -d /tmp/vllm-continuum-rbln.XXXXXX)"
trap 'rmdir "$runtime_dir" 2>/dev/null || true' EXIT

if [[ $# -lt 1 ]]; then
    echo "usage: $0 SCRIPT [ARG ...]" >&2
    exit 64
fi

script="$1"
shift
if [[ "$script" != /* ]]; then
    script="$repo_root/$script"
fi
if [[ ! -f "$script" ]]; then
    echo "isolation error: script not found: $script" >&2
    exit 66
fi

cd "$runtime_dir"
env -u PYTHONPATH \
    VLLM_CONTINUUM_REPO_ROOT="$repo_root" \
    /usr/bin/python3 -I "$script" "$@"
