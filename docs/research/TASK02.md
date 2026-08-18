# TASK02 — Stage 0 CA25 단일 추론 Bring-up 사전 검증

## 상태

BLOCKED

## 날짜

2026-08-18

## 목적

현재 설치된 RBLN-compatible stack으로 실제 CA25에서 batch/request 1의 최소 단일 LLM inference를 수행하고 실행 경로, model, device configuration, NPU 사용 증거를 재현 가능하게 기록한다.

## 배경

Stage 0는 이후 serving, APC, decoder observation 연구의 선행 gate다. 기존 환경 감사에서는 실행 가능한 precompiled model artifact가 확인되지 않았다.

관련 TASK:

- [TASK01](TASK01.md) — INDEX-first 연구 기록 workflow 구축

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- Git commit: `f68a09900422e30ca519491c4d2fa94b8bc74f67`
- Git dirty: 기존 문서 변경과 untracked `.idea/`가 존재
- 현재 관찰 hostname: `atom-max8`
- 기존 환경 문서 hostname: `rebel-pcie-0123`; 차이 원인은 `UNKNOWN`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch-rbln 0.3.0`
- Hardware inventory: 8 physical RBLN-CA25 cards, 32 RBLN-visible IDs, physical card당 4 IDs

## 수행 내용

- 필수 연구·환경·legacy 문서와 기존 TASK를 확인했다.
- Repository root 및 기존 isolation launcher에서 import/version invariant를 fail-loud 검증했다.
- 기존 `runtime_probe.py`를 재사용하고 decoder probe는 실행하지 않았다.
- 제한된 home/cache, `/mnt`, `/opt`, 설치 distribution에서 model/compiled artifact와 example을 조사했다.
- `rbln-smi`로 실행 전 idle inventory를 확인했다.
- Model artifact가 없고 download/compile이 승인 대상이므로 inference 전에 중단했다.

## 변경된 파일

- `docs/research/STAGE0_RBLN_INFERENCE.md`
- `docs/research/TASK02.md`
- `docs/research/INDEX.md`

Raw artifact는 `.gitignore` 대상인 `results/npu/stage0/20260818-184144-blocked-model-artifact/`에 생성됐다.

## 실험 또는 검증 방법

```bash
python3 - <<'PY'
# vllm/vllm-rbln import path와 distribution version assert
PY

experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/probes/runtime_probe.py \
  --output-dir results/npu/stage0/20260818-184144-blocked-model-artifact

rbln-smi
```

Local artifact 탐색은 `/home/rebel`의 제한 depth와 알려진 cache, `/mnt`, `/opt` depth 5로 제한했다. 전체 filesystem 전수검색은 수행하지 않았다.

## 결과

### 관찰

- Source isolation: `PASS`
- Python: `/usr/bin/python3`, 3.10.12
- `vllm.__file__`: `/usr/local/lib/python3.10/dist-packages/vllm/__init__.py`
- `vllm.__version__`: `0.22.0`
- `vllm` distribution: `0.22.0+cpu`
- `vllm-rbln`: `0.11.1`
- Local model/compiled artifact: 발견되지 않음
- Preflight: 32 visible IDs 모두 memory `0.0B / 15.7GiB`, utilization `0.0`, active context 없음
- Actual inference: 미실행

### 판정

Stage 0는 `BLOCKED`다. Import invariant는 통과했지만 model load, CA25 execution, valid output, device assignment, raw inference log 조건을 충족하지 못했다.

## 핵심 발견

- 기존 source-isolation probe를 그대로 재사용할 수 있다.
- 설치 package에는 model class와 compile/load path가 있지만 실행 가능한 model weight 또는 compiled artifact는 없다.
- 설치 metadata는 `Qwen/Qwen3-4B`를 explicit compile example로 제공한다.
- 더 작은 `Qwen/Qwen3.5-0.8B` source example이 있으나 현 vLLM-RBLN Stage 0에서 validated되었다는 로컬 근거와 device 요구는 확인되지 않았다.
- Llama 계열도 설치 source/metadata에 지원 단서가 있지만 local artifact가 없고 더 큰 resource 및 access 조건이 예상되어 최소 bring-up의 첫 후보로 선택하지 않았다. 사용 금지 또는 비호환으로 판정한 것은 아니다.
- 현재 probe hostname은 기존 환경 문서와 다르므로 run마다 hostname provenance를 다시 기록해야 한다.

## 해석

Idle CA25 inventory와 import 성공은 실제 NPU inference의 증거가 아니다. Model artifact가 없는 상태에서 PASS를 만들려면 신규 download와 compilation이라는 승인 대상 변경이 필요하다. 이를 우회하지 않고 gate를 `BLOCKED`로 유지한다.

## 확인되지 않은 사항

- 선택 model/revision, 실제 disk size, compile duration/artifact size
- 최소 device 수와 physical card mapping
- resolved runtime configuration
- input/output tokens, latency, TTFT
- 실제 NPU context/memory/utilization 변화
- hostname 차이의 원인

## 실패 / 무효 시도

실제 inference attempt는 없었다. Model 없이 entrypoint를 호출하거나 network download를 유발하는 명령은 실행하지 않았다. Package/RSD/device/system 변경도 하지 않았다.

## 연구 원칙에 미치는 영향

- Import success, hardware inventory, actual execution evidence를 서로 다른 gate로 유지한다.
- 관찰하지 못한 device/config/latency를 추측하지 않고 `UNKNOWN`으로 기록한다.
- 8 physical cards를 32 physical NPUs로 표현하지 않는다.
- 승인 없는 download/compile로 blocker를 우회하지 않는다.

## 다음 작업

검증된 precompiled artifact path를 제공받거나, model identifier와 download/compile 범위가 승인된 뒤 Stage 0 inference를 재개한다. Stage 1은 시작하지 않는다.

## 재현 정보

- 상세 보고: [STAGE0_RBLN_INFERENCE.md](STAGE0_RBLN_INFERENCE.md)
- Raw probe artifact: `results/npu/stage0/20260818-184144-blocked-model-artifact/`
- Base commit: `f68a09900422e30ca519491c4d2fa94b8bc74f67`
- Isolation launcher: `experiments/npu/launch/run_isolated_python.sh`
- Runtime probe: `experiments/npu/probes/runtime_probe.py`
