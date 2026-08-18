# Agent 작업 규칙

이 저장소는 Rebellions NPU 연구의 clean-room source of truth다.

## 언어

진행 설명, 분석, Markdown, TODO, 최종 보고는 한국어로 작성한다. 코드, identifier, package/API 이름, configuration key, metric field, 실제 log/error는 영어 원문을 유지한다.

## Runtime 경계

- repository-local `vllm/`을 만들지 않는다.
- site-packages를 직접 수정하지 않는다.
- old CUDA fork는 `/home/rebel/vllm-continuum`에서 reference로만 읽는다.
- RBLN-specific 코드는 `experiments/npu/` 또는 명시적 backend 경계에 둔다.
- `src/continuum/`은 accelerator-neutral하게 유지한다.

## 연구 validity

- CUDA semantics와 GPU threshold를 RBLN에 적용하지 않는다.
- eviction/release와 recomputation을 동일시하지 않는다.
- cache source를 latency로 추론하지 않는다.
- `UNKNOWN`과 `PARTIAL`을 허용한다.
- requested/observed condition과 condition reached를 별도 기록한다.
- metric의 population, unit, source, device scope를 기록한다.
- 모든 run에 Git/package/model/device/resolved config provenance를 남긴다.

## 변경 통제

dependency 설치, model download/compile, RSD 변경, device reset, patch 적용은 먼저 보고한다. Patch가 필요하면 exact package version과 upstream hash를 검증하고 observation-only 변경을 우선한다. 기존 legacy repository는 수정하거나 삭제하지 않는다.
