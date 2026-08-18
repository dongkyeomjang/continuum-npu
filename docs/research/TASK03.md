# TASK03 — 작업 종료 시 main commit Workflow 도입

## 상태

DONE

## 날짜

2026-08-18

## 목적

모든 coding/research agent가 각 작업의 검증된 변경을 local `main` branch에 commit하고 commit provenance를 보고하도록 repository-wide 종료 workflow를 강화한다.

## 배경

관련 TASK:

- [TASK01](TASK01.md) — INDEX-first 연구 기록 workflow 구축
- [TASK02](TASK02.md) — Stage 0 사전 검증 기록

TASK/INDEX 문서화 규칙은 있었지만 이전 정책은 자동 commit을 금지했다. 사용자는 앞으로 각 작업 종료 시 `main`에 commit하도록 명시적으로 요청했다.

## 시작 상태

- Branch: `main`
- HEAD: `f68a09900422e30ca519491c4d2fa94b8bc74f67`
- TASK01·TASK02와 workflow 문서 변경이 아직 uncommitted 상태였다.
- Untracked `.idea/`는 사용자 소유·무관 변경으로 판단해 commit 대상에서 제외했다.

## 수행 내용

- `AGENTS.md`와 `CLAUDE.md`에 작업 종료 commit을 `HARD REQUIREMENT`로 추가했다.
- Agent가 소유한 파일만 명시적으로 stage하도록 했다.
- Commit 전 staged diff/검증, commit 후 hash/Git 상태 확인을 요구했다.
- Local `main` commit과 remote `push` 권한을 구분했다.
- Commit 실패 시 작업 완료로 보고하지 않도록 했다.
- 상세 정책 drift를 막기 위해 `TASK_GUIDE.md`에도 동일한 종료 invariant를 추가했다.

## 변경된 파일

- `AGENTS.md`
- `CLAUDE.md`
- `docs/research/TASK_GUIDE.md`
- `docs/research/TASK03.md`
- `docs/research/INDEX.md`

이번 commit에는 아직 commit되지 않았던 TASK01·TASK02 및 Stage 0 문서도 함께 포함한다. `.idea/`와 ignored raw artifact는 포함하지 않는다.

## 실험 또는 검증 방법

- `git diff --check`
- Untracked Markdown whitespace 검사
- Markdown 상대 링크 검사
- staged file 목록 및 staged diff 확인
- Commit 후 `git rev-parse HEAD`, `git status --short` 확인

## 결과

### 관찰

- 현재 branch는 `main`이다.
- 기존 정책에는 작업 종료 commit 단계가 없었다.

### 구현 결과

- 각 작업의 local `main` commit이 완료 invariant가 됐다.
- 무관한 사용자 변경을 자동 stage하지 않는 소유권 경계를 함께 명시했다.
- Remote `push`는 자동화 범위에서 제외했다.

## 핵심 발견

Commit 자동화를 안전하게 운영하려면 branch/commit 요구뿐 아니라 staging 범위와 push 권한 경계를 함께 고정해야 한다.

## 해석

이제 TASK 문서와 실제 source history가 작업 종료 시점에 함께 고정된다. 단, working tree의 모든 변경을 일괄 commit하는 규칙은 아니며 각 agent가 소유한 변경만 대상으로 한다.

## 확인되지 않은 사항

없음.

## 실패 / 무효 시도

없음.

## 연구 원칙에 미치는 영향

연구 결과 provenance에 local Git commit을 필수 완료 조건으로 추가했다. Remote repository 반영은 별도 승인 경계로 유지한다.

## 다음 작업

없음. 현재 요청 범위를 넘어 Stage 0 또는 다른 연구 작업을 시작하지 않는다.

## 재현 정보

- Repository: `/home/rebel/continuum-npu`
- Base commit: `f68a09900422e30ca519491c4d2fa94b8bc74f67`
- Target branch: `main`
