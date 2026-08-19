# Continuum-NPU 연구 TASK 작성 지침

이 문서는 `docs/research/TASKNN.md`의 생성과 유지에 대한 source of truth다. 연구 진행 상황의 진입점은 [INDEX.md](INDEX.md)다.

## 기록 대상

새 Stage, experiment, instrumentation, 중요한 bug/root cause 해결, architecture 변경, metric 정의, hypothesis 검증·반증, baseline·workload·policy 구축, 중요한 runtime discovery 또는 향후 방향에 영향을 주는 blocker는 TASK로 기록한다.

오타, 한 줄 문서·주석 수정, 단순 rename/formatting/lint, 기존 TASK를 마무리하는 사소한 patch는 독립 TASK로 만들지 않는다. 같은 작업의 추가 검증, artifact path·누락 보완은 기존 TASK에 추가할 수 있다. 새 hypothesis, experiment, architecture, 결론 재검증, blocker 해결, policy 또는 implementation phase는 새 TASK로 기록한다. TASK는 commit log를 대체하지 않는다.

## 번호와 namespace

1. 생성 직전에 `INDEX.md`, 실제 `docs/research/TASK*.md`, `git status`를 다시 확인한다.
2. `docs/research/TASK*.md`의 가장 큰 번호에 1을 더한다. 번호를 재사용하지 않는다.
3. 동시 agent가 예상 번호를 사용했다면 다음 번호를 쓴다. 시작 시점에 번호를 미리 고정하지 않는다.
4. `docs/legacy/TASK*.md`는 legacy GPU namespace이므로 번호 계산에서 제외한다.
5. TASK 생성과 INDEX 갱신은 같은 작업 단위에서 수행한다.

## 상태 정의

- `DONE`: 목표와 성공 기준을 충족했다.
- `PARTIAL`: 일부 목표만 달성했으며 후속 작업이 필요하다.
- `BLOCKED`: 외부 dependency, hardware, permission, model 등의 이유로 현재 진행할 수 없다.
- `FAILED`: 실행했으나 목표를 달성하지 못했다.
- `INVALID`: 실험 조건, measurement 또는 instrumentation 문제로 결과를 연구 결론에 사용할 수 없다.
- `SUPERSEDED`: 후속 TASK의 더 나은 구현 또는 실험으로 대체됐다.

큰 작업은 필요하면 `IN_PROGRESS` skeleton으로 시작할 수 있지만 작업 종료 시 위 최종 상태로 변경한다. 실패와 blocker도 향후 판단에 중요한 지식이면 기록한다.

## 필수 구조

```markdown
# TASKNN — 제목

## 상태

DONE / PARTIAL / BLOCKED / FAILED / INVALID / SUPERSEDED

## 날짜

YYYY-MM-DD

## 목적

## 배경

관련 TASK:

- `TASKxx.md` — 실제 문서에서는 상대 링크와 설명을 작성

## 시작 상태

Git commit, package version, model, relevant config, device configuration 등 중요한 전제조건

## 수행 내용

## 변경된 파일

## 실험 또는 검증 방법

## 결과

관찰 사실과 raw measurement

측정 TASK는 다음을 분리해 기록한다.

- `requested_condition` — 요청한 실험 조건
- `observed_condition` — 실제로 관측된 조건
- `condition_reached` — 요청 조건 도달 여부 (`YES` / `NO` / `PARTIAL` / `UNKNOWN`)

## 핵심 발견

## 해석

파생 해석과 hypothesis를 관찰과 분리

## 확인되지 않은 사항

UNKNOWN 또는 추가 검증 필요 사항

## 실패 / 무효 시도

## 연구 원칙에 미치는 영향

## 다음 작업

## 재현 정보

command, config, artifact/result path, commit, version 등

- 선등록 commit: 선등록 commit hash와 측정 시작 시각의 선후 관계. 측정이 없는 TASK는 `해당 없음`
```

섹션을 억지로 길게 쓰지는 않지만 중요한 섹션을 이유 없이 생략하지 않는다. 해당 사항이 없으면 `없음`이라고 명시할 수 있다.

## 증거 기록 원칙

- 관찰값, 파생 해석, 연구적 추론을 구분한다.
- 근거가 부족하면 `UNKNOWN`, `확인되지 않음`, `추가 검증 필요`로 남긴다.
- requested condition, observed condition, condition reached를 별도 기록한다.
- 측정과 판정이 포함된 TASK는 판정 기준, 예측, 실험 격자를 측정 시작 전에 commit한다(선등록, preregistration). `## 재현 정보`에 선등록 commit hash와 측정 시작 시각의 선후 관계를 기록한다. 측정 후에 판정 기준을 완화하지 않으며, 완화가 불가피하면 원 기준의 실패를 함께 보고한다.
- 두 조건의 동치(equivalence) 판정은 고정 밴드가 아니라 중앙 ratio의 bootstrap CI가 1을 포함하고 CI 폭이 사전 등록한 상한 이내인지로 한다.
- metric의 population, unit, source, device scope를 기록한다.
- raw log 수천 줄은 TASK에 복사하지 않는다. `results/npu/...` 등의 artifact path, 핵심 measurement, 해석, 재현 방법을 기록하고 필요한 짧은 error/log만 인용한다.

## INDEX 갱신

새 TASK를 만든 즉시 [INDEX.md](INDEX.md)에 번호, 상태, 제목, 1~2줄 요약을 추가한다. 해결된 blocker를 제거하고 현재 상태, 핵심 연구 흐름, 다음 권장 작업도 사실에 맞게 갱신한다. INDEX는 상세 일지가 아니라 현재 상태를 보여주는 간결한 진입점이다.

의미 있는 TASK 완료 보고에는 생성한 파일, 상태, INDEX 갱신 여부, 핵심 결과, 다음 작업을 포함한다. 다음 작업은 제안만 하며 사용자 지시 없이 실행하지 않는다.

## 작업 종료 commit

각 작업의 검증된 변경은 local `main` branch에 commit해야 완료된다. Agent가 이번 작업에서 생성·수정한 파일만 명시적으로 stage하며 기존 사용자/다른 agent 변경, secret, raw result, ignored artifact는 포함하지 않는다. 의미 있는 TASK와 INDEX 갱신은 해당 구현·연구 변경과 같은 commit에 포함한다. Commit 후 hash와 남은 Git 상태를 보고한다.

작업 종료 보고마다 commit할 변경이 있었는지와 관계없이 반드시 사용자에게 "GitHub의 `origin/main`에 push할까요?"라고 묻고 답을 기다린다. Remote `push`는 자동 수행하지 않으며 사용자가 현재 질문에 명시적으로 승인한 경우에만 해당 local `main` commit을 push한다. 과거 승인이나 일반적 선호를 현재 push 승인으로 재사용하지 않는다. Push 전 remote와 대상 commit을 확인하고 push 후 local/remote ref를 확인한다. Force push는 별도 명시적 지시 없이는 수행하지 않는다.
