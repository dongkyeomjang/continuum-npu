# `vllm-rbln 0.11.1` — decoder bucket observation patch

[patches/README.md](../README.md)의 7개 항목을 이 문서가 채운다. 승인 근거는 [INDEX](../../docs/research/INDEX.md)의 **결정 3**이며 판정 근거는 [TASK10](../../docs/research/TASK10.md)이다.

## 1. 대상 package와 exact version

- Package: `vllm-rbln`
- Version: **`0.11.1`** (`importlib.metadata.version("vllm-rbln")`로 확인)
- 실행 경로: `VLLM_RBLN_USE_VLLM_MODEL=False` (기본). 이 patch는 optimum 경로 전용이다.

`apply.sh`가 매 호출마다 version을 확인하고 다르면 비-0 exit으로 중단한다.

## 2. Upstream file path와 SHA256

| 항목 | 값 |
|---|---|
| 경로 | `/usr/local/lib/python3.10/dist-packages/vllm_rbln/model_executor/models/optimum/model_base.py` |
| 적용 전 SHA256 | `46ce1675a2b55e36d4d6dd0154edae793cd3874ed1fbe16e74a40ed7c809298e` |
| 적용 후 SHA256 | `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01` |
| 대상 함수 | `RBLNOptimumDecoderMixin.preprocess_for_decoder` |
| Diff 규모 | **추가 9줄(주석 4 + 코드 5), 기존 줄 수정 0, 삭제 0** |

## 3. Scheduler / batch selection / KV allocation semantics를 바꾸지 않는 근거

추가된 코드는 `logger.debug(...)` 호출 하나뿐이다.

- **제어 흐름 무변경**: 분기, 반복, 예외 경로를 추가하지 않는다. `padded_batch_size`는 이미 계산된 값을 읽기만 한다.
- **batch selection 무변경**: `select_bucket_size`(`vllm_rbln/utils/optimum/bucket.py:20`)와 `self.decoder_batch_sizes`를 건드리지 않는다. 이 함수에는 `@cache`가 걸려 있는데, 함수를 감싸지 않고 **caller에서 결과를 읽기만** 하므로 cache 동작도 바뀌지 않는다.
- **scheduler 무변경**: patch는 model runner 하위의 model wrapper에 있고 scheduler(`optimum_scheduler.py`)와 KV cache manager(`optimum_kv_cache_manager.py`)는 대상이 아니다.
- **KV allocation 무변경**: `pad_decoder_items`, block table, `dummy_block`을 건드리지 않는다.
- **새 실패 모드 없음**: `input_ids`가 `None`일 수 있는 경로를 `input_ids.shape[0] if input_ids is not None else None`으로 방어한다.
- **기본 실행에서 무출력**: level이 `DEBUG`이므로 `VLLM_LOGGING_LEVEL=DEBUG` 없이는 아무것도 출력하지 않는다.

## 4. Observation-only 변경을 우선했다는 검토 결과

[TASK10](../../docs/research/TASK10.md) "핵심 산출"에서 선등록으로 한정한 4개 수단(DEBUG 로그 전문, `/metrics` 122개 항목, `VLLM_RBLN_METRICS=1`, 기타 read-only 경로)을 모두 검색해 per-step `(요청 수, 선택된 bucket)` 노출 경로가 없음을 확인했다. 계산 자체는 실행 경로에 이미 존재하므로 값을 새로 만들지 않고 **읽어서 내보내기만** 하는 변경을 선택했다.

대안 검토는 [INDEX](../../docs/research/INDEX.md) 결정 3의 "대안" 표에 있다.

## 5. 적용 명령과 복구 명령

```bash
# 상태 확인 (root 불필요)
bash patches/vllm_rbln-0.11.1/apply.sh status

# 적용 / 복구 (site-packages가 root 소유이므로 root 필요)
sudo bash patches/vllm_rbln-0.11.1/apply.sh apply
sudo bash patches/vllm_rbln-0.11.1/apply.sh revert
```

`apply`는 적용 후 SHA256과 `ast.parse` 문법 검사를 모두 통과해야 성공으로 종료한다. `revert`는 복구 후 SHA256이 pristine 값과 일치해야 성공으로 종료한다.

## 6. Version / hash drift 시 fail-loud 중단 방법

`apply.sh`는 모든 하위 명령에서 다음 순서로 검사하고, 어긋나면 파일을 건드리기 **전에** 비-0으로 종료한다.

1. `vllm-rbln` version ≠ `0.11.1` → `version drift` 중단
2. 대상 파일 부재 → 중단
3. 현재 SHA256이 pristine·patched 어느 쪽도 아님 → `drift:<sha>`로 분류하고 `refusing to patch/revert` 중단
4. `apply` 시 이미 patched, `revert` 시 이미 pristine → `nothing to do` 중단
5. 적용/복구 후 SHA256이 기대값과 다름 → 중단
6. 적용 후 문법 검사 실패 → 중단

`set -euo pipefail`이므로 중간 명령 실패도 즉시 전파된다.

## 7. Patch 적용 여부를 run metadata에 남기는 방법

측정 run마다 아래를 artifact 디렉터리의 `patch-state.txt`로 캡처한다.

```bash
bash patches/vllm_rbln-0.11.1/apply.sh status > <RUN>/patch-state.txt
```

출력에는 대상 경로, 현재 SHA256, `pristine|patched|drift:<sha>` 상태가 들어간다. TASK의 `## 재현 정보`에 이 파일 경로와 그때의 state를 함께 적는다.
