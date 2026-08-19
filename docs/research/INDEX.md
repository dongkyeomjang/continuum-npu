# Continuum-NPU Research Task Index

이 문서는 모든 agent가 작업 전에 읽는 연구 진행 상황의 단일 진입점이다. 상세 작성 규칙은 [TASK_GUIDE.md](TASK_GUIDE.md)를 따른다.

## 현재 상태

현재 연구 단계: clean-room migration과 NPU 환경·이식 준비도 감사를 완료했고 Stage 0 bring-up 사전 검증을 수행했다. Source isolation과 CA25 idle inventory는 확인했으나 실제 inference는 실행하지 못했다.

가장 최근 TASK: [TASK04](TASK04.md) — 연구 workflow 문서 개정: 결정 대기 절, 선등록 hard rule, hostname `UNKNOWN` 승격 (`DONE`)

"가장 최근 TASK"는 번호가 가장 큰 TASK다. 그 TASK의 상태가 `BLOCKED`, `PARTIAL`, `FAILED`, `INVALID` 중 하나여서 최근 진척을 대표하지 못할 때만 아래에 "최근 완료 TASK"(가장 번호가 큰 `DONE` TASK)를 별도로 한 줄 추가한다. 두 줄이 같은 TASK를 가리키면 한 줄만 남긴다.

현재 주요 blocker: Stage 0는 실행 가능한 model artifact 부재로 `BLOCKED`이고, Stage 1·Stage 2는 Stage 0 선행 요건 미충족으로 `BLOCKED`다. 해소는 사용자 판정에 달려 있으므로 상세 선택지와 근거는 아래 [사용자 결정 대기](#사용자-결정-대기) 절을 단일 출처로 삼는다. 이 문단에 선택지를 중복 서술하지 않는다.

환경 provenance `UNKNOWN`: 환경 문서 [NPU_ENVIRONMENT.md](../environment/NPU_ENVIRONMENT.md)의 hostname은 `rebel-pcie-0123`이지만 현재 관찰 hostname은 `atom-max8`이다. 두 이름이 같은 host인지, 재설치·rename·다른 장비인지는 `UNKNOWN`이다. 따라서 해당 문서의 topology distance 구조, NUMA affinity, RSD group, device inventory가 현재 host에서도 유효한지 역시 `UNKNOWN`이며, 이를 근거로 device 수·NUMA 배치를 확정하지 않는다. 해소 경로는 `atom-max8` read-only 재-inventory와 항목별 대조다.

다음 권장 작업: 아래 [사용자 결정 대기](#사용자-결정-대기) 절의 미해결 결정을 사용자가 판정하면 그에 따라 Stage 0를 재개한다.

## Task Index

| Task | 상태 | 제목 | 간략 설명 |
|---|---|---|---|
| [TASK01](TASK01.md) | DONE | 연구 작업 기록 및 Agent Workflow 구축 | INDEX-first workflow와 TASK 기반 연구 이력을 도입했다. 모든 agent가 관련 과거 결정을 확인하고 TASK와 INDEX를 함께 갱신하도록 규칙을 통합했다. |
| [TASK02](TASK02.md) | BLOCKED | Stage 0 CA25 단일 추론 Bring-up 사전 검증 | Source isolation과 8 physical CA25 card/32 visible ID inventory를 재검증했다. 실행 가능한 local model/artifact가 없어 승인 필요한 download/compile 전에 중단했다. |
| [TASK03](TASK03.md) | DONE | 작업 종료 시 main commit Workflow 도입 | 각 작업의 검증된 agent-owned 변경을 local `main`에 commit하고 hash를 보고하도록 종료 규칙을 강화했다. Remote `push`는 별도 지시 대상으로 유지했다. |
| [TASK04](TASK04.md) | DONE | 연구 workflow 문서 개정 | INDEX에 "사용자 결정 대기" 절을 신설하고, 선등록·동치 판정 규칙을 집행 문서의 hard rule로 승격했으며, hostname 불일치를 INDEX 수준 `UNKNOWN`으로 올렸다. |

## 사용자 결정 대기

이 절은 agent가 임의로 진행할 수 없고 사용자 판정이 필요한 결정의 단일 출처다. 각 항목은 결정 ID, 질문, 선택지, 선택지별 근거·비용·미지수, 권고안, 관련 TASK를 갖는다. 권고안은 제안일 뿐이며 판정은 사용자가 한다. 결정이 내려지면 항목을 "해소됨"으로 표시하고 근거 TASK를 링크한다.

### 결정 2 — Stage 0 대상 model의 download/compile 승인

- 상태: `대기` (근거 미수집)
- 질문: Stage 0 single inference의 대상 model로 무엇을 선택하고, 해당 model의 weight download와 RBLN compilation을 승인할 것인가?
- 선택지: 미정
- 선택지별 근거 / 비용 / 미지수: `UNKNOWN`
- 권고안: 미정
- 관련 TASK: [TASK02](TASK02.md), [TASK04](TASK04.md)

작업 2(결정 1 — 후보 model metadata 및 환경 재-inventory 조사) 완료 후 채운다. 조사 전에는 후보, download 크기, KV bytes/token, device 요구를 추정으로 채우지 않는다.

## 완료된 주요 작업

- Clean-room NPU repository migration 및 source isolation 검증이 초기 repository commit에서 완료됐다. 이는 TASK 체계 도입 전 작업이므로 근거 없이 별도 TASK로 소급 재구성하지 않았다.
- NPU hardware/software 환경, topology, source-resolution 위험, 포팅 준비도를 read-only로 감사했다. 상세 근거는 [NPU 환경](../environment/NPU_ENVIRONMENT.md), [이식 사전 분석](../environment/NPU_PORTING_ANALYSIS.md), [연구 준비도](../environment/NPU_RESEARCH_READINESS.md)에 있다.
- TASK01에서 agent 연구 기록 체계를 구축했다.
- TASK02에서 source isolation을 재검증하고 Stage 0 model gate의 blocker를 최신 환경에서 확인했다.
- TASK03에서 각 작업 종료 시 local `main` commit을 필수 workflow로 도입했다.
- TASK04에서 사용자 결정 대기 절, 선등록·동치 판정 hard rule, hostname `UNKNOWN` 승격으로 연구 workflow 문서를 개정했다.

## 진행 중 또는 BLOCKED인 작업

- Stage 0 single inference: local weight/검증된 precompiled RBLN model artifact 부재와 download/compile 미승인으로 `BLOCKED`.
- Stage 1 serving: Stage 0 선행 요건 미충족으로 `BLOCKED`.
- Stage 2 APC OFF/ON characterization: Stage 1 미실행으로 `BLOCKED`.
- Decoder batch observation: source-level observation point는 확인했으나 per-step runtime metric은 `UNKNOWN`이며 runtime 검증 전이다.

## 핵심 연구 흐름

Clean-room migration 및 환경 감사 → TASK01 연구 기록 체계 → TASK02 Stage 0 사전 검증(`BLOCKED`) → TASK03 작업 종료 commit workflow → TASK04 workflow 문서 개정 → Stage 0 single inference → Stage 1 serving/config 검증 → Stage 2 APC OFF/ON characterization → decoder batch observation-only characterization → raw-signal feasibility

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
- 측정과 판정이 포함된 TASK는 판정 기준·예측·실험 격자를 측정 전에 commit하고(선등록) 사후에 기준을 완화하지 않는다.
- 두 조건의 동치 판정은 고정 밴드가 아니라 중앙 ratio bootstrap CI가 1을 포함하는지와 사전 등록한 CI 폭 상한으로 한다.

## 다음 작업 후보

1. 후보 model metadata 및 `atom-max8` 환경 read-only 재-inventory 조사로 결정 2의 근거 표를 채운다.
2. 검증된 precompiled RBLN model artifact 확보 또는 결정 2 승인 후 Stage 0 source-isolated single inference.
3. Stage 0 통과 후 Stage 1 serving과 resolved config 기록.
4. Stage 1 통과 후 APC OFF/ON을 독립 구성한 Stage 2 repeated-prefix baseline.
5. baseline 통과 후 decoder bucket의 observation-only characterization.

이 목록은 권고 순서다. 사용자의 지시 없이 다음 작업을 자동 시작하지 않는다.
