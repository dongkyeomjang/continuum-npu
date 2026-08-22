# 선등록 — causal 반환 정책의 실기기 검증

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. **측정 후 판정 기준을 완화하지 않는다.**

## 무엇을 검사하는가

[TASK26](TASK26.md)이 남긴 `UNKNOWN` — "ε 이득이 실제 device에서 재현되는가" — 를 정책 형태로 닫는다.

**주의: 이득을 검사하는 것이 아니다.** [TASK27](TASK27.md)에서 어떤 causal 정책도 device time을 평균적으로 개선하지 못했고, 선정된 `FREESLOT`(ε=1 s)조차 이번 seed에서는 **손해**로 예측된다. 검사 대상은 **시뮬레이터의 정책 수준 예측이 device에서 성립하는가**다. sim이 "나빠진다"고 한 만큼 실제로 나빠지면 그것이 sim-to-real 재현이다.

## 승인 범위 (사용자 판정, 2026-08-22)

serving 기동·종료(예상 30회 내외), 기존 관측 스택, `src/continuum/policy/`·`src/continuum/sim/`·`experiments/npu/` 코드 추가·수정. **정책은 client 측 반환 보류로만 구현한다 — server·patch 변경 금지.**

범위 밖: 재compile, download, patch 변경, RSD 변경, GPU 서버 작업, remote push 자동 수행.

## Substrate 상태

측정 전 `apply.sh status`가 `patched`(SHA256 `70942d16…`)가 아니면 시작하지 않는다. 재compile을 하지 않으므로 격자는 `(1, 2, 4, 8)`, artifact는 `models/Qwen3-4B-rbln-b8-s8192-d4-mb`다.

## 실험 격자

| 항목 | 값 |
|---|---|
| N | **6, 8** (확증 구간) + **10** (탐색 구간) |
| arm | `IMMEDIATE` / `FREESLOT` (ε = 1 s) |
| block | **b6, b7, b8** (신규) |
| 총 조합 | 3 × 2 × 3 = **18** |
| plan seed | `base_seed = 20260860`, `block_id = n<N>b<B>` |
| 세션 구조·분포·gap | [TASK20](TASK20.md) 이래와 **완전히 동일** (`first uniform:800:1600`, `later fixed:8`, `generation uniform:32:256`, `gap uniform:1:5`, turns 2) |
| server | 조합마다 fresh, `--enable-prefix-caching --enable-prompt-tokens-details` |

**짝 설계(P1)**: 두 arm은 **같은 plan**을 쓴다. plan은 `(base_seed, block_id)`만으로 생성되고 arm 이름은 들어가지 않으므로, 두 arm의 segment 길이·생성 길이·tool gap이 구성상 동일하다. 유일한 차이는 **turn 1의 반환을 client가 붙드는지 여부**다.

**정책 구현**: 시뮬레이터와 client가 `src/continuum/policy/online.py`의 **같은 객체**를 쓴다. 예측과 실측의 차이가 구현 불일치일 가능성을 구조적으로 제거한다.

블록 랜덤화: b6 `IMMEDIATE`→`FREESLOT`, b7 `FREESLOT`→`IMMEDIATE`, b8 `IMMEDIATE`→`FREESLOT`.

## 선등록 예측 — 이 문서의 본체

[TASK27](TASK27.md)의 시뮬레이터(commit `10b9328`)를 위 plan에 그대로 돌려 얻은 값이다. **어떤 파라미터도 이 예측을 위해 조정하지 않았다.**

`busy ratio` = device time(`FREESLOT`) / device time(`IMMEDIATE`). **1보다 크면 정책이 손해다.**

| N | 구간 | **예측 busy ratio** | 예측 절감 | 블록별 예측 ratio (b6/b7/b8) | 재사용 (IMM→FS) | hold p50 / p99 / max (s) |
|---|---|---|---|---|---|---|
| 6 | **확증** | **1.0554** | −5.54 % | 1.0060 / 1.0789 / 1.0838 | 12 → 12 / 18 | 0.77 / 1.01 / 1.01 |
| 8 | **확증** | **1.0332** | −3.32 % | 1.0582 / 1.0247 / 1.0165 | 13 → 13 / 24 | 0.46 / 1.01 / 1.01 |
| 10 | 탐색 | 1.0023 | −0.23 % | 1.0462 / 0.9701 / 0.9931 | 8 → 9 / 30 | 0.17 / 1.21 / 1.21 |

참고(판정 아님): oracle 대비 회수율 예측은 N=6 −79.7 %, N=8 −42.6 %, N=10 −4.4 %다. utilization 예측은 N=6 0.885 → 0.883, N=8 0.855 → 0.860, N=10 0.869 → 0.879 — **[TASK26](TASK26.md) 결론대로 참고 열로만 쓴다.**

## 판정 기준

### 확증 구간 (N ∈ {6, 8})

두 조건을 **모두** 만족해야 `PASS`다.

1. **오차**: `|예측 busy ratio − 실측 busy ratio| ≤ 0.03`
2. **방향**: 예측과 실측이 1을 기준으로 같은 쪽에 있거나, **둘 다 동치 밴드 `[0.98, 1.02]` 안**에 있다

> 밴드 예외를 두는 이유는 [TASK25](TASK25.md)와 같다. 1에 붙은 예측값에 부호 일치를 요구하면 모형이 아니라 규칙의 민감도를 재게 된다. **측정 전에 고정한다.**
>
> 밴드 `[0.98, 1.02]`는 utilization 밴드 `[0.97, 1.03]`보다 좁다. device time을 step 열에서 정확히 세기 때문이며, 예측 효과 크기(0.033·0.055)가 밴드보다 크므로 판정이 실질적이다.

| 결과 | 판정 |
|---|---|
| N=6·N=8 둘 다 만족 | **PASS** |
| 하나만 만족 | **PARTIAL** — 어느 쪽이 왜 빗나갔는지 기록 |
| 둘 다 실패 | **FAIL** |

### 탐색 구간 (N = 10)

**판정하지 않는다.** [TASK24](TASK24.md)가 N ≥ 10에서 시뮬레이터 오차가 5–6배 커진다고 기록했고 [TASK25](TASK25.md)의 검증 격자(N ≤ 7)에도 없다. 예측 대비 오차를 **보고만** 한다.

### 채널 일치 요건 (모든 구간에 선행)

device time을 **독립적인 두 채널**로 잰다.

| 채널 | 정의 | 모형 의존 |
|---|---|---|
| **A** | `[BUCKET]` step 열의 `(actual, bucket)` 쌍마다 [TASK13](TASK13.md) step 비용을 곱해 합산 | 비용 모형에 의존 |
| **B** | client의 `sent_s`/`done_s`에서 **in-flight 구간의 합집합** 길이. 아무 요청도 없는 구간(순수 tool gap·보류)은 자동으로 빠진다 | **모형 무의존** |

**두 채널의 busy ratio 차이가 0.02를 넘으면 그 N의 판정을 보류한다.** 절대값은 다를 수밖에 없다(B는 queueing·HTTP를 포함한다). 같아야 하는 것은 arm 간 **비**다.

## 불변식 (fail-loud, 위반 조합은 `INVALID`)

- **P1**: 두 arm의 plan(세션 수, turn 수, segment 길이, 생성 길이, gap)이 동일
- **P2**: 두 arm의 decode 작업량 `Σ(completion_tokens − 1)`이 동일 — 정책이 타이밍이 아니라 작업량을 바꿨다면 이후 비교가 무의미하다
- **P3**: `FREESLOT` arm의 모든 `held_s ≤ ε + 0.05 s`. 예산 위반은 정책 구현 실패다
- **P4**: `IMMEDIATE` arm의 모든 `held_s = 0`
- I1–I5: [NSLOTS_SWEEP_PREREG.md](NSLOTS_SWEEP_PREREG.md)와 동일. bucket 집합 `{1, 2, 4, 8}`

## 필수 측정 항목

조합별: per-request JSONL(`held_s` 포함), plan summary, `[BUCKET]`·`[PFX]` 로그 전문, `/metrics` 덤프, utilization JSON. 전체: patch state, `rbln-smi`, provenance, 측정 시작·종료 시각, 선등록 commit.

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-policy-device`

1. `apply.sh status` → `patched` 확인
2. N 6 → 8 → 10 순서, 블록별 arm 순서표대로 실행. background + 완료 표식 + PID 기준 server 종료
3. 조합마다 `utilization.py --cost-model`
4. P1–P4·I1–I5 확인 → 채널 일치 확인 → 확증 구간 판정 → 탐색 구간 보고

```bash
SWEEP_BASE_SEED=20260860 SWEEP_POLICY=freeslot SWEEP_BUDGET=1.0 \
  bash experiments/npu/stage2/run_sweep.sh <RUN> FREESLOT <N> <B> none
SWEEP_BASE_SEED=20260860 \
  bash experiments/npu/stage2/run_sweep.sh <RUN> IMMEDIATE <N> <B> none
```

**실행 중인 실험의 script를 편집하지 않는다** ([TASK23](TASK23.md)의 연쇄 실패 원인).

## 관련 문서

- [TASK27](TASK27.md) — 정책 정의, 선정 근거, seed 강건성
- [TASK26](TASK26.md) — oracle bound(회수율의 분모), utilization이 비용이 아니라는 결론
- [TASK25](TASK25.md) — 선등록 out-of-sample 검증의 선례와 밴드 예외 규칙
- [TASK13](TASK13.md) — 채널 A의 step 비용
