# 선등록 — N/slots sweep 본 측정

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다.

## 연구 질문

agentic tool gap의 bucket utilization 저하와 층 2 재사용률은 oversubscription 비율 **N/slots**의 함수로 어떻게 변하는가?

[TASK19](TASK19.md) 파일럿에서 방향이 N에 따라 뒤집혔다(N=8 ratio 0.872, N=16 ratio 1.009). 이번은 그 의존성을 격자로 측정한다.

## 승인 범위 (사용자 판정, 2026-08-20)

b8 artifact serving 기동·종료(예상 60회 내외, PID 특정 확인), localhost 요청, DEBUG + `VLLM_RBLN_METRICS=1` + `--enable-prompt-tokens-details`, `src/continuum/`·`experiments/npu/` 코드 추가·수정.

범위 밖: 재compile, download, patch 추가·수정, RSD 변경, remote push 자동 수행.

**실행이 길어지면 조합 단위로 중간 저장하고, 한 세션에 못 끝내면 완료 조합까지로 `PARTIAL` 보고한다. 미완 조합을 추정으로 채우지 않는다.**

## Substrate 상태

측정 전 `apply.sh status`가 `patched`(SHA256 `70942d16…`)가 아니면 시작하지 않는다.

## 실험 격자

| 항목 | 값 |
|---|---|
| **N (논리 세션 수)** | **4, 6, 8, 10, 12, 16** → N/slots = 0.5, 0.75, 1.0, 1.25, 1.5, 2.0 (`outer_slot_count = max_num_seqs = 8`) |
| **arm** | AGENTIC / CONVENTIONAL (짝, `zero_gaps()` 파생) |
| **블록** | 전 N에 **3블록**(b0–b2), **N ∈ {8, 16}에 +2블록**(b3–b4) |
| 총 조합 | 6×2×3 + 2×2×2 = **44** |
| 세션 구조 | 2 turn. 첫 segment `uniform:800:1600`, 이후 `fixed:8`, 생성 `uniform:32:256` |
| gap | AGENTIC `uniform:1:5` 초 / CONVENTIONAL 동일 plan에서 gap 제거 |
| plan seed | `base_seed=20260830`, `block_id = n<N>b<B>` (**arm 간 동일**) |
| sampling seed | 20260819 |
| server | 조합마다 fresh. `--enable-prefix-caching --enable-prompt-tokens-details` |
| 환경변수 | `VLLM_LOGGING_LEVEL=DEBUG`, `VLLM_RBLN_METRICS=1` |

세션 구조·길이 분포·gap 분포는 [TASK19](TASK19.md) 재측정과 **동일하게 고정**한다(비교 가능성 유지). **gap 분산 축은 이 TASK가 다루지 않는다.**

### 블록별 arm 실행 순서 (블록 랜덤화)

```python
balanced_arm_orders(["AGENTIC", "CONVENTIONAL"], rounds=5,
                    base_seed=20260830, block_id="task20")
```

| block | 순서 |
|---|---|
| 0 | AGENTIC → CONVENTIONAL |
| 1 | CONVENTIONAL → AGENTIC |
| 2 | AGENTIC → CONVENTIONAL |
| 3 | CONVENTIONAL → AGENTIC |
| 4 | AGENTIC → CONVENTIONAL |

N은 4 → 6 → 8 → 10 → 12 → 16 순서로 돈다.

## 관측치

| # | 관측치 | 정의 | 역할 |
|---|---|---|---|
| **1** | **시간가중 bucket utilization** | `Σ(request_nums) / Σ(padded_batch_size)` over `[BUCKET]` step | **1차 판정치** |
| **2** | 층 2 재사용률 | turn 2 중 `cached_tokens > 0`인 비율 (세션별, [TASK18](TASK18.md) 채널) | N 의존 관측 |
| **3** | **비용 모델 전이 검증** | 아래 | 2차 |
| 4 | 재개 도착 시각열 | turn 2의 `sent_s` 정렬열과 세션별 재사용 성패 | 후속 TASK 해석 지원 |

### 관측치 3의 정의

[TASK16](TASK16.md) descriptor(= [TASK13](TASK13.md) 비용 모델)를 `[BUCKET]` step 열에 대입한다.

```
predicted_busy_s   = Σ_steps  step_time_s(request_nums)
predicted_itl_sum_s = Σ_steps  request_nums × step_time_s(request_nums)
measured_itl_sum_s  = vllm:inter_token_latency_seconds_sum
```

`predicted_itl_sum`과 `measured_itl_sum`은 **같은 양**이다 — 한 decode step에서 running 요청마다 token 1개가 나오고 그 token의 inter-token latency가 그 step 길이이기 때문이다. 두 값의 비를 조합마다 기록하고, **arm 간 차**(predicted Δ vs measured Δ)를 대조한다.

이는 [TASK13](TASK13.md)의 정상 상태 비용 모델이 **전이가 일어나는 workload로 전이되는지**를 보는 검증이다.

## 불변식 (fail-loud, 위반 조합은 `INVALID`로 격리)

| # | 불변식 |
|---|---|
| **P1** | 같은 (N, block)의 두 arm plan이 `gap_after_s`를 제외한 전 항목에서 동일 |
| I1 | 모든 `[BUCKET]` 줄이 파싱된다 |
| I2 | `request_nums ≤ padded_batch_size` |
| I3 | `padded_batch_size ∈ {1,2,4,8}` |
| I4 | 관측 사상 = `bucket_for(request_nums)` |
| I5 | `Σ(request_nums)` = `Σ_requests (completion_tokens − 1)` |

`INVALID` 조합은 판정에서 제외하고 그 사실과 개수를 보고한다. **다른 조합으로 대체하거나 추정으로 채우지 않는다.**

## 판정 (선등록)

블록 수가 작으므로 **pooled 점추정 + 전 블록 방향 일치**를 함께 요구한다.

- 블록 b의 ratio: `util(AGENTIC, N, b) / util(CONVENTIONAL, N, b)`
- pooled ratio: `Σ_b Σ(request_nums)_A / Σ_b Σ(padded)_A` ÷ 같은 것을 C로 — 즉 **블록을 합쳐 계산한 utilization의 비**(블록 크기 가중)

**사전 등록 동치 밴드: [0.97, 1.03]**

| N별 판정 | 조건 |
|---|---|
| **저하 존재** | 그 N의 전 블록 ratio < 1 **이고** pooled ratio < 0.97 |
| **저하 없음(동치)** | 그 N의 전 블록 ratio가 [0.97, 1.03] 안 |
| **INCONCLUSIVE** | 그 외 |

**`INCONCLUSIVE`가 나오면 블록을 이 TASK에서 추가하지 않는다.** 새 TASK로 넘긴다.

밴드 [0.97, 1.03]의 근거: [TASK19](TASK19.md)에서 관측된 효과는 N=8에서 12.8 %, N=16에서 0.9 %였다. 3 % 밴드는 관측된 큰 효과를 검출하면서 1 % 수준의 흔들림을 동치로 처리한다. **이 값은 측정 전에 고정하며 사후에 넓히지 않는다.**

관측치 2·3·4는 판정 대상이 아니라 **기술 대상**이다.

## 사전 예측 (판정 기준 아님)

| # | 예측 | 근거 |
|---|---|---|
| a | utilization ratio가 N ≤ 8에서 1 미만, N ≥ 12에서 동치 밴드 안 | [TASK19](TASK19.md) 두 점 |
| b | 재사용률이 N 증가에 단조 감소, N ≥ 12에서 0 부근 | outer slot 8개를 N 세션이 나눈다 |
| c | 저하 최대점이 N = 8 근방 | N < 8이면 batch가 원래 얇아 gap의 추가 효과가 작고, N > 8이면 대기 큐가 흡수한다 |
| d | `predicted_itl_sum / measured_itl_sum`이 전 조합에서 같은 자릿수 | 같은 양의 두 산출 |
| e | AGENTIC의 재개 도착이 CONVENTIONAL보다 흩어진다 | gap 분산 |

예측 c는 이번 격자가 처음 검증하는 항목이며 확신도가 낮다.

## 필수 측정 항목

조합별: per-request JSONL, plan summary(+`total_gap_s`), `[BUCKET]`·`[PFX]` 로그 전문, `/metrics` 덤프, utilization JSON(불변식·예측 포함), 완료 표식. 전체: patch state, `rbln-smi`(첫 기동 전·마지막 종료 후), provenance.

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-nslots-sweep`

1. `apply.sh status` → `patched` 확인
2. block 0..4, N 4→16 순서로, 블록별 arm 순서표대로 `run_sweep.sh <RUN> <ARM> <N> <BLOCK> <none|zero>` 실행
   - AGENTIC은 `none`(뽑힌 gap 유지), CONVENTIONAL은 `zero`
   - `run_sweep.sh`는 조합 완료 시 `done.<TAG>` 표식을 남기고, 이미 있으면 건너뛴다 → 중단·재개 가능
3. 조합마다 `utilization.py --cost-model` 실행
4. P1을 (N, block)마다 확인
5. N별 판정표 작성

## 관련 문서

- [TASK19](TASK19.md) — 파일럿, 격자 제안의 출처
- [TASK18](TASK18.md) — per-request 귀속 채널
- [TASK16](TASK16.md) — substrate descriptor (관측치 3의 모델)
- [TASK13](TASK13.md) — 비용 모델
