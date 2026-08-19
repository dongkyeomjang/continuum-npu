# Continuum-NPU Research Task Index

이 문서는 모든 agent가 작업 전에 읽는 연구 진행 상황의 단일 진입점이다. 상세 작성 규칙은 [TASK_GUIDE.md](TASK_GUIDE.md)를 따른다.

## 현재 상태

현재 연구 단계: Stage 0, Stage 1a, Stage 1b가 모두 `PASS`했고, [TASK11](TASK11.md)에서 prefix cache hit 단위를 **inner block 128 token**으로 확정했다. [TASK12](TASK12.md)에서 결정 3을 집행해 per-step decoder bucket 관측 patch를 적용·검증했다. Stage 2와 Track A 양쪽의 진입 조건이 갖춰졌다.

가장 최근 TASK: [TASK12](TASK12.md) — 결정 3 집행: decoder bucket 관측 patch 적용과 검증 (`DONE`)

"가장 최근 TASK"는 번호가 가장 큰 TASK다. 그 TASK의 상태가 `BLOCKED`, `PARTIAL`, `FAILED`, `INVALID` 중 하나여서 최근 진척을 대표하지 못할 때만 아래에 "최근 완료 TASK"(가장 번호가 큰 `DONE` TASK)를 별도로 한 줄 추가한다. 두 줄이 같은 TASK를 가리키면 한 줄만 남긴다.

현재 주요 blocker: 없다. 미해결 사용자 결정도 없다. Stage 2와 Track A는 blocker가 아니라 아직 실행하지 않은 상태다.

**substrate 상태 주의**: 이 host의 `vllm-rbln 0.11.1`은 [TASK12](TASK12.md)의 observation-only patch가 **적용된 상태**다 (`model_base.py` SHA256 `70942d16…`). Git이 추적하지 않으므로 모든 측정 run은 `bash patches/vllm_rbln-0.11.1/apply.sh status` 출력을 artifact에 provenance로 남긴다.

Stage 1 이후 설계에 제약이 되는 관측 (근거 [TASK06](TASK06.md), [TASK08](TASK08.md)):

- `attn_impl=eager` 기본값에서 KV pool 크기는 DRAM이 아니라 `batch_size`가 결정한다. `kvcache_num_blocks = (max_seq_len // kvcache_block_size) × batch_size`이고 기본값에서 `kvcache_block_size = max_seq_len`이므로 결과는 정확히 `batch_size`이며 block 1개가 sequence 1개분이다. 현재 b1 artifact의 KV pool은 sequence 1개분(8,320 token)뿐이므로 동시성 실험은 재compile을 전제로 한다.
- decoder bucket은 자동으로 다단화되지 않는다. `decoder_batch_sizes`를 명시하지 않으면 단일 bucket이고 bucket 선택 자체가 일어나지 않는다.
- per-step `(요청 수, 선택된 bucket)`은 upstream에서 계산만 되고 노출되지 않았으나, [TASK12](TASK12.md)의 observation-only patch가 `[BUCKET] request_nums=<n> padded_batch_size=<b>` DEBUG 로그로 노출시켰다. 관측된 사상은 `select_bucket_size` 산식과 전건 일치했다(1→1, 2→2, 3→4, 5→8, 8→8). `VLLM_RBLN_DECODE_BATCH_BUCKET_*`와 `VLLM_RBLN_SUB_BLOCK_CACHE`는 기본 경로에서 무효다.
- `num_gpu_blocks`는 frontend가 EngineCore 보고값을 누적하는 구조(`vllm/v1/engine/core_client.py:712`) 때문에 EngineCore 값의 2배로 나온다([TASK09](TASK09.md)에서 해소). 실제 KV pool은 EngineCore 값이다. `"GPU KV cache size: N tokens"` log는 `num_blocks × block_size`가 아니라 `max_concurrency × max_model_len`이다.
- 채택 가능한 관측 신호([TASK09](TASK09.md), [TASK11](TASK11.md) 감사): `vllm:num_requests_running`, `vllm:num_requests_waiting`, `vllm:kv_cache_usage_perc`(해상도는 inner block, 분모 `num_gpu_blocks−1`), `vllm:prefix_cache_queries_total`·`hits_total`·`prompt_tokens_cached_total`(전부 단위가 요청이 아니라 **token**. cached는 hits와 항상 같은 값), server 주기 로그의 `Running/Waiting/KV usage`, DEBUG 로그의 `[PFX] [CACHE-HIT]`(outer/inner block ID)와 `Allocated/Freed block(s)`. `/metrics` gauge는 반드시 in-flight로 표집하고 metric 이름은 정확히 일치시킨다.
- **prefix cache hit 단위는 inner block 128 token**이다([TASK11](TASK11.md)). hit 양은 `floor((prompt_tokens − 1) / 128) × 128`이며 10개 조건에서 전건 일치했다. prompt가 129 token 미만이면 hit이 구조적으로 0이다. outer block 8,192은 hit 단위가 아니다.
- **APC OFF/ON은 단일 인자 토글이 아니다**([TASK11](TASK11.md)). OFF에서 `block_size`가 128 → 8192, `num_gpu_blocks`가 513 → 9, KV cache size가 65,664 → 73,728 token으로 함께 바뀐다. 비교 시 이 confounder를 함께 기록한다. OFF에서는 `queries`조차 0이므로 `--no-enable-prefix-caching`으로 확실히 끌 수 있다.
- Compile cost는 165 s / 9.08 GiB로 측정되어 재compile은 실질적 제약이 아니다.
- `enable_prefix_caching`은 지정하지 않으면 `True`로 resolve되므로 APC OFF/ON은 명시적으로 통제한다.

환경 provenance `UNKNOWN` (`PARTIAL` 해소): 환경 문서 [NPU_ENVIRONMENT.md](../environment/NPU_ENVIRONMENT.md)의 hostname은 `rebel-pcie-0123`이지만 현재 관찰 hostname은 `atom-max8`이다. 두 이름이 같은 host인지, 재설치·rename·다른 장비인지는 여전히 `UNKNOWN`이다. [TASK05](TASK05.md)의 read-only 재-inventory에서 hostname을 제외한 모든 대조 항목(visible ID 수 32, card grouping 4×8, device memory 15.7 GiB, NUMA 분할, topology distance 4/8/12, RSD group 0)이 일치했으므로 해당 문서의 hardware 기술은 현재 host에서 실무상 사용할 수 있다. 다만 값 일치는 장비 동일성의 증거가 아니므로 provenance `UNKNOWN`은 유지한다.

다음 권장 작업: 두 갈래가 독립적으로 가능하다. (1) Stage 2 repeated-prefix baseline — 설계 제약은 [TASK11](TASK11.md)의 "다음 작업" 절. (2) Track A decoder bucket characterization — 진입 조건은 [TASK12](TASK12.md)에서 갖춰졌고 이월 사항은 그 TASK의 "다음 작업" 절. 둘 다 측정이 포함되므로 선등록 후 진행한다. 사용자 지시 없이 자동 착수하지 않는다.

## Task Index

| Task | 상태 | 제목 | 간략 설명 |
|---|---|---|---|
| [TASK01](TASK01.md) | DONE | 연구 작업 기록 및 Agent Workflow 구축 | INDEX-first workflow와 TASK 기반 연구 이력을 도입했다. 모든 agent가 관련 과거 결정을 확인하고 TASK와 INDEX를 함께 갱신하도록 규칙을 통합했다. |
| [TASK02](TASK02.md) | SUPERSEDED | Stage 0 CA25 단일 추론 Bring-up 사전 검증 | Source isolation과 8 physical CA25 card/32 visible ID inventory를 재검증했다. 실행 가능한 local model/artifact가 없어 승인 필요한 download/compile 전에 중단했다. 이 `BLOCKED`는 [TASK06](TASK06.md)의 실제 실행으로 해소됐다. |
| [TASK03](TASK03.md) | DONE | 작업 종료 시 main commit Workflow 도입 | 각 작업의 검증된 agent-owned 변경을 local `main`에 commit하고 hash를 보고하도록 종료 규칙을 강화했다. Remote `push`는 별도 지시 대상으로 유지했다. |
| [TASK04](TASK04.md) | DONE | 연구 workflow 문서 개정 | INDEX에 "사용자 결정 대기" 절을 신설하고, 선등록·동치 판정 규칙을 집행 문서의 hard rule로 승격했으며, hostname 불일치를 INDEX 수준 `UNKNOWN`으로 올렸다. |
| [TASK05](TASK05.md) | DONE | Stage 0 후보 model 조사와 atom-max8 재-inventory | 후보 3개의 HF metadata·config·KV bytes/token·설치 source 지원 근거를 read-only로 수집해 결정 2 근거 표를 만들었다. `atom-max8` 재-inventory는 hostname을 제외한 전 항목이 환경 문서와 일치했다. |
| [TASK06](TASK06.md) | DONE | Stage 0 실행: Qwen/Qwen3-4B download·compile·CA25 단일 추론 | 선등록한 7개 PASS 조건을 전부 충족해 Stage 0를 `PASS` 판정했다. Compile 165 s / artifact 9.08 GiB, `num_devices=4`는 단일 physical card(`rbln0`–`rbln3`)에 배치됐고 memory·utilization·context로 NPU 실행을 확인했다. |
| [TASK08](TASK08.md) | DONE | compile 파라미터 공간과 KV accounting source 조사 | `eager`에서 `kvcache_num_blocks = batch_size`임을 source로 확정하고 TASK06의 KV accounting `UNKNOWN`을 대부분 해소했다. 문서화된 bucket 관측 지점이 기본 실행 경로 밖임을 확인하고 Stage 1b compile 파라미터 권고안과 사전 예측표를 만들었다. |
| [TASK09](TASK09.md) | DONE | Stage 1a: b1 artifact serving bring-up과 관측 감사 | 선등록 5개 조건을 전부 충족해 `PASS` 판정했다. `num_gpu_blocks` 2배 anomaly를 frontend 누적 구조로 해소하고 KV·큐 metric의 live 여부를 in-flight 표집으로 감사했다. b1 artifact는 동시 요청을 거부하지 않고 큐에 세운다(`running` 최대 1, `waiting` 최대 2). |
| [TASK10](TASK10.md) | DONE | Stage 1b: multi-bucket compile과 동시성 진입, decoder bucket 관측 판정 | 선등록 3개 조건을 전부 충족해 `PASS` 판정했다. `batch_size=8`에서 `running`이 8에 도달했고 TASK08의 KV accounting 예측 9개가 전부 실측과 일치했다. compile 349 s / artifact 11.50 GiB이며 크기는 decoder bucket 개수에만 비례한다. decoder bucket의 per-step 관측은 4개 수단 모두에서 불가로 판정해 결정 3을 신설했다. |
| [TASK11](TASK11.md) | DONE | prefix cache hit 경계와 KV block 의미론 확정 | hit 단위를 inner block 128 token으로 확정하고 산식 `floor((n−1)/128)×128`이 10개 조건에서 전건 일치함을 확인했다. TASK09·TASK10의 `hits = 0`은 prompt가 129 token 문턱 아래였기 때문이다. 선등록 예측 9개 중 8개 적중. APC OFF가 block 입도까지 바꾸는 confounder를 발견했다. |
| [TASK12](TASK12.md) | DONE | 결정 3 집행: decoder bucket 관측 patch 적용과 검증 | `patches/` 정책의 첫 실전 적용. 검증 관문 3개(의미론 전건 일치, 관찰자 효과, 복구)를 모두 통과해 patch를 적용 상태로 유지했다. `[BUCKET]` 로그 635줄에서 사상 1→1, 2→2, 3→4, 5→8, 8→8이 전건 일치했고 bucket padding 낭비가 정량화됐다. |
| [TASK07](TASK07.md) | DONE | 작업 종료 시 GitHub push 확인 Workflow 도입 | 모든 작업 종료 시 `origin/main` push 여부를 반드시 사용자에게 묻고, 현재 질문에 대한 명시적 승인 후에만 push하도록 규칙을 추가했다. |

## 사용자 결정 대기

이 절은 agent가 임의로 진행할 수 없고 사용자 판정이 필요한 결정의 단일 출처다. 현재 미해결 항목은 없다. 각 항목은 결정 ID, 질문, 선택지, 선택지별 근거·비용·미지수, 권고안, 관련 TASK를 갖는다. 권고안은 제안일 뿐이며 판정은 사용자가 한다. 결정이 내려지면 항목을 "해소됨"으로 표시하고 근거 TASK를 링크한다.

### 결정 3 — decoder bucket 관측용 hash-guarded observation-only patch 승인

- 상태: `해소됨` — **승인 (2026-08-19). 집행 완료: [TASK12](TASK12.md)**
- 집행 결과: patch를 작성·적용하고 검증 관문 3개를 모두 통과해 **적용 상태로 유지**한다. 정책 문서는 [patches/vllm_rbln-0.11.1/README.md](../../patches/vllm_rbln-0.11.1/README.md)다.
- 질문: 기본 실행 경로의 per-step `(실제 요청 수, 선택된 decoder bucket)`을 관측하기 위해, `patches/` 정책을 따르는 hash-guarded **observation-only** patch를 승인할 것인가?
- 관련 TASK: [TASK08](TASK08.md)(source 근거), [TASK10](TASK10.md)(실행 수준 확인)
- 근거: [TASK10](TASK10.md) "핵심 산출". 선등록에서 한정한 4개 수단을 모두 검색했으나 노출 경로가 없었다. Patch는 작성하지도 적용하지도 않았다.

**왜 필요한가**

Track A(decoder bucket characterization)는 "요청 수가 N일 때 어느 bucket이 선택되고 그 padding 낭비가 얼마인가"를 대상으로 한다. 이 값이 관측되지 않으면 Track A는 성립하지 않는다.

**관측 불가의 근거 (4개 수단 전부 검색)**

| 수단 | 결과 |
|---|---|
| `VLLM_LOGGING_LEVEL=DEBUG` server 로그 911줄 | 기동 시점의 정적 목록(`Bucket sizes for RBLN sampler: (1, 2, 4, 8)`)과 warm-up dummy compile 로그만 존재. 서비스 구간에는 request 단위 block 할당·해제 로그만 있고 step 단위 batch 정보 없음 |
| `/metrics` 122개 항목 | `bucket` 매칭은 전부 Prometheus histogram bucket. batch·decoder 관련 항목 없음 |
| `VLLM_RBLN_METRICS=1` | `PREFILL` / `DECODE` / `PADDED DECODE` 절의 latency 통계만. `PADDED DECODE`는 `StepReport.padded_decode`를 `True`로 설정하는 caller가 package 전체에 없어 항상 비어 있음 |
| 기타 read-only 경로 | 기동 시 config dump와 `rbln_config.json`은 정적 bucket 목록 |

**Patch 대상 (제안, 미작성)**

| 항목 | 내용 |
|---|---|
| 대상 package | `vllm-rbln 0.11.1` (site-packages) |
| 대상 파일 | `vllm_rbln/model_executor/models/optimum/model_base.py` |
| 대상 함수 | `RBLNOptimumDecoderMixin.preprocess_for_decoder` (약 361–406줄) |
| 삽입 위치 | `select_bucket_size` 호출 직후, `kwargs` 구성 직전 |
| 변경 내용 | `request_nums`와 `padded_batch_size`를 `logger.debug`로 1줄 emit |
| 예상 diff 규모 | **추가 3–5줄, 기존 줄 수정 0** |
| 대안 지점 | `optimum/decoder_only.py:58–65` `RBLNOptimumForCausalLM.forward` — `request_nums`와 `padded_batch_size`가 모두 지역 변수로 존재. 이쪽도 동일 규모 |

**observation-only인 근거**

- 제어 흐름을 바꾸지 않는다. `padded_batch_size` 계산은 그대로 두고 읽기만 한다.
- scheduler, batch selection, KV allocation semantics를 건드리지 않는다. `select_bucket_size`(`utils/optimum/bucket.py:20`)와 `pad_decoder_items`는 수정 대상이 아니다.
- `select_bucket_size`에 `@cache`가 걸려 있으므로 **함수 자체를 wrapping하면 첫 호출만 잡힌다.** 따라서 caller 쪽에서 읽는 방식이 유일하게 올바르며, 이는 동시에 cache 동작을 건드리지 않는다는 뜻이다.
- log level `DEBUG`이므로 기본 실행에서는 출력되지 않는다.

**`patches/` 정책 준수 방식** ([patches/README.md](../../patches/README.md) 7개 항목)

1. 대상 package와 exact version: `vllm-rbln 0.11.1`
2. upstream file path와 적용 전 SHA256을 patch 파일에 기록
3. semantics 무변경 근거: 위 "observation-only인 근거"
4. observation-only 우선 검토 결과: 위 4개 수단 검색 기록([TASK10](TASK10.md))
5. 적용/복구 명령을 patch 파일에 함께 기록
6. version/hash drift 시 fail-loud 중단: 적용 script가 SHA256 불일치 시 비-0 exit
7. run metadata에 patch 적용 여부와 hash를 기록

**대안**

| 대안 | 평가 |
|---|---|
| bucket을 직접 관측하지 않고 `running` 수로 추론 | `vllm:num_requests_running`은 scheduler 관점의 요청 수이고 bucket은 model runner가 그 뒤에 고르는 값이다. 두 값이 항상 같다는 근거가 없으므로 대리 지표로 쓰면 관측과 추론이 섞인다 |
| `VLLM_RBLN_USE_VLLM_MODEL=True` 경로로 전환 | 이 경로에는 `find_decode_batch_bucket`이 있으나 역시 per-step log는 없고, Stage 0–1b가 전부 기본 경로에서 검증됐으므로 substrate를 바꾸는 큰 변경이다 |
| upstream에 관측 추가를 요청 | 시간 척도가 이 연구와 맞지 않는다 |
| Track A를 보류하고 Stage 2(APC)를 먼저 진행 | 가능하다. Stage 2는 bucket 관측을 요구하지 않는다. 결정 3을 미루면서 연구를 진행하는 경로다 |

**권고**

Track A를 진행할 의사가 있다면 승인을 권고한다. 변경 규모가 log 1줄이고, 계산 자체는 이미 실행 경로에 존재하며, hash guard로 drift를 fail-loud로 잡을 수 있다. Track A를 당장 진행하지 않겠다면 **판정을 미루고 Stage 2를 먼저 진행하는 선택**도 합리적이다 — 결정 3은 Stage 2의 gate가 아니다.

권고는 제안일 뿐이며 판정은 사용자가 한다. 승인 전에는 patch를 작성하지도 적용하지도 않는다.

### 결정 2 — Stage 0 대상 model의 download/compile 승인

- 상태: `해소됨` — **판정 완료 (선택지 A 승인, 2026-08-19)**
- 판정 내용: `Qwen/Qwen3-4B`를 Stage 0 대상 model로 선택하고, weight download와 문서화된 파라미터(`--max_seq_len 8192 --batch_size 1 --num_devices 4`)의 optimum-rbln compile, CA25 단일 inference를 승인했다. Compile artifact 경로는 `/home/rebel/continuum-npu/models/`(gitignore 대상)이며, disk 100 GiB·compile wall-clock 2시간의 예산 상한을 함께 정했다. RSD 변경, device reset, site-packages 수정, `patches/` 적용, Stage 1 이후 작업, remote `push`는 계속 승인 범위 밖이다.
- 질문: Stage 0 single inference의 대상 model로 무엇을 선택하고, 해당 model의 weight download와 RBLN compilation을 승인할 것인가?
- 관련 TASK: [TASK02](TASK02.md), [TASK04](TASK04.md), [TASK05](TASK05.md)
- 승인 범위와 판정 기준의 사전 고정: [STAGE0_PREREG.md](STAGE0_PREREG.md)
- 근거 조사: [TASK05](TASK05.md). 조사 시각 2026-08-19 15:59 KST. Model은 실행하지 않았고 weight도 받지 않았다.

**전제 (세 선택지 공통)**: 기본 vLLM 실행 경로(`VLLM_RBLN_USE_VLLM_MODEL=False`)는 model 디렉터리의 `rbln_config.json`을 요구한다. 따라서 어떤 후보를 고르든 Stage 0는 **weight download + optimum-rbln compile** 두 단계를 모두 승인해야 진행된다.

| 항목 | A. `Qwen/Qwen3-4B` (권고) | B. `Qwen/Qwen3Guard-Gen-0.6B` | C. `Qwen/Qwen3.5-0.8B` |
|---|---|---|---|
| `architectures` | `Qwen3ForCausalLM` | `Qwen3ForCausalLM` | `Qwen3_5ForConditionalGeneration` |
| Download 크기 (safetensors / repo 전체) | 7.492 GiB / 7.507 GiB | 1.400 GiB / 1.415 GiB | 1.627 GiB / 1.648 GiB |
| Parameter 수 | 4.02 B (BF16) | 0.75 B | 0.87 B |
| KV bytes/token (파생) | 147,456 B = **144.0 KiB** (`36×8×128×2×2`) | 114,688 B = **112.0 KiB** (`28×8×128×2×2`) | 12,288 B = **12.0 KiB** (`6×2×256×2×2`, full-attn 6 layer만) + sequence당 linear state 약 9.6 MiB(bf16 가정, dtype `UNKNOWN`) |
| Attention 구조 | 36 layer 전부 full attention | 28 layer 전부 full attention | 24 layer 중 full 6 / GatedDeltaNet linear 18 (**hybrid**) |
| vllm-rbln registry 분류 | `_RBLN_GENERATION_MODELS` (text decoder-only) | `_RBLN_GENERATION_MODELS` (text decoder-only) | `_RBLN_MULTIMODAL_MODELS` (vision-language) |
| 지원 근거 등급 | **A** — CLI quick-start, class docstring 2곳, package README에 end-to-end compile command | **B** — architecture는 A와 동일 entry지만, 이 checkpoint id는 Cosmos guardrail의 `base_model_id` 기본값으로만 등장. decoder-only compile 예시 없음 | **C** — docstring 1곳(`RBLNQwen3_5ForCausalLM`). 단, HF checkpoint의 실제 arch는 registry상 multimodal 경로로 해석됨 |
| 문서화된 device 요구 | `num_devices=4` (`--batch_size 1 --max_seq_len 8192`) | 문서 예시 없음 (`UNKNOWN`) | `num_devices=1, device=0` (`kvcache_partition_len 4096, max_seq_len 8192`) |
| 최소 device 수 | `UNKNOWN` (자동 유도 코드 없음) | `UNKNOWN` | `UNKNOWN` |
| `max_position_embeddings` | 40,960 | 32,768 | 262,144 |
| License / gated | apache-2.0 / `False` | apache-2.0 / `False` | apache-2.0 / `False` |
| Stage 2 APC 자동 비활성 대상 | 아님 (`sliding_window: null`, `use_sliding_window: false`) | 아님 (동일) | 아님 (`layer_types`에 `sliding` 없음) |
| Compile 소요시간 / artifact 크기 | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` |
| 주요 미지수·위험 | download 7.5 GiB, device 4개 점유(전 32 ID idle이므로 가용). compile 비용 `UNKNOWN` | compile 예시 부재. safety-classifier tuning이라 생성 출력이 guard 판정 형식 — Stage 0 "valid output" 판정 기준을 따로 정해야 함 | **vision-language checkpoint**이며 text backbone이 hybrid. KV를 갖는 layer가 24개 중 6개뿐이라 KV lifecycle baseline으로 부적합. linear state dtype `UNKNOWN` |

**권고: A. `Qwen/Qwen3-4B`**

이유는 세 가지다. 첫째, 설치된 package에서 **end-to-end compile command가 문서화된 유일한 후보**다 (`optimum-rbln-cli --model-id Qwen/Qwen3-4B -o ./compiled_qwen3 --max_seq_len 8192 --batch_size 1 --num_devices 4`). Stage 0는 bring-up gate이므로 실패 시 원인이 "model 선택"이 아니라 "환경"으로 좁혀지는 후보가 유리하다. 둘째, 36 layer가 전부 full attention이라 KV bytes/token이 단일 산식으로 정의된다. 이 저장소의 연구 대상이 KV lifecycle과 cache attribution이므로 baseline은 KV semantics가 단순해야 한다. 셋째, download 7.5 GiB와 device 4개는 현재 host에서 제약이 아니다 — 32 visible ID가 전부 idle이고 device당 15.7 GiB가 비어 있다.

**권고와 다른 선택 시 고려사항**

- **B를 고르는 경우**: download를 5.4배 줄이지만 KV bytes/token은 144 → 112 KiB로 22%만 줄어든다. 즉 KV 압력 관점의 이득은 작고 절약되는 것은 주로 download/compile 비용이다. 또한 compile 예시가 없어 실패 시 "이 checkpoint가 이 경로에서 검증된 적 있는가"가 `UNKNOWN`으로 남는다. Stage 0 성공 판정 기준에 "생성 출력이 guard 판정 형식임"을 미리 반영해야 한다.
- **C를 고르는 경우**: 이 후보는 소형 text model이 아니라 vision-language model이며 text backbone의 3/4이 KV cache를 갖지 않는다. Stage 0는 통과할 수 있어도 Stage 2 APC characterization과 decoder observation의 baseline으로는 관측 대상이 왜곡된다. hybrid attention을 **연구 대상으로 삼겠다는 별도 결정**이 있을 때만 합리적이다.
- **어느 것도 승인하지 않는 경우**: 검증된 precompiled RBLN artifact path를 제공하면 download/compile 없이 Stage 0를 재개할 수 있다. TASK02의 local 탐색에서는 그런 artifact가 발견되지 않았다.
- **승인 시 함께 정해야 할 것**: `max_seq_len`, `batch_size`, `num_devices`, compile artifact 저장 경로, host disk 예산. compile 소요시간과 artifact 크기는 현재 `UNKNOWN`이므로 첫 compile 자체가 그 값의 측정이 된다.

권고는 제안일 뿐이며 판정은 사용자가 한다.

## 완료된 주요 작업

- Clean-room NPU repository migration 및 source isolation 검증이 초기 repository commit에서 완료됐다. 이는 TASK 체계 도입 전 작업이므로 근거 없이 별도 TASK로 소급 재구성하지 않았다.
- NPU hardware/software 환경, topology, source-resolution 위험, 포팅 준비도를 read-only로 감사했다. 상세 근거는 [NPU 환경](../environment/NPU_ENVIRONMENT.md), [이식 사전 분석](../environment/NPU_PORTING_ANALYSIS.md), [연구 준비도](../environment/NPU_RESEARCH_READINESS.md)에 있다.
- TASK01에서 agent 연구 기록 체계를 구축했다.
- TASK02에서 source isolation을 재검증하고 Stage 0 model gate의 blocker를 최신 환경에서 확인했다.
- TASK03에서 각 작업 종료 시 local `main` commit을 필수 workflow로 도입했다.
- TASK04에서 사용자 결정 대기 절, 선등록·동치 판정 hard rule, hostname `UNKNOWN` 승격으로 연구 workflow 문서를 개정했다.
- TASK05에서 Stage 0 후보 model metadata와 `atom-max8` hardware inventory를 read-only로 조사해 결정 2의 근거 표를 완성했다.
- TASK08에서 optimum-rbln compile 파라미터 공간과 KV accounting을 source로 확정하고 Stage 1b 권고안을 만들었다.
- TASK09에서 Stage 1a serving bring-up을 `PASS` 판정하고 `/metrics` 신호를 감사했다. TASK06의 `num_gpu_blocks` `UNKNOWN`이 해소됐다.
- TASK10에서 multi-bucket artifact로 동시 8 sequence 실행을 확인하고 Stage 1b를 `PASS` 판정했다. decoder bucket 관측이 불가임을 실행 수준에서 확인해 결정 3을 신설했다.
- TASK11에서 prefix cache hit 단위를 inner block 128 token으로 확정하고 APC OFF/ON 통제 방식을 검증했다.
- TASK12에서 결정 3을 집행해 decoder bucket 관측 patch를 적용·검증했다. `patches/` 정책의 첫 실전 적용이다.
- TASK06에서 [STAGE0_PREREG.md](STAGE0_PREREG.md)로 판정 기준을 선등록한 뒤 Stage 0를 실행해 `PASS` 판정했다. `Qwen/Qwen3-4B` revision `1cfa9a72…`를 download(7.507 GiB / 66.8 s)하고 `--batch_size 1 --max_seq_len 8192 --num_devices 4`로 compile(165 s / 9.083 GiB)한 뒤 단일 inference(input 12 token, output 64 token, e2e 0.702 s)를 수행했다.
- TASK07에서 모든 작업 종료 시 GitHub push 여부를 사용자에게 확인하는 workflow를 도입했다.

## 진행 중 또는 BLOCKED인 작업

- Stage 0 single inference: [TASK06](TASK06.md)에서 `PASS`. 더 이상 진행 중이거나 blocked인 항목이 아니다.
- Stage 1a serving bring-up: [TASK09](TASK09.md)에서 `PASS`. 더 이상 진행 중이거나 blocked인 항목이 아니다.
- Stage 1b multi-bucket compile과 동시성 진입: [TASK10](TASK10.md)에서 `PASS`.
- Track A (decoder bucket characterization): 미착수. [TASK12](TASK12.md)에서 관측 경로가 확보됐다. bucket 전이 관측을 위해 요청별 생성 길이를 다르게 하는 격자가 필요하다.
- Stage 2 준비: [TASK11](TASK11.md)에서 hit 단위와 APC 통제 방식을 확정했다. 설계 제약(prefix ≥ 129 token, 조건 간 prefix 오염 차단, APC OFF/ON의 block 입도 confounder 기록)은 해당 TASK에 있다.
- Stage 2 APC OFF/ON characterization: Stage 1 미실행으로 미착수.
- Decoder batch observation: source-level observation point는 확인했으나 per-step runtime metric은 `UNKNOWN`이며 runtime 검증 전이다.

## 핵심 연구 흐름

Clean-room migration 및 환경 감사 → TASK01 연구 기록 체계 → TASK02 Stage 0 사전 검증(`BLOCKED`) → TASK03 작업 종료 commit workflow → TASK04 workflow 문서 개정 → TASK05 후보 model 조사·환경 재-inventory → TASK06 Stage 0 single inference(`PASS`) → TASK07 작업 종료 push 확인 workflow → TASK08 compile 파라미터·KV accounting source 조사 → TASK09 Stage 1a serving bring-up(`PASS`) → TASK10 Stage 1b multi-bucket compile·동시성(`PASS`) → TASK11 prefix cache hit 경계 확정 → TASK12 decoder bucket 관측 patch 적용·검증 → Stage 2 APC OFF/ON characterization → decoder batch observation-only characterization → raw-signal feasibility

Stage 0–2 observation baseline 전에는 scheduler policy, KEEP/OFFLOAD/RECOMPUTE 또는 host/peer KV parking을 구현하지 않는다.

Legacy GPU 연구 문서는 `docs/legacy/TASK25.md`, `TASK27.md`, `TASK29.md`, `TASK31.md`에 있으며 새 NPU TASK와 다른 namespace다. 새 번호는 오직 이 디렉터리의 `TASKNN.md`만 기준으로 계산한다.

## 현재 유지해야 하는 핵심 원칙

- decision accuracy만 최적화하지 않고 mis-selection cost와 regret을 함께 본다.
- requested condition, observed condition, condition reached를 구분한다.
- eviction/release를 recomputation으로 간주하지 않는다.
- cache source를 latency만으로 판정하지 않는다.
- 증거가 부족하면 `PARTIAL`과 `UNKNOWN`을 허용한다.
- GPU threshold와 CUDA semantics를 NPU에 그대로 적용하지 않는다.
- instantaneous pressure만으로 cache survival을 설명하지 않는다.
- observation과 interpretation/hypothesis를 분리하고 모든 run의 provenance를 남긴다.
- 각 작업의 검증된 agent-owned 변경을 local `main`에 commit하고 commit hash를 보고한다.
- 모든 작업 종료 시 GitHub `origin/main` push 여부를 사용자에게 묻고 현재 질문에 명시적으로 승인받은 경우에만 push한다.
- 측정과 판정이 포함된 TASK는 판정 기준·예측·실험 격자를 측정 전에 commit하고(선등록) 사후에 기준을 완화하지 않는다.
- 두 조건의 동치 판정은 고정 밴드가 아니라 중앙 ratio bootstrap CI가 1을 포함하는지와 사전 등록한 CI 폭 상한으로 한다.

## 다음 작업 후보

1. 사용자가 [사용자 결정 대기](#사용자-결정-대기)의 결정 3을 판정한다.
2. Stage 2 repeated-prefix baseline. 설계 제약은 [TASK11](TASK11.md)의 "다음 작업" 절을 따른다. 선등록 후 진행한다.
3. Stage 1 통과 후 APC OFF/ON을 독립 구성한 Stage 2 repeated-prefix baseline.
4. baseline 통과 후 decoder bucket의 observation-only characterization.

이 목록은 권고 순서다. 사용자의 지시 없이 다음 작업을 자동 시작하지 않는다.
