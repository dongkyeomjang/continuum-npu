# 선등록 — agentic workload generator v0와 bucket 전이 첫 관측

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다.

## 목적

1. [TASK12](TASK12.md)부터 이월된 **"bucket 전이 미관측"** 을 해소한다.
2. Track A characterization의 도구(agentic workload generator)를 확보한다.

**파일럿 규모다.** agentic vs conventional 본 비교는 이번 범위가 아니며, **utilization 저하의 정량 주장을 하지 않는다.**

## 승인 범위 (사용자 판정, 2026-08-19)

b8 artifact serving 기동·종료(PID 특정 종료 확인), localhost 요청, DEBUG + `VLLM_RBLN_METRICS=1` 병용, `src/continuum/` 신규 모듈 추가.

범위 밖: 재compile, download, patch 추가·수정, RSD 변경, remote push 자동 수행.

## Substrate 상태 (provenance 필수)

측정 전 `apply.sh status`가 `patched`(SHA256 `70942d16…`)가 아니면 시작하지 않는다.

## Generator v0 (측정 전 확정, 이 commit에 포함)

`src/continuum/workload/agentic.py` — accelerator-neutral. **plan만 만들고 text는 만들지 않는다** (text 생성은 tokenizer가 필요해 backend 쪽 일이다).

- `Distribution`: `fixed` / `uniform` / `lognormal`. lognormal은 (mu, sigma)가 아니라 **중앙값과 배수 spread**로 받는다
- `Turn`: `new_segment_tokens`, `generation_tokens`, `gap_after_s`, `text_seed`
- `Session`: turn 열. `context_tokens_before(k)`가 turn k가 물려받는 누적 context를 준다
- `generate_sessions(...)`: 모든 draw가 `derive_block_seed(base_seed, ...)`에서 나오므로 `(base_seed, block_id)`가 같으면 plan이 정확히 재현된다
- `plan_summary(...)`: requested condition 기록용

**Continuum semantics**: turn k의 prompt = turn k−1의 prompt + turn k−1의 생성 텍스트 + 새 segment. 즉 gap 후 재요청은 누적 transcript를 그대로 포함한다. tool gap은 client 측 `sleep`으로 모사한다.

## 실험 격자

### 공통

| 항목 | 값 |
|---|---|
| Model | `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음) |
| Server | `vllm serve <artifact> --host 127.0.0.1 --port 8000 --enable-prefix-caching` |
| 환경변수 | `VLLM_LOGGING_LEVEL=DEBUG`, `VLLM_RBLN_METRICS=1` |
| 세션 수 | **8** (동시) |
| Sampling | `temperature=0.0`, `top_p=1.0`, seed 20260819 |
| plan seed | `base_seed=20260821` |
| server | 관측마다 **fresh server** |

### 관측 A — 생성 길이만 분산 (gap 없음)

| 항목 | 값 |
|---|---|
| turn 수 | 1 |
| 첫 segment | 300 token (세션마다 유일 내용) |
| 생성 길이 | **ladder 64, 96, 128, 160, 192, 224, 256, 288** (세션 s는 `64 + 32·s`) |
| gap | 없음 |

8 세션이 동시에 시작해 **32 step 간격으로 하나씩 끝난다.** 따라서 `request_nums`가 8 → 7 → … → 1로 내려가고 bucket이 그에 맞춰 전이해야 한다.

첫 segment를 300 token으로 잡은 이유: prefix cache 문턱 129를 넘기지만([TASK11](TASK11.md)) outer slot 소비는 세션당 1개로 유지해 관측 A가 slot 압력에 오염되지 않게 한다.

### 관측 B — gap 추가

| 항목 | 값 |
|---|---|
| turn 수 | 2 |
| 첫 segment | 2,000 token (세션마다 유일) |
| 이후 segment | 8 token |
| 생성 길이 | uniform 32–64 |
| gap | uniform **1–6 초** (세션마다 다름 → turn 2 도착이 흩어진다) |

turn 1이 세션마다 outer slot 1개씩 총 8개를 채운다(`outer_slot_count = 8`). 그 뒤 각 세션의 turn 2가 gap을 두고 도착한다.

## 판정 기준

**counter와 로그로 판정한다. latency는 판정에 쓰지 않는다.**

### 판정 A — bucket 전이 관측

`[BUCKET]` 로그에서 `(request_nums, padded_batch_size)` 쌍의 **시간 순서**를 본다.

| 판정 | 조건 |
|---|---|
| **전이 관측됨** | 한 server lifetime 안에서 `padded_batch_size`가 **8 → 4 → 2 → 1** 로 단조 감소하는 구간이 존재하고, 각 전이 시점의 `request_nums`가 [TASK13](TASK13.md)의 사상표와 일치한다 |
| 부분 관측 | 일부 전이만 나타남. 나타난 것과 빠진 것을 기록하고 `PARTIAL` |
| 미관측 | 전이가 없음. 설계가 전이를 만들지 못한 이유를 기록하고 `PARTIAL` |

사상표(전건 일치를 요구): 8→8, 7→8, 6→8, 5→8, 4→4, 3→4, 2→2, 1→1.

### 판정 B — gap 재개 attribution

각 세션 turn 2의 층 2 재사용을 [TASK15](TASK15.md)에서 확정한 채널로 판정한다.

- 층 2 재사용 = `vllm:prompt_tokens_cached_total` 증분
- 실제 계산량 = `vllm:request_prefill_kv_computed_tokens_sum` 증분
- 대조 = `vllm:prefix_cache_hits_total`(층 1)과 `[PFX]` 로그

turn 2의 전생존 기대 재사용은 turn 1 prompt와의 공유 prefix에서 나오며, 세션마다 생성 길이가 달라 값이 다르므로 **세션별로 산식으로 계산해 기록**한다.

| 판정 | 조건 |
|---|---|
| 재사용 성공 | 층 2 `cached` > 0 |
| 재사용 실패 | 층 2 `cached` = 0 |

**성공 세션 수를 그대로 보고한다.** 특정 개수를 요구하지 않는다.

### FAIL / PARTIAL 처리 규칙 (측정 전 고정)

| 상황 | 판정 |
|---|---|
| patch state가 `patched`가 아님 | `BLOCKED` |
| server 기동 실패 또는 요청 non-200 | `FAILED` |
| 관측 A에서 전이가 하나도 없음 | `PARTIAL`, 원인 기록 |
| `[BUCKET]` 사상이 [TASK13](TASK13.md) 표와 어긋남 | 판정 보류, 불일치 기록 |
| 종료 후 device memory 미복귀 | `PARTIAL` |

## 사전 예측 (판정 기준 아님)

| # | 예측 | 근거 |
|---|---|---|
| 1 | 관측 A에서 8 → 4 → 2 → 1 전이가 전부 나타난다 | ladder 생성 길이가 32 step 간격으로 세션을 끝낸다 |
| 2 | 전이 시점의 사상이 [TASK13](TASK13.md) 표와 전건 일치 | `select_bucket_size` |
| 3 | 관측 A에서 `request_nums = 7, 6, 5`가 모두 나타난다 | 세션이 하나씩 빠진다 |
| 4 | **관측 B에서 turn 2의 층 2 재사용이 8 세션 전부 실패한다 (0/8)** | 아래 참조 |
| 5 | 관측 B에서 층 1 `hits`는 0이 아닌 값을 보고한다 | [TASK15](TASK15.md)의 거짓 양성 |
| 6 | 관측 B에서 `[PFX] [EVICTION]`이 최소 8회 | 세션당 turn 2가 slot 1개씩 요구 |

**예측 4의 근거**: turn 1이 8개 slot을 모두 채운 상태에서 turn 2는 **새 request_id**로 등록되므로(`is_request_registered`가 False) 새 outer slot을 요구한다. free slot이 0이므로 `can_allocate`가 먼저 FIFO eviction을 수행하고, `_allocation_order`에서 가장 이른 inactive mapping이 곧 그 세션 자신 또는 다른 세션의 turn 1 slot이다. 게다가 재사용은 **원본 slot과 새 slot이 동시에 필요**하다(`get_matched_outer_blocks`가 둘의 disjoint를 assert하고 `copy_cached_kv_blocks`가 복사한다). 따라서 pool이 가득 찬 상태에서는 재사용이 성립하기 어렵다.

예측 4는 이 파일럿에서 가장 확신도가 낮으면서 가장 흥미로운 항목이다. 빗나가면 그 자체가 결과다.

## 필수 측정 항목

- 관측 A·B별: 전 요청 status·`usage`·counter 증분, 세션별 start/end wall-clock
- `[BUCKET]` 로그 전문과 `(request_nums, padded_batch_size)` 쌍의 시간 순서
- `[PFX]` 로그 전문 (ALLOC / EVICTION / CACHE-HIT / CACHE-PARTIAL)
- plan summary (requested condition)
- patch state, `rbln-smi`(기동 전·종료 후), provenance 일체

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-agentic-pilot`

관측 A·B 각각: `apply.sh status` 확인 → server 기동 → `/health` 대기 →

```bash
env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage2/agentic_pilot.py \
  --base-url http://127.0.0.1:8000 \
  --tokenizer-dir /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb \
  --sessions 8 --turns <1|2> \
  --first-segment-tokens <300|2000> --later-segment-tokens 8 \
  --generation <ladder:64:32|uniform:32:64> --gap <fixed:0|uniform:1:6> \
  --base-seed 20260821 --block-id <obsA|obsB> --sampling-seed 20260819 \
  --output-dir <절대경로>/<RUN>/probe
```

→ PID 특정 후 `SIGTERM` → 종료 확인 → 로그 집계

## 산출

1. generator 사용법
2. 관측된 전이 사례 (시간 순서 포함)
3. 본 characterization 격자 설계에 필요한 **미지수 목록**

**utilization 저하의 정량 주장은 하지 않는다.**

## 관련 문서

- [TASK13](TASK13.md) — 사상표와 step 비용 모형
- [TASK15](TASK15.md) — 층 2 attribution 채널
- [TASK16](TASK16.md) — substrate descriptor, 층 태그 규칙
- [TASK12](TASK12.md) — bucket 전이 미관측의 출처
