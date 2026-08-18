# Continuum NPU 이식 사전 분석

## 1. 경계

기존 `vllm/`은 CUDA 기반 연구 구현의 reference code이다. NPU 실행 substrate는 site-packages의 `vllm 0.22.0+cpu` + `vllm-rbln 0.11.1`이다. old tree를 dual-backend로 만들거나 installed source를 old tree에 복사하지 않는다.

## 2. Component mapping

| Existing Component | GPU Assumption | NPU Equivalent | Status | Required Change | Risk |
|---|---|---|---|---|---|
| scheduler | old vLLM 0.10.2-family custom scheduler | vLLM 0.22 + `RBLNScheduler` | REQUIRES_REDESIGN | API·semantics mapping 후 accelerator-neutral policy layer | 매우 높음 |
| KV allocation | GPU block allocator, mixed scheduling | RBLN KV manager, request allocation semantics | REQUIRES_REDESIGN | allocation/lifetime 실측 우선 | 매우 높음 |
| KV release | `free()`와 prefix cache 상호작용 | RBLN scheduler/cache manager | REQUIRES_ADAPTER | release event·cache survival 별도 계측 | 높음 |
| KEEP | GPU pin/TTL | 검증된 동치 경로 없음 | REQUIRES_REDESIGN | NPU cache lifecycle 관찰 후 재정의 | 매우 높음 |
| OFFLOAD | CUDA/lmcache CPU·NVMe path | optional RBLN KV connector | UNSUPPORTED | 현 환경에 dependency 미설치, 설치 금지 | 매우 높음 |
| RELOAD | CUDA/NIXL/lmcache timing | source-level connector design | UNKNOWN | transport·buffer·live-KV gate 분리 | 매우 높음 |
| RECOMPUTE | cache miss를 reprefill로 해석 | APC/sub-block path 가능 | REQUIRES_REDESIGN | token evidence 없으면 `UNKNOWN` | 매우 높음 |
| prefix caching | upstream APC + GPU backend | upstream APC + conditional RBLN sub-block cache | REQUIRES_ADAPTER | resolved APC/sub-block state 독립 기록 | 높음 |
| resume attribution | latency/cache verdict 혼용 이력 | cached/computed/external token signal 후보 | REQUIRES_REDESIGN | `LOCAL_OR_PREFIX_HIT`, `PARTIAL`, `UNKNOWN` 허용 | 매우 높음 |
| memory-pressure measurement | `gpu_cache_usage`, CUDA memory | KV manager usage 및 device metric 후보 | REQUIRES_ADAPTER | 명목 occupancy와 turnover 분리 | 높음 |
| latency timing | `torch.cuda.synchronize`, CUDA event | RBLN/runtime synchronization 미확인 | REQUIRES_REDESIGN | end-to-end·server event 동시 계측 | 높음 |
| worker | custom CUDA worker | `RBLNWorker` | REQUIRES_REDESIGN | old patch 이식 금지, adapter 선호 | 높음 |
| model runner | CUDA graph/model runner | `RBLNModelRunner`, `OptimumModelRunner` | REQUIRES_ADAPTER | observation point만 최소 노출 | 높음 |
| experiment runner | HTTP/client orchestration | backend-neutral client 가능 | MINOR_CHANGE | NPU metadata·fail-loud gate 추가 | 중간 |
| metrics | GPU 명칭·0 추정 가능성 | versioned neutral schema | REQUIRES_ADAPTER | legacy field 보존, `null/UNKNOWN` 사용 | 중간 |
| tool-gap workload | client-side sleep + growing prompt | 그대로 사용 가능 | WORKS_AS_IS | timestamp·input invariant 추가 | 낮음 |
| multi-device execution | GPU `tensor_parallel_size=N` | RBLN local-rank/device multiplicity | REQUIRES_REDESIGN | model mode별 assignment 검증 | 매우 높음 |

## 3. CUDA dependency 분류

저장소의 `torch.cuda.synchronize()`, CUDA event, `pynvml`, `nvidia-smi`, `gpu_memory_utilization`, CUDA worker/model runner, NCCL path는 NPU timing·memory semantics에 그대로 쓸 수 없다.

- A — NPU-specific 변경 필수: runtime worker/model runner, synchronization, allocator/copy, distributed backend
- B — device abstraction 가능: workload, policy input schema, run metadata, HTTP timing
- C — experiment harness 한정: `nvidia-smi`, GPU selection, GPU health check
- D — 명칭만 GPU: 일부 result field. 의미 재검증 없이 NPU 값을 넣지 않음
- E — dead/obsolete: copied build artifact와 완료된 과거 experiment path 후보
- F — 판단 불가: runtime에서 실제 호출되는지 미확인 path

특히 CUDA synchronization을 제거하고 wall clock만 넣는 것은 timing correctness를 보장하지 않는다. RBLN command completion semantics를 관찰할 signal이 필요하다.

## 4. APC와 resume attribution

`VLLM_RBLN_SUB_BLOCK_CACHE=True`는 APC default-on을 의미하지 않는다. upstream `enable_prefix_caching`이 true이고 model/config eligibility를 만족할 때만 effective sub-block cache가 활성화된다.

초기 taxonomy:

```text
LOCAL_OR_PREFIX_HIT
HOST_RELOAD
PEER_NPU_RELOAD
RECOMPUTE_OR_REPREFILL
PARTIAL
UNKNOWN
```

local survival marker가 없으면 `LOCAL_KV_HIT`와 `PREFIX_CACHE_HIT`를 분리하지 않는다. latency는 attribution 증거가 아니다. TASK31에서 확인한 16-token local block, 256-token external chunk, shared prefix, 물리적 도달 가능 최대치를 고려하지 않으면 marker가 구조적으로 잘못 분류할 수 있다.

## 5. Dynamic decoder batching

설치 source에서 관찰 지점은 확인되었다.

- actual batch 후보: `num_reqs_unpadded`
- selected compiled bucket: `_determine_batch_padding()`의 `num_reqs_padded`
- native runner 선택: `find_decode_batch_bucket(num_reqs_unpadded)`
- optimum sampler bucket list: `self.model.decoder_batch_sizes` 또는 `max_num_seqs`에서 생성

compiled bucket list와 sampler bucket은 init debug log에서 일부 확인 가능하다. 그러나 per-step `actual_num_reqs` / `selected_bucket`을 구조화한 existing metric은 현재 확인하지 못했다. 향후 필요 시 site-packages 직접 수정이 아닌 hash-guarded observation adapter/patch가 필요하다.

## 6. Transfer capability 분리

| Layer | Host↔NPU | NPU↔NPU |
|---|---|---|
| hardware/runtime transport | UNKNOWN | UNKNOWN |
| Python/C++ arbitrary buffer API | NOT EXPOSED / UNKNOWN | NOT EXPOSED / UNKNOWN |
| live vLLM KV export/reattach | UNKNOWN | UNKNOWN |

source-level NIXL direct-device path가 존재하는 것과 현 deployment에서 실행 가능하다는 것은 다르다. `nixl-rbln`이 미설치이며 live KV migration은 입증되지 않았다.

## 7. Compiled artifact

복사된 CUDA `.so`, `build/`, `.venv`, cache는 source host의 architecture/runtime에 의존한다. 삭제하지 않았지만 NPU execution artifact로 사용하지 않는다.

## 8. 포팅 전 필수 gate

1. source-isolated site-packages import
2. 검증된 precompiled RBLN model artifact
3. Stage 0 single inference
4. Stage 1 serving + resolved config
5. APC OFF/ON 독립 구성
6. token/cache evidence가 있는 Stage 2 repeated prefix
7. decoder batch observation

이 gate를 통과하기 전에 old GPU scheduler를 이식하지 않는다.
