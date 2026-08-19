# TASK10 — Stage 1b: multi-bucket compile과 동시성 진입, decoder bucket 관측 판정

## 상태

DONE

## 판정

Stage 1b = **`PASS`**. 선등록한 3개 조건을 전부 충족했다.

decoder bucket 관측 = **불가**. 등록한 4개 수단을 모두 검색했으나 per-step `(실제 요청 수, 선택된 bucket)`을 노출하는 경로가 없었다. [INDEX](INDEX.md)에 **결정 3**을 신설했다. Patch는 적용하지 않았다.

## 날짜

2026-08-19

## 목적

동시 sequence가 실제로 도는 상태를 만들고, decoder bucket 선택이 runtime에서 관측 가능한지 판정한다. Track A(bucket characterization) 진입 gate다.

## 배경

관련 TASK:

- [TASK08](TASK08.md) — compile 파라미터 공간과 KV accounting을 source로 확정하고 이 TASK의 파라미터 권고안과 사전 예측표를 만들었다.
- [TASK09](TASK09.md) — Stage 1a `PASS`. 관측 신호를 감사해 `num_requests_running`/`waiting`/`kv_cache_usage_perc`가 live함을 확인했고, b1 artifact가 동시 요청을 큐에 세운다는 것을 관측했다.
- [TASK06](TASK06.md) — Stage 0 `PASS`. compile cost 기준선(165 s / 9.083 GiB).

선등록 문서: [STAGE1B_PREREG.md](STAGE1B_PREREG.md)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `1796eed0d08597097baa0b01ce8bf2ddd048a82c`
- Git dirty: untracked `.idea/`만
- Host: `atom-max8`. Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`
- Device: 32 visible ID 전부 idle. Server 미기동, port 8000 비어 있음
- Disk: `/` 사용률 8 % (60 GiB), `models/` 9.1 GiB
- Model: `Qwen/Qwen3-4B` revision `1cfa9a7208912126459214e8b04321603b3df60c` (기존 HF cache 재사용, 재download 없음)

## 수행 내용

1. 선등록 문서와 동시성 sweep client script를 **측정 시작 전에** commit했다 (`1796eed`).
2. compile 전 device·disk 상태를 캡처하고 server 미기동을 확인했다.
3. 승인 파라미터로 compile 1회를 수행했다 (`timeout 1800`, `/usr/bin/time -v`). 진단 재시도는 필요하지 않았다.
4. 새 artifact로 server를 기동하고 동시성 1 → 2 → 4 → 8 sweep을 실행하며 `/metrics`를 50 ms 주기로 in-flight 표집했다.
5. 선등록한 4개 수단으로 decoder bucket 관측 가능성을 검색했다. 수단 3(`VLLM_RBLN_METRICS=1`)을 위해 server를 한 번 더 기동·종료했다.
6. 두 server lifecycle 모두 `SIGTERM`으로 종료하고 process 부재·port 해제·device memory 복귀·context 소멸을 확인했다.

RSD, device state, package, site-packages는 변경하지 않았다. `patches/`는 적용하지 않았다. `RBLN_DEVICES`는 설정하지 않았다. 신규 download는 없었다.

## 변경된 파일

선등록 commit `1796eed`:

- `docs/research/STAGE1B_PREREG.md` (신규)
- `experiments/npu/stage1/concurrency_probe.py` (신규)

이번 기록 commit:

- `docs/research/TASK10.md` (신규)
- `docs/research/INDEX.md` (Task Index, 현재 상태, **결정 3 신설**)

Raw artifact는 `.gitignore` 대상인 `results/npu/stage1/20260819-174300-stage1b-b8-multibucket/`에, compile artifact는 `models/Qwen3-4B-rbln-b8-s8192-d4-mb/`에 있다.

## 실험 또는 검증 방법

`<RUN>` = `results/npu/stage1/20260819-174300-stage1b-b8-multibucket`

```bash
# 1. compile (승인 파라미터 그대로)
env -u PYTHONPATH /usr/bin/time -v timeout 1800 optimum-rbln-cli \
  --model-id Qwen/Qwen3-4B \
  --output-dir /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb \
  --batch_size 8 --decoder_batch_sizes 1,2,4,8 \
  --max_seq_len 8192 --num_devices 4

# 2. serving
env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG vllm serve \
  /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb \
  --host 127.0.0.1 --port 8000 > <RUN>/server.log 2>&1 &

# 3. 동시성 sweep (별도 shell에서 rbln-smi 1초 폴링)
env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage1/concurrency_probe.py \
  --base-url http://127.0.0.1:8000 \
  --prompt-file /home/rebel/continuum-npu/experiments/npu/stage1/prompt.txt \
  --max-tokens 256 --seed 20260819 --levels 1,2,4,8 \
  --output-dir /home/rebel/continuum-npu/<RUN>/probe

# 4. bucket 관측 수단 3 확인 (server 재기동)
env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG VLLM_RBLN_METRICS=1 vllm serve ...
```

## 결과

### 조건 분리

- `requested_condition`: `batch_size=8`, `decoder_batch_sizes=1,2,4,8`, `max_seq_len=8192`, `num_devices=4`. Serving은 `max_tokens=256`, greedy, seed 20260819, 동시성 1/2/4/8, `RBLN_DEVICES` 미설정.
- `observed_condition`: compile된 `rbln_config.json`이 `batch_size=8`, `decoder_batch_sizes=[8,4,2,1]`, `kvcache_num_blocks=8`, `num_devices=4`를 담았고 vLLM이 `max_num_seqs`를 1 → 8로 갱신했다. 동시성 8에서 `running`이 8에 도달했다.
- `condition_reached`: `YES`.

### 관찰 — compile

Population: compile job 1회. Source: `optimum-rbln-cli 0.11.1`, `/usr/bin/time -v`.

| 항목 | 값 |
|---|---|
| exit code | 0 (진단 재시도 불필요) |
| **compile wall-clock** | **349.0 s (5.82 min)**. `/usr/bin/time` 기준 5:49.18 |
| host CPU time | user 790.63 s + sys 640.62 s, CPU 409 % |
| host peak RSS | 37,611,180 KiB ≈ 35.9 GiB |
| **artifact 총 크기** | **12,349,415,921 B = 11.501 GiB** |
| compiled model 수 | 5 (`prefill`, `decoder_batch_8/4/2/1`) |
| 시각 | 2026-08-19 17:43:31 → 17:49:20 (KST) |

`rbln_config.json` 주요 값 — **[TASK08](TASK08.md)의 사전 예측과 전부 일치**:

| key | 예측 | 관측 |
|---|---|---|
| `batch_size` | 8 | 8 ✓ |
| `decoder_batch_sizes` | `[8, 4, 2, 1]` | `[8, 4, 2, 1]` ✓ |
| `kvcache_num_blocks` | 8 | 8 ✓ |
| `kvcache_block_size` | 8192 | 8192 ✓ |
| `attn_impl` | `eager` | `eager` ✓ |
| `prefill_chunk_size` | 128 | 128 ✓ |
| KV tensor shape | `[8, 8, 8192, 128]` | `[8, 8, 8192, 128]` bf16 ✓ |
| compiled model 이름 | `prefill` + `decoder_batch_{1,2,4,8}` | 동일 ✓ |

#### compile cost 스케일 (Stage 0 대비)

| 항목 | Stage 0 (b1, bucket 1개) | Stage 1b (b8, bucket 4개) | 배수 |
|---|---|---|---|
| wall-clock | 165.0 s | 349.0 s | **2.12×** |
| compiled model 수 | 2 | 5 | 2.5× |
| model 1개당 시간 | 82.5 s | 69.8 s | 0.85× |
| artifact 총 크기 | 9,752,342,327 B | 12,349,415,921 B | **1.27×** |
| host peak RSS | 33.2 GiB | 35.9 GiB | 1.08× |

파일별 대조:

| 파일 | Stage 0 | Stage 1b | 차이 |
|---|---|---|---|
| `prefill.rbln` | 8,899,037,284 B | 8,899,037,396 B | **+112 B** |
| `decoder_batch_1.rbln` | 841,829,476 B | 841,829,608 B | **+132 B** |
| `decoder_batch_2.rbln` | — | 871,612,781 B | 신규 |
| `decoder_batch_4.rbln` | — | 847,605,989 B | 신규 |
| `decoder_batch_8.rbln` | — | 877,817,914 B | 신규 |
| `rbln_config.json` | 42,153 B | 78,819 B | +36,666 B |

**총 증가분 2,597,073,594 B는 신규 decoder bucket 3개의 합 2,597,036,684 B와 `rbln_config.json` 증가분으로 전부 설명된다.**

### 관찰 — serving resolved config

Source: `<RUN>/server.log` (911줄). 기동 요청 17:49:59 → `/health` 200 17:51:07, **약 68 s** (Stage 1a b1은 41 s).

| 항목 | [TASK08](TASK08.md)/선등록 예측 | 관측 | 일치 |
|---|---|---|---|
| `max_num_seqs` | 8 | 1 → **8**로 갱신 | ✓ |
| EngineCore `num_gpu_blocks` | 513 | **513** (`num_blocks already synced to 513`) | ✓ |
| frontend `num_gpu_blocks` | 1026 | **1026** (`num_gpu_blocks is: 1026`) | ✓ |
| `GPU KV cache size` | 65,664 token | **65,664 tokens** | ✓ |
| `Maximum concurrency` | 8.02× | **8.02x** | ✓ |
| `max_model_len` | 8192 | 40960 → 8192 | ✓ |
| `max_num_batched_tokens` | 128 | 2048 → 128 | ✓ |
| `enable_prefix_caching` | `True` | `True` | ✓ |
| `kv_cache_usage_perc` 분모 | 512 | **512** (관측 최소 증분 1/512 = 0.001953125) | ✓ |

**예측 9개가 전부 맞았다.** frontend가 EngineCore 값의 정확히 2배라는 [TASK09](TASK09.md)의 구조적 설명도 b8에서 재현됐다.

### 관찰 — 동시성

Population: 동시성 수준 4개, 총 15개 요청. Unit: 요청 수, 초, 비율. Source: `/metrics` in-flight 표집(50 ms 주기)과 server 주기 로그. Device scope: `rbln0`–`rbln3`.

| 수준 | 요청 status | wall-clock (s) | `running` 최대 | 관측된 `running` 값 | `waiting` 최대 | `kv_cache_usage_perc` 최대 |
|---|---|---|---|---|---|---|
| 1 | 200 ×1 | 2.762 | 1 | {0, 1} | 0 | 0.005859375 (3/512) |
| 2 | 200 ×2 | 2.838 | 2 | {0, 1, 2} | 1 | 0.01171875 (6/512) |
| 4 | 200 ×4 | 2.968 | 4 | {0, 2, 4} | 2 | 0.0234375 (12/512) |
| 8 | 200 ×8 | 3.691 | **8** | {0, 2, 4, 6, 8} | 6 | 0.046875 (24/512) |

동시성 8에서 8개 요청이 **모두 3.690–3.691 s에 함께 종료**됐다 (시작은 0.001–0.003 s). 각 요청 usage는 prompt 20 / completion 256 / total 276 token으로 동일했다.

Server 주기 로그에도 `Running: 8 reqs, Waiting: 0 reqs, GPU KV cache usage: 1.6%`가 기록됐다.

`kv_cache_usage_perc`는 요청 1개당 정확히 3/512씩 증가했다. 요청 1개의 token 수 276에 대해 `ceil(276 / 128) = 3` inner block이며 산식과 정합한다.

`waiting` 최대값(수준 8에서 6)은 ramp-up 구간의 관측이다. `running`과 `waiting`의 최대값은 서로 다른 시점의 값이며 동시에 성립하지 않는다.

### 관찰 — prefix cache

모든 수준에서 `vllm:prefix_cache_hits_total` 증분이 **0**이었다. `vllm:prefix_cache_queries_total` 증분은 수준별로 20 / 40 / 80 / 160으로, 각 요청의 prompt token 20개 × 요청 수와 정확히 일치했다. [TASK09](TASK09.md)에서 확인한 "단위는 요청이 아니라 token"이 재확인됐다.

`vllm:num_preemptions_total` 증분도 전 수준 0이었다.

### 관찰 — NPU 실행 증거와 종료

Source: `rbln-smi` 1초 폴링. Device scope: 전 32 ID.

- Memory: `rbln0`–`rbln3`가 `0.0B` → **4.3 GiB**(`rbln0`는 4.3–4.5 GiB). 나머지 28개 ID는 `0.0B` 유지.
- Utilization: 최대 87.7(`rbln2`), 86.7(`rbln3`), 86.3(`rbln0`).
- Context: `VLLM::EngineCor` PID 299016 출현 (폴링 전체 4,568 row).

[TASK08](TASK08.md)의 파생 예측 4.12 GiB/device(weight 1.873 + KV 2.25)와 관측 4.3–4.5 GiB는 어긋나지 않는다. 차이는 kernel·activation 예약을 예측에 넣지 않았기 때문으로 보이며, b1의 예측 2.15 vs 관측 2.2와 같은 방향·크기의 편차다.

두 server lifecycle 모두 `SIGTERM` 후 로그에 `Shutdown initiated` → `Shutdown complete` → `v1 optimum_worker shutdown called` → `Application shutdown complete`가 기록됐고, 종료 후 process 부재, port 8000 해제, `rbln0`–`rbln3` memory `0.0B` 복귀, Context Information 빈 상태를 확인했다.

### 선등록 PASS 조건 대조

| # | 조건 | 결과 | 근거 |
|---|---|---|---|
| 1 | `batch_size`만큼의 sequence가 동시 RUNNING | 충족 | `vllm:num_requests_running` in-flight 최대 **8.0**, server 로그 `Running: 8 reqs`. 8개 요청이 3.691 s에 함께 종료 |
| 2 | resolved config 기록 + b1 대비 변화를 예측과 대조 | 충족 | 위 표. 예측 9개 전부 일치 |
| 3 | NPU 실행 증거 + 정상 종료 | 충족 | memory 0→4.3 GiB, util 최대 87.7, context 출현 / 종료 후 `0.0B` 복귀와 context 소멸 |

**판정: `PASS`.** 측정 후 기준을 완화하거나 조정하지 않았다.

### 핵심 산출 — decoder bucket 관측 판정: **불가**

선등록에서 "기존 수단"으로 한정한 4개를 모두 검색했다.

#### 수단 1 — `VLLM_LOGGING_LEVEL=DEBUG` server 로그 전문 (911줄)

`bucket|padded_batch|decoder_batch|select_bucket|request_nums|num_reqs|batch_size`로 검색한 결과 나온 것은 두 종류뿐이며 **둘 다 기동 시점(17:50:22–17:51:04)의 출력**이고 서비스 구간(17:51:07 이후)에는 없다.

```text
optimum_model_runner.py:1473  Bucket sizes for RBLN sampler: (1, 2, 4, 8)
optimum_model_runner.py:1192  Running dummy compile with batch_size=1|2|4|8, vocab_size=151936
```

앞은 **sampler**의 bucket 목록이고 뒤는 warm-up dummy compile이다. 둘 다 "어떤 bucket이 존재하는가"이지 "이번 step에서 어느 bucket이 선택됐는가"가 아니다.

서비스 구간에 실제로 나온 vllm-rbln DEBUG는 다음 4종이며 어느 것도 step 단위 batch 정보를 담지 않는다.

| 위치 | 내용 | 빈도 |
|---|---|---|
| `optimum_model_runner.py:638` | `Request <id> is now scheduled. Prompt tokens: 20, Already generated tokens: 0, Allocated block(s): [1]` | 15 |
| `optimum_model_runner.py:845` | `Request <id> is finished. Prompt tokens: 20, Generated tokens: 256, Freed block(s): [1, 2, 3]` | 15 |
| `optimum_prefix_cache_manager.py:308,361,407` | prefix cache manager 내부 | 29 |
| `optimum_block_mapping_manager.py:106` | block mapping | 7 |

#### 수단 2 — `/metrics` 전체 122개 항목

`bucket|batch|decoder|pad`로 검색한 결과는 전부 Prometheus **histogram bucket**(`_bucket` 접미사)이며 decoder bucket과 무관하다. batch size나 선택된 bucket을 담는 항목은 없다.

#### 수단 3 — `VLLM_RBLN_METRICS=1`

Server를 이 flag로 재기동해 동시성 8 요청을 보냈다. 종료 시 출력된 것은 다음 3개 절뿐이다.

```text
PREFILL METRICS:  Total call counts: 8
DECODE METRICS:   Total call counts: 127
PADDED DECODE METRICS: No data recorded
```

`PADDED DECODE`라는 절이 존재하지만 **항상 비어 있다.** `metrics.py`의 `StepReport.padded_decode`는 기본값 `False`이고, 이 값을 `True`로 설정하는 caller가 설치 package 전체에 **없다** (`grep -rn "padded_decode=" vllm_rbln/` 결과는 `metrics.py` 내부 2곳의 전달뿐). 즉 padding 여부를 구분하는 field가 배선되어 있지 않다.

각 절이 담는 것은 latency 통계(mean/p50/p90/p99/max)와 host/device/ccl/prepare 시간이다. `collect_metrics(..., token_count=0, ...)`로 호출되므로 token 수도 0이다. batch size나 bucket field는 없다.

이 flag는 관측 전용이며 실행 semantics를 바꾸지 않는다 (`optimum_model_runner.py:256,385,1534`에서 `PerformanceTracker` 생성과 `collect_metrics` 호출만 게이팅한다).

#### 수단 4 — 기타 read-only 경로

기동 시 config dump에는 `decoder_batch_sizes`가 나오지만 이는 정적 목록이다. `rbln_config.json`도 마찬가지다.

#### 판정

**per-step `(실제 요청 수, 선택된 bucket)`을 노출하는 경로는 없다.** [TASK08](TASK08.md)이 source 수준에서 예측한 대로이며, 이번에 실행 수준에서 확인됐다. 계산은 `optimum/model_base.py:396–405`의 `preprocess_for_decoder`에서 이루어지지만 log·metric emit이 없다.

이에 따라 [INDEX](INDEX.md)에 **결정 3 — decoder bucket 관측용 hash-guarded observation-only patch 승인**을 신설했다. **Patch는 작성하지도 적용하지도 않았다.**

## 핵심 발견

1. **동시 실행이 확인됐다.** `batch_size=8` artifact에서 `running`이 8에 도달했고 8개 요청이 같은 시각에 종료했다. b1에서 running이 1을 넘지 못했던 것([TASK09](TASK09.md))과 대비된다. Track A와 Stage 2의 전제 조건이 충족됐다.
2. **artifact 크기는 `batch_size`나 `kvcache_num_blocks`가 아니라 decoder bucket 개수에 비례한다.** `kvcache_num_blocks`가 1 → 8로 8배가 됐는데 `prefill.rbln`은 **112 byte**만 커졌다. 총 증가분은 신규 bucket 3개의 크기로 전부 설명된다. 즉 **`.rbln`에 KV cache buffer가 들어 있지 않다.** [TASK08](TASK08.md)이 남긴 "artifact가 KV에 비례해 커지는가"라는 미지수가 "아니다"로 닫혔다.
3. **compile 시간은 compiled model 개수에 거의 비례한다.** model 1개당 82.5 s(Stage 0) → 69.8 s(Stage 1b)로 오히려 조금 줄었다. bucket을 늘리는 비용은 예측 가능하고 저렴하다. bucket 8개를 쓰더라도 10분 내외로 추정된다(추정이며 측정값 아님).
4. **[TASK08](TASK08.md)의 사전 예측 9개가 전부 맞았다.** `kvcache_num_blocks = batch_size`, `num_gpu_blocks = batch_size × 64 + 1`, frontend 2배, KV cache size, `kv_cache_usage_perc` 분모까지 정확히 일치했다. source에서 유도한 KV accounting 모델이 실행 수준에서 검증됐다.
5. **`kv_cache_usage_perc`가 요청 1개당 정확히 3/512씩 움직였다.** 요청당 276 token → 3 inner block과 정합한다. 이 지표는 **inner block 단위의 신뢰할 수 있는 KV 점유 신호**로 채택 가능하다. b8에서 분모가 512이므로 b1(64)보다 해상도가 8배 높다.
6. **per-request block 할당·해제가 DEBUG 로그로 노출된다.** `Request <id> is now scheduled ... Allocated block(s): [1]` / `Request <id> is finished ... Freed block(s): [1, 2, 3]`. 이는 이 저장소의 연구 대상(KV lifecycle, cache attribution)에 직접 쓸 수 있는 신호이며, 이번 감사에서 처음 발견됐다. 다만 `enable_prefix_caching=True`일 때만 나온다 (`optimum_model_runner.py:843` 조건).
7. **decoder bucket은 관측 불가다.** 4개 수단을 모두 검색해 확인했다. `VLLM_RBLN_METRICS`의 `PADDED DECODE` 절은 배선되지 않아 항상 비어 있다.
8. **prefix cache hit이 b8에서도 0이었다.** prompt 20 token, 요청 8개가 같은 prefix를 공유했는데도 hit이 없었다. [TASK09](TASK09.md)의 관측이 재현됐다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(해석)** 발견 2와 3을 합치면 재compile 비용 모형이 선다: **시간 ≈ 70 s × (compiled model 수), 크기 ≈ 8.3 GiB + 0.85 GiB × (decoder bucket 수)**. `batch_size`와 `max_seq_len`은 이 모형에 거의 들어오지 않는다. 다만 관측점이 2개(b1/1-bucket, b8/4-bucket)뿐이므로 외삽이며, bucket 수를 크게 늘린 조건에서 재확인이 필요하다.
- **(hypothesis)** prefix cache hit이 0인 원인은 [TASK09](TASK09.md)에서 세운 가설(prompt가 block 경계에 못 미쳐 캐시 대상이 되지 않음)과 일관된다. b8에서 outer block은 여전히 8,192 token이고 prompt는 20 token이다. 이 가설이 맞다면 hit을 보려면 prefix가 최소 한 block 경계를 넘어야 하며, 그 경계가 inner 128인지 outer 8,192인지는 아직 `UNKNOWN`이다. Stage 2 설계 전에 이 값을 확정해야 한다.
- **(hypothesis)** `waiting`이 ramp-up 중 최대 6까지 올라간 것은 vLLM scheduler가 한 step에 admit하는 요청 수에 제약이 있기 때문으로 보인다(`running` 관측값이 0, 2, 4, 6, 8로 2씩 증가했다). `max_num_batched_tokens=128`과 `prefill_chunk_size=128`, prompt 20 token의 관계에서 나올 수 있는 값이지만 확인하지 않았다.
- **(해석)** 발견 6의 block 할당·해제 로그는 request 단위이지 step 단위가 아니다. 따라서 "어느 시점에 어느 block이 살아 있었는가"는 재구성할 수 있어도 "이번 step의 batch가 몇이었는가"는 알 수 없다. bucket 관측 불가 판정과 모순되지 않는다.
- **(해석)** b8 기동이 68 s로 b1의 41 s보다 길다. bucket 4개에 대해 warm-up dummy compile이 각각 수행된 로그가 있으므로 bucket 수에 따른 증가로 보이지만, 1회 관측이라 비례 관계를 주장하지 않는다.

## 확인되지 않은 사항

- prefix cache hit의 block 경계 단위 (inner 128 token인지 outer 8,192 token인지) (`UNKNOWN`). Stage 2 repeated-prefix 설계에 직결되며 [TASK09](TASK09.md)에서 이월됐다.
- `running`이 2씩 증가한 이유 (`UNKNOWN`). scheduler admit 정책을 추적하지 않았다.
- `prefill.rbln` 8.288 GiB와 bf16 weight 7.492 GiB의 차이 796 MiB의 내역 (`UNKNOWN`, [TASK08](TASK08.md)에서 이월). KV가 아님은 확정됐다.
- bucket 수를 더 늘렸을 때 compile 비용 모형이 유지되는지 (`UNKNOWN`, 관측점 2개의 외삽).
- decoder bucket을 관측 가능하게 만드는 patch의 실제 diff와 hash guard 구현 (미작성, 결정 3 대기).
- `vllm:prefix_cache_hits_total`, `vllm:prompt_tokens_cached_total`, `vllm:num_preemptions_total`이 이 stack에서 채워지는 경로가 있는지 (`UNKNOWN`, [TASK09](TASK09.md)에서 이월. b8에서도 전부 0이었다).
- 종료 시 `leaked semaphore` 경고의 원인 (`UNKNOWN`, device 자원은 완전히 해제되므로 판정에 무관).

## 실패 / 무효 시도

- compile은 승인 파라미터로 1회에 성공했다. 진단 재시도(승인된 2회 중 2번째)를 사용하지 않았다.
- `pgrep -f "bin/vllm serve ..."`가 그 명령을 실행한 bash wrapper 자신의 command line에도 매칭되어 "server가 아직 살아 있다"는 오탐이 3회 발생했다. 실제 상태는 `ps -eo pid,cmd | grep "python3 /usr/local/bin/vllm serve"`, port, device memory, background task exit code로 교차 확인했고 전부 종료·해제였다. 측정에는 영향이 없다. ([TASK09](TASK09.md)에서 같은 패턴이 shell을 죽인 사례가 있었다.)
- 무효로 판정한 측정은 없다. Device·RSD·package·site-packages 변경은 없었다.

## 연구 원칙에 미치는 영향

- **source에서 유도한 예측을 측정 전에 등록하면 판정이 명확해진다.** 이번에는 예측 9개가 전부 맞아 KV accounting 모델이 검증됐다. 빗나갔다면 어느 산식이 틀렸는지 바로 좁혀졌을 것이다. 이후 측정 TASK에도 유도 예측표를 선등록한다.
- **"관측 불가"도 증거를 요구한다.** 어떤 수단을 어떻게 검색했고 무엇이 없었는지를 남겨야 이후에 재검토할 수 있다. 수단의 범위를 측정 전에 한정해 두었기 때문에 사후에 "더 찾아봤어야 했다"는 논쟁이 생기지 않는다.
- **artifact 크기를 KV 용량의 대리 지표로 쓰지 않는다.** `kvcache_num_blocks`가 8배가 되어도 `prefill.rbln`은 112 byte만 커졌다.
- **최대값끼리 결합하지 않는다.** `running` 최대 8과 `waiting` 최대 6은 서로 다른 시점의 값이며 동시에 성립하지 않는다.
- **process를 pattern으로 죽이거나 확인하지 않는다.** wrapper shell이 같은 pattern에 매칭된다. PID를 특정하고 port·device·exit code로 교차 확인한다.

## 다음 작업

두 갈래가 있으며 사용자 지시 없이 착수하지 않는다.

1. **결정 3 판정** — decoder bucket observation-only patch를 승인할지. 승인되면 Track A가 patch 경로로 진행되고, 승인되지 않으면 bucket을 직접 관측하지 않는 대안 설계가 필요하다.
2. **prefix cache hit 단위 확정** — Stage 2 repeated-prefix baseline 설계의 전제다. 현재 artifact로 prefix 길이를 바꿔가며 hit 발생 지점을 찾는 방식이 가능하며 재compile이 필요 없다. 측정이 포함되므로 선등록한다.

## 재현 정보

- 선등록 commit: `1796eed0d08597097baa0b01ce8bf2ddd048a82c`
- **측정 시작 시각: 2026-08-19 17:43:08 KST.** 선등록 commit 시각은 2026-08-19 17:42:59 KST이므로 **선등록이 측정보다 9초 앞선다.**
- 측정 종료 시각: 2026-08-19 17:55:01 KST
- Base commit (측정 중 HEAD): `1796eed0d08597097baa0b01ce8bf2ddd048a82c`, dirty = untracked `.idea/` 및 gitignored `results/`, `models/`
- Model: `Qwen/Qwen3-4B` revision `1cfa9a7208912126459214e8b04321603b3df60c` (재download 없음)
- Compile artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb/` (gitignored, 11.501 GiB)
- Raw artifact: `results/npu/stage1/20260819-174300-stage1b-b8-multibucket/`
  - `measurement-start.txt`, `measurement-end.txt`
  - `compile/` — `compile.log`, `started_at.txt`, `finished_at.txt`, `exit_code.txt`, `rbln_config-b8.json`
  - `df-before-compile.txt`, `df-after-compile.txt`, `du-models-before.txt`, `du-models-after.txt`
  - `server.log`(911줄), `server2-metrics-flag.log`(`VLLM_RBLN_METRICS=1`), `server-{start-requested,ready,stop-requested,exit}.txt`, `server2-*.txt`
  - `rbln-smi-{before-compile,before-serve,after-shutdown,final}.txt`
  - `probe/concurrency_probe.json`, `probe/concurrency_summary.json`, `probe/rbln-smi-poll.txt`, `probe/probe-stdout.log`
  - `probe-metricsflag/concurrency_{probe,summary}.json`
- 실행 script: `experiments/npu/stage1/concurrency_probe.py`, `experiments/npu/stage1/prompt.txt`
- Isolation launcher: `experiments/npu/launch/run_isolated_python.sh`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch-rbln 0.3.0`, `torch 2.11.0+cpu`, `transformers 5.8.1`
- Host: `atom-max8`, KMD ver 3.2.2, device `rbln0`–`rbln3`
- 예산 사용: compile 1/2회, wall-clock 349 s / 1800 s 상한, `models/` 21 GiB / 80 GiB 상한, `/` 사용률 9 % / 80 % 상한
