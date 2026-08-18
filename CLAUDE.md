# Claude 작업 규칙

1. 사용자 대상 설명과 연구 문서는 한국어로 작성한다. 코드 identifier, package/API 이름, 실제 log/error는 영어를 유지한다.
2. 이 저장소에 자체 `vllm/` fork를 만들지 않는다. NPU substrate는 설치된 `vllm 0.22.0+cpu` + `vllm-rbln 0.11.1`이다.
3. site-packages를 직접 수정하지 않는다. 필요한 관측 변경은 `patches/` 정책을 따른다.
4. CUDA semantics를 RBLN에 그대로 적용하지 않는다. GPU threshold도 재사용하지 않는다.
5. eviction/release를 recomputation으로 해석하지 않는다.
6. cache source를 latency만으로 판정하지 않는다. 증거가 부족하면 `UNKNOWN`, 공유 prefix만 남으면 `PARTIAL`을 허용한다.
7. requested condition과 observed condition, condition reached 여부를 분리한다.
8. package/version/config/model/device provenance를 모든 실험 artifact에 기록한다.
9. dependency 설치, model download/compile, RSD 변경, device reset 전에 사용자에게 보고하고 승인을 받는다.
10. legacy `/home/rebel/vllm-continuum`을 수정하거나 삭제하지 않는다.
11. Stage 0–2 baseline 전에는 KEEP/OFFLOAD/RECOMPUTE, host/peer parking, scheduler policy를 구현하지 않는다.
12. raw evidence를 보존하고 invariant 실패 시 run을 `INVALID`로 종료한다. 관측 불가 field를 0으로 채우지 않는다.
