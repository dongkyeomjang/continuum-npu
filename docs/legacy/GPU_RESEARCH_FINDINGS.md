# GPU Continuum 연구 핵심 교훈

## 연구 출발점

Agent workload는 LLM request 사이에 tool call 또는 human-paced gap이 생긴다. 기존 연구는 이 gap 동안 accelerator에 남은 KV cache를 어떻게 관리할지 조사했다. 단순히 빈 KV를 CPU/NVMe로 내리는 문제가 아니라, cache survival, 재개 비용, 작업집합 회전과 tail/SLO 비용을 함께 다루는 문제였다.

## 기존 정책

- `KEEP`: tool gap 동안 request의 KV를 accelerator에서 유지하거나 pin하여 빠른 재개를 기대한다.
- `OFFLOAD`: KV를 CPU/NVMe 계층으로 저장하고 재개 때 reload한다.
- `RECOMPUTE`: KV를 보존하지 않고 재개 시 prefix를 다시 prefill한다.

이 이름은 GPU 연구 당시의 구현 의미다. RBLN에서 동일한 primitive와 lifecycle이 확인되기 전에는 같은 이름만으로 semantic equivalence를 가정하지 않는다.

## TASK25 핵심 결과

Adaptive policy의 decision accuracy만으로 정책 가치를 평가할 수 없다. 잘못된 선택의 비용은 context length에 따라 크게 비대칭적이었다. 큰 context에서 잘못된 결정을 내릴 때 regret가 작은 context보다 훨씬 커졌고, 중앙 경향의 작은 이득과 tail 악화가 동시에 나타날 수 있었다.

NPU 연구에서는 accuracy 외에 다음을 별도로 본다.

- regret
- mis-selection cost
- tail latency
- SLO violation
- context/workload별 비용 비대칭

## TASK27 핵심 결과

GPU 실험에서 `KEEP`의 가치는 context length, tool gap, pressure 조건에 따라 달랐다. 짧은 context에서는 pin이 해로울 수 있었고 긴 context에서는 재획득 비용을 줄였다. 순간 `kv_usage`는 압박의 단조 대리값이 아니었으며, 포화 시 request가 할당 단계에 들어오지 못해 오히려 낮아질 수 있었다.

최종 GPU 규칙과 수치 threshold는 그 환경의 실측 결과다. 이를 NPU threshold로 복사하지 않는다. NPU에서는 requested condition, observed condition, condition reached를 다시 측정한다.

## TASK29 핵심 결과

용량은 단순 session count가 아니라 실현된 working set과 KV pool의 비에 의해 갈렸다. 같은 requested concurrency에서도 context 추첨에 따라 observed working set이 달라졌고, 셀을 풀링하면 이봉 분포와 절벽을 숨길 수 있었다.

Offload가 steady-state capacity를 자동으로 늘리지는 않았다. 재개 시 accelerator로 다시 가져와야 하는 working set이 pool을 넘으면 thrashing이 발생했다. 그러나 이후 TASK31은 이 음성 결과가 prefix cache가 재획득 비용을 흡수한 조건에 한정됨을 밝혔다.

필수 교훈:

- requested pressure와 observed pressure를 분리한다.
- condition이 실제 도달했는지 검증한다.
- steady-state capacity와 working-set phase를 구분한다.
- session count 같은 명목 x축만으로 결론을 내리지 않는다.

## TASK31 핵심 결과

### Eviction/release와 recomputation은 다르다

Request에서 KV block을 release해도 prefix cache가 살아 있으면 재개가 full reprefill이 아닐 수 있다. 빠른 latency를 local survival로, 느린 latency를 recomputation으로 분류해서는 안 된다.

### Cache source를 분리해야 한다

Local prefix cache, external cache reload, recomputation을 token-level evidence로 구분해야 한다. Reliable marker가 없으면 `LOCAL_OR_PREFIX_HIT` 또는 `UNKNOWN`을 사용한다.

### `PARTIAL`이 필요하다

공유 system prompt만 남고 session-specific prefix가 사라질 수 있다. 이 상태를 hit/miss 이분법으로 강제하면 잘못된 결론이 난다.

### 물리적 granularity를 검증해야 한다

GPU local cache의 16-token block과 external cache의 256-token chunk 때문에 명목 prompt 길이 기준 90% threshold가 구조적으로 도달 불가능한 셀이 있었다. Threshold는 명목값이 아니라 물리적으로 도달 가능한 최대에 대해 검증한다.

### Instantaneous pressure만으로 survival을 설명할 수 없다

순간 KV occupancy가 낮아도 긴 gap 동안 다른 request가 누적 할당하면 cache pool이 여러 번 회전해 paused session의 prefix가 사라졌다. 후보 state는 다음과 같다.

```text
tool gap duration
× background KV allocation rate
× working-set turnover
```

`cumulative allocation during gap / effective KV pool capacity`는 유망한 가설이지만 NPU에서 다시 측정해야 한다.

## NPU 연구에서 유지할 방법론

1. randomized paired experiment와 block-balanced order
2. 측정 전 preregistration
3. 입력, 표본 수, arm identity, marker semantics의 fail-loud invariant
4. decision accuracy가 아닌 regret와 mis-selection cost
5. median/paired ratio와 tail latency/SLO violation 병기
6. requested condition, observed condition, condition reached 분리
7. latency가 아닌 raw signal에 근거한 resume attribution
8. `UNKNOWN`/`PARTIAL` 허용
9. raw log와 population definition, unit, source, device scope 보존
10. threshold가 실제 system에서 도달 가능한지 pre-flight로 확인

## NPU에서 다시 검증할 것

- APC OFF/ON과 effective RBLN sub-block state
- local KV survival과 prefix-cache hit의 구분 가능성
- RBLN KV allocation/free/turnover signal
- decoder actual batch와 selected compiled bucket
- Host↔NPU 및 NPU↔NPU transport와 live KV lifecycle integration
- 모든 crossover와 pressure threshold
