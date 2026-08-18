# TASK01 — 연구 작업 기록 및 Agent Workflow 구축

## 상태

DONE

## 날짜

2026-08-18

## 목적

Claude Code, Codex 및 기타 coding agent 사이의 연구 context 단절을 방지하고, 의미 있는 연구·구현 결과를 일관된 NPU TASK history로 보존한다.

## 배경

새 session이 과거 결과를 확인하지 않으면 이미 실패하거나 반증된 접근을 반복하고 현재 blocker 또는 연구 validity 원칙을 놓칠 수 있다. 기존 환경·포팅 문서는 있었지만 모든 작업의 단일 진입점과 TASK 생성 workflow는 없었다.

관련 TASK: 없음. 새 NPU TASK namespace의 bootstrap 작업이다.

## 시작 상태

- Git commit: `f68a099` (`Initialize clean NPU research repository`)
- `docs/research/`: `.gitkeep`만 존재하며 기존 `TASKNN.md`와 `INDEX.md`는 없었다.
- 기존 연구 근거: `docs/environment/`의 환경 감사·포팅 분석·준비도 문서
- Stage 0 model gate: 검증된 precompiled RBLN model artifact가 확인되지 않아 `BLOCKED`
- Working tree: 작업 전 untracked `.idea/`가 있었으며 사용자 소유 변경으로 보고 수정하지 않았다.

## 수행 내용

- `AGENTS.md`에 repository-wide INDEX-first mandatory workflow를 추가했다.
- `CLAUDE.md`에 Claude Code 실행 중심의 동일한 hard requirement를 추가했다.
- `docs/research/INDEX.md`를 현재 연구 상태에 맞는 단일 진입점으로 작성했다.
- `docs/research/TASK_GUIDE.md`에 번호, 상태 taxonomy, 문서 구조, 증거 기록 및 INDEX 동시 갱신 규칙을 정의했다.
- legacy GPU TASK와 새 NPU TASK namespace를 분리했다.
- 의미 있는 작업 종료 후 TASK 기록과 INDEX 갱신을 하나의 완료 invariant로 정했다.

## 변경된 파일

- `AGENTS.md`
- `CLAUDE.md`
- `docs/research/INDEX.md`
- `docs/research/TASK_GUIDE.md`
- `docs/research/TASK01.md`

## 실험 또는 검증 방법

- `git status --short`로 기존 변경과 생성 파일을 확인한다.
- `git diff --check`로 whitespace 오류를 확인한다.
- Markdown 상대 링크 대상의 존재 여부를 확인한다.
- AGENTS/CLAUDE workflow와 필수 invariant를 상호 점검한다.

## 결과

### 관찰

- 기존 `docs/research/TASK*.md`가 없어 새 NPU namespace의 첫 번호는 `TASK01`이었다.
- `docs/legacy/`의 `TASK25`, `TASK27`, `TASK29`, `TASK31`은 별도 legacy GPU namespace에 존재한다.
- 환경 문서상 source isolation은 `PASS`, Stage 0 model gate는 `BLOCKED`다.

### 구현 결과

- 모든 agent가 작업 전 INDEX와 관련 TASK를 읽는 workflow를 문서화했다.
- 새 TASK 생성 시 실제 파일과 Git 상태를 재확인하고 TASK와 INDEX를 함께 갱신하도록 했다.
- 상태 `DONE`, `PARTIAL`, `BLOCKED`, `FAILED`, `INVALID`, `SUPERSEDED`의 의미를 고정했다.

## 핵심 발견

기존 연구 사실은 환경 문서에 충분히 남아 있어 migration 전체를 가상의 여러 TASK로 소급 복원할 필요가 없었다. 기록 체계 도입 자체만 bootstrap TASK로 남기고 이전 작업은 INDEX에서 근거 문서로 연결하는 편이 chronology 왜곡을 피한다.

## 해석

INDEX는 현재 상태와 탐색 경로를 제공하고 TASK는 연구 의미와 재현 정보를 보존한다. 상세 형식을 `TASK_GUIDE.md`에 집중시켜 `AGENTS.md`와 `CLAUDE.md`의 중복 정책 drift 가능성을 줄였다.

## 확인되지 않은 사항

- 이 workflow가 모든 외부 agent runtime에서 자동 로드되는지는 각 도구의 repository instruction discovery 동작에 의존하므로 `UNKNOWN`이다.
- Stage 0 실행 가능 model artifact의 존재는 이번 작업에서 새로 조사하지 않았으며 기존 감사 결과대로 확인되지 않았다.

## 실패 / 무효 시도

없음.

## 연구 원칙에 미치는 영향

- 작업 전 INDEX와 관련 TASK 확인을 hard requirement로 승격했다.
- 관찰, 해석, hypothesis 및 `UNKNOWN`을 명시적으로 분리한다.
- 과거 invalid 접근의 무맥락 반복을 금지한다.
- legacy GPU와 clean-room NPU 연구 번호를 분리한다.

## 다음 작업

사용자가 검증된 precompiled RBLN model path를 제공하거나 download/compile을 승인한 경우에만 Stage 0 source-isolated single inference를 시작한다. 이 TASK 완료를 이유로 다음 연구 단계를 자동 실행하지 않는다.

## 재현 정보

- Repository: `/home/rebel/continuum-npu`
- Base commit: `f68a099`
- 검증 command: `git status --short`, `git diff --check`
- 연구 인덱스: `docs/research/INDEX.md`
- TASK 지침: `docs/research/TASK_GUIDE.md`
