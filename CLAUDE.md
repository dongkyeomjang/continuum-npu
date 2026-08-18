# Claude 작업 규칙

## HARD REQUIREMENT: 작업 시작 절차

Research history source of truth는 [`docs/research/INDEX.md`](docs/research/INDEX.md)다. Claude Code는 **어떤 작업이든 시작하기 전에 이 파일을 반드시 읽는다. INDEX.md를 읽지 않은 상태에서 의미 있는 구현 또는 실험을 시작하지 않는다.** 단순 코드 수정, 버그 수정, 실험, 분석, 문서화도 동일하다.

1. `docs/research/INDEX.md`에서 현재 단계, 최근 TASK, 과거 시도, blocker를 확인한다.
2. 같은 component, experiment, metric, hypothesis, blocker, baseline, artifact 또는 RBLN/vLLM API와 관련된 TASK를 식별한다.
3. 관련 `TASKNN.md`와 필요한 선행 TASK를 읽는다. 과거 TASK 전체를 무조건 읽을 필요는 없다.
4. `git status`로 기존 변경을 확인한 뒤 작업한다.
5. 검증 후 의미 있는 작업 단위인지 판단한다.
6. 기록 대상이면 TASK 생성 직전에 `INDEX.md`, `TASK*.md`, `git status`를 다시 확인한다.
7. 다음 번호의 `TASKNN.md`를 작성하고 같은 작업 안에서 `INDEX.md`를 갱신한다.
8. `git diff --check`와 문서 링크 등 필요한 검증을 수행한다.
9. 이번 작업에서 Claude가 생성·수정한 파일만 명시적으로 stage하고 `main` branch에 commit한다.
10. Commit hash와 남은 Git 상태를 확인한 뒤 한국어로 보고한다.

TASK 생성 기준, 번호, 상태, 문서 구조는 [`docs/research/TASK_GUIDE.md`](docs/research/TASK_GUIDE.md)가 source of truth다. 새 TASK를 기록할 때 반드시 읽는다. TASK 없이 INDEX만, 또는 TASK만 만들고 INDEX를 갱신하지 않은 상태로 끝내지 않는다. 완료 후에도 사용자의 지시 없이 다음 연구 TASK를 자동 시작하지 않는다.

## HARD REQUIREMENT: 작업 종료 Commit

각 작업은 검증된 변경을 local `main` branch에 commit해야 완료된다. 작업 시작 시 branch를 확인한다. 다른 branch에서 안전하게 `main`으로 전환할 수 없으면 임의 merge/rebase하지 않고 사용자에게 보고한다.

- 이번 작업에서 Claude가 소유한 파일만 경로를 명시해 stage한다. `git add -A`를 사용하지 않는다.
- 기존 사용자/다른 agent 변경, `.idea/`, secret, raw result, ignored artifact를 자동 stage하지 않는다.
- 의미 있는 TASK와 INDEX 갱신은 구현 변경과 같은 commit에 포함한다.
- Commit 전에 staged diff와 `git diff --check`를 확인한다.
- Commit 후 hash와 `git status --short`를 확인한다.
- Commit 실패 시 완료로 보고하지 않는다.
- Remote `push`는 별도 사용자 지시 없이 수행하지 않는다.

## 실행 및 연구 원칙

1. 사용자 대상 설명, 연구 문서, 결과 해석, 설계 판단, 실패 원인, 향후 계획은 한국어로 작성한다. 코드 identifier, package/API 이름, CLI, configuration key, metric field, 실제 log/error는 영어 원문을 유지한다.
2. 이 저장소에 자체 `vllm/` fork를 만들지 않는다. NPU substrate는 설치된 `vllm 0.22.0+cpu` + `vllm-rbln 0.11.1`이다.
3. site-packages를 직접 수정하지 않는다. 필요한 관측 변경은 `patches/` 정책을 따르며 적용 전에 보고한다.
4. CUDA semantics와 GPU threshold를 RBLN에 그대로 적용하지 않는다.
5. decision accuracy만 최적화하지 않고 mis-selection cost와 regret을 함께 본다.
6. eviction/release를 recomputation으로 해석하지 않는다.
7. cache source를 latency만으로 판정하지 않는다. 증거가 부족하면 `UNKNOWN`, 일부만 확인되면 `PARTIAL`을 허용한다.
8. requested condition, observed condition, condition reached 여부를 분리한다. instantaneous pressure만으로 cache survival을 설명하지 않는다.
9. 관찰, 파생 해석, hypothesis를 분리하고 metric의 population, unit, source, device scope를 기록한다.
10. package/version/config/model/device/Git provenance를 모든 실험 artifact에 기록한다.
11. dependency 설치, model download/compile, RSD 변경, device reset, patch 적용 전에 사용자에게 보고하고 승인을 받는다.
12. legacy `/home/rebel/vllm-continuum`을 수정하거나 삭제하지 않는다.
13. Stage 0–2 baseline 전에는 KEEP/OFFLOAD/RECOMPUTE, host/peer parking, scheduler policy를 구현하지 않는다.
14. raw evidence를 보존하고 invariant 실패 시 run을 `INVALID`로 종료한다. 관측 불가 field를 0으로 채우지 않는다.
15. 과거에 실패한 접근, 잘못된 가정, unreachable condition, semantic confounder, invalid metric으로 판정된 내용을 관련 TASK 확인 없이 반복하지 않는다.

`docs/legacy/TASKxx.md`는 legacy GPU namespace다. 새 NPU TASK 번호는 `docs/research/TASK*.md`만 기준으로 정한다.
