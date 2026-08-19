# TASK17 — agentic workload generator v0와 bucket 전이 첫 관측

## 상태

DONE

## 판정

- **판정 A (bucket 전이 관측): 전이 관측됨.** 한 server lifetime 안에서 `padded_batch_size`가 **8 → 4 → 2 → 1**로 단조 감소했고, 전 전이 시점의 사상이 [TASK13](TASK13.md) 표와 **전건 일치**했다. [TASK12](TASK12.md)부터 이월된 `UNKNOWN`이 해소됐다.
- **판정 B (gap 재개 attribution): 8 세션 중 4개 성공, 4개 실패.** 사전 예측 4(0/8 실패)는 **빗나갔다.**

## 날짜

2026-08-19

## 목적

1. [TASK12](TASK12.md)부터 이월된 "bucket 전이 미관측"을 해소한다.
2. Track A characterization의 도구(agentic workload generator)를 확보한다.

**파일럿이다.** agentic vs conventional 본 비교는 범위 밖이며 **utilization 저하의 정량 주장을 하지 않는다.**

## 배경

관련 TASK:

- [TASK12](TASK12.md) — bucket 전이 미관측의 출처. 이후 [TASK13](TASK13.md)에서도 수준 내 `request_nums`를 고정해 전이가 생기지 않았다.
- [TASK13](TASK13.md) — 사상표와 step 비용 모형.
- [TASK15](TASK15.md) — 층 2 attribution 채널.
- [TASK16](TASK16.md) — substrate descriptor, 층 태그 규칙.

선등록 문서: [AGENTIC_PILOT_PREREG.md](AGENTIC_PILOT_PREREG.md)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `3bab21bb86c564d3d6f95ce31b437b13f01c2173`
- Git dirty: untracked `.idea/`만
- **Substrate: patched** (SHA256 `70942d16…`). 측정 전 gate 통과
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)
- Device: 32 visible ID 전부 idle, port 8000 비어 있음

## 수행 내용

1. `src/continuum/workload/agentic.py`(accelerator-neutral)를 신설했다. **plan만 만들고 text는 만들지 않는다** — text 생성은 tokenizer가 필요해 backend 쪽 일이다.
2. `experiments/npu/stage2/agentic_pilot.py`가 plan을 실제 prompt로 materialize하고 세션을 동시 구동한다.
3. 선등록 문서·module·runner를 **측정 시작 전에** commit했다 (`3bab21b`).
4. Patch gate 통과 후 관측 A·B를 각각 **fresh server**로 실행했다.

재compile, download, patch 변경, RSD 변경은 없었다.

## 변경된 파일

선등록 commit `3bab21b`:

- `docs/research/AGENTIC_PILOT_PREREG.md` (신규)
- `src/continuum/workload/agentic.py` (신규, neutral)
- `experiments/npu/stage2/agentic_pilot.py` (신규, backend)

이번 기록 commit:

- `docs/research/TASK17.md` (신규)
- `docs/research/INDEX.md`

Raw artifact는 `.gitignore` 대상인 `results/npu/stage2/20260819-211600-agentic-pilot/`에 있다.

## Generator v0 사용법

```python
from continuum.workload.agentic import Distribution, generate_sessions, plan_summary

sessions = generate_sessions(
    session_count=8,
    turns_per_session=2,
    first_segment=Distribution("fixed", value=2000),      # 여는 context
    later_segment=Distribution("fixed", value=8),         # tool 결과 되먹임
    generation=Distribution("uniform", low=32, high=64),
    gap_seconds=Distribution("lognormal", median=2.0, spread=1.6),
    base_seed=20260821,
    block_id="obsB",
)
```

- `Distribution`은 `fixed` / `uniform` / `lognormal`. lognormal은 `(mu, sigma)`가 아니라 **중앙값과 배수 spread**로 받는다 — "대부분 짧고 일부 길다"를 표현할 때 그쪽이 읽기 쉽다.
- 모든 draw가 `derive_block_seed(base_seed, ...)`에서 나오므로 `(base_seed, block_id)`가 같으면 plan이 정확히 재현된다.
- `Session.context_tokens_before(k)`가 turn k가 물려받는 누적 context를 준다.
- **Continuum semantics**: turn k의 prompt = turn k−1의 prompt + turn k−1의 생성 텍스트 + 새 segment. tool gap은 client 측 `sleep`.

runner는 `--generation ladder:START:STEP`로 결정적 계단 생성 길이를 줄 수 있다. 세션을 일정 간격으로 끝내 decode batch를 내리는 용도다.

## 결과

### 조건 분리

- `requested_condition`: 8 세션 동시. 관측 A는 1 turn, 첫 segment 300 token, 생성 길이 ladder `64 + 32·s`, gap 없음. 관측 B는 2 turn, 첫 segment 2,000 token, 이후 segment 8 token, 생성 uniform 32–64, gap uniform 1–6 초. plan seed 20260821, sampling seed 20260819, 관측마다 fresh server.
- `observed_condition`: 전 요청 status 200. 관측 A의 prompt는 전 세션 300 token, 생성은 요청대로 64/96/…/288. 관측 B의 turn 1 prompt 2,000 token, turn 2 prompt 2,043–2,072 token(세션마다 생성 길이가 달라 다름). patch state 전 구간 `patched`.
- `condition_reached`: `YES`.

### 관측 A — bucket 전이

Population: 한 server lifetime의 decode step 287회. Source: `[BUCKET]` DEBUG 로그. Device scope: `rbln0`–`rbln3`.

세션 종료 시각이 계단을 이뤘다: 1.46 / 1.90 / 2.34 / 2.78 / 3.15 / 3.51 / 3.87 / 4.20 s.

`[BUCKET]` 로그를 시간 순서로 압축하면:

| 순서 | `request_nums` | `padded_batch_size` | step 수 |
|---|---|---|---|
| 1 | 8 | **8** | 63 |
| 2 | 7 | 8 | 32 |
| 3 | 6 | 8 | 32 |
| 4 | 5 | 8 | 32 |
| 5 | 4 | **4** | 32 |
| 6 | 3 | 4 | 32 |
| 7 | 2 | **2** | 32 |
| 8 | 1 | **1** | 32 |

**`padded_batch_size`가 8 → 4 → 2 → 1로 단조 감소했다.** 전 구간의 사상이 [TASK13](TASK13.md) 표와 일치한다(8→8, 7→8, 6→8, 5→8, 4→4, 3→4, 2→2, 1→1). 총 287 = 63 + 32×7이며 63은 첫 세션의 64 token 생성에서 decode step 63회에 해당한다.

**판정 A: 전이 관측됨.**

부수 관측: `request_nums`가 7, 6, 5인 96 step 동안 bucket은 8이었다. padding slot이 각각 1, 2, 3이며 [TASK16](TASK16.md) descriptor의 `bucket_crossing_cost_s(5..7) = 2.145 ms`가 그 구간에 적용된다. **다만 이는 descriptor를 이 관측에 대입한 것이지 이번에 측정한 값이 아니다.**

### 관측 B — gap 재개 attribution

Population: 8 세션 × 2 turn = 16 요청. Source: `[PFX]` DEBUG 로그(1차), `/metrics` 증분(참고). Device scope: `rbln0`–`rbln3`.

turn 1은 3.49–3.88 s에 모두 끝났고, turn 2는 gap에 따라 **4.67 – 8.51 s**에 흩어져 도착했다.

`[PFX]` 로그 집계:

| 항목 | 수 |
|---|---|
| `ALLOC` | 16 (요청당 1, 전부 `OB_COUNT=1`) |
| `MAPPING-SEARCH` | 8 (turn 2 요청 수와 일치) |
| **`CACHE-HIT`** | **4** (전부 `OB_COUNT=1`) |
| **`CACHE-PARTIAL`** | **4** (전부 `REUSED=0/1920`) |
| `EVICTION` | 9 |
| `FREE-REQUEST` | 16 |

**8 세션 중 4개가 turn 2에서 층 2 재사용에 성공했고 4개가 실패했다.** 실패는 전부 `REUSED=0/1920`으로 부분 생존이 없었다.

eviction OB 순서: `0, 1, 2, 3, 4, 5, 6, 7, 0`. 할당 순서대로 진행하는 FIFO이며 [TASK14](TASK14.md)·[TASK15](TASK15.md)와 같다.

로그 순서로 본 성공/실패 열: **HIT, PARTIAL, HIT, HIT, HIT, PARTIAL, PARTIAL, PARTIAL**. 초반 도착이 대체로 성공하고 후반이 실패했으나 두 번째 도착이 실패했으므로 "먼저 온 4개가 성공"이라는 단순 규칙은 성립하지 않는다.

**어느 세션이 어느 결과인지는 이번 자료로 확정할 수 없다.** runner가 응답의 `id`를 기록하지 않아 `[PFX]` 로그의 request id를 세션에 매핑할 수 없다 (아래 "실패 / 무효 시도" 참조).

관측 B의 `[BUCKET]` 사상도 전 구간 [TASK13](TASK13.md) 표와 일치했으며, turn 1 구간(8→1)과 turn 2 구간(2→1→5→4→3→1)에서 **여러 차례 비단조 전이**가 나타났다. 실제 agentic workload에서 bucket이 오르내린다는 첫 관측이다.

### 층 1과 층 2의 대조

`/metrics` 증분 표에서 turn 2의 층 1 `hits`는 1,920–9,600으로 전 세션이 0이 아니었던 반면 층 2 `cached`는 0인 세션이 있었다. [TASK15](TASK15.md)의 거짓 양성이 agentic workload에서도 나타난다.

다만 아래 이유로 **이 표의 per-request 값은 신뢰할 수 없다.**

### 사전 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| 1 | 관측 A에서 8 → 4 → 2 → 1 전이 전부 관측 | ✓ |
| 2 | 전이 시점 사상이 [TASK13](TASK13.md) 표와 전건 일치 | ✓ |
| 3 | 관측 A에서 `request_nums = 7, 6, 5`가 모두 나타남 | ✓ |
| 4 | **관측 B에서 8 세션 전부 재사용 실패 (0/8)** | ✗ **빗나감. 4/8 성공** |
| 5 | 관측 B에서 층 1 `hits`가 0이 아닌 값 보고 | ✓ |
| 6 | 관측 B에서 `EVICTION` 최소 8회 | ✓ (9회) |

6개 중 5개 적중. 빗나간 예측 4는 선등록에 "이 파일럿에서 가장 확신도가 낮으면서 가장 흥미로운 항목"으로 명시해 둔 것이다.

## 핵심 발견

1. **`stack`** — **bucket 전이가 관측됐다.** 생성 길이를 흩뜨리면 `padded_batch_size`가 8 → 4 → 2 → 1로 내려가고 전 전이의 사상이 [TASK13](TASK13.md) 표와 일치한다. [TASK12](TASK12.md)부터 세 TASK를 이월해 온 `UNKNOWN`이 닫혔다. Track A characterization의 대상 현상이 재현 가능한 방식으로 만들어졌다.
2. **`class`** — **전이를 만들려면 생성 길이를 흩뜨리면 된다.** [TASK12](TASK12.md)·[TASK13](TASK13.md)이 전이를 못 본 이유는 모든 요청의 `max_tokens`가 같아 동시에 끝났기 때문이다. 고정 bucket을 쓰는 어느 substrate에서나 같은 설계 실수가 전이를 감출 수 있다.
3. **`stack`** — **agentic workload에서 bucket이 오르내린다.** 관측 B의 turn 2 구간에서 `padded_batch_size`가 1 → 5 → 4 → 3 → 1처럼 비단조로 움직였다. 정상 상태 격자로는 볼 수 없는 거동이다.
4. **`stack`** — **동시 세션 수 = outer slot 수인 agentic workload에서 절반의 세션이 gap을 넘기지 못했다.** 4/8만 재사용에 성공했고 실패는 전부 `REUSED=0/1920`으로 all-or-nothing이었다. 예측(0/8)보다 나았지만 절반이다.
5. **`stack`** — **재사용 성공 여부가 세션 자신의 행동이 아니라 도착 순서에 좌우된다.** 실패한 세션도 성공한 세션과 같은 prefix 길이·같은 gap 구조를 가졌다. 차이는 FIFO pointer가 그 세션의 slot에 도달했는지뿐이다.
6. **`universal`** — **동시 실행 중에는 counter 증분으로 per-request attribution을 할 수 없다.** 요청 전후로 `/metrics`를 긁으면 그 사이에 진행한 다른 요청의 기여가 섞인다. 관측 B에서 층 2 `cached` 증분이 5,760·9,600처럼 단일 요청이 낼 수 없는 값을 보였고, `[PFX]` 로그 기준 실제 성공은 4개인데 증분 기준으로는 5개로 보였다. **동시 workload에서 신뢰할 수 있는 per-request 채널은 request id를 담은 로그다.**

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(hypothesis)** 예측 4가 빗나간 이유는 gap이 흩어져 turn 2 도착이 순차적이었기 때문으로 보인다. 도착 하나가 eviction 하나를 유발하며 FIFO pointer를 한 칸 밀고, pointer가 아직 재개하지 않은 세션의 slot에 닿기 전에 도착한 세션은 자기 slot을 지킨다. 전 세션이 동시에 재개했다면 결과가 달랐을 수 있다. **gap 분포가 재사용률을 좌우한다**는 가설이며 이번 파일럿으로 검증하지 않았다.
- **(해석)** 발견 5는 정책 설계에 함의가 있다. FIFO는 "누가 곧 재개할 것인가"를 전혀 보지 않으므로, 재개가 임박한 세션의 slot을 재개가 먼 세션 때문에 잃을 수 있다. Stage 0–2 baseline 전에는 정책을 구현하지 않는다는 원칙에 따라 여기서는 기록만 한다.
- **(해석)** 관측 A에서 `request_nums`가 7·6·5인 96 step 동안 bucket 8이 쓰였다. [TASK16](TASK16.md) descriptor를 대입하면 그 구간의 bucket crossing 비용은 2.145 ms/step이지만, **이번에 그 비용을 측정한 것이 아니다.** 파일럿이므로 utilization 저하를 정량화하지 않는다.
- **(해석)** 발견 6은 이전 TASK들의 결과를 위협하지 않는다. [TASK14](TASK14.md)·[TASK15](TASK15.md)는 전부 동시성 1이었고 요청 사이에 증분을 쟀다. 동시 workload로 넘어오면서 처음 문제가 됐다.

## 확인되지 않은 사항

- 어느 세션이 재사용에 성공했는지 (`UNKNOWN`). runner가 응답 `id`를 기록하지 않아 `[PFX]` 로그와 매핑할 수 없다.
- gap 분포가 재사용률을 어떻게 바꾸는지 (`UNKNOWN`). 단일 분포(uniform 1–6 s) 1회만 봤다.
- 동시 세션 수 ≠ outer slot 수일 때의 재사용률 (`UNKNOWN`). 8 = 8만 봤다.
- 전이 구간의 실제 시간 비용 (`UNKNOWN`). descriptor 예측만 있고 이번에 측정하지 않았다.
- 관측 B의 비단조 bucket 전이가 어떤 도착·종료 사건에 대응하는지 (`UNKNOWN`). 사건 시각과 `[BUCKET]` 로그를 1초 해상도로는 정렬할 수 없다.
- 재현성 (`UNKNOWN`). 관측 A·B 각 1회의 파일럿이다.

## 본 characterization 격자 설계에 필요한 미지수

1. **request id ↔ 세션 매핑** — runner가 응답 `id`를 기록해야 per-request 판정이 가능하다. 본 실험 전 필수 수정이다.
2. **per-request 관측 채널** — 동시 workload에서 counter 증분이 무효이므로 `[PFX]`/`[BUCKET]` 로그 파싱이 1차 채널이 된다. 로그 timestamp가 1초 해상도라는 제약([TASK13](TASK13.md))을 어떻게 다룰지 정해야 한다.
3. **gap 분포의 격자** — 재사용률이 gap 분포에 의존한다는 가설을 검증하려면 median·spread를 축으로 삼아야 한다.
4. **세션 수 : slot 수 비율** — 8:8만 봤다. 이 비율이 주 독립변수 후보다.
5. **전이 구간 비용의 측정 방법** — bucket이 오르내리는 동안의 step 시간을 어떻게 귀속할지. [TASK13](TASK13.md)의 정상 상태 방법(수준마다 server 하나)이 통하지 않는다.
6. **conventional 대조군의 정의** — agentic과 비교하려면 같은 총 token·같은 동시성인 gap 없는 workload를 어떻게 구성할지 정해야 한다.

## 실패 / 무효 시도

1. **runner가 응답 `id`를 기록하지 않아 세션별 재사용 판정을 하지 못했다.** `[PFX]` 로그는 request id를 담고 있는데 probe JSON에는 `usage`만 남겼다. 총계(4/8)는 확정할 수 있으나 세션 귀속은 불가능하다. 본 실험 전에 고쳐야 한다.
2. **동시 실행 중 counter 증분이 per-request로 유효하지 않았다.** `/metrics` 전후 스크레이프 사이에 다른 요청이 진행한다. 증분 기준으로는 성공 5개로 보였으나 `[PFX]` 기준 실제는 4개였다. **`[PFX]` 로그를 1차로 채택하고 증분 표는 참고로만 기록했다.**
3. 무효로 판정한 측정은 없다. 16 + 8 = 24 요청 전부 status 200.
4. Device·RSD·package·patch 변경 없음. 2개 server lifecycle 모두 종료 후 device memory `0.0B` 복귀, context 소멸.

## 연구 원칙에 미치는 영향

- **동시 workload에서는 counter 증분으로 per-request 귀속을 하지 않는다.** request id를 담은 채널만 per-request 판정에 쓴다. 동시성 1 실험에서 통하던 방법이 그대로 넘어오지 않는다.
- **현상을 못 본 것이 현상이 없는 것은 아니다.** bucket 전이는 세 TASK 동안 관측되지 않았는데, 원인은 substrate가 아니라 모든 요청의 `max_tokens`를 같게 둔 실험 설계였다.
- **파일럿에서는 정량 주장을 하지 않는다.** descriptor를 관측 구간에 대입해 비용을 계산할 수는 있으나 그것은 예측이지 측정이 아니다.
- **가장 확신도 낮은 예측을 명시해 두면 그것이 빗나갔을 때 결과로 읽힌다.** 예측 4는 빗나갔고, 빗나간 방식(0/8이 아니라 4/8, 그리고 도착 순서 의존)이 발견 5가 됐다.

## 다음 작업

1. runner에 request id 기록을 추가한다 (본 실험 전 필수).
2. 위 "미지수 목록" 6개를 격자 설계에 반영한다.
3. agentic vs conventional 본 비교. 측정이 포함되므로 선등록한다.

사용자 지시 없이 다음 TASK를 자동 시작하지 않는다.

## 재현 정보

- 선등록 commit: `3bab21bb86c564d3d6f95ce31b437b13f01c2173`
- **측정 시작 시각: 2026-08-19 21:15:52 KST.** 선등록 commit 시각은 2026-08-19 21:15:33 KST이므로 **선등록이 측정보다 19초 앞선다.**
- 측정 종료 시각: `<RUN>/measurement-end.txt`
- Base commit (측정 중 HEAD): `3bab21bb86c564d3d6f95ce31b437b13f01c2173`, dirty = untracked `.idea/` 및 gitignored `results/`, `models/`
- **Patch state: `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`** — `<RUN>/patch-state.txt`
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)
- plan seed: `base_seed=20260821`, `block_id` = `obsA` / `obsB`. `generate_sessions`가 결정적이므로 plan이 재현된다
- Raw artifact: `results/npu/stage2/20260819-211600-agentic-pilot/`
  - `measurement-start.txt`, `measurement-end.txt`, `patch-state.txt`
  - `server-obsA.log`, `server-obsB.log` — `[BUCKET]`·`[PFX]` 로그와 PREFILL/DECODE METRICS
  - `probe/agentic.obsA.json`, `probe/agentic.obsB.json` — plan summary와 요청별 기록
  - `probe-obsA.log`, `probe-obsB.log`, `rbln-smi-before.txt`, `rbln-smi-final.txt`
- 신규 코드: `src/continuum/workload/agentic.py` (neutral), `experiments/npu/stage2/agentic_pilot.py` (backend)
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(**patched**), `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch 2.11.0+cpu`
- Host: `atom-max8`, device `rbln0`–`rbln3`
