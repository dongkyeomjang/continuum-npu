# 선등록 — per-request/per-session 귀속 채널 구축과 검증 게이트

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다.

## 목적

[TASK17](TASK17.md)이 "본 실험 전 필수"로 게이트화한 request id ↔ 세션 매핑을 구축하고, **동시성 하에서 per-request 귀속이 올바름을 구성상 정답이 알려진 실험으로 검증**한다.

**게이트가 실패하면 후속 짝 비교를 시작하지 않는다.**

## 승인 범위 (사용자 판정, 2026-08-19)

b8 artifact serving 기동·종료(횟수 무제한, PID 특정 확인), localhost 요청, DEBUG + `VLLM_RBLN_METRICS=1`, `src/continuum/` 및 `experiments/npu/` 코드 추가·수정.

범위 밖: 재compile, download, patch 추가·수정, RSD 변경, remote push 자동 수행.

### 이번에 추가하는 server flag

**`--enable-prompt-tokens-details`** 를 켠다.

- 근거: `vllm/entrypoints/openai/cli_args.py:135`의 `enable_prompt_tokens_details`가 `completion/serving.py:446-448`에서 `usage.prompt_tokens_details.cached_tokens`를 채운다.
- 값의 출처는 `RequestOutput.num_cached_tokens` → `req_state.num_cached_tokens` → `prefill_stats.num_cached_tokens` = `sum(cached_length)` = **층 2**([TASK15](TASK15.md)에서 확정한 경로).
- **실행 semantics를 바꾸지 않는다.** 응답에 필드를 하나 더 채울 뿐이며 scheduling·batching·KV 할당에 관여하지 않는다.

## Substrate 상태

측정 전 `apply.sh status`가 `patched`(SHA256 `70942d16…`)가 아니면 시작하지 않는다.

## 1. Join key 조사 결과 (측정 전)

### 경로

```
client 응답 body["id"]                       = request_id
   vllm/entrypoints/openai/completion/serving.py:144
       request_id = f"cmpl-{self._base_request_id(...)}"
   :398, :453  → 응답의 id=request_id

engine per-prompt id                         = f"{request_id}-{i}"
   :180  request_id_item = f"{request_id}-{i}"

server [PFX] 로그의 REQUEST=                  = cmpl-<base>-<i>-<suffix8>
```

관측된 실제 값의 예 ([TASK17](TASK17.md) 로그): 서버 `cmpl-81e2aa729659761a-0-abf5989a`, client `cmpl-a6c94a91613c383b` 형태.

**따라서 client id는 server가 로그하는 id의 strict prefix다.** join은 `server_id.startswith(client_id + "-")`로 하며 **timestamp 정렬이 필요 없다.**

말미의 8-hex suffix가 어디서 붙는지는 source에서 찾지 못했다 (`UNKNOWN`). join에는 영향이 없으나, **prefix join이 유일해야 한다는 것을 매 run마다 fail-loud로 검사**한다 (2개 이상 매칭되면 오류).

### 로그 timestamp 해상도

`vllm/logger.py:26`의 `_DATE_FORMAT = "%m-%d %H:%M:%S"` — **1초**다 ([TASK13](TASK13.md) 확인). 따라서 per-request 판정에 timestamp를 쓰지 않는다. id join이 1차 채널이다.

`[BUCKET]` 로그에는 request id가 없다. bucket은 step 단위 속성이므로 per-request join 대상이 아니며, 집계(utilization)에만 쓴다.

### 1차 채널 결정

| 용도 | 채널 | 귀속 방식 |
|---|---|---|
| **per-request 층 2 재사용** | 응답의 `usage.prompt_tokens_details.cached_tokens` | **구성상 귀속** (client가 자기 응답에서 읽는다) |
| per-request 실제 계산량 | `prompt_tokens − cached_tokens` | 위와 동일. vLLM의 `request_prefill_kv_computed_tokens` 산식과 같다 |
| per-request 층 2 결과 교차확인 | `[PFX]` 로그 | id prefix join |
| step 단위 batch | `[BUCKET]` 로그 | 집계 전용 |
| 총계 검산 | `/metrics`의 `request_prefill_kv_computed_tokens_sum` | 합계 대조 |

**counter 증분은 per-request 귀속에 쓰지 않는다** ([TASK17](TASK17.md) 발견 6).

## 2. Runner (측정 전 확정, 이 commit에 포함)

`experiments/npu/stage2/session_runner.py` — 요청마다 JSONL 한 줄:

`arm`, `block_id`, `session`, `session_index`, `turn`, **`request_id`**, `status`, `sent_s`/`done_s`(client 단조시계), `requested_generation_tokens`, `requested_segment_tokens`, `gap_after_s`, `prompt_tokens`, `completion_tokens`, **`cached_tokens`**, `at_utc`.

`--first-segment ladder:START:STEP`로 세션마다 **결정적으로 유일한** prompt 길이를 줄 수 있다. 게이트가 "구성상 정답"을 갖기 위한 장치다.

## 3. 검증 게이트 (측정 전 고정)

### 실험 구성

| 항목 | 값 |
|---|---|
| 세션 수 | **8** (동시) |
| 첫 segment | **ladder 300, 600, 900, 1200, 1500, 1800, 2100, 2400 token** (`ladder:300:300`) |
| 이후 segment | 8 token |
| turn 수 | 2 |
| 생성 길이 | 32 (고정 — 게이트는 전이가 아니라 귀속을 본다) |
| gap | 2 초 (고정) |
| Model | `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음) |
| Server | `--enable-prefix-caching --enable-prompt-tokens-details` |
| 환경변수 | `VLLM_LOGGING_LEVEL=DEBUG`, `VLLM_RBLN_METRICS=1` |
| seed | plan `base_seed=20260822`, sampling 20260819 |

세션마다 prompt 길이가 유일하므로 **turn 1의 계산량이 세션마다 서로 다른 알려진 값**이 된다. 이것이 "구성상 정답"이다.

### 게이트 조건

| 게이트 | 조건 | 통과 기준 |
|---|---|---|
| **G1** | turn 0(첫 turn)은 세션마다 유일한 내용이므로 층 2 재사용이 있을 수 없다. 각 세션의 `cached_tokens = 0`이고 따라서 `kv_computed = prompt_tokens`가 그 세션 고유값과 일치해야 한다 | **8/8** |
| **G2** | 전 요청(16개)에 대해 id prefix join으로 찾은 `[PFX]` 결과가 `cached_tokens`와 모순되지 않아야 한다. `CACHE-HIT`면 `cached > 0`, `CACHE-PARTIAL`이면 `cached = 0`. `[PFX]` 항목이 없는 요청은 검사 대상에서 제외하되 그 수를 기록한다 | **전건 일치** |
| **G3** | per-request `kv_computed`의 합이 server의 `request_prefill_kv_computed_tokens_sum` 총계와 일치해야 한다 (오차 < 0.5) | 일치 |

**join이 모호(2개 이상 매칭)하거나 `request_id`가 없으면 즉시 실패**다.

### 판정

| 상황 | 판정 |
|---|---|
| G1 8/8 + G2 전건 + G3 일치 | **게이트 통과.** 후속 짝 비교 진행 |
| G1 7/8 이하 | **FAIL.** 원인 규명 전 후속 작업 진입 금지 |
| G2 불일치 존재 | **FAIL.** 불일치 목록을 기록 |
| G3 불일치 | **FAIL.** 차이와 그 방향을 기록 |
| patch state가 `patched`가 아님 | `BLOCKED` |
| server 기동 실패 또는 요청 non-200 | `FAILED` |

FAIL 시 **후속 짝 비교를 시작하지 않고 보고 후 중단한다.**

## 사전 예측 (판정 기준 아님)

| # | 예측 | 근거 |
|---|---|---|
| 1 | G1 8/8 통과 | turn 1 prompt가 세션마다 유일 |
| 2 | `cached_tokens` 필드가 실제로 채워진다 (전부 `None`이 아니다) | `--enable-prompt-tokens-details` |
| 3 | turn 2에서 일부 세션만 `cached_tokens > 0` | [TASK17](TASK17.md)의 4/8 |
| 4 | G2 전건 일치 | 두 값이 같은 층 2 원천에서 나온다 |
| 5 | G3 일치 | 같은 산식 |
| 6 | 짧은 prompt 세션(300 token)의 turn 2도 재사용 가능 | 300 > 129 문턱 ([TASK11](TASK11.md)) |

예측 3은 게이트 통과 여부와 무관하다 — 게이트는 **재사용이 일어나는지**가 아니라 **귀속이 맞는지**를 본다.

## 필수 측정 항목

요청별 JSONL 전체, `[PFX]`·`[BUCKET]` 로그 전문, 최종 `/metrics` 덤프, join_check 결과 JSON, patch state, `rbln-smi`(기동 전·종료 후), provenance 일체.

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-attribution-gate`

1. `apply.sh status` → `patched` 확인, 아니면 중단
2. server 기동:

   ```bash
   env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG VLLM_RBLN_METRICS=1 \
     vllm serve <artifact> --host 127.0.0.1 --port 8000 \
     --enable-prefix-caching --enable-prompt-tokens-details
   ```

3. runner 실행 (`--first-segment ladder:300:300`, 8 세션, 2 turn, gap `fixed:2`)
4. 종료 직전 `/metrics`를 덤프
5. PID 특정 후 `SIGTERM`, 종료 확인
6. `experiments/npu/analysis/join_check.py`로 G1·G2·G3 판정

## 관련 문서

- [TASK17](TASK17.md) — 게이트를 요구한 출처, counter 증분 무효 발견
- [TASK15](TASK15.md) — 층 2 채널의 source 경로
- [TASK13](TASK13.md) — 로그 timestamp 1초 해상도
- [TASK11](TASK11.md) — hit 문턱 129 token
