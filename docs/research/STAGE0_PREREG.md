# Stage 0 선등록 — Qwen/Qwen3-4B download·compile·CA25 단일 추론

## 문서 성격

이 문서는 [CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md) "증거 기록 원칙"이 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit이 만들어진 뒤에 download, compile, inference를 시작한다. 측정 후 판정 기준을 완화하지 않으며, 완화가 불가피하면 원 기준의 실패를 함께 보고한다.

측정 결과와 판정은 이 문서에 쓰지 않고 후속 TASK 문서에 기록한다. 이 문서는 측정 전에 고정한 내용만 담는다.

## 승인 범위 (사용자 판정, 2026-08-19)

[INDEX](INDEX.md)의 **결정 2**에 대해 사용자가 선택지 **A. `Qwen/Qwen3-4B`** 를 승인했다.

승인된 것:

- `Qwen/Qwen3-4B` weight download (Hugging Face)
- optimum-rbln compile, 파라미터는 문서화된 검증 경로 그대로 `--max_seq_len 8192 --batch_size 1 --num_devices 4`
- compile artifact 저장 경로 `/home/rebel/continuum-npu/models/` (gitignore 대상)
- CA25 단일 inference 실행 (batch/request = 1)

승인되지 않은 것 (이번 작업에서 수행하지 않는다):

- RSD 변경, device reset, site-packages 수정, `patches/` 적용
- Stage 1 serving, Stage 2 APC, `decoder_observability.py` 실행, 추가 model download
- remote `push`
- 승인된 compile 파라미터의 임의 변경. 이 파라미터로 compile이 실패하면 파라미터를 바꿔 재시도하지 않고 실패 증거를 기록한다. 진단 목적의 read-only 조사는 허용한다.

## 예산 (사전 고정)

| 항목 | 상한 | 초과 시 처리 |
|---|---|---|
| Disk (download + compile artifact 합계) | 100 GiB | 중단, `BLOCKED` 기록, 사용자 보고 |
| Compile wall-clock | 2시간 | process 중단, 그 시점까지의 로그 보존, `BLOCKED` 기록 |

Compile 시작 전에 filesystem 여유 공간을 확인하고 기록한다. 예산 초과를 우회하지 않는다.

## 실험 격자

Sweep이 아니다. 단일 조건 1회 실행이다.

| 요소 | 고정값 |
|---|---|
| Model | `Qwen/Qwen3-4B` |
| Revision | download 시점의 HF main commit hash를 관측해 기록 (사전 고정 불가) |
| `max_seq_len` | 8192 |
| `batch_size` | 1 |
| `num_devices` | 4 |
| Request 수 | 1 |
| Prompt | `experiments/npu/stage0/prompt.txt` 파일 1개 (아래 원문) |
| Sampling | `temperature=0.0`, `top_p=1.0` (greedy) |
| `max_tokens` | 64 |
| Seed | 20260819 |
| Device 선택 | `RBLN_DEVICES`를 설정하지 않는다. vllm-rbln 기본 할당(`rbln_worker._init_device_env`)이 고르는 ID를 관측 대상으로 삼는다 |

Prompt 원문 (영어 단문 1개):

```text
Explain in two sentences what a neural processing unit is.
```

## PASS 조건

아래 7개 항목을 **전부** 충족할 때만 Stage 0를 `PASS`로 판정한다.

1. site-packages의 `vllm 0.22.0+cpu` + `vllm-rbln 0.11.1`을 사용한다 (source isolation probe `PASS`).
2. `Qwen/Qwen3-4B` weight download가 완료되고 revision(commit hash)을 기록한다.
3. 승인된 파라미터로 RBLN compile이 성공하고 artifact 경로와 크기를 기록한다.
4. 실제 CA25 inference가 성공한다. batch/request = 1, 위 고정 prompt 1개, 유의미한 텍스트 출력. "유의미"의 조작적 정의는 아래와 같다.
5. runtime device mapping을 기록한다. 사용된 RBLN visible ID 목록과, 그것이 어느 physical card / NUMA node에 속하는지.
6. NPU 실행 증거를 관측한다. inference 전/중/후 `rbln-smi`에서 memory 또는 utilization의 변화.
7. 재현 가능한 command 전문을 기록한다.

### 조건 4의 조작적 정의 (측정 전 고정)

출력 품질은 채점하지 않는다. 아래 3개를 모두 만족하면 "유의미한 텍스트 출력"으로 본다.

- decode된 output text가 빈 문자열이 아니고, 공백만으로 이루어지지 않는다.
- output token 수가 1개 이상이다.
- output text가 전부 special token 표기(`<|...|>` 형태) 또는 반복 제어 문자만으로 이루어지지 않는다. 즉 최소 1개의 일반 단어 문자(`[A-Za-z]`)를 포함한다.

문법성, 사실성, 지시 준수 여부는 판정 대상이 아니다.

### 조건 6의 조작적 정의 (측정 전 고정)

`rbln-smi`를 inference 전(model load 전), model load 후, inference 후 최소 3회 캡처하고, inference 구간 동안 별도 shell에서 주기적으로 폴링한다. 아래 중 **하나 이상**이 관측되면 조건 6을 충족한다.

- 어느 visible ID의 memory 사용량이 baseline `0.0B`에서 증가한다.
- 어느 visible ID의 utilization이 baseline `0.0`에서 증가한다.
- `rbln-smi`의 context/process 목록에 이번 실행 process가 나타난다.

폴링 주기의 한계로 utilization 변화를 놓칠 수 있음을 사전에 인정한다. 셋 중 아무것도 관측되지 않으면 조건 6은 미충족이며 조건 4가 충족되어도 `PARTIAL`이다.

## 예측 (측정 전 기록)

아래는 판정 기준이 아니라 사전 예측이다. 빗나가도 기준을 조정하지 않는다.

- Download 실측 크기는 TASK05의 HF metadata 값 7.507 GiB에 근접할 것이다. HF cache의 blob 중복 제거와 `.gitattributes` 등 부가 파일 때문에 정확히 일치하지 않을 수 있다.
- Compile artifact 크기는 bf16 weight 7.5 GiB와 같은 자릿수일 것이다. 정확한 값은 `UNKNOWN`이며 이번 compile이 그 값의 첫 측정이다.
- Compile wall-clock은 `UNKNOWN`이다. 2시간 상한 안에 끝날지도 `UNKNOWN`이다.
- 기본 device 할당은 `rbln0`–`rbln3`이 될 것으로 예측한다. `rbln_worker._init_device_env`가 `RBLN_DEVICES` 부재 시 `range(0, world_size * num_devices)`를 선택하기 때문이다. TASK05의 topology 관찰(4 ID × 8 card, distance 4 그룹)이 맞다면 이 4개는 동일 physical card에 속할 것이다. 이는 예측이며, 실제 관측 결과를 그대로 기록한다.
- vLLM의 resolved `max_model_len`은 `rbln_config.json`의 `max_seq_len`(8192)으로 덮어써질 것이다 (`from_optimum.py`).

## FAIL / PARTIAL 처리 규칙 (측정 전 고정)

| 상황 | 판정 | 보존할 증거 |
|---|---|---|
| download 성공, compile 실패 | `FAILED` | compile 로그 전문 |
| compile 성공, inference 실패 | `FAILED` | compile cost 측정값은 유효 기록으로 보존, inference 로그 |
| inference 성공, 조건 6(NPU 증거) 미관측 | `PARTIAL` | 전 구간 `rbln-smi` 캡처. "실행됨"과 "NPU에서 실행됨"을 구분해 기술 |
| 예산(disk 100 GiB 또는 compile 2시간) 초과로 중단 | `BLOCKED` | 중단 시점까지의 로그. INDEX "사용자 결정 대기"에 항목 재개설 |
| 조건 1(source isolation) 실패 | `INVALID` | probe 출력. 다른 조건의 결과를 연구 결론에 사용하지 않는다 |

## 필수 측정 항목

- Download: wall-clock, 실측 on-disk 크기, revision, 파일 수
- **Compile: wall-clock, artifact 크기** — 이후 재컴파일 예산 산정의 근거이므로 필수다. compile 중 host 자원(CPU/RAM) 관측은 선택이다.
- Inference: input token 수, output token 수, end-to-end latency, finish reason, output text
- Provenance: git commit과 dirty 여부, 전 package version, model revision, hostname, resolved vLLM config, 사용 device ID, `VLLM_RBLN*` 환경변수

Latency는 1회 관측값이다. 통계적 주장(평균, 분산, 비교)을 하지 않는다. TTFT는 offline `LLM.generate` 경로에서 분리 관측하지 않으므로 이번 run에서는 측정하지 않는다.

## 실행 절차 (측정 전 고정)

전 단계를 `experiments/npu/launch/run_isolated_python.sh` 또는 명시된 CLI로 수행하고 raw artifact를 `results/npu/stage0/<timestamp>-qwen3-4b/`에 보존한다 (`.gitignore` 대상).

1. **Source isolation probe**

   ```bash
   experiments/npu/launch/run_isolated_python.sh \
     experiments/npu/probes/runtime_probe.py \
     --output-dir results/npu/stage0/<RUN>/probe
   ```

2. **Download**

   ```bash
   experiments/npu/launch/run_isolated_python.sh \
     experiments/npu/stage0/download_model.py \
     --model-id Qwen/Qwen3-4B \
     --output-dir results/npu/stage0/<RUN>/download
   ```

3. **Disk 여유 확인** — `df -h /home/rebel`를 compile 시작 전에 캡처한다.

4. **Compile** (승인된 파라미터 그대로, `timeout 7200`으로 2시간 상한 강제)

   ```bash
   timeout 7200 optimum-rbln-cli \
     --model-id Qwen/Qwen3-4B \
     --output-dir /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b1-s8192-d4 \
     --batch_size 1 --max_seq_len 8192 --num_devices 4
   ```

5. **Inference** (`RBLN_DEVICES` 미설정, 별도 shell에서 `rbln-smi` 폴링)

   ```bash
   experiments/npu/launch/run_isolated_python.sh \
     experiments/npu/stage0/single_inference.py \
     --model-dir /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b1-s8192-d4 \
     --prompt-file experiments/npu/stage0/prompt.txt \
     --max-tokens 64 --seed 20260819 \
     --output-dir results/npu/stage0/<RUN>/inference
   ```

   compile artifact 디렉터리에 tokenizer 파일이 없으면 `--tokenizer`에 download된 HF snapshot 경로를 넘긴다. 이는 사전 등록한 예외이며 새 download를 유발하지 않는다.

6. **Device mapping 확인** — `rbln-smi`, `rbln-smi --topo`, `rbln-smi -L`을 캡처하고 사용 visible ID의 physical card / NUMA node 소속을 기록한다. 관찰 사실만 적고 topology 해석은 hypothesis로 분리한다.

## 관측 대상으로 사전 지정한 사항

- 문서화된 `num_devices=4`가 **동일 physical card**(TASK05가 관찰한 distance-4 그룹)로 잡히는지, 아니면 여러 card에 걸치는지. 어느 쪽이든 관찰 사실만 기록한다.
- vLLM이 `rbln_config.json`에서 유도한 `num_gpu_blocks`, `block_size`, `max_num_batched_tokens` 값.
- `enable_prefix_caching`의 resolved 값 (Stage 2 사전 정보로만 기록하며 이번 run에서 조작하지 않는다).

## 관련 문서

- [INDEX.md](INDEX.md) — 결정 2
- [TASK02](TASK02.md) — Stage 0 사전 검증 (`BLOCKED`)
- [TASK05](TASK05.md) — 후보 model 조사와 `atom-max8` 재-inventory
- [TASK_GUIDE.md](TASK_GUIDE.md) — TASK 작성과 선등록 규칙
