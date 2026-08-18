# Stage 0 — RBLN 단일 추론 검증

## 목적

Clean NPU repository에서 legacy CUDA vLLM을 사용하지 않고 현재 설치된 RBLN-compatible software stack으로 실제 CA25 단일 LLM inference 1회를 수행할 수 있는지 검증한다.

## 시작 환경

- 날짜: 2026-08-18 (Asia/Seoul)
- 현재 관찰 hostname: `atom-max8`
- Repository: `/home/rebel/continuum-npu`
- Branch / HEAD: `main` / `f68a09900422e30ca519491c4d2fa94b8bc74f67`
- Working tree: 기존 `AGENTS.md`, `CLAUDE.md`, `docs/research/` 변경과 untracked `.idea/`가 있어 dirty 상태였다. 기존 변경은 수정 취소하지 않았다.
- Python: `/usr/bin/python3`, 3.10.12
- `vllm` distribution: `0.22.0+cpu`
- `vllm-rbln`: `0.11.1`
- `optimum-rbln`: `0.11.1`
- `rebel-compiler`: `0.11.1.post1`
- `torch-rbln`: `0.3.0`

기존 환경 문서의 hostname은 `rebel-pcie-0123`이지만 이번 probe에서는 `atom-max8`이 관찰됐다. 호스트가 변경됐는지 hostname만 변경됐는지는 `UNKNOWN`이다. 따라서 기존 문서의 hostname을 이번 실행의 provenance로 재사용하지 않는다.

## Source isolation

Repository root에서 직접 수행한 fail-loud probe와 기존 격리 launcher를 통한 probe가 모두 통과했다.

```text
python: /usr/bin/python3
vllm.__file__: /usr/local/lib/python3.10/dist-packages/vllm/__init__.py
vllm.__version__: 0.22.0
vllm dist: 0.22.0+cpu
vllm_rbln.__file__: /usr/local/lib/python3.10/dist-packages/vllm_rbln/__init__.py
vllm-rbln dist: 0.11.1
source isolation invariant: PASS
```

기존 `experiments/npu/launch/run_isolated_python.sh`와 `experiments/npu/probes/runtime_probe.py`를 재사용했다. `decoder_observability.py`는 Stage 0 범위가 아니므로 실행하지 않았다.

## 사용 가능한 모델 조사

다음 범위를 read-only로 확인했다.

- `/home/rebel/.cache/huggingface`, `/home/rebel/.cache/rebellions`, `/home/rebel/.cache/optimum`: 디렉터리 자체가 존재하지 않음
- `/home/rebel` depth 4 및 제한된 cache 범위: `config.json`, `rbln_config.json`, `*.rbln` model artifact 없음
- `/mnt`, `/opt` depth 5: 실행 가능한 model/compiled artifact 없음
- `vllm-rbln`, `optimum-rbln`, `rebel-compiler` distribution: 실행 가능한 weight 또는 compiled artifact가 package에 포함되지 않음

설치된 `optimum-rbln 0.11.1` metadata는 다음 두 경로를 설명한다.

1. Hugging Face model identifier를 전달하면 첫 실행에 weight를 받고 RBLN SDK compilation을 수행한다.
2. 기존 compiled artifact directory를 전달하면 compilation 없이 load한다.

설치 metadata의 명시적 causal-LM example은 `Qwen/Qwen3-4B`이다. 설치 source에는 더 작은 `Qwen/Qwen3.5-0.8B` class example도 있지만, 현 `vllm-rbln 0.11.1`에서 Stage 0용으로 officially validated되었다는 로컬 근거와 필요한 device configuration은 확인되지 않았다.

Llama 계열도 제외된 것이 아니다. 설치 `optimum-rbln` source에는 `meta-llama/Llama-2-7b-hf` example이 있고 `vllm-rbln` metadata는 Llama 3 8B API tutorial을 가리킨다. 다만 local artifact가 없고 7B/8B 모델은 4B 후보보다 resource 요구가 크며 Hugging Face access에 license 동의나 인증이 필요할 수 있어 최소 bring-up의 첫 후보로 두지 않았다. 실제 접근 조건은 확인하지 않았으므로 `UNKNOWN`이다.

Resource 추정은 다음과 같이 제한한다.

- `Qwen/Qwen3-4B`: 4B parameter의 16-bit weight만 단순 계산하면 약 8 GB 수준이지만 실제 download size, quantization, compile working space, artifact size, device 수는 `UNKNOWN`이다.
- `Qwen/Qwen3.5-0.8B`: 0.8B parameter의 16-bit weight만 단순 계산하면 약 1.6 GB 수준이지만 실제 download size, compile artifact size, device 수 및 validated execution path는 `UNKNOWN`이다.
- `meta-llama/Llama-2-7b-hf` 또는 Llama 3 8B 계열: 설치 source/metadata의 지원 단서는 있으나 정확한 Stage 0 model identifier, access 권한, download size, compile artifact와 device 수는 `UNKNOWN`이다.

이는 capacity estimate이며 실제 package/model metadata 측정값이 아니다.

## 선택한 모델

선택한 실행 모델: 없음.

로컬 model 또는 compiled artifact가 없어 어떤 후보를 선택해도 새로운 model download와 runtime/offline compilation이 필요하다. 사용자 승인 전에는 이를 실행하지 않는다는 변경 통제 규칙에 따라 model load 단계로 진입하지 않았다.

승인 검토 후보는 다음과 같다.

- 공식 package example에 가장 가까운 경로: `Qwen/Qwen3-4B`
- 더 작은 resource 후보: `Qwen/Qwen3.5-0.8B` (단, validated vLLM-RBLN compatibility와 device 요구 확인 필요)
- 사용자가 Llama를 선호할 때의 후보: Llama 2 7B 또는 Llama 3 8B 계열 (정확한 identifier, license/access, 현 stack compatibility와 device 요구 확인 필요)

## 실행 방법

수행한 command는 source-isolation probe와 preflight뿐이다.

```bash
experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/probes/runtime_probe.py \
  --output-dir results/npu/stage0/20260818-184144-blocked-model-artifact
```

실제 inference command는 model identifier/path와 resolved device configuration이 없어 구성하지 않았다. Model load, generation, `vllm serve`는 실행하지 않았다.

## Device mapping

`rbln-smi` preflight에서 다음을 다시 관찰했다.

- 8 physical RBLN-CA25 cards
- 32 RBLN-visible device IDs
- physical card당 4 visible IDs
- physical card group 0–7은 각각 IDs `0–3`, `4–7`, `8–11`, `12–15`, `16–19`, `20–23`, `24–27`, `28–31`
- 모든 visible ID: memory `0.0B / 15.7GiB`, utilization `0.0`
- Context Information: active process/context 없음

즉 8 physical cards와 32 physical NPUs는 같은 표현이 아니다. 이번에는 inference를 실행하지 않았으므로 실제 사용한 RBLN-visible ID, physical card, `devices per local rank`, `tensor_parallel_size`는 모두 `UNKNOWN`이다.

## Runtime/compile 방식

- 실제 execution path: 미실행
- Runtime compile / precompiled: 미선택
- 확인된 package path: `optimum-rbln`은 model identifier의 first-run compilation 또는 compiled directory load를 지원
- 실제 compile start/end: 해당 없음
- 실제 model load start/end: 해당 없음

## 실행 결과

### 관찰

- Source isolation process exit code: `0`
- Model inference process: 실행하지 않음
- Input/output: 없음
- Input/output tokens: `UNKNOWN`
- End-to-end latency: `UNKNOWN`
- TTFT: `UNKNOWN`

### 해석

Software import 경계와 idle CA25 inventory는 검증됐지만 model load, generation, valid output 조건은 충족되지 않았다. 따라서 Stage 0 inference 성공으로 해석할 수 없다.

## NPU 사용 증거

Preflight `rbln-smi`는 CA25 device inventory와 idle 상태를 증명한다. 그러나 실제 inference가 없으므로 runtime device assignment, context/memory 변화, utilization 또는 RBLN execution log가 없다.

따라서 이번 작업에는 **실제 NPU inference 사용 증거가 없다**. Idle inventory를 execution 증거로 사용하지 않는다.

## 실패 또는 우회한 시도

- 실제 inference attempt는 수행하지 않았다.
- Local model/compiled artifact 탐색 결과가 비어 있어 model load command를 억지로 실행하지 않았다.
- `Qwen/Qwen3-4B` 또는 `Qwen/Qwen3.5-0.8B`를 자동 download/compile하지 않았다.
- Package upgrade, dependency 설치, site-packages 수정, RSD 변경, device reset을 수행하지 않았다.

이는 runtime failure가 아니라 승인 필요한 external model/compile dependency에 의한 사전 gate 차단이다.

## 아직 확인되지 않은 사항

- 승인 가능한 model identifier 또는 precompiled artifact path
- 정확한 model revision과 download size
- compile artifact size와 compile duration
- 최소 RBLN-visible device 수와 physical card mapping
- `devices per local rank`, `tensor_parallel_size`, resolved model/runtime configuration
- 실제 model output, token 수, latency, TTFT
- 실제 NPU context/memory/utilization 변화
- 기존 환경 문서와 현재 probe 사이 hostname 차이의 원인

## Stage 0 판정

`BLOCKED`

Source isolation은 `PASS`지만 필수 조건인 model load, 실제 CA25 execution, batch/request 1 inference, valid output, runtime device configuration 및 NPU 사용 증거가 없다.

Blocker는 로컬 precompiled artifact 또는 model weight가 없고, 신규 download와 RBLN compilation은 사전 승인 대상이라는 점이다.

## Stage 1 진입 가능 여부

`NO`

Stage 0 PASS 기준을 충족하지 못했다. `vllm serve`, OpenAI API server, APC, batching 또는 scheduler 연구로 진행하지 않는다.

## 다음 단계

사용자가 다음 중 하나를 선택한 뒤 Stage 0를 재개한다.

1. 현 stack과 호환되는 검증된 precompiled RBLN causal-LM artifact path를 제공한다.
2. 특정 model의 download와 compilation을 승인한다. 우선 `Qwen/Qwen3-4B` 공식 example 경로의 실제 download/compile/device 요구를 확인하고 승인 범위를 확정한다.
3. 작은 모델을 우선하려면 `Qwen/Qwen3.5-0.8B`의 공식 지원 여부와 device 요구를 먼저 확인한 뒤 별도로 승인한다.

Stage 1은 자동 시작하지 않는다.
