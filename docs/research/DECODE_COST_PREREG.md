# 선등록 — decode step 비용 모델: bucket 결정적인가, actual 결정적인가

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다. 결과와 판정은 후속 TASK 문서에 기록한다.

## 연구 질문과 가설

**RQ**: decode step의 시간 비용은 `selected_bucket`의 함수인가, `request_nums`의 함수인가?

**H (선등록 예측)**: RBLN decoder는 bucket별로 따로 compile된 static graph(`decoder_batch_{1,2,4,8}.rbln`)를 실행하므로, **같은 bucket 안에서는 actual `request_nums`와 무관하게 step 시간이 동일**하고 bucket 경계를 넘을 때만 계단형으로 변한다.

H가 채택되면 [TASK12](TASK12.md)가 정량화한 slot 낭비율이 **시간 의미를 갖는 metric으로 승격**되고, 낭비율 → 시간 환산 상수가 확정된다. H가 기각되면(같은 bucket 안에서 actual 의존이 관측되면) **그 형태 자체가 Track A의 새 관찰**이다. 어느 쪽이든 결과다.

## 승인 범위 (사용자 판정, 2026-08-19)

- b8 artifact serving 기동·종료(횟수 제한 없음), localhost 요청
- `VLLM_LOGGING_LEVEL=DEBUG` + `VLLM_RBLN_METRICS=1` 병용
- `src/continuum/workload/paired.py`의 seed/ordering 유틸 사용

범위 밖: 재compile, 신규 download, patch 추가·수정, APC OFF 실험, RSD 변경, remote push 자동 수행.

Server는 매 lifecycle 종료 시 **PID를 특정해** 확인한다.

## Substrate 상태 (provenance 필수)

이 host의 `vllm-rbln 0.11.1`은 [TASK12](TASK12.md)의 observation-only patch가 **적용된 상태**다. 모든 run의 artifact에 `bash patches/vllm_rbln-0.11.1/apply.sh status` 출력을 포함한다.

| 항목 | 값 |
|---|---|
| 대상 | `vllm_rbln/model_executor/models/optimum/model_base.py` |
| 기대 SHA256 | `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01` |
| 기대 state | `patched` |

측정 전 state가 `patched`가 아니면 측정을 시작하지 않는다.

## 측정 채널과 그 한계 (측정 전 고정)

네 채널을 병행하고 **채택 전 상호 대조**한다.

| 채널 | 내용 | 해상도·한계 |
|---|---|---|
| **A** — `[BUCKET]` 로그 rate | 초당 `[BUCKET]` 줄 수 → decode step/s | vLLM logger의 `_DATE_FORMAT`이 `"%m-%d %H:%M:%S"`라 **timestamp 해상도가 1초**다. 따라서 per-step 간격이 아니라 **초당 step 수(rate)** 만 얻는다. 생성 구간이 짧으면 표본이 몇 개뿐이다 |
| **B** — `VLLM_RBLN_METRICS=1` DECODE METRICS | mean/p50/p90/p99/max step latency(ms), host/device/ccl/prepare 평균 | `optimum_worker.shutdown()`의 `print_final_stats()`로 **server 종료 시 1회만** 출력되며 server lifetime 전체를 누적한다. 요약 통계라 raw sample이 없어 **bootstrap 불가**. → 수준마다 server를 따로 띄워야 귀속된다 |
| **C** — client streaming ITL | streaming content chunk 간격의 raw sample | **bootstrap의 유일한 raw 표본원.** client 측 값이므로 HTTP·thread 오버헤드를 포함한다. 동시성이 커질수록 client thread가 늘어 **client 측 jitter가 actual 의존처럼 보일 수 있다** — 채널 D가 이 confounder를 검사한다 |
| **D** — `vllm:inter_token_latency_seconds` | server 측 sum/count 증분 → 평균 ITL | client threading의 영향을 받지 않는다. C와 자릿수·경향이 어긋나면 C의 client 측 오염을 의심한다 |

**세 채널 이상이 자릿수 또는 경향에서 어긋나면 원인 규명 전에 판정하지 않는다.**

## 실험 설계

### server 구성

**수준마다 server를 새로 띄운다** (채널 B가 lifetime 누적이므로). 총 8개 lifecycle.

수준 실행 순서는 `src/continuum/workload/paired.py`의 `balanced_arm_orders`로 블록 랜덤화한다.

```python
balanced_arm_orders([str(i) for i in range(1, 9)], rounds=1,
                    base_seed=20260819, block_id="task13-pilot")
```

→ **`(4, 8, 2, 7, 3, 1, 5, 6)`** (결정적으로 재현된다)

이 순서로 실행해 시간 경과에 따른 drift(device 온도 등)가 수준 번호와 교란되지 않게 한다. 파일럿은 **1 블록**이며, 판정이 `INCONCLUSIVE`면 블록 반복 확장을 다음 TASK로 넘긴다.

### 고정 파라미터

| 항목 | 값 |
|---|---|
| Model | `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음, `decoder_batch_sizes=[8,4,2,1]`) |
| Server | `vllm serve <artifact> --host 127.0.0.1 --port 8000` |
| 환경변수 | `VLLM_LOGGING_LEVEL=DEBUG`, `VLLM_RBLN_METRICS=1` (전 수준 동일) |
| `RBLN_DEVICES` | 설정하지 않음 |
| Prompt | `experiments/npu/stage1/prompt.txt` (전 수준 동일, 20 token) |
| Sampling | `temperature=0.0`, `top_p=1.0` |
| `max_tokens` | **512** (수준 내 `request_nums`가 일정하도록 전 요청 동일) |
| Seed | 20260819 |
| 동시성 수준 | 1, 2, 3, 4, 5, 6, 7, 8 (전 수준, [TASK12](TASK12.md) 미관측 사상 6→8, 7→8 포함) |
| 요청 방식 | 각 수준에서 N개 동시 streaming 요청 |

전 요청이 같은 prompt·같은 `max_tokens`이므로 [TASK12](TASK12.md)처럼 수준 안에서 `request_nums`가 일정하게 유지될 것으로 본다. 실제로 그러한지는 `[BUCKET]` 로그로 확인하며, **일정하지 않으면 그 사실을 기록하고 해당 수준의 ITL 표본을 판정에서 제외**한다.

### ITL 표본 정의

각 요청의 streaming content chunk 도착 시각 차이를 표본으로 한다. **첫 chunk는 prefill을 포함하므로 제외**한다. 수준 N의 population = N개 요청의 모든 간격을 합친 것. Unit: 초. Source: client. Device scope: `rbln0`–`rbln3`.

## 판정 기준

**동치·차이 판정은 중앙 ratio의 bootstrap CI로 한다** (고정 밴드 금지, 저장소 원칙).

- 추정: percentile bootstrap, **resamples = 2,000**, 95 % CI
- 재현: 표본 재추출 seed는 `derive_block_seed(base_seed=20260819, label="<a>v<b>")`로 결정적으로 유도한다
- **사전 등록 CI 폭 상한: 0.10**

| 판정 | 조건 |
|---|---|
| `EQUIVALENT` | CI가 1을 포함하고 **CI 폭 ≤ 0.10** |
| `DIFFERENT` | CI가 1을 배제 |
| `INCONCLUSIVE` | CI가 1을 포함하나 폭 > 0.10 (검정력 부족) |

### 동치를 요구하는 쌍 (같은 bucket 안)

| 쌍 | bucket |
|---|---|
| 3 vs 4 | 4 |
| 5 vs 6 | 8 |
| 5 vs 7 | 8 |
| 5 vs 8 | 8 |
| 6 vs 7 | 8 |
| 6 vs 8 | 8 |
| 7 vs 8 | 8 |

### 차이를 요구하는 쌍 (bucket 경계)

| 쌍 | bucket 전이 |
|---|---|
| 1 vs 2 | 1 → 2 |
| 2 vs 3 | 2 → 4 |
| 4 vs 5 | 4 → 8 |

### H의 채택·기각

- **H 채택**: 동치 쌍 7개가 전부 `EQUIVALENT`이고 차이 쌍 3개가 전부 `DIFFERENT`
- **H 기각**: 동치 쌍 중 하나라도 `DIFFERENT` → 같은 bucket 안에서 actual 의존이 관측된 것이다. 그 형태(단조 증가인지 등)를 기술한다
- **`PARTIAL`**: `INCONCLUSIVE`가 하나라도 있으면 그 쌍을 검정력 부족으로 기록하고 전체 판정을 `PARTIAL`로 한다. 사후에 CI 폭 상한을 완화하지 않는다
- 차이 쌍이 `EQUIVALENT`로 나오면 → bucket이 step 시간을 결정하지 않는다는 뜻이므로 **H 기각**이며 별도로 기술한다

### 채널 대조 게이트 (판정 전 통과 필요)

1. 채널 B의 DECODE mean과 채널 C의 median ITL이 **같은 자릿수**여야 한다
2. 채널 A의 `1 / (step/s)`가 위 둘과 **같은 자릿수**여야 한다
3. 채널 D의 평균 ITL이 채널 C의 평균과 **같은 자릿수**여야 한다
4. bucket 경계에서의 증가 **방향**이 채널 B·C·D에서 일치해야 한다

하나라도 어긋나면 판정하지 않고 원인을 조사해 기록한다.

## 사전 예측 (판정 기준 아님)

| # | 예측 | 근거 |
|---|---|---|
| 1 | `[BUCKET]` 사상: 1→1, 2→2, 3→4, 4→4, 5→8, 6→8, 7→8, 8→8 | `select_bucket_size`. 6→8, 7→8은 [TASK12](TASK12.md) 미관측분 |
| 2 | step 시간이 bucket 순으로 단조 증가: b1 < b2 < b4 < b8 | 큰 batch graph가 더 많은 연산을 한다 |
| 3 | 같은 bucket 안에서는 동치 | H |
| 4 | 채널 B·C·D가 같은 자릿수 | 모두 같은 step을 다른 지점에서 잰다 |
| 5 | 채널 C median ITL은 10 ms 자릿수 | [TASK12](TASK12.md)의 127 step / 약 1.5 s |
| 6 | `prefix_cache_hits` 증분 0 | prompt 20 token < 129 문턱 ([TASK11](TASK11.md)) |
| 7 | 채널 B의 device time이 host time보다 크다 | NPU 실행이 지배적일 것 |

예측 7은 근거가 약하며 확신도가 낮다고 명시해 둔다.

## 필수 측정 항목

- 수준별: 요청 status, chunk 수, wall-clock, ITL raw 표본 전체, `[BUCKET]` 쌍 빈도
- 채널 B: 수준별 DECODE METRICS 전문(call counts, mean, p50/p90/p99/max, host/device/ccl/prepare)
- 채널 A: 초당 `[BUCKET]` 줄 수
- 채널 D: `vllm:inter_token_latency_seconds` sum/count 증분
- bucket별 step 시간 상수 표 (파생 산출)
- **patch state**: 각 run의 `apply.sh status` 출력
- `rbln-smi`: 첫 기동 전, 마지막 종료 후
- provenance: git commit과 dirty 여부, package version, model 경로, hostname, 환경변수, patch SHA256

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-decode-cost`

1. `apply.sh status`로 `patched` 확인 → `<RUN>/patch-state.txt`. 아니면 중단
2. 순서 `(4, 8, 2, 7, 3, 1, 5, 6)`대로 각 수준에서:
   a. server 기동(`VLLM_LOGGING_LEVEL=DEBUG VLLM_RBLN_METRICS=1`), `/health` 200 대기
   b. probe 실행

      ```bash
      env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
        experiments/npu/stage2/decode_cost_probe.py \
        --base-url http://127.0.0.1:8000 \
        --prompt-file /home/rebel/continuum-npu/experiments/npu/stage1/prompt.txt \
        --level <N> --max-tokens 512 --seed 20260819 \
        --output-dir <절대경로>/<RUN>/probe
      ```

   c. PID를 특정해 `SIGTERM`, 종료·port 해제 확인. DECODE METRICS는 이때 로그에 남는다
3. 채널 A·B를 로그에서 집계
4. bootstrap 분석

   ```bash
   env -u PYTHONPATH python3 experiments/npu/analysis/bootstrap_ratio.py \
     --input-dir <RUN>/probe --base-seed 20260819 --resamples 2000 \
     --ci-width-max 0.10 \
     --pairs 3:4,5:6,5:7,5:8,6:7,6:8,7:8,1:2,2:3,4:5 \
     --output <RUN>/bootstrap.json
   ```

5. 채널 대조 게이트 → 판정

## FAIL / PARTIAL 처리 규칙 (측정 전 고정)

| 상황 | 판정 |
|---|---|
| 측정 전 patch state가 `patched`가 아님 | `BLOCKED`. 즉시 중단·보고 |
| server 기동 실패 또는 요청 non-200 | `FAILED`. 로그 보존 |
| 수준 안에서 `request_nums`가 일정하지 않음 | 그 수준을 판정에서 제외하고 사실을 기록. 남은 쌍으로 `PARTIAL` 판정 |
| 채널 대조 게이트 실패 | 판정 보류. 불일치 내용을 기록하고 `PARTIAL` |
| `INCONCLUSIVE` 쌍 존재 | `PARTIAL`. 검정력 부족으로 기록, CI 폭 상한 완화 금지 |
| 종료 후 device memory 미복귀 | `PARTIAL`. 잔존 context 기록 후 보고 |

## 관련 문서

- [TASK12](TASK12.md) — `[BUCKET]` 관측 patch와 slot 낭비율. 이 TASK가 그 낭비율에 시간 의미를 부여할 수 있는지 판정한다
- [TASK11](TASK11.md) — prefix cache 문턱 129 token (예측 6의 근거)
- [TASK10](TASK10.md) — `decoder_batch_sizes=[8,4,2,1]` artifact의 출처
- [patches/vllm_rbln-0.11.1/README.md](../../patches/vllm_rbln-0.11.1/README.md) — substrate 상태
