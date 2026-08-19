# 선등록 — prefix cache hit 경계와 KV block 의미론 확정

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다. 결과와 판정은 후속 TASK 문서에 기록한다.

## 목적

[TASK09](TASK09.md)·[TASK10](TASK10.md)에서 반복 관측된 `vllm:prefix_cache_hits_total = 0`의 원인을 확정하고, inner block(128 token)과 outer block(8,192 token)의 실효 의미론을 판정한다. 이 결과가 Stage 2 repeated-prefix baseline 설계를 결정한다.

## 승인 범위 (사용자 판정, 2026-08-19)

- 기존 b8 artifact(`models/Qwen3-4B-rbln-b8-s8192-d4-mb`)로의 serving 기동·종료, localhost 요청
- `enable_prefix_caching` 명시 지정(True/False)과 `VLLM_RBLN_SUB_BLOCK_CACHE` 지정을 실험 arm으로 사용. 지정값을 requested/observed로 기록
- read-only source 조사

범위 밖: 재compile(불필요), 신규 model download, RSD 변경, site-packages 수정, `patches/` 적용(이 작업에서는 하지 않는다), Stage 2 본 실험, remote push 자동 수행.

Server process는 작업 종료 시 **PID를 특정해** 종료하고 종료를 확인한다 ([TASK10](TASK10.md)의 `pgrep -f` 오탐 교훈).

## Source 조사 결과 (측정 전, 예측의 근거)

### hit 판정 경로 전체

```
RBLNOptimumScheduler
  └─ RBLNKVCacheManager.get_computed_blocks           (vllm KVCacheManager 상속, 미override)
       ├─ max_cache_hit_length = request.num_tokens - 1        vllm/v1/core/kv_cache_manager.py:219
       ├─ RBLNKVCacheCoordinator.find_longest_cache_hit        (UnitaryKVCacheCoordinator 상속)
       │    └─ alignment_tokens = self.block_size              vllm/v1/core/kv_cache_coordinator.py:385
       │    └─ FullAttentionManager.find_longest_cache_hit     vllm/v1/core/single_type_kv_cache_manager.py:483
       │         ├─ max_num_blocks = max_length // block_size
       │         └─ block_pool.get_cached_block(...)           vllm/v1/core/block_pool.py:203
       │              └─ RBLNBlockHashToBlockMap.get_one_block vllm_rbln/v1/core/optimum_block_pool.py:29
       └─ prefix_cache_stats.record(num_tokens=request.num_tokens,
                                    num_hits=num_new_computed_tokens)
                                                               vllm/v1/core/kv_cache_manager.py:226-232
```

### 확정된 사실

1. **`queries`의 단위는 요청의 prompt token 수다** (`num_tokens=request.num_tokens`). [TASK09](TASK09.md)·[TASK10](TASK10.md)의 실측(요청당 12/17/20 증가)과 일치한다.
2. **`hits`의 단위는 token 수다** (`num_hits=num_new_computed_tokens`).
3. **hash 단위는 inner block이다.** `optimum_scheduler.py:208-209`에서 `hash_block_size`가 `None`이면 `block_size`(= `cache_config.block_size` = `prefill_chunk_size` = **128**)가 된다.
4. **정렬 단위도 inner block이다.** `UnitaryKVCacheCoordinator`가 `alignment_tokens = self.block_size`(128)를 넘기므로, `find_longest_cache_hit`의 정렬 while 루프는 `block_size == alignment_tokens`로 즉시 건너뛰어진다. **outer block 8,192은 hit 정렬 단위가 아니다.**
5. **hit 가능 최소 길이가 존재한다.** `max_num_blocks = (num_tokens - 1) // 128`이므로 prompt token이 **129개 미만이면 조회 루프가 한 번도 돌지 않아 hit이 구조적으로 0이다.** [TASK09](TASK09.md)의 12·17 token, [TASK10](TASK10.md)의 20 token prompt는 전부 이 조건에 걸린다.
6. **RBLN이 hit 조건을 추가로 좁힌다.** `RBLNBlockHashToBlockMap.get_one_block`(`optimum_block_pool.py:29-47`)은 upstream을 override해, 해당 hash를 가진 block이 **정확히 1개면 `None`을 반환**한다(주석: "This block is allocated by the current request itself"). 2개 이상일 때만 **뒤에서 두 번째** block을 돌려준다.
7. **outer block은 두 번째 층이다.** `RBLNPrefixKVCacheManager`(`optimum_prefix_cache_manager.py`)의 `CacheSearchManager._try_match_request`가 vLLM이 찾아준 inner block 목록을 `block_ratio = ob_size // ib_size = 64`씩 끊어 outer block에 사상한다. **1층이 못 찾은 것을 2층이 찾을 수는 없다.**
8. **2층에 전용 DEBUG 로그가 있다**: `[PFX] [CACHE-HIT]`(OB/IB 개수와 목록)와 `[PFX] [CACHE-PARTIAL]`. [TASK10](TASK10.md)의 로그에는 이 두 줄이 없었다.
9. `VLLM_RBLN_SUB_BLOCK_CACHE`는 `rbln_model_runner.py`/`rbln_scheduler.py`에서만 읽히므로 기본(optimum) 경로에서는 무효다 ([TASK08](TASK08.md) 재확인).

## 경쟁 가설

관측된 `hits = 0`을 설명하는 두 가지가 있고 서로 다른 예측을 낸다.

- **H1 (길이 문턱)**: prompt가 129 token 미만이라 조회 루프가 돌지 않았다. 근거는 사실 5.
- **H2 (중복 block 요구)**: `get_one_block`이 hash당 block이 1개면 `None`을 반환하므로, 어떤 prompt를 두 번째로 보낼 때도 hit이 나지 않는다. 근거는 사실 6.

H1은 "129 token 이상이면 2번째 요청부터 hit"을 예측하고, H2는 "129 token 이상이어도 2번째 요청은 hit 0이고 3번째부터 hit"(또는 영원히 0)을 예측한다. 이번 격자가 둘을 구별한다.

## 실험 격자

Server 구성 3개(arm)를 순차로 띄우고, 각 구성에서 아래 길이 × 요청 arm을 **순차(동시성 1)** 로 보낸다. 요청을 순차로 보내는 이유는 counter 증분을 요청 1개에 귀속시키기 위해서다.

### Server 구성 arm

| tag | 설정 | 목적 |
|---|---|---|
| `apc_on` | `--enable-prefix-caching` 명시 | 주 실험 |
| `apc_off` | `--no-enable-prefix-caching` 명시 | Stage 2 통제 방식의 사전 검증 |
| `subblock_off` | `--enable-prefix-caching` + `VLLM_RBLN_SUB_BLOCK_CACHE=false` | 사실 9의 falsification |

`apc_off`와 `subblock_off`는 길이 1,000 하나만 돌린다(확인 목적). `apc_on`은 전 길이를 돌린다.

### Prompt 길이 (tokenizer 실측으로 고정)

`experiments/npu/stage2/prefix_prompts.json`에 고정했다. 각 값은 artifact의 tokenizer로 **정확히** 맞춘 token 수다.

| 목표 | 실측 token | inner block 경계 대비 |
|---|---|---|
| 100 | 100 | `(100-1)//128 = 0` → 경계 아래 |
| 130 | 130 | `(130-1)//128 = 1` → 경계 막 넘음 |
| 260 | 260 | `(260-1)//128 = 2` |
| 1000 | 1000 | `(1000-1)//128 = 7` |
| 4000 | 4000 | `(4000-1)//128 = 31` |

`max_seq_len` 8,192 이내이며, 4,000 token에서도 outer block(8,192) 1개를 채우지 못한다. 이는 의도한 것이다 — 사실 4에 따르면 outer block은 정렬 단위가 아니므로, 4,000에서 hit이 나면 outer 경계 가설이 반증된다.

### 요청 arm

- **`identical`**: 같은 prompt를 **5회** 반복. base는 `prompts_a`.
- **`shared_prefix`**: 같은 prefix + 서로 다른 8-token suffix 5개. base는 `prompts_b`.

`prompts_a`와 `prompts_b`는 **첫 token부터 다르다**(`PFXBASEA` / `PFXBASEB`). 두 arm이 서로의 cache를 물려받지 않도록 하기 위해서다. Cache를 중간에 reset하지 않는다(reset은 승인 범위 밖이며 semantics 변경이다).

### 고정 파라미터

| 항목 | 값 |
|---|---|
| Model | `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음) |
| `max_tokens` | 8 (판정이 counter이므로 생성은 짧게) |
| Sampling | `temperature=0.0`, `top_p=1.0` |
| Seed | 20260819 |
| 동시성 | 1 (순차) |
| `RBLN_DEVICES` | 설정하지 않음 |
| 로그 | `VLLM_LOGGING_LEVEL=DEBUG` |

## 판정 기준

**counter만 사용한다. latency는 판정에 쓰지 않는다** — cache source를 latency로 판정하지 않는다는 저장소 원칙에 따른다. latency는 보조 기록이다.

각 (구성 × 길이 × arm × 반복 index)에서 요청 전후의 다음 증분을 기록한다.

- `vllm:prefix_cache_hits_total`
- `vllm:prompt_tokens_cached_total`
- `vllm:prefix_cache_queries_total`

판정 규칙:

1. **hit 경계 확정**: `hits > 0`이 처음 나타나는 (길이, 반복 index)를 찾는다. 그 값이 **128의 배수**이고 `≤ floor((prompt_tokens - 1) / 128) × 128`이면 hit 단위가 inner block(128)임을 확정한다.
2. **H1 vs H2 판별**:
   - 길이 ≥ 130에서 **반복 index 1**(두 번째 요청)에 `hits > 0` → **H1 채택, H2 기각**
   - 길이 ≥ 130에서 index 1은 0인데 index 2 이후 `hits > 0` → **H2 채택**
   - 전 길이·전 index에서 `hits = 0` → 둘 다로는 설명이 끝나지 않음. `PARTIAL`로 기록하고 무엇이 배제됐는지 남긴다
3. **outer block 가설 기각**: 4,000 token(< 8,192)에서 `hits > 0`이면 outer block 8,192가 hit 단위라는 가설은 기각된다.
4. **APC 통제 검증**: `apc_off`에서 `queries`·`hits` 증분이 0이고 `[PFX]` 로그가 없으면, Stage 2의 OFF/ON 통제가 `--no-enable-prefix-caching`으로 성립한다고 판정한다.
5. **사실 9 falsification**: `subblock_off`의 결과가 `apc_on`의 같은 길이와 **동일한 hit 패턴**이면 `VLLM_RBLN_SUB_BLOCK_CACHE`가 기본 경로에서 무효라는 [TASK08](TASK08.md)의 주장이 유지된다. 다르면 그 주장을 정정한다.

`prompt_tokens_cached_total`은 [TASK09](TASK09.md)에서 "노출되나 미검증"이었다. 이번에 값이 움직이면 채택 가능으로 승격하고, 움직이지 않으면 미검증을 유지한다.

### FAIL / PARTIAL 처리 규칙 (측정 전 고정)

| 상황 | 판정 |
|---|---|
| server 기동 실패 | `FAILED`. 로그 보존 |
| 요청 실패(non-200) | `FAILED`. 응답 본문 보존 |
| 전 조건에서 `hits = 0` | `PARTIAL`. H1·H2 중 무엇이 배제되고 무엇이 남는지 기록 |
| 관측된 hit이 128의 배수가 아님 | `PARTIAL`. 실측값과 산식의 불일치를 기록하고 hit 단위를 `UNKNOWN`으로 남김 |
| 종료 후 device memory 미복귀 | `PARTIAL`. 잔존 context 기록 후 보고 |

## 예측 (측정 전 기록, 판정 기준 아님)

| # | 예측 | 근거 |
|---|---|---|
| 1 | 길이 100은 전 반복에서 `hits = 0` | 사실 5 (`(100-1)//128 = 0`) |
| 2 | `queries` 증분은 매 요청 prompt token 수와 정확히 일치 | 사실 1 |
| 3 | 길이 130에서 hit이 나면 그 값은 **128** | 사실 3·4 (`(130-1)//128 = 1` block) |
| 4 | 길이 260 → 256, 1,000 → 896, 4,000 → 3,968이 hit 상한 | `floor((n-1)/128) × 128` |
| 5 | 4,000 token에서 hit이 나타난다 (outer 8,192 가설 기각) | 사실 4 |
| 6 | `apc_off`에서 `queries`·`hits` 모두 0 | `get_computed_blocks`의 `enable_caching` early return |
| 7 | `subblock_off`는 `apc_on`과 동일 | 사실 9 |
| 8 | **H2가 binding이라 index 1에서는 hit이 0이고 index 2부터 나타난다** | 사실 6. 다만 free된 block의 hash 등록 상태에 따라 달라질 수 있어 확신도가 낮다 |
| 9 | `shared_prefix` arm의 hit 상한은 공유 prefix 길이에서 결정된다 | suffix는 prefix 뒤에 오므로 앞쪽 block hash는 동일 |

예측 8은 다른 예측보다 불확실하다. 명시적으로 기록해 사후 합리화를 막는다.

## 필수 측정 항목

- 각 요청의 status, `usage.prompt_tokens`, `usage.prompt_tokens_details`, e2e latency(보조)
- 각 요청 전후의 counter 증분 6종과 요청 후 `kv_cache_usage_perc`
- server 로그의 `[PFX] [CACHE-HIT]` / `[PFX] [CACHE-PARTIAL]` 출현 여부와 내용
- 각 구성의 resolved config(`enable_prefix_caching`, `block_size`, EngineCore `num_gpu_blocks`, `GPU KV cache size`)
- `rbln-smi`: 기동 전 / 기동 후 / 종료 후
- provenance: git commit과 dirty 여부, package version, model 경로, hostname, 환경변수

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-prefix-boundary`

각 구성 arm마다:

1. `rbln-smi`와 port 8000 확인
2. server 기동, `/health` 200까지 대기
3. probe 실행 (경로는 절대 경로 — 격리 launcher가 cwd를 바꾼다)

   ```bash
   env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
     experiments/npu/stage2/prefix_cache_probe.py \
     --base-url http://127.0.0.1:8000 \
     --prompts-file /home/rebel/continuum-npu/experiments/npu/stage2/prefix_prompts.json \
     --lengths 100,130,260,1000,4000 --repeats 5 \
     --max-tokens 8 --seed 20260819 --tag apc_on \
     --output-dir <절대경로>/<RUN>/probe
   ```

4. server 로그에서 `[PFX]` 검색
5. PID를 특정해 `SIGTERM`, 종료·port 해제·device memory 복귀 확인

구성 순서: `apc_on` → `apc_off` → `subblock_off`.

## 관련 문서

- [TASK08](TASK08.md) — KV accounting과 `VLLM_RBLN_SUB_BLOCK_CACHE` 무효 주장의 출처
- [TASK09](TASK09.md) — `queries` 단위 token 확인, `hits` 미검증 분류
- [TASK10](TASK10.md) — b8에서도 hit 0 재현, `[PFX]` 로그 부재
- [STAGE1B_PREREG.md](STAGE1B_PREREG.md) — 종료 확인 절차의 선례
