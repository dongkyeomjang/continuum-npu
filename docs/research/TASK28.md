# TASK28 — causal 반환 정책의 실기기 검증

## 상태

DONE

## 판정

선등록 문서: [POLICY_DEVICE_PREREG.md](POLICY_DEVICE_PREREG.md) (commit `980f0c7`, 2026-08-22T17:19:42+09:00). **측정 시작 17:19:59 — 선등록 17초 뒤.**

### 채널 일치 (판정에 선행)

| N | 채널 A (step 열 × 비용 모형) | 채널 B (in-flight 합집합, 모형 무의존) | 차 | 요건 ≤ 0.02 |
|---|---|---|---|---|
| 6 | 1.0732 | 1.0625 | 0.0106 | 통과 |
| 8 | 1.0541 | 1.0438 | 0.0104 | 통과 |
| 10 | 0.9805 | 0.9913 | 0.0108 | 통과 |

**세 N 모두 두 채널이 일치했다.** 판정 보류 사유가 없다.

### 확증 구간 (N ∈ {6, 8}) — **PASS 2/2**

`busy ratio` = device time(`FREESLOT`) / device time(`IMMEDIATE`). **1보다 크면 정책이 손해다.**

| N | 선등록 sim | 실측 A | 오차 | 허용 ±0.03 | 방향 | 판정 | (실측 B / 오차) |
|---|---|---|---|---|---|---|---|
| 6 | 1.0554 | **1.0732** | **+0.0178** | 통과 | 일치 | **PASS** | 1.0625 / +0.0072 |
| 8 | 1.0332 | **1.0541** | **+0.0209** | 통과 | 일치 | **PASS** | 1.0438 / +0.0106 |

### 탐색 구간 (N = 10) — 판정하지 않음

선등록 sim 1.0023, 실측 A 0.9805(오차 −0.0218), 실측 B 0.9913(오차 −0.0110). **부호가 반대이지만 두 값 모두 동치 밴드 `[0.98, 1.02]` 안이다.**

### X — causal 정책이 device에서 회수한 oracle headroom

| N | oracle ratio (sim) | 정책 ratio (실측) | **X** |
|---|---|---|---|
| 6 | 0.9305 | 1.0732 | **−105.3 %** |
| 8 | 0.9221 | 1.0541 | **−69.5 %** |
| 10 (탐색) | 0.9462 | 0.9805 | +36.2 % |

**X는 확증 구간에서 음수다.** `FREESLOT`은 headroom을 회수하지 못할 뿐 아니라 **headroom과 비슷한 크기만큼 반대 방향으로 손해를 낸다.** [TASK27](TASK27.md)이 계산으로 얻은 결론이 device에서 재현됐다.

불변식 P1–P4·I1–I5 **18/18 통과**, `INVALID` 0건, 실행 실패 0건.

## 날짜

2026-08-22

## 목적

[TASK26](TASK26.md)이 남긴 `UNKNOWN` — "ε 이득이 실제 device에서 재현되는가" — 를 정책 형태로 닫는다. **이득의 검사가 아니라 [TASK27](TASK27.md) 시뮬레이터의 정책 수준 예측이 device에서 성립하는지의 검사다.**

## 배경

관련 TASK:

- [TASK27](TASK27.md) — 정책 정의·선정, seed 강건성, 예측을 낸 시뮬레이터(commit `10b9328`)
- [TASK26](TASK26.md) — oracle bound(X의 분모), utilization이 비용이 아니라는 결론
- [TASK25](TASK25.md) — 선등록 out-of-sample 검증의 선례, 밴드 예외 규칙
- [TASK13](TASK13.md) — 채널 A의 step 비용

## 시작 상태

- 선등록 commit: `980f0c7a8e4f27d7c2c58d745151104fe732c21a` (2026-08-22T17:19:42+09:00)
- 예측 생성 commit: `10b9328` ([TASK27](TASK27.md))
- 측정 시작 **17:19:59**, 종료 **17:44:46** — 선등록 이후
- Substrate: `patched` (SHA256 `70942d16…`), 측정 전 gate 통과
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (**재compile 없음**), 격자 `(1,2,4,8)`
- 측정 시작 시 32/32 device idle

## 수행 내용

1. `session_runner.py`에 `ReturnGate`를 넣어 client 측 반환 보류를 구현했다. **server·patch는 건드리지 않았다.**
2. gate는 [TASK27](TASK27.md)의 정책 객체를 **그대로** 쓴다. 시뮬레이터와 client가 같은 코드이므로 예측·실측 차이가 구현 불일치일 가능성이 구조적으로 없다.
3. 측정 전에 sim 예측을 수치로 선등록 commit했다.
4. 18조합(N ∈ {6,8,10} × 2 arm × 3블록)을 측정했다. 블록별 arm 순서 b6 I→F, b7 F→I, b8 I→F.
5. device time을 독립적인 두 채널로 산출하고, 채널 일치를 확인한 뒤 판정했다.

## 변경된 파일

- `docs/research/POLICY_DEVICE_PREREG.md` (선등록, `980f0c7`에서 commit)
- `experiments/npu/stage2/session_runner.py` (`ReturnGate`, `--return-policy`, `--return-budget-s`, `--buckets`, `held_s` 기록)
- `experiments/npu/stage2/run_sweep.sh` (`SWEEP_POLICY`/`SWEEP_BUDGET`/`SWEEP_BUCKETS`, 기본값은 이전과 동일한 `immediate`)
- `experiments/npu/analysis/policy_device.py` (신규, 2채널)
- `docs/research/TASK28.md` (신규)
- `docs/research/INDEX.md`

## 실험 또는 검증 방법

```bash
SWEEP_BASE_SEED=20260860 SWEEP_POLICY=freeslot SWEEP_BUDGET=1.0 \
  bash experiments/npu/stage2/run_sweep.sh <RUN> FREESLOT <N> <B> none
SWEEP_BASE_SEED=20260860 \
  bash experiments/npu/stage2/run_sweep.sh <RUN> IMMEDIATE <N> <B> none

python3 experiments/npu/analysis/policy_device.py --run <RUN> --cells 6:6,7,8 8:6,7,8 10:6,7,8
```

`requested_condition` / `observed_condition` / `condition_reached`:

| 항목 | requested | observed | reached |
|---|---|---|---|
| 조합 수 | 18 | **18** (실패 0, `INVALID` 0) | `YES` |
| serving lifecycle | 약 30회 | **19회** (smoke 1회 포함) | `YES` |
| 재compile | 금지 | **0회** | `YES` |
| server·patch 변경 | 금지 | **0건** (client 측 보류만) | `YES` |
| 측정이 선등록 이후 | 필수 | 선등록 17:19:42 → 측정 17:19:59 | `YES` |

## 결과

### 관측 1 — 블록별 실측

| N | 블록 | 채널 A: IMMEDIATE / FREESLOT (s) | A ratio | 채널 B (s) | B ratio |
|---|---|---|---|---|---|
| 6 | b6 | 7.506 / 7.632 | 1.0168 | 9.906 / 9.952 | 1.0046 |
| 6 | b7 | 6.619 / 7.236 | 1.0933 | 8.857 / 9.823 | 1.1091 |
| 6 | b8 | 8.554 / 9.469 | 1.1071 | 10.590 / 11.414 | 1.0778 |
| 8 | b6 | 7.783 / 8.373 | 1.0758 | 11.328 / 11.931 | 1.0532 |
| 8 | b7 | 8.760 / 9.231 | 1.0537 | 12.044 / 12.705 | 1.0548 |
| 8 | b8 | 6.604 / 6.797 | 1.0292 | 10.373 / 10.587 | 1.0206 |
| 10 | b6 | 7.262 / 7.312 | 1.0069 | 12.086 / 12.195 | 1.0091 |
| 10 | b7 | 7.823 / 7.111 | 0.9089 | 12.549 / 11.768 | 0.9377 |
| 10 | b8 | 8.197 / 8.406 | 1.0255 | 13.003 / 13.348 | 1.0266 |

**N=6·8은 6블록 전부 1 초과다.** N=10은 b7이 0.909로 크게 반대이며 이 한 블록이 N=10 합산을 1 아래로 끌어내린다.

블록별 예측 대비: N=6 sim `1.0060/1.0789/1.0838` 대 실측 `1.0168/1.0933/1.1071` — **블록 순서(b6 < b7 < b8)까지 맞았다.** N=8은 sim `1.0582/1.0247/1.0165` 대 실측 `1.0758/1.0537/1.0292`로 **순서가 맞고 실측이 일관되게 조금 크다.**

### 관측 2 — 예측이 계통적으로 낮다

확증 구간에서 실측 오차가 **둘 다 양수**다(+0.0178, +0.0209). 채널 B에서도 같은 방향이다(+0.0072, +0.0106). **시뮬레이터가 정책의 손해를 과소평가한다.** 블록 6개 중 6개가 같은 방향이므로 우연으로 보기 어렵다.

### 관측 3 — 부수 관측 (판정 아님)

| N | 재사용 실측 (IMM→FS) | sim 예측 | hold p50 실측 / sim | hold p99 실측 / sim |
|---|---|---|---|---|
| 6 | 13 → 14 / 18 | 12 → 12 | 0.81 / 0.77 | 1.00 / 1.01 |
| 8 | 11 → 10 / 24 | 13 → 13 | 0.37 / 0.46 | 1.00 / 1.01 |
| 10 | 7 → 6 / 30 | 8 → 9 | 0.21 / 0.17 | 1.00 / 1.21 |

**hold 분포는 잘 맞는다** (p50 오차 0.04–0.09 s, p99는 전부 예산 1.0 s에 붙음). **재사용 개수는 ±2 안에서 맞지만 방향이 두 번 어긋났다** — [TASK25](TASK25.md)가 기록한 "개수는 맞고 귀속은 어긋난다"와 같은 성격이다.

P3(예산 준수) 실측 최대 hold는 전 조합에서 1.000 s 이하였다.

## 핵심 발견

1. **`universal` — 시뮬레이터의 정책 수준 예측이 device에서 성립한다.** 측정 전에 commit한 device time ratio가 확증 구간 2/2에서 허용치 안이고, 블록별 순서까지 재현됐다. **[TASK25](TASK25.md)가 확인한 것은 고정 workload의 재현이었고, 이번에 확인된 것은 *제어 개입이 들어간* 조건의 예측이다.** 모형이 "다른 정책을 걸면 어떻게 되는가"에 답할 수 있다는 뜻이다.
2. **`stack` — causal 정책은 headroom을 회수하지 못하고 반대 방향으로 그만큼 손해를 낸다.** X = −105.3 %(N=6), −69.5 %(N=8). [TASK27](TASK27.md)의 계산 결론이 device에서 확인됐다. **"조금 기다렸다 같이 보낸다"는 직관은 계산에서만이 아니라 실기기에서도 틀렸다.**
3. **`stack` — 시뮬레이터는 보류의 손해를 계통적으로 과소평가한다.** 확증 구간 오차가 둘 다 양수이고 블록 6/6이 같은 방향이다. 크기는 0.007–0.021로 판정을 뒤집지 않지만 **부호가 계통적**이므로 모형에 빠진 항이 있다.
4. **`stack` — hold 시간 분포는 정확히 재현되고 재사용 귀속은 아니다.** hold p50 오차가 0.04–0.09 s인 반면 재사용 개수는 방향이 두 번 어긋났다. **정책의 *행동*은 모형이 정확히 아는데 그 행동의 *캐시 결과*는 덜 정확하다.**

## 해석

- **(해석)** 발견 3의 계통 편향에 대한 가설 두 가지. (a) 보류 중에도 client가 쓰는 CPU(다음 turn의 `build_exact` tokenize)와 HTTP 왕복이 있는데 시뮬레이터의 `client_overhead_s`는 0이다 — [TASK24](TASK24.md)에서 0.6–5.6 ms로 측정하고 쓰지 않기로 한 항이다. (b) 보류가 만드는 도착 군집이 server 큐에서 추가 직렬화를 일으키는데 모형에는 admission 1건/step 규칙만 있다. **이 TASK로는 둘을 가르지 못한다.**
- **(해석)** 발견 1이 이 연구선의 실용적 결론이다. 정책 후보를 device에서 하나씩 재는 대신 **시뮬레이터에서 걸러도 된다.** [TASK27](TASK27.md)의 96칸 + 6 seed × 24칸 평가는 device에서 하면 수백 회의 serving lifecycle이 필요했다.
- **(해석)** N=10 b7의 0.909는 단일 블록의 큰 이탈이다. [TASK27](TASK27.md)의 seed 강건성 표에서 `FREESLOT`의 분산이 +4.5 % ~ −4.9 %였던 것과 같은 크기이며, **정책 효과가 plan에 따라 부호까지 바뀐다는 [TASK27](TASK27.md) 발견 4의 device 측 사례**다.
- **(해석)** X가 −100 % 근처라는 것은 "아무것도 하지 않는 편이 낫다"보다 강한 말이다. **잘못된 정책은 아무것도 안 하는 것보다 headroom만큼 더 나쁠 수 있다.**

## 확인되지 않은 사항

- 발견 3의 계통 편향 원인 (`UNKNOWN`). client overhead인지 큐 직렬화인지 가르지 못했다.
- N=10 구간의 판정 (`해당 없음` — 선등록에서 판정하지 않기로 했다). 실측 0.9805/0.9913은 예측 1.0023과 밴드 안에서 어긋난다.
- 다른 정책(`QUANTIZE`, `TOPUP`)의 device 거동 (`UNKNOWN`). [TASK27](TASK27.md)에서 더 나쁘다고 예측됐으나 재지 않았다.
- 다른 ε에서의 device 거동 (`UNKNOWN`). ε=1 s만 쟀다.
- 예측기를 가진 정책 또는 server 측 정책의 device 거동 (`UNKNOWN`). 승인 범위 밖이다.

## 실패 / 무효 시도

없다. 18조합 전부 `VALID`, 실행 실패 0건, 예산 위반 0건이다.

본 측정 전 smoke 실행 1회(`FREESLOT.n6.b6`, 별도 run dir)로 gate 동작·`held_s` 기록·`[BUCKET]` 로깅을 확인했다. 그 결과는 판정에 쓰지 않았다.

## 연구 원칙에 미치는 영향

1. **제어 개입이 들어간 예측도 선등록으로만 주장한다.** 고정 workload의 재현과 개입 조건의 예측은 다른 주장이며 각각 검증한다.
2. **모형 의존 채널과 모형 무의존 채널을 함께 잰다.** 이번엔 둘이 일치했지만, 일치를 확인했기 때문에 판정을 신뢰할 수 있다.
3. **계통 편향은 크기가 작아도 기록한다.** 6/6 블록이 같은 방향이면 판정을 안 바꾸더라도 빠진 항의 신호다.
4. **정책을 device에서 고르지 않는다.** 검증된 시뮬레이터로 거르고 device는 확인에 쓴다.

## 다음 작업

제안만 하며 사용자 지시 없이 실행하지 않는다.

1. **기전 절제 분석** — GPU 실측을 대체하는 반사실 계산.
2. 발견 3의 계통 편향 원인 규명 — `client_overhead_s`를 실측값으로 넣고 재예측해 편향이 설명되는지 확인. 새 측정이 필요 없다.
3. 예측기를 쓰는 정책 또는 server 측 정책. 둘 다 현재 승인 범위 밖이다.

## 재현 정보

- 선등록 commit: `980f0c7a8e4f27d7c2c58d745151104fe732c21a`, 2026-08-22T17:19:42+09:00. **측정 시작 17:19:59 — 선등록 이후**
- 예측 생성 commit: `10b9328` ([TASK27](TASK27.md))
- Raw artifact: `results/npu/stage2/20260822-171959-policy-device/`
  - `measurement-start.txt` / `measurement-end.txt`, `prereg-commit.txt`, `patch-state.txt`
  - 2채널 산출: `device.json`
  - 조합별: `util.*.json`, `server-*.log`, `metrics-*.prom`, `probe/requests.*.jsonl`(`held_s` 포함), `probe/meta.*.json`
- smoke run: `results/npu/stage2/20260822-171*-policy-smoke/` (판정 미사용)
- plan seed: `base_seed = 20260860`, 블록 b6–b8, arm 순서 b6 I→F / b7 F→I / b8 I→F
- 정책: `src/continuum/policy/online.py`의 `FreeSlot`, ε = 1 s, buckets `(1,2,4,8)`
- 실행 script: `experiments/npu/stage2/{run_sweep.sh,session_runner.py}`, `experiments/npu/analysis/{utilization.py,policy_device.py}`
- Substrate: `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`
- 예산 사용: serving lifecycle **19회** / 약 30회, 재compile **0회**, server·patch 변경 **0건**
- 측정 후 device 상태: `rbln-smi-final.txt`
