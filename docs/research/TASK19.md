# TASK19 — AGENTIC vs CONVENTIONAL 짝 비교 파일럿

## 상태

DONE

## 판정

- **1차 측정: `INVALID`.** 불변식 P1(두 arm의 plan이 gap 외 동일)이 위반됐다. 선등록 규칙대로 짝 비교를 무효 처리했고 **판정 기준을 완화하지 않았다.**
- **재측정(개정 1): 4개 조합 전부 `VALID`.** P1 구성상 성립, 불변식 I1–I5 전부 통과.
- 파일럿이므로 채택/기각이 아니라 **방향·ratio 점추정·분산 정보**를 산출했다.

**핵심 결과: 방향이 N에 따라 뒤집힌다.** N=8에서 AGENTIC utilization이 12.8 % 낮지만(예측대로), N=16에서는 0.9 % **높다**(예측과 반대). 사전 예측 2("N=16이 저하가 크다")는 **기각 방향**이다.

## 날짜

2026-08-19

## 목적

"agentic tool use가 bucket utilization을 체계적으로 저하시키는가"(Track A 핵심 RQ)의 첫 짝 비교. **파일럿 1블록**이며 확정 주장을 하지 않는다.

## 배경

관련 TASK:

- [TASK18](TASK18.md) — per-request 귀속 게이트 통과. 이 TASK의 선행 조건이었다.
- [TASK17](TASK17.md) — generator, bucket 전이 관측, 발견 5(재사용 성패가 도착 순서에 좌우).
- [TASK13](TASK13.md) — 사상표와 step 비용 모형.
- [TASK16](TASK16.md) — substrate descriptor, 층 태그.

선등록 문서: [PAIRED_PILOT_PREREG.md](PAIRED_PILOT_PREREG.md) (개정 1 포함)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `a261df703308adb14ec603a9fa05276560acdfff`
- 개정 1 commit: `838a42d0a85e1d74e48b4ea25bae7e558fd69fcd` (재측정 전)
- **Substrate: patched** (SHA256 `70942d16…`). 두 측정 모두 gate 통과
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)
- Server flag: `--enable-prefix-caching --enable-prompt-tokens-details`

## 수행 내용

1. 선등록 문서와 `utilization.py`(불변식 6개 fail-loud)를 **측정 전에** commit했다 (`a261df7`).
2. 순서 `(CONVENTIONAL/8, CONVENTIONAL/16, AGENTIC/16, AGENTIC/8)`대로 1차 측정을 수행했다.
3. **P1 위반을 발견**하고 원인을 CPython `randrange`의 rejection sampling으로 확정했다.
4. 짝 설계를 "한 plan에서 두 arm 파생"으로 바꾸고 **재측정 전에** 개정 선등록을 commit했다 (`838a42d`).
5. 같은 순서로 재측정하고 불변식과 관측치를 산출했다.

재compile, download, patch 변경, RSD 변경은 없었다.

## 변경된 파일

선등록 commit `a261df7`:

- `docs/research/PAIRED_PILOT_PREREG.md` (신규)
- `experiments/npu/analysis/utilization.py` (신규)

개정 commit `838a42d`:

- `docs/research/PAIRED_PILOT_PREREG.md` (개정 1 절 추가)
- `src/continuum/workload/agentic.py` (`zero_gaps` 신설)
- `experiments/npu/stage2/session_runner.py` (`--zero-gaps`)

이번 기록 commit: `docs/research/TASK19.md`, `docs/research/INDEX.md`

Raw artifact는 `.gitignore` 대상인 `results/npu/stage2/20260819-233000-paired-pilot/`(1차, `INVALID`)와 `.../20260819-233800-paired-pilot-v2/`(재측정)에 있다.

## 1차 측정 — `INVALID`

### 위반 내용

| N | `generation_tokens` turn 0 동일 | turn 1 동일 |
|---|---|---|
| 8 | ✓ | **✗** |
| 16 | ✓ | **✗** |

예: N=8 turn 1 생성 길이가 AGENTIC `[47, 251, 56, 243, 58, 73, 128, 150]`, CONVENTIONAL `[47, 60, 56, 243, 74, 73, 39, 99]`로 8개 중 4개가 달랐다.

### 원인 (source 확정)

`Distribution.draw`의 `uniform`은 `rng.randint`를 호출한다. CPython의 `randrange(0, 1)`은 `_randbelow(1)`에서 **rejection sampling 루프**를 돌아 소비 비트 수가 매번 다르다.

```python
def _randbelow_with_getrandbits(self, n):
    if not n: return 0
    k = n.bit_length()          # n=1 -> k=1
    r = getrandbits(k)
    while r >= n:               # r==1 이면 다시 뽑는다
        r = getrandbits(k)
    return r
```

seed 200개로 확인한 결과 `randint(0,0)` 이후의 stream이 `randint(1,5)` 이후와 일치한 것은 **157/200**뿐이었다. 선등록 당시 단일 seed로 확인한 것이 우연히 통과한 경우였다.

turn 0의 seg·gen은 gap 추출 **이전**에 뽑히므로 두 arm에서 동일했고, gap 추출 이후인 turn 1의 gen만 어긋났다. 이는 진단과 정확히 일치한다.

### 처리

선등록의 "P1 위반 시 `INVALID`"를 그대로 적용했다. 각 arm의 개별 측정은 I1–I5를 전부 통과했으므로 **짝이 아닌 관측**으로는 유효하며 참고로 남긴다.

| 조합 | utilization | 처리량 (tok/s) | turn 2 재사용 |
|---|---|---|---|
| CONVENTIONAL/8 | 0.8918 | 223.6 | 4/8 |
| AGENTIC/8 | 0.8718 | 151.4 | 4/8 |
| CONVENTIONAL/16 | 0.9689 | 269.2 | 0/16 |
| AGENTIC/16 | 0.9599 | 249.7 | 0/16 |

## 재측정 (개정 1) — 결과

### 조건 분리

- `requested_condition`: N ∈ {8, 16}, 2 turn, 첫 segment `uniform:800:1600`, 이후 segment 8, 생성 `uniform:32:256`, gap AGENTIC `uniform:1:5`초 / CONVENTIONAL 동일 plan에서 gap 제거, plan seed 20260823, block_id `n8`/`n16`(arm 간 동일), sampling seed 20260819, 조합마다 fresh server, 실행 순서 `(CONVENTIONAL/8, CONVENTIONAL/16, AGENTIC/16, AGENTIC/8)`.
- `observed_condition`: 전 요청 status 200. **P1 통과** — 두 arm의 plan이 `gap_after_s`를 제외한 전 항목에서 동일. 총 생성 token이 arm 간 정확히 같다(N=8 1,757 / N=16 4,609). `Σ(request_nums)`도 arm 간 정확히 같다(1,741 / 4,577). patch state 전 구간 `patched`.
- `condition_reached`: `YES`.

### 불변식

| 불변식 | 결과 |
|---|---|
| P1 (plan 동일) | **통과** (N=8, N=16 모두) |
| I1–I5 | **4개 조합 전부 통과**, `VALID` |

I5(`Σ(request_nums)` = `Σ(completion_tokens − 1)`)가 통과했다는 것은 `[BUCKET]` 로그와 client 기록이 **독립적으로 같은 총량을 말한다**는 뜻이다.

### 관측치 1 — 시간가중 bucket utilization (1차 판정치)

| N | CONVENTIONAL | AGENTIC | **ratio (A/C)** | 방향 |
|---|---|---|---|---|
| **8** | 0.9587 | **0.8362** | **0.8722** | AGENTIC 12.8 % 낮음 |
| **16** | 0.9593 | **0.9681** | **1.0091** | AGENTIC 0.9 % **높음** |

**N=8에서는 예측대로 저하가 나타나고 N=16에서는 나타나지 않는다.**

같은 총 decode 작업량(`Σ(request_nums)` 동일)을 AGENTIC이 **더 많은 step에 나눠** 처리한다.

| N | arm | decode step 수 | `Σ(request_nums)` |
|---|---|---|---|
| 8 | CONVENTIONAL | 375 | 1,741 |
| 8 | AGENTIC | **598** | 1,741 |
| 16 | CONVENTIONAL | 643 | 4,577 |
| 16 | AGENTIC | **730** | 4,577 |

N=8의 `(request_nums → bucket)` 분포가 이를 직접 보여준다.

| 쌍 | CONVENTIONAL | AGENTIC |
|---|---|---|
| 1→1 | 94 | **242** |
| 2→2 | 67 | 66 |
| 3→4 | 20 | 67 |
| 4→4 | 11 | 86 |
| 5→8 | 1 | **82** |
| 6→8 | 6 | 11 |
| 7→8 | 40 | 6 |
| 8→8 | **136** | 38 |

CONVENTIONAL은 `8→8`(패딩 0)에 136 step이 몰려 있는 반면 AGENTIC은 `1→1`에 242 step, `5→8`(패딩 3)에 82 step이 있다. **gap이 batch를 얇게 만들고 얇아진 batch가 큰 bucket에 실린다.**

### 관측치 2 — 처리량

| N | CONVENTIONAL | AGENTIC | ratio |
|---|---|---|---|
| 8 | 214.7 tok/s | 150.8 tok/s | 0.7024 |
| 16 | 271.6 tok/s | 260.8 tok/s | 0.9601 |

**이 값은 utilization 저하의 증거가 아니다.** gap 자체가 경과시간에 들어가므로 AGENTIC이 낮은 것은 자명하다(선등록 예측 4에 명시). N=8의 처리량 비(0.70)가 utilization 비(0.87)보다 훨씬 낮은 것은 gap 시간이 지배적이기 때문이다.

### 관측치 3 — 층 2 재사용률 (turn 2)

| N | CONVENTIONAL | AGENTIC |
|---|---|---|
| 8 | **1/8** | **3/8** |
| 16 | 0/16 | 0/16 |

**AGENTIC이 CONVENTIONAL보다 재사용률이 높았다.** 사전 예측 3과 반대다.

N=16에서는 양쪽 모두 0이다. 16 세션이 outer slot 8개를 두고 경쟁하므로 어느 쪽도 살아남지 못한다.

### 관측치 4 — mean ITL (보조)

| N | CONVENTIONAL | AGENTIC |
|---|---|---|
| 8 | 0.02391 s | 0.01779 s |
| 16 | 0.02517 s | 0.02436 s |

**p50/p99는 산출하지 않았다** (선등록대로). non-streaming 요청이라 client 측 raw 표본이 없다.

### 사전 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| 1 | AGENTIC utilization < CONVENTIONAL | **부분 적중.** N=8 ✓(0.87), N=16 ✗(1.01) |
| 2 | N=16이 N=8보다 저하가 크다 | **✗ 기각 방향.** N=16은 저하가 없다 |
| 3 | AGENTIC 재사용률이 더 낮다 | **✗** N=8에서 3/8 vs 1/8로 더 높다 |
| 4 | AGENTIC 처리량이 더 낮다 | ✓ (자명, 증거로 쓰지 않음) |
| 5 | 두 arm의 총 생성 token 동일 | ✓ 정확히 일치 |

5개 중 2개만 적중했다. **예측이 많이 빗나간 것이 이번 파일럿의 소득이다** — 기전에 대한 이해가 부족했음이 드러났다.

### 판정 산출

- **(a) 방향**: N=8에서만 예측 방향과 일치. N=16에서는 반대. **방향이 N에 의존한다.**
- **(b) ratio 점추정**: N=8 **0.872**, N=16 **1.009**.
- **(c) 분산 정보**: **1블록이라 arm 내 분산을 추정할 수 없다.** 1차·재측정의 CONVENTIONAL/8 utilization이 0.8918 vs 0.9587로 **0.067 차이**가 났는데, 두 run은 plan이 달랐으므로(1차의 짝 깨짐) 이 차이를 재현 분산으로 읽을 수 없다. **본 실험에서 arm 내 반복이 반드시 필요하다.**

## 핵심 발견 (층 태그)

1. **`class`** — **queue 깊이가 agentic 페널티를 가린다.** N=8(= `max_num_seqs`)에서는 gap 중 세션이 빠진 자리를 채울 것이 없어 batch가 얇아지지만, N=16에서는 대기 중인 요청이 그 자리를 메운다. 유한한 batch slot과 대기 큐를 가진 어느 substrate에서나 같은 상쇄가 기대된다. **"agentic이 utilization을 낮춘다"는 명제는 부하 수준을 명시하지 않으면 성립하지 않는다.**
2. **`stack`** — **N=8에서 utilization 비는 0.872다.** 같은 작업량을 598 step(AGENTIC) vs 375 step(CONVENTIONAL)에 나눠 처리했고, `1→1` step이 94 → 242로 늘고 `8→8`이 136 → 38로 줄었다.
3. **`stack`** — **AGENTIC의 재사용률이 오히려 높았다** (3/8 vs 1/8). gap이 재개 도착을 흩뜨려 outer slot 경쟁을 완화한다. [TASK17](TASK17.md) 발견 5·[TASK18](TASK18.md) 발견 5와 방향이 일치하며 **세 번째 데이터점**이다.
4. **`universal`** — **짝 설계는 난수 소비량이 아니라 구성으로 보장해야 한다.** 두 arm을 각각 생성하면 분포가 조금만 달라도 stream이 어긋난다. 한 plan에서 파생하면 그 가능성이 사라진다.
5. **`universal`** — **불변식이 설계 결함을 잡았다.** P1이 없었다면 짝이 깨진 채로 12.8 %라는 수치를 보고했을 것이다. 1차·재측정의 N=8 utilization이 0.8918 vs 0.8362로 달랐으므로 결론의 크기가 실제로 바뀌었을 것이다.
6. **`stack`** — **N=16에서는 재사용이 양쪽 다 0이다.** 세션 수가 outer slot 수의 2배면 gap 유무와 무관하게 prefix가 살아남지 못한다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(hypothesis)** 발견 1의 기전은 "대기 큐가 gap을 흡수한다"이다. `max_num_seqs = 8`이므로 N=16이면 항상 8개가 running이고 gap에 들어간 세션의 자리를 대기 세션이 즉시 채운다. 이 가설이 맞다면 **저하가 나타나는 조건은 `N ≲ max_num_seqs`** 이고, 그 위에서는 utilization이 아니라 **지연**에 비용이 나타날 것이다. 이번 파일럿은 N 두 점만 봤으므로 경계를 특정할 수 없다.
- **(해석)** 발견 3은 정책적으로 역설적이다. gap이 재사용에 **유리**하게 작용했다 — 도착을 흩뜨려 FIFO pointer가 한 번에 여러 slot을 쓸어가지 못하게 하기 때문이다. 다만 N=8에서 1/8 vs 3/8은 표본이 매우 작다.
- **(해석)** 관측치 2의 처리량 비(0.70)와 utilization 비(0.87)의 차이는 gap이 순수한 유휴 시간이라는 뜻이다. **utilization 저하가 시간으로 전이되는 몫을 분리하려면 gap 시간을 제외한 비교가 필요하다.** 이번 설계로는 분리할 수 없다.
- **(해석)** mean ITL이 AGENTIC에서 오히려 낮은 것(N=8: 0.0178 vs 0.0239)은 batch가 얇을 때 step이 싸기 때문으로 보인다([TASK13](TASK13.md)의 bucket별 step 비용). 즉 **ITL이 좋아 보이는 것이 utilization이 나쁘다는 신호**일 수 있다. 보조 지표로만 기록한다.

## 확인되지 않은 사항

- 저하가 사라지는 N의 경계 (`UNKNOWN`). N=8, 16 두 점만 봤다.
- arm 내 분산 (`UNKNOWN`). 1블록이다.
- gap 시간을 제외한 utilization→시간 전이 (`UNKNOWN`).
- 재사용률 역전의 재현성 (`UNKNOWN`). 1/8 vs 3/8은 표본이 작다.
- gap 분포(중앙값·spread)의 영향 (`UNKNOWN`). `uniform:1:5` 하나만 썼다.
- 1차 측정과 재측정의 CONVENTIONAL/8 차이(0.8918 vs 0.9587)가 plan 차이 때문인지 run 간 분산 때문인지 (`UNKNOWN`).
- ITL p50/p99 (`UNKNOWN`, non-streaming이라 raw 표본 없음).

## 실패 / 무효 시도

1. **1차 측정의 짝 비교가 `INVALID`였다.** P1 위반. 원인은 `Distribution`에서 `fixed`가 rng를 소비하지 않는 것을 피하려고 `uniform:0:0`을 쓴 것인데, 그 자체가 가변 소비를 하는 함수였다. **선등록 기준을 완화하지 않고 무효 처리한 뒤 설계를 고쳐 재등록·재측정했다.**
2. 선등록 당시 `uniform:0:0`의 소비량 동일성을 **단일 seed로만** 확인한 것이 실수였다. 200 seed로 확인했다면 157/200에서 걸렸을 것이다.
3. 무효로 판정한 측정 외에는 없다. 두 측정 모두 전 요청 status 200.
4. Device·RSD·package·patch 변경 없음. server lifecycle 8회(1차 4 + 재측정 4), 전부 종료 후 device memory `0.0B` 복귀·context 소멸.

## 연구 원칙에 미치는 영향

- **짝 설계는 구성으로 보장한다.** 두 arm을 각각 생성하고 "같을 것"이라 가정하지 않는다. 한 plan에서 파생한다.
- **난수 소비량의 동일성을 단일 seed로 확인하지 않는다.** 확률적 소비를 하는 함수가 있다.
- **불변식은 결론을 바꿀 수 있는 지점에 건다.** P1이 없었다면 크기가 다른 결론을 보고했을 것이다.
- **파일럿에서 예측이 많이 빗나가는 것은 성공이다.** 5개 중 2개만 맞았고, 빗나간 방식(N 의존, 재사용 역전)이 본 실험의 설계를 바꾼다.
- **1블록으로 분산을 말하지 않는다.** 두 run의 차이를 재현 분산으로 읽을 수 없음을 명시했다.

## 다음 작업 — 본 실험 격자 제안

### 격자 축

| 축 | 값 | 근거 |
|---|---|---|
| **arm** | AGENTIC / CONVENTIONAL | 짝, `zero_gaps`로 파생 |
| **N (부하)** | **4, 6, 8, 10, 12, 16** | 발견 1. 저하가 사라지는 경계가 `max_num_seqs = 8` 부근으로 추정되므로 그 주변을 촘촘히 |
| **블록 반복** | **arm×N 조합당 최소 3블록** | (c)에서 분산을 추정할 수 없었다 |

### 고정할 것

model artifact, `max_seq_len`, `decoder_batch_sizes`, prompt 길이 분포(`uniform:800:1600`), 생성 길이 분포(`uniform:32:256`), sampling seed, server flag, 조합마다 fresh server, patch 상태.

### 움직일 것

arm, N, 블록 seed.

### 별도 축으로 뺄 것 (본 실험에 넣지 말 것)

- **gap 분포**: 재사용률에 영향을 준다는 데이터점이 셋이므로 독립 실험으로 다룬다.
- **gap 시간 제외 비교**: 별도 설계가 필요하다.

### 선행 수정

1. ITL p50/p99가 필요하면 runner를 streaming으로 바꾼다. 필요 없으면 선등록에서 제외한다.
2. `utilization.py`의 불변식은 그대로 쓴다. I5가 로그와 client 기록의 독립 교차 검증으로 작동했다.

사용자 지시 없이 다음 TASK를 자동 시작하지 않는다.

## 재현 정보

- 선등록 commit: `a261df703308adb14ec603a9fa05276560acdfff`
- **1차 측정 시작: 2026-08-19 23:30:11 KST** (선등록 23:29:51 KST보다 20초 뒤)
- 개정 1 commit: `838a42d0a85e1d74e48b4ea25bae7e558fd69fcd` (23:37:40 KST)
- **재측정 시작: 2026-08-19 23:37:53 KST** (개정 commit보다 13초 뒤)
- Base commit (재측정 중 HEAD): `838a42d0a85e1d74e48b4ea25bae7e558fd69fcd`, dirty = untracked `.idea/` 및 gitignored `results/`, `models/`
- **Patch state: `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`**
- 실행 순서: `(CONVENTIONAL/8, CONVENTIONAL/16, AGENTIC/16, AGENTIC/8)` — `balanced_arm_orders([...], rounds=1, base_seed=20260823, block_id="task19-pilot")`
- plan seed: `base_seed=20260823`, `block_id=n8`/`n16` (arm 간 동일). CONVENTIONAL은 `--zero-gaps`
- Raw artifact:
  - 1차 (`INVALID`): `results/npu/stage2/20260819-233000-paired-pilot/`
  - 재측정: `results/npu/stage2/20260819-233800-paired-pilot-v2/`
  - 각각 `measurement-{start,end}.txt`, `patch-state.txt`, `server-<ARM>.n<N>.log`, `probe/requests.<ARM>.n<N>.jsonl`, `probe/meta.<ARM>.n<N>.json`, `metrics-<ARM>.n<N>.prom`, `util.<ARM>.n<N>.json`, `rbln-smi-{before,final}.txt`
- 실행 script: `experiments/npu/stage2/session_runner.py`, `experiments/npu/analysis/utilization.py`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(**patched**), `optimum-rbln 0.11.1`, `torch 2.11.0+cpu`
- Host: `atom-max8`, device `rbln0`–`rbln3`
