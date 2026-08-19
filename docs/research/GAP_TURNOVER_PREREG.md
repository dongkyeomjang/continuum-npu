# 선등록 — prefix-cache block 생존/eviction 파일럿 (NPU GapTurnover 첫 실측)

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다. 결과와 판정은 후속 TASK 문서에 기록한다.

## 연구 질문과 가설

**RQ**: tool gap을 모사한 구간 동안 배경 할당이 누적될 때, 완료된 요청의 cached prefix block은 언제 밀려나는가?

**H (source 조사로 정제)**: 아래 "Source 조사 결과"에서 확정한 대로, **binding resource는 token 총량이 아니라 outer block 개수(`num_ob = 8`)** 이고 eviction은 **inactive mapping에 대한 FIFO**다. 따라서 target의 outer block은 **가장 먼저 할당됐으므로 가장 먼저 evict**되며, 배경 요청이 free outer block을 소진하는 시점에 생존이 끊긴다.

## 승인 범위 (사용자 판정, 2026-08-19)

b8 artifact serving 기동·종료(횟수 제한 없음), localhost 요청, `VLLM_LOGGING_LEVEL=DEBUG` + `VLLM_RBLN_METRICS=1`, `src/continuum/workload/paired.py` 유틸 사용.

범위 밖: 재compile, 신규 download, patch 추가·수정, APC OFF 실험(이번 배치는 전부 `enable_prefix_caching=True`), RSD 변경, remote push 자동 수행.

Server는 매 lifecycle 종료 시 **PID를 특정해** 확인한다.

## Substrate 상태 (provenance 필수)

`vllm-rbln 0.11.1`은 [TASK12](TASK12.md)의 observation-only patch가 적용된 상태여야 한다. 측정 전 `bash patches/vllm_rbln-0.11.1/apply.sh status`가 `patched`(SHA256 `70942d16…`)가 아니면 측정을 시작하지 않는다. 출력을 artifact에 남긴다.

## Source 조사 결과 (측정 전, 예측의 근거)

### 두 층의 pool과 서로 다른 eviction 정책

| 층 | 자료구조 | 단위 | b8 artifact에서의 크기 | 정책 |
|---|---|---|---|---|
| 1 (vLLM) | `FreeKVCacheBlockQueue` (`vllm/v1/core/kv_cache_utils.py:164`) | inner block 128 token | `num_gpu_blocks = 513`, 그중 null block 1개 제외 → **512** | **LRU** (free 시 뒤에 append, front가 least-recent) |
| 2 (RBLN) | `RBLNBlockAllocator` + `BlockMappingManager` (`optimum_prefix_cache_manager.py`) | outer block 8,192 token | `num_ob = ceil(512 / 64)` = **8** | **FIFO** (`FIFOEvictionPolicy`가 `__init__`에 하드코딩, `optimum_prefix_cache_manager.py:258`) |

`LRUEvictionPolicy` 클래스가 같은 파일에 존재하지만 **사용되지 않는다.**

### 확정된 사실

1. `num_ob = ceil(num_inner_blocks / block_ratio)`이고 `num_inner_blocks = num_gpu_blocks − 1 = 512`, `block_ratio = ob_size / ib_size = 8192 / 128 = 64` → **`num_ob = 8`**.
2. 요청이 **정상 종료**하면(`preemption=False`) outer block은 반환되지 않고 `mapping.is_active = False`로만 바뀐다 (`free_request`). 즉 **inactive 상태로 계속 pool을 점유**하며 동시에 cache 후보가 된다.
3. `can_allocate`는 free outer block이 부족할 때만 `select_blocks_for_eviction`을 호출하고, `FIFOEvictionPolicy`는 **`_allocation_order`(할당 순서)** 중 inactive인 것을 앞에서부터 고른다.
4. 2,000 token 요청은 `ceil(2000/128) = 16` inner block → `ceil(16/64) = **1** outer block`을 쓴다. **8,192 token 이하라면 길이에 무관하게 outer block 1개다.**
5. 따라서 **token 총량은 outer block 소비를 결정하지 않는다.** 요청 **개수**가 결정한다.
6. `is_full_block_available()`은 b8에서 `num_ob(8) >= max_num_seqs(8) × ceil(8192/8192)=8` → `True`. 이때 `get_dummy_block()`은 `can_allocate(1, 0)`으로 **outer block 1개를 추가로 요구**한다. 이것이 가용 outer block을 1개 줄일 수 있다.
7. 관측 채널이 있다: `[PFX] [ALLOC]`(OB/IB 목록), `[PFX] [EVICTION]`(evict된 OB, 남은 free 수, 남은 inactive mapping 목록), `[PFX] [CACHE-HIT]`, `[PFX] [CACHE-PARTIAL]`.
8. 층 1의 hit(`prefix_cache_hits_total`)은 `get_computed_blocks`가 계상하며 **층 2와 독립적으로 동작한다.** `_evict_block`은 vLLM의 inner block pool을 건드리지 않는다.
9. 2,000 token 요청은 inner block을 16개만 쓰므로 512개 pool에서 층 1이 고갈되려면 32개 요청이 필요하다. 즉 **작은 배경 요청에서는 층 2가 먼저 고갈된다.**

## 경쟁 예측과 판별

사실 8·9에서 두 층이 어긋날 수 있다. 이번 실험이 이를 판별한다.

- **D1 (두 층 정합)**: 층 2가 target의 OB를 evict하면 층 1의 hit도 같이 사라진다.
- **D2 (두 층 분기)**: 층 1은 inner block이 남아 있어 hit을 계속 보고하지만 층 2는 OB가 없어 실제 device 재사용에 실패한다 → `[PFX] [CACHE-PARTIAL]`이 나타나거나 `[CACHE-HIT]`가 사라진다.

D2가 관측되면 **`prefix_cache_hits_total`만으로 재사용을 판정하면 과대평가**라는 뜻이며, 이는 이후 모든 cache 실험의 metric 채택에 영향을 준다.

## 실험 설계

### 1 trial 구조 (순차, 동시성 1)

1. **target**: 유일 내용의 2,000 token prompt, `max_tokens=8`
2. **gap 모사**: 유일 내용의 배경 요청 B개를 **순차** 전송 (각 2,000 token, `max_tokens=8`)
3. **resume**: `target + " " + suffix(8 token)` 전송. 이 요청의 `prefix_cache_hits` 증분과 `[PFX]` 로그로 생존을 판정

### C 격자

지시받은 token 기준 격자 {0, 0.25, 0.5, 1.0, 1.5} × pool(65,664 token)를 배경 요청 2,000 token으로 환산하면 **B = {0, 8, 16, 33, 49}** 다. 그런데 사실 1–5에 따르면 전이가 **B = 7~8** 부근에서 일어나므로 이 격자는 문턱 아래 해상도가 없다. 따라서 **문턱 주변 해상도를 추가**한다.

| trial | B (배경 요청 수) | 근거 |
|---|---|---|
| B0 | 0 | 대조 |
| B3 | 3 | 문턱 아래 |
| B6 | 6 | 문턱 직전 |
| B7 | 7 | 예측 전이점 |
| B8 | 8 | 예측 전이점 |
| B9 | 9 | 문턱 직후 |
| B16 | 16 | 지시 격자 0.5× |
| B33 | 33 | 지시 격자 1.0× |
| B49 | 49 | 지시 격자 1.5× |

지시 격자의 0.25×(B8)는 위 B8과 같으므로 중복 실행하지 않는다.

**requested C와 observed C를 분리한다.** requested는 위 B, observed는 (a) 배경 요청들의 `usage.prompt_tokens` 합, (b) `[PFX] [ALLOC]` 로그에서 센 실제 OB 할당 수다.

### trial 간 오염 차단

**trial마다 fresh server**를 쓴다. 유일 prefix만으로는 부족하다 — 측정 대상이 **outer block pool의 상태**인데 그 상태는 server를 재기동해야 초기화되고, 앞 trial이 남긴 inactive mapping이 다음 trial의 free block 수를 바꾸기 때문이다. 총 9 lifecycle.

### 고정 파라미터

| 항목 | 값 |
|---|---|
| Model | `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음) |
| Server | `vllm serve <artifact> --host 127.0.0.1 --port 8000 --enable-prefix-caching` |
| 환경변수 | `VLLM_LOGGING_LEVEL=DEBUG`, `VLLM_RBLN_METRICS=1` |
| `RBLN_DEVICES` | 설정하지 않음 |
| Prompt | `experiments/npu/stage2/gap_prompts.json` (tokenizer 실측, 전 prompt 첫 token부터 상이) |
| target / background | 각 2,000 token |
| suffix | 8 token |
| `max_tokens` | 8 |
| Sampling | `temperature=0.0`, `top_p=1.0` |
| Seed | 20260819. prompt 내용 seed는 `derive_block_seed(20260819, "<trial>/<role>")` |

## 판정 기준

**hit 산식 기반으로 판정한다. latency는 판정에 쓰지 않는다** (cache source를 latency로 판정 금지 원칙). latency는 보조 기록이다.

전생존 기대 hit은 `floor(min(|P_T|, resume_prompt_tokens − 1) / 128) × 128`이다. `|P_T| = 2,000`, resume prompt = 2,009 token이므로 **기대값 = 1,920 token (= inner block 15개)**.

**생존율 = resume 요청의 `prefix_cache_hits` 증분 / 1,920**

| 판정 | 조건 |
|---|---|
| 전생존 | 생존율 = 1.0 |
| 부분 생존 | 0 < 생존율 < 1.0 |
| 소멸 | 생존율 = 0 |

**문턱 = 생존율이 처음으로 1.0 미만이 되는 B.**

층 판별(D1 vs D2)은 같은 trial에서 층 1(`prefix_cache_hits` 증분)과 층 2(`[PFX] [CACHE-HIT]`의 OB/IB 목록, `[CACHE-PARTIAL]`, `[EVICTION]`)를 대조해 한다.

eviction 순서는 `[PFX] [EVICTION]` 로그의 `OB=` 값과 `[PFX] [ALLOC]`의 할당 순서를 대조해 판정한다.

### FAIL / PARTIAL 처리 규칙 (측정 전 고정)

| 상황 | 판정 |
|---|---|
| 측정 전 patch state가 `patched`가 아님 | `BLOCKED`. 중단·보고 |
| server 기동 실패 또는 요청 non-200 | `FAILED`. 로그 보존 |
| B0(대조)에서 생존율 < 1.0 | `INVALID`. 배경 할당이 없는데 생존하지 않으면 설계 전제가 깨진 것이다 |
| 전 B에서 생존율 1.0 | `PARTIAL`. 문턱이 이 격자 밖이라는 사실을 기록하고 B를 늘릴 것을 다음 작업으로 넘긴다 |
| 관측된 hit이 128의 배수가 아님 | `PARTIAL`. [TASK11](TASK11.md)의 hit 단위와 모순되므로 원인 규명 전 판정 보류 |
| `[PFX] [EVICTION]` 로그가 한 번도 없는데 생존율이 떨어짐 | `PARTIAL`. 층 2 외의 기전을 의심하고 기록 |
| 종료 후 device memory 미복귀 | `PARTIAL`. 잔존 context 기록 후 보고 |

## 사전 예측 (판정 기준 아님)

| # | 예측 | 근거 |
|---|---|---|
| 1 | B0에서 생존율 1.0 (hit = 1,920) | 배경 할당 없음 |
| 2 | 배경 요청 1개당 outer block **정확히 1개** 할당 | 사실 4 |
| 3 | **문턱은 B = 6 또는 7**. target이 OB 1개를 쓰고 남은 7개 중 dummy block이 1개를 쓸 수 있다(사실 6) | 사실 1·2·3·6 |
| 4 | 문턱 이후 생존율은 **0으로 급락**(부분 생존 없음). target의 OB 1개가 통째로 evict되기 때문 | 사실 2·3 |
| 5 | eviction 대상 첫 OB는 **target의 OB**(할당 순서 1위) | FIFO |
| 6 | B16/B33/B49에서도 생존율 0 | 문턱 초과 |
| 7 | **D2(두 층 분기)가 관측된다** — 층 1은 hit을 계속 보고하고 층 2만 실패 | 사실 8·9 |
| 8 | observed background token = B × 2,000 | 설계 |

예측 3(문턱 6 vs 7)과 예측 7은 확신도가 낮다고 명시해 둔다. 특히 예측 7은 두 층이 서로를 통지하는 경로를 끝까지 추적하지 않았다.

## 필수 측정 항목

- trial별: 전 요청의 status·`usage.prompt_tokens`·counter 증분 6종, resume의 hit과 생존율
- `[PFX] [ALLOC]` / `[EVICTION]` / `[CACHE-HIT]` / `[CACHE-PARTIAL]` 로그 전문과 OB/IB 목록
- observed C: 배경 token 합, 실제 OB 할당 수
- **patch state** 출력
- `rbln-smi`: 첫 기동 전, 마지막 종료 후
- provenance: git commit과 dirty 여부, package version, model 경로, hostname, 환경변수

## 실행 절차 (측정 전 고정)

`<RUN>` = `results/npu/stage2/<timestamp>-gap-turnover`

1. `apply.sh status`로 `patched` 확인 → `<RUN>/patch-state.txt`. 아니면 중단
2. trial `B0, B3, B6, B7, B8, B9, B16, B33, B49` 각각에 대해:
   a. server 기동, `/health` 200 대기
   b. probe 실행

      ```bash
      env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
        experiments/npu/stage2/gap_turnover_probe.py \
        --base-url http://127.0.0.1:8000 \
        --prompts-file /home/rebel/continuum-npu/experiments/npu/stage2/gap_prompts.json \
        --trial <KEY> --max-tokens 8 --seed 20260819 \
        --output-dir <절대경로>/<RUN>/probe
      ```

   c. PID 특정 후 `SIGTERM`, 종료·port 해제 확인
3. `[PFX]` 로그 집계 → 문턱·순서·층 판별
4. C-생존율 곡선 작성

## 관련 문서

- [TASK11](TASK11.md) — hit 단위 128 token, 기대 hit 산식의 출처
- [TASK12](TASK12.md) — substrate patch 상태
- [TASK13](TASK13.md) — 같은 batch의 선행 작업
- [TASK09](TASK09.md) — `Allocated/Freed block(s)` 로그의 최초 발견
