# Rebellions NPU 연구 준비도

## Q1. 현 Continuum을 NPU에서 그대로 실행할 수 있는가?

**아니오.** 기존 tree는 vLLM 0.10.2-family CUDA fork이고 설치된 RBLN substrate는 vLLM 0.22 API를 요구한다. source resolution, scheduler/worker/cache semantics, synchronization, connector 의존성이 모두 다르다.

## Q2. 가장 먼저 깨지는 부분은?

저장소 root에서 Python을 실행할 때 local `vllm/`이 site-packages를 shadowing하는 source-resolution 문제다. 이를 해결해도 old scheduler/worker API는 vLLM 0.22 + RBLN semantics와 호환되지 않는다.

## Q3. Hardware-independent하게 재사용 가능한 영역은?

정확한 line-of-code 비율은 측정하지 않았으므로 수치를 제시하지 않는다. 영역 기준으로 workload generation, client-side tool gap, request sequencing, experiment arm/trial metadata, regret/SLO/tail-latency analysis, preregistration, requested/observed condition 분리는 재사용 가능하다. scheduler, worker, KV allocator, transfer, synchronization은 재설계 대상이다.

## Q4. KV lifecycle을 NPU에서 관찰할 수 있는가?

**일부 가능성은 있으나 실행 검증 전이다.** RBLN scheduler/cache manager의 allocation/free/usage path는 source에 존재한다. request-level survival과 resume source를 확정할 구조화 metric은 확인되지 않았다.

## Q5. APC hit와 실제 KV survival을 구분할 수 있는가?

현재 **확인되지 않음**. 초기 실험은 `LOCAL_OR_PREFIX_HIT`를 사용하고 증거 부족 시 `UNKNOWN`으로 남겨야 한다. latency로 구분하지 않는다.

## Q6. Host↔NPU KV transfer primitive가 존재하는가?

Source-level design은 존재하지만 현 deployment의 API·bandwidth·live KV integration은 `UNKNOWN`이다. 현 단계에서 지원된다고 판정하지 않는다.

## Q7. NPU↔NPU D2D primitive가 존재하는가?

Source-level NIXL path는 존재하지만 `nixl-rbln`은 미설치이고 benchmark는 실행하지 못했다. 현 deployment 판정은 `UNKNOWN`이다.

## Q8. D2D를 live vLLM KV migration에 연결할 수 있는가?

**입증되지 않음.** transport, arbitrary buffer transfer, allocator/cache manager export·reattach는 별도 gate다. 앞의 gate 통과가 다음 gate를 의미하지 않는다.

## Q9. 8-card topology가 KV parking에 의미 있는 비균질성을 보이는가?

Distance class 4/8/12라는 구조적 비균질성은 있다. 성능 비균질성은 측정하지 않았으므로 `UNKNOWN`이다.

## Q10. Dynamic decoder batching을 scheduler에서 관찰할 수 있는가?

Source observation point는 확정했다. native runner의 `num_reqs_unpadded`와 `num_reqs_padded`, optimum runner의 `bucket_sizes`가 핵심이다. compiled bucket list의 init log는 있지만 per-step 구조화 metric은 아직 확인되지 않았다.

## Q11. 가장 현실적인 첫 연구는?

| 후보 | Novelty | 구현 난이도 | Runtime 변경 | 측정 가능성 | 연구 가치 | Major blocker |
|---|---|---|---|---|---|---|
| A. Gap-turnover-aware KV policy | 높음 | 높음 | scheduler/cache observation 필요 | raw allocation signal 미검증 | 매우 높음 | resume attribution |
| B. Host KV parking | 중간 | 매우 높음 | connector/lifecycle | transport 미검증 | 높음 | live KV export/reattach |
| C. Peer-NPU KV parking | 높음 | 매우 높음 | connector/allocator | D2D 미측정 | 매우 높음 | NIXL 미설치, live migration |
| D. Tool-return-aware dynamic batch scheduling | 높음 | 중간–높음 | 초기에 observation만 | source point 확정 | 높음 | per-step metric 미노출 |
| E. Agent-aware NPU partitioning | 중간–높음 | 매우 높음 | process/device assignment | topology 성능 미측정 | 높음 | RSD/device semantics |

권고 순서는 **Stage 0–2 observation baseline → D의 observation-only characterization → A의 raw-signal feasibility**다. 정책 제어나 KV migration은 아직 시작하지 않는다.

## 현재 결론

- Source isolation: `PASS`
- Stage 0 model gate: `BLOCKED`
- Stage 1 serving: Stage 0 선행 요건 미충족으로 `BLOCKED`
- Stage 2 APC OFF/ON: Stage 1 미실행으로 `BLOCKED`
- Decoder observation point: source-level 확정, runtime metric은 미검증

검증된 precompiled RBLN model path를 확보하거나, 다운로드·compile에 대한 명시적 승인을 받기 전에 Stage 0를 강행하지 않는다.
