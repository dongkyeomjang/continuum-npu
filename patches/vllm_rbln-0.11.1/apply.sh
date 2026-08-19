#!/usr/bin/env bash
# Hash-guarded apply/revert for the decoder-bucket observation patch.
#
#   sudo bash patches/vllm_rbln-0.11.1/apply.sh apply
#   sudo bash patches/vllm_rbln-0.11.1/apply.sh revert
#        bash patches/vllm_rbln-0.11.1/apply.sh status    # no root needed
#
# Fail-loud: every step verifies the target's SHA256 against the recorded
# value and aborts with a non-zero exit before touching anything on mismatch.
set -euo pipefail

PKG="vllm-rbln"
EXPECTED_VERSION="0.11.1"
TARGET="/usr/local/lib/python3.10/dist-packages/vllm_rbln/model_executor/models/optimum/model_base.py"
SHA_PRISTINE="46ce1675a2b55e36d4d6dd0154edae793cd3874ed1fbe16e74a40ed7c809298e"
SHA_PATCHED="70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01"
PATCH_FILE="$(cd "$(dirname "$0")" && pwd)/decoder_bucket_observe.patch"

die() { echo "patch guard: $*" >&2; exit 1; }

current_sha() { sha256sum "$TARGET" | cut -d' ' -f1; }

check_version() {
    local v
    v="$(/usr/bin/python3 -c 'import importlib.metadata as m; print(m.version("vllm-rbln"))')"
    [[ "$v" == "$EXPECTED_VERSION" ]] || die "$PKG version drift: expected $EXPECTED_VERSION, found $v"
}

state() {
    local sha; sha="$(current_sha)"
    case "$sha" in
        "$SHA_PRISTINE") echo "pristine" ;;
        "$SHA_PATCHED")  echo "patched" ;;
        *)               echo "drift:$sha" ;;
    esac
}

[[ -f "$TARGET" ]] || die "target not found: $TARGET"
[[ -f "$PATCH_FILE" ]] || die "patch file not found: $PATCH_FILE"

case "${1:-}" in
    status)
        check_version
        echo "target:  $TARGET"
        echo "sha256:  $(current_sha)"
        echo "state:   $(state)"
        ;;
    apply)
        check_version
        s="$(state)"
        [[ "$s" != "patched" ]] || die "already patched; nothing to do"
        [[ "$s" == "pristine" ]] || die "refusing to patch, unexpected content ($s)"
        patch --forward --strip=1 --directory="$(dirname "$TARGET")" \
              --input="$PATCH_FILE" "$TARGET" >/dev/null \
            || die "patch application failed"
        [[ "$(current_sha)" == "$SHA_PATCHED" ]] \
            || die "post-apply sha mismatch: $(current_sha)"
        /usr/bin/python3 -c "import ast,sys; ast.parse(open('$TARGET').read())" \
            || die "post-apply syntax check failed"
        echo "applied. sha256=$(current_sha)"
        ;;
    revert)
        check_version
        s="$(state)"
        [[ "$s" != "pristine" ]] || die "already pristine; nothing to do"
        [[ "$s" == "patched" ]] || die "refusing to revert, unexpected content ($s)"
        patch --reverse --strip=1 --directory="$(dirname "$TARGET")" \
              --input="$PATCH_FILE" "$TARGET" >/dev/null \
            || die "patch reversal failed"
        [[ "$(current_sha)" == "$SHA_PRISTINE" ]] \
            || die "post-revert sha mismatch: $(current_sha)"
        echo "reverted. sha256=$(current_sha)"
        ;;
    *)
        echo "usage: $0 {status|apply|revert}" >&2
        exit 64
        ;;
esac
