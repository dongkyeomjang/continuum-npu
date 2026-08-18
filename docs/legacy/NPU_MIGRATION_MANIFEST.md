# NPU Repository Migration Manifest

- 작성일: 2026-08-18
- Source: `/home/rebel/vllm-continuum`
- Destination: `/home/rebel/continuum-npu`
- 방식: whitelist migration

이 manifest는 기존 저장소를 네 범주로 분류한다. `KEEP`만 파일 단위로 복사하고, `EXTRACT`는 필요한 순수 로직을 새 module로 재작성한다. `ARCHIVE_ONLY`와 `DROP`은 기존 저장소에서 삭제하지 않으며 새 저장소에 넣지 않는다.

## KEEP

### `notes/NPU_ENVIRONMENT.md`

이유:
현재 CA25 서버의 hardware/software/topology와 source-resolution 위험을 기록한 provenance 문서다.

Destination:
`docs/environment/NPU_ENVIRONMENT.md`

### `notes/NPU_PORTING_ANALYSIS.md`

이유:
기존 CUDA 구성요소와 RBLN substrate 사이의 semantic gap 및 redesign boundary를 기록한다.

Destination:
`docs/environment/NPU_PORTING_ANALYSIS.md`

### `notes/NPU_RESEARCH_READINESS.md`

이유:
APC, resume attribution, transfer, dynamic decoder batching의 확인 가능 범위와 `UNKNOWN`을 보존한다.

Destination:
`docs/environment/NPU_RESEARCH_READINESS.md`

### `tasks/TASK25.md`, `tasks/TASK27.md`, `tasks/TASK29.md`, `tasks/TASK31.md`

이유:
비대칭 mis-selection cost, KEEP 조건부 가치, requested/observed pressure, cache attribution과 turnover 가설의 원자료다. GPU threshold를 재사용하기 위한 문서가 아니라 방법론과 실패 이력을 보존하기 위한 legacy reference다.

Destination:
`docs/legacy/TASK25.md`, `docs/legacy/TASK27.md`, `docs/legacy/TASK29.md`, `docs/legacy/TASK31.md`

### `experiments/npu/launch/run_isolated_python.sh`

이유:
repository-local `vllm/` shadowing을 fail-loud로 막는 NPU 전용 launcher다. CUDA나 old vLLM API에 의존하지 않는다.

Destination:
`experiments/npu/launch/run_isolated_python.sh`

### `experiments/npu/probes/runtime_probe.py`

이유:
site-packages `vllm`/`vllm-rbln` path와 version을 machine-readable artifact로 검증한다. 새 저장소 경계에서 다시 실행할 가치가 있다.

Destination:
`experiments/npu/probes/runtime_probe.py`

### `experiments/npu/probes/decoder_observability.py`

이유:
site-packages를 수정하지 않고 exact installed source/hash와 decoder observation point를 기록한다.

Destination:
`experiments/npu/probes/decoder_observability.py`

## EXTRACT

### `experiments/npu/instrumentation/metrics_schema.py`

source:
`experiments/npu/instrumentation/metrics_schema.py`

추출할 기능:

- versioned accelerator-neutral observation record
- `UNKNOWN`/`PARTIAL`을 포함한 resume taxonomy
- token accounting, decoder bucket invariant

GPU/NPU 의존성:
없음. NPU 전용 경로에서 일반 연구 계층으로 승격할 수 있다.

새로운 destination:
`src/continuum/metrics/schema.py`

### `experiments/measure_task29_capacity.py`

source:
`experiments/measure_task29_capacity.py`

추출할 기능:

- client-side tool-gap timestamp model
- requested condition과 observed condition 분리
- expected sample count와 input-length fail-loud pattern

GPU/NPU 의존성:
HTTP/workload logic과 GPU server lifecycle, legacy arm injection, LMCache assumptions가 섞여 있다.

새로운 destination:
이번 migration에서는 pure validation interface만 `src/continuum/analysis/validation.py`로 재작성한다. 실제 workload driver는 RBLN Stage 0–2 이후 작성한다.

### `experiments/analyze_task25_m5.py`, `experiments/analyze_task27_direct.py`

source:
위 두 legacy analyzer

추출할 기능:

- paired ratio 개념
- median 중심 요약
- mis-selection cost와 regret 입력 검증

GPU/NPU 의존성:
계산 자체는 중립적이나 legacy JSON key, arm 이름, result layout에 강하게 결합되어 있다.

새로운 destination:
이번 migration에서는 paired ordering과 fail-loud 자료구조만 `src/continuum/workload/paired.py`로 재작성한다. 통계 구현은 NPU schema가 안정된 뒤 별도 migration한다.

### `experiments/analyze_tracelab.py`

source:
`experiments/analyze_tracelab.py`

추출할 기능:

- TraceLab JSONL streaming parser
- context/tool latency population definition
- malformed/missing field fail-loud validation

GPU/NPU 의존성:
accelerator dependency는 낮지만 local dataset path와 TASK31-specific bins/output schema에 결합되어 있다.

새로운 destination:
향후 `src/continuum/workload/tracelab.py`. 이번 초기 migration에서는 파일 전체를 복사하지 않고 provenance와 추출 계획만 보존한다.

### `experiments/task*_predictions.json`

source:
TASK25/26/27/29/31 preregistration JSON

추출할 기능:
schema version, hypothesis, invalidation rule, requested/observed condition 표현

GPU/NPU 의존성:
실제 threshold, arm, GPU pool 크기와 legacy path가 포함되어 있다.

새로운 destination:
향후 `src/continuum/analysis/preregistration.py`. 기존 JSON 자체는 `ARCHIVE_ONLY`다.

## ARCHIVE_ONLY

### `results/`

이유:
GPU raw measurement, crash salvage, figures와 TraceLab 산출물을 포함한다. 과거 연구 검증에는 중요하지만 NPU result provenance와 섞으면 안 된다.

### `paper/`, `notes/`의 기존 논문·회의 자료

이유:
역사와 서사 검증에는 가치가 있으나 새 저장소의 현재 설계 문서로 오해될 수 있다. 핵심 결론은 `GPU_RESEARCH_FINDINGS.md`에 요약한다.

### `experiments/`의 TASK별 launcher/analyzer/measurement code

이유:
대부분 legacy result schema, GPU server launcher, LMCache, old vLLM request extension에 결합되어 있다. 필요한 pure logic만 `EXTRACT`한다.

### `continuum_exp/`, `mini-swe-agent/`

이유:
이전 workload/source snapshot이다. 새 NPU runtime의 실행 코드로 가져오지 않으며 필요하면 legacy path에서 읽는다.

### `vllm/`, `tasks/` 전체, `docs/`, `examples/`, `benchmarks/`, `tests/`

이유:
old vLLM fork와 그 upstream ecosystem이다. 선택한 TASK 네 개만 문서 reference로 migration한다.

## DROP

다음은 새 저장소에 복사하지 않는다. 여기서 `DROP`은 기존 저장소 삭제를 뜻하지 않는다.

### Environment와 cache

- `.venv/`, `.venv-fig/`: 이전 absolute Python path를 가진 broken environment
- `__pycache__/`, `*.pyc`: host/interpreter dependent cache
- `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`
- `.env`, `.env.*`: credential 유입 위험

### Build와 binary

- `build/`, `dist/`, `*.so`
- `csrc/`, CUDA extension, CUDA/NCCL/P2P microbenchmark
- `CMakeLists.txt`, `cmake/`, old `setup.py`, old `pyproject.toml`

이유:
CUDA/compiler/runtime에 결합되어 있고 CA25 RBLN artifact가 아니다.

### Old runtime fork

- repository 전체 `vllm/`
- `vllm.egg-info/`
- old scheduler, worker, model runner, `set_up_pin`, CUDA pinned-memory 구현

이유:
vLLM 0.10.2-family CUDA fork이며 site-packages vLLM 0.22를 shadowing한다.

### Launcher와 dependency definition

- `CUDA_VISIBLE_DEVICES`/`nvidia-smi`/`pynvml` 기반 launcher와 health monitor
- 기존 `requirements/`, `constraints.txt`
- GPU server launcher와 serial mapping

### Git와 hosting

- `.git/`, `.github/`, `.buildkite/`
- old remote, branch, history, workflow, issue/PR template, dependabot, CODEOWNERS

### Editor/local agent state

- `.idea/`, `.claude/`, `.codex/`, `.gemini/`, `.agents/`

이유:
사용자별 상태 또는 과거 repository 운영 설정이며 새 source of truth에 가져오지 않는다. 새 `CLAUDE.md`와 `AGENTS.md`는 요구사항에 맞춰 재작성한다.

## Migration invariant

새 저장소에는 다음이 존재하면 안 된다.

```text
vllm/
.venv/
.venv-fig/
.github/
*.so
CUDA source/build artifact
old Git history/remote
```

새 코드에 `torch.cuda`, `CUDA_VISIBLE_DEVICES`, `nvidia-smi`, `pynvml`, `NCCL`이 나타나면 runtime dependency인지 문서/reference 문자열인지 구분하고, runtime dependency이면 migration을 실패 처리한다.
