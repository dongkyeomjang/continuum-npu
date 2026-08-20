# TASK21 — gap 분산 → 재사용 메커니즘 검증

## 상태

DONE

## 판정

**1차 판정: `INCONCLUSIVE`.** 3블록 중 2블록이 `DISPERSED > SYNC`(4/8 vs 2/8)이고 1블록이 **동률**(3/8 vs 3/8)이다. 선등록은 "3블록 **전부** `DISPERSED > SYNC`"를 H 지지의 조건으로 두었고 동률 블록은 이를 만족하지 못하므로 `INCONCLUSIVE`다. **반대 방향 블록은 0개다.**

**부가 판정(도착 순서 서명): 6개 arm-block 중 5개에서 확인**됐다. DISPERSED는 3/3, SYNC는 2/3이다.

**판정 기준을 사후에 완화하지 않았다.**

## 날짜

2026-08-20

## 목적

층 2 재사용률을 좌우하는 것이 gap의 **존재·길이**인가 **재개 도착의 분산**인가를 분산만을 조작 변수로 두고 검증한다.

## 배경

기존 데이터점 3개는 모두 "분산이 있으면 재사용이 많다" 방향이었으나 prompt 구성이 함께 달라 단독 비교가 불가능했다.

| TASK | gap | 재사용률 |
|---|---|---|
| [TASK17](TASK17.md) | `uniform:1:6` (분산) | 4/8 |
| [TASK18](TASK18.md) | `fixed:2` (동일) | 2/8 |
| [TASK19](TASK19.md) | `uniform:1:5` (분산) | 3/8 |

[TASK20](TASK20.md)은 여기에 조건을 더했다 — arm 간 재사용률 방향이 **N에 따라 뒤집힌다**(N=6 AGENTIC 낮음, N=8 동률, N=10 AGENTIC 높음). 이번 실험은 N=8 고정이다.

선등록 문서: [GAP_DISPERSION_PREREG.md](GAP_DISPERSION_PREREG.md)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `12fbd1cefbc42b18354152f5db7461446d39ea02`
- runner seed 분리 commit: `533aa316123da22b0abd6977457df977244b1f57` (측정 전)
- **Substrate: patched** (SHA256 `70942d16…`). 측정 전 gate 통과
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)

## 수행 내용

1. 선등록 문서를 commit했다 (`12fbd1c`).
2. `run_sweep.sh`가 [TASK20](TASK20.md)의 plan seed를 하드코딩하고 있어 이 실험의 선등록 값(`base_seed=20260831`, `block_id=g<B>`)을 쓸 수 없었다. **측정 시작 전에** 환경변수(`SWEEP_BASE_SEED`, `SWEEP_BLOCK_PREFIX`)로 분리하고 선등록의 실행 절차를 실제 호출 형태로 구체화해 commit했다 (`533aa31`).
3. Patch gate 통과 후 6 조합(3블록 × 2 arm)을 블록 순서표대로 실행했다.
4. 불변식·관측치를 산출했다.

재compile, download, patch 변경, RSD 변경은 없었다.

## 변경된 파일

- 선등록 `12fbd1c`: `docs/research/GAP_DISPERSION_PREREG.md`
- 측정 전 `533aa31`: `experiments/npu/stage2/run_sweep.sh`, `docs/research/GAP_DISPERSION_PREREG.md`
- 이번 기록: `docs/research/TASK21.md`, `docs/research/INDEX.md`

Raw artifact는 `.gitignore` 대상인 `results/npu/stage2/20260820-180000-gap-dispersion/`에 있다.

## 결과

### 조건 분리

- `requested_condition`: N=8 고정, 2 turn, 첫 segment `uniform:800:1600`, 이후 8, 생성 `uniform:32:256`, gap `uniform:1:5`를 한 번 뽑아 DISPERSED는 그대로·SYNC는 전부 평균으로 치환, 3블록, plan seed 20260831, `block_id=g<B>`(arm 간 동일), 조합마다 fresh server.
- `observed_condition`: 전 요청 status 200. **P1·P2 전 블록 통과.** 총 gap 시간이 arm 간 정확히 같다(b0 19.0, b1 20.0, b2 24.0). I1–I5 전 조합 통과, `INVALID` 0건. patch state `patched`.
- `condition_reached`: `YES`.

### 불변식 — 조작 변수가 분산 하나임의 직접 증거

| block | P1 | P2 | 총 gap | SYNC gaps | DISPERSED gaps |
|---|---|---|---|---|---|
| 0 | ✓ | ✓ | 19.0 s | 2.375 × 8 | 3, 1, 1, 3, 4, 3, 3, 1 |
| 1 | ✓ | ✓ | 20.0 s | 2.5 × 8 | 4, 3, 1, 1, 2, 4, 2, 3 |
| 2 | ✓ | ✓ | 24.0 s | 3.0 × 8 | 1, 4, 4, 4, 3, 1, 4, 3 |

두 arm은 **총 gap 시간이 소수점까지 같고 분산만 다르다.**

### 관측치 1 — 층 2 재사용률 (1차 판정치)

| block | SYNC | DISPERSED | 방향 |
|---|---|---|---|
| 0 | **2/8** | **4/8** | `D > S` |
| 1 | 3/8 | 3/8 | **동률** |
| 2 | **2/8** | **4/8** | `D > S` |
| 합계 | **7/24 (29 %)** | **11/24 (46 %)** | — |

**`S > D`인 블록은 없다.** 선등록의 "전부" 조건을 b1의 동률이 막았다.

SYNC의 재사용률 7/24는 [TASK18](TASK18.md)의 `fixed:2` gap에서 관측된 2/8과 같은 수준이다 (예측 4 적중).

### 관측치 2 — 재개 도착 순서 서명

turn 2를 `sent_s` 순으로 정렬한 뒤 성공(`O`)/실패(`.`) 열과 평균 순위(1이 가장 이른 도착):

| block | arm | 성패 열 | 성공 평균순위 | 실패 평균순위 | 서명 |
|---|---|---|---|---|---|
| 0 | SYNC | `.OO.....` | 2.50 | 5.17 | ✓ |
| 0 | DISPERSED | `OO.OO...` | 3.00 | 6.00 | ✓ |
| 1 | SYNC | `.O.O.O..` | 4.00 | 4.80 | ✓ |
| 1 | DISPERSED | `OO.O....` | 2.33 | 5.80 | ✓ |
| 2 | SYNC | `...O.O..` | 5.00 | 4.33 | **✗** |
| 2 | DISPERSED | `OO.OO...` | 3.00 | 6.00 | ✓ |

**6개 중 5개에서 서명이 확인됐다.** DISPERSED는 **3/3**이고 세 블록 모두 `OO`로 시작한다 — 가장 이른 두 도착이 항상 성공했다. SYNC는 2/3이며 성패 열이 흩어져 있다.

선등록대로 **상관계수나 유의성을 계산하지 않았다.** 블록당 8 세션, 3블록으로는 검정력이 없다.

### 관측치 3 — `[PFX] [EVICTION]` OB 열

| block | arm | OB 열 |
|---|---|---|
| 0 | SYNC | 4, **0, 1, 2, 3, 5, 6, 7**, 1 |
| 0 | DISPERSED | 4, **0, 1, 2, 3, 5, 6, 7**, 4 |
| 1 | SYNC | 7, **0, 1, 2, 3, 4, 5, 6**, 3 |
| 1 | DISPERSED | 4, **0, 1, 2, 3, 5, 6, 7**, 4 |
| 2 | SYNC | 6, **0, 1, 2, 3, 4, 5, 7**, 3 |
| 2 | DISPERSED | 1, **0, 2, 3, 4, 5, 6, 7**, 1 |

**중간 8개는 전 조합에서 할당 순서(FIFO)를 따른다.** 다만 **첫 eviction의 OB가 0이 아니라 4·7·6·1**이며, 마지막에 한 번 더 evict가 붙는다. 예측 3("두 arm 모두 할당 순서를 따른다")은 대체로 맞지만 **선행 1건은 설명되지 않았다** (아래 `UNKNOWN`).

### 관측치 4 — utilization (기술 대상, 판정 아님)

| block | SYNC | DISPERSED |
|---|---|---|
| 0 | 0.8735 | 0.8331 |
| 1 | 0.9092 | 0.9244 |
| 2 | 0.8736 | 0.8233 |

방향이 혼재하며 차이는 최대 5 %다. 예측 5("비슷하다")는 크기로는 맞고 방향은 일정하지 않다.

### 사전 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| 1 | DISPERSED > SYNC, 3/3 블록 | **부분 적중.** 2/3 방향 일치, 1블록 동률, 반대 0 |
| 2 | SYNC의 실패가 도착 순서 후반에 집중 | **부분 적중.** SYNC 2/3, DISPERSED 3/3 |
| 3 | EVICTION OB 열이 할당 순서를 따른다 | **부분 적중.** 중간 8개는 따르나 선행 1건이 예외 |
| 4 | SYNC 재사용률이 [TASK18](TASK18.md)의 2/8 부근 | ✓ (7/24 ≈ 2.3/8) |
| 5 | utilization이 두 arm 비슷 | ✓ 크기는, 방향은 혼재 |

## 핵심 발견 (층 태그)

1. **`stack`** — **분산만 바꿔도 재사용률이 움직인다.** 총 gap 시간을 소수점까지 고정한 상태에서 DISPERSED 11/24, SYNC 7/24였다. 반대 방향 블록은 없었다. 다만 동률 블록 때문에 선등록 기준으로는 `INCONCLUSIVE`다.
2. **`stack`** — **DISPERSED에서 가장 이른 두 도착이 항상 성공했다** (3/3 블록에서 `OO`로 시작). FIFO pointer가 아직 그 세션들의 slot에 닿지 않았기 때문으로 보이며, 도착 순서가 성패를 가른다는 [TASK17](TASK17.md) 발견 5의 가장 선명한 서명이다.
3. **`stack`** — **SYNC에서는 성패 열이 흩어진다.** 동시에 도착하면 client 측 순서와 server 측 처리 순서가 어긋나 어느 세션이 살아남을지 사실상 예측 불가다. b2에서 서명이 뒤집힌 것도 이 때문으로 보인다.
4. **`class`** — **eviction은 FIFO이고 재접근을 보상하지 않는다.** OB 열의 중간 8개가 전 조합에서 할당 순서였다. 정책이 "언제 재개할 것인가"를 전혀 보지 않는다는 구조적 사실이며, 같은 정책을 쓰는 어느 구현에서나 성립한다.
5. **`universal`** — **동률을 "지지"로 세지 않는 규칙이 결론을 바꿨다.** 2/3 방향 일치와 반대 0건은 시사적이지만, 선등록이 "전부"를 요구했으므로 `INCONCLUSIVE`다. 이 규칙이 없었다면 3 데이터점을 4번째로 확정했다고 보고했을 것이다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(hypothesis, 통합 가설의 첫 직접 증거)** 총 gap 시간을 고정하고 분산만 바꿨을 때 재사용률이 움직였고 도착 순서 서명이 6개 중 5개에서 확인됐다. 이는 **"tool-return timing이 KV 생존을 통제한다"** 는 통합 가설의 첫 직접 증거로 읽을 수 있다 — gap의 *길이*가 아니라 *언제 돌아오는가*가 생존을 가른다는 것이다.

  **그러나 이는 hypothesis이며 이 실험이 확정하지 않는다.** 근거: (i) 선등록 판정이 `INCONCLUSIVE`다, (ii) N=8 한 점, gap 분포 하나, 3블록이다, (iii) 도착 순서 서명은 관찰 기술이지 통계적 검정이 아니다, (iv) [TASK20](TASK20.md)에서 arm 간 재사용 방향이 N에 따라 뒤집혔으므로 N 의존성이 이 결과에도 있을 수 있다.

- **(해석)** b1이 동률(3/8 vs 3/8)인 이유는 확인하지 않았다. b1의 DISPERSED gap이 `4,3,1,1,2,4,2,3`으로 다른 두 블록보다 중앙에 몰려 있어 분산이 작았을 수 있으나, 분산을 정량화해 비교하지 않았다.
- **(해석)** 발견 2·3을 합치면 "분산이 도움이 되는 기전"은 **도착을 직렬화해 FIFO sweep을 늦추는 것**이지 gap 자체가 KV를 보호하는 것이 아니다. 이는 정책 설계에서 "재개 시각을 흩뜨리는 것"이 개입 수단이 될 수 있음을 시사하지만, Stage 0–2 baseline 전에는 구현하지 않는다는 원칙에 따라 기록만 한다.
- **(해석)** utilization이 두 arm에서 비슷한 것은 총 gap 시간이 같아 batch가 비는 총량이 같기 때문으로 보인다. 즉 **분산은 재사용에는 영향을 주지만 utilization에는 거의 주지 않는다** — 두 지표가 서로 다른 자원(outer slot vs decode batch)을 반영한다는 뜻이다.

## 확인되지 않은 사항

- b1이 동률인 이유 (`UNKNOWN`). gap 분산을 정량화해 블록 간 비교하지 않았다.
- `[PFX] [EVICTION]` 첫 항목의 OB가 0이 아닌 이유와 마지막 추가 eviction의 출처 (`UNKNOWN`). dummy block 할당([TASK14](TASK14.md) 사실 6)과 관련될 수 있으나 추적하지 않았다.
- SYNC b2에서 서명이 뒤집힌 이유 (`UNKNOWN`).
- 분산의 정도(예: gap 표준편차)와 재사용률의 관계 (`UNKNOWN`). 두 극단만 비교했다.
- N ≠ 8에서의 분산 효과 (`UNKNOWN`). [TASK20](TASK20.md)이 N 의존을 보였으므로 이 결과의 일반성은 제한된다.
- 재사용 성패와 도착 순위의 통계적 연관 (`UNKNOWN`, 검정력 부족으로 계산하지 않음).

## 실패 / 무효 시도

1. `run_sweep.sh`가 [TASK20](TASK20.md)의 plan seed를 하드코딩하고 있어 이 실험의 선등록 값을 쓸 수 없었다. **측정 시작 전에** 환경변수로 분리하고 선등록 실행 절차를 구체화해 commit했다. 기본값은 [TASK20](TASK20.md) 값 그대로여서 이미 끝난 sweep의 재현성은 바뀌지 않는다.
2. `INVALID` 조합은 **0건**이다. 6/6이 P1·P2·I1–I5를 통과했다.
3. Device·RSD·package·patch 변경 없음. server lifecycle 6회, 전부 종료 후 device memory `0.0B` 복귀.

## 연구 원칙에 미치는 영향

- **동률을 "지지"로 세지 않는다.** 방향성 가설의 판정에서 동률은 지지가 아니라 미지지다. 이 규칙이 결론을 `INCONCLUSIVE`로 유지시켰다.
- **조작 변수가 하나임을 불변식으로 증명한다.** P2(총 gap 시간 동일)가 "분산만 달랐다"를 데이터로 뒷받침한다. 설계 의도를 서술하는 것과 그것이 성립했음을 보이는 것은 다르다.
- **통합 가설을 지지하는 결과라도 관찰과 분리해 기록한다.** 판정이 `INCONCLUSIVE`인데 해석에서 "증거를 얻었다"고 쓰면 기록이 판정을 앞선다.
- **표본이 작을 때 통계 검정을 하지 않겠다고 미리 정한다.** 사후에 p값을 계산하고 싶어지는 것을 막는다.

## 다음 작업

1. **b1 동률의 원인** — gap 분산을 정량화(표준편차 등)해 블록 간 비교한다. 분산-재사용률 관계를 축으로 삼는 실험이 자연스러운 후속이다.
2. **블록 추가** — 3블록으로는 동률 하나가 판정을 막는다. 블록 수를 늘리면 `INCONCLUSIVE`가 갈릴 수 있다. **별도 TASK로 한다.**
3. **N 의존성** — [TASK20](TASK20.md)이 arm 간 재사용 방향의 N 의존을 보였으므로, 분산 효과도 N에 따라 달라지는지 확인이 필요하다.
4. `[PFX] [EVICTION]` 선행 항목의 출처 추적.

사용자 지시 없이 다음 TASK를 자동 시작하지 않는다.

## 재현 정보

- 선등록 commit: `12fbd1cefbc42b18354152f5db7461446d39ea02` (2026-08-20 17:03:46 KST)
- 측정 전 runner 수정 commit: `533aa316123da22b0abd6977457df977244b1f57` (17:54:29 KST)
- **측정 시작 시각: 2026-08-20 17:54:3x KST** — 두 commit 모두 측정보다 앞선다
- 측정 종료 시각: `<RUN>/measurement-end.txt`
- Base commit (측정 중 HEAD): `533aa316123da22b0abd6977457df977244b1f57`
- **Patch state: `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`**
- plan seed: `SWEEP_BASE_SEED=20260831`, `SWEEP_BLOCK_PREFIX=g` → `block_id=g<B>` (arm 간 동일). SYNC는 `--sync-gaps`
- 블록별 arm 순서: `balanced_arm_orders(["SYNC","DISPERSED"], rounds=3, base_seed=20260831, block_id="task21")` → b0 S→D, b1 S→D, b2 D→S
- Raw artifact: `results/npu/stage2/20260820-180000-gap-dispersion/`
  - `measurement-{start,end}.txt`, `patch-state.txt`, `gapdisp.log`, `done.<TAG>` 6개
  - `server-<ARM>.n8.b<B>.log`, `probe/requests.<TAG>.jsonl`, `probe/meta.<TAG>.json`
  - `metrics-<TAG>.prom`, `util.<TAG>.json`, `rbln-smi-{before,final}.txt`
- 실행 script: `experiments/npu/stage2/{run_sweep.sh,session_runner.py}`, `experiments/npu/analysis/utilization.py`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(**patched**), `optimum-rbln 0.11.1`, `torch 2.11.0+cpu`
- Host: `atom-max8`, device `rbln0`–`rbln3`
