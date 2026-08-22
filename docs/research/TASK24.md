# TASK24 — step 수준 시뮬레이터 구축과 in-sample 보정

## 상태

DONE

## 판정

기존 실측 80조합(TASK19·[TASK20](TASK20.md)·[TASK23](TASK23.md) 2a·2b)을 **자유 파라미터를 맞추지 않고** 재현했다.

| 재현 대상 | 결과 |
|---|---|
| utilization | 중앙 오차 `+0.0000`, 평균절대 **0.0066**, 최대절대 0.0495 |
| decode step 수 | 중앙 상대오차 `+0.0000`, 평균절대 1.8 %, 최대 12.4 % |
| 층 2 재사용 hit/miss | **608/654 = 93.0 %** 일치. hit인 경우 **token 수까지 전건 일치** |
| pooled ratio (11개 격자·N 조합) | 방향 **11/11** 일치, 최대 오차 **0.0202** |
| [TASK23](TASK23.md) 개입 | N=6 pooled 1.1504 → 0.9717 (실측) 대 1.1523 → 0.9687 (sim). **역전 소멸 재현** |

**두 이상치 모두 재현됐고 기전이 시뮬레이터 내부 상태로 설명된다** (아래 "이상치 재현").

## 날짜

2026-08-22

## 목적

[TASK23](TASK23.md)이 "부호는 개입으로 확정했으나 **크기를 예측하는 모형은 없다**"로 남긴 미해결을 닫는다. 닫는 방식은 닫힌 식을 더 정교하게 만드는 것이 아니라, 부호와 크기를 **동시에** 만들어 내는 step 수준 상태 기계를 세우고 기존 실측 전부로 대조하는 것이다.

## 배경

관련 TASK:

- [TASK23](TASK23.md) — 격자 정렬 법칙. `padding_slots(N)`의 단조성이 N=4·N=5에서 깨진 것이 이 TASK의 출발점
- [TASK22](TASK22.md) — prefill 배타 실행과 정지 항 (`prefill_s × 동시 decoder 수`)
- [TASK20](TASK20.md) — 44조합 N/slots sweep. 대조 자료의 주 출처
- [TASK16](TASK16.md) — `SubstrateDescriptor`. 시뮬레이터의 유일한 상수 입력
- [TASK14](TASK14.md), [TASK15](TASK15.md) — outer slot 8개 FIFO와 재사용 절벽
- [TASK13](TASK13.md) — decode step 비용 `f(bucket) + g(actual)`와 사상표

## 시작 상태

- Base commit: `8254ceb`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`
- Substrate: `patched` (SHA256 `70942d16…`). 이 TASK는 **측정을 하지 않았고** serving도 기동하지 않았다
- 대조 자료: 기존 artifact 3개 run, 80조합

## 수행 내용

1. `src/continuum/sim/`에 결정적 discrete-event 시뮬레이터를 만들었다. 입력은 `SubstrateDescriptor`와 workload plan뿐이며 가속기 이름이 코드에 없다.
2. scheduler semantics를 source에서 확인해 그대로 옮겼다 (`optimum_scheduler.py`, `optimum_prefix_cache_manager.py`, `optimum_eviction_policy.py`).
3. 층 2 hit 양의 규칙을 실측 806개 turn-1 요청으로 특정했다.
4. outer block pool의 할당·축출·조회 순서를 `[PFX]` 로그의 실제 사건 열과 대조해 확정했다.
5. 실측 plan을 `meta.*.json`에서 **재생성이 아니라 복원**해 80조합을 대조했다.
6. 비결정 가정(동시 도착의 admission 순서)의 비용을 관측 순서를 넣어 정량화했다.

## 변경된 파일

- `src/continuum/sim/__init__.py` (신규)
- `src/continuum/sim/cache.py` (신규) — outer block pool
- `src/continuum/sim/engine.py` (신규) — step 스케줄러
- `experiments/npu/analysis/sim_compare.py` (신규) — 실측 replay·채점
- `docs/research/TASK24.md` (신규)
- `docs/research/INDEX.md`

## 실험 또는 검증 방법

```bash
python3 experiments/npu/analysis/sim_compare.py \
  --run results/npu/stage2/20260820-165200-nslots-sweep \
  --labels AGENTIC.n6.b0,CONVENTIONAL.n6.b0
# TASK23 2b 격자는 --buckets 1,2,4,6,8
```

`requested_condition` / `observed_condition` / `condition_reached`:

| 항목 | requested | observed | reached |
|---|---|---|---|
| 대조 조합 수 | 기존 실측 전부 | **80** (오류 0) | `YES` |
| 자유 파라미터 | 최소화 | **보정용 0개** (아래 목록) | `YES` |
| serving 기동 | 불필요 | **0회** | `YES` |

## 결과

### 관측 1 — scheduler semantics (source-read)

`optimum_scheduler.py`는 한 step에서 prefill과 decode를 섞지 않는다. WAITING이 있고 `len(running) < max_num_seqs`이면 **정확히 하나**를 admit하고(`if req_index > 0: break`), RUNNING의 decode는 `if req_index == 0`일 때만 스케줄된다. 즉 **prefill 1건이 그 step 전체를 차지하고 실행 중인 모든 decode가 정지한다** — [TASK22](TASK22.md)가 시간 단위로 관측한 것의 source 근거다.

### 관측 2 — 층 2 hit 양의 규칙 (신규 발견, 실측 271/271)

turn-1 요청 806건 중 hit이 난 271건 전부에서 다음이 성립했다.

```
cached_tokens = floor(min(prompt_tokens(직전 요청), prompt_tokens(현재) − 1) / 128) × 128
```

**직전 요청이 prefill에서 계산한 prompt token만 캐시되며, decode가 써 넣은 생성 token은 캐시되지 않는다.** 생성 token까지 공유 prefix로 세는 대안은 271건 중 38건만 맞았다(164건이 1 block, 69건이 2 block 초과 예측).

| 후보 | 일치 |
|---|---|
| `floor(min(p₀ + g₀, p₁−1)/128)×128` (생성분 포함) | 38/271 |
| **`floor(min(p₀, p₁−1)/128)×128`** (prefill 계산분만) | **271/271** |
| `floor((p₀−1)/128)×128` | 269/271 |

세 번째 후보와 두 번째는 `p₀`가 128의 배수일 때만 갈리고 그런 경우가 2건 있었는데 둘 다 두 번째가 맞았다. 즉 **prompt 경계에서 정확히 꽉 찬 inner block은 캐시되고, decode 중에 꽉 찬 block은 캐시되지 않는다.**

### 관측 3 — outer block pool의 사건 순서 (`[PFX]` 로그 대조)

`[PFX] [ALLOC]` / `[CACHE-HIT]` / `[EVICTION]` 열을 두 조합에서 사건 단위로 따라가 다음을 확정했다.

1. **admission마다 새 outer block을 하나 할당한다.** cache hit이 나도 마찬가지이며, hit은 별도의 mapping을 매칭할 뿐 할당을 대신하지 않는다.
2. **free block이 없으면 먼저 축출한다.** victim은 할당 순서(FIFO) 기준 최고참 **inactive** block이다.
3. **완료 요청의 block이 evictable로 바뀌는 시점은 다음 admission이 victim을 고른 *뒤*다.** `EVICTION OB=3` → `FREE-REQUEST` → `ALLOC OB=[3]` 순으로 기록된다.
4. **조회는 active/inactive를 가리지 않는다.** 아직 다른 요청이 쓰고 있는 mapping도 매칭된다. 따라서 miss의 원인은 축출뿐이다.

3번이 결정적이다. **tool gap 없이 즉시 돌아오는 세션은 자기 entry를 자기가 축출할 수 없다** — victim을 고르는 시점에 그 entry가 아직 사용 중으로 세어지기 때문이다. gap을 두고 돌아오는 세션에는 그 보호가 없다. `CONVENTIONAL.n6.b0`의 축출 열 `3, 2, 1, 0, 4`와 6/6 hit이 이 규칙으로 정확히 재현된다.

### 관측 4 — in-sample 재현표

80조합, 오류 0.

| 지표 | 중앙 | 평균절대 | 최대절대 |
|---|---|---|---|
| utilization 오차 | `+0.0000` | **0.0066** | 0.0495 |
| decode step 수 상대오차 | `+0.0000` | 1.8 % | 12.4 % |

N별 utilization 절대오차:

| N | 3 | 4 | 5 | 6 | 7 | 8 | 10 | 12 | 16 |
|---|---|---|---|---|---|---|---|---|---|
| 평균 | .0012 | .0021 | .0021 | .0029 | .0038 | .0037 | .0180 | .0225 | .0113 |
| 최대 | .0031 | .0058 | .0036 | .0064 | .0082 | .0124 | .0482 | .0495 | .0204 |

**`max_num_seqs = 8` 이하에서는 오차가 0.004 이내이고, 초과 구간(N ≥ 10)에서 5–6배로 커진다.**

층 2 재사용: hit/miss 판정 **608/654 = 93.0 %** 일치, 총 hit 실측 239 대 sim 231. hit으로 맞힌 경우 **token 수까지 전건 일치**했다(관측 2의 규칙이 정확하다는 뜻).

### 관측 5 — pooled ratio 재현

`ratio = util(AGENTIC)/util(CONVENTIONAL)`, pooled는 [TASK20](TASK20.md)과 같은 step 가중.

| 격자 | N | padding/bucket | 실측 pooled | sim pooled | 오차 |
|---|---|---|---|---|---|
| (1,2,4,8) | 3 | 0.250 | 1.0820 | 1.0852 | +0.0031 |
| (1,2,4,8) | **4** | **0.000** | **1.0414** | **1.0409** | −0.0005 |
| (1,2,4,8) | **5** | **0.375** | **1.1336** | **1.1345** | +0.0009 |
| (1,2,4,8) | 6 | 0.250 | 1.1504 | 1.1523 | +0.0019 |
| (1,2,4,8) | 7 | 0.125 | 1.0220 | 1.0171 | −0.0049 |
| (1,2,4,8) | 8 | 0.000 | 0.9205 | 0.9211 | +0.0006 |
| (1,2,4,8) | 10 | — | 0.9103 | 0.9065 | −0.0038 |
| (1,2,4,8) | 12 | — | 0.9192 | 0.9395 | +0.0202 |
| (1,2,4,8) | 16 | — | 0.9944 | 0.9807 | −0.0137 |
| **(1,2,4,6,8)** | **6** | **0.000** | **0.9717** | **0.9687** | −0.0031 |
| (1,2,4,6,8) | 8 | 0.000 | 0.9508 | 0.9474 | −0.0034 |

방향(1 초과/미만) **11/11 일치**.

### 관측 6 — 이상치 재현과 기전

**이상치 1: N=4는 padding이 0인데 pooled가 1.0414로 1보다 크다.** sim 1.0409로 재현됐다. sim이 보여 주는 이유는 step 점유 분포다.

| N=4 | padding 0인 step 비율 | 분포 |
|---|---|---|
| CONVENTIONAL | 0.774 | `1→1` 9 % `2→2` 10 % **`3→4` 23 %** `4→4` 58 % |
| AGENTIC | **0.954** | `1→1` 52 % `2→2` 32 % `3→4` 5 % `4→4` 11 % |

`padding_slots(4) = 0`은 **정상 상태에만** 해당한다. 세션이 하나씩 끝나면서 batch가 4 → 3 → 2 → 1로 내려가는 **감쇠 경로**를 지나는데, 그 경로의 `3→4`는 padding 1이다. CONVENTIONAL은 여기서 23 %의 step을 쓰고 AGENTIC은 5 %만 쓴다.

**이상치 2: padding 비율이 가장 큰 N=5(0.375)의 역전이 N=6(0.25)보다 작다.** sim도 1.1345 < 1.1523으로 순서까지 재현했다.

| | CONVENTIONAL padding 0 비율 | AGENTIC padding 0 비율 |
|---|---|---|
| N=5 | 0.469 | 0.693 |
| N=6 | **0.392** | **0.805** |

**양쪽 arm이 모두 N=6에서 더 벌어진다.** N=6의 conventional은 43 %의 step을 `6→8`(padding 2)로 보내 N=5의 `5→8` 34 %보다 나쁘고, N=6의 agentic은 gap이 batch를 `2→2`(38 %, padding 0)로 자주 쪼개는 반면 N=5의 agentic은 `3→4`(21 %, padding 1)에 더 자주 앉는다.

**따라서 법칙이 깨진 이유는 법칙이 틀려서가 아니라 `padding_slots(N)`이 정상 상태 하나만 가격을 매기기 때문이다.** ratio를 정하는 것은 두 arm이 실제로 방문하는 **점유 분포 전체에 걸친 padding의 적분**이며, 그 분포는 닫힌 식이 아니라 상태 기계가 만들어 낸다.

### 관측 7 — 비결정 가정의 비용

동시에 도착한 요청의 admission 순서는 실제로는 thread 스케줄링이 정하므로 재현되지 않는다. 기본값은 session index 순이고, 실측 `sent_s` 순서를 넣으면 다음이 된다.

| 가정 | utilization 평균절대오차 | 최대 | 재사용 일치 |
|---|---|---|---|
| session index 순 (기본) | 0.0066 | 0.0495 | 93.0 % |
| **관측 도착 순서** | **0.0046** | **0.0260** | **94.8 %** |
| client overhead 5 ms | 0.0065 | 0.0500 | 93.0 % |

**남은 오차의 약 3분의 1이 이 비결정 하나에서 온다.** 예측 용도로는 관측 순서를 알 수 없으므로 기본값을 쓴다.

## 자유 파라미터 목록

보정을 위해 값을 맞춘 파라미터는 **없다.** 아래는 descriptor 밖에서 시뮬레이터가 요구하는 입력 전부다.

| 항목 | 값 | 출처 | 보정 여부 |
|---|---|---|---|
| `max_running_requests` | 8 | compile `batch_size` = `max_num_seqs` | 구성값 |
| `client_overhead_s` | **0.0** | 실측 0.6–5.6 ms를 **쓰지 않고 0으로 둠** | 미보정. 5 ms를 넣어도 오차가 0.0066 → 0.0065로 무변 |
| `arrival_order` | session index | 재현 불가능한 비결정에 대한 **가정** | 미보정. 비용은 관측 7 |
| bucket 6의 고정 비용 | bucket 4·8 사이 **선형 보간** | [TASK13](TASK13.md)이 bucket 6을 측정한 적 없음 | **유도값.** [TASK23](TASK23.md) 2b 격자에만 영향 |
| prompt token | plan에서 유도 | 실측 806건 중 784건 정확 일치, 22건이 **1 token** 낮음(재tokenize 이음매) | 미보정 |
| 층 2 hit 규칙 | 관측 2 | source-read + 실측 271/271 | 미보정 |
| pool 사건 순서 | 관측 3 | source-read + `[PFX]` 로그 대조 | 미보정 |

## 핵심 발견

1. **`stack` — 층 2 캐시는 prefill이 계산한 token만 담고 decode가 써 넣은 token은 담지 않는다.** 실측 271/271. 즉 agentic 세션의 turn *k* 가 재사용할 수 있는 것은 turn *k−1* 의 **prompt**까지이고, turn *k−1* 이 생성한 부분은 매번 다시 계산된다. 생성이 길수록 재사용률의 상한이 내려간다.
2. **`class`(형태) + `stack`(값) — 즉시 돌아오는 세션은 자기 캐시를 자기가 축출하지 않는다.** 완료 block이 evictable로 바뀌는 시점이 다음 admission의 victim 선택보다 **뒤**이기 때문이다. gap을 두고 돌아오는 세션에는 이 보호가 없다. **gap의 재사용 손해에는 "경쟁자가 늘어난다"뿐 아니라 "자기 보호를 잃는다"가 들어 있다.** 형태를 `class`로 보는 근거: "정리 시점이 할당 결정보다 늦다"는 순서 문제는 특정 자료구조가 아니라 완료 처리와 스케줄링을 분리한 어느 엔진에서나 생길 수 있다.
3. **`stack` — `padding_slots(N)`이 단조성을 깨는 이유는 감쇠 경로다.** N=4는 정상 상태 padding이 0인데도 batch가 4→3→2→1로 내려가며 `3→4`를 지나고, CONVENTIONAL은 그 구간에 step의 23 %를 쓴다. **정상 상태 padding은 실제 padding의 하한일 뿐이다.**
4. **`universal` — 부호와 크기를 함께 만드는 것은 닫힌 식이 아니라 상태 기계다.** 같은 descriptor 상수만 쓰고 보정 파라미터 없이 11개 pooled ratio를 방향 11/11, 최대 오차 0.0202로 재현했다. [TASK23](TASK23.md)이 "크기 모형 없음"으로 남긴 미해결은 **닫힌 식을 포기하는 것으로** 닫힌다.
5. **`stack` — 재현 품질이 `max_num_seqs`에서 꺾인다.** N ≤ 8은 utilization 평균절대오차 0.004 이내, N ≥ 10은 0.011–0.023이다. 대기열이 생기는 구간에 아직 모형에 없는 것이 있다.

## 해석

- **(해석)** 발견 1과 2를 합치면 agentic 재사용의 손실 경로가 둘로 나뉜다. **양의 손실**(생성분은 애초에 캐시되지 않는다)과 **생존의 손실**(gap 동안 축출된다)이다. [TASK21](TASK21.md)이 관측한 "도착 순서가 성패를 가른다"는 두 번째 경로의 표현이고, 첫 번째 경로는 gap과 무관하게 항상 작동한다.
- **(해석)** 발견 3은 [TASK23](TASK23.md)의 법칙을 반증하지 않고 **적용 범위를 좁힌다.** 법칙은 "정상 상태 padding이 부호를 정한다"로 읽어야 하고, 크기는 감쇠 경로까지 포함한 분포에서 나온다. N ≥ 10에서 저하가 확정된 것도 같은 틀에서 읽힌다.
- **(해석)** 발견 5의 꺾임은 아직 원인이 확정되지 않았다. 대기열이 있는 구간에서는 admission 순서, `skipped_waiting` 재큐, prefill 대기가 얽히는데 그중 무엇이 지배적인지 이 TASK로는 가르지 못한다.
- **(해석)** in-sample 재현은 **예측력의 증거가 아니다.** 대조에 쓴 80조합은 전부 이미 관측된 것이고, 규칙 중 둘(관측 2·3)은 그 자료를 보고 특정했다. 예측력 주장은 선등록된 out-of-sample 검증에서만 나올 수 있으며 그것이 다음 TASK다.

## 확인되지 않은 사항

- N ≥ 10에서 오차가 커지는 원인 (`UNKNOWN`). 대기열 구간의 어떤 기전이 빠졌는지 가르지 못했다.
- 완료 block의 evictable 전환이 왜 다음 admission의 victim 선택보다 늦는지 (`UNKNOWN`). 순서는 `[PFX]` 로그로 확정했지만 그 원인이 vLLM의 완료 처리 시점인지 vllm-rbln의 free 경로인지는 확인하지 않았다.
- turn이 3 이상인 세션에서 층 2 mapping이 어떻게 연장되는지 (`UNKNOWN`). 실측이 전부 2 turn이라 대조 자료가 없다.
- bucket 6의 고정 비용 (`UNKNOWN`, 선형 보간으로 대체). [TASK23](TASK23.md) 2b 격자 결과에만 영향을 준다.
- 재tokenize 이음매로 turn-1 prompt가 1 token 짧아지는 22/806 사례의 조건 (`UNKNOWN`, 영향은 1/1200 수준).

## 실패 / 무효 시도

- **cache hit이 매칭한 block을 활성화한다는 모형** — 처음 세운 가설이다. 이 모형에서는 hit이 난 block이 축출 대상에서 빠지는데, `[PFX]` 로그에 `CACHE-HIT OB=[3]` 직후 `EVICTION OB=3`이 실제로 나와 반증됐다.
- **hit이 매칭 block을 흡수하고 새 block을 쓰지 않는다는 모형** — `CONVENTIONAL`의 6/6 hit은 맞히지만 `AGENTIC`의 축출 열을 만들지 못한다. `ALLOC OB=[6]`이 hit과 무관하게 새 block을 잡는 로그로 반증됐다.
- **완료 즉시 evictable로 전환하는 모형** — 구현했으나 `CONVENTIONAL.n6.b0`에서 세션이 자기 entry를 자기가 축출해 hit이 6 대신 3이 됐다. 로그의 `EVICTION` → `FREE-REQUEST` → `ALLOC` 순서로 반증하고 지연 규칙으로 교체했다.

세 가설 모두 실측 자료가 아니라 **로그의 사건 열**로 갈렸다. 집계값만 봤다면 첫 모형도 "93 %쯤 맞는다"로 통과했을 것이다.

## 연구 원칙에 미치는 영향

1. **in-sample 재현을 예측력으로 보고하지 않는다.** 대조 자료를 보고 규칙을 특정한 이상, 같은 자료에서의 일치는 구성상 보장에 가깝다. 예측 주장은 선등록된 out-of-sample에서만 한다.
2. **모형의 규칙은 집계값이 아니라 사건 열로 검증한다.** 세 개의 틀린 pool 모형이 전부 집계 수준에서는 그럴듯했다.
3. **"보정하지 않았다"를 주장하려면 descriptor 밖 입력을 전부 나열한다.** 값을 맞춘 적이 없어도 가정은 가정이다(관측 7의 admission 순서, 보간한 bucket 6 비용).
4. **정상 상태 상수를 경로 전체의 값으로 쓰지 않는다.** `padding_slots(N)`은 감쇠 경로의 padding을 세지 않으므로 실제 padding의 하한이다.

## 다음 작업

제안만 하며 사용자 지시 없이 실행하지 않는다.

1. **선등록 out-of-sample 검증** — 측정 전에 시뮬레이터로 pooled ratio와 블록 방향을 예측해 commit하고, 신규 seed로 실측한다. 이 TASK의 유일한 정당한 후속이다.
2. N ≥ 10 오차의 원인 규명 — 대기열 구간의 누락 기전.
3. offline oracle bound — 검증 게이트를 통과한 뒤에만 의미가 있다.

## 재현 정보

- 선등록 commit: **해당 없음.** 이 TASK는 측정을 수행하지 않았고 기존 artifact만 재분석했다
- Base commit: `8254ceb`
- 시뮬레이터: `src/continuum/sim/{__init__,cache,engine}.py`
- 대조 harness: `experiments/npu/analysis/sim_compare.py`
- 대조 artifact: `results/npu/stage2/{20260820-165200-nslots-sweep,20260821-222000-grid-observe,20260821-231000-grid-intervene}/`
- Substrate 인스턴스: `experiments/npu/substrate/rbln_ca25_vllm_rbln_0111.py`
- source 근거: `vllm_rbln/v1/core/optimum_scheduler.py`, `vllm_rbln/v1/core/prefix_cache_manager/{optimum_prefix_cache_manager,optimum_eviction_policy}.py`
- 예산 사용: serving 기동 **0회**, 재compile 0회, 신규 측정 0건
