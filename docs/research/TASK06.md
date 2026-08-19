# TASK06 — Stage 0 실행: Qwen/Qwen3-4B download·compile·CA25 단일 추론

## 상태

DONE

## 날짜

2026-08-19

## 목적

[INDEX](INDEX.md) 결정 2가 판정 완료(선택지 A 승인)되었으므로, 선등록한 판정 기준에 따라 Stage 0를 실행한다. `Qwen/Qwen3-4B` weight를 download하고 승인된 파라미터로 optimum-rbln compile을 수행한 뒤, 설치된 `vllm 0.22.0+cpu` + `vllm-rbln 0.11.1` 경로로 실제 CA25에서 batch/request = 1의 단일 inference를 1회 수행한다. Stage 0 gate를 판정하고, 이후 재컴파일 예산 산정에 필요한 compile cost와 runtime device mapping을 측정한다.

## 배경

관련 TASK:

- [TASK02](TASK02.md) — Stage 0 사전 검증. 실행 가능한 model artifact 부재로 `BLOCKED`였다. 이 TASK가 그 blocker를 해소한다.
- [TASK05](TASK05.md) — 후보 model metadata 조사와 `atom-max8` 재-inventory. 결정 2의 근거 표를 만들었고 `Qwen/Qwen3-4B`를 권고했다.
- [TASK04](TASK04.md) — 선등록 hard rule 도입. 이 TASK는 그 규칙이 적용된 첫 측정 TASK다.

선등록 문서: [STAGE0_PREREG.md](STAGE0_PREREG.md)

## 시작 상태

- Repository / branch / worktree: `/home/rebel/continuum-npu` / `main` (단일 worktree)
- 작업 시작 시 HEAD: `6453a112c0db517234d7e2cdbea5524df38557ec`. `git merge --ff-only 6453a11`은 `Already up to date`였다.
- 선등록 commit: `805c93be8bdc4e5020189aa513fd286713b16738`
- Git dirty: untracked `.idea/`만 존재. 이 디렉터리는 agent 소유가 아니므로 stage하지 않았다.
- Host: `atom-max8`, `Linux-6.8.0-40-generic-x86_64-with-glibc2.35`
- Python: `/usr/bin/python3` 3.10.12
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch-rbln 0.3.0`, `torch 2.11.0+cpu`, `transformers 5.8.1`, `huggingface_hub 1.27.0`
- Device: RBLN-CA25 32 visible ID, 전부 idle (`0.0B / 15.7GiB`, util `0.0`, active context 없음), KMD ver 3.2.2
- Disk: `/` 876 GiB 중 789 GiB 여유

## 수행 내용

1. `main` 정합화 확인 후 선등록 문서 `STAGE0_PREREG.md`, Stage 0 실행 script 2개, 고정 prompt 파일, `.gitignore`의 `models/` 항목을 **측정 시작 전에** commit했다 (`805c93b`).
2. 격리 launcher로 source isolation probe를 재실행했다.
3. `Qwen/Qwen3-4B` weight를 download하고 revision, wall-clock, 실측 크기를 기록했다.
4. Compile 직전 disk 여유를 캡처하고, 승인된 파라미터 그대로 `optimum-rbln-cli`를 `timeout 7200`과 `/usr/bin/time -v` 아래에서 실행했다.
5. 별도 shell에서 `rbln-smi`를 1초 주기로 폴링하면서 단일 inference를 실행했다. Script 내부에서도 model load 전 / load 후 / inference 후 3회를 캡처했다.
6. `rbln-smi`, `rbln-smi --topo`, `rbln-smi -L`로 사용 visible ID의 physical card·NUMA node 소속을 확인했다.
7. 선등록 PASS 조건 7개를 항목별로 대조해 판정했다.

RSD, device state, package, site-packages, `patches/`는 변경하지 않았다. `decoder_observability.py`는 실행하지 않았다.

## 변경된 파일

선등록 commit `805c93b`:

- `docs/research/STAGE0_PREREG.md` (신규)
- `experiments/npu/stage0/download_model.py` (신규)
- `experiments/npu/stage0/single_inference.py` (신규)
- `experiments/npu/stage0/prompt.txt` (신규)
- `.gitignore` (`models/` 추가)
- `docs/research/INDEX.md` (결정 2 판정 완료 반영)

이번 기록 commit:

- `docs/research/TASK06.md` (신규)
- `docs/research/INDEX.md` (Stage 0 상태 갱신)

Raw artifact는 `.gitignore` 대상인 `results/npu/stage0/20260819-163200-qwen3-4b/`에 보존했다. Compile artifact는 `.gitignore` 대상인 `models/Qwen3-4B-rbln-b1-s8192-d4/`에 있다.

## 실험 또는 검증 방법

`<RUN>` = `results/npu/stage0/20260819-163200-qwen3-4b`

```bash
# 0. main 정합화
git merge --ff-only 6453a11          # Already up to date

# 1. source isolation probe
experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/probes/runtime_probe.py \
  --output-dir <RUN>/probe

# 2. download
experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage0/download_model.py \
  --model-id Qwen/Qwen3-4B \
  --output-dir <RUN>/download

# 3. disk 여유 확인
df -h /home/rebel

# 4. compile (승인 파라미터 그대로, 2시간 상한 강제)
env -u PYTHONPATH /usr/bin/time -v timeout 7200 optimum-rbln-cli \
  --model-id Qwen/Qwen3-4B \
  --output-dir /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b1-s8192-d4 \
  --batch_size 1 --max_seq_len 8192 --num_devices 4

# 5. rbln-smi 폴링 (별도 shell, 1초 주기)
for i in $(seq 1 400); do { date -Is; rbln-smi; echo "=========="; } >> <RUN>/inference/rbln-smi-poll.txt; sleep 1; done

# 6. 단일 inference (RBLN_DEVICES 미설정)
env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage0/single_inference.py \
  --model-dir /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b1-s8192-d4 \
  --prompt-file /home/rebel/continuum-npu/experiments/npu/stage0/prompt.txt \
  --max-tokens 64 --seed 20260819 \
  --output-dir <RUN>/inference

# 7. device mapping
rbln-smi ; rbln-smi --topo ; rbln-smi -L
```

## 결과

### 조건 분리

- `requested_condition`: `Qwen/Qwen3-4B`, `max_seq_len=8192`, `batch_size=1`, `num_devices=4`, request 1개, greedy(`temperature=0.0`, `top_p=1.0`), `max_tokens=64`, seed 20260819, `RBLN_DEVICES` 미설정.
- `observed_condition`: 위 요청값이 그대로 적용됐다. compile된 `rbln_config.json`의 `batch_size=1`, `max_seq_len=8192`, `num_devices=4`가 확인됐고, vLLM이 이를 읽어 `max_model_len`을 40960 → 8192로, `max_num_batched_tokens`를 8192 → 128로 갱신했다. 실제 실행은 visible ID `rbln0`–`rbln3`에서 이루어졌다.
- `condition_reached`: `YES`.

### 관찰 — source isolation

Source: 격리 launcher를 통한 `runtime_probe.py` 및 inference script 내부 assert. Device scope: 해당 없음.

```text
python: /usr/bin/python3 (3.10.12)
vllm.__file__: /usr/local/lib/python3.10/dist-packages/vllm/__init__.py
vllm.__version__: 0.22.0 / distribution 0.22.0+cpu
vllm_rbln.__file__: /usr/local/lib/python3.10/dist-packages/vllm_rbln/__init__.py
vllm-rbln distribution: 0.11.1
repository-local vllm/: 없음
isolation invariant: PASS
```

### 관찰 — download

Population: HF repo `Qwen/Qwen3-4B` 1개. Unit: byte, 초. Source: `huggingface_hub 1.27.0` `snapshot_download`.

| 항목 | 값 |
|---|---|
| revision (commit hash) | `1cfa9a7208912126459214e8b04321603b3df60c` |
| snapshot 경로 | `/home/rebel/.cache/huggingface/hub/models--Qwen--Qwen3-4B/snapshots/1cfa9a7208912126459214e8b04321603b3df60c` |
| download wall-clock | 66.79 s |
| 실측 on-disk 크기 | 8,060,926,626 B = 7.507 GiB |
| 파일 수 | 13 |
| 시각 (UTC) | 2026-08-19T07:32:09 → 07:33:15 |

실측 크기는 TASK05가 HF metadata에서 읽은 repo 총 크기 8,060,926,626 B와 **byte 단위로 일치**했다.

### 관찰 — compile

Population: compile job 1회. Unit: byte, 초. Source: `optimum-rbln-cli 0.11.1` + `rebel-compiler 0.11.1.post1`, `/usr/bin/time -v`.

| 항목 | 값 |
|---|---|
| 추론된 RBLN class | `RBLNQwen3ForCausalLM` |
| exit code | 0 |
| **compile wall-clock** | **165.0 s (2.75 min)**. `/usr/bin/time` 기준 2:44.92 |
| host CPU time | user 429.24 s + sys 612.36 s, CPU 사용률 631 % |
| host peak RSS | 34,801,256 KiB ≈ 33.2 GiB |
| **compile artifact 총 크기** | **9,752,342,327 B = 9.083 GiB** |
| 시각 | 2026-08-19 16:33:34 → 16:36:19 (KST) |

Artifact 구성:

| 파일 | 크기 |
|---|---|
| `prefill.rbln` | 8,899,037,284 B = 8.288 GiB |
| `decoder_batch_1.rbln` | 841,829,476 B = 803.0 MiB |
| `tokenizer.json` | 11,422,650 B |
| `rbln_config.json` | 42,153 B |
| `config.json`, `generation_config.json`, `tokenizer_config.json`, `chat_template.jinja` | 합계 6.6 KiB |

Tokenizer 파일이 artifact 디렉터리에 함께 저장되었으므로 선등록의 `--tokenizer` 예외 경로는 사용하지 않았다.

Disk 사용량: compile 전 `/` 사용 51 GiB → compile 후 60 GiB. download + compile artifact 합계 증가분은 약 17 GiB로, 선등록 예산 100 GiB의 17 %다. Compile wall-clock 165 s는 예산 2시간의 2.3 %다. **두 예산 모두 초과하지 않았다.**

`rbln_config.json`의 주요 값:

| key | 값 |
|---|---|
| `batch_size` | 1 |
| `max_seq_len` | 8192 |
| `num_devices` | 4 (`_compile_cfgs` 2개 entry 모두) |
| `dtype` | `bfloat16` |
| `kvcache_block_size` | 8192 |
| `kvcache_num_blocks` | 1 |
| `kvcache_partition_len` | `None` |
| `prefill_chunk_size` | 128 |
| `decoder_batch_sizes` | `[1]` |
| `attn_impl` / `cache_impl` | `eager` / `static` |
| `sliding_window` / `sliding_window_layers` | `None` / `[]` |
| `phases` | `['prefill', 'decode']` |
| `kvcache_metas` | layer당 shape `[1, 8, 8192, 128]`, `layer_type: full_attention` |

`kvcache_metas`의 layer별 shape `[batch=1, kv_heads=8, seq=8192, head_dim=128]`은 TASK05가 config에서 파생 계산한 KV 산식(`36 × 8 × 128 × 2 × 2` = 144.0 KiB/token)의 head 구성과 일치한다. 다만 이는 compile artifact가 선언한 shape이며 device 상의 실효 점유(padding·page table 포함)를 관측한 값은 아니다.

### 관찰 — 단일 inference

Population: request 1개. Unit: token, 초. Source: `vllm 0.22.0+cpu` offline `LLM.generate`. Device scope: `rbln0`–`rbln3`.

| 항목 | 값 |
|---|---|
| exit code | 0 |
| input token 수 | 12 |
| output token 수 | 64 |
| finish reason | `length` (`max_tokens=64` 도달) |
| engine load wall-clock | 44.87 s (그중 engine core init 27.68 s) |
| end-to-end generate latency | 0.702 s |
| 시각 (UTC) | 2026-08-19T07:38:06.98 → 07:38:07.68 |

출력 텍스트 (381자):

```text
 A neural processing unit (NPU) is a specialized piece of hardware designed to efficiently handle tasks related to artificial intelligence, particularly those involving neural networks. It is optimized for processing large volumes of data with high parallelism, making it suitable for applications like machine learning, computer vision, and natural language processing. 

A neural
```

Latency 0.702 s는 **1회 관측값**이다. 평균, 분산, 다른 조건과의 비교 등 통계적 주장을 하지 않는다. TTFT는 이 경로에서 분리 관측하지 않았다.

vLLM resolved config:

| 항목 | 값 |
|---|---|
| `max_model_len` | 8192 (40960에서 `rbln_config.json` 기준으로 갱신) |
| `max_num_seqs` | 1 |
| `max_num_batched_tokens` | 128 (8192에서 갱신) |
| `block_size` | 128 |
| `num_gpu_blocks` | 130 |
| GPU KV cache size (log) | 8,320 token |
| `enable_prefix_caching` | `True` |
| `tensor_parallel_size` / `world_size` | 1 / 1 |
| `model_config.dtype` | `torch.float32` |
| scheduler | `vllm_rbln.v1.core.optimum_scheduler.RBLNOptimumScheduler` |

### 관찰 — device mapping

Source: `rbln-smi`, `rbln-smi --topo`, `rbln-smi -L`. Device scope: 전 32 visible ID.

`RBLN_DEVICES`를 설정하지 않았고, 실행 process가 model context를 만든 visible ID는 **`rbln0`, `rbln1`, `rbln2`, `rbln3`** 4개다.

| visible ID | PCI BUS ID | NUMA node | CPU affinity | 상호 topology distance |
|---|---|---|---|---|
| `rbln0` | `0000:05:00.0` | 0 | 0-23,48-71 | 4 |
| `rbln1` | `0000:06:00.0` | 0 | 0-23,48-71 | 4 |
| `rbln2` | `0000:07:00.0` | 0 | 0-23,48-71 | 4 |
| `rbln3` | `0000:08:00.0` | 0 | 0-23,48-71 | 4 |

`rbln-smi`의 device 표에서 이 4개는 **하나의 `RBLN-CA25` 블록**으로 묶여 표시되고 그 블록에만 Power 값(단일 카드 단위)이 표시된다. Topology 표에서 네 ID 상호 distance는 전부 4이고, 다음 블록(`rbln4`–`rbln7`)까지는 8, 다른 NUMA node(`rbln16`+)까지는 12이다.

즉 **문서화된 `num_devices=4`는 동일 physical card(distance-4 그룹, NUMA node 0) 안에 배치되었다.**

### 관찰 — NPU 실행 증거 (선등록 조건 6)

Source: `rbln-smi` 3회 캡처 + 1초 주기 폴링 79 snapshot. Device scope: 전 32 visible ID.

선등록한 3개 신호가 **모두** 관측됐다.

1. **Memory**: `rbln0`–`rbln3`가 `0.0B` → `2.2GiB`(`rbln0`는 `2.3GiB`)로 증가했다. 다른 28개 ID는 전 구간 `0.0B`를 유지했다.
2. **Utilization**: 폴링 중 `rbln0` 27.9 / 30.8, `rbln1` 21.1 / 36.9, `rbln2` 57.8, `rbln3` 1.4 / 56.4가 관측됐다. Baseline은 전부 `0.0`이었다.
3. **Context**: `rbln-smi`의 Context Information에 `VLLM::EngineCor` PID 267516이 나타났다.

부수 관측:

- `rbln0`–`rbln3`의 Perf state가 `P14` → `P2`로 전환됐고, 해당 카드의 Power는 idle 45.1 W에서 최대 136.7 W까지 상승했다. `rbln0` 온도는 38 °C → 46 °C.
- Model load 직후 context 목록에는 **36개 row**가 있었다. `rbln0`–`rbln3`에 memalloc `2.2GiB`인 context 4개(CTX 10001–10004, PTID 1–4), `rbln0`에 `64.0MiB` context 1개, 그리고 **32개 visible ID 전부에 memalloc `0.0B`인 context 1개씩**이다.

### 선등록 PASS 조건 대조

| # | 조건 | 결과 | 근거 |
|---|---|---|---|
| 1 | site-packages `vllm 0.22.0+cpu` + `vllm-rbln 0.11.1`, isolation `PASS` | 충족 | probe 및 script 내부 assert 통과 |
| 2 | weight download 완료 + revision 기록 | 충족 | `1cfa9a72…`, 7.507 GiB |
| 3 | 승인 파라미터로 compile 성공 + 경로·크기 기록 | 충족 | exit 0, `models/Qwen3-4B-rbln-b1-s8192-d4`, 9.083 GiB |
| 4 | batch/request = 1, 고정 prompt 1개, 유의미한 텍스트 출력 | 충족 | output token 64개, 381자, 영문 단어 다수, special token만으로 구성되지 않음 |
| 5 | runtime device mapping 기록 | 충족 | `rbln0`–`rbln3` = 단일 physical card, NUMA node 0 |
| 6 | NPU 실행 증거 (memory 또는 utilization 변화) | 충족 | memory·utilization·context 3개 신호 모두 관측 |
| 7 | 재현 가능한 command 전문 기록 | 충족 | 위 "실험 또는 검증 방법" 절 |

### 판정

**Stage 0 = `PASS`.** 선등록한 7개 조건을 전부 충족했다. 측정 후 기준을 완화하거나 조정하지 않았다.

## 핵심 발견

1. Stage 0 gate가 열렸다. TASK02 이후 유지된 "실행 가능한 model artifact 부재" blocker가 해소됐고, 이 저장소에서 실제 CA25 inference가 가능함이 관측으로 확인됐다.
2. **Compile cost는 예상보다 훨씬 작다.** `Qwen/Qwen3-4B`, `batch_size=1`, `max_seq_len=8192`, `num_devices=4` 기준으로 165 s / 9.08 GiB다. 재컴파일이 실험 설계의 실질적 제약이 아니라는 뜻이므로, 이후 `max_seq_len`이나 `batch_size`를 바꾸는 실험 격자를 compile 비용 때문에 좁힐 필요가 없다. 단 host peak RSS 33.2 GiB는 compile 동시 실행의 제약이 될 수 있다.
3. Artifact 9.08 GiB 중 `prefill.rbln`이 8.29 GiB로 91 %를 차지하고 `decoder_batch_1.rbln`은 803 MiB다. `decoder_batch_sizes=[1]`이므로 decoder bucket은 1개이며, bucket을 늘리면 늘어나는 쪽은 decoder artifact다.
4. 문서화된 `num_devices=4`는 **동일 physical card 안에서** 충족됐다. 기본 할당은 `RBLN_DEVICES` 없이 `rbln0`–`rbln3`을 골랐고, 이는 topology 표의 distance-4 그룹과 정확히 일치한다.
5. Model이 점유한 device memory는 ID당 2.2 GiB다. bf16 weight 7.5 GiB를 4-way로 나눈 산술값 약 1.9 GiB보다 크지만 같은 자릿수다. Device당 15.7 GiB 중 약 13.4 GiB가 남아 있다.
6. **vLLM이 유도한 KV cache 규모가 작다.** `rbln_config.json`의 `kvcache_num_blocks`가 1이고 vLLM은 이를 `block_size=128`, `num_gpu_blocks=130`, "GPU KV cache size: 8,320 tokens"로 변환했다. 8,320 token은 `max_model_len` 8192를 갓 넘는 수준이라 **동시 sequence를 담을 여유가 사실상 없다.** Stage 1·2의 multi-request KV pressure 실험을 설계할 때 이 값이 1차 제약이다.
7. `enable_prefix_caching`이 별도 지정 없이 `True`로 resolve됐다. TASK05가 예측한 대로 이 model은 `disable_unsupported_prefix_caching`의 자동 비활성 대상이 아니다. Stage 2의 APC OFF/ON 구성은 명시적 지정으로 통제해야 한다.
8. 실행 process는 사용하지 않는 28개 ID를 포함해 **32개 visible ID 전부에 memalloc 0의 context를 열었다.** 이는 다른 실험이 동시에 device를 쓸 때의 간섭 여부와 관련되므로 기록해 둔다.

## 해석

이하는 관찰이 아니라 파생 해석과 hypothesis다.

- **(hypothesis)** `num_devices=4`가 distance-4 그룹으로 잡힌 것은 `rbln_worker._init_device_env`가 `RBLN_DEVICES` 부재 시 `range(0, world_size × num_devices)`를 선택하기 때문일 뿐, tensor-parallel 대상을 topology 기준으로 고르는 로직이 확인된 것은 아니다. 결과가 같은 카드로 떨어진 것은 "visible ID 번호 순서가 physical card 그룹 순서와 일치한다"는 이 host의 배치 덕분일 수 있다. `RBLN_DEVICES`로 card를 가로지르는 조합을 강제했을 때 무엇이 달라지는지는 이번 run에서 확인하지 않았다.
- **(hypothesis)** `kvcache_num_blocks=1`은 optimum-rbln이 `batch_size=1`·`kvcache_block_size=max_seq_len`으로 compile할 때 sequence 1개분만 잡은 결과로 보인다. 그렇다면 KV pool 용량은 compile 파라미터로 결정되며 runtime에서 늘릴 수 없다. 이 가설이 맞다면 Stage 2의 KV pressure 실험은 `batch_size`를 키운 재compile을 전제로 한다. 재compile cost가 165 s 수준이라는 이번 측정은 그 설계를 실행 가능하게 만든다. 다만 `num_gpu_blocks=130`과 "KV cache size 8,320 tokens"(= 65 × 128)의 관계는 `update_num_blocks`의 block ratio 변환을 거친 값이라 아직 정합적으로 설명되지 않는다 (아래 `UNKNOWN`).
- **(해석)** `model_config.dtype`이 `torch.float32`로 resolve된 것은 vLLM의 host-side model config 값이며, 실제 device 연산 dtype은 compile artifact의 `dtype: bfloat16`이 지배한다고 보는 것이 자연스럽다. 그러나 이번 run에서 device 연산 dtype을 직접 관측하지는 않았다.
- **(해석)** load 44.87 s 중 engine core init이 27.68 s이고 그 안에 warm-up(`VLLM_RBLN_ENABLE_WARM_UP` 기본 `True`)이 포함된다. 따라서 load 시간은 artifact 크기만의 함수가 아니며, 이후 실험에서 load cost를 비교할 때 warm-up 포함 여부를 조건으로 분리해야 한다.
- **(해석)** utilization 값이 폴링 79 snapshot 중 7개에서만 0이 아니었던 것은 generate 구간이 0.702 s로 1초 폴링 주기보다 짧기 때문이다. 이 metric은 sampling 한계가 크므로 utilization을 정량 지표로 사용하지 않는다. 이번 목적(실행 여부의 증거)에는 충분하다.

## 확인되지 않은 사항

- `num_gpu_blocks=130`과 log의 "GPU KV cache size: 8,320 tokens"(65 블록 × 128)의 정합 관계. `update_num_blocks`의 block ratio와 prefix-caching용 outer/inner block 변환을 source 수준에서 추적하지 않았다 (`UNKNOWN`).
- 32개 visible ID 전부에 memalloc 0 context가 열린 이유와, 그것이 다른 process의 device 사용을 제약하는지 (`UNKNOWN`).
- `Qwen/Qwen3-4B`의 **최소** device 수. `num_devices=4`만 검증했고 1, 2로 compile되는지는 시도하지 않았다 (`UNKNOWN`, TASK05에서 이월).
- Device당 2.2 GiB 점유의 내역(weight shard / kernel / KV / activation 예약 분해). `rbln-smi`는 합계만 보고한다 (`UNKNOWN`).
- TTFT와 per-token decode latency. 이번 경로에서 분리 관측하지 않았다.
- `hostname` `rebel-pcie-0123`과 `atom-max8`의 관계 (`UNKNOWN` 유지, TASK05에서 이월).
- `VLLM_RBLN_USE_VLLM_MODEL=True` 경로의 적합성 (`UNKNOWN` 유지). 이번 run은 기본 경로(`False`)만 사용했다.
- Host↔NPU, NPU↔NPU bandwidth/latency (`UNKNOWN` 유지).

## 실패 / 무효 시도

- 첫 inference 시도가 `FileNotFoundError: experiments/npu/stage0/prompt.txt`로 exit 1 실패했다. 원인은 `run_isolated_python.sh`가 임시 디렉터리로 `cd`한 뒤 script를 실행하는데 `--prompt-file`에 상대 경로를 넘겼기 때문이다. 실험 조건이나 device와 무관한 harness 경로 문제이며, prompt 파일의 절대 경로를 넘겨 재실행했다. 선등록한 실험 격자·판정 기준·script는 바꾸지 않았다. 이 실패는 device를 전혀 건드리지 않았다.
- 같은 이유로 `download_model.py`와 `single_inference.py`의 출력이 `--output-dir`의 상대 경로 기준으로 임시 디렉터리 안에 기록됐다. (`runtime_probe.py`는 `VLLM_CONTINUUM_REPO_ROOT` 기준으로 상대 경로를 해석하므로 영향이 없었다.) 해당 artifact를 `results/npu/stage0/20260819-163200-qwen3-4b/` 아래로 옮겨 보존했다. 측정값 자체는 영향을 받지 않았다.
- Model download·compile·inference 외의 시스템 변경은 하지 않았다. RSD 조회조차 이번 run에서는 수행하지 않았다.

## 연구 원칙에 미치는 영향

- "실행됨"과 "NPU에서 실행됨"을 분리한 선등록 조건이 실제로 유효했다. 이번에는 세 신호가 모두 관측되어 `PARTIAL`을 쓸 필요가 없었지만, utilization만으로 판정했다면 폴링 주기 때문에 놓칠 수 있었다. 짧은 run에서는 memory와 context를 1차 증거로 삼고 utilization은 보조로 쓴다.
- Compile 파라미터가 KV pool 용량을 결정한다는 점(가설)은 "requested condition과 observed condition을 분리한다"는 원칙을 compile 단계까지 확장해야 함을 시사한다. 이후 실험에서는 요청한 `batch_size`/`max_seq_len`뿐 아니라 그로부터 유도된 `kvcache_num_blocks`와 vLLM의 `num_gpu_blocks`를 함께 기록한다.
- Metadata에서 파생한 크기 추정(TASK05의 7.507 GiB)이 실측과 byte 단위로 일치했다. 반면 compile artifact 크기와 소요시간은 파생 추정 자체가 불가능했고 첫 측정이 유일한 근거였다. 파생 가능한 값과 측정으로만 얻을 수 있는 값을 계속 구분한다.
- 격리 launcher가 cwd를 바꾸므로 script에 넘기는 경로는 절대 경로를 쓰거나 script가 `VLLM_CONTINUUM_REPO_ROOT` 기준으로 해석해야 한다. 이후 Stage 실행에 동일하게 적용한다.

## 다음 작업

Stage 1 serving(`vllm serve` 기반 resolved config 기록과 endpoint 검증)이 다음 권장 작업이다. 사용자 지시 없이 자동 착수하지 않는다.

Stage 1 설계 시 이번 결과에서 이월할 사항:

- 이번 artifact는 `batch_size=1`, `kvcache_num_blocks=1`이라 동시 request 실험에는 부족할 가능성이 높다. Stage 1에서 어느 범위까지 이 artifact로 진행하고 어디서부터 재compile이 필요한지 먼저 판정한다.
- APC는 기본 `True`로 resolve되므로 Stage 2 이전에도 OFF/ON을 명시적으로 통제한다.
- 측정이 포함되므로 Stage 1도 판정 기준을 먼저 선등록 commit한다.

## 재현 정보

- 선등록 commit: `805c93be8bdc4e5020189aa513fd286713b16738`
- **측정 시작 시각: 2026-08-19 16:31:58 KST** (source isolation probe 실행). 선등록 commit 시각은 2026-08-19 16:31:50 KST이므로 **선등록이 측정보다 8초 앞선다.**
- 측정 종료 시각: 2026-08-19 16:38:08 KST (inference 종료)
- Base commit (측정 중 HEAD): `805c93be8bdc4e5020189aa513fd286713b16738`, dirty = `True` (untracked `.idea/` 및 gitignored `results/`, `models/`)
- Branch / worktree: `main` / `/home/rebel/continuum-npu`
- Model: `Qwen/Qwen3-4B` revision `1cfa9a7208912126459214e8b04321603b3df60c`
- Compile artifact: `models/Qwen3-4B-rbln-b1-s8192-d4/` (gitignored)
- Raw artifact: `results/npu/stage0/20260819-163200-qwen3-4b/` (gitignored)
  - `measurement-start.txt`
  - `probe/` — `environment.json`, `metadata.json`, `resolved_config.json`, `runtime_probe.log`
  - `download/` — `download.json`, `snapshot-listing.txt`
  - `df-before-download.txt`, `df-before-compile.txt`, `df-after-compile.txt`
  - `compile/` — `compile.log`, `started_at.txt`, `finished_at.txt`, `exit_code.txt`
  - `inference/` — `inference.json`, `inference.log`, `rbln-smi-before.txt`, `rbln-smi-after-load.txt`, `rbln-smi-after-inference.txt`, `rbln-smi-poll.txt`(79 snapshot), `started_at.txt`, `finished_at.txt`, `exit_code.txt`
  - `devices/` — `rbln-smi-baseline.txt`, `rbln-smi-topo.txt`, `rbln-smi-L.txt`
- 실행 script: `experiments/npu/stage0/download_model.py`, `experiments/npu/stage0/single_inference.py`, `experiments/npu/stage0/prompt.txt`
- Isolation launcher: `experiments/npu/launch/run_isolated_python.sh`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch-rbln 0.3.0`, `torch 2.11.0+cpu`, `transformers 5.8.1`, `huggingface_hub 1.27.0`
- Host: `atom-max8`, KMD ver 3.2.2
