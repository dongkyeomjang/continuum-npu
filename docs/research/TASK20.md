# TASK20 — N/slots sweep 본 측정

## 상태

DONE

## 판정

44 조합 전부 `VALID`(P1·I1–I5 전건 통과, `INVALID` 0건). 선등록 판정 규칙 적용 결과:

| N | N/slots | pooled ratio | 판정 |
|---|---|---|---|
| 4 | 0.50 | 1.0414 | `INCONCLUSIVE` |
| 6 | 0.75 | 1.1504 | `INCONCLUSIVE` |
| 8 | 1.00 | 0.9253 | `INCONCLUSIVE` |
| **10** | 1.25 | **0.9103** | **저하 존재** |
| **12** | 1.50 | **0.9192** | **저하 존재** |
| 16 | 2.00 | 0.9944 | `INCONCLUSIVE` |

**사전 예측 (a)와 (c)가 모두 빗나갔다.** 저하는 N ≤ 8이 아니라 **N = 10–12**에서 확정됐고, N = 6에서는 **AGENTIC utilization이 15 % 더 높다.**

## 날짜

2026-08-20

## 목적

agentic tool gap의 utilization 저하와 층 2 재사용률이 oversubscription 비율 N/slots의 함수로 어떻게 변하는지 측정한다.

## 배경

관련 TASK:

- [TASK19](TASK19.md) — 파일럿. N=8 ratio 0.872, N=16 ratio 1.009로 방향이 뒤집혔고 이 격자를 제안했다.
- [TASK18](TASK18.md) — per-request 귀속 채널.
- [TASK16](TASK16.md) — substrate descriptor (관측치 3의 모델).
- [TASK13](TASK13.md) — 비용 모델.

선등록 문서: [NSLOTS_SWEEP_PREREG.md](NSLOTS_SWEEP_PREREG.md)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `f9cc1069e3975a632f6b35fac470cf8824007534`
- **Substrate: patched** (SHA256 `70942d16…`). 측정 전 gate 통과
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)
- Device: 32 visible ID 전부 idle, port 8000 비어 있음

## 수행 내용

1. 선등록 문서와 `run_sweep.sh`(조합 단위 완료 표식으로 중단·재개 가능)를 **측정 전에** commit했다 (`f9cc106`).
2. Patch gate 통과 후 44 조합을 블록 순서표대로 실행했다.
3. 1회차 실행이 도구 호출 상한(10분)에 걸려 중단됐다. 잔존 server를 PID 특정해 정리하고, 완료 표식이 있는 7 조합을 건너뛰며 background로 재개했다 (아래 "실패 / 무효 시도").
4. 조합마다 `utilization.py --cost-model`을 실행해 불변식과 관측치를 산출했다.

재compile, download, patch 변경, RSD 변경은 없었다.

## 변경된 파일

선등록 commit `f9cc106`: `docs/research/NSLOTS_SWEEP_PREREG.md`, `experiments/npu/stage2/run_sweep.sh`, `experiments/npu/stage2/session_runner.py`(`--sync-gaps`), `experiments/npu/analysis/utilization.py`(`--cost-model`), `src/continuum/workload/agentic.py`(`set_uniform_gaps`).

이번 기록 commit: `docs/research/TASK20.md`, `docs/research/INDEX.md`.

Raw artifact는 `.gitignore` 대상인 `results/npu/stage2/20260820-165200-nslots-sweep/`에 있다.

## 결과

### 조건 분리

- `requested_condition`: N ∈ {4,6,8,10,12,16} × 2 arm × 3블록(+N∈{8,16} 2블록), 2 turn, 첫 segment `uniform:800:1600`, 이후 8, 생성 `uniform:32:256`, gap AGENTIC `uniform:1:5` / CONVENTIONAL 동일 plan에서 제거, plan seed 20260830, block_id `n<N>b<B>`, sampling seed 20260819, 조합마다 fresh server.
- `observed_condition`: 전 요청 status 200. **P1 위반 0건** — 전 (N, block)에서 두 arm plan이 gap 외 동일. 불변식 I1–I5 전 조합 통과. patch state 전 구간 `patched`.
- `condition_reached`: `YES`.

### 관측치 1 — utilization ratio (1차 판정치)

블록별 ratio = `util(AGENTIC) / util(CONVENTIONAL)`.

| N | N/slots | b0 | b1 | b2 | b3 | b4 | **pooled** | 판정 |
|---|---|---|---|---|---|---|---|---|
| 4 | 0.50 | 0.9436 | 1.0895 | 1.0712 | — | — | 1.0414 | `INCONCLUSIVE` (방향 혼재) |
| 6 | 0.75 | 1.1726 | 1.1696 | 1.1080 | — | — | **1.1504** | `INCONCLUSIVE` (전 블록 밴드 **위**) |
| 8 | 1.00 | 0.8489 | 0.8966 | 0.9270 | 0.9580 | 1.0229 | 0.9253 | `INCONCLUSIVE` (b4가 1 초과) |
| **10** | 1.25 | 0.9072 | 0.9096 | 0.9144 | — | — | **0.9103** | **저하 존재** |
| **12** | 1.50 | 0.9020 | 0.8979 | 0.9612 | — | — | **0.9192** | **저하 존재** |
| 16 | 2.00 | 0.9603 | 0.9897 | 1.0053 | 1.0241 | 0.9889 | 0.9944 | `INCONCLUSIVE` (방향 혼재) |

`INCONCLUSIVE`의 성격이 N마다 다르다.

- **N=6은 방향이 일관되게 반대다.** 3블록 전부 1.11–1.17로 밴드 위에 있다. 선등록 규칙에 "저하 없음"은 밴드 **안**을 요구하므로 `INCONCLUSIVE`로 분류되지만, 이는 "효과 없음"이 아니라 **반대 방향의 일관된 효과**다.
- **N=8은 5블록 중 4블록이 1 미만**(0.849–0.958)이고 pooled 0.9253이지만 b4가 1.0229라 "전 블록 방향 일치"를 만족하지 못했다.
- N=4·16은 방향이 실제로 혼재한다.

**선등록 규칙을 사후에 완화하지 않았다.** N=8을 "저하 존재"로 올리지 않는다.

### N=6 역전의 기전 — bucket 격자와의 정합

`(request_nums → bucket)` 분포가 원인을 직접 보여준다 (N=6, block 0).

| 쌍 | padding | CONVENTIONAL | AGENTIC |
|---|---|---|---|
| 1→1 | 0 | 65 | **252** |
| 2→2 | 0 | 24 | 149 |
| 3→4 | 1 | 19 | 44 |
| 4→4 | 0 | 42 | **161** |
| 5→8 | **3** | 80 | 18 |
| 6→8 | **2** | **204** | 91 |
| utilization | | 0.7463 | **0.8751** |

**N=6은 bucket 격자와 정합하지 않는 크기다.** 6개가 동시에 돌면 bucket 8에 실려 slot 2개가 낭비된다(25 %). CONVENTIONAL은 434 step 중 284 step(65 %)을 `5→8`·`6→8`에서 보낸다. AGENTIC은 gap이 batch를 1–4로 얇게 만들어 `1→1`·`2→2`·`4→4`처럼 **padding 0인 칸**에 들어간다.

즉 **N이 compiled bucket 사이에 끼는 값일 때, gap이 batch를 쪼개 오히려 utilization을 올린다.**

### 관측치 2 — 층 2 재사용률 (블록 합산)

| N | AGENTIC | CONVENTIONAL |
|---|---|---|
| 4 | **12/12 (100 %)** | **12/12 (100 %)** |
| 6 | 13/18 (72 %) | **18/18 (100 %)** |
| 8 | 16/40 (40 %) | 16/40 (40 %) |
| 10 | **7/30 (23 %)** | 3/30 (10 %) |
| 12 | 0/36 | 0/36 |
| 16 | 0/80 | 0/80 |

**N 증가에 단조 감소하고 N ≥ 12에서 0이다** (예측 b 적중).

**arm 간 비교는 N에 따라 뒤집힌다**: N=6에서 AGENTIC이 낮고(72 % vs 100 %), N=8에서 같고, N=10에서 AGENTIC이 높다(23 % vs 10 %). [TASK19](TASK19.md)에서 N=8 기준 3/8 vs 1/8이던 관측이 이번 N=8에서는 16/40 vs 16/40으로 **동률**이다.

### 관측치 3 — 비용 모델 전이 검증

`predicted_itl_sum / measured_itl_sum` (블록 평균):

| N | AGENTIC | CONVENTIONAL |
|---|---|---|
| 4 | 0.8553 | 0.8118 |
| 6 | 0.7911 | 0.7839 |
| 8 | 0.7223 | 0.6499 |
| 10 | 0.6610 | 0.5931 |
| 12 | 0.5986 | 0.5698 |
| 16 | 0.5693 | 0.5645 |

**[TASK13](TASK13.md)의 정상 상태 비용 모델이 다중 세션 workload로 전이되지 않는다.** 예측이 실측보다 항상 작고, N이 커질수록 비가 0.86 → 0.57로 단조 감소한다. 예측 d(같은 자릿수)는 자릿수만 보면 맞지만 **체계적 편향이 있고 N에 의존한다.**

### 사전 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| a | ratio가 N ≤ 8에서 1 미만, N ≥ 12에서 동치 밴드 안 | **✗** N=6은 1 초과, N=12는 저하 존재 |
| b | 재사용률이 N 증가에 단조 감소, N ≥ 12에서 0 부근 | ✓ |
| c | 저하 최대점이 N = 8 근방 | **✗** pooled 최소는 N = 10 (0.9103) |
| d | predicted/measured가 전 조합에서 같은 자릿수 | ✓ (다만 체계적 편향) |
| e | AGENTIC 재개 도착이 더 흩어진다 | 기록됨 (판정 대상 아님) |

**5개 중 2개만 적중했다.**

## 핵심 발견 (층 태그)

1. **`class`** — **agentic gap의 utilization 효과는 부호가 바뀐다.** N이 compiled bucket 사이에 끼면(N=6 → bucket 8) gap이 batch를 padding 0인 크기로 쪼개 utilization을 **올리고**(ratio 1.15), N이 bucket과 맞거나 초과하면 내린다. 고정 bucket 격자를 쓰는 어느 substrate에서나 "N과 bucket 격자의 정합"이 부호를 결정할 것으로 본다 — 기전이 격자 구조에서 나오기 때문이다.
2. **`stack`** — **저하가 확정된 구간은 N = 10–12 (N/slots 1.25–1.5)** 이며 pooled ratio 0.910–0.919다. N=8은 5블록 중 4블록이 저하 방향이었으나 선등록 기준을 만족하지 못했다.
3. **`stack`** — **N ≥ 12에서 층 2 재사용이 arm 무관하게 0이다.** 세션 수가 outer slot의 1.5배를 넘으면 gap 유무와 관계없이 prefix가 살아남지 못한다.
4. **`stack`** — **재사용률의 arm 간 방향이 N에 따라 뒤집힌다** (N=6 AGENTIC 낮음, N=8 동률, N=10 AGENTIC 높음). [TASK17](TASK17.md)–[TASK19](TASK19.md)에서 "gap이 재사용에 유리하다"고 본 관측은 **N에 조건부**였다.
5. **`stack`** — **[TASK13](TASK13.md) 비용 모델이 다중 세션으로 전이되지 않는다.** 예측/실측 비가 N에 따라 0.86 → 0.57로 단조 감소한다. 정상 상태(모든 요청 동일 길이, 단일 batch 크기)에서 잰 상수를 전이 workload에 그대로 쓰면 **비용을 최대 43 % 과소평가**한다.
6. **`universal`** — **"전 블록 방향 일치 + pooled 밴드 밖"이라는 이중 조건이 실제로 작동했다.** N=8은 pooled로는 저하지만 5블록 중 1블록이 반대 방향이라 채택되지 않았다. 조건이 하나였다면 다른 결론이 나왔을 것이다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(hypothesis, 발견 5의 기전)** 예측/실측 비가 N에 따라 떨어지는 것은 **prefill이 배타적으로 실행되기 때문**으로 보인다. `optimum_scheduler.py:300-304`의 주석이 명시한다:

  > "If a request is in the prefill phase, it is given priority and processed exclusively (only one at a time)."

  세션이 많을수록 다른 세션의 prefill이 더 자주 끼어들고, 그 시간이 **running 요청들의 inter-token latency에 그대로 실린다.** `predicted_itl_sum`은 decode step만 세므로 그만큼 작아진다. 이 가설이 맞다면 비용 모델에 **prefill 배타 구간**을 항으로 넣어야 한다. 다만 prefill 시간을 ITL에서 분리 계측하지는 않았다.

- **(해석)** 발견 1은 "agentic이 utilization을 낮춘다"는 명제를 다시 좁힌다. [TASK19](TASK19.md)에서 "부하 수준에 의존한다"로 좁혔는데, 이번에 **"N과 bucket 격자의 정합에 의존하며 부호까지 바뀐다"** 로 더 좁혀졌다. N=6처럼 격자와 어긋나는 부하에서는 gap이 이득이다.

- **(해석)** 발견 3·4를 합치면 재사용의 그림은 이렇다. N ≤ slots에서는 재사용이 거의 다 되고(N=4 100 %), slot 경계 부근에서 gap 분산이 유리하게 작용하며(N=10), slot의 1.5배를 넘으면 무엇을 해도 안 된다(N ≥ 12). **정책이 개입할 여지가 있는 구간은 좁다.**

- **(해석)** N=8에서 [TASK19](TASK19.md)는 ratio 0.872, 이번 5블록은 0.849–1.023(pooled 0.925)이었다. **블록 간 변동이 파일럿 1블록의 점추정보다 크다.** [TASK19](TASK19.md)가 "1블록으로 분산을 말하지 않는다"고 한 것이 옳았다.

## 확인되지 않은 사항

- N=8의 판정 (`INCONCLUSIVE`). 블록을 늘리면 갈릴 수 있으나 **이 TASK에서 추가하지 않는다**(선등록).
- N=6 역전이 다른 bucket 격자에서도 재현되는지 (`UNKNOWN`). 재compile이 필요하다.
- 발견 5의 기전 확인 (`UNKNOWN`). prefill 배타 구간을 ITL에서 분리 계측하지 않았다.
- N=4·16의 방향 혼재가 효과 부재인지 검정력 부족인지 (`UNKNOWN`).
- 재사용률 arm 차이의 통계적 안정성 (`UNKNOWN`). N=10의 7/30 vs 3/30은 표본이 작다.
- bucket 격자와 N의 정합을 나타내는 지표(예: `padding_slots(N)/N`)가 ratio를 설명하는지 (`UNKNOWN`, 관측점 6개로는 모형을 세울 수 없다).

## 실패 / 무효 시도

1. **1회차 실행이 도구 호출 상한(10분)에 걸려 중단됐다.** 44 조합 × 약 100초 ≈ 75분이 필요한데 한 번의 foreground 호출로 시도한 것이 설계 실수였다. 중단 시점에 server 1개가 살아 있어 PID를 특정해 정리했고, device memory가 `0.0B`로 복귀함을 확인했다.
   - `run_sweep.sh`의 완료 표식 덕분에 완료된 7 조합을 건너뛰고 background로 재개할 수 있었다. **미완 조합을 추정으로 채우지 않았다.**
   - 중단 시점에 진행 중이던 `CONVENTIONAL.n10.b0`은 표식이 없어 재실행됐다.
2. `INVALID` 조합은 **0건**이다. 44/44가 P1·I1–I5를 통과했다.
3. Device·RSD·package·patch 변경 없음. server lifecycle 45회(중단분 1 포함), 전부 종료 후 device memory `0.0B` 복귀.

## 연구 원칙에 미치는 영향

- **긴 sweep은 조합 단위로 완료 표식을 남긴다.** 중단이 발생해도 완료분을 잃지 않고, 미완을 추정으로 채우려는 유혹이 생기지 않는다.
- **"방향 일치 + pooled 밴드"의 이중 조건을 유지한다.** 한 블록의 반대 방향이 결론을 뒤집을 수 있음을 N=8이 보여줬다.
- **`INCONCLUSIVE`의 성격을 구분해 기록한다.** "방향 혼재"(N=4, 16)와 "일관되게 반대 방향"(N=6)은 전혀 다른 상태인데 같은 라벨을 받는다. 라벨만 보고 넘어가면 N=6의 발견을 놓친다.
- **정상 상태에서 잰 비용 모델을 전이 workload에 쓰기 전에 전이 검증을 한다.** 이번에 최대 43 % 과소평가가 드러났다.
- **파일럿 1블록의 점추정을 본 실험이 재현할 것이라 기대하지 않는다.**

## 다음 작업

1. **비용 모델에 prefill 배타 항 추가** — 발견 5의 기전 가설을 검증하려면 prefill 구간을 ITL에서 분리해야 한다. 관측 채널 설계가 선행 과제다.
2. **N=8 블록 추가** — 별도 TASK. 이 TASK에서 추가하지 않았다.
3. **bucket 격자 정합 축** — N=6 역전이 격자 의존이라면 `decoder_batch_sizes`를 바꾼 재compile이 필요하다. 승인 대상이다.
4. gap 분산 축은 같은 batch의 다음 작업이 다룬다.

사용자 지시 없이 다음 TASK를 자동 시작하지 않는다.

## 재현 정보

- 선등록 commit: `f9cc1069e3975a632f6b35fac470cf8824007534`
- **측정 시작 시각: 2026-08-20 16:51:32 KST.** 선등록 commit 시각은 16:51:16 KST이므로 **선등록이 측정보다 16초 앞선다.**
- 측정 종료 시각: `<RUN>/measurement-end.txt`
- Base commit (측정 중 HEAD): `f9cc1069e3975a632f6b35fac470cf8824007534`
- **Patch state: `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`**
- plan seed: `base_seed=20260830`, `block_id=n<N>b<B>` (arm 간 동일). CONVENTIONAL은 `--zero-gaps`
- 블록별 arm 순서: `balanced_arm_orders(["AGENTIC","CONVENTIONAL"], rounds=5, base_seed=20260830, block_id="task20")` → b0 A→C, b1 C→A, b2 A→C, b3 C→A, b4 A→C
- Raw artifact: `results/npu/stage2/20260820-165200-nslots-sweep/`
  - `measurement-{start,end}.txt`, `patch-state.txt`, `sweep.log`, `done.<TAG>` 44개
  - `server-<ARM>.n<N>.b<B>.log`, `probe/requests.<TAG>.jsonl`, `probe/meta.<TAG>.json`
  - `metrics-<TAG>.prom`, `util.<TAG>.json`
  - `rbln-smi-{before,final}.txt`
- 실행 script: `experiments/npu/stage2/{run_sweep.sh,session_runner.py}`, `experiments/npu/analysis/utilization.py`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(**patched**), `optimum-rbln 0.11.1`, `torch 2.11.0+cpu`
- Host: `atom-max8`, device `rbln0`–`rbln3`
