# 선등록 — B = 7 절벽 재현과 resume attribution 확정

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다.

## 목적

[TASK14](TASK14.md) 파일럿의 두 헤드라인 후보를 반복 측정으로 굳힌다.

1. **절벽**: outer block 소진 지점에서 실제 재사용이 100 % → 0 %로 끊긴다
2. **metric 거짓 양성**: 그 구간에서 `prefix_cache_hits_total`이 재사용을 과대보고한다

그리고 [TASK14](TASK14.md)가 `UNKNOWN`으로 남긴 **"층 1 hit / 층 2 miss 상태에서 실제로 재계산이 일어나는가"** 를 증거로 확정한다.

## 승인 범위 (사용자 판정, 2026-08-19)

b8 artifact serving 기동·종료(PID 특정 종료 확인), localhost 요청, DEBUG + `VLLM_RBLN_METRICS=1` 병용, `src/continuum/` 신규 모듈 추가.

범위 밖: 재compile, download, patch 추가·수정, RSD 변경, remote push 자동 수행.

## Substrate 상태 (provenance 필수)

측정 전 `bash patches/vllm_rbln-0.11.1/apply.sh status`가 `patched`(SHA256 `70942d16…`)가 아니면 시작하지 않는다. 출력을 artifact에 남긴다.

## Attribution 채널 선정과 의미론 검증 (측정 전)

[TASK14](TASK14.md)는 실제 재사용을 `[PFX]` DEBUG 로그로만 판정했다. 이번에 **Prometheus metric 중 어느 것이 어느 층을 세는지** source에서 확정했다.

### Source 추적

```
RBLNOptimumScheduler.schedule()                       optimum_scheduler.py:395-421
  ├─ new_computed_blocks, num_new_local_computed_tokens
  │     = kv_cache_manager.get_computed_blocks(request)          ← 층 1 (inner)
  │        └─ prefix_cache_stats.record(num_hits=...)            → vllm:prefix_cache_hits_total
  ├─ cached_block_table, cached_length
  │     = kv_cache_manager.get_prefix_cached_blocks(...)         ← 층 2 (outer)
  │        └─ prefix_cache_manager.get_matched_outer_blocks(...)
  └─ request.prefill_stats.set(num_local_cached_tokens=sum(cached_length))   ← 층 2
         └─ loggers.py:1159  counter_prompt_tokens_cached.inc(pts.cached_tokens)
         └─ loggers.py:1198  prefill_kv_computed = num_prompt_tokens − num_cached_tokens
```

### 결론: 채널의 층 귀속

| 채널 | 층 | 근거 |
|---|---|---|
| `vllm:prefix_cache_hits_total` | **층 1** | `get_computed_blocks` 안의 `prefix_cache_stats.record` |
| `vllm:prompt_tokens_cached_total` | **층 2** | `prefill_stats`가 `sum(cached_length)`(= `get_matched_outer_blocks` 결과)로 채워진다 |
| `vllm:request_prefill_kv_computed_tokens` | **층 2 파생** | `num_prompt_tokens − num_cached_tokens`(층 2) |
| `vllm:iteration_tokens_total` | **층 2 파생** | scheduler의 `num_scheduled_tokens`가 층 2 반영 이후 값 |
| `VLLM_RBLN_METRICS` PREFILL `Total call counts` | **device 실행** | model forward 호출 수. 어느 층의 장부와도 무관 |
| `[PFX] [CACHE-HIT]` / `[CACHE-PARTIAL]` | **층 2** | prefix cache manager 자체 로그 |

### 사후 검증 (기존 데이터, 이번 측정 아님)

[TASK14](TASK14.md)의 raw artifact를 다시 읽어 위 귀속을 확인했다.

| trial | `hits`(층 1) | `prompt_tokens_cached`(층 2) | `[PFX]` |
|---|---|---|---|
| B0 / B3 / B6 | 1,920 | **1,920** | `CACHE-HIT` |
| B7 / B8 / B9 / B16 | 1,920 | **0** | `CACHE-PARTIAL` 0/1920 |
| B33 | 0 | 0 | 로그 없음 |

`prompt_tokens_cached_total`이 `[PFX]` 로그와 **정확히 일치**한다. 즉 **층 2를 세는 Prometheus metric이 이미 존재했다.**

이는 [TASK11](TASK11.md)이 `UNKNOWN`으로 남긴 "`prompt_tokens_cached_total`이 `hits`와 다른 값을 갖는 조건이 있는가"에 대한 답이며, [INDEX](INDEX.md)의 "cached는 hits와 항상 같은 값"이라는 서술은 **층 2가 항상 hit하던 regime에서의 과잉일반화**였다. 이번 TASK의 commit에서 INDEX를 정정한다.

### 이번 측정에서 쓸 채널

| 역할 | 채널 |
|---|---|
| **1차 판정 (독립)** | `VLLM_RBLN_METRICS` PREFILL `Total call counts` — device 실행 횟수 |
| 2차 판정 | `vllm:request_prefill_kv_computed_tokens_sum` 증분 (층 2 파생) |
| 층 2 대조 | `vllm:prompt_tokens_cached_total` 증분, `[PFX]` 로그 |
| 층 1 대조 | `vllm:prefix_cache_hits_total` 증분 |
| 보조 (판정 미사용) | `vllm:request_prefill_time_seconds_sum`, resume e2e latency |

**채널 간 불일치가 있으면 판정을 보류하고 불일치를 기록한다.**

## 실험 격자

| 항목 | 값 |
|---|---|
| B (배경 요청 수) | **5, 6, 7, 8** — 절벽 좌우 집중. B ≥ 16 재확인은 하지 않는다 |
| 반복 | **각 3 trial** (총 12 trial) |
| trial 키 | `B<b>r<j>`, prompt seed는 `derive_block_seed(20260820, "<key>/<role>")` |
| 격리 | trial마다 **fresh server** ([TASK14](TASK14.md) 방식 유지 — 측정 대상이 outer block pool 상태다) |
| Model | `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음) |
| target / 배경 | 각 2,000 token (유일 내용) |
| suffix | 8 token |
| `max_tokens` | 8 |
| Sampling | `temperature=0.0`, `top_p=1.0`, seed 20260819 |
| 동시성 | 1 (순차) |
| 환경변수 | `VLLM_LOGGING_LEVEL=DEBUG`, `VLLM_RBLN_METRICS=1` |

[TASK14](TASK14.md)와 base seed를 20260819 → **20260820**으로 바꿔 prompt 내용을 새로 뽑는다. 같은 prompt를 재사용하면 재현이 아니라 반복이 되기 때문이다.

## 판정 기준

전생존 기대 hit = `floor(min(2000, 2008−1)/128) × 128` = **1,920 token**.

### 판정 1 — 절벽 재현

| 판정 | 조건 |
|---|---|
| **재현됨** | B ∈ {5, 6}의 9 trial 전부 층 2 재사용 = 1,920이고, B ∈ {7, 8}의 6 trial 전부 층 2 재사용 = 0 |
| 부분 재현 | 위 12개 중 1개 이상이 어긋남. 어긋난 trial을 전부 기록하고 `PARTIAL` |

### 판정 2 — metric 거짓 양성 재현

B ∈ {7, 8}의 6 trial 전부에서 `prefix_cache_hits_total` 증분 = 1,920 **이면서** 층 2 재사용 = 0이면 재현됨.

### 판정 3 — 실제 재계산 attribution

resume 요청의 prefill 계산량을 1차 채널로 확정한다.

각 trial의 PREFILL `Total call counts`는 server lifetime 누적이다. 배경·target 요청은 전부 유일 prompt라 cache hit이 없으므로 각각 `ceil(2000/128) = 16` chunk를 쓴다. 따라서

```
resume_chunks = PREFILL_total_calls − 16 × (B + 1)
```

| 판정 | 조건 |
|---|---|
| **재계산 확정** | B ∈ {7,8}에서 `resume_chunks = 16`(= `ceil(2008/128)`), B ∈ {5,6}에서 `resume_chunks = 1`(= `ceil(88/128)`) |
| 반증 | B ∈ {7,8}에서 `resume_chunks = 1` → 재계산이 일어나지 않았다는 뜻이며 **정합성 문제**를 시사한다. 즉시 기록하고 별도 조사 대상으로 올린다 |
| 판정 보류 | 1차 채널과 2차 채널(`request_prefill_kv_computed_tokens`)이 어긋남 |

### FAIL / PARTIAL 처리 규칙 (측정 전 고정)

| 상황 | 판정 |
|---|---|
| 측정 전 patch state가 `patched`가 아님 | `BLOCKED` |
| server 기동 실패 또는 요청 non-200 | `FAILED` |
| 배경·target 요청의 prefill chunk가 16이 아님 | 판정 3의 산술 전제가 깨짐 → `PARTIAL`, 산술을 쓰지 않고 채널 2·3만으로 기술 |
| 채널 간 불일치 | 판정 보류, `PARTIAL` |
| 종료 후 device memory 미복귀 | `PARTIAL` |

## 사전 예측 (판정 기준 아님)

| # | 예측 | 근거 |
|---|---|---|
| 1 | 절벽이 B = 7에서 **3/3 재현** | [TASK14](TASK14.md) + outer block 8개 산술 |
| 2 | B ≥ 7의 6 trial 전부 층 1 `hits` = 1,920, 층 2 재사용 = 0 | [TASK14](TASK14.md) |
| 3 | **resume prefill 계산량**: B ≤ 6에서 88 token(1 chunk), B ≥ 7에서 2,008 token(16 chunk) | 층 2가 KV 복사원을 잃으면 재계산 외에 방법이 없다 |
| 4 | `request_prefill_kv_computed_tokens_sum` resume 증분 = 88(B≤6) / 2,008(B≥7) | 층 2 파생 산식 |
| 5 | `prompt_tokens_cached_total` resume 증분 = 1,920(B≤6) / 0(B≥7) | 층 2 |
| 6 | eviction 수 = `B − 5` (B ≥ 6) | [TASK14](TASK14.md) 관측 재현 |
| 7 | resume e2e latency가 B ≤ 6에서 약 0.11 s, B ≥ 7에서 약 0.45 s | [TASK14](TASK14.md). **판정 미사용** |

예측 3은 이 TASK의 핵심이며 반증 가능하다 — 반증되면 정합성 문제다.

## 부수 관측 (판정 대상 아님)

- eviction 수가 산술 예상 `B − 6`이 아니라 `B − 5`인 현상 ([TASK14](TASK14.md) 이월). 재현 여부만 기록한다.
- 층 1 문턱(16 < B ≤ 33)의 정밀화는 **하지 않는다.** 층 1이 실사용 지표가 아님이 확정됐기 때문이다.

## 산출 — 생존 법칙의 재기술

관찰과 법칙(가설)을 분리해 기록한다.

- **관찰**: 위 판정 결과
- **법칙 후보 (가설)**: "생존 ⇔ gap 중 도착한 요청 수 ≤ free outer slot 수"

법칙은 이 인스턴스의 상수(`outer_slot_count = 8`)에 의존하므로, 그 사실을 층 태그와 함께 기록한다.

## 층 태깅 (이 TASK부터 적용)

핵심 발견마다 다음 태그를 붙인다. 정의와 판정 기준은 후속 TASK(substrate descriptor v0)에서 정식화하며, 이 TASK는 그 규칙을 선행 적용한다.

| 태그 | 뜻 |
|---|---|
| `silicon` | 이 가속기 하드웨어 고유 |
| `stack` | 이 software stack(vllm-rbln + optimum-rbln) 고유 |
| `class` | 이 종류의 가속기·stack 일반에 적용될 것으로 보이는 성질 |
| `universal` | 가속기·stack과 무관한 성질 |

## 필수 측정 항목

trial별: 전 요청 status·`usage`·counter 증분 전체, resume의 층 1/층 2 값, PREFILL/DECODE METRICS 전문, `[PFX]` 로그 전문(ALLOC/EVICTION/CACHE-HIT/CACHE-PARTIAL), 파생 `resume_chunks`, patch state, `rbln-smi`(첫 기동 전·마지막 종료 후), provenance 일체.

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-cliff-repro`

1. `apply.sh status` → `patched` 확인, 아니면 중단
2. trial 12개(`B5r0..B8r2`)를 키 순서대로: server 기동 → `/health` 대기 → probe → PID 특정 후 `SIGTERM` → 종료 확인
3. 로그에서 PREFILL call counts와 `[PFX]` 집계 → 판정 1·2·3

## 관련 문서

- [TASK14](TASK14.md) — 파일럿, 재현 대상
- [TASK11](TASK11.md) — hit 산식과 `prompt_tokens_cached` `UNKNOWN`의 출처
- [TASK13](TASK13.md) — PREFILL/DECODE METRICS 채널의 선례
- [GAP_TURNOVER_PREREG.md](GAP_TURNOVER_PREREG.md) — 층 구조 source 조사
