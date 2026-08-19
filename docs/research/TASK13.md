# TASK13 — decode step 비용 모델: bucket 결정적인가, actual 결정적인가

## 상태

DONE

## 판정

**선등록한 H는 기각됐다.** 판정 기준으로 등록한 채널 C(end-to-end ITL)의 bootstrap에서 **동치를 요구한 7개 쌍이 전부 `DIFFERENT`** 로 나왔다. 같은 bucket 안에서도 actual `request_nums`에 의존하는 성분이 있다.

다만 **비용이 두 성분으로 분해된다**는 것이 이번의 실질적 발견이다. 채널 B(model 실행 span)는 bucket이 결정하고(같은 bucket 안 범위 ≤ 0.03 ms), actual 의존은 model·sampler 밖의 engine overhead에 있으며 요청당 약 **0.041 ms**다. 전체 ITL에서 그 비중은 bucket 효과보다 훨씬 작다(같은 bucket 내 최대 +1.2 % vs bucket 경계 +5.7~17.8 %).

## 날짜

2026-08-19

## 목적

decode step의 시간 비용이 `selected_bucket`의 함수인지 `request_nums`의 함수인지 판정한다. [TASK12](TASK12.md)가 정량화한 slot 낭비율이 시간 의미를 갖는 metric으로 승격될 수 있는지가 걸려 있다.

## 배경

관련 TASK:

- [TASK12](TASK12.md) — `[BUCKET]` 관측 patch. slot 낭비율(동시성 3에서 25 %, 5에서 37.5 %)을 산술로 정량화했으나 시간 비용과의 관계는 미측정으로 남겼다. `request_nums` 6·7의 사상도 `UNKNOWN`이었다.
- [TASK11](TASK11.md) — prefix cache 문턱 129 token (예측 6의 근거).
- [TASK10](TASK10.md) — `decoder_batch_sizes=[8,4,2,1]` artifact의 출처.

선등록 문서: [DECODE_COST_PREREG.md](DECODE_COST_PREREG.md)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `241b7b8084464d1d460c1d9607c9ecca305b4af8`
- Git dirty: untracked `.idea/`만
- **Substrate: patched.** `model_base.py` SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01` ([TASK12](TASK12.md)의 observation-only patch). 측정 전 gate를 통과했다
- Host: `atom-max8`. Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(patched), `optimum-rbln 0.11.1`
- Device: 32 visible ID 전부 idle, port 8000 비어 있음
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)

## 수행 내용

1. 측정 채널 4개의 해상도와 한계를 source에서 확인했다 (vLLM logger의 `_DATE_FORMAT`이 1초 해상도, `VLLM_RBLN_METRICS`가 shutdown 시 lifetime 누적으로만 출력).
2. 선등록 문서, probe script, bootstrap 분석 script를 **측정 시작 전에** commit했다 (`241b7b8`).
3. Patch state gate를 통과한 뒤, `balanced_arm_orders`가 결정적으로 준 순서 **`(4, 8, 2, 7, 3, 1, 5, 6)`** 대로 수준마다 server를 새로 띄우고 측정했다.
4. 각 수준에서 N개 동시 streaming 요청(`max_tokens=512`)을 보내고 chunk 도착 시각으로 ITL raw 표본을 수집했다.
5. Server 종료 시 로그에 남는 DECODE/SAMPLER METRICS를 수집하고 `[BUCKET]` 사상과 초당 줄 수를 집계했다.
6. 채널 대조 게이트 4개를 통과시킨 뒤 bootstrap CI로 판정했다.

재compile, download, patch 변경, RSD 변경은 없었다.

## 변경된 파일

선등록 commit `241b7b8`:

- `docs/research/DECODE_COST_PREREG.md` (신규)
- `experiments/npu/stage2/decode_cost_probe.py` (신규)
- `experiments/npu/analysis/bootstrap_ratio.py` (신규)

이번 기록 commit:

- `docs/research/TASK13.md` (신규)
- `docs/research/INDEX.md`

Raw artifact는 `.gitignore` 대상인 `results/npu/stage2/20260819-194900-decode-cost/`에 있다.

## 실험 또는 검증 방법

`<RUN>` = `results/npu/stage2/20260819-194900-decode-cost`

수준마다(순서 `4,8,2,7,3,1,5,6`):

```bash
env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG VLLM_RBLN_METRICS=1 \
  vllm serve /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb \
  --host 127.0.0.1 --port 8000 > <RUN>/server-level<N>.log 2>&1 &

env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage2/decode_cost_probe.py \
  --base-url http://127.0.0.1:8000 \
  --prompt-file /home/rebel/continuum-npu/experiments/npu/stage1/prompt.txt \
  --level <N> --max-tokens 512 --seed 20260819 \
  --output-dir /home/rebel/continuum-npu/<RUN>/probe

# PID 특정 후 SIGTERM (이때 DECODE/SAMPLER METRICS가 로그에 남는다)
```

판정:

```bash
env -u PYTHONPATH python3 experiments/npu/analysis/bootstrap_ratio.py \
  --input-dir <RUN>/probe --base-seed 20260819 --resamples 2000 \
  --ci-width-max 0.10 \
  --pairs 3:4,5:6,5:7,5:8,6:7,6:8,7:8,1:2,2:3,4:5 \
  --output <RUN>/bootstrap.json
```

## 결과

### 조건 분리

- `requested_condition`: 동시성 1–8 각 1회, `max_tokens=512`, greedy, seed 20260819, streaming, `VLLM_LOGGING_LEVEL=DEBUG`+`VLLM_RBLN_METRICS=1`, `RBLN_DEVICES` 미설정, 수준마다 새 server, 실행 순서 `(4,8,2,7,3,1,5,6)`.
- `observed_condition`: 전 요청 status 200, 전 요청 chunk 수 512(동일), 수준마다 `[BUCKET]` 줄이 511개이고 **수준 안에서 `request_nums`가 단일 값으로 일정**했다. patch state는 전 구간 `patched`.
- `condition_reached`: `YES`.

### 관찰 — `[BUCKET]` 사상 (전 사상 커버)

Population: 수준 8개 × 511 decode step = 4,088 step. Source: patch가 emit한 DEBUG 로그.

| `request_nums` | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| 관측 `padded_batch_size` | 1 | 2 | **4** | 4 | **8** | **8** | **8** | 8 |
| 빈도 | 511 | 511 | 511 | 511 | 511 | 511 | 511 | 511 |

**[TASK12](TASK12.md)가 `UNKNOWN`으로 남긴 `6 → 8`, `7 → 8`이 관측됐다.** 사상표 8개 항목이 모두 채워졌고 예측 1이 적중했다.

### 관찰 — 채널별 측정값

Population: 수준별 decode step. Unit: ms. Device scope: `rbln0`–`rbln3`.

| 수준 | bucket | B model p50 | B sampler p50 | B 합 | C median ITL | D mean ITL | C mean ITL | 잔차 (C med − B 합) |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 9.51 | 0.36 | 9.87 | 10.379 | 10.435 | 10.436 | 0.509 |
| 2 | 2 | 10.05 | 0.37 | 10.42 | 10.975 | 11.005 | 11.002 | 0.555 |
| 3 | 4 | 10.36 | 0.47 | 10.83 | 11.482 | 11.548 | 11.548 | 0.652 |
| 4 | 4 | 10.35 | 0.47 | 10.82 | 11.569 | 11.650 | 11.651 | 0.749 |
| 5 | 8 | 12.39 | 0.56 | 12.95 | 13.632 | 13.806 | 13.807 | 0.682 |
| 6 | 8 | 12.40 | 0.56 | 12.96 | 13.696 | 13.827 | 13.829 | 0.736 |
| 7 | 8 | 12.40 | 0.56 | 12.96 | 13.785 | 13.917 | 13.919 | 0.825 |
| 8 | 8 | 12.42 | 0.59 | 13.01 | 13.795 | 13.991 | 13.993 | 0.785 |

ITL raw 표본 수는 수준당 `511 × N`이다 (511 … 4,088).

`prefix_cache_hits` 증분은 전 수준 **0**이었다 (예측 6 적중, prompt 20 token < 129 문턱).

### 채널 대조 게이트: **4개 전부 통과**

| 게이트 | 결과 |
|---|---|
| 1. B mean ≈ C median 자릿수 | 9.5–12.4 vs 10.4–13.8 ms — 동일 자릿수 ✓ |
| 2. A의 `1/(step/s)` ≈ B·C 자릿수 | 정상 상태 rate에서 L1 96 → 10.417, L4 86 → 11.628, L8 72 → 13.889 ms/step. C median 10.379 / 11.569 / 13.795와 동일 자릿수이며 값도 근접 ✓ |
| 3. D ≈ C 자릿수 | server 측 평균과 client 측 평균이 소수 셋째 자리까지 일치(예: 10.435 vs 10.436) ✓ |
| 4. bucket 경계 증가 방향 일치 | B·C·D 모두 b1 < b2 < b4 < b8 ✓ |

게이트 3의 일치는 **채널 C가 client threading에 오염되지 않았음**을 뜻한다. 선등록에서 우려한 confounder가 실측으로 배제됐다.

### 판정 — bootstrap CI (채널 C, resamples 2,000, 95 %)

사전 등록 CI 폭 상한은 0.10이다.

**동치를 요구한 쌍 (같은 bucket 안):**

| 쌍 | n_a | n_b | median_a (ms) | median_b (ms) | ratio | 95 % CI | CI 폭 | 판정 |
|---|---|---|---|---|---|---|---|---|
| 3 vs 4 | 1,533 | 2,044 | 11.482 | 11.569 | 1.0076 | [1.0064, 1.0085] | 0.0021 | **DIFFERENT** |
| 5 vs 6 | 2,555 | 3,066 | 13.632 | 13.696 | 1.0047 | [1.0042, 1.0053] | 0.0012 | **DIFFERENT** |
| 5 vs 7 | 2,555 | 3,577 | 13.632 | 13.785 | 1.0112 | [1.0107, 1.0119] | 0.0012 | **DIFFERENT** |
| 5 vs 8 | 2,555 | 4,088 | 13.632 | 13.795 | 1.0120 | [1.0114, 1.0126] | 0.0012 | **DIFFERENT** |
| 6 vs 7 | 3,066 | 3,577 | 13.696 | 13.785 | 1.0065 | [1.0060, 1.0069] | 0.0009 | **DIFFERENT** |
| 6 vs 8 | 3,066 | 4,088 | 13.696 | 13.795 | 1.0072 | [1.0068, 1.0077] | 0.0009 | **DIFFERENT** |
| 7 vs 8 | 3,577 | 4,088 | 13.785 | 13.795 | 1.0008 | [1.0003, 1.0013] | 0.0010 | **DIFFERENT** |

**7개 전부 CI가 1을 배제했다. H 기각.**

**차이를 요구한 쌍 (bucket 경계):**

| 쌍 | bucket 전이 | ratio | 95 % CI | 판정 |
|---|---|---|---|---|
| 1 vs 2 | 1 → 2 | 1.0574 | [1.0562, 1.0590] | **DIFFERENT** ✓ |
| 2 vs 3 | 2 → 4 | 1.0462 | [1.0452, 1.0468] | **DIFFERENT** ✓ |
| 4 vs 5 | 4 → 8 | 1.1784 | [1.1773, 1.1797] | **DIFFERENT** ✓ |

차이 쌍 3개는 요구대로 `DIFFERENT`다. `INCONCLUSIVE`는 하나도 없었다 — CI 폭이 전부 0.0009–0.0027로 상한 0.10보다 훨씬 좁았다.

**측정 후 CI 폭 상한을 완화하지 않았다.** 동치 쌍이 전부 기각된 것은 검정력이 부족해서가 아니라 **효과가 작지만 실재하고 표본이 커서 검출됐기** 때문이다.

### 파생 산출 — bucket별 model step 시간 상수 (채널 B)

| bucket | 관측 수준 | model p50 (ms) | 같은 bucket 내 범위 |
|---|---|---|---|
| 1 | L1 | 9.51 | — |
| 2 | L2 | 10.05 | — |
| 4 | L3, L4 | 10.36, 10.35 → 평균 **10.355** | **0.01 ms** |
| 8 | L5–L8 | 12.39, 12.40, 12.40, 12.42 → 평균 **12.4025** | **0.03 ms** |

sampler p50도 같은 구조다: b1 0.36, b2 0.37, b4 0.47/0.47, b8 0.56/0.56/0.56/0.59.

### 파생 산출 — 잔차의 actual 의존

`잔차 = C median ITL − (B model p50 + B sampler p50)` 은 model·sampler span **밖의** engine overhead다.

| 수준 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| 잔차 (ms) | 0.509 | 0.555 | 0.652 | 0.749 | 0.682 | 0.736 | 0.825 | 0.785 |

`request_nums`에 대한 최소제곱 직선은 **기울기 약 0.0413 ms/요청, 절편 약 0.501 ms**다. bucket과 무관하게 actual에 대해 단조 증가하는 경향이며, 이것이 같은 bucket 안 차이의 출처로 보인다(해석은 아래 참조).

### 사전 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| 1 | 사상 1→1, 2→2, 3→4, 4→4, 5→8, 6→8, 7→8, 8→8 | ✓ 전건 일치 |
| 2 | bucket 순 단조 증가 b1 < b2 < b4 < b8 | ✓ (9.51 < 10.05 < 10.355 < 12.4025) |
| 3 | 같은 bucket 안 동치 | ✗ **채널 C에서 기각.** 채널 B에서는 범위 ≤ 0.03 ms로 사실상 일정 |
| 4 | B·C·D 같은 자릿수 | ✓ |
| 5 | C median ITL이 10 ms 자릿수 | ✓ (10.4–13.8 ms) |
| 6 | `prefix_cache_hits` 증분 0 | ✓ |
| 7 | device time > host time | **확인 불가.** DECODE METRICS에 host/device/ccl/prepare 줄이 출력되지 않았다 (아래 참조) |

## 핵심 발견

1. **선등록한 H는 채널 C 기준으로 기각된다.** 같은 bucket 안 7개 쌍이 전부 `DIFFERENT`였다. decode step의 end-to-end 비용은 bucket만의 함수가 아니다.
2. **그러나 비용이 두 성분으로 깨끗하게 분해된다.** model 실행 span은 bucket이 결정하고(같은 bucket 내 범위 0.01–0.03 ms), actual 의존은 model·sampler 밖의 engine overhead에 있으며 요청당 약 0.041 ms다.
3. **크기의 위계가 분명하다.** bucket 경계 효과는 +4.6 %~+17.8 %인데 같은 bucket 안 actual 효과는 최대 +1.2 %다. **bucket이 지배 항이고 actual은 보정 항이다.**
4. **`4 → 5` 전이가 가장 크다 (+17.8 %).** bucket 4 → 8 전이이며, 요청 1개가 늘어난 대가로 step 시간이 2.06 ms 증가한다. [TASK12](TASK12.md)의 낭비율 37.5 %(동시성 5)가 시간으로는 이 비용에 해당한다.
5. **sampler도 bucket 결정적이다.** SAMPLER DECODE METRICS의 p50이 bucket별로 0.36 / 0.37 / 0.47 / 0.56–0.59로 계단형이다. padding이 sampler 비용에도 그대로 실린다.
6. **채널 C가 client threading에 오염되지 않았다.** server 측 평균(D)과 client 측 평균(C)이 소수 셋째 자리까지 일치했다. 선등록에서 우려했던 confounder가 실측으로 배제됐다.
7. **채널 A(1초 해상도)도 쓸 만하다.** 정상 상태 step/s의 역수가 채널 C median과 0.5 % 이내로 맞았다. 해상도가 거칠어 판정에는 못 쓰지만 교차 확인에는 충분하다.
8. **`[BUCKET]` 사상표가 완성됐다.** 1–8 전 값이 관측되어 [TASK12](TASK12.md)의 `UNKNOWN`이 닫혔다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(해석)** 발견 2·3을 합치면 비용 모형은 `step_time ≈ f(bucket) + g(actual)` 형태이고, `f`는 계단 함수, `g`는 기울기 0.041 ms/요청의 완만한 선형 항이다. `f`가 지배하므로 **[TASK12](TASK12.md)의 slot 낭비율은 시간 의미를 갖는다** — 다만 "낭비 slot 1개 = 고정 시간"이 아니라 "bucket을 한 단계 올리는 비용"으로 읽어야 한다. bucket 4 → 8은 slot 4개가 늘고 step 시간은 2.05 ms 늘었다.
- **(hypothesis)** 잔차의 actual 의존은 model·sampler span 밖의 per-request 작업(detokenize, output processing, scheduler bookkeeping, HTTP 응답 생성)에서 온다고 본다. 이 작업량은 padding과 무관하게 실제 요청 수에 비례하므로 bucket과 독립적으로 증가한다. 이 귀속은 span 계측으로 확인하지 않았으므로 hypothesis다.
- **(해석)** `7 vs 8`의 ratio가 1.0008로 다른 같은-bucket 쌍보다 훨씬 작다. 잔차 표에서도 L7 0.825 > L8 0.785로 단조성이 깨진다. 1 블록 파일럿이므로 이 비단조성이 실재하는지 잡음인지 구분할 수 없다. **CI가 1을 배제했다는 사실이 효과의 재현성을 보장하지는 않는다** — bootstrap CI는 이 한 번의 표본 안에서의 불확실성만 다룬다.
- **(해석)** bucket 1 → 2가 +5.7 %인데 2 → 4는 +4.6 %로 더 작다. batch가 2배가 될 때마다 일정 비율로 늘지 않는다. 4 → 8에서 +17.8 %로 다시 커진다. 이 비선형성의 원인은 확인하지 않았다.

## 확인되지 않은 사항

- 예측 7(device time > host time)을 **확인하지 못했다.** DECODE METRICS에 `Average host/device/ccl/prepare time` 줄이 출력되지 않았다. `metrics.py`의 `show_stats`는 해당 리스트가 비어 있으면 출력하지 않으므로, `rebel.capture_reports()`가 이 경로에서 report를 채우지 않은 것으로 보이나 확인하지 않았다 (`UNKNOWN`).
- 같은 bucket 안 actual 효과의 **재현성** (`UNKNOWN`). 파일럿 1 블록이므로 블록 반복이 필요하다. `7 vs 8`의 비단조성도 여기 걸린다.
- 잔차의 귀속처 (`UNKNOWN`). span 계측으로 확인하지 않았다.
- bucket 배수당 증가율의 비선형성(+5.7 %, +4.6 %, +17.8 %)의 원인 (`UNKNOWN`).
- 요청들의 생성 길이가 서로 다를 때, 즉 **bucket 전이가 실제로 일어나는 상황**의 step 시간 (`UNKNOWN`, [TASK12](TASK12.md)에서 이월). 이번 격자도 수준 내 `request_nums`를 일정하게 유지했다.
- prompt 길이가 KV 점유에 미치는 영향은 통제하지 않았다. 전 수준 동일 prompt(20 token)였으므로 이번 결론은 그 조건 안에서만 유효하다.
- 채널 B는 요약 통계만 제공해 bootstrap을 적용하지 못했다. bucket 결정성 주장은 **CI 없는 관측**이다 (범위 0.01–0.03 ms).

## 실패 / 무효 시도

- 무효로 판정한 측정은 없다. 8개 수준 전부 status 200, chunk 512, `[BUCKET]` 511줄로 조건이 일치했다.
- 예측 7은 필요한 로그 줄이 출력되지 않아 확인 자체가 불가능했다. 예측을 사후에 바꾸지 않고 미확인으로 기록한다.
- Device·RSD·package·patch 변경은 없었다. 8개 server lifecycle 모두 종료 후 device memory가 `0.0B`로, context가 빈 상태로 복귀했다.

## 연구 원칙에 미치는 영향

- **표본이 크면 작은 효과도 검출된다. "유의미"와 "중요"는 다르다.** 같은 bucket 안 차이는 CI가 1을 배제했지만 크기는 최대 1.2 %로 bucket 효과(최대 17.8 %)의 1/15이다. 판정과 함께 **효과 크기의 위계**를 always 보고한다.
- **동치 판정이 기각됐다고 가설이 무가치한 것은 아니다.** H를 기각하면서 동시에 "무엇이 bucket 결정적이고 무엇이 아닌지"를 분해할 수 있었다. 기각의 내용이 결과다.
- **채널을 여러 개 두면 confounder를 실측으로 배제할 수 있다.** 채널 D가 없었다면 같은 bucket 안 차이를 client threading 탓으로 오해했을 수 있다.
- **판정 채널과 설명 채널을 분리해 기록한다.** 판정은 raw 표본이 있는 채널 C로만 했고, 채널 B는 CI 없는 관측으로 명시했다.
- **1 블록 파일럿의 CI는 재현성이 아니라 그 표본 안의 불확실성만 말한다.** 블록 반복 전에는 효과의 안정성을 주장하지 않는다.
- patched substrate에서의 측정이므로 모든 run의 provenance에 patch state를 남겼다.

## 다음 작업

1. **블록 반복 확장** — 같은 bucket 안 actual 효과와 `7 vs 8` 비단조성의 재현성을 확인한다. `balanced_arm_orders`의 `rounds`를 늘리면 된다.
2. **bucket 전이 상황의 측정** — 요청별 생성 길이를 다르게 해 `request_nums`가 줄어드는 구간을 만든다. [TASK12](TASK12.md)에서 이월된 항목이며 이번에도 미해소다.
3. **잔차 귀속** — model·sampler 밖 overhead가 무엇인지 확인하려면 추가 계측이 필요하다. patch 확대는 별도 승인 대상이다.

사용자 지시 없이 다음 TASK를 자동 시작하지 않는다.

## 재현 정보

- 선등록 commit: `241b7b8084464d1d460c1d9607c9ecca305b4af8`
- **측정 시작 시각: 2026-08-19 19:48:46 KST.** 선등록 commit 시각은 2026-08-19 19:48:25 KST이므로 **선등록이 측정보다 21초 앞선다.**
- 측정 종료 시각: 2026-08-19 20:1x KST (`<RUN>/measurement-end.txt`)
- Base commit (측정 중 HEAD): `241b7b8084464d1d460c1d9607c9ecca305b4af8`, dirty = untracked `.idea/` 및 gitignored `results/`, `models/`
- **Patch state (측정 전 gate): `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`** — `<RUN>/patch-state.txt`
- 수준 실행 순서: `(4, 8, 2, 7, 3, 1, 5, 6)` — `balanced_arm_orders([str(i) for i in range(1,9)], rounds=1, base_seed=20260819, block_id="task13-pilot")`로 결정적으로 재현된다
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)
- Raw artifact: `results/npu/stage2/20260819-194900-decode-cost/`
  - `measurement-start.txt`, `measurement-end.txt`, `patch-state.txt`
  - `server-level{1..8}.log` — `[BUCKET]` 로그와 종료 시 DECODE/SAMPLER METRICS
  - `probe/decode_cost.level{1..8}.json` — ITL raw 표본 전체와 counter 증분
  - `probe-level{1..8}.log`, `level{N}-server-{start,stop}.txt`
  - `bootstrap.json` — CI 판정 전문
  - `rbln-smi-before.txt`, `rbln-smi-final.txt`
- 실행 script: `experiments/npu/stage2/decode_cost_probe.py`, `experiments/npu/analysis/bootstrap_ratio.py`, `experiments/npu/stage1/prompt.txt`
- Isolation launcher: `experiments/npu/launch/run_isolated_python.sh`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(**patched**), `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch 2.11.0+cpu`
- Host: `atom-max8`, device `rbln0`–`rbln3`
