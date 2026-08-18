# Continuum-NPU Research Task Index

이 문서는 모든 agent가 작업 전에 읽는 연구 진행 상황의 단일 진입점이다. 상세 작성 규칙은 [TASK_GUIDE.md](TASK_GUIDE.md)를 따른다.

## 현재 상태

현재 연구 단계: clean-room migration과 NPU 환경·이식 준비도 감사를 완료했고 Stage 0 bring-up 사전 검증을 수행했다. Source isolation과 CA25 idle inventory는 확인했으나 실제 inference는 실행하지 못했다.

가장 최근 TASK: [TASK03](TASK03.md) — 작업 종료 시 main commit Workflow 도입 (`DONE`)

최근 완료 TASK: [TASK03](TASK03.md) — 작업 종료 시 main commit Workflow 도입 (`DONE`)

현재 주요 blocker: 로컬 model weight 또는 검증된 precompiled RBLN artifact가 없다. 신규 model download와 RBLN compilation은 사전 승인 대상이므로 Stage 0가 `BLOCKED`다. Stage 1 serving과 Stage 2 APC OFF/ON도 Stage 0 선행 요건 미충족으로 `BLOCKED`다.

다음 권장 작업: 사용자가 검증된 precompiled RBLN model path를 제공하거나 model download/compile을 명시적으로 승인하면 Stage 0 source-isolated single inference를 수행한다.

## Task Index

| Task | 상태 | 제목 | 간략 설명 |
|---|---|---|---|
| [TASK01](TASK01.md) | DONE | 연구 작업 기록 및 Agent Workflow 구축 | INDEX-first workflow와 TASK 기반 연구 이력을 도입했다. 모든 agent가 관련 과거 결정을 확인하고 TASK와 INDEX를 함께 갱신하도록 규칙을 통합했다. |
| [TASK02](TASK02.md) | BLOCKED | Stage 0 CA25 단일 추론 Bring-up 사전 검증 | Source isolation과 8 physical CA25 card/32 visible ID inventory를 재검증했다. 실행 가능한 local model/artifact가 없어 승인 필요한 download/compile 전에 중단했다. |
| [TASK03](TASK03.md) | DONE | 작업 종료 시 main commit Workflow 도입 | 각 작업의 검증된 agent-owned 변경을 local `main`에 commit하고 hash를 보고하도록 종료 규칙을 강화했다. Remote `push`는 별도 지시 대상으로 유지했다. |

## 완료된 주요 작업

- Clean-room NPU repository migration 및 source isolation 검증이 초기 repository commit에서 완료됐다. 이는 TASK 체계 도입 전 작업이므로 근거 없이 별도 TASK로 소급 재구성하지 않았다.
- NPU hardware/software 환경, topology, source-resolution 위험, 포팅 준비도를 read-only로 감사했다. 상세 근거는 [NPU 환경](../environment/NPU_ENVIRONMENT.md), [이식 사전 분석](../environment/NPU_PORTING_ANALYSIS.md), [연구 준비도](../environment/NPU_RESEARCH_READINESS.md)에 있다.
- TASK01에서 agent 연구 기록 체계를 구축했다.
- TASK02에서 source isolation을 재검증하고 Stage 0 model gate의 blocker를 최신 환경에서 확인했다.
- TASK03에서 각 작업 종료 시 local `main` commit을 필수 workflow로 도입했다.

## 진행 중 또는 BLOCKED인 작업

- Stage 0 single inference: local weight/검증된 precompiled RBLN model artifact 부재와 download/compile 미승인으로 `BLOCKED`.
- Stage 1 serving: Stage 0 선행 요건 미충족으로 `BLOCKED`.
- Stage 2 APC OFF/ON characterization: Stage 1 미실행으로 `BLOCKED`.
- Decoder batch observation: source-level observation point는 확인했으나 per-step runtime metric은 `UNKNOWN`이며 runtime 검증 전이다.

## 핵심 연구 흐름

Clean-room migration 및 환경 감사 → TASK01 연구 기록 체계 → TASK02 Stage 0 사전 검증(`BLOCKED`) → TASK03 작업 종료 commit workflow → Stage 0 single inference → Stage 1 serving/config 검증 → Stage 2 APC OFF/ON characterization → decoder batch observation-only characterization → raw-signal feasibility

Stage 0–2 observation baseline 전에는 scheduler policy, KEEP/OFFLOAD/RECOMPUTE 또는 host/peer KV parking을 구현하지 않는다.

Legacy GPU 연구 문서는 `docs/legacy/TASK25.md`, `TASK27.md`, `TASK29.md`, `TASK31.md`에 있으며 새 NPU TASK와 다른 namespace다. 새 번호는 오직 이 디렉터리의 `TASKNN.md`만 기준으로 계산한다.

## 현재 유지해야 하는 핵심 원칙

- decision accuracy만 최적화하지 않고 mis-selection cost와 regret을 함께 본다.
- requested condition, observed condition, condition reached를 구분한다.
- eviction/release를 recomputation으로 간주하지 않는다.
- cache source를 latency만으로 판정하지 않는다.
- 증거가 부족하면 `PARTIAL`과 `UNKNOWN`을 허용한다.
- GPU threshold와 CUDA semantics를 NPU에 그대로 적용하지 않는다.
- instantaneous pressure만으로 cache survival을 설명하지 않는다.
- observation과 interpretation/hypothesis를 분리하고 모든 run의 provenance를 남긴다.
- 각 작업의 검증된 agent-owned 변경을 local `main`에 commit하고 commit hash를 보고한다.

## 다음 작업 후보

1. 검증된 precompiled RBLN model artifact 확보 후 Stage 0 source-isolated single inference.
2. Stage 0 통과 후 Stage 1 serving과 resolved config 기록.
3. Stage 1 통과 후 APC OFF/ON을 독립 구성한 Stage 2 repeated-prefix baseline.
4. baseline 통과 후 decoder bucket의 observation-only characterization.

이 목록은 권고 순서다. 사용자의 지시 없이 다음 작업을 자동 시작하지 않는다.
