# 선등록 — decoder bucket 관측 patch의 적용·검증

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작하고 patch를 적용한다. 측정 후 판정 기준을 완화하지 않는다. 결과와 판정은 후속 TASK 문서에 기록한다.

`patches/` 정책의 첫 실전 적용이므로 절차 자체가 선례가 된다.

## 목적

[INDEX](INDEX.md) **결정 3**이 승인됐다. [TASK10](TASK10.md)이 "관측 불가"로 판정한 per-step `(실제 요청 수, 선택된 decoder bucket)`을 hash-guarded observation-only patch로 노출시키고, **그 신호가 실제로 의미하는 바를 채택 전에 검증한다.**

## 승인 범위 (사용자 판정, 2026-08-19)

- 결정 3 승인. `patches/` 정책에 따른 patch 파일 작성과 **적용·복구** (SHA256 guard 필수)
- 기존 b8 artifact로의 serving 기동·종료, localhost 요청

범위 밖: 재compile, 신규 download, RSD 변경, patch 이외의 site-packages 수정, Stage 2 본 실험, remote push 자동 수행.

Server process는 작업 종료 시 **PID를 특정해** 종료하고 종료를 확인한다.

## Patch (측정 전 확정, 이 commit에 포함)

| 항목 | 값 |
|---|---|
| 파일 | `patches/vllm_rbln-0.11.1/decoder_bucket_observe.patch` |
| 대상 | `vllm_rbln/model_executor/models/optimum/model_base.py`의 `RBLNOptimumDecoderMixin.preprocess_for_decoder` |
| 규모 | **추가 9줄(주석 4 + 코드 5), 기존 줄 수정 0, 삭제 0** |
| 적용 전 SHA256 | `46ce1675a2b55e36d4d6dd0154edae793cd3874ed1fbe16e74a40ed7c809298e` |
| 적용 후 SHA256 | `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01` |
| guard script | `patches/vllm_rbln-0.11.1/apply.sh` (`status` / `apply` / `revert`) |
| 정책 7항목 | `patches/vllm_rbln-0.11.1/README.md` |

내보내는 로그 한 줄:

```text
[BUCKET] request_nums=<int|None> padded_batch_size=<int>
```

## 검증 기준 (patch 적용 전 고정)

세 관문을 **전부** 통과해야 신호를 채택하고 patch를 적용 상태로 유지한다.

### 관문 1 — 의미론 검증 (전건 일치 요구)

동시성 **1 → 2 → 3 → 5 → 8** sweep에서 관측된 모든 `(request_nums, padded_batch_size)` 쌍이 `select_bucket_size`의 기대 사상과 **전건 일치**해야 한다.

기대 사상은 "`decoder_batch_sizes`(오름차순 `(1, 2, 4, 8)`) 중 `request_nums` 이상인 최소값"이다.

| `request_nums` | 기대 `padded_batch_size` |
|---|---|
| 1 | 1 |
| 2 | 2 |
| 3 | **4** |
| 4 | 4 |
| 5 | **8** |
| 6 | 8 |
| 7 | 8 |
| 8 | 8 |

동시성 수준 N을 요청해도 요청이 끝나면서 step별 `request_nums`가 줄어드므로 **관측되는 값은 1..N의 여러 값**이 된다. 판정은 요청한 N이 아니라 **관측된 각 쌍**에 대해 한다.

- 관측된 쌍이 하나라도 위 사상과 어긋나면 → **신호 채택 보류.** 불일치 쌍을 전부 기록하고 원인을 조사한다. patch는 revert한다.
- 동시성 3과 5에서 각각 `request_nums=3 → 4`, `request_nums=5 → 8`인 쌍이 **최소 1회씩 관측되어야** 한다. bucket 경계를 넘는 사상이 실제로 관측되지 않으면 사상표의 흥미로운 부분이 검증되지 않은 것이므로 `PARTIAL`로 기록한다.

### 관문 2 — 관찰자 효과 게이트

동일 조건·동일 요청 세트를 **patch 적용 전 1회(run A)** 와 **적용 후 1회(run B)** 실행해 e2e latency의 **자릿수 변화가 없음**을 확인한다.

- n = 1 비교이므로 ±수치 기준을 걸지 않는다. **통계적 주장을 하지 않는다.**
- 판정: 각 동시성 수준에서 run A와 run B의 wall-clock이 같은 자릿수(10배 이내)이면 통과.
- 자릿수가 달라지면 → 신호 채택 보류, patch revert, 원인 기록.

두 run 모두 `VLLM_LOGGING_LEVEL=DEBUG`로 실행한다. DEBUG 자체의 비용을 두 run이 공유하게 해서 patch의 순효과만 비교하기 위해서다.

### 관문 3 — 복구 검증

`sudo bash patches/vllm_rbln-0.11.1/apply.sh revert` 후 대상 파일의 SHA256이 pristine 값(`46ce1675…`)과 일치해야 한다.

관문 1·2를 통과했으면 검증 후 다시 `apply`해서 **적용 상태로 유지**한다. 최종 상태를 `apply.sh status`로 기록한다.

## 실험 격자

| 요소 | 고정값 |
|---|---|
| Model | `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음, `decoder_batch_sizes=[8,4,2,1]`) |
| Server | `vllm serve <artifact> --host 127.0.0.1 --port 8000` |
| 환경변수 | `VLLM_LOGGING_LEVEL=DEBUG` (run A·B 동일) |
| `RBLN_DEVICES` | 설정하지 않음 |
| Prompt | `experiments/npu/stage1/prompt.txt` (Stage 1과 동일) |
| Sampling | `temperature=0.0`, `top_p=1.0` |
| `max_tokens` | 128 |
| Seed | 20260819 |
| 동시성 수준 | 1, 2, 3, 5, 8 (각 수준 1회) |
| probe | `experiments/npu/stage1/concurrency_probe.py` (기존 script 재사용, 변경 없음) |

동시성 3과 5를 넣은 이유는 bucket 경계를 넘는 사상(3→4, 5→8)을 관측하기 위해서다.

## 사전 예측 (판정 기준 아님)

| # | 예측 | 근거 |
|---|---|---|
| 1 | run A(적용 전)에는 `[BUCKET]` 로그가 0줄 | patch 미적용 |
| 2 | run B에는 매 decode step마다 1줄 | `preprocess_for_decoder`가 decode step마다 호출됨 |
| 3 | 관측된 쌍이 사상표와 전건 일치 | `select_bucket_size`의 `bisect_left` 구현 |
| 4 | `request_nums=3`에서 `padded_batch_size=4` → padding 낭비 1 slot | 사상표 |
| 5 | `request_nums=5,6,7`에서 `padded_batch_size=8` → 낭비 3,2,1 slot | 사상표 |
| 6 | latency 자릿수 변화 없음 | 추가된 것이 `logger.debug` 1회뿐 |
| 7 | `request_nums=None`인 줄은 나오지 않는다 | decode 경로에서 `input_ids`는 항상 존재 |

## 필수 측정 항목

- run A·B 각각의 동시성 수준별 wall-clock, 요청 status, `num_requests_running` 최대값
- run B의 `[BUCKET]` 로그 전체와 그로부터 집계한 `(request_nums, padded_batch_size)` 쌍의 빈도표
- patch 적용 전/후/복구 후의 SHA256과 `apply.sh status` 출력
- `rbln-smi`: 각 server lifecycle의 기동 전·종료 후
- provenance: git commit과 dirty 여부, package version, model 경로, hostname, **patch 적용 상태**

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage1/<timestamp>-bucket-patch`

1. `apply.sh status`로 pristine 확인 → `<RUN>/patch-state-before.txt`
2. **run A** (patch 미적용): server 기동 → 동시성 sweep 1,2,3,5,8 → 종료 확인
3. `sudo bash patches/vllm_rbln-0.11.1/apply.sh apply` → `<RUN>/patch-state-applied.txt`
4. **run B** (patch 적용): 동일 조건으로 server 기동 → 동일 sweep → 종료 확인
5. run B 로그에서 `[BUCKET]` 집계, 관문 1 판정
6. run A vs run B wall-clock 대조, 관문 2 판정
7. `sudo bash .../apply.sh revert` → SHA256 확인, 관문 3 판정 → `<RUN>/patch-state-reverted.txt`
8. 관문 1·2·3 통과 시 다시 `apply` → `<RUN>/patch-state-final.txt`

`sudo`가 필요한 3·7·8단계는 site-packages가 root 소유이기 때문이다. 이 단계에서 password가 필요하면 사용자에게 실행을 요청하고 그 사실을 TASK에 기록한다.

## FAIL / PARTIAL 처리 규칙 (측정 전 고정)

| 상황 | 판정 |
|---|---|
| `apply.sh`가 version/SHA drift로 중단 | `BLOCKED`. drift 내용 기록 후 보고 |
| patch 적용 후 server 기동 실패 | `FAILED`. 즉시 revert하고 로그 보존 |
| 관문 1 불일치 | `PARTIAL`. 불일치 쌍 기록, 신호 채택 보류, patch revert |
| 3→4 또는 5→8 쌍이 관측되지 않음 | `PARTIAL`. 사상표의 경계 부분 미검증으로 기록 |
| 관문 2에서 자릿수 변화 | `PARTIAL`. patch revert |
| 관문 3 SHA 불일치 | `FAILED`. 즉시 보고. 이 경우 patch 절차 자체를 신뢰할 수 없다 |

## 관련 문서

- [INDEX](INDEX.md) — 결정 3
- [TASK10](TASK10.md) — 관측 불가 판정과 patch 제안의 근거
- [patches/README.md](../../patches/README.md) — 정책 7항목
- [patches/vllm_rbln-0.11.1/README.md](../../patches/vllm_rbln-0.11.1/README.md) — 이 patch의 정책 문서
