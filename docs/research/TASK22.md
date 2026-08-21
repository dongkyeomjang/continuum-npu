# TASK22 — prefill 배타 실행의 직접 검증과 비용 모델 v2

## 상태

DONE

## 판정

| 판정 | 결과 |
|---|---|
| **1. 스파이크 존재** | **`PARTIAL`** — 주입 9 run × 4 bystander **36/36**이 문턱을 넘었으나, **대조 3 run에서도 문턱 초과가 나타나** 선등록 규칙에 따라 낮췄다 |
| **2. 동시성** | **동시 확인.** 9/9 run에서 K=4 스파이크 구간이 공통 교집합을 갖는다 |
| **3. 비례성** | **비례 확인.** 500 < 2000 < 6000 단조 증가, `스파이크/prefill 시간` = 1.140 / 1.036 / 1.012로 전부 밴드 [0.5, 2.0] 안 |

불변식 V1–V4 **12/12 통과**, `INVALID` 0건.

판정 3이 "비례 확인"이므로 **비용 모델 v2**를 세웠고, 사후 대조에서 [TASK20](TASK20.md)의 편향을 **87–120 % 설명**했다.

## 날짜

2026-08-21

## 목적

resume가 유발하는 prefill이 실행 중인 다른 세션들의 decode를 정지시키는지, 정지 시간이 prefill 계산량에 어떻게 비례하는지 직접 측정한다.

## 배경

[TASK20](TASK20.md)이 `predicted/measured` ITL 편향(N에 따라 0.86 → 0.57)의 유력한 기전으로 prefill 배타 실행을 제시했으나 직접 관측하지 않았다. 근거는 `optimum_scheduler.py:300-304`의 주석이다.

> "If a request is in the prefill phase, it is given priority and processed exclusively (only one at a time)."

선등록 문서: [PREFILL_TAX_PREREG.md](PREFILL_TAX_PREREG.md)

## 시작 상태

- 선등록 commit: `ba6ee2bdee53266e339c7f8b4cb73e7f4f96f7a5`
- **Substrate: patched** (SHA256 `70942d16…`). 측정 전 gate 통과
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)

## 수행 내용

1. 선등록 문서·probe·분석기를 **측정 전에** commit했다 (`ba6ee2b`).
2. bystander 4개가 streaming으로 계속 생성하는 중에 통제된 길이의 유일 prompt를 1회 주입하는 12 run(수준 4 × 반복 3)을 fresh server로 실행했다.
3. 불변식 V1–V4를 검사하고 판정 3개를 산출했다.
4. 판정 3이 통과해 비용 모델 v2를 세우고 descriptor에 반영했다.
5. [TASK20](TASK20.md) 편향에 대한 **사후** 대조를 수행했다.

재compile, download, patch 변경, RSD 변경은 없었다.

## 결과

### 조건 분리

- `requested_condition`: bystander 4개(prompt 300 token 유일, `max_tokens=800`, streaming), warm-up 3.0 s 후 주입 1회(prompt 0/500/2000/6000 token 유일, `max_tokens=1`, non-streaming), 수준마다 3반복, run마다 fresh server, plan seed 20260840, sampling seed 20260819.
- `observed_condition`: 전 run에서 bystander 4개가 status 200이고 arrival ≥ 2. 주입의 `observed_prompt_tokens`가 요청값과 정확히 일치하고 **`cached_tokens = 0`**. 주입 창의 `request_prefill_time_seconds_count` 증분이 정확히 **1**. patch state `patched`.
- `condition_reached`: `YES`.

### 관측 — 전 12 run

| tag | 주입 token | 실계산량 | prefill (s) | baseline (ms) | 중앙 스파이크 (ms) | ×baseline | 존재 | 동시 |
|---|---|---|---|---|---|---|---|---|
| inj0.r0–r2 | 0 | — | — | 11.75–12.00 | — | — | — | — |
| inj500.r0 | 500 | 500 | 0.0884 | 11.84 | 100.58 | 8.49 | ✓ | ✓ |
| inj500.r1 | 500 | 500 | 0.0885 | 11.76 | 100.87 | 8.58 | ✓ | ✓ |
| inj500.r2 | 500 | 500 | 0.0886 | 11.76 | 100.89 | 8.58 | ✓ | ✓ |
| inj2000.r0 | 2000 | 2000 | 0.3596 | 11.77 | 372.57 | 31.66 | ✓ | ✓ |
| inj2000.r1 | 2000 | 2000 | 0.3596 | 11.73 | 374.00 | 31.90 | ✓ | ✓ |
| inj2000.r2 | 2000 | 2000 | 0.3590 | 11.62 | 371.36 | 31.96 | ✓ | ✓ |
| inj6000.r0 | 6000 | 6000 | 1.1758 | 11.86 | 1190.04 | 100.37 | ✓ | ✓ |
| inj6000.r1 | 6000 | 6000 | 1.1772 | 12.18 | 1191.68 | 97.81 | ✓ | ✓ |
| inj6000.r2 | 6000 | 6000 | 1.1802 | 12.98 | 1194.77 | 92.02 | ✓ | ✓ |

baseline 11.6–13.0 ms는 예측 e(bucket 4의 약 11.5 ms)와 일치한다.

### 판정 1 — 스파이크 존재: `PARTIAL`

주입 run에서는 **36/36**(9 run × 4 bystander)이 문턱 5.0을 넘었다(8.49–100.37).

그러나 **대조 run에서도 문턱 초과가 나타났다.** 선등록이 "대조에서 문턱을 넘으면 판정 1을 `PARTIAL`로 낮춘다"고 정해 두었으므로 그대로 적용한다.

| 대조 run | bystander별 최대 간격 (ms) | ×baseline |
|---|---|---|
| inj0.r0 | 148.3 / 214.6 / 81.0 / 16.7 | 12.59 / 18.22 / 6.88 / 1.42 |
| inj0.r1 | 217.5 / 80.7 / 17.6 / 148.5 | 18.50 / 6.87 / 1.49 / 12.64 |
| inj0.r2 | 217.1 / 149.7 / 18.7 / 81.8 | 18.10 / 12.47 / 1.56 / 6.82 |

**다만 발생 시각이 주입 창과 완전히 분리된다.**

| | 대조의 최대 간격 | 주입 스파이크 |
|---|---|---|
| 시각 | **t < 0.33 s** (2건은 t ≈ 8.2–8.4 s의 작은 값) | **t ≈ 3.02–4.22 s** (주입 창과 일치) |

대조의 큰 간격은 **bystander 자신들의 시작 prefill이 직렬화된 결과**다. 세 값이 217 / 148 / 81 / 17 ms로 계단을 이루면서 **끝나는 시각이 0.308 / 0.321 / 0.324 s로 동일**하다 — bystander i가 뒤이은 bystander들의 prefill을 차례로 기다린 서명이다. 300 token prompt는 `ceil(300/128) = 3` chunk이고 chunk당 약 22 ms이므로 약 66 ms씩 계단이 생긴다.

즉 **대조의 문턱 초과는 교란이 아니라 같은 기전의 독립 관측**이다. 그러나 선등록이 "주입 때문이라는 귀속이 약해진다"는 이유로 `PARTIAL`을 정했으므로 **기준을 사후에 바꾸지 않는다.**

### 판정 2 — 동시성: 확인

9/9 run에서 4개 스파이크 구간이 공통 교집합을 갖는다. 실제 시각은 **1 ms 이내로 겹친다**.

예 (inj6000.r0, 주입 창 [3.011, 4.212] s):

```
bys0: 1190.1 ms @ [3.030, 4.220]
bys1: 1190.0 ms @ [3.030, 4.220]
bys2: 1190.1 ms @ [3.030, 4.220]
bys3: 1189.8 ms @ [3.030, 4.220]
```

**네 세션이 같은 순간에 같은 길이만큼 멈춘다.**

### 판정 3 — 비례성: 확인

| 수준 | 실계산량 | 중앙 prefill (s) | 중앙 스파이크 (s) | 스파이크/prefill |
|---|---|---|---|---|
| 500 | 500 | 0.0885 | 0.1009 | **1.140** |
| 2000 | 2000 | 0.3596 | 0.3726 | **1.036** |
| 6000 | 6000 | 1.1772 | 1.1917 | **1.012** |

단조 증가하고 세 비가 모두 밴드 [0.5, 2.0] 안이다. 비가 1보다 약간 큰 것은 스파이크가 prefill 시간에 더해 그 step의 decode 시간을 포함하기 때문으로 보이며, 작은 주입일수록 그 상대 비중이 크다(1.140 → 1.012).

### 비용 모델 v2

prefill 시간은 **chunk 단위 + 길이 drift** 로 잘 맞는다. TASK22 관측점 3개와 [TASK15](TASK15.md)의 2,008 token 점으로 적합했다.

```
prefill_s(n) = ceil(n / 128) × (0.021206 + 6.399e-07 × n)
```

| n | 관측 (s) | 모형 (s) | 잔차 |
|---|---|---|---|
| 500 | 0.0885 | 0.0861 | −0.0024 |
| 2000 | 0.3596 | 0.3598 | +0.0002 |
| 2008 | 0.3592 | 0.3599 | +0.0007 |
| 6000 | 1.1772 | 1.1771 | −0.0001 |

**최대 잔차 2.4 ms** (500 token에서). chunk당 시간이 22.13 → 25.05 ms로 커지는 것이 drift 항의 근거다.

descriptor에 `PrefillCostModel`을 추가했다. `stall_s(computed_tokens, concurrent_decoders)`가 **다른 세션들이 잃는 총 decode 시간**을 준다 — 예: 2,000 token 주입 × 4 decoder = **1.439 s**.

`prefill_cost_model` field는 `None`을 허용하되 provenance 규칙은 유지한다. `None`은 "prefill이 공짜"가 아니라 **"이 substrate에서 측정하지 않았다"** 는 뜻임을 docstring에 명시했다.

### 사후 대조 — [TASK20](TASK20.md) 편향의 설명력

**이는 사후 분석이며 이 TASK의 판정 대상이 아니다.**

근사: `predicted_itl_sum_v2 = v1 + (run의 prefill 시간 합) × (평균 running)`. prefill 시간 합은 각 run의 `/metrics` 덤프에서, 평균 running은 `Σ(request_nums)/decode_steps`에서 얻었다.

| N | arm | v1 비 | **v2 비** | 설명분 |
|---|---|---|---|---|
| 4 | AGENTIC | 0.8553 | **0.9897** | 92.9 % |
| 4 | CONVENTIONAL | 0.8118 | **1.0387** | 120.5 % |
| 6 | AGENTIC | 0.7911 | **0.9730** | 87.1 % |
| 6 | CONVENTIONAL | 0.7839 | **1.0163** | 107.5 % |
| 8 | AGENTIC | 0.7223 | **0.9909** | 96.7 % |
| 8 | CONVENTIONAL | 0.6499 | **0.9946** | 98.5 % |
| 10 | AGENTIC | 0.6610 | **1.0059** | 101.7 % |
| 10 | CONVENTIONAL | 0.5931 | **0.9975** | 99.4 % |
| 12 | AGENTIC | 0.5986 | **1.0215** | 105.3 % |
| 12 | CONVENTIONAL | 0.5698 | **0.9794** | 95.2 % |
| 16 | AGENTIC | 0.5693 | **0.9785** | 95.0 % |
| 16 | CONVENTIONAL | 0.5645 | **0.9969** | 99.3 % |

v1이 0.565–0.855로 흩어져 있고 N에 단조 의존하던 것이 **v2에서 0.973–1.039로 모이고 N 의존이 사라진다.**

**설명되지 않는 잔차**: v2 비가 1에서 ±3.9 % 벗어난다. 120.5 %처럼 100 %를 넘는 칸은 **과대 보정**이며, 근사가 "모든 prefill 동안 평균 running 수만큼 정지"를 가정한 탓으로 보인다. 실제로는 prefill 시점의 running 수가 평균과 다르다. **이 잔차의 출처는 `UNKNOWN`이다.**

### 사전 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| a | 주입 시점에 전 bystander 동시 스파이크 | ✓ 9/9, 1 ms 이내 |
| b | 스파이크 ≈ prefill 시간, 계산량에 단조 증가 | ✓ 비 1.012–1.140 |
| c | 대조 구간엔 스파이크 없음 | **✗** startup prefill 직렬화로 문턱 초과 발생 |
| d | 주입의 `cached_tokens = 0` | ✓ 9/9 |
| e | baseline 약 11.5 ms | ✓ 11.6–13.0 ms |
| f | 6000 token prefill이 약 1.1 s | ✓ 1.176–1.180 s |

6개 중 5개 적중. 빗나간 c가 판정 1을 `PARTIAL`로 만들었다.

## 핵심 발견 (층 태그)

1. **`stack`** — **prefill이 실행 중인 모든 세션의 decode를 정확히 그 길이만큼 정지시킨다.** 4개 bystander의 스파이크가 1 ms 이내로 겹치고 스파이크/prefill 비가 1.01–1.14다. `optimum_scheduler.py`의 주석이 말한 배타 실행이 **시간 단위로 관측**됐다.
2. **`stack`** — **정지 시간은 prefill 계산량으로 예측된다.** `ceil(n/128) × (0.0212 + 6.4e-7 n)`이 500–6000 token에서 최대 잔차 2.4 ms로 맞는다. chunk당 시간이 22.1 → 25.1 ms로 커지는 drift가 있다.
3. **`stack`** — **[TASK20](TASK20.md)의 비용 모델 편향이 prefill 항으로 87–120 % 설명된다.** v1 비 0.565–0.855(N 의존)가 v2에서 0.973–1.039(N 의존 소멸)로 모인다. [TASK20](TASK20.md)이 hypothesis로 남긴 기전이 정량적으로 확인됐다.
4. **`class`** — **prefill 비용은 요청 자신의 지연이 아니라 시스템 비용이다.** 배타 실행 substrate에서 한 요청의 prefill은 동시 decoder 수만큼 배증된다(2,000 token × 4 decoder = 1.44 s). 같은 스케줄링을 쓰는 어느 구현에서나 성립하며, 이는 **긴 prefix의 재계산 비용이 세션 하나가 아니라 전체에 부과된다**는 뜻이다.
5. **`stack`** — **대조 구간이 같은 기전을 독립적으로 보여줬다.** bystander 4개의 시작 prefill이 217/148/81/17 ms 계단을 만들고 **끝나는 시각이 동일**했다. 설계상 "아무 일도 없어야 할" 구간이 오히려 기전의 두 번째 증거가 됐다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(해석)** 발견 4를 [TASK14](TASK14.md)·[TASK15](TASK15.md)와 합치면 prefix cache eviction의 비용이 다시 보인다. outer slot이 밀려 resume가 1,920 token을 재계산하면([TASK15](TASK15.md)), 그 0.36 s는 재계산한 세션만의 손실이 아니라 **그때 돌던 모든 세션의 손실**이다. cache 실패의 시스템 비용은 재계산 시간 × 동시 decoder 수다.
- **(hypothesis)** 스파이크/prefill 비가 1보다 큰 것(1.140 → 1.012)은 스파이크가 prefill에 더해 그 step의 decode 시간(약 11.5 ms)을 포함하기 때문으로 보인다. 500 token에서 11.5/88.5 = 13 %로 관측된 초과 14 %와 가깝다. 다만 분해해 확인하지는 않았다.
- **(해석)** 사후 대조에서 100 %를 넘는 칸(최대 120.5 %)은 근사의 과대 보정이다. "모든 prefill 동안 평균 running 수만큼 정지"라는 가정이 실제와 다르며, 정확히 하려면 prefill 시점의 running 수를 알아야 한다. `[BUCKET]` 로그와 prefill 시각을 정렬하면 가능하나 로그 timestamp가 1초 해상도라 어렵다.
- **(해석)** drift 항(chunk당 22.1 → 25.1 ms)은 chunk 내 attention이 앞선 context 길이에 따라 커지는 것과 일관된다. 다만 4개 관측점으로 2차 항을 구분하지는 못했다.

## 확인되지 않은 사항

- 사후 대조의 잔차(v2 비가 1에서 ±3.9 %) 출처 (`UNKNOWN`). 근사의 과대·과소 보정으로 보이나 분해하지 않았다.
- 스파이크가 prefill 시간을 초과하는 몫의 정확한 분해 (`UNKNOWN`).
- prefill 시간이 6,000 token 너머에서도 이 모형을 따르는지 (`UNKNOWN`). `max_seq_len`이 8,192이므로 관측 가능한 범위는 좁다.
- bystander 수가 4가 아닐 때 스파이크 크기가 달라지는지 (`UNKNOWN`). K=4만 측정했다.
- 동시에 여러 요청이 prefill을 기다릴 때의 큐잉 거동 (`UNKNOWN`). 주입은 항상 1개였다.
- prefill 중 KV 할당·eviction이 정지 시간에 기여하는지 (`UNKNOWN`).

## 실패 / 무효 시도

1. **예측 c(대조에 스파이크 없음)가 빗나갔고 그 결과 판정 1이 `PARTIAL`이 됐다.** 원인은 bystander들의 시작 prefill이 서로를 정지시킨 것이며, 설계 시 warm-up 구간에도 같은 기전이 작동한다는 점을 고려하지 못했다. **선등록 기준을 사후에 바꾸지 않았다.** 개선안은 대조를 "bystander를 순차로 띄워 startup prefill을 분리"하는 것이나 이번에 하지 않았다.
2. `INVALID` run은 **0건**이다. V1–V4를 12/12가 통과했다.
3. Device·RSD·package·patch 변경 없음. server lifecycle 12회, 전부 종료 후 device memory `0.0B` 복귀.

## 연구 원칙에 미치는 영향

- **대조 구간도 설계해야 한다.** "주입만 안 하면 아무 일 없다"는 가정이 틀렸다. 대조가 무엇을 통제하는지 명시하고, 통제되지 않는 기전이 대조에도 있는지 미리 따진다.
- **기준을 낮추는 규칙을 미리 써 두면 실제로 발동한다.** 판정 1의 `PARTIAL`은 사후 재량이 아니라 선등록의 집행이다.
- **시스템 비용과 개별 지연을 구분한다.** prefill은 요청 자신의 지연으로 보면 0.36 s지만 시스템 비용으로는 1.44 s다.
- **모델을 고칠 때는 고친 뒤의 잔차를 함께 보고한다.** 87–120 % 설명이라는 말은 100 %를 넘는 칸이 있다는 뜻이며, 그것도 결과다.

## 다음 작업

1. 사후 대조의 잔차를 줄이려면 prefill 시점의 running 수가 필요하다. `[BUCKET]` 로그와 prefill 시각의 정렬 방법을 설계해야 한다.
2. bystander 수 K를 바꿔 `stall_s`의 선형성(정지 × 동시 decoder 수)을 직접 검증한다.
3. 대조 설계 개선 — bystander를 순차 기동해 startup prefill을 분리한다.

사용자 지시 없이 다음 TASK를 자동 시작하지 않는다.

## 재현 정보

- 선등록 commit: `ba6ee2bdee53266e339c7f8b4cb73e7f4f96f7a5` (2026-08-21 22:00:47 KST)
- **측정 시작 시각: 2026-08-21 22:01:09 KST** (선등록보다 22초 뒤)
- 측정 종료 시각: `<RUN>/measurement-end.txt`
- Base commit (측정 중 HEAD): `ba6ee2bdee53266e339c7f8b4cb73e7f4f96f7a5`
- **Patch state: `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`**
- plan seed: `base_seed=20260840`, 내용 seed `derive_block_seed(20260840, "inj<L>.<rep>/<role>")`
- Raw artifact: `results/npu/stage2/20260821-220100-prefill-tax/`
  - `measurement-{start,end}.txt`, `patch-state.txt`, `ptax.log`, `done.<TAG>` 12개
  - `server-inj<L>.<rep>.log`, `probe/prefill_tax.inj<L>.<rep>.json`, `metrics-inj<L>.<rep>.prom`
  - `prefill_tax_result.json`, `rbln-smi-{before,final}.txt`
- 실행 script: `experiments/npu/stage2/prefill_tax_probe.py`, `experiments/npu/analysis/prefill_tax.py`
- 비용 모델 v2: `src/continuum/substrate/descriptor.py`의 `PrefillCostModel`, 인스턴스는 `experiments/npu/substrate/rbln_ca25_vllm_rbln_0111.py`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(**patched**), `optimum-rbln 0.11.1`, `torch 2.11.0+cpu`
- Host: `atom-max8`, device `rbln0`–`rbln3`
