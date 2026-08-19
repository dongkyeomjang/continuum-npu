# TASK11 — prefix cache hit 경계와 KV block 의미론 확정

## 상태

DONE

## 판정

**hit 단위 = inner block 128 token으로 확정.** 경쟁 가설 중 **H1(길이 문턱) 채택, H2(중복 block 요구) 기각**. outer block 8,192이 hit 정렬 단위라는 가설도 기각됐다. 선등록한 9개 예측 중 8개가 맞았고, 명시적으로 확신도가 낮다고 기록한 예측 8만 빗나갔다.

## 날짜

2026-08-19

## 목적

[TASK09](TASK09.md)·[TASK10](TASK10.md)에서 반복 관측된 `vllm:prefix_cache_hits_total = 0`의 원인을 확정하고, inner block(128)과 outer block(8,192)의 실효 의미론을 판정한다. Stage 2 repeated-prefix baseline 설계의 전제다.

## 배경

관련 TASK:

- [TASK08](TASK08.md) — KV accounting을 source로 확정. `VLLM_RBLN_SUB_BLOCK_CACHE`가 기본 경로에서 무효라고 주장했다. 이 TASK가 그 주장을 실험으로 검증한다.
- [TASK09](TASK09.md) — `queries`의 단위가 token임을 확인하고 `hits`·`prompt_tokens_cached`를 "노출되나 미검증"으로 분류했다. prompt 12·17 token.
- [TASK10](TASK10.md) — b8에서도 hit 0 재현. prompt 20 token. `[PFX]` 로그 부재.

선등록 문서: [STAGE2_PREFIX_PREREG.md](STAGE2_PREFIX_PREREG.md)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `ef3063e7a4ebd486944dc09a5c18575ac9178246`
- Git dirty: untracked `.idea/`만
- Host: `atom-max8`. Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`
- Device: 32 visible ID 전부 idle, port 8000 비어 있음
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` ([TASK10](TASK10.md) 산출, 재compile 없음)

## 수행 내용

1. Source 조사로 hit 판정 경로 전체를 추적하고 사실 9개를 확정했다 (선등록 문서에 기록).
2. artifact의 tokenizer로 100/130/260/1,000/4,000 token prompt를 **정확히** 맞춰 고정하고, 두 arm이 서로의 cache를 물려받지 않도록 첫 token부터 다른 base 2벌(`prompts_a`, `prompts_b`)과 8-token suffix 5개를 만들었다.
3. 선등록 문서·prompt 파일·probe script를 **측정 시작 전에** commit했다 (`ef3063e`).
4. Server 구성 3개(`apc_on`, `apc_off`, `subblock_off`)를 순차로 띄우고 각 구성에서 요청을 **순차(동시성 1)** 로 보내며 요청 1개마다 counter 전후 증분을 기록했다.
5. 각 구성의 server 로그에서 `[PFX] [CACHE-HIT]` / `[CACHE-PARTIAL]` 출현을 확인했다.
6. 각 구성 종료 시 PID를 특정해 `SIGTERM`을 보내고 종료·port 해제·device memory 복귀를 확인했다.

재compile, download, RSD 변경, site-packages 수정, patch 적용은 없었다.

## 변경된 파일

선등록 commit `ef3063e`:

- `docs/research/STAGE2_PREFIX_PREREG.md` (신규)
- `experiments/npu/stage2/build_prompts.py` (신규)
- `experiments/npu/stage2/prefix_cache_probe.py` (신규)
- `experiments/npu/stage2/prefix_prompts.json` (신규, tokenizer 실측 고정)

이번 기록 commit:

- `docs/research/TASK11.md` (신규)
- `docs/research/INDEX.md`

Raw artifact는 `.gitignore` 대상인 `results/npu/stage2/20260819-181100-prefix-boundary/`에 있다.

## 실험 또는 검증 방법

`<RUN>` = `results/npu/stage2/20260819-181100-prefix-boundary`

```bash
# prompt 생성 (측정 전, 선등록에 포함)
env -u PYTHONPATH python3 experiments/npu/stage2/build_prompts.py \
  --tokenizer-dir /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb \
  --targets 100,130,260,1000,4000 --suffix-tokens 8 --suffix-variants 5 \
  --output experiments/npu/stage2/prefix_prompts.json

# 구성별 server (셋 중 하나씩)
env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG vllm serve <artifact> \
  --host 127.0.0.1 --port 8000 --enable-prefix-caching            # apc_on
env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG vllm serve <artifact> \
  --host 127.0.0.1 --port 8000 --no-enable-prefix-caching         # apc_off
env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG VLLM_RBLN_SUB_BLOCK_CACHE=false \
  vllm serve <artifact> --host 127.0.0.1 --port 8000 --enable-prefix-caching  # subblock_off

# probe
env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage2/prefix_cache_probe.py \
  --base-url http://127.0.0.1:8000 \
  --prompts-file /home/rebel/continuum-npu/experiments/npu/stage2/prefix_prompts.json \
  --lengths 100,130,260,1000,4000 --repeats 5 \
  --max-tokens 8 --seed 20260819 --tag apc_on \
  --output-dir /home/rebel/continuum-npu/<RUN>/probe
```

## 결과

### 조건 분리

- `requested_condition`: prompt token 100/130/260/1,000/4,000, 요청 arm `identical`(동일 prompt 5회)과 `shared_prefix`(공유 prefix + 상이한 8-token suffix 5개), 동시성 1, `max_tokens=8`, greedy, seed 20260819. 구성 arm 3개.
- `observed_condition`: server가 보고한 `usage.prompt_tokens`가 목표 token 수와 **정확히 일치**했다 (`identical`은 100/130/260/1000/4000, `shared_prefix`는 suffix 9 token이 더해져 109/139/269/1009/4009). `apc_on`·`subblock_off`는 `enable_prefix_caching=True`, `apc_off`는 `False`로 resolve됐다. 전 요청 status 200.
- `condition_reached`: `YES`.

### 관찰 — `apc_on` 전 격자

Population: 요청 50개(길이 5 × arm 2 × 반복 5). Unit: token. Source: `/metrics` counter의 요청 전후 증분. Device scope: `rbln0`–`rbln3`.

| 길이 | arm | prompt_tok | `hits` 증분 (index 0 → 4) | `prompt_tokens_cached` 증분 |
|---|---|---|---|---|
| 100 | identical | 100 | 0, 0, 0, 0, 0 | 전부 0 |
| 100 | shared_prefix | 109 | 0, 0, 0, 0, 0 | 전부 0 |
| 130 | identical | 130 | **0, 128, 128, 128, 128** | 동일 |
| 130 | shared_prefix | 139 | **0, 128, 128, 128, 128** | 동일 |
| 260 | identical | 260 | 128, **256, 256, 256, 256** | 동일 |
| 260 | shared_prefix | 269 | 128, **256, 256, 256, 256** | 동일 |
| 1,000 | identical | 1,000 | 256, **896, 896, 896, 896** | 동일 |
| 1,000 | shared_prefix | 1,009 | 256, **896, 896, 896, 896** | 동일 |
| 4,000 | identical | 4,000 | 896, **3968, 3968, 3968, 3968** | 동일 |
| 4,000 | shared_prefix | 4,009 | 896, **3968, 3968, 3968, 3968** | 동일 |

`queries` 증분은 **모든 요청에서 `usage.prompt_tokens`와 정확히 같았다** (100, 109, 130, 139, 260, 269, 1000, 1009, 4000, 4009).

`prompt_tokens_cached_total` 증분은 **전 요청에서 `hits` 증분과 값이 같았다.** [TASK09](TASK09.md)에서 "노출되나 미검증"이었던 이 metric은 이제 **채택 가능**으로 승격된다.

`num_preemptions_total` 증분은 전 요청 0이었다.

### 관찰 — 산식 대조

정상 상태(index 1 이후)의 `hits`를 선등록 산식 `floor((prompt_tokens - 1) / 128) × 128`과 대조한다.

| prompt_tok | 산식 | 실측 | 일치 |
|---|---|---|---|
| 100 | `(99 // 128) × 128 = 0` | 0 | ✓ |
| 109 | `(108 // 128) × 128 = 0` | 0 | ✓ |
| 130 | `(129 // 128) × 128 = 128` | 128 | ✓ |
| 139 | `(138 // 128) × 128 = 128` | 128 | ✓ |
| 260 | `(259 // 128) × 128 = 256` | 256 | ✓ |
| 269 | `(268 // 128) × 128 = 256` | 256 | ✓ |
| 1,000 | `(999 // 128) × 128 = 896` | 896 | ✓ |
| 1,009 | `(1008 // 128) × 128 = 896` | 896 | ✓ |
| 4,000 | `(3999 // 128) × 128 = 3968` | 3968 | ✓ |
| 4,009 | `(4008 // 128) × 128 = 3968` | 3968 | ✓ |

**10개 조건 전부 일치했다.** 모든 hit 값이 128의 배수다.

### 관찰 — 2층(outer block) 로그

`apc_on` 로그에 `[PFX] [CACHE-HIT]`가 **38회** 출현했다. 이는 `hits > 0`인 요청 수 38개와 정확히 일치한다. `[PFX] [CACHE-PARTIAL]`은 한 번도 나오지 않았다.

예시:

```text
[PFX] [CACHE-HIT] REQUEST=cmpl-a53f7e71... | OB_COUNT=1 OB=[2] | IB_COUNT=1 IB=[[11]]
```

즉 1층이 찾은 inner block이 2층에서 outer block 1개에 사상됐다. 이 로그는 outer/inner block ID를 함께 담으므로 **KV block lifecycle 관측 경로로 채택 가능**하다.

### 관찰 — `apc_off` (길이 1,000, 요청 10개)

| 항목 | `apc_on` | `apc_off` |
|---|---|---|
| resolved `enable_prefix_caching` | `True` | `False` |
| resolved `block_size` | 128 | **8192** (16 → 8192로 갱신) |
| EngineCore `num_gpu_blocks` | 513 | **9** |
| `GPU KV cache size` | 65,664 tokens | **73,728 tokens** |
| `queries` 증분 | prompt_tokens와 동일 | **0** (전 요청) |
| `hits` 증분 | 위 표대로 | **0** (전 요청) |
| `[PFX]` 로그 | 38회 | **0회** |
| e2e latency (참고) | 0.105–0.216 s | 0.256–0.278 s |

**APC OFF에서 `queries`조차 0이다.** `get_computed_blocks`가 `enable_caching`이 False면 즉시 반환하므로 `prefix_cache_stats.record`가 호출되지 않는다.

### 관찰 — `subblock_off` (길이 1,000, 요청 10개)

`VLLM_RBLN_SUB_BLOCK_CACHE=false` + `--enable-prefix-caching`:

| 항목 | 값 |
|---|---|
| resolved `enable_prefix_caching` | `True` |
| EngineCore `num_gpu_blocks` | 513 |
| `GPU KV cache size` | 65,664 tokens |
| `hits` 증분 (identical, index 0→4) | 0, 896, 896, 896, 896 |
| `hits` 증분 (shared_prefix, index 0→4) | 0, 896, 896, 896, 896 |
| `[PFX] [CACHE-HIT]` | 8회 (= `hits > 0`인 요청 수) |

**`apc_on`의 같은 길이와 정상 상태 값이 동일하다.** [TASK08](TASK08.md)의 "이 flag는 기본 경로에서 무효" 주장이 유지된다.

### 관찰 — index 0의 비-0 hit (선등록 예측에 없던 관측)

`apc_on`에서 길이 260·1,000·4,000의 **index 0**이 각각 128·256·896의 hit을 냈다. 이는 **길이 조건들이 서로 독립이 아니었기 때문**이다. `prompts_a`는 같은 단어 목록을 잘라 만들었으므로 짧은 길이의 prompt가 긴 길이 prompt의 **접두사**다. 앞서 실행한 130이 128 token을 캐시해 두었고, 260의 첫 요청이 그것을 재사용했다. 260 → 1,000, 1,000 → 4,000도 같다.

이 해석은 `subblock_off` 실행이 독립적으로 지지한다. 그 구성은 **fresh server에서 길이 1,000만** 돌렸고 index 0의 hit이 **0**이었다. 즉 index 0의 비-0 hit은 같은 server 안에서 앞선 짧은 길이가 남긴 cache 때문이다.

`shared_prefix` arm도 같은 패턴을 보였고(`prompts_b` 내부에서 동일한 접두사 관계), 두 base가 서로 다르므로 arm 간 오염은 없었다.

### 선등록 판정 규칙 대조

| 규칙 | 결과 |
|---|---|
| 1. hit 단위 확정 | **확정.** 첫 비-0 hit은 길이 130 index 1의 **128**. 모든 hit이 128의 배수이며 `floor((n−1)/128)×128` 상한과 10/10 일치. **hit 단위 = inner block 128 token** |
| 2. H1 vs H2 | 길이 130의 **index 1에서 이미 hit 128**. → **H1 채택, H2 기각** |
| 3. outer block 가설 | 4,000 token(< 8,192)에서 hit 3,968 관측. → **outer block 8,192이 hit 단위라는 가설 기각** |
| 4. APC 통제 검증 | `apc_off`에서 `queries`·`hits` 0, `[PFX]` 0회. → **`--no-enable-prefix-caching`으로 Stage 2 OFF/ON 통제 성립** |
| 5. 사실 9 falsification | `subblock_off`가 `apc_on`과 동일. → **[TASK08](TASK08.md) 주장 유지** |

### 선등록 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| 1 | 길이 100은 전 반복 `hits = 0` | ✓ |
| 2 | `queries` = prompt token 수 | ✓ (50/50 요청) |
| 3 | 길이 130의 hit = 128 | ✓ |
| 4 | 260→256, 1,000→896, 4,000→3,968 | ✓ |
| 5 | 4,000에서 hit 발생 | ✓ |
| 6 | `apc_off`에서 `queries`·`hits` 0 | ✓ |
| 7 | `subblock_off` = `apc_on` | ✓ |
| 8 | **H2가 binding이라 index 1은 0** | ✗ **빗나감** — index 1에서 128 hit |
| 9 | `shared_prefix`의 hit 상한은 공유 prefix가 결정 | ✓ |

**8/9 적중.** 빗나간 예측 8은 선등록 문서에 "다른 예측보다 불확실하다"고 명시해 둔 항목이다.

## 핵심 발견

1. **hit 단위는 inner block 128 token이다.** `floor((prompt_tokens − 1) / 128) × 128` 산식이 10개 조건에서 전건 일치했다. outer block 8,192은 hit 단위가 아니다.
2. **[TASK09](TASK09.md)·[TASK10](TASK10.md)의 `hits = 0`은 prompt가 짧았기 때문이다.** 12·17·20 token은 전부 129 token 문턱 아래였다. **prefix caching은 정상 동작하고 있었다.** 이전 두 TASK의 "미검증" 분류는 이제 해소된다.
3. **`get_one_block`의 중복 block 요구(H2)는 binding이 아니었다.** 길이 130의 두 번째 요청이 이미 128 hit을 냈다. source만 읽고 세운 H2는 실행 수준에서 기각됐다.
4. **`prompt_tokens_cached_total`이 `hits`와 항상 같은 값이었다.** "노출되나 미검증"에서 **채택 가능**으로 승격한다. 다만 두 값이 같으므로 독립 정보를 주지는 않는다.
5. **APC OFF/ON은 단일 인자 토글이 아니다.** OFF에서 `block_size`가 128 → **8192**로, `num_gpu_blocks`가 513 → **9**로, KV cache size가 65,664 → **73,728 token**으로 함께 바뀐다. `update_block_size`의 else 분기가 `block_size = kvcache_block_size`를 쓰기 때문이다. **Stage 2에서 APC OFF/ON을 비교하면 KV block 입도와 pool 구조가 동시에 바뀐다.** 이는 통제해야 할 confounder다.
6. **`[PFX] [CACHE-HIT]` 로그가 outer/inner block ID를 함께 노출한다.** 출현 횟수가 `hits > 0` 요청 수와 정확히 일치했다. [TASK10](TASK10.md)이 발견한 `Allocated/Freed block(s)` 로그와 함께 KV lifecycle 관측 경로가 된다.
7. **prompt 길이 조건들이 서로 독립이 아니면 index 0이 오염된다.** 짧은 prompt가 긴 prompt의 접두사이면 앞선 조건이 뒤 조건의 cache를 채운다. `subblock_off`의 fresh server 실행이 이를 독립적으로 확인했다.
8. **`--no-enable-prefix-caching`으로 APC를 확실히 끌 수 있다.** OFF에서 `queries`조차 0이므로 "요청이 cache 조회를 시도했는지"까지 구분된다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(해석)** 발견 5는 Stage 2 설계를 직접 제약한다. "APC OFF vs ON"을 그대로 비교하면 관측된 차이가 prefix 재사용 때문인지 block 입도(128 vs 8192) 때문인지 분리할 수 없다. 두 가지 대응이 가능하다: (a) OFF/ON 각각의 resolved `block_size`·`num_gpu_blocks`를 조건으로 기록하고 해석에서 분리, (b) `--block-size`를 명시해 두 arm의 입도를 맞출 수 있는지 확인. (b)의 가능 여부는 확인하지 않았다.
- **(hypothesis)** H2가 binding이 아니었던 이유는, 첫 요청이 끝나고 block이 free된 뒤에도 hash 등록이 남아 있고 두 번째 요청 시점에 그 hash에 block이 2개 이상 연결되는 경로가 있기 때문으로 보인다. 정확한 기전은 추적하지 않았다. `get_one_block`의 "정확히 1개면 None" 분기가 어떤 상황에서 실제로 발동하는지는 `UNKNOWN`이다.
- **(해석)** latency는 판정에 쓰지 않았지만 참고로, `apc_on` 길이 4,000의 index 0이 0.701 s, index 1 이후가 0.120 s였다. `apc_off`는 같은 길이 1,000에서 0.256 s로 `apc_on`의 정상 상태 0.105 s보다 컸다. 방향은 cache 재사용과 일관되지만 **1회 관측이고 cache source를 latency로 판정하지 않는다는 원칙에 따라 근거로 쓰지 않는다.**
- **(hypothesis, tool-gap 연구 함의)** hit 단위가 128 token이고 재사용이 outer block 사상을 거친다는 것은, 이 stack에서 KV 재획득 채널이 **inner block 단위의 host-side 재계산 회피**로 존재한다는 뜻이다. 즉 "무엇을 남길지"의 최소 단위가 128 token이다. 이는 KEEP/OFFLOAD/RECOMPUTE 설계의 입도 하한을 시사하지만, Stage 0–2 baseline 전에는 구현하지 않는다는 원칙에 따라 여기서는 hypothesis로만 기록한다.

## 확인되지 않은 사항

- `get_one_block`의 "hash당 block 1개면 `None`" 분기가 실제로 발동하는 조건 (`UNKNOWN`). H2는 기각됐지만 그 코드가 죽은 코드인지, 특정 상황에서만 도는지는 확인하지 않았다.
- APC OFF/ON의 block 입도 차이를 제거할 수 있는지 (`--block-size` 명시가 optimum 경로에서 통하는지) (`UNKNOWN`).
- prompt가 outer block 경계(8,192 token)를 넘을 때의 거동 (`UNKNOWN`). `max_seq_len`이 8,192이므로 현재 artifact로는 관측할 수 없다.
- cache eviction 거동 (`UNKNOWN`). 이번 격자는 KV pool(65,664 token)을 채우지 않았고 `num_preemptions_total`도 전 요청 0이었다.
- 동시 요청에서의 hit 거동 (`UNKNOWN`). 이번 실험은 전부 동시성 1이었다.
- `prompt_tokens_cached_total`이 `hits`와 다른 값을 갖는 조건이 있는지 (`UNKNOWN`).
- [TASK10](TASK10.md)의 "`running`이 2씩 증가" `UNKNOWN`은 이번 실험이 동시성 1이라 부수 관측되지 않았다. 별도로 추적하지 않는다.

## 실패 / 무효 시도

- `vllm serve --help`가 87줄만 출력하고 prefix caching 관련 항목을 보여주지 않아 flag 이름을 help로 확인하지 못했다. `vllm/engine/arg_utils.py:505`의 `enable_prefix_caching: bool | None`을 근거로 `--no-enable-prefix-caching`을 사용했고 resolved 값이 `False`로 확인되어 의도대로 동작했다.
- 무효로 판정한 측정은 없다. 전 요청 status 200.
- Device·RSD·package·site-packages 변경은 없었다. patch는 적용하지 않았다.

## 연구 원칙에 미치는 영향

- **"신호가 0이다"를 "신호가 죽었다"로 읽지 않는다.** [TASK09](TASK09.md)·[TASK10](TASK10.md)에서 두 번 관측된 `hits = 0`은 metric의 결함이 아니라 **실험 조건이 신호의 발생 조건 밖에 있었기 때문**이었다. 미검증 신호는 그 신호가 발생할 조건을 source에서 유도해 그 조건 안에서 재시험한다.
- **source에서 세운 가설도 실행으로 기각될 수 있다.** H2는 코드를 정확히 읽고 세웠지만 틀렸다. 확신도가 낮은 예측은 선등록에 그렇게 표시해 두어야 사후 합리화를 막을 수 있다.
- **조건 간 독립성을 설계 시점에 확인한다.** 길이 sweep의 prompt들이 서로 접두사 관계이면 앞 조건이 뒤 조건의 초기 상태를 오염시킨다. 이번에는 별도 구성의 fresh server 실행이 있어 해석이 가능했다.
- **"단일 인자 토글"을 검증 없이 가정하지 않는다.** APC OFF/ON은 block 입도와 pool 크기를 함께 바꿨다. 실험 arm을 정할 때 resolved config를 arm별로 전부 기록한다.
- cache 관련 판정은 counter로 하고 latency는 보조로만 쓴다는 원칙이 이번에도 유효했다. latency 방향은 결론과 일치했지만 근거로 쓰지 않았다.

## 다음 작업

Stage 2 repeated-prefix baseline 설계에 이월할 제약:

1. **prefix는 최소 129 token, 실효적으로는 128의 배수 + 1 이상**이어야 hit이 발생한다. 짧은 prompt로 설계하면 신호가 구조적으로 0이다.
2. **길이·조건 간 prefix 오염을 차단**한다. 조건마다 첫 token부터 다른 base를 쓰거나 server를 재기동한다.
3. **APC OFF/ON 비교는 block 입도 confounder를 함께 기록**한다. OFF는 `block_size=8192`, `num_gpu_blocks=9`이고 ON은 128 / 513이다.
4. 관측 신호로 `prefix_cache_queries_total`·`hits_total`·`prompt_tokens_cached_total`(= hits)과 `[PFX] [CACHE-HIT]` 로그를 쓴다. 판정에 latency를 쓰지 않는다.
5. eviction과 동시성 하의 hit 거동은 아직 `UNKNOWN`이므로 Stage 2에서 별도 조건으로 다룬다.

사용자 지시 없이 Stage 2에 착수하지 않는다.

## 재현 정보

- 선등록 commit: `ef3063e7a4ebd486944dc09a5c18575ac9178246`
- **측정 시작 시각: 2026-08-19 18:11:0x KST.** 선등록 commit 시각은 2026-08-19 18:10:55 KST이므로 **선등록이 측정보다 앞선다.**
- 측정 종료 시각: 2026-08-19 18:17:39 KST
- Base commit (측정 중 HEAD): `ef3063e7a4ebd486944dc09a5c18575ac9178246`, dirty = untracked `.idea/` 및 gitignored `results/`, `models/`
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)
- Raw artifact: `results/npu/stage2/20260819-181100-prefix-boundary/`
  - `measurement-start.txt`, `measurement-end.txt`
  - `server-apc_on.log`, `server-apc_off.log`, `server-subblock_off.log`
  - `{apc_on,apc_off,subblock_off}-{start,exit}.txt`
  - `rbln-smi-before.txt`, `rbln-smi-final.txt`
  - `probe/prefix_cache_probe.{apc_on,apc_off,subblock_off}.json`
- 고정 prompt: `experiments/npu/stage2/prefix_prompts.json` (tokenizer 실측, git 추적)
- 실행 script: `experiments/npu/stage2/{build_prompts.py,prefix_cache_probe.py}`
- Isolation launcher: `experiments/npu/launch/run_isolated_python.sh`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch 2.11.0+cpu`, `transformers 5.8.1`
- Host: `atom-max8`, device `rbln0`–`rbln3`
