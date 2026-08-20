# 선등록 — gap 분산 → 재사용 메커니즘 검증

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다.

## 연구 질문과 가설

**RQ**: 층 2 재사용률을 좌우하는 것이 gap의 **존재·길이**인가, 아니면 **재개 도착의 분산**인가?

**H**: 분산이다. gap이 흩어지면 재개가 순차적으로 도착해 FIFO pointer가 한 번에 여러 slot을 쓸어가지 못하고, 동시에 도착하면 일괄 sweep이 일어난다.

### 기존 데이터점 3개 (모두 같은 방향)

| TASK | 구성 | gap | 재사용률 |
|---|---|---|---|
| [TASK17](TASK17.md) | 8 세션, 2,000 token | `uniform:1:6` (분산) | **4/8** |
| [TASK18](TASK18.md) | 8 세션, ladder 300–2,400 | `fixed:2` (동일) | **2/8** |
| [TASK19](TASK19.md) | 8 세션, `uniform:800:1600` | `uniform:1:5` (분산) | **3/8** |

세 실험은 prompt 구성도 달라 단독 비교가 불가능했다. **이번 실험은 분산만을 조작 변수로 둔다.**

## 승인 범위 (사용자 판정, 2026-08-20)

b8 artifact serving 기동·종료(PID 특정 확인), localhost 요청, DEBUG + `VLLM_RBLN_METRICS=1` + `--enable-prompt-tokens-details`, `src/continuum/`·`experiments/npu/` 코드 추가·수정.

범위 밖: 재compile, download, patch 추가·수정, RSD 변경, remote push 자동 수행.

## Substrate 상태

측정 전 `apply.sh status`가 `patched`(SHA256 `70942d16…`)가 아니면 시작하지 않는다.

## 실험 설계

### 조작 변수는 분산 하나뿐

| 항목 | 값 |
|---|---|
| N | **8 고정** (= `outer_slot_count`) |
| 세션·길이 plan | 동일 seed에서 파생. `first uniform:800:1600`, `later fixed:8`, `generation uniform:32:256` |
| gap 분포 | `uniform:1:5` 초로 **한 번 뽑는다** |
| **DISPERSED arm** | 뽑힌 gap을 그대로 사용 (세션마다 다름) |
| **SYNC arm** | 같은 plan의 gap을 **전부 평균값으로 치환** (`set_uniform_gaps`) |
| **총 gap 시간** | **두 arm이 정확히 동일** (`set_uniform_gaps`가 합 보존을 assert한다) |
| 블록 | **3블록** (b0–b2), 블록마다 새 plan |
| plan seed | `base_seed=20260831`, `block_id = g<B>` (**arm 간 동일**) |
| sampling seed | 20260819 |
| server | 조합마다 fresh. `--enable-prefix-caching --enable-prompt-tokens-details` |

`set_uniform_gaps`는 gap 외 전 항목을 그대로 두고 gap만 평균으로 바꾼 사본을 돌려주며, 총합이 바뀌면 `AssertionError`로 중단한다. **따라서 두 arm은 총 gap 시간이 같고 분산만 다르다.**

### 블록별 arm 실행 순서

```python
balanced_arm_orders(["SYNC", "DISPERSED"], rounds=3,
                    base_seed=20260831, block_id="task21")
```

| block | 순서 |
|---|---|
| 0 | SYNC → DISPERSED |
| 1 | SYNC → DISPERSED |
| 2 | DISPERSED → SYNC |

## 관측치

| # | 관측치 | 정의 |
|---|---|---|
| **1** | **층 2 재사용률** | turn 2 중 `cached_tokens > 0`인 세션 비율. **1차 판정치** |
| 2 | 재개 도착 순서와 성패 | turn 2를 `sent_s` 순으로 정렬한 뒤 각 세션의 재사용 성패 |
| 3 | `[PFX] [EVICTION]` OB 열 | FIFO sweep의 직접 증거 |
| 4 | utilization (기술) | 판정 대상 아님. 분산이 batch 모양에 미치는 영향 기록용 |

## 불변식 (fail-loud, 위반 조합은 `INVALID`)

| # | 불변식 |
|---|---|
| **P1** | 같은 block의 두 arm plan이 `gap_after_s`를 제외한 전 항목에서 동일 |
| **P2** | 두 arm의 `total_gap_s`가 동일 (오차 < 1e-6) |
| I1–I5 | [NSLOTS_SWEEP_PREREG.md](NSLOTS_SWEEP_PREREG.md)와 동일 |

## 판정 (선등록)

**표본이 작으므로 통계 검정을 하지 않는다.** 다음 두 가지를 요구한다.

| 판정 | 조건 |
|---|---|
| **H 지지** | 3블록 **전부** `재사용률(DISPERSED) > 재사용률(SYNC)` |
| **H 반증** | 3블록 전부 반대 방향 |
| **INCONCLUSIVE** | 방향이 섞임 |

동률(`=`)이 있는 블록은 "전부"를 만족하지 못하므로 `INCONCLUSIVE`로 간다.

### 부가 판정 — 도착 순서 서명

FIFO pointer 메커니즘이 맞다면 **재사용 실패가 도착 순서 후반에 몰려야** 한다. 각 arm·블록에서 turn 2를 `sent_s` 순으로 정렬해 실패 세션의 **평균 순위**를 기록한다(1이 가장 이른 도착).

| 판정 | 조건 |
|---|---|
| 서명 확인 | 실패 세션의 평균 순위 > 성공 세션의 평균 순위, SYNC·DISPERSED 양쪽에서 |
| 서명 미확인 | 그 외 |

**이는 관찰 기술 수준의 판정이며 상관계수나 유의성을 계산하지 않는다** — 블록당 8 세션, 3블록으로는 검정력이 없다.

## 사전 예측 (판정 기준 아님)

| # | 예측 | 근거 |
|---|---|---|
| 1 | DISPERSED 재사용률 > SYNC, 3/3 블록 | 기존 3 데이터점의 방향 |
| 2 | SYNC의 실패가 도착 순서 후반에 집중 | FIFO pointer가 초반 도착에 밀려 후반 세션의 slot에 도달 |
| 3 | `[PFX] [EVICTION]` OB 열이 두 arm 모두 할당 순서(0,1,2,…)를 따른다 | FIFO |
| 4 | SYNC 재사용률이 [TASK18](TASK18.md)의 2/8 부근 | 그 실험이 `fixed:2`로 사실상 SYNC였다 |
| 5 | utilization은 두 arm이 비슷하다 | 총 gap 시간이 같아 batch가 비는 총량이 같다 |

예측 5는 확신도가 낮다 — 분산이 batch 모양을 바꿀 수 있다.

## 필수 측정 항목

조합별: per-request JSONL(`sent_s` 포함), plan summary와 `total_gap_s`, `[BUCKET]`·`[PFX]` 로그 전문, `/metrics` 덤프, utilization JSON. 전체: patch state, `rbln-smi`, provenance.

## 해석 방침

결과가 예측 방향대로 나오면 "**tool-return timing이 KV 생존을 통제한다**"는 통합 가설의 첫 직접 증거가 된다. 그러나 이는 **관찰이 아니라 hypothesis이며 반드시 분리해 기록한다.** 이 실험은 N=8·단일 gap 분포·3블록이므로 그 가설을 확정하지 않는다.

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-gap-dispersion`

1. `apply.sh status` → `patched` 확인
2. block 0–2, 위 순서표대로 `run_sweep.sh <RUN> <SYNC|DISPERSED> 8 <B> <sync|none>` 실행
   - SYNC는 `sync`, DISPERSED는 `none`
3. 조합마다 `utilization.py --cost-model` 실행
4. P1·P2 확인 후 판정

## 관련 문서

- [TASK19](TASK19.md), [TASK18](TASK18.md), [TASK17](TASK17.md) — 기존 데이터점 3개
- [TASK14](TASK14.md) — FIFO eviction 정책의 source 근거
- [NSLOTS_SWEEP_PREREG.md](NSLOTS_SWEEP_PREREG.md) — 불변식 I1–I5의 정의
