# TASK08 — compile 파라미터 공간과 KV accounting source 조사

## 상태

DONE

## 날짜

2026-08-19

## 목적

Stage 1b의 재compile 파라미터를 근거 있게 고르기 위해, 설치 package source만 읽어 세 가지를 확정한다.

1. optimum-rbln의 compile 파라미터 공간 — `batch_size`, `decoder_batch_sizes`, `kvcache_num_blocks`, `kvcache_block_size`, `kvcache_partition_len`이 서로 어떻게 결정되고 vLLM의 `max_num_seqs`와 어떻게 이어지는가.
2. [TASK06](TASK06.md)이 `UNKNOWN`으로 남긴 KV accounting — `num_gpu_blocks=130` / `block_size=128` / log `"GPU KV cache size: 8,320 tokens"`의 정합 관계.
3. decoder bucket 관측 지점이 현재 설치 버전의 **실제 실행 경로**에 존재하는지, per-step 값이 기존 수단으로 노출되는지.

Compile, 실행, download를 하지 않는다. 측정이 없으므로 선등록 대상이 아니다.

## 배경

관련 TASK:

- [TASK06](TASK06.md) — Stage 0 `PASS`. `kvcache_num_blocks=1`이라 KV pool이 sequence 1개분뿐임을 관측했고, `num_gpu_blocks=130`과 8,320 token의 관계를 `UNKNOWN`으로 남겼다.
- [TASK05](TASK05.md) — 기본 vLLM 경로(`VLLM_RBLN_USE_VLLM_MODEL=False`)가 optimum-rbln compile artifact를 요구함을 확인했다. 이 TASK는 그 경로의 내부 규칙을 확정한다.

[NPU_PORTING_ANALYSIS.md](../environment/NPU_PORTING_ANALYSIS.md)는 bucket 관측 지점으로 `_determine_batch_padding()`의 `num_reqs_padded`와 `find_decode_batch_bucket(num_reqs_unpadded)`를 지목했다. 이 TASK는 그 지목이 현재 실행 경로에 유효한지 검증한다.

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- Git commit: `ff5db7889...` (TASK07 직후), dirty = untracked `.idea/`만
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`
- 대조 artifact: `models/Qwen3-4B-rbln-b1-s8192-d4/rbln_config.json` (TASK06 산출, 무변경)
- 실행 경로: `VLLM_RBLN_USE_VLLM_MODEL=False` (기본값)

## 수행 내용

`vllm_rbln`, `optimum.rbln`, `vllm` site-packages를 read-only로 열람했다. 파일 수정, compile, 실행, device 접근은 없었다. 발췌를 `results/npu/stage1/20260819-task08-source-audit/source-excerpts.txt`에 보존했다.

## 변경된 파일

- `docs/research/TASK08.md` (신규)
- `docs/research/INDEX.md`

Raw evidence는 `.gitignore` 대상인 `results/npu/stage1/20260819-task08-source-audit/`에 있다 (`source-excerpts.txt`, `rbln_config-b1.json`, `collected_at.txt`).

## 실험 또는 검증 방법

측정이 아니라 source 조사다. 열람한 파일은 아래 "결과"의 각 항목에 `파일:줄` 형태로 인용한다.

## 결과

### 1. 실행 경로 확정 — porting analysis의 관측 지점은 **이 경로에 없다**

`VLLM_RBLN_USE_VLLM_MODEL=False`(기본)에서 실행되는 것은 `optimum_worker.py` / `optimum_model_runner.py`다. `rbln_worker.py` / `rbln_model_runner.py`는 `True` 경로 전용이다.

`find_decode_batch_bucket`과 `RBLNBucketingManager`는 **`rbln_model_runner.py`에만** 존재한다 (`vllm_rbln/v1/worker/bucketing/bucketing_manager.py:54`, 사용처 `rbln_model_runner.py:2768,2791`, `rbln_worker.py:576`, `spec_decode/eagle.py:609`). `_determine_batch_padding()`라는 이름의 함수는 설치 버전 어디에도 없다.

`VLLM_RBLN_DECODE_BATCH_BUCKET_*` 환경변수 5종(`envs.py:74–78`)도 `bucketing` package를 통해서만 쓰이므로 **기본 경로에서는 효과가 없다.** 같은 이유로 `VLLM_RBLN_SUB_BLOCK_CACHE`(`envs.py:67`)도 `rbln_model_runner.py:2591`과 `rbln_scheduler.py:70`에서만 읽히므로 기본 경로의 KV block 변환에 개입하지 않는다.

기본(optimum) 경로의 실제 bucket 선택 지점은 다음이다.

| 위치 | 내용 |
|---|---|
| `vllm_rbln/model_executor/models/optimum/model_base.py:361–406` `RBLNOptimumDecoderMixin.preprocess_for_decoder` | `request_nums = input_ids.shape[0]`(실제 요청 수)와 `padded_batch_size`(선택된 bucket)를 모두 계산한다 |
| `vllm_rbln/utils/optimum/bucket.py:20` `select_bucket_size` | `bisect_left`로 `bucket_sizes` 중 요청 수 이상인 최소값을 고른다. `@cache`가 붙어 있다 |
| `vllm_rbln/model_executor/models/optimum/decoder_only.py:58,65` `RBLNOptimumForCausalLM.forward` | `padded_batch_size`로 `self.model.decoders[padded_batch_size]`를 선택해 실행한다 |
| `model_base.py:292–296` `setup_decoder_mixin` | `use_multiple_decoder`가 False면 `decoder_batch_size = scheduler_config.max_num_seqs` 하나로 고정되고 `select_bucket_size`는 호출조차 되지 않는다 |

**세 지점 모두 log 문·metric emit이 없다.** 즉 per-step `(request_nums, padded_batch_size)` 쌍은 계산되지만 어디에도 노출되지 않는다.

### 2. compile 파라미터 공간

#### `batch_size` ↔ `decoder_batch_sizes`

`configuration_decoderonly.py:334–353`:

- `decoder_batch_sizes`가 `None`이면 **`[batch_size]` 하나**가 된다. 즉 자동 다단화는 없다. `batch_size=8`을 주면 `[8]`이지 `[1,2,4,8]`이 아니다.
- 명시하면 `use_multiple_decoder`(`len > 1`)가 True가 되고 다음 규칙이 적용된다: 최대값이 `batch_size`보다 크면 `ValueError`, 작으면 경고 후 `batch_size`를 append, 그리고 **내림차순 정렬**.
- `expected_compiled_model_names`(`:404`)는 `["prefill", "decoder_batch_{b}" for b in decoder_batch_sizes]`다. 즉 **bucket 1개당 `.rbln` 파일 1개**가 만들어진다.

vLLM 쪽 연결: `decoder_only.py:41`이 `decoder_batch_sizes=self.model.rbln_config.decoder_batch_sizes`를 그대로 넘기고, `model_base.py:296`이 `tuple(reversed(...))`로 오름차순 tuple을 만들어 `select_bucket_size`에 쓴다.

CLI 전달: `optimum/rbln/cli.py`의 `parse_value`가 쉼표 문자열을 list로 파싱하므로 `--decoder_batch_sizes 1,2,4,8` 형태가 그대로 `rbln_config`에 들어간다.

#### `attn_impl` / `kvcache_block_size` / `kvcache_partition_len`

`modeling_attention_utils.py:27–64` `set_default_values`:

- `attn_impl`이 `None`이면 `"eager"`.
- `kvcache_partition_len`을 주면 `attn_impl`이 자동으로 `"flash_attn"`이 된다. `flash_attn`에서 `kvcache_partition_len`이 `None`이면 16,384.
- `kvcache_block_size`가 `None`일 때: **`eager`이면 `max_seq_len`**, `flash_attn`이면 `kvcache_partition_len`.
- `prefill_chunk_size`가 `None`이면 RBLN-CR은 512, 그 외(**CA25 포함**)는 128. 64의 배수여야 한다.

→ TASK06 artifact의 `attn_impl=eager`, `kvcache_block_size=8192(=max_seq_len)`, `kvcache_partition_len=None`, `prefill_chunk_size=128`은 전부 **기본값이 그대로 적용된 결과**다.

#### `kvcache_num_blocks` — TASK06 hypothesis의 확정

`configuration_decoderonly.py:343–356`:

```
is_auto_num_blocks  := (kvcache_num_blocks == 0)          # 기본값 0
num_full_blocks     := (max_seq_len // kvcache_block_size) * batch_size
num_min_blocks      := batch_size                          # eager
```

`modeling_decoderonly.py:533–535` (eager 분기):

```
if rbln_config.is_auto_num_blocks:
    # Eager attention should use fixed number of blocks.
    rbln_config.kvcache_num_blocks = rbln_config.num_full_blocks
```

**`eager` + `kvcache_block_size = max_seq_len`이면 `num_full_blocks = 1 × batch_size = batch_size`다.** 따라서 KV pool의 block 수는 `batch_size`와 정확히 같고, block 1개가 sequence 1개분(8,192 token)이다.

이는 TASK06이 hypothesis로 남긴 "`kvcache_num_blocks=1`은 `batch_size=1`의 결과"를 **source 수준에서 확정**한다. `docstring`이 말하는 "available DRAM에 맞춰 자동 결정"은 `flash_attn` 분기에만 해당하고, `eager`에서는 DRAM과 무관하게 `batch_size`로 고정된다.

`configuration_decoderonly.py:453–460`: KV tensor shape은 `[num_blocks, num_key_value_heads, block_size, head_dim]`이다. TASK06 artifact의 `[1, 8, 8192, 128]`과 일치한다.

#### `max_num_seqs`와의 연결

`vllm_rbln/utils/optimum/converter/from_optimum.py:92`가 `scheduler_config.max_num_seqs = params.batch_size`로 덮어쓴다. 즉 vLLM의 최대 동시 sequence 수는 compile된 `batch_size`가 지배하며 CLI로 올려도 무시된다.

### 3. KV accounting — TASK06 `UNKNOWN`의 부분 해소

#### outer/inner block 변환

`vllm_rbln/utils/optimum/converter/common.py:38–81` `_apply_prefix_caching_block_size` (APC가 켜져 있을 때만 실행):

- `prefix_block_size` = `additional_config["prefix_block_size"]` 또는 기본값 `prefill_chunk_size`
- `cache_config.block_size = prefix_block_size` → **inner block (ib) = 128**
- `additional_config["attn_block_size"] = kvcache_block_size` → **outer block (ob) = 8192**

`utils/optimum/block_size.py:39–57`:

```
blk_ratio = ob_size // ib_size            = 8192 // 128 = 64      (APC OFF면 1)
is_full_block_available(n) := n >= max_num_seqs * ceil(max_model_len / ob_size)
```

`from_optimum.py:145–151` / `model_base.py:103–115` (동일 산식):

```
full 이면  num_gpu_blocks = kvcache_num_blocks * blk_ratio + 1
아니면     num_gpu_blocks = (kvcache_num_blocks - 1) * blk_ratio + 1
```

#### `"GPU KV cache size: N tokens"`의 의미

`vllm/v1/core/kv_cache_utils.py:1724–1733`: 이 log는 `num_blocks × block_size`가 **아니라** `max_concurrency × max_model_len`이다.

#### TASK06 값과의 대조

`batch_size=1`, APC ON을 대입하면:

| 값 | source 유도 | TASK06 관측 |
|---|---|---|
| `kvcache_num_blocks` | 1 | 1 ✓ |
| `blk_ratio` | 64 | — |
| `is_full_block_available(1)` | `1 >= 1 × ceil(8192/8192) = 1` → True | — |
| `num_gpu_blocks` | `1 × 64 + 1 = 65` | **130** ✗ |
| inner block/sequence | `ceil(8192/128) = 64` | — |
| `max_concurrency` | `65 / 64 = 1.0156` | — |
| GPU KV cache size | `1.0156 × 8192 = 8,320 token` | 8,320 ✓ |

**log의 8,320 token은 `num_gpu_blocks = 65`와 정확히 정합한다.** 즉 EngineCore가 실제로 쓰는 값은 65다.

TASK06이 기록한 130은 `LLM.llm_engine.vllm_config.cache_config.num_gpu_blocks`를 **frontend process에서** 읽은 값이며 정확히 65의 2배다. `vllm/v1/engine/core.py:276`이 EngineCore에서 `cache_config.num_gpu_blocks = scheduler_kv_cache_config.num_blocks`를 다시 설정하므로 두 process의 값이 다를 수 있는 구조는 확인했으나, **2배라는 관계 자체를 만들어내는 지점은 source 조사로 찾지 못했다** (`UNKNOWN`, 아래 참조).

#### KV 실측과의 교차 검증

TASK06이 관측한 device당 2.2 GiB를 source 유도값으로 재구성한다. KV tensor 72개(36 layer × K,V), shape `[1, 8, 8192, 128]`, bf16:

| 항목 | 값 |
|---|---|
| KV tensor 1개 | `1 × 8 × 8192 × 128 × 2 B` = 16 MiB |
| KV 총량 (72개) | 1.125 GiB |
| device 4개로 분할 | 0.281 GiB/device |
| bf16 weight 7.492 GiB / 4 | 1.873 GiB/device |
| **합계 예측** | **2.15 GiB/device** |
| TASK06 관측 | 2.2 GiB/device |

균등 분할을 가정한 파생값이지만 관측과 어긋나지 않는다. 이는 위 KV accounting 모델을 **독립적으로 지지**한다.

### 4. 관측 가능성 — 기존 수단의 한계

`VLLM_RBLN_METRICS=1`을 켜면 optimum 경로에서 `metrics.py`의 `PerformanceTracker`가 동작한다(`optimum_model_runner.py:256,385,1534`). 그러나 기록 대상은 prefill/decode 각각의 **latency 통계와 host/device/ccl/prepare 시간**뿐이고, `collect_metrics(..., token_count=0, ...)`로 호출되므로 token 수조차 0으로 들어간다. **batch size, 요청 수, 선택된 bucket을 담는 field가 없다.**

`metrics_v2.py`는 `rbln_model_runner.py`(비-기본 경로) 전용이며 역시 phase(prefill/decode) 단위 latency만 갖는다.

## 핵심 발견

1. **문서화된 bucket 관측 지점이 실행 경로 밖이다.** `NPU_PORTING_ANALYSIS.md`가 지목한 `find_decode_batch_bucket`은 `VLLM_RBLN_USE_VLLM_MODEL=True` 경로에만 있고, `_determine_batch_padding()`은 설치 버전에 아예 없다. 기본 경로의 실제 지점은 `optimum/model_base.py:preprocess_for_decoder`와 `utils/optimum/bucket.py:select_bucket_size`다.
2. **다단 bucket은 자동으로 생기지 않는다.** `decoder_batch_sizes`를 명시하지 않으면 `[batch_size]` 단일 bucket이고, 그때는 `select_bucket_size`가 호출조차 되지 않아 bucket 선택이라는 현상 자체가 존재하지 않는다. Track A는 `decoder_batch_sizes`를 명시한 compile을 전제로 한다.
3. **`eager`에서 KV pool 크기는 DRAM이 아니라 `batch_size`가 결정한다.** `kvcache_num_blocks = num_full_blocks = (max_seq_len // kvcache_block_size) × batch_size`이고, 기본값에서 `kvcache_block_size = max_seq_len`이므로 결과는 정확히 `batch_size`다. docstring의 "available DRAM에 맞춰 자동 결정"은 `flash_attn` 분기에만 해당한다. TASK06의 hypothesis가 확정됐다.
4. **TASK06의 `num_gpu_blocks=130`은 신뢰할 metric이 아니다.** EngineCore가 실제로 쓰는 값은 65이고, 이는 log의 8,320 token과 정합한다. frontend `vllm_config`에서 읽은 값은 그 2배였다. **`num_gpu_blocks`를 frontend에서 읽어 KV 용량 지표로 쓰면 안 된다.**
5. **`"GPU KV cache size: N tokens"`는 `num_blocks × block_size`가 아니라 `max_concurrency × max_model_len`이다.** 두 값이 b1에서 우연히 같아 보였을 뿐이다.
6. **관측 field 자체가 없다.** `VLLM_RBLN_METRICS`는 latency만 담고 batch/bucket field가 없다. per-step bucket 관측은 log level을 올려도 나오지 않는다 — 해당 코드 경로에 log 문이 없기 때문이다.
7. `VLLM_RBLN_DECODE_BATCH_BUCKET_*`와 `VLLM_RBLN_SUB_BLOCK_CACHE`는 기본 경로에서 **무효**다. 이 flag들로 bucket을 조작하려는 시도는 하지 않는다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(hypothesis)** `num_gpu_blocks` frontend 130 vs EngineCore 65의 2배 차이는 `update_num_blocks`가 두 process에서 각각 실행되면서 `additional_config["num_blocks_synced"]` guard가 한쪽에서 듣지 않았거나, vLLM core가 KV cache group 수(K/V 분리로 72 vs 36)로 나누는 지점에서 생겼을 수 있다. 어느 쪽인지는 source만으로 확정하지 못했다. TASK09에서 두 process의 값을 각각 기록해 판별한다.
- **(해석)** `select_bucket_size`에 `@cache`가 걸려 있다는 것은 이 함수가 순수 함수로 취급된다는 뜻이다. 관측 목적으로 이 함수를 감싸는 방식(wrapper)은 cache 때문에 **첫 호출만 잡히고 이후 호출을 놓친다.** 관측 지점으로는 caller인 `preprocess_for_decoder` 쪽이 적절하다.
- **(해석)** bucket 1개당 `.rbln` 1개이므로 `decoder_batch_sizes=[1,2,4,8]`은 decoder artifact를 4개 만든다. Stage 0의 `decoder_batch_1.rbln`이 803 MiB였으므로 decoder 쪽 artifact는 대략 그 수 배가 될 것이다. 다만 `prefill.rbln` 8.288 GiB와 bf16 weight 7.492 GiB의 차이 796 MiB가 무엇인지(KV buffer인지 다른 것인지) 확정하지 못했으므로, batch가 커질 때 artifact가 KV에 비례해 커지는지는 예측하지 않는다. **이번 compile이 그 측정이다.**
- **(해석)** KV pool이 `batch_size`에 선형이고 block 1개가 full sequence라는 구조는, 이 stack에서 "KV 압력"이 GPU vLLM처럼 token 단위로 연속 변하지 않고 **sequence 단위로 계단식**이라는 뜻이다. Stage 2 이후의 pressure 설계에 직접 영향을 준다.

## 작업 3(Stage 1b) compile 파라미터 권고안

권고: **`--batch_size 8 --decoder_batch_sizes 1,2,4,8 --max_seq_len 8192 --num_devices 4`**

근거:

- `batch_size=8`이면 `kvcache_num_blocks = 8`이 되어 동시 sequence 8개분 KV가 확보된다 (b1의 8배).
- `decoder_batch_sizes`를 명시해야만 `use_multiple_decoder=True`가 되어 bucket 선택 현상이 발생한다. `[1,2,4,8]`은 요청 수 1→2→4→8 진행에서 bucket 전이가 매 단계 일어나도록 고른 격자다.
- `max_seq_len`, `num_devices`는 Stage 0와 동일하게 두어 비교 가능성을 유지한다.

이 파라미터에서 source로 유도되는 **사전 예측** (작업 3에서 requested vs observed로 대조한다):

| 항목 | 예측값 | 산식 |
|---|---|---|
| `rbln_config.kvcache_num_blocks` | 8 | `num_full_blocks = 1 × 8` |
| `rbln_config.decoder_batch_sizes` | `[8, 4, 2, 1]` | 내림차순 정렬 |
| compiled model 파일 | `prefill.rbln` + `decoder_batch_{1,2,4,8}.rbln` | `expected_compiled_model_names` |
| KV tensor shape | `[8, 8, 8192, 128]` | `[num_blocks, kv_heads, block_size, head_dim]` |
| KV 총량 / device당 | 9.0 GiB / 2.25 GiB | 72 tensor × 128 MiB / 4 |
| device 점유 예측 | 약 4.12 GiB/device | weight 1.873 + KV 2.25 |
| vLLM `max_num_seqs` | 8 | `from_optimum.py:92` |
| EngineCore `num_gpu_blocks` | 513 | `8 × 64 + 1` |
| `"GPU KV cache size"` | 65,664 token | `(513/64) × 8192` |
| frontend `num_gpu_blocks` | 513 또는 1026 | 2배 anomaly의 재현 여부가 판별 근거 |

compile wall-clock과 artifact 크기는 예측하지 않는다 (`UNKNOWN`). Stage 0 대비 스케일이 이번 compile의 측정값이다.

**대안**: `batch_size=4`, `decoder_batch_sizes=1,2,4`. device 점유가 약 3.0 GiB/device로 더 안전하지만 bucket 전이 관측 기회가 1단계 줄어든다. 승인 격자 안에 있으므로 `batch_size=8` compile이 실패하면 진단 재시도에서 쓸 수 있다.

## 확인되지 않은 사항

- frontend `num_gpu_blocks`가 EngineCore 값의 정확히 2배인 이유 (`UNKNOWN`). TASK09에서 두 process 값을 각각 기록해 판별한다.
- `prefill.rbln` 8.288 GiB와 bf16 weight 7.492 GiB의 차이 796 MiB의 내역 (`UNKNOWN`). `.rbln`에 KV buffer가 포함되는지 여부가 artifact 크기 스케일 예측을 좌우한다.
- vLLM Prometheus `/metrics`가 이 stack에서 실제로 어떤 항목을 노출하는지, RBLN 전용 scheduler/KV manager가 표준 KV·prefix-cache metric을 채우는지 (`UNKNOWN`, TASK09의 감사 대상).
- `decoder_batch_sizes` 다단 지정이 실제 compile에서 성공하는지 (`UNKNOWN`, source상 지원되나 실행 검증 전).
- `batch_size > 1`에서 device 점유·compile cost가 예측대로 스케일하는지 (`UNKNOWN`, 작업 3의 측정 대상).
- `max_seq_len // kvcache_block_size > 1`인 구성(`flash_attn` 또는 명시적 `kvcache_block_size`)에서의 KV accounting은 조사하지 않았다.

## 실패 / 무효 시도

없음. read-only 조사이며 실행·변경이 없었다.

## 연구 원칙에 미치는 영향

- **문서화된 관측 지점을 재검증 없이 신뢰하지 않는다.** `NPU_PORTING_ANALYSIS.md`의 bucket 관측 지점은 현재 기본 실행 경로에 존재하지 않았다. 환경 문서의 코드 경로 기술은 실행 경로(`VLLM_RBLN_USE_VLLM_MODEL` 값)와 함께 재확인한다.
- **metric을 채택하기 전에 어느 process에서 읽는 값인지 구분한다.** `num_gpu_blocks`는 frontend와 EngineCore에서 값이 달랐다. 이후 모든 config metric은 출처 process를 함께 기록한다.
- **log 문자열의 의미를 산식으로 확인한다.** `"GPU KV cache size: N tokens"`는 `num_blocks × block_size`가 아니었다. 이름에서 의미를 추론하지 않는다.
- 환경변수는 실행 경로별로 유효 범위가 다르다. `VLLM_RBLN_*` flag를 쓰기 전에 해당 경로에서 읽히는지 확인한다.

## 다음 작업

작업 2(Stage 1a) — 기존 b1 artifact로 `vllm serve` bring-up과 `/metrics` 관측 감사. 선등록 후 진행한다.

## 재현 정보

- Base commit: `ff5db7889` 시점의 `main` (이 TASK의 commit이 그 다음)
- 선등록 commit: 해당 없음 (측정이 없는 read-only 조사 TASK)
- Raw evidence: `results/npu/stage1/20260819-task08-source-audit/`
- 열람한 source (installed, 무변경):
  - `optimum/rbln/transformers/modeling_attention_utils.py`
  - `optimum/rbln/transformers/models/decoderonly/{configuration_decoderonly.py,modeling_decoderonly.py}`
  - `optimum/rbln/cli.py`
  - `vllm_rbln/utils/optimum/{bucket.py,block_size.py}`
  - `vllm_rbln/utils/optimum/converter/{from_optimum.py,common.py,params.py}`
  - `vllm_rbln/model_executor/models/optimum/{model_base.py,decoder_only.py}`
  - `vllm_rbln/v1/worker/{optimum_worker.py,optimum_model_runner.py,rbln_worker.py,rbln_model_runner.py,metrics.py,metrics_v2.py}`
  - `vllm_rbln/v1/worker/bucketing/bucketing_manager.py`
  - `vllm_rbln/{envs.py,platform.py}`
  - `vllm/v1/core/kv_cache_utils.py`, `vllm/v1/engine/core.py`
