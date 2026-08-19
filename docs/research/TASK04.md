# TASK04 — 연구 workflow 문서 개정: 결정 대기 절, 선등록 hard rule, hostname UNKNOWN 승격

## 상태

DONE

## 날짜

2026-08-19

## 목적

연구 workflow 문서의 세 가지 구조적 결함을 고친다.

1. 사용자 판정이 필요한 결정이 `INDEX.md`의 blocker 문단에 산문으로 섞여 있어 선택지·근거·비용·미지수를 사용자가 한눈에 비교할 수 없었다.
2. 선등록(preregistration)과 동치 판정 규칙이 legacy 문서(`docs/legacy/GPU_RESEARCH_FINDINGS.md`)의 "유지할 방법론" 목록에만 있어 집행력이 없었다.
3. 환경 문서와 현재 관찰의 hostname 불일치가 TASK02 본문에만 있어 INDEX 진입점에서는 보이지 않았다.

## 배경

관련 TASK:

- [TASK01](TASK01.md) — INDEX-first 연구 기록 workflow 구축
- [TASK02](TASK02.md) — Stage 0 사전 검증. hostname 불일치(`rebel-pcie-0123` vs `atom-max8`)와 model artifact blocker를 처음 기록했다.
- [TASK03](TASK03.md) — 작업 종료 시 local `main` commit workflow 도입

TASK02가 Stage 0를 `BLOCKED`로 남긴 뒤 진행 재개 조건은 사용자 판정(model download/compile 승인)이 됐다. 그러나 그 판정에 필요한 선택지와 근거를 기록할 자리가 문서 구조에 없었다. 또한 Stage 0 이후 TASK는 대부분 측정·판정 TASK이므로, 측정이 시작되기 전에 선등록 규칙을 집행 문서로 올려두어야 사후 기준 완화를 구조적으로 막을 수 있다.

## 시작 상태

- Repository: `/home/rebel/continuum-npu-minnow` (worktree)
- Branch: `minnow`, HEAD `d4604a69090b008369adfa23925f16ef21732dec`
- `main`은 `/home/rebel/continuum-npu` worktree에 checkout되어 있어 이 worktree에서 `main`으로 전환할 수 없다. `minnow`와 `main`은 같은 commit `d4604a6`을 가리켰다.
- Working tree: clean
- 기존 TASK: TASK01–TASK03. 다음 번호는 `TASK04`.

## 수행 내용

### 1. `INDEX.md`에 "사용자 결정 대기" 절 신설

- Task Index 표와 "완료된 주요 작업" 사이에 `## 사용자 결정 대기` 절을 만들었다.
- 항목 형식을 고정했다: 결정 ID, 상태, 질문, 선택지, 선택지별 근거/비용/미지수(`UNKNOWN` 허용), 권고안, 관련 TASK.
- 권고안은 제안일 뿐 판정은 사용자가 한다는 문구와, 결정 해소 시 근거 TASK를 링크하라는 규칙을 절 머리말에 명시했다.
- **결정 2 — Stage 0 대상 model의 download/compile 승인**을 빈 틀로 등록하고 상태를 `대기` (근거 미수집)로 두었다. 후속 조사 완료 후 채운다고 표시했으며, 조사 전에 후보·download 크기·KV bytes/token·device 요구를 추정으로 채우지 말라는 제약을 함께 적었다.
- 결정 1(후보 model metadata 조사)은 사용자 지시문으로 이미 집행이 승인되어 판정 대기 항목이 아니므로 별도 항목으로 만들지 않았다.
- 기존 "현재 주요 blocker" 문단은 선택지를 중복 서술하지 않고 이 절을 단일 출처로 참조하도록 고쳤다.

### 2. 선등록·동치 판정 규칙을 hard rule로 승격

`docs/legacy/GPU_RESEARCH_FINDINGS.md`의 "NPU 연구에서 유지할 방법론" 2번(측정 전 preregistration)을 집행 문서 세 곳에 같은 의미로 추가했다.

- `CLAUDE.md` "실행 및 연구 원칙" 16, 17번
- `AGENTS.md` "연구 validity" 절 마지막 두 bullet
- `docs/research/TASK_GUIDE.md` "증거 기록 원칙" 두 bullet

승격한 규칙의 내용:

- 측정과 판정이 포함된 TASK는 판정 기준, 예측, 실험 격자를 측정 시작 전에 commit한다(선등록). TASK 재현 정보에 선등록 commit hash와 측정 시작 시각의 선후 관계를 기록한다. 측정 후에 판정 기준을 완화하지 않으며, 완화가 불가피하면 원 기준의 실패를 함께 보고한다.
- 두 조건의 동치 판정은 고정 밴드가 아니라 중앙 ratio의 bootstrap CI가 1을 포함하고 CI 폭이 사전 등록한 상한 이내인지로 한다.

`TASK_GUIDE.md` 필수 구조의 `## 재현 정보`에는 `선등록 commit` 항목을 명시했고, 측정이 없는 TASK는 `해당 없음`으로 적도록 했다.

### 3. hostname 불일치를 INDEX 수준 `UNKNOWN`으로 승격

`INDEX.md` 현재 상태에 "환경 provenance `UNKNOWN`" 문단을 추가했다. 환경 문서의 `rebel-pcie-0123`과 현재 관찰 `atom-max8`이 불일치하고 원인은 `UNKNOWN`이며, 그 결과 `NPU_ENVIRONMENT.md`의 topology distance 구조, NUMA affinity, RSD group, device inventory가 현재 host에서 유효한지도 `UNKNOWN`임을 기재했다. 해소 경로는 `atom-max8` read-only 재-inventory와 항목별 대조임을 명시했다.

### 4. 경미 정리 2건

- `INDEX.md`의 "가장 최근 TASK"와 "최근 완료 TASK" 중복을 제거했다. "가장 최근 TASK"는 번호가 가장 큰 TASK로 정의하고, 그 TASK가 `BLOCKED`/`PARTIAL`/`FAILED`/`INVALID`일 때만 "최근 완료 TASK"(가장 번호가 큰 `DONE`)를 별도 줄로 추가하도록 조건을 한 줄로 남겼다.
- `TASK_GUIDE.md` 필수 구조의 `## 결과` 절에 측정 TASK용 하위 항목 `requested_condition` / `observed_condition` / `condition_reached`를 명시했다. 기존에는 "증거 기록 원칙"에만 있어 TASK template에 반영되지 않았다.

## 변경된 파일

- `CLAUDE.md`
- `AGENTS.md`
- `docs/research/TASK_GUIDE.md`
- `docs/research/INDEX.md`
- `docs/research/TASK04.md` (신규)

`docs/legacy/`, `README.md`, `docs/environment/`는 이번 TASK에서 변경하지 않았다.

## 실험 또는 검증 방법

문서 전용 변경이므로 측정 실험은 없다. 수행한 검증:

- `git diff --check` — whitespace/conflict marker 검사
- `INDEX.md`, `TASK04.md`, `TASK_GUIDE.md`, `CLAUDE.md`, `AGENTS.md`의 Markdown 상대 링크 대상 파일 존재 확인
- `INDEX.md` 내 앵커 링크 `#사용자-결정-대기`가 실제 `## 사용자 결정 대기` heading과 대응하는지 확인
- `CLAUDE.md` / `AGENTS.md` / `TASK_GUIDE.md` 세 문서에 추가한 선등록·동치 판정 문구의 의미 일치 확인
- staged file 목록과 staged diff 확인, commit 후 `git rev-parse HEAD` / `git status --short` 확인

## 결과

### 관찰

- 개정 전 `INDEX.md`에는 사용자 판정 대기 항목을 위한 구조가 없었고, blocker 문단이 상태 서술과 진행 조건 서술을 겸하고 있었다.
- 개정 전 선등록 규칙은 `docs/legacy/GPU_RESEARCH_FINDINGS.md`에만 존재했고 집행 문서(`CLAUDE.md`, `AGENTS.md`, `TASK_GUIDE.md`) 어디에도 없었다.
- 개정 전 hostname 불일치는 `TASK02.md` 본문에만 있었고 `INDEX.md`와 `NPU_ENVIRONMENT.md`에는 반영되지 않았다.
- `TASK_GUIDE.md`의 `## 결과` template에는 requested/observed/condition_reached 구분이 없었다.

측정 TASK가 아니므로 `requested_condition` / `observed_condition` / `condition_reached`는 해당 없음.

### 구현 결과

- 사용자 판정 대기 결정의 단일 출처가 `INDEX.md`에 생겼고 결정 2 틀이 등록됐다.
- 선등록·동치 판정이 세 집행 문서의 hard rule이 됐고 TASK template에 선등록 commit 기록란이 생겼다.
- hostname 불일치와 그 파급(환경 문서 유효성 `UNKNOWN`)이 INDEX 진입점에서 보인다.

## 핵심 발견

집행되지 않는 방법론은 legacy 문서에 보존되어 있어도 다음 측정에서 재현되지 않는다. 선등록처럼 "측정 시작 전"이라는 시점 제약이 있는 규칙은 첫 측정 TASK가 발생하기 전에 집행 문서로 올려야 의미가 있다. Stage 0가 `BLOCKED`인 지금이 그 시점이다.

또한 blocker를 산문으로만 기술하면 "왜 막혔는가"와 "누가 무엇을 판정해야 풀리는가"가 섞인다. 후자를 구조화된 항목으로 분리하면 사용자 판정에 필요한 정보가 무엇인지(그리고 아직 무엇이 `UNKNOWN`인지)가 문서 구조 자체로 드러난다.

## 해석

이하는 관찰이 아닌 해석이다.

- hostname 불일치를 INDEX 수준으로 올린 것은 "환경 문서가 틀렸다"는 판정이 아니다. 두 이름의 관계가 확인되지 않았으므로 문서의 topology/NUMA/RSD 값을 현재 host의 사실로 인용할 근거가 없다는 뜻이다. 재-inventory 전까지 device 수·NUMA 배치를 실험 설계의 전제로 삼지 않는 것이 안전하다.
- 동치 판정을 고정 밴드에서 bootstrap CI 기준으로 바꾼 것은 NPU에서 어떤 밴드가 적절한지 알려진 바가 없기 때문이다. GPU에서 쓰던 밴드 폭을 그대로 옮기면 CUDA threshold 재사용 금지 원칙을 위반한다.

## 확인되지 않은 사항

- hostname `rebel-pcie-0123`과 `atom-max8`의 관계 (`UNKNOWN`)
- `NPU_ENVIRONMENT.md`의 topology distance 구조, NUMA affinity, RSD group, device memory가 현재 host에서 유효한지 (`UNKNOWN`)
- 동치 판정에 쓸 bootstrap CI 폭 상한의 구체 값. 측정 TASK별로 선등록 시점에 정한다 (현재 `UNKNOWN`)
- 결정 2의 후보 model, download 크기, KV bytes/token, device 요구 (`UNKNOWN`, 후속 조사 대상)

## 실패 / 무효 시도

없음. 문서 변경만 수행했고 system 조회, model download, compile, device 변경, dependency 변경은 하지 않았다.

## 연구 원칙에 미치는 영향

- 측정·판정 TASK는 선등록 commit 없이 시작할 수 없다. 측정 시작 시각이 선등록 commit보다 앞서면 그 사실을 재현 정보에 남겨야 한다.
- 동치 판정에 고정 밴드를 쓰지 않는다.
- 사용자 판정이 필요한 사항은 agent가 기본값으로 처리하지 않고 `INDEX.md`의 "사용자 결정 대기"에 등록한다.
- 환경 문서의 hardware 값은 현재 host에서 재확인되기 전까지 실험 전제로 사용하지 않는다.

## 다음 작업

후보 model metadata와 `atom-max8` read-only 재-inventory를 조사해 결정 2 표를 채운다. 이는 별도 TASK로 기록한다. Stage 0 inference, download, compile은 사용자 판정 전에는 시작하지 않는다.

## 재현 정보

- Base commit: `d4604a69090b008369adfa23925f16ef21732dec`
- Branch: `minnow` (`main`이 `/home/rebel/continuum-npu` worktree에 checkout되어 있어 이 worktree에서 `main` 전환 불가. 임의 merge/rebase는 하지 않았고 사용자에게 보고한다.)
- 선등록 commit: 해당 없음 (측정이 없는 문서 TASK)
- 근거 문서: `docs/legacy/GPU_RESEARCH_FINDINGS.md` "NPU 연구에서 유지할 방법론" 2번
- 검증 command: `git diff --check`, Markdown 상대 링크 존재 확인
