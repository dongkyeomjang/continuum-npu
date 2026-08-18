# Legacy 저장소 정리 후보

대상: `/home/rebel/vllm-continuum`

이 문서는 장차 검토할 삭제 후보만 기록한다. 이번 migration에서는 아무것도 삭제하지 않았다.

## SAFE_TO_DELETE_LATER

최종 삭제 전에 legacy 연구 실행 재현이 더 이상 필요하지 않은지 한 번 더 확인한다.

- `.venv/`, `.venv-fig/`: 이전 host absolute path를 가진 broken environment
- 모든 `__pycache__/`, `*.pyc`
- copied `build/`, `dist/`
- CUDA `.so`와 재생성 가능한 binary artifact
- 임시 log와 명백한 local cache

## KEEP_AS_ARCHIVE

- `tasks/` 전체 연구 기록
- `results/`의 raw experiment result와 crash salvage
- 원본 GPU Continuum source와 custom scheduler/worker/model runner
- `paper/`와 실제 사용된 figure/table
- preregistration JSON과 experiment launcher/analyzer
- TraceLab 분석 기록 및 population definition
- Git history와 당시 branch provenance

## REVIEW_BEFORE_DELETE

- large model/download cache: provenance와 다른 사용자의 의존 여부 확인 필요
- intermediate experiment artifact: 논문 표/그림의 source인지 확인 필요
- datasets/traces: license, 원본 hash, 다른 연구의 의존 여부 확인 필요
- copied `mini-swe-agent/`, `continuum_exp/`: 재현성에 필요한 snapshot인지 확인 필요
- old documentation/build tree: 논문 또는 artifact evaluation에서 참조되는지 확인 필요

## 삭제 전 필수 검증

1. 새 NPU 저장소와 legacy archive backup이 별도 위치에 존재하는지 확인
2. 논문 figure/table이 어떤 raw result를 사용하는지 mapping
3. dataset/model license와 checksum 보존
4. 삭제 대상의 정확한 path와 size를 read-only로 다시 확인
5. 사용자 명시 승인 후 recoverable 방식 우선
