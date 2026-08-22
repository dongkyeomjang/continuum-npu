# TASK29 — 기전 절제 분석과 결정 5 기록

## 상태

DONE

## 판정

**판정 기준이 있는 TASK가 아니다. 측정이 아니라 계산이며, 이 문서 전체에서 그 성격을 유지한다.**

절제 결과는 **모형이 무엇을 함의하는가**에 대한 진술이다. 다른 스택에 대한 진술로 읽으려면 "그 스택이 실제로 대체 semantics를 갖는다"는 별도 근거가 필요하고, 그 근거는 아래 인용 목록에서 온다 — **이 저장소에 설치된 `vllm 0.22.0` source 자체**다.

| 축 | 대체 | 기전이 소멸하는가 |
|---|---|---|
| ① eviction | FIFO·시퀀스 단위 → LRU·index 단위 | **문턱의 *성격*이 바뀐다.** 측정 조건은 배경 요청 **개수** B=7에서 절벽이며 요청 크기와 무관하다. 절제 조건의 문턱은 **token 총량**에 걸려 배경 크기에 따라 B가 61/31/16으로 움직이고 500 token에서는 B=70까지 손실이 없다 |
| ② bucket 격자 | (1,2,4,8) → 연속 | **완전히 소멸한다.** N=6 pooled 1.1523 → **1.0000**, N=8 0.9238 → **1.0000** (양쪽 arm이 정확히 같아진다) |
| ② ' | (1,2,4,8) → **GPU cudagraph 격자** | **소멸하지 않는다.** `max_num_seqs=8`에서 GPU 기본 격자는 `[1,2,4,8,16]`이고 1..8 구간이 NPU 격자와 **동일**하므로 결과가 소수 넷째 자리까지 같다 |
| ③ prefill 직렬화 | 배타 → chunked (정지 0) | **정지는 소멸하지만 device time은 늘어난다.** stall 12.7/28.2/84.4 s → **0**인데 busy는 30.6→31.5, 31.2→33.5, 40.1→44.1 s로 **증가**한다 |

**②'가 이 TASK에서 가장 중요한 결과일 수 있다.** 격자 정렬 법칙은 GPU에서 사라질 것으로 예상됐으나, 같은 `max_num_seqs`에서는 **재현될 것으로 계산된다.**

## 날짜

2026-08-22

## 목적

GPU 실측을 대체하는 반사실 분석을 수행한다. 이 연구가 세운 세 기전([TASK14](TASK14.md)/[TASK15](TASK15.md)의 재사용 절벽, [TASK23](TASK23.md)의 격자 정렬 법칙, [TASK22](TASK22.md)의 prefill 직렬화 세금)이 **각 기전을 담당하는 substrate 성질을 다른 스택의 것으로 바꿨을 때** 어떻게 되는지를 계산으로 보인다.

## 배경

관련 TASK:

- [TASK28](TASK28.md) — 시뮬레이터가 제어 개입 조건까지 예측함을 실기기로 확인. 이 계산이 의미를 갖는 근거
- [TASK25](TASK25.md) — out-of-sample 예측력 게이트 `PASS`
- [TASK23](TASK23.md) — 격자 정렬 법칙 (축 ②의 대상)
- [TASK22](TASK22.md) — prefill 배타 실행 (축 ③의 대상)
- [TASK14](TASK14.md), [TASK15](TASK15.md) — 재사용 절벽과 FIFO outer slot (축 ①의 대상)

## 시작 상태

- Base commit: `df777ba`
- **측정 없음.** serving 기동 0회, 재compile 0회, GPU 서버 접근 0건

## 수행 내용

1. 시뮬레이터에 절제 축 3개를 구현했다. **측정 경로의 기본값은 바뀌지 않았고** [TASK24](TASK24.md) 80조합의 비트 단위 재현을 회귀 검사로 확인했다.
2. 축 ①은 [TASK15](TASK15.md)의 절벽 구성을 그대로 재현해 두 캐시 체제에서 각각 계산했고, 배경 요청 **크기**를 바꿔 문턱이 무엇에 의존하는지 분리했다.
3. 축 ②는 [TASK20](TASK20.md) plan에서 N=6·N=8의 pooled ratio를 세 격자로 계산했다.
4. 축 ③은 [TASK20](TASK20.md) plan에서 N=6·8·12의 device time 분해와 oracle headroom을 두 조건으로 계산했다.
5. 각 대체의 근거를 **설치된 vLLM source에서** 확인해 인용 목록을 만들었다.

## 변경된 파일

- `src/continuum/sim/cache.py` (`GranularPool` 추가, `OuterBlockPool`에 LRU 축 추가)
- `src/continuum/sim/engine.py` (`cache_granularity`, `eviction_policy`, `prefill_exclusive`)
- `experiments/npu/analysis/ablation.py` (신규)
- `docs/research/TASK29.md` (신규)
- `docs/research/INDEX.md`

## 결과

### 축 ① — eviction: FIFO·시퀀스 단위 → LRU·index 단위

[TASK15](TASK15.md)의 구성을 그대로 쓴다: target이 2,000 token prefix를 캐시하고, gap 동안 배경 요청 B개가 도착한 뒤, target이 2,008 token으로 돌아온다.

| B | 측정 그대로 (FIFO, 시퀀스 단위) | 절제 (LRU, index 단위) |
|---|---|---|
| 0–6 | 1,920 | 1,920 |
| **7** | **0** | 1,920 |
| 8–28 | 0 | 1,920 |
| **31** | 0 | **0** |
| 32–40 | 0 | 0 |

**두 조건 모두 절벽이지만 문턱이 다르다.** 더 중요한 것은 문턱이 **무엇의 함수인가**다.

| 배경 요청 크기 | 측정 절벽 B | 절제 첫 손실 B | 절제 소멸 B |
|---|---|---|---|
| 500 tok | **7** | 없음 (B=70까지) | 없음 |
| 1,000 tok | **7** | 61 | 62 |
| 2,000 tok | **7** | 31 | 31 |
| 4,000 tok | **7** | 16 | 16 |

**측정 substrate의 문턱은 요청 개수 7로 고정이며 요청 크기와 무관하다.** 절제 substrate의 문턱은 **token 총량**에 걸려 배경 크기에 반비례한다. [TASK14](TASK14.md)가 "생존을 결정하는 것은 token 총량이 아니라 요청 개수"라고 기록한 성질이, 바로 이 FIFO·시퀀스 단위 구조가 만들어 낸 것임을 계산이 보여 준다.

`class`로 승격할 수 있는 것은 **"고정된 소수의 시퀀스 단위 슬롯을 쓰면 생존이 개수 문턱이 된다"** 는 형태이고, **문턱 값 7은 인스턴스 상수**다. 승격 조건은 아래 인용 ①이 뒷받침한다.

### 축 ② — bucket 격자

[TASK20](TASK20.md)의 실측 plan에서 pooled ratio(`util(AGENTIC)/util(CONVENTIONAL)`)를 세 격자로 계산했다.

| 격자 | N=6 pooled | N=8 pooled |
|---|---|---|
| 측정 그대로 `(1,2,4,8)` | **1.1523** | **0.9238** |
| 연속 `bucket = actual` | **1.0000** | **1.0000** |
| **GPU cudagraph 격자 `(1,2,4,8,16)`** | **1.1523** | **0.9238** |

- **연속 격자에서 법칙은 완전히 소멸한다.** padding이 정의상 0이 되어 두 arm의 utilization이 정확히 같아지므로 ratio가 1이다. 부호도 크기도 남지 않는다.
- **GPU cudagraph 격자에서는 소멸하지 않는다.** `max_num_seqs = 8`에서 vLLM의 기본 capture size 목록은 `[1, 2, 4, 8, 16]`이고, 동시성이 8을 넘지 않는 이 워크로드에서 실제로 쓰이는 부분집합 `{1,2,4,8}`이 NPU 격자와 **같다.** 따라서 결과가 소수 넷째 자리까지 일치한다.

**GPU에도 격자가 있으므로 "GPU에는 이 법칙이 없다"는 대비는 성립하지 않는다.** 다만 `max_num_seqs`가 커지면 GPU 격자는 8 간격, 이어서 16 간격으로 촘촘해지므로(예: `max_num_seqs=256`이면 51개 크기) **상대 padding이 작아져 법칙의 크기가 줄어들 것으로 본다.** 이는 계산하지 않은 추론이다.

### 축 ③ — prefill: 배타 실행 → chunked

| N | 조건 | busy (s) | decode | prefill | **stall** | 재사용 | oracle ε=1 절감 |
|---|---|---|---|---|---|---|---|
| 6 | 측정 (배타) | 30.638 | 24.857 | 5.780 | **12.666** | 13/18 | 8.62 % |
| 6 | 절제 (chunked) | **31.528** | 25.570 | 5.958 | **0** | 12/18 | 9.59 % |
| 8 | 측정 (배타) | 31.159 | 22.439 | 8.720 | **28.163** | 9/24 | 8.66 % |
| 8 | 절제 (chunked) | **33.452** | 24.732 | 8.720 | **0** | 9/24 | 10.21 % |
| 12 | 측정 (배타) | 40.138 | 23.870 | 16.268 | **84.384** | 1/36 | 2.86 % |
| 12 | 절제 (chunked) | **44.113** | 28.446 | 15.667 | **0** | 4/36 | 2.63 % |

**정지 항은 정의대로 0이 된다.** cache 실패 비용의 "× 동시 decoder 수" 증폭이 사라지므로 [TASK22](TASK22.md)가 세운 비용 모형 v2의 두 번째 항이 통째로 없어진다.

**그런데 device time은 오히려 2.9–9.9 % 늘어난다.** 기전은 decode 항에 있다(24.9 → 25.6, 22.4 → 24.7, 23.9 → 28.4 s). **배타 prefill은 실행 중인 decoder들을 멈춰 세워 강제로 동기화시키고, 재개될 때 더 넓은 batch를 만든다.** 그 부수 효과가 사라지면 decode가 더 좁은 batch로 흩어져 token당 비용이 오른다.

oracle headroom(ε=1 s)은 N=6에서 8.62 → 9.59 %, N=8에서 8.66 → 10.21 %로 늘고 N=12에서는 2.86 → 2.63 %로 줄어든다. **정지 세금이 사라진 만큼 headroom이 batching 쪽으로 재분배된다** — [TASK26](TASK26.md)이 N이 클수록 재계산 절감의 비중이 커진다고 한 것과 맞물린다.

## GPU 측 대응 근거 (인용 목록)

**모두 이 host에 설치된 `vllm 0.22.0+cpu` source에서 직접 확인했다.** 외부 문헌 인용이 아니라 실행 가능한 코드다.

| # | 주장 | 근거 |
|---|---|---|
| ① | vLLM의 prefix cache는 **LRU**이며 회수 단위는 **inner block**이다 | `vllm/v1/core/kv_cache_utils.py:164–181`, `FreeKVCacheBlockQueue` docstring: *"The queue is ordered by block ID in the beginning. When a block is allocated and then freed, it will be appended back with the eviction order: 1. The least recent used block is at the front (LRU)."* |
| ①' | 한 요청의 block들은 **꼬리부터** 회수된다 | 같은 docstring: *"2. If two blocks have the same last accessed time (allocated by the same sequence), the one with more hash tokens (the tail of a block chain) is at the front."* — 절제 모형의 tie-break를 이 문장에 맞췄다 |
| ② | GPU에도 **이산 격자**가 있다 (cudagraph capture size) | `vllm/config/compilation.py:676–690`: 기본 목록은 `[1, 2, 4] + range(8, 256, 8) + range(256, max+1, 16)`이고 `max_cudagraph_capture_size = min(max_num_seqs*2, 512)`. `max_num_seqs=8` → `[1, 2, 4, 8, 16]` |
| ③ | vLLM은 **chunked prefill이 기본**이다 | `vllm/config/scheduler.py:84`: `enable_chunked_prefill: bool = True`. encoder-decoder 모델에서만 강제 해제된다(`:226–232`) |
| ④ | 대조군인 RBLN은 **prefill을 배타 실행**한다 | `vllm_rbln/v1/core/optimum_scheduler.py:300–304` 주석과 실제 제어 흐름(`if req_index > 0: break`, decode는 `if req_index == 0`일 때만), [TASK22](TASK22.md)에서 시간 단위로 직접 관측 |
| ⑤ | 대조군인 RBLN은 **FIFO를 하드코딩**한다 | `vllm_rbln/v1/core/prefix_cache_manager/optimum_eviction_policy.py:48–82`, `FIFOEvictionPolicy`가 사용되고 `LRUEvictionPolicy`는 정의만 존재 |

**인용이 뒷받침하는 것과 아닌 것을 구분한다.** ①–⑤는 *semantics가 그러하다*를 뒷받침한다. **그 semantics 아래에서 나오는 수치(절제 컬럼의 값)는 전부 이 시뮬레이터의 계산이며 GPU에서 측정된 적이 없다.**

## 핵심 발견

각 항목에 **모형 수준 / 승격 조건**을 함께 적는다.

1. **`class`(형태) — 생존 법칙의 문턱이 "개수"인 것은 시퀀스 단위 FIFO 슬롯 구조의 결과다.** 측정 조건의 문턱은 배경 요청 크기 500·1,000·2,000·4,000 token 전부에서 B=7로 고정이고, 절제 조건에서는 61·31·16으로 크기에 반비례한다. **형태를 `class`로 보는 근거**: "고정 개수의 시퀀스 단위 슬롯"이라는 설계 범주에서 바로 따라 나오며 특정 구현 상수에 의존하지 않는다. **모형 수준이며, 승격 조건은 인용 ①·⑤ 및 향후 GPU 실측 1건(생존 곡선)이다.**
2. **`stack` — 격자 정렬 법칙은 연속 격자에서 정확히 1.0000으로 소멸한다.** 두 arm의 utilization이 항등적으로 같아지므로 부호도 크기도 남지 않는다. **모형 수준. 이 결과는 항등식에 가까워 승격 조건이 사실상 없다** — padding이 0이면 padding으로 설명되던 차이가 0이 되는 것은 정의의 문제다.
3. **`class`(형태) — GPU에도 격자가 있으므로 법칙은 GPU에서 사라지지 않는다.** `max_num_seqs=8`에서 cudagraph 격자 `[1,2,4,8,16]`의 유효 부분이 NPU 격자와 동일해 pooled ratio가 소수 넷째 자리까지 같다. **이는 이 연구의 사전 기대(비교축 ②가 "GPU에서 소멸하는지"를 본다)를 뒤집는다.** **모형 수준이나 근거의 절반은 인용 ②의 source 사실이다. 승격 조건: GPU에서 `max_num_seqs`를 8로 두고 같은 워크로드를 재는 실측 1건.**
4. **`stack` — chunked prefill은 정지를 없애면서 device time을 3–10 % 늘린다.** 배타 prefill이 decoder를 멈춰 세워 **강제 동기화**를 일으키고, 그 부수 효과가 batch 폭을 넓히고 있었다. **"직렬화 세금"이 순수한 비용이 아니라 일부는 batching 보조금이었다.** **모형 수준. 승격 조건: chunked prefill 스택에서 같은 workload의 device time 실측.**
5. **`universal` — 절제는 기전의 *존재*를 검증하지 못하고 *귀속*만 검사한다.** 세 축 모두 "이 성질을 빼면 이 결과가 어떻게 되는가"에 답할 뿐, 그 성질을 가진 다른 하드웨어에서 같은 값이 나온다고 말하지 않는다. **모형 수준이며, 이 항목은 방법론이므로 승격 대상이 아니다.**

## 해석

- **(해석)** 발견 3이 GPU 교차검증의 설계를 바꾼다. 원래 비교축 ②는 "격자 정렬 법칙이 cudagraph capture size 축에서 재현되는가"였고 암묵적 기대는 "GPU는 연속에 가까우니 약해질 것"이었다. 계산은 **같은 `max_num_seqs`에서는 동일**하고 **`max_num_seqs`가 커질 때 약해질 것**이라고 말한다. GPU 실험을 한다면 재야 할 축은 accelerator가 아니라 **`max_num_seqs`** 다.
- **(해석)** 발견 4는 [TASK22](TASK22.md)의 해석을 정교하게 만든다. prefill 배타 실행은 cache 실패 비용을 증폭시키지만(정지 × 동시 decoder), 동시에 decoder를 정렬시켜 batch를 넓힌다. **두 효과의 부호가 반대이고 이 워크로드에서는 후자가 더 크다.**
- **(해석)** 발견 1이 GPU 실측의 최소 범위를 정한다. 세 축 중 **생존 곡선만이** 모형과 문헌만으로는 닫히지 않는다 — 축 ②는 source 사실(격자 목록)로 대부분 닫히고 축 ③은 부호 방향이 분명하지만, 축 ①의 문턱 위치는 실제 pool 크기·block 크기·workload에 달려 있어 실측 없이는 값을 말할 수 없다.
- **(해석)** 절제 컬럼의 수치를 GPU 예측으로 인용하면 안 된다. 이 시뮬레이터는 RBLN 상수([TASK13](TASK13.md) step 비용 등)를 그대로 쓰고 semantics만 바꿨다. **GPU의 step 비용 곡선은 다르고, 그것이 축 ②·③의 크기를 좌우한다.**

## 확인되지 않은 사항

- 절제 조건의 수치가 실제 GPU 스택에서 재현되는지 (`UNKNOWN`). **측정한 적 없다.**
- `max_num_seqs`가 클 때 격자 정렬 법칙이 실제로 약해지는지 (`UNKNOWN`, 계산하지 않은 추론).
- GPU의 step 비용 곡선 `f(bucket)` (`UNKNOWN`). 축 ②·③의 크기가 여기에 달려 있다.
- 축 ①에서 문턱 근처의 감쇠 형태 (`PARTIAL`). 배경 요청이 target과 같은 크기이면 한 admission이 target의 chain 전체를 회수해 계단이 2–3개뿐이다. 크기가 섞인 실제 workload에서의 형태는 계산하지 않았다.
- 세 축의 상호작용 (`UNKNOWN`). 각각 하나씩만 바꿨다.

## 실패 / 무효 시도

- **절제 ①의 첫 구현이 한 admission의 block마다 다른 timestamp를 줬다.** 그 결과 LRU가 chain의 **머리**를 먼저 버려 prefix가 통째로 사라졌고, 감쇠가 아니라 절벽이 나왔다. vLLM의 `FreeKVCacheBlockQueue` docstring이 같은 시각의 block 중 **꼬리**를 먼저 버린다고 명시하고 있어 tie-break를 `(touch, -position)`으로 고쳤다. **대체 semantics를 문서대로 구현하지 않으면 절제가 아무것도 절제하지 않는다.**
- **절제 축을 추가하면서 측정 경로가 바뀌지 않았는지 확인하지 않을 뻔했다.** [TASK27](TASK27.md)에서 같은 실수를 한 뒤라 회귀 검사를 먼저 돌렸고, [TASK24](TASK24.md) 80조합이 비트 단위로 동일함을 확인한 뒤 진행했다.

## 연구 원칙에 미치는 영향

1. **절제 결과는 모형 진술이며 문서 전체에서 그 성격을 유지한다.** 표의 "절제" 열은 예측이 아니라 반사실이다.
2. **대체 semantics는 대체 대상 스택의 source·문서대로 구현한다.** 그러지 않으면 절제가 자기 자신의 가정을 되돌려 줄 뿐이다.
3. **`class` 승격은 항목별로 조건을 적는다.** "형태는 class"라는 문장에 근거와 승격 조건이 없으면 그것은 태그가 아니라 희망이다.
4. **사전 기대와 반대되는 절제 결과를 그대로 보고한다.** 축 ②'는 GPU 대비를 약화시키지만, 그것이 계산이 말하는 바다.

## 다음 작업

제안만 하며 사용자 지시 없이 실행하지 않는다.

1. **논문 조립** — 시스템 명칭 변경을 포함한다(아래 명칭 충돌).
2. GPU 실측이 필요해지면 **생존 곡선 1실험**으로 최소화한다([결정 4](INDEX.md#결정-4--gpua6000-교차검증-착수-시점) 개정본).
3. [TASK28](TASK28.md) 발견 3의 계통 편향 원인 규명.
4. `max_num_seqs` 축에서 격자 정렬 법칙의 크기 변화 계산 — 새 측정이 필요 없다.

## 재현 정보

- 선등록 commit: **해당 없음.** 판정 기준이 있는 측정이 아니라 계산이다
- Base commit: `df777ba`
- 절제 구현: `src/continuum/sim/cache.py`(`GranularPool`), `src/continuum/sim/engine.py`(`cache_granularity`, `eviction_policy`, `prefill_exclusive`)
- 실행 harness: `experiments/npu/analysis/ablation.py`
- 대상 plan: `results/npu/stage2/20260820-165200-nslots-sweep/probe/meta.*.n{6,8,12}.b{0,1,2}.json`
- 회귀 검사: [TASK24](TASK24.md) 80조합 비트 단위 일치 (절제 축 추가 전후)
- 인용 근거: `/usr/local/lib/python3.10/dist-packages/vllm/` 및 `.../vllm_rbln/` (설치본, 버전 `0.22.0+cpu` / `0.11.1`)
- 예산 사용: serving 기동 **0회**, 재compile **0회**, GPU 서버 접근 **0건**
