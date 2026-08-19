# Stage 1b 선등록 — multi-bucket compile과 동시성 진입, decoder bucket 관측 판정

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 compile과 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다. 결과와 판정은 후속 TASK 문서에 기록한다.

## 목적

동시 sequence가 실제로 도는 상태를 만들고, decoder bucket 선택이 runtime에서 관측 가능한지 판정한다. 이것이 Track A(bucket characterization) 진입 gate다.

## 승인 범위 (사용자 판정, 2026-08-19)

- 기존 `Qwen/Qwen3-4B` weight 재사용 (revision `1cfa9a7208912126459214e8b04321603b3df60c`, 재download 없음)
- **추가 compile 최대 2회** — 본 compile 1회 + 실패 시 진단 재시도 1회. 아래 격자 안에서만.
- `vllm serve` 기동·종료, localhost HTTP 요청
- 로그 상세화 환경변수. 실행 semantics를 바꾸는 flag는 값과 근거를 기록
- read-only source 조사

범위 밖: 신규 model download, site-packages 수정, `patches/` **적용**(조사·제안까지만), RSD 변경, device reset, Stage 2 APC 실험, remote `push`, `RBLN_DEVICES` 설정.

## 예산

| 항목 | 상한 | 초과 시 |
|---|---|---|
| compile 1회 wall-clock | 30분 | process 중단, 로그 보존, `BLOCKED` |
| `models/` 누적 | 80 GiB | 중단, 보고 |
| `/` disk 사용률 | 80 % | 중단, 보고 |
| compile 횟수 | 2회 (본 1 + 진단 재시도 1) | 중단, 보고 |

**compile과 serving을 동시에 실행하지 않는다** ([TASK06](TASK06.md)의 compile host peak RSS 33.2 GiB 근거). Server process는 작업 종료 시 반드시 종료하고 종료를 확인한다.

## 실험 격자

### Compile (1회)

[TASK08](TASK08.md)의 권고안을 그대로 쓴다.

```bash
timeout 1800 optimum-rbln-cli \
  --model-id Qwen/Qwen3-4B \
  --output-dir /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb \
  --batch_size 8 --decoder_batch_sizes 1,2,4,8 \
  --max_seq_len 8192 --num_devices 4
```

`--decoder_batch_sizes` 다단 지정이 실패하면 **파라미터를 바꿔 재시도하지 않고** 실패 증거를 기록한 뒤, 진단 재시도 1회로 `--batch_size 8`만 준 단일 bucket compile을 수행한다. 그 경우 "bucket 다단화가 별도 결정이었다"는 사실 자체를 결과로 기록한다.

### Serving 동시성

| 요소 | 고정값 |
|---|---|
| Server | `vllm serve <새 artifact> --host 127.0.0.1 --port 8000` |
| 환경변수 | `VLLM_LOGGING_LEVEL=DEBUG`만 설정 |
| `RBLN_DEVICES` | 설정하지 않음 |
| Prompt | `experiments/npu/stage1/prompt.txt` (Stage 1a와 동일) |
| Sampling | `temperature=0.0`, `top_p=1.0` (greedy) |
| `max_tokens` | 256 (Stage 1a의 32보다 길게 — 짧은 요청은 gauge 표집 창이 너무 좁았다) |
| Seed | 20260819 |
| 동시성 수준 | 1 → 2 → 4 → 8, 각 수준마다 별도로 실행 |
| `/metrics` 표집 | 각 수준 동안 50 ms 주기 in-flight 폴링, metric 이름 **정확 일치** |

각 요청은 prompt 뒤에 ` (level N req i)`를 붙여 구분한다.

## PASS 조건

아래 3개를 **전부** 충족할 때만 Stage 1b를 `PASS`로 판정한다.

1. **compile된 `batch_size`만큼의 sequence가 동시에 RUNNING 상태로 관측된다.** 즉 동시성 8 수준에서 `vllm:num_requests_running`의 in-flight 최대값이 **8**에 도달하거나, server 주기 로그에 `Running: 8 reqs`가 기록된다. **"요청이 다 성공함"은 불충족이다** — 순차 처리와 구분되어야 한다.
2. resolved config의 `max_num_seqs`, `num_gpu_blocks`(frontend/EngineCore 각각), `"GPU KV cache size"`가 기록되고, b1 대비 변한 방향이 아래 [TASK08](TASK08.md) 예측표와 대조된다. **불일치도 결과이며 그 자체로 조건 위반은 아니다** — 대조와 기록이 조건이다.
3. NPU 실행 증거와 정상 종료. 조작적 정의는 [STAGE1A_PREREG.md](STAGE1A_PREREG.md) 조건 4·5와 동일하다 (memory·context 1차, utilization 보조 / 종료 후 device memory `0.0B` 복귀와 context 소멸).

### FAIL / PARTIAL 처리 규칙 (측정 전 고정)

| 상황 | 판정 |
|---|---|
| 승인 파라미터로 compile 실패 (진단 재시도 포함) | `FAILED`. compile 로그 전문 보존 |
| compile 성공, server 기동 실패 | `FAILED`. compile cost 측정값은 유효 기록으로 보존 |
| 기동 성공, 동시성 8에서 running이 8에 도달하지 못함 | `PARTIAL`. 도달한 최대 running 값과 그때의 waiting을 기록하고 원인 가설을 분리 기술 |
| 요청 성공, NPU 증거 미관측 | `PARTIAL` |
| 종료 후 device memory 미복귀 | `PARTIAL`. 잔존 context 기록 후 사용자 보고 |
| compile 예산 또는 disk 예산 초과 | `BLOCKED`. INDEX "사용자 결정 대기" 항목 개설 |

## 사전 예측 ([TASK08](TASK08.md) 유도, 판정 기준 아님)

| 항목 | 예측값 | 산식 |
|---|---|---|
| `rbln_config.kvcache_num_blocks` | 8 | `num_full_blocks = (8192//8192) × 8` |
| `rbln_config.decoder_batch_sizes` | `[8, 4, 2, 1]` | 내림차순 정렬 |
| compiled 파일 | `prefill.rbln` + `decoder_batch_{1,2,4,8}.rbln` | `expected_compiled_model_names` |
| KV tensor shape | `[8, 8, 8192, 128]` | `[num_blocks, kv_heads, block_size, head_dim]` |
| KV 총량 / device당 | 9.0 GiB / 2.25 GiB | 72 tensor × 128 MiB ÷ 4 |
| device 점유 | 약 4.12 GiB/device | weight 1.873 + KV 2.25 |
| vLLM `max_num_seqs` | 8 | `from_optimum.py:92` |
| EngineCore `num_gpu_blocks` | 513 | `8 × 64 + 1` |
| frontend `num_gpu_blocks` | 1026 | EngineCore 값의 2배 ([TASK09](TASK09.md)) |
| `"GPU KV cache size"` | 65,664 token | `(513/64) × 8192` |
| `kv_cache_usage_perc` 해상도 | 1/512 | 분모 = `num_gpu_blocks - 1` |

compile wall-clock과 artifact 크기는 예측하지 않는다 (`UNKNOWN`). Stage 0의 165 s / 9.083 GiB 대비 **batch·bucket 수에 어떻게 스케일하는지가 이번 compile의 측정값**이다.

동시성 거동 예측: `batch_size=8`이므로 동시성 8까지 running이 선형으로 증가할 것이다. 빗나가도 기준을 조정하지 않는다.

## 핵심 산출 — decoder bucket 관측 판정

각 동시성 수준에서 per-step `(실제 요청 수, 선택된 bucket)`을 **기존 수단만으로** 관측할 수 있는지 판정한다. 기존 수단의 범위를 측정 전에 다음으로 한정한다.

1. `VLLM_LOGGING_LEVEL=DEBUG` server 로그 전문 검색
2. `/metrics` 전체 항목
3. `VLLM_RBLN_METRICS=1`로 얻는 `PerformanceTracker` 출력 (실행 semantics를 바꾸지 않는 관측 flag이며, 켤 경우 그 사실과 근거를 기록한다)
4. 그 밖의 read-only 경로 (기동 시 출력되는 config dump 등)

판정 규칙:

- **관측 가능**: 위 수단 중 하나에서 per-step 값이 확인되면 경로와 예시 값을 기록한다. Track A는 patch 없이 진행 가능하다.
- **관측 불가**: 그 사실을 근거(어떤 수단을 어떻게 검색했고 무엇이 없었는지)와 함께 기록하고, [INDEX](INDEX.md) "사용자 결정 대기"에 **결정 3 — decoder bucket 관측용 hash-guarded observation-only patch 승인**을 신설한다. 항목에는 patch 대상 파일·함수, 예상 diff 규모, observation-only임의 근거, `patches/` 정책 준수 방식, 대안을 담는다. **patch를 적용하지 않는다.**

[TASK08](TASK08.md)의 사전 예측은 "관측 불가"다. 예측이 맞더라도 위 4개 수단을 실제로 검색한 증거를 남긴다.

## 필수 측정 항목

- compile: wall-clock, artifact 총 크기와 파일별 크기, `rbln_config.json` 주요 key, exit code
- Stage 0 대비 compile cost 스케일 (시간 배수, 크기 배수)
- serving: 기동 wall-clock, frontend/EngineCore 각각의 `num_gpu_blocks`, `max_num_seqs`, `"GPU KV cache size"`, `enable_prefix_caching`
- 각 동시성 수준: 요청별 status·start/end offset·usage, `num_requests_running`/`waiting`/`kv_cache_usage_perc`의 in-flight 최대값과 관측된 distinct 값 집합, counter 증분
- `rbln-smi`: compile 전 / 기동 전 / 기동 후 / 요청 중 폴링 / 종료 후
- bucket 관측 판정의 근거 (검색한 수단과 결과)
- provenance: git commit과 dirty 여부, package version, model revision, hostname, 사용 device ID, 환경변수

모든 latency는 1회 관측값이다. 통계적 주장을 하지 않는다.

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage1/<timestamp>-stage1b-b8-multibucket`

1. compile 전 `rbln-smi`, `df -h /`, `du -sh models/` 캡처. server가 떠 있지 않음을 확인.
2. compile 실행 (`timeout 1800`, `/usr/bin/time -v`, 로그를 `<RUN>/compile/compile.log`로).
3. compile 후 artifact 크기와 `rbln_config.json`을 기록. `df`/`du` 재확인.
4. server 기동 후 `/health` 200까지 대기. 별도 shell에서 `rbln-smi` 1초 폴링 시작.
5. 동시성 sweep 실행:

   ```bash
   env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
     experiments/npu/stage1/concurrency_probe.py \
     --base-url http://127.0.0.1:8000 \
     --prompt-file /home/rebel/continuum-npu/experiments/npu/stage1/prompt.txt \
     --max-tokens 256 --seed 20260819 --levels 1,2,4,8 \
     --output-dir <절대경로>/<RUN>/probe
   ```

   경로는 모두 절대 경로로 넘긴다 (격리 launcher가 cwd를 바꾼다).

6. bucket 관측 판정을 위해 위 4개 수단을 검색한다.
7. Server를 `SIGTERM`으로 종료(PID를 `pgrep`으로 특정)하고 종료·해제를 확인한다.
8. PASS 조건 3개와 핵심 산출을 대조해 판정한다.

## 관련 문서

- [TASK06](TASK06.md) — Stage 0 `PASS`, b1 artifact와 compile cost 기준선
- [TASK08](TASK08.md) — compile 파라미터 공간, KV accounting, 권고안과 예측의 근거
- [TASK09](TASK09.md) — Stage 1a `PASS`, 관측 신호 감사 결과
- [STAGE1A_PREREG.md](STAGE1A_PREREG.md) — 조건 3의 조작적 정의 원본
