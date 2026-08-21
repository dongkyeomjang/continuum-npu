# 선등록 — prefill 배타 실행의 직접 검증과 비용 모델 v2

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다.

## 연구 질문과 가설

**RQ**: resume가 유발하는 prefill이 실행 중인 다른 세션들의 decode를 정지시키는가? 정지 시간은 prefill 계산량에 어떻게 비례하는가?

**H**: 정지시킨다. `optimum_scheduler.py:300-304`가 명시한다.

> "If a request is in the prefill phase, it is given priority and processed exclusively (only one at a time)."

[TASK20](TASK20.md)은 이 배타 실행을 `predicted/measured` ITL 편향(N에 따라 0.86 → 0.57)의 **유력한 기전**으로 제시했으나 직접 관측하지 않았다. 이번에 직접 잰다.

## 승인 범위 (사용자 판정, 2026-08-21)

serving 기동·종료(예상 40회 내외), localhost 요청, 기존 관측 스택 전부, `src/continuum/`·`experiments/npu/` 코드 추가·수정.

범위 밖: download, patch 추가·수정, RSD 변경, remote push 자동 수행. (재compile은 이 TASK 범위 밖이며 후속 작업에서만 쓴다.)

## Substrate 상태

측정 전 `apply.sh status`가 `patched`(SHA256 `70942d16…`)가 아니면 시작하지 않는다.

## 관측 채널 선정 (측정 전)

1차 채널로 **bystander의 streaming token 도착 간격 시계열**을 쓴다.

- streaming 가용성은 [TASK09](TASK09.md)에서 확인됐다 (`stream:true`, content chunk 32개, 첫 chunk 0.031 s).
- [TASK20](TASK20.md)이 지적한 non-streaming 한계(client 측 raw ITL 표본 없음)를 이것으로 해소한다.
- **대체 채널이 필요한 경우**(streaming이 실패하거나 chunk가 token 단위가 아닌 경우) `[BUCKET]` step 간격을 쓴다. 다만 로그 timestamp가 1초 해상도([TASK13](TASK13.md))라 **step 간격은 얻을 수 없고 초당 step 수만 얻는다** — 그 경우 판정을 `PARTIAL`로 낮추고 사실을 기록한다.

주입 요청의 prefill 시간은 `vllm:request_prefill_time_seconds` 증분으로 잰다. **이 창에서 완료되는 요청은 주입 요청 하나뿐**이므로([TASK17](TASK17.md)의 동시성 오염 문제를 피한다) 증분이 그 요청에 귀속된다. 그 조건을 `_count` 증분 = 1로 **검사**하고, 아니면 `prefill_time_s`를 `null`로 남긴다.

주입 요청의 실제 계산량은 `usage.prompt_tokens − usage.prompt_tokens_details.cached_tokens`로 얻는다 ([TASK18](TASK18.md) 채널).

## 실험 설계

| 항목 | 값 |
|---|---|
| bystander 수 K | **4** |
| bystander prompt | 300 token (세션마다 유일) |
| bystander `max_tokens` | **800** (약 9 초 decode — 주입 창을 충분히 덮는다) |
| bystander 전송 | **streaming** |
| warm-up | **3.0 초** 후 주입 |
| 주입 prompt | **0(대조) / 500 / 2000 / 6000** token (유일 내용, 매 반복 다름) |
| 주입 `max_tokens` | **1** (prefill 직후 종료 → 증분이 그 요청에 귀속) |
| 반복 | 수준마다 **3회** (대조 포함 총 12 run) |
| server | run마다 **fresh** |
| plan seed | `base_seed=20260840`, 내용 seed는 `derive_block_seed(20260840, "inj<L>.<rep>/<role>")` |
| sampling seed | 20260819 |
| Model | `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음) |
| server flag | `--enable-prefix-caching --enable-prompt-tokens-details` |
| 환경변수 | `VLLM_LOGGING_LEVEL=DEBUG`, `VLLM_RBLN_METRICS=1` |

주입 prompt는 세션마다·반복마다 유일하므로 **`cached_tokens = 0`이어야 하고**, 실제로 그런지 확인한다(requested/observed 분리).

## 관측치

| # | 관측치 | 정의 |
|---|---|---|
| 1 | bystander 도착 간격 | 연속 chunk 도착 시각 차. baseline = 주입 창 **밖** 간격의 중앙값 |
| 2 | 스파이크 | 주입 창(`sent_s`–`done_s`)과 **겹치는** 간격 중 최대값 |
| 3 | 주입 prefill 시간 | `request_prefill_time_seconds` 증분 (`_count` 증분 = 1일 때만 유효) |
| 4 | 주입 실계산량 | `prompt_tokens − cached_tokens` |

## 판정 (측정 전 고정)

세 질문을 **각각** 판정한다.

### 판정 1 — 스파이크 존재

**사전 등록 문턱: 스파이크 / baseline ≥ 5.0**

| 판정 | 조건 |
|---|---|
| 존재 | 주입이 있는 9 run **전부**에서, K=4 bystander **전부**가 문턱을 넘는다 |
| 부분 | 일부 run·bystander만 넘는다 (수를 기록) |
| 없음 | 어느 run에서도 넘지 않는다 |

문턱 5.0의 근거: baseline은 bucket 4의 step 시간 약 11.5 ms([TASK13](TASK13.md))로 예상되고, 가장 짧은 주입(500 token)의 prefill은 [TASK15](TASK15.md)의 2,008 token → 0.359 s에서 선형 외삽하면 약 0.09 s = 약 8× baseline이다. 5.0은 그보다 낮게 잡아 가장 짧은 수준도 검출되게 한다.

### 판정 2 — 동시성

각 bystander의 스파이크 구간 `[start, end]`이 **서로 전부 겹치면** 동시로 본다 (`max(start) < min(end)`).

| 판정 | 조건 |
|---|---|
| 동시 | 주입이 있는 9 run 전부에서 K개 구간이 공통 교집합을 갖는다 |
| 부분 | 일부 run만 |
| 비동시 | 어느 run에서도 겹치지 않는다 |

### 판정 3 — 비례성

주입 수준 3개의 **중앙 스파이크 크기**가 실계산량에 **단조 증가**해야 한다.

| 판정 | 조건 |
|---|---|
| 비례 확인 | 500 < 2000 < 6000 순으로 중앙 스파이크가 단조 증가하고, 각 수준에서 `중앙 스파이크 / 주입 prefill 시간`이 **[0.5, 2.0]** 안 |
| 단조만 확인 | 단조 증가하나 비가 밴드 밖 |
| 미확인 | 단조가 깨짐 |

밴드 [0.5, 2.0]은 **자릿수 일치**를 요구하는 느슨한 기준이다. 스파이크는 client 측 관측이고 prefill 시간은 server 측 계측이라 정확한 일치를 기대하지 않는다. **사후에 넓히지 않는다.**

### 대조 구간

주입이 없는 3 run에서 최대 간격 / baseline이 **문턱 5.0 미만**이어야 한다. 넘으면 스파이크가 주입 때문이라는 귀속이 약해지므로 그 사실을 기록하고 판정 1을 `PARTIAL`로 낮춘다.

## 비용 모델 v2 (판정 3이 "비례 확인"일 때만)

descriptor에 **prefill 직렬화 항**을 추가한다.

```
decode 진행 시간 = Σ_steps step_time_s(request_nums)          (v1, TASK13)
                 + Σ_prefill  prefill_time_s(computed_tokens)  (v2 신규)
```

`prefill_time_s`는 이번 측정의 실계산량–prefill 시간 관계로 세운다 (관측점 3개 + [TASK15](TASK15.md)의 2,008 token 점).

그 뒤 [TASK20](TASK20.md)의 `predicted/measured` 편향(0.57–0.86)이 v2로 **얼마나 설명되는지 사후 대조**한다. 이는 **사후 분석이며 이 TASK의 판정 대상이 아니다.** 설명되지 않는 잔차는 `UNKNOWN`으로 정직하게 남긴다.

## 사전 예측 (판정 기준 아님)

| # | 예측 | 근거 |
|---|---|---|
| a | 주입 시점에 전 bystander의 도착 간격에 동시 스파이크 | 배타 실행 |
| b | 스파이크 크기 ≈ prefill 시간, 실계산량에 단조 증가 | 배타 실행 |
| c | 대조 구간엔 스파이크 없음 | 주입이 없으므로 |
| d | 주입의 `cached_tokens = 0` | 유일 prompt |
| e | baseline이 약 11.5 ms | bucket 4 step 시간 ([TASK13](TASK13.md)) |
| f | 6000 token 주입의 prefill이 약 1.1 s | [TASK15](TASK15.md) 2,008 → 0.359 s의 선형 외삽 |

예측 f는 prefill 시간이 token 수에 선형이라는 가정에 기대며 확신도가 낮다.

## 불변식 (fail-loud)

| # | 불변식 |
|---|---|
| V1 | bystander가 K개 전부 status 200이고 `arrival_count ≥ 2` |
| V2 | 주입의 `cached_tokens = 0` |
| V3 | 주입 창에서 `request_prefill_time_seconds_count` 증분 = 1 |
| V4 | 주입의 `observed_prompt_tokens`가 요청값과 일치 |

위반 run은 `INVALID`로 격리하고 판정에서 제외하며 개수를 보고한다.

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-prefill-tax`

12 run(수준 4개 × 3반복) 각각: `apply.sh status` 확인 → server 기동 → `/health` 대기 → probe 실행 → `/metrics` 덤프 → PID 특정 후 `SIGTERM` → 종료 확인. background + 완료 표식으로 실행한다 ([TASK20](TASK20.md) 교훈).

```bash
env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage2/prefill_tax_probe.py \
  --base-url http://127.0.0.1:8000 \
  --tokenizer-dir <artifact> \
  --bystanders 4 --bystander-prompt-tokens 300 --bystander-max-tokens 800 \
  --inject-prompt-tokens <0|500|2000|6000> --warmup-s 3.0 \
  --base-seed 20260840 --rep r<0|1|2> --sampling-seed 20260819 \
  --output-dir <절대경로>/<RUN>/probe
```

판정: `experiments/npu/analysis/prefill_tax.py --spike-factor 5.0`

## 관련 문서

- [TASK20](TASK20.md) — 비용 모델 전이 실패와 기전 가설의 출처
- [TASK13](TASK13.md) — v1 비용 모델, baseline step 시간
- [TASK15](TASK15.md) — prefill 시간 관측점 (2,008 token → 0.359 s)
- [TASK18](TASK18.md) — `cached_tokens` per-request 채널
- [TASK09](TASK09.md) — streaming 가용성
