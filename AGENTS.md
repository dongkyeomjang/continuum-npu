# Agent 작업 규칙

이 저장소는 Rebellions NPU 연구의 clean-room source of truth다.

## 언어

진행 설명, 분석, Markdown, TODO, 최종 보고는 한국어로 작성한다. 코드, identifier, package/API 이름, configuration key, metric field, 실제 log/error는 영어 원문을 유지한다. 필요한 기술 용어는 한국어와 영어 원문을 함께 쓸 수 있다.

## HARD REQUIREMENT: Mandatory Research Workflow

Research history source of truth는 [`docs/research/INDEX.md`](docs/research/INDEX.md)다. **INDEX.md를 읽지 않은 상태에서 의미 있는 구현 또는 실험을 시작하지 않는다.** 단순 코드 수정, 버그 수정, 실험, 분석, 문서화에도 예외가 없다.

모든 작업은 다음 순서를 따른다.

1. `docs/research/INDEX.md`를 읽고 현재 연구 단계, 최근 작업, 기존 실패·blocker를 확인한다.
2. 현재 요청과 관련된 `TASKNN.md`를 식별한다.
3. 관련 TASK와 결정을 이해하는 데 필요한 선행 TASK를 읽는다.
4. `git status`로 기존 변경과 동시 작업 가능성을 확인한다.
5. 작업을 수행한다.
6. 요청 범위에 맞게 검증한다.
7. 의미 있는 연구/구현 단위가 완료되었는지 판단한다.
8. 기록 대상이면 TASK 생성 직전에 `INDEX.md`, `TASK*.md`, `git status`를 다시 확인하고 다음 번호를 결정한다.
9. `TASKNN.md`를 작성한다.
10. 같은 작업 안에서 `INDEX.md`를 갱신한다. TASK만 만들고 INDEX를 갱신하지 않은 상태는 완료가 아니다.
11. `git diff --check`와 문서 링크 등 필요한 검증을 수행한다.
12. 이번 작업에서 agent가 생성·수정한 파일만 명시적으로 stage하고 `main` branch에 commit한다.
13. commit hash와 남은 Git 상태를 확인한 뒤 사용자에게 한국어로 결과를 보고한다.
14. 종료 보고의 마지막에 반드시 "GitHub의 `origin/main`에 push할까요?"라고 묻고 답을 기다린다.

같은 component, experiment, metric, hypothesis, blocker, baseline, artifact 또는 RBLN/vLLM 내부 API를 다루면 관련 TASK로 본다. 판단이 애매하면 INDEX에서 가장 가까운 TASK를 읽는다. 과거에 실패한 접근, 잘못된 가정, unreachable condition, semantic confounder, invalid metric으로 판정된 내용을 맥락 없이 반복하지 않는다.

TASK 생성 기준, 번호, 상태, 필수 구조, 동시 작업 규칙의 상세 source of truth는 [`docs/research/TASK_GUIDE.md`](docs/research/TASK_GUIDE.md)다. 새 TASK를 기록할 때 반드시 읽고 따른다.

현재 작업이 끝났더라도 사용자의 지시 없이 INDEX의 다음 연구 TASK를 자동으로 시작하지 않는다.

## HARD REQUIREMENT: 작업 종료 Commit

각 작업은 검증을 통과한 변경을 `main` branch에 commit해야 완료된다. 작업 시작 시 현재 branch를 확인하고 원칙적으로 `main`에서 작업한다. 다른 branch에 있거나 안전하게 `main`으로 전환할 수 없으면 임의 merge/rebase하지 말고 사용자에게 보고한다.

- `git add -A`처럼 범위가 넓은 staging을 피하고 이번 작업에서 agent가 소유한 파일만 명시적으로 stage한다.
- 작업 전부터 존재한 변경, 다른 agent/사용자의 변경, `.idea/`, secret, raw result, ignored artifact를 자동 포함하지 않는다.
- Commit 전에 staged diff와 `git diff --check`를 확인한다.
- 의미 있는 TASK를 만들었다면 TASK와 INDEX를 같은 commit에 포함한다.
- Commit message는 작업 목적을 설명해야 한다.
- Commit 후 `git status --short`와 `git rev-parse HEAD`를 확인한다.
- Commit 실패 시 성공 또는 완료로 보고하지 않고 원인을 기록한다.
- 이 규칙은 local `main` commit을 요구한다. Remote `push`는 자동 수행하지 않는다.
- 작업 종료 보고마다 commit할 변경이 있었는지와 관계없이 반드시 GitHub `push` 여부를 사용자에게 묻는다.
- 사용자가 현재 종료 질문에 명시적으로 승인한 경우에만 해당 local `main` commit을 `origin/main`에 push한다. 과거 승인이나 일반적 선호를 현재 push 승인으로 재사용하지 않는다.
- Push 전 remote와 대상 commit을 확인하고, push 후 local/remote ref를 확인해 결과를 보고한다.
- Push가 실패하면 원문 error를 보존하고 한국어로 원인을 설명한다. Force push는 별도 명시적 지시 없이는 수행하지 않는다.

## Runtime 경계

- repository-local `vllm/`을 만들지 않는다.
- site-packages를 직접 수정하지 않는다.
- old CUDA fork는 `/home/rebel/vllm-continuum`에서 reference로만 읽는다.
- RBLN-specific 코드는 `experiments/npu/` 또는 명시적 backend 경계에 둔다.
- `src/continuum/`은 accelerator-neutral하게 유지한다.

## 연구 validity

- decision accuracy만 최적화하지 않고 mis-selection cost와 regret을 함께 본다.
- CUDA semantics와 GPU threshold를 RBLN에 적용하지 않는다.
- eviction/release와 recomputation을 동일시하지 않는다.
- cache source를 latency로 추론하지 않는다.
- `UNKNOWN`, `PARTIAL`, `BLOCKED`, `INVALID`를 근거에 맞게 사용한다.
- requested condition, observed condition, condition reached를 별도 기록한다.
- instantaneous pressure만으로 cache survival을 설명하지 않는다.
- metric의 population, unit, source, device scope를 기록한다.
- 모든 run에 Git/package/model/device/resolved config provenance를 남긴다.
- 측정과 판정이 포함된 TASK는 판정 기준, 예측, 실험 격자를 측정 시작 전에 commit한다(선등록, preregistration). TASK 재현 정보에 선등록 commit hash와 측정 시작 시각의 선후 관계를 기록한다. 측정 후에 판정 기준을 완화하지 않으며, 완화가 불가피하면 원 기준의 실패를 함께 보고한다.
- 두 조건의 동치(equivalence) 판정은 고정 밴드가 아니라 중앙 ratio의 bootstrap CI가 1을 포함하고 CI 폭이 사전 등록한 상한 이내인지로 한다.

관찰 사실, 파생 해석, 연구 hypothesis를 분리한다. 관측 불가 값을 0으로 채우거나 근거 없는 결론으로 보완하지 않는다. raw result는 `results/npu/` 등 artifact 경로에 보존하고 TASK에는 핵심 measurement, 해석, 경로, 재현 방법을 기록한다.

## 변경 통제

dependency 설치, model download/compile, RSD 변경, device reset, patch 적용은 먼저 보고한다. Patch가 필요하면 exact package version과 upstream hash를 검증하고 observation-only 변경을 우선한다. 기존 legacy repository는 수정하거나 삭제하지 않는다.

`docs/legacy/TASKxx.md`는 legacy GPU namespace이며 `docs/research/TASKxx.md`의 NPU 번호 계산에 포함하지 않는다.
