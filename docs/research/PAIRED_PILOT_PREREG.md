# 선등록 — AGENTIC vs CONVENTIONAL 짝 비교 파일럿

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다.

## 목적

"agentic tool use가 bucket utilization을 체계적으로 저하시키는가"(Track A 핵심 RQ)의 첫 짝 비교.

**파일럿 1블록이다.** 효과의 **방향과 크기 추정**까지만 하며 **확정 주장을 하지 않는다.**

## 선행 조건

[TASK18](TASK18.md)의 per-request 귀속 게이트가 **통과**했다 (G1 8/8, G2 16/16, G3 일치). 그 채널을 그대로 쓴다.

## 승인 범위 (사용자 판정, 2026-08-19)

b8 artifact serving 기동·종료(횟수 무제한, PID 특정 확인), localhost 요청, DEBUG + `VLLM_RBLN_METRICS=1`, `src/continuum/` 및 `experiments/npu/` 코드 추가·수정.

범위 밖: 재compile, download, patch 추가·수정, RSD 변경, remote push 자동 수행.

## Substrate 상태

측정 전 `apply.sh status`가 `patched`(SHA256 `70942d16…`)가 아니면 시작하지 않는다.

## 실험 설계

### Arm 정의 (짝 설계)

세션 = 유일 prompt(≥129 token) → turn 1 생성 → **[AGENTIC: tool gap / CONVENTIONAL: gap 0]** → turn 2 재개(누적 transcript 포함) → 생성 종료.

**두 arm은 동일 seed·동일 `block_id`를 써서 prompt 길이와 생성 길이 시퀀스가 정확히 같고 gap만 다르다.**

이를 위해 CONVENTIONAL의 gap 분포를 `fixed:0`이 아니라 **`uniform:0:0`** 으로 둔다. `Distribution.draw`에서 `fixed`는 rng를 소비하지 않고 `uniform`은 소비하므로, `fixed:0`을 쓰면 이후 turn의 seg·gen 추출이 어긋나 **짝이 깨진다.** `uniform:0:0`은 `rng.randint(0,0)`으로 같은 횟수를 소비하면서 0을 돌려준다. 측정 전에 두 arm의 plan summary가 gap 외 전 항목에서 동일함을 확인한다 (아래 불변식 P1).

### 부하 구성

| 항목 | 값 |
|---|---|
| 논리 세션 수 N | **8, 16** (두 수준) |
| turn 수 | 2 |
| 첫 segment | `uniform:800:1600` token (세션별 상이, `derive_block_seed` 기반) |
| 이후 segment | `fixed:8` token |
| 생성 길이 | `uniform:32:256` (세션별 상이 — 전이 유발 목적) |
| gap | AGENTIC `uniform:1:5` 초 / CONVENTIONAL `uniform:0:0` |
| Model | `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음) |
| Server | `--enable-prefix-caching --enable-prompt-tokens-details` |
| 환경변수 | `VLLM_LOGGING_LEVEL=DEBUG`, `VLLM_RBLN_METRICS=1` |
| plan seed | `base_seed=20260823`, `block_id = n8` / `n16` (**arm 간 동일**) |
| sampling seed | 20260819 |

gap 범위 `1–5`초의 근거: turn 1의 총 소요는 prompt 약 1,200 token(prefill 약 0.2 s) + 생성 평균 약 144 token(step 약 13.8 ms → 약 2.0 s)으로 **약 2초 자릿수**로 사전 추정된다 ([TASK13](TASK13.md) 비용 모형, [TASK15](TASK15.md) prefill 시간). 같은 자릿수를 덮도록 잡았다.

### 실행

**arm × N 조합마다 fresh server** (arm 간 cache 오염 차단). 총 4 lifecycle.

실행 순서는 `balanced_arm_orders`로 블록 랜덤화한다.

```python
balanced_arm_orders(["AGENTIC/8", "CONVENTIONAL/8", "AGENTIC/16", "CONVENTIONAL/16"],
                    rounds=1, base_seed=20260823, block_id="task19-pilot")
```

→ **`("CONVENTIONAL/8", "CONVENTIONAL/16", "AGENTIC/16", "AGENTIC/8")`** (결정적으로 재현된다)

## 선등록 관측치

| # | 관측치 | 정의 | 역할 |
|---|---|---|---|
| **1** | **시간가중 bucket utilization** | `Σ(request_nums) / Σ(padded_batch_size)` over `[BUCKET]` decode step | **1차 판정치**. 무차원 |
| 2 | 처리량 | 총 생성 token / 총 경과시간, arm 간 ratio | utilization 저하의 시간 전이 확인 |
| 3 | 층 2 재사용률 | turn 2 중 `cached_tokens > 0`인 비율 (세션별, [TASK18](TASK18.md) 채널) | [TASK17](TASK17.md) 발견 5의 재관측 |
| 4 | mean ITL (보조) | `vllm:inter_token_latency_seconds` sum/count | 보조 |

관측치 1은 **slot 점유 비율이지 시간 점유 비율이 아니다.** 같은 bucket 안 step 비용이 같다는 [TASK13](TASK13.md) 결과에 기대어 "시간가중"이라 부르지만, bucket이 다르면 step 비용이 다르므로 **시간 몫으로 읽지 않는다.**

**ITL p50/p99는 산출하지 않는다.** non-streaming 요청이라 client 측 raw 표본이 없고, histogram 보간은 오차를 도입한다. 이유를 명시하고 mean만 기록한다.

## 불변식 (fail-loud, 위반 시 `INVALID`)

| # | 불변식 |
|---|---|
| **P1** | 같은 N의 두 arm의 plan summary가 `gap_after_s`를 제외한 전 항목에서 동일 |
| **I1** | 모든 `[BUCKET]` 줄이 파싱된다 |
| **I2** | 모든 step에서 `request_nums ≤ padded_batch_size` |
| **I3** | `padded_batch_size ∈ {1, 2, 4, 8}` |
| **I4** | 관측 사상이 `bucket_for(request_nums)`와 일치 ([TASK13](TASK13.md) 표) |
| **I5** | `Σ(request_nums)` = `Σ_requests (completion_tokens − 1)` |

I5의 근거: decode step 하나가 running 요청마다 token 1개를 낸다. 첫 token은 prefill에서 나오므로 요청당 decode step 기여는 `completion_tokens − 1`이다. **[TASK17](TASK17.md) 관측 A 데이터로 사전 검산했다 — 1,400 = 1,400.**

## 판정

파일럿이므로 **채택/기각이 아니다.** 다음 세 가지를 산출한다.

- **(a) 방향 일치 여부**: AGENTIC utilization < CONVENTIONAL 인가
- **(b) ratio 점추정**: `utilization(AGENTIC) / utilization(CONVENTIONAL)`, N별
- **(c) 본 실험 표본 수 설계에 필요한 분산 정보**: 1블록이라 arm 내 분산을 추정할 수 없다는 사실 자체와, 다음 실험에서 무엇을 반복해야 하는지

**utilization 산출 자체의 불변식은 fail-loud이며 위반 시 그 조합을 `INVALID`로 처리한다.**

## 사전 예측 (판정 기준 아님)

| # | 예측 | 근거 |
|---|---|---|
| 1 | **방향**: AGENTIC utilization < CONVENTIONAL | gap 동안 세션이 빠져 batch가 얇아지고, 재개가 흩어져 도착하면 작은 `request_nums`가 큰 bucket에 실린다 |
| 2 | **N=16이 N=8보다 저하가 크다** | gap 중 다른 세션 도착이 batch를 더 출렁이게 한다 |
| 3 | AGENTIC의 층 2 재사용률이 CONVENTIONAL보다 낮다 | gap 동안 배경 할당이 쌓인다 ([TASK14](TASK14.md)·[TASK15](TASK15.md)) |
| 4 | AGENTIC 처리량이 CONVENTIONAL보다 낮다 | gap 자체가 경과시간에 들어간다 — **utilization과 무관하게 자명하다** |
| 5 | 두 arm의 총 생성 token이 동일 | 짝 설계 |

**크기는 예측하지 않는다.** 이번 목적이 추정이기 때문이다.

예측 4는 자명하므로 관측치 2를 utilization 저하의 증거로 쓰지 않는다. 관측치 2는 **utilization 저하가 시간으로 전이되는지**를 보기 위한 것이며, gap 시간을 제외한 비교가 필요하다는 점을 결과에서 다룬다.

## 필수 측정 항목

조합별: per-request JSONL 전체, plan summary, `[BUCKET]`·`[PFX]` 로그 전문, 최종 `/metrics` 덤프, utilization 산출 JSON(불변식 결과 포함), patch state, `rbln-smi`(첫 기동 전·마지막 종료 후), provenance 일체.

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-paired-pilot`

1. `apply.sh status` → `patched` 확인
2. 순서 `(CONVENTIONAL/8, CONVENTIONAL/16, AGENTIC/16, AGENTIC/8)`대로 각 조합에서:
   a. server 기동, `/health` 대기
   b. `session_runner.py` 실행 (`--arm <ARM> --block-id n<N>`)
   c. `/metrics` 덤프
   d. PID 특정 후 `SIGTERM`, 종료 확인
3. 조합별 `utilization.py` 실행 → 불변식 판정
4. P1 확인 후 arm 비교표 작성

## 산출

arm별·N별 utilization/처리량/재사용률 표와 **본 실험 격자 제안**(격자 축, 블록 수, 고정할 것/움직일 것)을 "다음 작업" 절에 기록한다.

## 관련 문서

- [TASK18](TASK18.md) — per-request 귀속 채널과 게이트
- [TASK17](TASK17.md) — generator, bucket 전이, 발견 5
- [TASK13](TASK13.md) — 사상표와 step 비용 모형
- [TASK16](TASK16.md) — substrate descriptor, 층 태그
