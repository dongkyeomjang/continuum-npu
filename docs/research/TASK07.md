# TASK07 — 작업 종료 시 GitHub push 확인 Workflow 도입

## 상태

DONE

## 날짜

2026-08-19

## 목적

모든 작업 종료 시 local `main` commit 이후 GitHub `origin/main` push 여부를 사용자에게 반드시 묻고, 현재 질문에 대한 명시적 승인 후에만 push하도록 repository-wide workflow를 고정한다.

## 배경

관련 TASK:

- [TASK03](TASK03.md) — 작업 종료 시 local `main` commit workflow 도입

TASK03은 remote `push`를 별도 지시 대상으로만 규정했다. 사용자는 이제 모든 작업 종료 시 push 여부를 항상 질문하도록 요청했다. OpenAI 공식 문서에 따르면 Codex는 작업 전에 repository의 `AGENTS.md`를 읽어 project-specific 지침을 적용하므로, 이 선호를 repository instruction에 기록하는 것이 이 저장소에서 지속 가능한 방식이다.

## 시작 상태

- Branch: `main`
- HEAD: `057bbae5c8479769aa7eecf76f8f59be7c456937`
- Remote: `origin` → `git@github.com:dongkyeomjang/continuum-npu.git`
- Working tree: untracked `.idea/`만 존재

## 수행 내용

- `AGENTS.md`와 `CLAUDE.md` 종료 workflow에 push 확인 질문을 hard requirement로 추가했다.
- 자동 push를 금지하고 현재 종료 질문의 명시적 승인만 유효하도록 했다.
- 과거 승인이나 일반적 선호를 현재 push 권한으로 재사용하지 않도록 했다.
- Push 전 remote/commit 확인, push 후 local/remote ref 확인을 요구했다.
- Force push는 별도 명시적 지시 없이는 금지했다.
- `TASK_GUIDE.md`에 동일한 source-of-truth 규칙을 반영했다.

## 변경된 파일

- `AGENTS.md`
- `CLAUDE.md`
- `docs/research/TASK_GUIDE.md`
- `docs/research/TASK07.md`
- `docs/research/INDEX.md`

## 실험 또는 검증 방법

- `git diff --check`
- Markdown 상대 링크 검사
- AGENTS/CLAUDE/TASK_GUIDE 정책 일관성 검사
- 명시적 파일 staging 및 staged diff 검사
- Local `main` commit 후 hash와 Git 상태 확인

## 결과

### 관찰

- 기존 규칙은 push를 자동 승인하지 않았지만 매 작업 종료 시 질문하도록 요구하지는 않았다.

### 구현 결과

- 모든 작업 종료 보고에 GitHub push 확인 질문이 필수가 됐다.
- Push 실행 권한은 각 종료 질문에 대한 사용자의 명시적 응답으로 제한됐다.

## 핵심 발견

지속적 선호와 실제 외부 변경 권한은 분리해야 한다. "항상 질문"은 repository 지침으로 지속시키되 실제 push는 매번 새 승인을 받는다.

## 해석

이 workflow는 작업 결과를 GitHub에 반영할 기회를 놓치지 않으면서도 remote state 변경을 사용자가 매번 통제하게 한다.

## 확인되지 않은 사항

없음.

## 실패 / 무효 시도

공식 OpenAI 문서 검색 첫 시도는 일반 developers portal 결과만 반환했다. 이후 공식 AGENTS.md guide를 직접 열어 repository instruction discovery 동작을 확인했다.

## 연구 원칙에 미치는 영향

Local commit provenance는 계속 필수다. Remote 반영은 매 작업 종료 시 질문하되 사용자 승인 전에는 수행하지 않는다.

## 다음 작업

없음. 이 작업의 local commit 후 사용자에게 `origin/main` push 여부를 묻는다.

## 재현 정보

- Repository: `/home/rebel/continuum-npu`
- Base commit: `057bbae5c8479769aa7eecf76f8f59be7c456937`
- Target branch: `main`
- Remote: `origin`
- 공식 근거: `https://learn.chatgpt.com/docs/agent-configuration/agents-md`
- 선등록 commit: 해당 없음 (측정 없는 workflow 문서 변경)
