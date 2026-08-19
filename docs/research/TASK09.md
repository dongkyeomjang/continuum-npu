# TASK09 — Stage 1a: 기존 b1 artifact로 serving bring-up과 관측 감사

## 상태

DONE

## 판정

Stage 1a = **`PASS`**. 선등록한 5개 조건을 전부 충족했다.

## 날짜

2026-08-19

## 목적

`vllm serve` 경로 자체를 검증하고, 이후 Stage에서 쓸 관측 신호를 감사한다. 재compile 없이 [TASK06](TASK06.md)이 만든 `models/Qwen3-4B-rbln-b1-s8192-d4`를 그대로 쓴다.

## 배경

관련 TASK:

- [TASK06](TASK06.md) — Stage 0 `PASS`. b1 artifact의 출처이며 `num_gpu_blocks=130`을 `UNKNOWN`으로 남겼다.
- [TASK08](TASK08.md) — compile 파라미터와 KV accounting을 source로 확정하고 이 TASK의 예측을 만들었다.

선등록 문서: [STAGE1A_PREREG.md](STAGE1A_PREREG.md)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `318c430ccd412e555d98589b11cf826e2be3be62`
- Git dirty: untracked `.idea/`만
- Host: `atom-max8`, Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`
- Device: 32 visible ID 전부 idle (`0.0B / 15.7GiB`, context 없음)
- Port 8000 비어 있음, `/` 사용률 8 %

## 수행 내용

1. 선등록 문서, 관측 시퀀스 client script, 고정 prompt를 **측정 시작 전에** commit했다 (`318c430`).
2. 기동 전 `rbln-smi`와 port를 확인했다.
3. `VLLM_LOGGING_LEVEL=DEBUG`로 server를 기동하고 `/health` 200까지 대기했다. 별도 shell에서 `rbln-smi`를 1초 주기로 폴링했다.
4. 선등록한 관측 시퀀스를 격리 launcher로 실행했다 (`/health` → `/v1/models` → `/metrics` → 단일 요청 → `/metrics` → streaming → `/metrics` → 동시 2개 → `/metrics`).
5. **선등록 시퀀스 외 추가 관측**을 2회 수행했다 (아래 "추가 관측" 절). 판정 기준은 변경하지 않았다.
6. Server를 `SIGTERM`으로 종료하고 process 부재, port 해제, device memory 복귀, context 소멸을 확인했다.

RSD, device state, package, site-packages, `patches/`는 변경하지 않았다. `RBLN_DEVICES`는 설정하지 않았다. 재compile은 없었다.

## 변경된 파일

선등록 commit `318c430`:

- `docs/research/STAGE1A_PREREG.md` (신규)
- `experiments/npu/stage1/serving_probe.py` (신규)
- `experiments/npu/stage1/prompt.txt` (신규)

이번 기록 commit:

- `docs/research/TASK09.md` (신규)
- `docs/research/INDEX.md`

Raw artifact는 `.gitignore` 대상인 `results/npu/stage1/20260819-173100-stage1a-b1-serving/`에 있다.

## 실험 또는 검증 방법

`<RUN>` = `results/npu/stage1/20260819-173100-stage1a-b1-serving`

```bash
rbln-smi > <RUN>/rbln-smi-before.txt

env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG vllm serve \
  /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b1-s8192-d4 \
  --host 127.0.0.1 --port 8000 > <RUN>/server.log 2>&1 &

# /health 200까지 1초 간격 폴링
# 별도 shell: rbln-smi 1초 폴링 -> <RUN>/probe/rbln-smi-poll.txt

env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage1/serving_probe.py \
  --base-url http://127.0.0.1:8000 \
  --prompt-file /home/rebel/continuum-npu/experiments/npu/stage1/prompt.txt \
  --max-tokens 32 --seed 20260819 --concurrency 2 \
  --output-dir /home/rebel/continuum-npu/<RUN>/probe

kill -TERM <server pid>
rbln-smi > <RUN>/rbln-smi-final.txt
```

## 결과

### 조건 분리

- `requested_condition`: b1 artifact, `max_tokens=32`, greedy(`temperature=0.0`, `top_p=1.0`), seed 20260819, 요청 1개 → streaming 1개 → 동시 2개, `RBLN_DEVICES` 미설정, `VLLM_LOGGING_LEVEL=DEBUG`만 설정.
- `observed_condition`: 위 조건이 그대로 적용됐다. served model id는 artifact 절대 경로였고, resolved `max_num_seqs=1`, `max_model_len=8192`, `block_size=128`, `enable_prefix_caching=True`였다. 실행 device는 `rbln0`–`rbln3`이었다.
- `condition_reached`: `YES`.

### 관찰 — 기동과 resolved config

Population: server 인스턴스 1개. Source: `vllm serve` 로그(`<RUN>/server.log`, 478줄). Device scope: `rbln0`–`rbln3`.

| 항목 | 값 |
|---|---|
| 기동 요청 → `/health` 200 | 2026-08-19 17:31:10 → 17:31:51 (약 41 s, 폴링 1 s 해상도) |
| served model id | `/home/rebel/continuum-npu/models/Qwen3-4B-rbln-b1-s8192-d4` |
| `max_model_len` | 8192 (40960에서 갱신) |
| `max_num_batched_tokens` | 128 (2048에서 갱신) |
| `enable_prefix_caching` | `True` |
| scheduler | `vllm_rbln.v1.core.optimum_scheduler.RBLNOptimumScheduler` |
| `GPU KV cache size` | 8,320 tokens |
| `Maximum concurrency for 8,192 tokens per request` | 1.02x |

`max_num_batched_tokens` 갱신의 출발값이 Stage 0의 8192가 아니라 2048인 것은 offline `LLM` API와 `vllm serve`의 vLLM 기본값 차이다. 결과값 128은 동일하다.

### 관찰 — `num_gpu_blocks` 2배 anomaly **해소**

[TASK06](TASK06.md)의 `UNKNOWN`이 해소됐다. 같은 로그에 두 값이 모두 나타난다.

```text
(APIServer  pid=288189) DEBUG [v1/metrics/loggers.py:285]
    Engine 000: vllm cache_config_info with initialization after num_gpu_blocks is: 130
(EngineCore pid=288492) DEBUG [vllm_rbln/.../converter/from_optimum.py:133]
    num_blocks already synced to 65, skipping...
```

원인은 `vllm/v1/engine/core_client.py:710–714`다.

```python
# Setup KV cache config with initialization state from
# engine core process. Sum values from all engines in DP case.
num_gpu_blocks = vllm_config.cache_config.num_gpu_blocks or 0
num_gpu_blocks += response.num_gpu_blocks
vllm_config.cache_config.num_gpu_blocks = num_gpu_blocks
```

vLLM은 이 field가 frontend에서 비어 있다고 가정하고 EngineCore 보고값을 **누적**한다 (DP 합산 용도). 그런데 vllm-rbln의 `check_and_update_config`가 frontend에서 이미 `update_num_blocks`로 65를 써 넣기 때문에, EngineCore가 보고한 65가 그 위에 더해져 **130**이 된다.

즉 130은 **65의 이중 계상**이며 실제 KV pool은 65 inner block이다. [TASK08](TASK08.md)이 source로 유도한 `1 × 64 + 1 = 65`, 그리고 log의 8,320 token(`max_concurrency 1.0156 × 8192`)과 정합한다.

### 관찰 — 요청 응답

Population: 요청 4개(단일 1, streaming 1, 동시 2). Unit: token, 초. Source: HTTP 응답과 `/metrics`.

| 요청 | status | prompt tok | completion tok | finish | e2e (s) |
|---|---|---|---|---|---|
| 단일 | 200 | 12 | 32 | `length` | 0.376 |
| streaming | 200 | 12 | 32 (chunk 32개) | — | 0.347 |
| 동시 #0 | 200 | 17 | 32 | `length` | 0.348 |
| 동시 #1 | 200 | 17 | 32 | `length` | 0.687 |

단일 요청 출력 (조건 2 판정 근거):

```text
 A neural processing unit (NPU) is a specialized piece of hardware designed to efficiently handle tasks related to artif
```

빈 문자열이 아니고, output token 32개이며, 일반 단어 문자를 포함한다. 조건 2 충족.

모든 latency는 1회 관측값이다. 통계적 주장을 하지 않는다.

### 관찰 — NPU 실행 증거

Source: `rbln-smi` 1초 폴링 194 snapshot + 기동 전/종료 후 캡처. Device scope: 전 32 ID.

- Memory: `rbln0`–`rbln3`가 `0.0B` → `2.2GiB`(`rbln0`은 `2.3GiB`). 나머지 28개 ID는 전 구간 `0.0B`.
- Utilization: 최대 88.6(`rbln0`), 87.9(`rbln1`, `rbln2`), 87.8(`rbln3`). Baseline 전부 `0.0`.
- Context: `VLLM::EngineCor` PID 288492가 context 목록에 출현 (폴링 전체에서 5,692 row).

세 신호 모두 관측됐다. 조건 4 충족.

Stage 0의 device당 2.2 GiB와 동일하다. [TASK08](TASK08.md)의 파생 예측 2.15 GiB/device와도 어긋나지 않는다.

### 관찰 — 종료와 자원 해제

Server를 `SIGTERM`으로 종료했고 로그에 `Shutdown initiated (timeout=0)` → `Shutdown complete` → `v1 optimum_worker shutdown called` → `Application shutdown complete`가 순서대로 기록됐다. 종료 후:

- `vllm serve` process 부재
- port 8000 해제
- `rbln0`–`rbln3` memory `0.0B / 15.7GiB`로 복귀
- Context Information이 `N/A`(빈 상태)로 복귀

조건 5 충족. `resource_tracker: There appear to be 1 leaked semaphore objects` 경고가 종료 시 1회 출력됐으나 device 자원과는 무관하며 device는 완전히 해제됐다.

### 관측 감사 1 — `/metrics`

`/metrics`는 4회 스냅샷 모두 200이었고 **metric 이름 122개**를 노출했다 (`vllm:` 96, `http_` 16, `python_`/`process_` 10). 전체 목록은 `<RUN>/probe/metric_names.txt`에 있다. 조건 3 충족.

**KV·큐·prefix cache 관련 항목의 의미론 검증 결과:**

| metric | 상태 | 근거 |
|---|---|---|
| `vllm:num_requests_running` | **채택 가능** | in-flight 폴링에서 `{0.0, 1.0}` 관측. 동시 요청 3개에서도 최대 1.0 |
| `vllm:num_requests_waiting` | **채택 가능** | in-flight 폴링에서 `{0.0, 1.0, 2.0}` 관측. server 로그의 `Waiting: 1/2 reqs`와 일치 |
| `vllm:kv_cache_usage_perc` | **채택 가능** | in-flight 폴링에서 `{0.0, 0.015625, 0.03125}` 관측. 각각 inner block 0/1/2개 ÷ 64 |
| `vllm:prefix_cache_queries_total` | **채택 가능 (단위 주의)** | 0 → 12 → 24 → 58로 증가. 증가량이 요청의 **prompt token 수**와 일치하므로 단위는 요청이 아니라 token |
| `vllm:prefix_cache_hits_total` | **노출되나 미검증** | 전 구간 0.0. 동일 prompt를 반복해도 0이었다 |
| `vllm:prompt_tokens_cached_total` | **노출되나 미검증** | 전 구간 0.0 |
| `vllm:num_preemptions_total` | **노출되나 미검증** | 전 구간 0.0. 이번 부하에서 preemption이 발생하지 않았을 뿐일 수 있다 |
| `vllm:external_prefix_cache_*`, `vllm:mm_cache_*` | 해당 없음 | 이 구성에서 사용되지 않는 경로 |
| `vllm:estimated_flops_per_gpu_total` 등 | **노출되나 0 고정** | RBLN 경로에서 채워지지 않는 것으로 보인다 |

값이 실제로 움직인 metric(4 스냅샷 기준, `_created` 제외)은 `vllm:request_*`, `vllm:e2e_request_latency_seconds*`, `vllm:time_to_first_token_seconds*`, `vllm:inter_token_latency_seconds*`, `vllm:generation_tokens_total`, `vllm:prompt_tokens_total`, `vllm:iteration_tokens_total*`, `vllm:request_queue_time_seconds*`, `vllm:request_prefill_time_seconds*`, `vllm:request_decode_time_seconds*`, `vllm:request_prefill_kv_computed_tokens*`, `vllm:request_success_total`과 `http_*`/`process_*` 계열이다.

**`vllm:kv_cache_usage_perc`의 분모는 64다.** 관측된 0.015625 = 1/64이고 EngineCore `num_gpu_blocks`는 65다. `vllm_rbln/v1/core/optimum_block_pool.py:94`가 마지막 block을 `dummy_block`으로 예약하므로 가용 block이 64개인 것과 정합한다.

**per-step decoder bucket을 담는 metric은 없다.** [TASK08](TASK08.md)의 예측대로다.

### 관측 감사 2 — streaming과 TTFT

`stream:true`가 동작했다. status 200, content chunk 32개, 첫 content chunk까지 **0.0309 s**, 전체 0.347 s.

이 값은 client 측 wall-clock이며 server 내부 TTFT가 아니다. server가 별도로 노출하는 `vllm:time_to_first_token_seconds`(단일 요청 후 sum 0.0483 s)와는 다른 값이다. 두 값 모두 1회 관측이며 통계적 주장을 하지 않는다.

### 관측 감사 3 — 동시 요청 2개의 거동

**거부도 오류도 아니었다. 두 요청 모두 200으로 성공했고 순차 처리됐다.**

- 동시 #0: 시작 0.0005 s, 종료 0.3482 s, e2e 0.348 s
- 동시 #1: 시작 0.0013 s, 종료 0.6880 s, e2e 0.687 s
- pairwise wall-clock overlap: 0.347 s

overlap 자체는 동시 실행의 증거가 아니다(선등록에서 사전 제약). 실제 근거는 두 가지다.

1. `vllm:request_queue_time_seconds_sum`이 동시 요청 직후 0.00070 → **0.3167 s**로 뛰었다. 즉 두 번째 요청이 약 0.316 s 큐에서 대기했고, 이는 첫 요청의 e2e 0.348 s와 거의 같다.
2. in-flight 폴링에서 `vllm:num_requests_running`이 **한 번도 1을 넘지 않았다** (동시 요청 3개인 추가 관측에서도 동일). 같은 구간에 `vllm:num_requests_waiting`은 최대 2였다.

`batch_size=1` artifact가 동시 sequence를 처리하지 못하고 큐에 세운다는 [TASK08](TASK08.md)의 예측과 일치한다.

### 추가 관측 (선등록 시퀀스 외)

선등록 시퀀스의 `/metrics` 스냅샷 4회가 **전부 요청 사이(idle)** 에 찍혀 `num_requests_running`/`waiting`/`kv_cache_usage_perc`의 live 여부를 판정할 수 없었다. 이 세 metric의 채택 가능성은 이후 Stage 전체의 관측 설계를 좌우하므로, server가 살아 있는 동안 **in-flight 샘플링**을 추가로 수행했다.

- 방식: 동시 요청 3개(`max_tokens=200`)를 보내면서 `/metrics`를 50 ms 주기로 폴링.
- 이 추가 관측은 **PASS 조건을 바꾸지 않는다.** 판정은 선등록한 5개 조건으로만 했다.
- 1차 시도는 무효였다 (아래 "실패 / 무효 시도"). 2차 수정본의 결과를 위 감사표에 반영했다.
- 2차 관측을 위해 server를 한 번 더 기동·종료했다. 두 lifecycle 모두 device memory가 `0.0B`로 복귀했다.

### 선등록 PASS 조건 대조

| # | 조건 | 결과 | 근거 |
|---|---|---|---|
| 1 | b1 artifact로 정상 기동 + resolved config 기록 | 충족 | `/health` 200, `/v1/models` 200, 로그의 resolved config |
| 2 | endpoint 요청 1개 성공 + 유의미한 텍스트 | 충족 | 200, 32 token, 영문 단어 다수 |
| 3 | `/metrics` 200 + metric 전체 목록 기록 | 충족 | 122개, `metric_names.txt` |
| 4 | NPU 실행 증거 | 충족 | memory·utilization·context 3개 신호 모두 |
| 5 | 정상 종료 + device memory `0.0B` 복귀 | 충족 | process 부재, port 해제, memory `0.0B`, context 소멸 |

**판정: `PASS`.** 측정 후 기준을 완화하거나 조정하지 않았다.

## 핵심 발견

1. **`num_gpu_blocks` 2배 anomaly가 해소됐다.** vLLM frontend가 EngineCore 보고값을 DP 합산 목적으로 **누적**하는데(`core_client.py:712`), vllm-rbln이 frontend에서 같은 field를 미리 채우기 때문에 이중 계상된다. 실제 KV pool은 65 inner block이며 frontend 값 130은 무의미하다. TASK06의 `UNKNOWN`이 닫혔다.
2. **`vllm:kv_cache_usage_perc`가 살아 있고 inner block 단위로 움직인다.** 분모는 `num_gpu_blocks - 1 = 64`(마지막 block은 dummy로 예약). 이는 Stage 2 KV pressure 관측의 **1차 신호로 채택 가능**하다.
3. **`num_requests_running` / `num_requests_waiting`도 살아 있다.** b1 artifact에서 running은 최대 1, waiting은 최대 2였다. 동시성 판정의 log·metric 근거로 쓸 수 있다.
4. **b1 artifact는 동시 요청을 거부하지 않고 큐에 세운다.** 두 요청 모두 성공했고 두 번째가 0.316 s 대기했다. "요청이 다 성공함"은 동시 실행의 증거가 아님이 실측으로 확인됐다.
5. **`prefix_cache_queries_total`의 단위는 요청이 아니라 token이다.** 증가량이 각 요청의 prompt token 수와 정확히 일치했다. 이름만 보고 요청 수로 해석하면 안 된다.
6. **동일 prompt를 반복해도 `prefix_cache_hits_total`이 0이었다.** APC가 켜져 있는데도 hit이 없다.
7. **server의 주기 로그가 동시성 관측 경로다.** `Running: N reqs, Waiting: M reqs, GPU KV cache usage: X%, Prefix cache hit rate: Y%` 형식이며 실제로 `Running: 1, Waiting: 2`가 찍혔다. 다만 로그 주기가 약 10 s여서 짧은 요청은 놓친다.
8. `vllm serve` 기동은 약 41 s이고 device 점유는 Stage 0 offline 경로와 동일한 2.2 GiB/device다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(hypothesis)** prefix cache hit이 0인 것은 outer block이 8,192 token인데 prompt가 12–19 token뿐이라 **완성된 block이 하나도 없기** 때문일 가능성이 높다. vLLM의 prefix caching은 가득 찬 block 단위로 hash·재사용하므로, block 경계에 못 미치는 prompt는 캐시 대상이 되지 않는다. 이 가설이 맞다면 Stage 2의 repeated-prefix 실험은 **prefix 길이가 최소 한 개의 block 경계를 넘도록** 설계해야 한다. 이 stack에서 그 경계가 inner block 128인지 outer block 8,192인지는 아직 확인하지 않았다(아래 `UNKNOWN`). 후자라면 요구 prefix 길이가 8,192 token이므로 실험 설계에 큰 영향을 준다.
- **(해석)** `kv_cache_usage_perc`가 1/64 단위로만 변한다는 것은 이 지표의 **해상도가 inner block**이라는 뜻이다. token 단위의 연속적 KV 압력을 이 지표로 관측할 수 없다. b1에서는 64단계뿐이므로 Stage 2에서 미세한 압력 변화를 보려면 block 수가 큰 구성이 필요하다.
- **(해석)** frontend와 EngineCore가 같은 이름의 config field에 서로 다른 값을 갖는 구조가 확인됐다. 이는 `num_gpu_blocks`만의 문제가 아닐 수 있다. 이후 resolved config를 기록할 때는 **어느 process에서 읽었는지**를 항상 함께 남긴다.
- **(해석)** 동시 요청 #1의 e2e 0.687 s ≈ #0의 e2e 0.348 s × 2다. 순차 처리에서 기대되는 값이지만 1회 관측이므로 비례 관계를 주장하지 않는다.

## 확인되지 않은 사항

- prefix cache의 hit 단위가 inner block(128 token)인지 outer block(8,192 token)인지 (`UNKNOWN`). Stage 2 설계에 직결되므로 우선 해소 대상이다.
- `vllm:prefix_cache_hits_total`, `vllm:prompt_tokens_cached_total`, `vllm:num_preemptions_total`이 이 stack에서 실제로 채워지는 경로가 있는지 (`UNKNOWN`). 이번 부하에서 0이었을 뿐일 수 있다.
- `vllm:estimated_flops_per_gpu_total` 계열이 RBLN에서 채워지지 않는 것이 설계인지 (`UNKNOWN`, 이번 연구에 필요하지 않아 추적하지 않았다).
- server 내부 TTFT와 client 측 first-chunk 시간의 차이 원인 (0.0483 s vs 0.0309 s). 1회 관측이라 차이를 해석하지 않았다.
- 종료 시 `leaked semaphore` 경고의 원인 (`UNKNOWN`). device 자원은 완전히 해제됐으므로 이번 판정에 영향이 없다.
- `batch_size > 1` artifact에서 running이 1을 넘는지 (Stage 1b의 PASS 조건).

## 실패 / 무효 시도

1. **in-flight metric 샘플러 1차 시도가 무효였다.** 임시 스크립트가 `line.startswith("vllm:num_requests_waiting")`로 metric을 골랐는데, 이 접두어는 `vllm:num_requests_waiting_by_reason{...}`에도 매칭되어 마지막 매칭 줄의 값으로 덮어써졌다. 그 결과 waiting이 항상 0.0으로 읽혔다. Server 로그에 `Waiting: 1 reqs` / `Waiting: 2 reqs`가 찍혀 있어 불일치를 발견했고, metric 이름을 정확히 일치시키도록 수정해 재측정했다. 수정본에서 waiting은 `{0.0, 1.0, 2.0}`으로 관측됐다.
   - 저장소의 `experiments/npu/stage1/serving_probe.py`는 `parse_prometheus`가 이름과 label을 정확히 분리하므로 이 버그의 영향을 받지 않는다. 무효였던 것은 임시 스크립트뿐이다.
   - 두 스크립트 모두 `<RUN>/probe/inflight_sampler_{buggy,corrected}.py`로 보존했다.
2. Server 종료 시 `pkill -TERM -f "vllm serve ..."` 패턴이 그 명령을 실행한 shell 자신의 command line에도 매칭되어 shell이 함께 종료됐다(exit 144). Server는 정상적으로 SIGTERM을 받아 graceful shutdown했고 device도 해제됐으므로 측정에는 영향이 없다. 2차 종료에서는 `pgrep`으로 PID를 특정해 `kill`했다.
3. Device·RSD·package·site-packages 변경은 없었다.

## 연구 원칙에 미치는 영향

- **신호는 이름이 아니라 움직임으로 채택한다.** `/metrics`에 이름이 있어도 값이 움직이지 않는 항목이 여럿이었다(`prefix_cache_hits_total`, `prompt_tokens_cached_total`, `estimated_flops_*`). 채택 전 "실제로 변하는가"를 확인하고, 확인하지 못했으면 "노출되나 미검증"으로 분류한다.
- **idle 시점 스냅샷으로 gauge를 판정하지 않는다.** 요청 사이에만 찍은 스냅샷으로는 running/waiting/usage가 살아 있는지 알 수 없다. gauge는 반드시 in-flight로 표집한다.
- **metric 파싱은 접두어가 아니라 정확한 이름으로 한다.** Prometheus는 접두어를 공유하는 이름을 허용한다. 이번에 실제로 오독이 발생했다.
- **불일치는 교차 확인으로 잡는다.** 로그와 metric이 어긋난 것이 무효 측정을 발견한 계기였다. 중요한 신호는 두 경로로 확인한다.
- **wall-clock overlap을 동시 실행의 증거로 쓰지 않는다.** 선등록에 이 제약을 명시해 두었고, 실제로 overlap이 있었지만 순차 처리였다.
- **metric의 단위를 산식으로 확인한다.** `prefix_cache_queries_total`은 요청이 아니라 token 단위였다.

## 다음 작업

Stage 1b — [TASK08](TASK08.md)의 권고안(`--batch_size 8 --decoder_batch_sizes 1,2,4,8 --max_seq_len 8192 --num_devices 4`)으로 재compile하고 동시성에 진입해 decoder bucket 관측 가능성을 판정한다. 측정이 포함되므로 선등록 후 진행한다.

이번 결과에서 Stage 1b로 이월할 사항:

- 동시 실행 판정의 근거는 `vllm:num_requests_running > 1`과 server 주기 로그의 `Running: N reqs`다. 두 경로 모두 살아 있음을 확인했다.
- `/metrics`는 in-flight로 표집해야 하며 metric 이름은 정확히 일치시켜야 한다.
- resolved config를 기록할 때 frontend와 EngineCore를 구분한다. frontend `num_gpu_blocks`는 EngineCore 값의 2배로 나올 것이다.

## 재현 정보

- 선등록 commit: `318c430ccd412e555d98589b11cf826e2be3be62`
- **측정 시작 시각: 2026-08-19 17:31:03 KST.** 선등록 commit 시각은 2026-08-19 17:30:55 KST이므로 **선등록이 측정보다 8초 앞선다.**
- 측정 종료 시각: 2026-08-19 17:37:06 KST
- Base commit (측정 중 HEAD): `318c430ccd412e555d98589b11cf826e2be3be62`, dirty = untracked `.idea/` 및 gitignored `results/`, `models/`
- Model artifact: `models/Qwen3-4B-rbln-b1-s8192-d4/` (TASK06 산출, 무변경)
- Raw artifact: `results/npu/stage1/20260819-173100-stage1a-b1-serving/`
  - `measurement-start.txt`, `measurement-end.txt`, `df.txt`
  - `server.log`(1차, 478줄), `server2.log`(2차), `server-{start-requested,ready,stop-requested,exit}.txt`, `server2-*.txt`
  - `rbln-smi-{before,after-shutdown,final}.txt`
  - `probe/serving_probe.json` — 선등록 시퀀스 전체 기록과 `/metrics` 스냅샷 4회 전문
  - `probe/metric_names.txt` — 노출 metric 이름 122개
  - `probe/metrics_t0_idle.prom` — idle 스냅샷 원문
  - `probe/rbln-smi-poll.txt` — 1초 폴링 194 snapshot
  - `probe/inflight_metrics.json`(무효), `probe/inflight_metrics_corrected.json`(유효)
  - `probe/inflight_sampler_{buggy,corrected}.py`
- 실행 script: `experiments/npu/stage1/serving_probe.py`, `experiments/npu/stage1/prompt.txt`
- Isolation launcher: `experiments/npu/launch/run_isolated_python.sh`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch-rbln 0.3.0`, `torch 2.11.0+cpu`, `transformers 5.8.1`
- Host: `atom-max8`, KMD ver 3.2.2, device `rbln0`–`rbln3`
