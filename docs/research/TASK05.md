# TASK05 — Stage 0 후보 model metadata 조사와 atom-max8 read-only 재-inventory

## 상태

DONE

## 날짜

2026-08-19

## 목적

두 가지 read-only 조사로 [INDEX](INDEX.md) "사용자 결정 대기"의 **결정 2 — Stage 0 대상 model의 download/compile 승인**을 사용자가 판정할 수 있는 근거 표를 만든다.

1. Stage 0 후보 model의 HF metadata, config, 파생 KV 비용, 설치 package 내 지원 근거를 수집한다.
2. 현재 host `atom-max8`의 hardware inventory를 재관찰해 `NPU_ENVIRONMENT.md`(hostname `rebel-pcie-0123`) 값과 항목별로 대조한다.

이 TASK는 model 실행, download, compilation을 포함하지 않는다.

## 배경

관련 TASK:

- [TASK02](TASK02.md) — Stage 0 사전 검증. `Qwen/Qwen3-4B`와 `Qwen/Qwen3.5-0.8B`를 후보로 식별했고, hostname 불일치를 처음 기록했다.
- [TASK04](TASK04.md) — "사용자 결정 대기" 절 신설과 hostname `UNKNOWN`의 INDEX 승격. 결정 2의 빈 틀을 만들었다.

TASK02는 후보를 "설치 metadata에 등장한다"는 수준에서만 식별했고, download 크기, KV 비용, device 요구, 지원 경로의 등급 차이는 확인하지 않았다. 승인 판정에는 그 정보가 필요하다.

## 시작 상태

- Repository: `/home/rebel/continuum-npu-minnow` (worktree). Branch `minnow`, HEAD `3ec545efa40f6b3deb83f1cbf6489d7db1a879e2`
- `main`은 `/home/rebel/continuum-npu` worktree에 checkout되어 있어 이 worktree에서 전환할 수 없다.
- Host: `atom-max8`, Ubuntu 22.04.5 LTS, kernel `6.8.0-40-generic`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch-rbln 0.3.0`, `huggingface_hub 1.27.0`
- 승인 범위: read-only 시스템 조회와 weight download가 없는 HTTPS metadata 조회. download/compile/RSD 변경/device reset은 금지.

## 수행 내용

### 1. `atom-max8` read-only 재-inventory

`hostname`, `lscpu`, `/sys/devices/system/node/*`, `rbln-smi`, `rbln-smi --topo`, `rbln-smi -g`(RSD group 조회), `rbln-smi -L`을 실행했다. `numactl`은 이 host에 설치되어 있지 않아 NUMA 정보는 `lscpu`와 sysfs에서 얻었다. RSD, device state, package를 변경하지 않았고 `rblnBandwidthLatencyTest`는 실행하지 않았다.

결과를 `NPU_ENVIRONMENT.md` 말미의 신규 절 `## atom-max8 재관찰 (2026-08-19)`에 항목별 대조 표로 기록했다. 기존 내용은 삭제·수정하지 않았다.

### 2. 설치 package 내 지원 근거 조사

`vllm_rbln`과 `optimum.rbln` source에서 HF model id 형태 문자열과 model architecture registry를 조사했다.

- `vllm_rbln/utils/optimum/registry.py`가 architecture 이름을 optimum-rbln class로 매핑하는 지점이다. `_RBLN_GENERATION_MODELS`(text decoder-only), `_RBLN_MULTIMODAL_MODELS`, `_RBLN_EMBEDDING_MODELS`, `_RBLN_ENCODER_DECODER_MODELS`로 분리되어 있다.
- `optimum/rbln/cli.py`, `optimum/rbln/transformers/models/qwen3/*`, `.../qwen3_5/*`, `optimum_rbln-0.11.1.dist-info/METADATA`에서 후보별 compile 예시를 확인했다.
- `vllm_rbln/envs.py`와 `vllm_rbln/utils/optimum/converter/params.py`에서 vLLM 실행 경로가 요구하는 artifact를 확인했다.
- `optimum/rbln/transformers/models/decoderonly/configuration_decoderonly.py`에서 decoder bucket 기본값을 확인했다.
- `vllm_rbln/platform.py`의 `disable_unsupported_prefix_caching`에서 APC 자동 비활성 조건을 확인했다 (Stage 2 사전 정보).

### 3. HF metadata 조회 (network read-only)

`huggingface_hub.HfApi.model_info` / `list_repo_tree`와 `https://huggingface.co/<id>/raw/main/config.json` HTTPS GET만 사용했다. `snapshot_download`, `from_pretrained`, `git clone`, weight file 요청은 하지 않았다. Network는 차단되지 않았으므로 `BLOCKED` 항목은 없다.

조사 대상은 TASK02가 식별한 2개(`Qwen/Qwen3-4B`, `Qwen/Qwen3.5-0.8B`)와, 조사 중 설치 source에서 발견한 소형 후보 1개(`Qwen/Qwen3Guard-Gen-0.6B`)다.

### 4. KV bytes/token 파생 계산

관찰된 config 값으로만 계산했고 산식을 함께 남겼다.

## 변경된 파일

- `docs/environment/NPU_ENVIRONMENT.md` (말미에 재관찰 절 추가, 기존 내용 무변경)
- `docs/research/TASK05.md` (신규)
- `docs/research/INDEX.md` (결정 2 표 작성, Task Index/현재 상태 갱신)

Raw artifact는 `.gitignore` 대상인 `results/npu/inventory/20260819-155506-atom-max8/`에 보존했다.

## 실험 또는 검증 방법

측정 실험이 아니라 read-only 조사다. 사용한 command:

```bash
hostname; hostname -f; uname -a; lscpu
cat /sys/devices/system/node/node*/cpulist /sys/devices/system/node/node*/meminfo
rbln-smi
rbln-smi --topo
rbln-smi -g          # RSD group 조회 전용, 변경 subcommand(group/tdr/timeout/sort/mknod) 미사용
rbln-smi -L
grep -rIn ... /usr/local/lib/python3.10/dist-packages/{vllm_rbln,optimum/rbln}
python3 -c "huggingface_hub.HfApi().model_info(...) / list_repo_tree(...)"
curl 상당의 urllib GET https://huggingface.co/<id>/raw/main/config.json
```

## 결과

### 관찰 — 환경 재-inventory

Population: `atom-max8` host 1대의 전체 RBLN-visible device 32개. Source: `rbln-smi` (KMD ver 3.2.2), `lscpu`, sysfs. Device scope: 전 device. 측정이 아닌 inventory 조회다.

`NPU_ENVIRONMENT.md`의 항목 중 hostname을 제외한 **모든 대조 항목이 일치**했다.

- 일치: OS, kernel, architecture, NPU model(RBLN-CA25), visible ID 수(32), card grouping(4 ID × 8 card), device memory(ID당 15.7 GiB), idle 상태(전 ID `0.0B / 15.7GiB`, util `0.0`, active context 없음), NUMA 분할(node0 `rbln0`–`rbln15`, node1 `rbln16`–`rbln31`), topology distance class(4/8/12), RSD group(Grp 0에 32 ID 전부), tool 가용성
- 불일치: hostname (`rebel-pcie-0123` vs `atom-max8`)
- 신규 관찰: KMD version `3.2.2`, CPU AMD EPYC 9254 24-Core × 2 socket / 96 logical CPU, NUMA node별 `MemTotal` 약 792 GB, 각 device의 PCI BUS ID와 UUID, `numactl` 미설치

`requested_condition`: 문서 기재 topology/NUMA/RSD/device inventory가 현재 host에서 유효한지 확인.
`observed_condition`: hostname을 제외한 전 항목 값이 동일.
`condition_reached`: `PARTIAL`. 값 일치는 관찰했으나 두 조사가 동일 물리 장비라는 증거는 얻지 못했다.

### 관찰 — 후보 model metadata

Population: HF Hub의 model repository 3개. Unit: byte(파일 크기), 개수(layer/head), token. Source: `huggingface.co` HTTPS metadata API 및 `raw/main/config.json` (조회 시각 2026-08-19 15:59 KST). Device scope: 해당 없음.

| 항목 | `Qwen/Qwen3-4B` | `Qwen/Qwen3Guard-Gen-0.6B` | `Qwen/Qwen3.5-0.8B` |
|---|---|---|---|
| `architectures` | `Qwen3ForCausalLM` | `Qwen3ForCausalLM` | `Qwen3_5ForConditionalGeneration` |
| `model_type` | `qwen3` | `qwen3` | `qwen3_5` (text sub-config `qwen3_5_text`) |
| safetensors 총 크기 | 8,044,982,000 B = 7.492 GiB | 1,503,300,328 B = 1.400 GiB | 1,746,942,600 B = 1.627 GiB |
| repo 총 크기 | 8,060,926,626 B = 7.507 GiB | 1,519,204,911 B = 1.415 GiB | 1,769,980,465 B = 1.648 GiB |
| parameter 수 | 4,022,468,096 (전부 BF16) | 751,632,384 | 873,438,784 (BF16 873,436,192 + F32 2,592) |
| license | apache-2.0 | apache-2.0 | apache-2.0 |
| gated | `False` | `False` | `False` |
| `hidden_size` | 2560 | 1024 | 1024 (text) |
| `num_hidden_layers` | 36 | 28 | 24 (text) |
| `num_key_value_heads` | 8 | 8 | 2 (text) |
| `head_dim` | 128 | 128 | 256 (text) |
| dtype | `torch_dtype: bfloat16` | `torch_dtype: bfloat16` | `text_config.dtype: bfloat16` |
| `max_position_embeddings` | 40,960 | 32,768 | 262,144 (text) |
| `sliding_window` / `use_sliding_window` | `null` / `false` | `null` / `false` | 필드 없음. `layer_types`는 `linear_attention`/`full_attention`만 사용 |
| attention 구성 | 36 layer 전부 full attention | 28 layer 전부 full attention | 24 layer 중 `full_attention` 6 + `linear_attention`(GatedDeltaNet) 18 |
| repo lastModified | 2025-07-26 | 2025-11-07 | 2026-03-02 |

### 파생 계산 — KV bytes/token

산식: `layers × num_key_value_heads × head_dim × 2 (K, V) × dtype bytes`. dtype은 config의 bf16을 근거로 2 byte를 적용했다. Unit: byte per token per sequence. 이는 config에서 유도한 **파생값**이며 runtime에서 관측한 값이 아니다. RBLN block 단위 padding, page table overhead, partition 구조는 포함하지 않았다.

- `Qwen/Qwen3-4B`: `36 × 8 × 128 × 2 × 2` = **147,456 B/token = 144.0 KiB/token**
- `Qwen/Qwen3Guard-Gen-0.6B`: `28 × 8 × 128 × 2 × 2` = **114,688 B/token = 112.0 KiB/token**
- `Qwen/Qwen3.5-0.8B`: full attention layer만 KV cache를 가진다. `6 × 2 × 256 × 2 × 2` = **12,288 B/token = 12.0 KiB/token**

`Qwen/Qwen3.5-0.8B`의 나머지 18개 `linear_attention` layer는 per-token KV가 아니라 **sequence당 고정 크기 state**를 가진다. `optimum/rbln/transformers/models/qwen3_5/modeling_qwen3_5.py`의 `_qwen3_5_linear_state_shapes`에서:

- `conv_dim = 2 × (linear_num_key_heads × linear_key_head_dim) + (linear_num_value_heads × linear_value_head_dim)` = `2 × (16 × 128) + (16 × 128)` = 6,144
- `conv_state` = `(batch, linear_conv_kernel_dim - 1, conv_dim)` → slot당 `3 × 6,144` = 18,432 element
- `recurrent_state` = `(batch, linear_num_value_heads × linear_key_head_dim, linear_value_head_dim)` → slot당 `2,048 × 128` = 262,144 element
- 18 layer 합계 = slot당 5,050,368 element. bf16 가정 시 10,100,736 B ≈ 9.63 MiB/sequence. **다만 이 state의 실제 dtype은 `UNKNOWN`이다** — config에 `mamba_ssm_dtype: float32`가 있고 `get_input_info`는 mask에 `rbln_config.dtype`을 쓴다. fp32라면 약 19.27 MiB/sequence다.

참고 파생값 (sequence 1개 기준, 위 산식 그대로 적용):

| 후보 | 1,024 token | 8,192 token | 40,960 token |
|---|---|---|---|
| `Qwen/Qwen3-4B` | 144 MiB | 1,152 MiB | 5,760 MiB |
| `Qwen/Qwen3Guard-Gen-0.6B` | 112 MiB | 896 MiB | (max_position 32,768 초과) |
| `Qwen/Qwen3.5-0.8B` (full-attn 부분만) | 12 MiB | 96 MiB | 480 MiB |

### 관찰 — 설치 package의 지원 근거

`vllm_rbln/utils/optimum/registry.py`:

- `_RBLN_GENERATION_MODELS`에 `"Qwen3ForCausalLM": ("qwen3", "RBLNQwen3ForCausalLM")`가 있다. → `Qwen3-4B`와 `Qwen3Guard-Gen-0.6B`는 text decoder-only 경로에 등록되어 있다.
- `Qwen3_5ForConditionalGeneration`은 `_RBLN_GENERATION_MODELS`가 아니라 **`_RBLN_MULTIMODAL_MODELS`**에 `("qwen3_5", "RBLNQwen3_5ForConditionalGeneration")`으로 등록되어 있다. `Qwen3_5ForCausalLM`(text-only 변형)은 registry의 어느 dict에도 없다.

`optimum-rbln`의 compile entrypoint와 예시:

- CLI: `optimum-rbln-cli --model-id Qwen/Qwen3-4B -o ./compiled_qwen3 --max_seq_len 8192 --batch_size 1 --num_devices 4` — `optimum/rbln/cli.py`의 quick-start 예시와 `optimum_rbln-0.11.1.dist-info/METADATA`의 README 예시에 동일하게 등장한다.
- Python: `RBLNQwen3ForCausalLM.from_pretrained("Qwen/Qwen3-4B", export=True, rbln_batch_size=1, rbln_num_devices=4)` — `modeling_qwen3.py`, `configuration_qwen3.py` docstring.
- `Qwen/Qwen3.5-0.8B`는 `modeling_qwen3_5.py`의 `RBLNQwen3_5ForCausalLM` docstring 1곳에만 등장한다: `rbln_config={"num_devices": 1, "kvcache_partition_len": 4096, "max_seq_len": 8192, "device": 0}`.
- `Qwen/Qwen3Guard-Gen-0.6B`는 `optimum/rbln/diffusers/pipelines/cosmos/cosmos_guardrail.py`의 `base_model_id` / `textguard_model_id` 기본값으로만 등장한다. decoder-only compile 예시로는 등장하지 않는다.

vLLM 실행 경로:

- `vllm_rbln/envs.py`의 `VLLM_RBLN_USE_VLLM_MODEL` 기본값은 `False`이며, 이 경로에서 `vllm_rbln/utils/optimum/converter/params.py`는 `vllm_config.model_config.model` 디렉터리에서 `rbln_config.json`을 읽는다. 없으면 `"rbln_config.json not found in model directory"`로 실패한다. → **기본 경로에서 vLLM 실행 전에 optimum-rbln compile artifact가 반드시 필요하다.**
- `VLLM_RBLN_USE_VLLM_MODEL=True`인 두 번째 경로가 있고 `VLLM_RBLN_COMPILE_MODEL`(기본 `True`) 등 별도 env가 적용된다. `vllm_rbln/models/qwen3.py`가 존재한다. 이 경로의 Stage 0 적합성은 이번 조사에서 확인하지 않았다 (`UNKNOWN`).

Device 요구:

- `optimum/rbln/configuration_utils.py`에서 `num_devices` 기본값은 `None`이고, model 크기로부터 최소 device 수를 자동 유도하는 코드는 찾지 못했다. `tensor_parallel_size`는 `num_devices`의 deprecated alias다.
- 따라서 각 후보의 **최소** device 수는 `UNKNOWN`이며, 위 숫자는 문서화된 예시값일 뿐이다.

Decoder bucket 기본 config:

- `configuration_decoderonly.py`에서 `decoder_batch_sizes`가 `None`이면 `[batch_size]`가 되어 **기본적으로 decoder bucket이 1개**다. 지정 시 `batch_size`보다 큰 값은 error, 최대값이 `batch_size`보다 작으면 `batch_size`를 추가하고 내림차순 정렬한다.

Stage 2 사전 정보:

- `vllm_rbln/platform.py`의 `disable_unsupported_prefix_caching`은 sliding window model, pooling model, encoder-decoder model, Qwen3 pooling model에서 prefix caching을 자동으로 끈다. `_uses_sliding_window`는 `sliding_window`가 `None`이 아니거나 `layer_types`에 `sliding`이 포함될 때 True다.
- 세 후보 모두 이 조건에 걸리지 않는다 (`Qwen3-4B`, `Qwen3Guard`는 `sliding_window: null`·`use_sliding_window: false`, `Qwen3.5`의 `layer_types`에는 `sliding` 문자열이 없다).

### 관찰 — compile 비용

Compile 소요시간과 compiled artifact 크기의 근거를 설치 package와 metadata에서 찾지 못했다. **`UNKNOWN`이며 추정하지 않는다.**

## 핵심 발견

1. TASK02가 "소형 source example"로 분류한 `Qwen/Qwen3.5-0.8B`는 실제로 **vision-language checkpoint**다. `architectures`가 `Qwen3_5ForConditionalGeneration`이고 config에 `vision_config`, `image_token_id`, `video_token_id`가 있으며, vllm-rbln registry에서도 multimodal 경로에 등록되어 있다. TASK02의 "소형 text 후보" 기술은 이 관찰로 정정된다.
2. 같은 model의 text backbone은 **hybrid**다. 24 layer 중 18개가 GatedDeltaNet `linear_attention`이라 per-token KV cache가 없다. 이 저장소의 연구 대상(KV lifecycle, cache attribution, memory turnover)에서 이 model을 첫 baseline으로 쓰면 KV 관측 대상 자체가 layer의 1/4로 줄고, 나머지는 성격이 다른 recurrent state가 된다.
3. 설치 package에서 **end-to-end compile command가 문서화된 후보는 `Qwen/Qwen3-4B` 하나뿐**이다 (CLI help, class docstring 2곳, package README).
4. 기본 vLLM 실행 경로는 optimum-rbln이 만든 `rbln_config.json`을 요구한다. 즉 Stage 0는 download와 compile 두 단계를 모두 승인받아야 진행된다. TASK02의 `BLOCKED` 판정 근거가 source 수준에서 재확인됐다.
5. `Qwen/Qwen3Guard-Gen-0.6B`는 `Qwen3ForCausalLM` architecture이므로 `Qwen3-4B`와 **동일한 registry entry와 compile class**를 쓰면서 download가 5.4배 작다. 다만 KV bytes/token은 112 KiB로 144 KiB의 78% 수준이라 KV 압력은 크게 줄지 않는다.
6. `atom-max8` hardware inventory는 hostname을 제외하고 환경 문서와 전부 일치했다.

## 해석

이하는 관찰이 아닌 해석·가설이다.

- 재-inventory의 전 항목 일치는 "환경 문서의 hardware 기술을 현재 host의 실험 설계 근거로 써도 된다"는 실용적 판단을 지지한다. 그러나 hostname 불일치의 원인은 여전히 `UNKNOWN`이고, 동일 장비라는 결론으로 승격하지 않는다. 두 조사가 같은 사양의 다른 장비였을 가능성을 배제할 증거가 없다.
- Stage 0의 목적은 KV lifecycle 연구의 baseline 확보이지 "가장 싼 bring-up"이 아니다. 그렇다면 후보 선택에서 download 크기보다 **KV semantics의 단순성과 지원 근거의 강도**가 우선한다는 것이 이번 조사의 함의다.
- `Qwen3.5-0.8B`의 hybrid 구조는 나중에 그 자체로 흥미로운 비교 대상이 될 수 있다 (linear-attention state와 KV cache의 turnover 차이). 그러나 baseline이 확립되기 전에 도입하면 관측 대상과 confounder를 분리할 수 없다.
- `Qwen3-4B` bf16 weight 7.5 GiB를 문서 예시대로 4 device에 tensor parallel로 나누면 device당 약 1.9 GiB이고, device memory는 ID당 15.7 GiB다. 이는 균등 분할을 가정한 산술일 뿐 실제 배치·overhead·activation 예약을 반영하지 않는다. KV pool 실효 용량은 `UNKNOWN`이다.

## 확인되지 않은 사항

- hostname `rebel-pcie-0123`과 `atom-max8`의 관계 (`UNKNOWN`)
- 각 후보의 **최소** device 수. 문서화된 예시값만 확보했다 (`UNKNOWN`)
- compile 소요시간, compiled artifact 크기, host disk 요구량 (`UNKNOWN`)
- `Qwen3.5-0.8B` linear state의 실제 dtype과 그에 따른 sequence당 byte (`UNKNOWN`)
- KV block/page 단위 padding, partition 구조를 반영한 실효 KV 소비 (파생 계산은 이론값)
- `VLLM_RBLN_USE_VLLM_MODEL=True` 경로의 Stage 0 적합성 (`UNKNOWN`)
- Host↔NPU, NPU↔NPU bandwidth/latency (`UNKNOWN` 유지)
- 각 후보가 실제로 compile·load·generate에 성공하는지. 어떤 후보도 실행하지 않았다.

## 실패 / 무효 시도

- `numactl --hardware`는 이 host에 `numactl`이 설치되어 있지 않아 실행하지 못했다 (`command not found`). 설치는 dependency 변경이므로 시도하지 않고 `lscpu`와 `/sys/devices/system/node`로 대체했다.
- `openai/gpt2`의 metadata 조회는 `RepositoryNotFoundError (401)`로 실패했다. 이 후보는 조사 대상이 아니었고 후속 판단에 사용하지 않았다.
- Network 차단으로 인한 `BLOCKED` 항목은 없었다.
- Model download, compile, inference, device/RSD 변경은 수행하지 않았다.

## 연구 원칙에 미치는 영향

- Model 후보를 "설치 metadata에 이름이 등장한다"만으로 동급 취급하지 않는다. registry 분류(generation / multimodal / embedding), architecture의 KV 구조, compile 예시의 존재 여부를 분리해 등급을 매긴다.
- KV bytes/token은 layer 수만이 아니라 **어느 layer가 실제로 KV cache를 갖는지**에 의존한다. hybrid attention model에서 `layers × kv_heads × head_dim × 2 × dtype`을 전체 layer에 일괄 적용하면 과대 계산된다.
- 환경 문서 값의 재확인은 provenance 불일치를 해소하지 않는다. 값 일치와 장비 동일성을 구분해 기록한다.

## 다음 작업

사용자가 [INDEX](INDEX.md)의 결정 2를 판정하면 그에 따라 Stage 0를 재개한다. 판정 전에는 download, compile, inference를 시작하지 않는다. Stage 0 재개 시 measurement가 포함되므로 [TASK04](TASK04.md)에서 도입한 선등록 규칙에 따라 판정 기준을 먼저 commit한다.

## 재현 정보

- Base commit: `3ec545efa40f6b3deb83f1cbf6489d7db1a879e2`
- Branch: `minnow` (`main`은 `/home/rebel/continuum-npu` worktree에 checkout됨)
- 선등록 commit: 해당 없음 (측정이 없는 read-only 조사 TASK)
- Raw artifact: `results/npu/inventory/20260819-155506-atom-max8/`
  - 환경: `host.txt`, `lscpu.txt`, `numa-sysfs.txt`, `numactl-hardware.txt`(실패 기록), `rbln-smi.txt`, `rbln-smi-topo.txt`, `rbln-smi-group.txt`, `rbln-smi-list.txt`, `rbln-smi-help.txt`
  - Model: `model-metadata/hf-metadata.json`, `model-metadata/Qwen__Qwen3-4B.config.json`, `model-metadata/Qwen__Qwen3.5-0.8B.config.json`, `model-metadata/Qwen__Qwen3Guard-Gen-0.6B.config.json`
- HF metadata 조회 시각: 2026-08-19 15:59 (Asia/Seoul), source `huggingface.co`
- 근거 source 경로 (installed, 무변경):
  - `/usr/local/lib/python3.10/dist-packages/vllm_rbln/utils/optimum/registry.py`
  - `/usr/local/lib/python3.10/dist-packages/vllm_rbln/utils/optimum/converter/params.py`
  - `/usr/local/lib/python3.10/dist-packages/vllm_rbln/envs.py`
  - `/usr/local/lib/python3.10/dist-packages/vllm_rbln/platform.py`
  - `/usr/local/lib/python3.10/dist-packages/optimum/rbln/cli.py`
  - `/usr/local/lib/python3.10/dist-packages/optimum/rbln/transformers/models/qwen3/{modeling_qwen3.py,configuration_qwen3.py}`
  - `/usr/local/lib/python3.10/dist-packages/optimum/rbln/transformers/models/qwen3_5/modeling_qwen3_5.py`
  - `/usr/local/lib/python3.10/dist-packages/optimum/rbln/transformers/models/decoderonly/configuration_decoderonly.py`
  - `/usr/local/lib/python3.10/dist-packages/optimum_rbln-0.11.1.dist-info/METADATA`
