# Continuum NPU

## 프로젝트 목적

이 저장소는 Rebellions CA25 NPU 환경에서 agent workload의 KV lifecycle, cache attribution, memory turnover, dynamic decoder batching을 연구하기 위한 새로운 source of truth다.

현재 목표는 기존 GPU scheduler를 포팅하는 것이 아니다. 먼저 지원되는 `vllm 0.22.0+cpu` + `vllm-rbln 0.11.1` stack 위에서 관찰 가능한 signal과 실험 validity를 확립한다.

## 현재 NPU 환경

- 8 physical CA25 card
- 32 RBLN-visible device ID
- `vllm-rbln==0.11.1`
- `vllm==0.22.0+cpu`
- `optimum-rbln==0.11.1`
- `rebel-compiler==0.11.1.post1`
- `torch-rbln==0.3.0`

정확한 topology와 package provenance는 `docs/environment/` 문서를 기준으로 한다.

## 기존 GPU Continuum과의 관계

`/home/rebel/vllm-continuum`은 이전 CUDA 연구의 archive/reference다. 이 저장소는 `/home/rebel/continuum-npu`이며 old vLLM fork를 포함하지 않는다.

과거 연구의 지식과 방법론은 `docs/legacy/`에 보존하지만 GPU threshold, CUDA timing semantics, old vLLM internal API는 현재 NPU 정책의 기본값으로 재사용하지 않는다.

## 현재 연구 단계

Clean-room migration과 source isolation 검증 단계다. Stage 0 NPU inference, Stage 1 serving, Stage 2 APC characterization, KV placement policy는 아직 시작하지 않는다.

## Repository 구조

- `docs/environment/`: 현재 NPU 환경과 포팅 사전 분석
- `docs/legacy/`: GPU 연구의 핵심 기록과 교훈
- `src/continuum/`: accelerator-neutral workload, metric, analysis, policy 계층
- `experiments/npu/`: RBLN-specific probe, launcher, config, instrumentation
- `patches/`: version/hash가 고정된 observation-only patch 정책
- `results/`: 새 NPU run artifact 전용

## 실행 원칙

1. repository 안에 자체 `vllm/` fork를 만들지 않는다.
2. site-packages를 직접 수정하지 않는다.
3. CUDA semantics와 GPU threshold를 RBLN에 적용하지 않는다.
4. eviction/release를 recomputation으로 해석하지 않는다.
5. latency만으로 cache source를 판정하지 않는다.
6. `UNKNOWN`과 `PARTIAL`을 유효한 관측 결과로 허용한다.
7. requested condition과 observed condition을 별도로 기록한다.
8. package, version, model, device, resolved config provenance 없이 실험 결과를 해석하지 않는다.

## 주의사항

새 dependency 설치, RSD 변경, model download/compile, runtime patch는 먼저 근거와 영향 범위를 보고한 뒤 승인받는다. 기존 `/home/rebel/vllm-continuum`은 삭제하거나 수정하지 않는다.
