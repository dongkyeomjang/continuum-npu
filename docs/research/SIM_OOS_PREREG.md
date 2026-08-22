# 선등록 — 시뮬레이터의 out-of-sample 예측 검증

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. **측정 후 판정 기준을 완화하지 않는다.**

## 왜 필요한가

[TASK24](TASK24.md)의 시뮬레이터는 기존 80조합을 utilization 평균절대오차 0.0066으로 재현했지만, 그 자료는 전부 **이미 관측된 것**이고 규칙 중 둘(층 2 hit 양, outer pool 사건 순서)은 **그 자료를 보고 특정했다.** 따라서 in-sample 일치는 예측력의 증거가 아니다. 예측력 주장은 측정 전에 commit된 예측이 신규 seed의 실측과 맞을 때만 성립한다.

## 승인 범위 (사용자 판정, 2026-08-21)

serving 기동·종료(예상 20회 내외, 기존 b8 artifact), 기존 관측 스택, `src/continuum/` 코드 추가.

범위 밖: **재compile, download, patch 변경, RSD 변경, remote push 자동 수행.** GPU 서버 관련 작업도 [결정 4](INDEX.md#결정-4--gpua6000-교차검증-착수-시점)에 따라 이번 batch에서 시작하지 않는다.

## Substrate 상태

측정 전 `apply.sh status`가 `patched`(SHA256 `70942d16…`)가 아니면 시작하지 않는다. 재compile을 하지 않으므로 격자는 `(1, 2, 4, 8)`이고 artifact는 `models/Qwen3-4B-rbln-b8-s8192-d4-mb`다.

## 실험 격자

| 항목 | 값 |
|---|---|
| N | **3, 4, 7** |
| block | **b3, b4, b5** (신규. 기존 b0–b2와 파일이 겹치지 않는다) |
| arm | AGENTIC / CONVENTIONAL (짝, `zero_gaps()` 파생) |
| 총 조합 | 3 × 2 × 3 = **18** |
| plan seed | `base_seed = 20260850`, `block_id = n<N>b<B>` |
| 세션 구조·분포·gap | [TASK20](TASK20.md)·[TASK23](TASK23.md)과 **완전히 동일** (`first uniform:800:1600`, `later fixed:8`, `generation uniform:32:256`, `gap uniform:1:5`, turns 2) |
| server | 조합마다 fresh, `--enable-prefix-caching --enable-prompt-tokens-details` |

블록별 arm 순서: `balanced_arm_orders(["AGENTIC","CONVENTIONAL"], rounds=3, base_seed=20260850, block_id="task25")` → **b3 A→C, b4 C→A, b5 A→C**

## 선등록 예측 — 이것이 이 문서의 본체다

[TASK24](TASK24.md)의 시뮬레이터(commit `0f6f302`)를 위 plan에 그대로 돌려 얻은 값이다. **어떤 파라미터도 이 예측을 위해 조정하지 않았다.**

### 블록별 예측 ratio (`util(AGENTIC)/util(CONVENTIONAL)`)

| N | b3 | b4 | b5 | **신규 3블록 pooled** |
|---|---|---|---|---|
| 3 | 1.0404 | 1.1935 | 1.1309 | **1.1145** |
| 4 | 1.0083 | 0.9984 | 1.0409 | **1.0161** |
| 7 | 1.0038 | 1.1067 | 1.0092 | **1.0362** |

pooled는 [TASK20](TASK20.md)과 같은 step 가중이다 — arm별로 블록을 합쳐 `Σ(request_nums)/Σ(padded_batch_size)`를 구한 뒤 두 arm의 비를 잡는다.

### 6블록 합산 판정 예측

기존 실측 3블록 + 신규 3블록. 기존 값은 실측이고 신규 값만 예측이다.

| N | 기존 실측 ratio (b0–b2) | 신규 예측 ratio (b3–b5) | 합산 예측 pooled | **예상 판정** |
|---|---|---|---|---|
| 3 | 1.0926 / 1.1360 / 1.0232 | 1.0404 / 1.1935 / 1.1309 | **1.1007** | **역전** (5/6 밴드 위) |
| 4 | 0.9436 / 1.0895 / 1.0712 | 1.0083 / 0.9984 / 1.0409 | **1.0279** | **`INCONCLUSIVE`** (위 3, 아래 1, 밴드 안 2) |
| 7 | 0.9928 / 1.0229 / 1.0481 | 1.0038 / 1.1067 / 1.0092 | **1.0293** | **`INCONCLUSIVE`** (위 2, 밴드 안 4) |

**N=16은 이번 batch에서 측정하지 않는다.** 격자에 없기 때문이다. 시뮬레이터만으로 8블록(기존 5 + 가상 신규 3) 합산을 예측하면 pooled **0.9892**, 판정 `INCONCLUSIVE`(아래 3, 밴드 안 5)다. **이 값은 검증되지 않으며 게이트에도 들어가지 않는다.** 기록만 남긴다.

## 판정 기준

### 게이트 (작업 2의 본 판정)

신규 3블록 pooled에 대해 **N = 3, 4, 7 각각**:

1. **오차**: `|sim pooled − measured pooled| ≤ 0.05`
2. **방향**: 두 값이 1을 기준으로 같은 쪽에 있거나, **둘 다 동치 밴드 `[0.97, 1.03]` 안**에 있다

> 방향 요건에 밴드 예외를 두는 이유: N=4의 예측값 1.0161은 밴드 안이며 1에 가깝다. 이런 값에 부호 일치를 요구하면 오차 0.02로도 실패하는데, 그것은 모형의 실패가 아니라 판정 규칙의 인위적 민감도다. **이 예외는 측정 전에 고정한다.**

| 결과 | 판정 |
|---|---|
| 3개 N 전부 1과 2를 만족 | **PASS** |
| 일부만 만족 | **PARTIAL** — 어느 N이 왜 빗나갔는지 기록한다 |
| 전부 실패 | **FAIL** |

**게이트가 `PASS`가 아니면 offline oracle bound(작업 3)를 수행하지 않는다.** 누락 기전의 규명이 우선이다.

### 6블록 합산 판정 규칙

동치 밴드는 [TASK20](TASK20.md)·[TASK23](TASK23.md)과 동일한 `[0.97, 1.03]`이다.

**6블록 중 5블록 이상이 같은 방향 그리고 pooled가 밴드 밖**이면 "역전"(> 1.03) 또는 "저하 존재"(< 0.97)를 채택한다. 6블록 전부가 밴드 안이면 "동치". 그 외는 `INCONCLUSIVE`.

**5/6 요건의 근거 (측정 전 고정).** 3블록에서 쓰던 "전부 동방향"은 부호검정 기준 한쪽 꼬리 확률 `P(X≥3) = 0.125`다. 블록 수가 늘 때 같은 엄격도를 유지하려면 6블록에서는 `P(X≥5) = 7/64 = 0.109 ≤ 0.125`인 **5/6**이 맞고, `X≥4`는 `22/64 = 0.344`로 훨씬 느슨해진다. [TASK23](TASK23.md)이 8블록에 7/8(`P = 9/256 = 0.035`)을 쓴 것과 같은 방식이며, **"전부"를 요구하는 규칙이 표본이 커질수록 비대칭적으로 엄해지는 문제**를 같은 방식으로 처리한다.

## 불변식 (fail-loud, 위반 조합은 `INVALID`)

P1(짝 plan 동일성), I1–I5는 [NSLOTS_SWEEP_PREREG.md](NSLOTS_SWEEP_PREREG.md)와 동일하다. bucket 집합은 `{1, 2, 4, 8}`이다.

## 부수 예측 (게이트 아님, 기록용)

시뮬레이터는 조합마다 층 2 재사용 hit/miss도 예측한다. [TASK24](TASK24.md)의 in-sample 일치율은 93.0 %였다. **신규 18조합에서의 일치율을 그대로 보고하되 판정 기준으로 쓰지 않는다** — 게이트는 pooled ratio 하나로 한정한다.

## 필수 측정 항목

조합별: per-request JSONL, plan summary, `[BUCKET]`·`[PFX]` 로그 전문, `/metrics` 덤프, utilization JSON. 전체: patch state, `rbln-smi`, disk 사용량, provenance, 측정 시작·종료 시각.

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-sim-oos`

1. `apply.sh status` → `patched` 확인
2. `SWEEP_BASE_SEED=20260850`로 N 3 → 4 → 7 순서, 블록별 arm 순서표대로 `run_sweep.sh` 실행. background + 완료 표식 + PID 기준 server 종료
3. 조합마다 `utilization.py --cost-model`
4. P1·I1–I5 확인 후 게이트 판정, 이어서 6블록 합산 재판정

```bash
SWEEP_BASE_SEED=20260850 \
  bash experiments/npu/stage2/run_sweep.sh <RUN> <ARM> <3|4|7> <3|4|5> <none|zero>
```

**실행 중인 실험의 script를 편집하지 않는다** ([TASK23](TASK23.md)에서 연쇄 실패를 낸 원인이다).

## 관련 문서

- [TASK24](TASK24.md) — 시뮬레이터, in-sample 재현, 자유 파라미터 목록
- [TASK23](TASK23.md) — N=3·N=7의 기존 3블록, 8블록 합산 규칙의 선례
- [TASK20](TASK20.md) — N=4·N=16의 기존 블록, pooled 정의와 밴드
