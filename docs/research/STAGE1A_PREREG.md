# Stage 1a 선등록 — 기존 b1 artifact로 serving bring-up과 관측 감사

## 문서 성격

이 문서는 [CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 server를 기동하고 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다. 측정 결과와 판정은 후속 TASK 문서에 기록한다.

## 목적

`vllm serve` 경로 자체를 검증하고, 이후 Stage에서 쓸 수 있는 **관측 신호가 무엇인지 감사**한다. 재compile은 하지 않고 [TASK06](TASK06.md)이 만든 `models/Qwen3-4B-rbln-b1-s8192-d4`를 그대로 쓴다.

## 승인 범위 (사용자 판정, 2026-08-19)

- 기존 `Qwen/Qwen3-4B` weight와 b1 compile artifact 재사용
- `vllm serve` 기동·종료, localhost HTTP 요청
- 로그 상세화를 위한 환경변수 설정. 실행 semantics를 바꾸는 flag는 값과 근거를 기록
- read-only source 조사

범위 밖: 신규 download, 재compile(작업 3에서만), site-packages 수정, `patches/` 적용, RSD 변경, device reset, Stage 2 APC 실험, remote `push`, `RBLN_DEVICES` 설정.

## 예산

- compile과 serving을 동시에 실행하지 않는다. 이 작업에는 compile이 없다.
- server process는 작업 종료 시 반드시 종료하고 종료를 확인한다.
- `/` disk 사용률 80 % 초과 금지.

## 실험 격자

Sweep이 아니다. 단일 server 구성에 대한 고정 관측 시퀀스다.

| 요소 | 고정값 |
|---|---|
| Model 경로 | `/home/rebel/continuum-npu/models/Qwen3-4B-rbln-b1-s8192-d4` |
| Server | `vllm serve <경로> --host 127.0.0.1 --port 8000` |
| `RBLN_DEVICES` | 설정하지 않음 (기본 할당 유지) |
| 환경변수 | `VLLM_LOGGING_LEVEL=DEBUG`만 설정. 실행 semantics를 바꾸는 `VLLM_RBLN_*` flag는 설정하지 않는다 |
| Prompt | `experiments/npu/stage1/prompt.txt` 1개 (아래 원문) |
| Sampling | `temperature=0.0`, `top_p=1.0` (greedy) |
| `max_tokens` | 32 |
| Seed | 20260819 |
| 관측 시퀀스 | `/health` → `/v1/models` → `/metrics`(idle) → 단일 요청 → `/metrics` → streaming 요청 → `/metrics` → 동시 요청 2개 → `/metrics` |

Prompt 원문:

```text
Explain in two sentences what a neural processing unit is.
```

동시 요청 2개는 prompt 뒤에 ` (request 0)` / ` (request 1)`을 붙여 서로 다른 요청으로 만든다. Prefix가 공유되지만 이번 작업에서 prefix cache hit을 판정 대상으로 삼지는 않는다.

## PASS 조건

아래 5개를 **전부** 충족할 때만 Stage 1a를 `PASS`로 판정한다.

1. Server가 기존 b1 artifact로 정상 기동하고 resolved config가 기록된다. `/health`가 200이고 `/v1/models`가 served model id를 반환한다.
2. OpenAI-compatible endpoint(`POST /v1/completions`)로 요청 1개가 200으로 성공하고 유의미한 텍스트를 반환한다. "유의미"의 조작적 정의는 [STAGE0_PREREG.md](STAGE0_PREREG.md) 조건 4와 **동일**하다 — 빈 문자열·공백 전용이 아니고, output token ≥ 1이며, 최소 1개의 일반 단어 문자(`[A-Za-z]`)를 포함한다. 문법성·사실성·지시 준수는 판정 대상이 아니다.
3. `/metrics`가 200으로 응답하고, 노출된 metric 이름 전체 목록을 기록한다.
4. NPU 실행 증거를 관측한다. 조작적 정의는 [STAGE0_PREREG.md](STAGE0_PREREG.md) 조건 6과 **동일** — memory 증가, utilization 증가, 또는 `rbln-smi` context에 server process 출현 중 하나 이상. memory와 context를 1차 증거로 삼고 utilization은 보조로 쓴다 (폴링 주기 한계를 사전 인정한다).
5. Server가 정상 종료되고 `rbln-smi`에서 사용 device memory가 `0.0B`로 복귀하며 해당 process의 context가 사라진다.

### FAIL / PARTIAL 처리 규칙 (측정 전 고정)

| 상황 | 판정 |
|---|---|
| server 기동 실패 | `FAILED`. 기동 로그 전문 보존 |
| 기동 성공, 요청 실패 | `FAILED`. server 로그와 응답 본문 보존 |
| 요청 성공, `/metrics` 접근 실패 | `PARTIAL`. 조건 3 미충족을 명시 |
| 요청 성공, NPU 증거 미관측 | `PARTIAL`. "실행됨"과 "NPU에서 실행됨"을 구분 |
| 종료 후 device memory가 `0.0B`로 복귀하지 않음 | `PARTIAL`. 잔존 context를 기록하고 사용자에게 보고 |
| source isolation 실패 | `INVALID` |

## 관측 감사 항목 (PASS 조건 아님, 필수 기록)

판정에 쓰지 않지만 반드시 기록한다. 이후 Stage의 신호 채택 여부가 여기에 달려 있다.

1. **`/metrics` KV·큐·prefix cache 신호**: KV cache usage, running/waiting 요청 수, prefix cache query/hit에 해당하는 항목이 있는가. 있으면 이름·단위·population을 기록하고, **단일 요청 전후로 값이 실제로 움직이는지** 확인한다 (신호 채택 전 의미론 검증의 1단계). 이름이 존재해도 값이 움직이지 않으면 "노출되지만 미검증"으로 분류한다.
2. **streaming**: `stream:true`가 동작하는지, 첫 content chunk까지의 wall-clock을 분리 관측할 수 있는지. 1회 관측이며 통계적 주장을 하지 않는다. 이 값은 TTFT의 **상한 근사**이지 server 내부 TTFT가 아니다.
3. **동시 요청 2개의 거동**: `batch_size=1` artifact에서 두 번째 요청이 대기하는지, 거부되는지, 오류인지. **어떤 결과든 관찰로만 기록한다.** 이 artifact의 한계 확인이 목적이며 특정 결과를 기대하지 않는다.

### 동시성 해석의 사전 제약

wall-clock overlap은 **동시 실행의 증거가 아니다**. 두 요청의 구간이 겹쳐도 server가 순차 처리하면서 두 번째를 큐에 세운 것일 수 있다. 이번 작업에서는 overlap을 관찰값으로만 기록하고, "동시에 RUNNING이었다"는 주장은 하지 않는다. 그 판정은 작업 3(Stage 1b)의 PASS 조건이며 log 또는 metric 근거를 요구한다.

## 예측 (측정 전 기록, 판정 기준 아님)

- [TASK08](TASK08.md)의 유도에 따라 resolved `max_num_seqs = 1`, EngineCore `num_gpu_blocks = 65`, `"GPU KV cache size: 8,320 tokens"`가 나올 것이다.
- `batch_size=1`이므로 동시 요청 2개는 **순차 처리**될 것으로 예측한다. 거부나 오류보다는 큐 대기가 유력하다. 빗나가도 기준을 조정하지 않는다.
- `/metrics`에는 vLLM 표준 항목(`vllm:num_requests_running`, `vllm:num_requests_waiting`, `vllm:kv_cache_usage_perc` 계열, `vllm:prefix_cache_queries`/`hits` 계열)이 노출될 것으로 예측하나, RBLN 전용 scheduler·KV manager가 이를 실제로 채우는지는 `UNKNOWN`이며 이번 감사가 그 확인이다.
- per-step decoder bucket은 노출되지 않을 것으로 예측한다 ([TASK08](TASK08.md) 핵심 발견 6).

## 필수 측정 항목

- server 기동 wall-clock, 기동 로그의 resolved config 전문
- **frontend와 EngineCore 각각의 `num_gpu_blocks`** ([TASK08](TASK08.md)이 남긴 2배 anomaly 판별)
- `/metrics` 스냅샷 4회(idle / 단일 요청 후 / streaming 후 / 동시 요청 후) 전문
- 각 요청의 status, usage token 수, e2e latency, 응답 텍스트
- streaming 첫 chunk까지의 시간과 chunk 수
- 동시 요청 각각의 시작·종료 wall-clock offset과 pairwise overlap
- `rbln-smi`: 기동 전 / 기동 후 / 요청 중 폴링 / 종료 후
- provenance: git commit과 dirty 여부, package version, model 경로, hostname, 사용 device ID, `VLLM_RBLN*` 환경변수

Latency는 모두 1회 관측값이다. 평균·분산·비교 등 통계적 주장을 하지 않는다.

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage1/<timestamp>-stage1a-b1-serving`

1. 기동 전 `rbln-smi` 캡처, port 8000이 비어 있는지 확인.
2. Server 기동 (별도 shell, 로그를 `<RUN>/server.log`로):

   ```bash
   VLLM_LOGGING_LEVEL=DEBUG vllm serve \
     /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b1-s8192-d4 \
     --host 127.0.0.1 --port 8000
   ```

3. `/health`가 200이 될 때까지 대기하며 기동 wall-clock 기록. 별도 shell에서 `rbln-smi` 1초 폴링 시작.
4. 관측 시퀀스 실행:

   ```bash
   experiments/npu/launch/run_isolated_python.sh \
     experiments/npu/stage1/serving_probe.py \
     --base-url http://127.0.0.1:8000 \
     --prompt-file /home/rebel/continuum-npu/experiments/npu/stage1/prompt.txt \
     --max-tokens 32 --seed 20260819 --concurrency 2 \
     --output-dir <절대경로>/<RUN>/probe
   ```

   경로는 모두 절대 경로로 넘긴다 (격리 launcher가 cwd를 바꾸므로 — [TASK06](TASK06.md) 실패 기록).

5. Server를 `SIGTERM`으로 종료하고 process 부재를 확인한다. 종료 후 `rbln-smi`를 캡처해 device memory 복귀와 context 소멸을 확인한다.
6. PASS 조건 5개와 감사 항목 3개를 대조해 판정한다.

## 관련 문서

- [TASK06](TASK06.md) — Stage 0 `PASS`, b1 artifact의 출처
- [TASK08](TASK08.md) — compile 파라미터 공간과 KV accounting, 예측의 근거
- [STAGE0_PREREG.md](STAGE0_PREREG.md) — 조건 4·6의 조작적 정의 원본
- [INDEX.md](INDEX.md)
