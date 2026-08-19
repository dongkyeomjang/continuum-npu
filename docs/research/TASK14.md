# TASK14 — prefix-cache block 생존/eviction 파일럿: NPU GapTurnover 첫 실측

## 상태

DONE

## 판정

**두 층에서 서로 다른 문턱이 관측됐다.**

- **층 2 (RBLN outer block, FIFO, 8개): 문턱 B = 7.** B ≤ 6에서 실제 재사용이 100 %, B ≥ 7에서 **0 %** 로 급락한다.
- **층 1 (vLLM inner block, LRU, 512개): 문턱은 16 < B ≤ 33.** 선등록한 판정 metric(`prefix_cache_hits_total`)은 B = 16까지 생존율 1.0을 보고했다.

**7 ≤ B ≤ 16 구간에서 선등록 metric은 실제 재사용을 100 % 과대평가한다.** 경쟁 예측 중 **D2(두 층 분기)가 채택**됐다.

## 날짜

2026-08-19

## 목적

tool gap을 모사한 구간 동안 배경 할당이 누적될 때 완료된 요청의 cached prefix block이 언제 밀려나는지 실측한다. NPU에서 체제 I/II 경계의 첫 좌표를 얻는 것이 목표다.

## 배경

관련 TASK:

- [TASK11](TASK11.md) — hit 단위 inner block 128 token. 기대 hit 산식의 출처.
- [TASK12](TASK12.md) — substrate patch 상태.
- [TASK13](TASK13.md) — 같은 batch의 선행 작업.
- [TASK09](TASK09.md) — `Allocated/Freed block(s)` 로그의 최초 발견.

선등록 문서: [GAP_TURNOVER_PREREG.md](GAP_TURNOVER_PREREG.md)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `85c146bc34b14195d61b7b0ca881f95c7de75995`
- Git dirty: untracked `.idea/`만
- **Substrate: patched** (SHA256 `70942d16…`). 측정 전 gate 통과
- Host: `atom-max8`. Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(patched), `optimum-rbln 0.11.1`
- Device: 32 visible ID 전부 idle, port 8000 비어 있음
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)

## 수행 내용

1. **Source 조사**로 두 층의 pool 크기와 eviction 정책을 확정했다 (선등록 문서에 사실 9개로 기록). 이 조사가 "binding resource는 token 총량이 아니라 outer block 개수"라는 정량 예측을 만들었다.
2. `derive_block_seed`로 trial·역할마다 유일한 2,000 token prompt를 tokenizer 실측으로 생성했다. 140개 prompt가 **첫 token부터 서로 다름**을 assert로 검증했다.
3. 선등록 문서·prompt 파일·probe script를 **측정 시작 전에** commit했다 (`85c146b`).
4. Patch state gate를 통과한 뒤 trial 9개(B0/B3/B6/B7/B8/B9/B16/B33/B49)를 **trial마다 fresh server**로 실행했다.
5. 각 trial에서 target → 배경 B개 → resume을 **순차(동시성 1)** 로 보내고 요청마다 counter 증분을 기록했다.
6. `[PFX]` 로그로 층 2의 할당·eviction·재사용을 집계하고 층 1과 대조했다.

재compile, download, patch 변경, RSD 변경, APC OFF 실험은 없었다.

## 변경된 파일

선등록 commit `85c146b`:

- `docs/research/GAP_TURNOVER_PREREG.md` (신규)
- `experiments/npu/stage2/build_gap_prompts.py` (신규)
- `experiments/npu/stage2/gap_turnover_probe.py` (신규)
- `experiments/npu/stage2/gap_prompts.json` (신규, tokenizer 실측 고정)

이번 기록 commit:

- `docs/research/TASK14.md` (신규)
- `docs/research/INDEX.md`

Raw artifact는 `.gitignore` 대상인 `results/npu/stage2/20260819-200800-gap-turnover/`에 있다.

## 실험 또는 검증 방법

`<RUN>` = `results/npu/stage2/20260819-200800-gap-turnover`

trial마다(`B0 B3 B6 B7 B8 B9 B16 B33 B49`):

```bash
env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG VLLM_RBLN_METRICS=1 \
  vllm serve /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb \
  --host 127.0.0.1 --port 8000 --enable-prefix-caching > <RUN>/server-<K>.log 2>&1 &

env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage2/gap_turnover_probe.py \
  --base-url http://127.0.0.1:8000 \
  --prompts-file /home/rebel/continuum-npu/experiments/npu/stage2/gap_prompts.json \
  --trial <K> --max-tokens 8 --seed 20260819 \
  --output-dir /home/rebel/continuum-npu/<RUN>/probe

# PID 특정 후 SIGTERM
```

## 결과

### 조건 분리

- `requested_condition`: 배경 요청 수 B ∈ {0,3,6,7,8,9,16,33,49}, target·배경 각 2,000 token, suffix 8 token, `max_tokens=8`, greedy, seed 20260819, 동시성 1, `enable_prefix_caching=True`, trial마다 fresh server.
- `observed_condition`: 전 요청 status 200. `usage.prompt_tokens`가 target 2,000 / 배경 2,000 / resume 2,008로 목표와 일치. 배경 token 합이 정확히 `B × 2,000`. 층 2의 `[PFX] [ALLOC]`이 **149회 전부 `OB_COUNT=1`** — 요청 1개당 outer block 정확히 1개. patch state는 전 구간 `patched`.
- `condition_reached`: `YES`.

### 관찰 — C-생존율 (두 층)

Population: trial 9개. Unit: token(hit), 개수(block). Source: `/metrics` counter 증분(층 1), server DEBUG 로그(층 2). Device scope: `rbln0`–`rbln3`.

전생존 기대 hit = `floor(min(2000, 2008−1)/128) × 128` = **1,920 token**.

| trial | B | observed 배경 token | 층 1 `hits` | 층 1 생존율 | 층 2 실제 재사용 | eviction 수 | resume e2e (참고) |
|---|---|---|---|---|---|---|---|
| B0 | 0 | 0 | 1,920 | **1.0** | `CACHE-HIT` IB 15개 | 0 | 0.111 s |
| B3 | 3 | 6,000 | 1,920 | **1.0** | `CACHE-HIT` IB 15개 | 0 | 0.111 s |
| B6 | 6 | 12,000 | 1,920 | **1.0** | `CACHE-HIT` IB 15개 | 1 | 0.112 s |
| B7 | 7 | 14,000 | 1,920 | **1.0** | **`CACHE-PARTIAL` REUSED=0/1920 (0 %)** | 2 | 0.448 s |
| B8 | 8 | 16,000 | 1,920 | **1.0** | **`CACHE-PARTIAL` REUSED=0/1920 (0 %)** | 3 | 0.448 s |
| B9 | 9 | 18,000 | 1,920 | **1.0** | **`CACHE-PARTIAL` REUSED=0/1920 (0 %)** | 4 | 0.447 s |
| B16 | 16 | 32,000 | 1,920 | **1.0** | **`CACHE-PARTIAL` REUSED=0/1920 (0 %)** | 11 | 0.445 s |
| B33 | 33 | 66,000 | **0** | **0.0** | 층 2 로그 없음 | 28 | 0.444 s |
| B49 | 49 | 98,000 | **0** | **0.0** | 층 2 로그 없음 | 44 | 0.444 s |

**층 2 문턱 = B 7** (B6 재사용 100 % → B7 재사용 0 %).
**층 1 문턱 = 16 < B ≤ 33** (이 격자로는 구간까지만 좁혀진다).

부분 생존은 어느 층에서도 관측되지 않았다. 두 문턱 모두 **1.0 → 0.0 급락**이다.

### 관찰 — eviction 순서

`[PFX] [EVICTION]`의 OB 순서:

| trial | evict된 OB 순서 |
|---|---|
| B6 | 0 |
| B7 | 0, 1 |
| B9 | 0, 1, 2, 3 |
| B16 | 0, 1, 2, 3, 4, 5 |

**target의 outer block(OB=0, 가장 먼저 할당됨)이 항상 첫 eviction 대상**이며 이후 할당 순서대로 이어진다. FIFO 정책과 정확히 일치한다.

eviction 수는 B ≥ 6에서 **`B − 5`** 로 관측됐다 (B6:1, B7:2, B9:4, B16:11, B33:28, B49:44). 총 할당은 `B + 2`(target + 배경 B + resume)이고 pool은 8이므로 `B + 2 − 8 = B − 6`이 산술 예상인데 실측이 1 더 많다. resume 요청의 decode가 outer block을 하나 더 요구한 것으로 보이나 확인하지 않았다.

### 관찰 — 층 분기의 직접 증거 (B7~B16)

같은 trial의 같은 resume 요청에 대해 두 층이 정반대를 보고한다.

```text
층 1: vllm:prefix_cache_hits_total 증분 = 1920   (생존율 1.0)
층 2: [PFX] [CACHE-PARTIAL] REUSED=0/1920 tokens (0.0%) |
              MISSED=1920 tokens (100.0%) | REASON=partial_cache_miss
```

**D2(두 층 분기) 채택, D1 기각.**

B6에서는 로그 순서가 `ALLOC(OB=7) → MAPPING-SEARCH → CACHE-HIT(OB=[0]) → MAPPING-REMOVE(OB=0) → EVICTION(OB=0)`이다. 즉 재사용이 **먼저** 성립하고 그 뒤에 evict됐다. B7부터는 cache 조회 시점에 이미 OB=0이 없다.

### 관찰 — B33 이후 층 1도 소멸

B33의 resume 요청 counter 증분: `queries=2008, hits=0, prompt_tokens_cached=0`. 층 1의 inner block까지 밀려났다. 배경 요청 33개 × 16 inner block = 528개로 512개 pool을 넘어선다.

### 선등록 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| 1 | B0에서 생존율 1.0 | ✓ |
| 2 | 배경 요청 1개당 outer block 정확히 1개 | ✓ (`ALLOC` 149회 전부 `OB_COUNT=1`) |
| 3 | **문턱은 B = 6 또는 7** | ✓ **층 2 문턱 = 7** (확신도 낮다고 명시했던 예측이 적중) |
| 4 | 문턱 이후 0으로 급락, 부분 생존 없음 | ✓ |
| 5 | 첫 eviction 대상은 target의 OB | ✓ (전 trial에서 OB=0) |
| 6 | B16/B33/B49에서 생존율 0 | **부분 오답.** 층 2는 ✓, 그러나 **층 1은 B16에서 1.0**이었다 |
| 7 | **D2(두 층 분기)가 관측된다** | ✓ (확신도 낮다고 명시했던 예측이 적중) |
| 8 | observed 배경 token = B × 2,000 | ✓ |

8개 중 7개 적중, 1개(예측 6) 부분 오답이다.

### 선등록 FAIL/PARTIAL 규칙 대조

- B0 생존율 1.0 → `INVALID` 조건에 걸리지 않음
- 전 B에서 생존율 1.0이 아님 → `PARTIAL` 조건에 걸리지 않음
- 관측된 hit이 전부 128의 배수(1,920 또는 0) → 모순 없음
- `[EVICTION]` 로그 없이 생존율이 떨어진 경우 없음
- 전 trial 종료 후 device memory `0.0B` 복귀, context 소멸

## 핵심 발견

1. **NPU에서 체제 경계의 첫 좌표를 얻었다.** 이 구성(b8 artifact, outer block 8개, 2,000 token 요청)에서 완료된 prefix의 실제 재사용은 **배경 요청 6개까지 생존하고 7개째에 사라진다.**
2. **생존을 결정하는 것은 token 총량이 아니라 요청 개수다.** 8,192 token 이하 요청은 길이와 무관하게 outer block 1개를 쓴다(149/149회 확인). 지시받은 token 기준 C 격자는 이 stack에서 생존을 예측하지 못한다 — 같은 14,000 token이라도 요청 7개면 소멸하고 요청 2개면 생존한다.
3. **`prefix_cache_hits_total`은 실제 재사용의 지표가 아니다.** 7 ≤ B ≤ 16 구간에서 이 metric은 1,920 hit(생존율 1.0)을 보고했지만 device 상 실제 재사용은 **0 %** 였다. 이 구간에서 **100 % 과대평가**한다.
4. **두 층의 문턱이 4~5배 차이 난다.** 층 2(outer, FIFO, 8개)는 B = 7, 층 1(inner, LRU, 512개)은 16 < B ≤ 33이다. 정책도 크기도 다르다.
5. **eviction 순서는 FIFO이고 target이 가장 먼저 희생된다.** 완료된 지 가장 오래된 것이 아니라 **할당된 지 가장 오래된 것**이 나간다. 재접근이 있어도 우선순위가 올라가지 않는다(`LRUEvictionPolicy` 클래스는 존재하나 사용되지 않는다).
6. **부분 생존 구간이 없다.** outer block이 8,192 token 단위이고 2,000 token prefix가 그 안에 통째로 들어가므로 all-or-nothing이다.
7. **층 1의 hit이 시간을 절약하지 못했다.** 참고 관측인 resume latency는 B ≤ 6에서 0.111 s, B ≥ 7에서 0.444–0.448 s로 **층 2 문턱에서만** 4배 뛰었고 층 1 문턱(B33)에서는 변화가 없었다. 판정에는 쓰지 않았으나 발견 3과 일관된다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(해석, GapTurnover 가설과의 관계)** 관찰된 것은 "누적 배경 **할당 건수**가 outer block pool을 소진하는 지점에서 생존이 끊긴다"이다. GapTurnover 가설이 "누적 배경 할당량이 pool 여유를 넘으면 생존이 끊긴다"를 말한다면 **방향은 지지**된다. 다만 이 stack에서 그 "양"의 단위는 token이 아니라 **outer block 개수**이며, 이는 가설을 이 substrate에 맞게 재기술해야 함을 뜻한다. 파일럿 1 trial/조건이므로 지지·기각을 확정하지 않는다.
- **(해석)** 발견 3은 이후 모든 cache 실험의 metric 채택에 직접 영향을 준다. [TASK09](TASK09.md)에서 "채택 가능"으로 분류하고 [TASK11](TASK11.md)에서 승격한 `prefix_cache_hits_total`은 **"층 1이 재사용 가능하다고 판단한 양"** 이지 "실제로 재사용된 양"이 아니다. 실제 재사용은 `[PFX] [CACHE-HIT]` / `[CACHE-PARTIAL]`로만 판정할 수 있다.
- **(hypothesis)** 층 1이 hit을 보고했는데 층 2가 재사용하지 못했을 때, 그 요청은 prefix를 **재계산**했을 것이다. resume latency가 0.111 → 0.444 s로 뛴 것과 일관된다. 다만 재계산 자체를 관측한 것은 아니다(prefill token 수를 분리 계측하지 않았다).
- **(hypothesis)** eviction 수가 산술 예상보다 1 많은 것은 resume 요청의 decode 단계가 outer block을 추가로 요구하기 때문으로 보인다. `_compute_num_blocks_to_allocate`의 DECODE 분기가 `num_already_allocated_ibs % block_ratio == 0`일 때 1을 반환하는 것과 관련될 수 있으나 확인하지 않았다.
- **(해석)** FIFO는 재접근을 보상하지 않으므로, 자주 쓰이는 prefix라도 오래 살아남지 못한다. KEEP/OFFLOAD 정책을 설계할 때 이 substrate의 기본 동작이 LRU가 아니라는 점이 전제가 된다. Stage 0–2 baseline 전에는 구현하지 않는다는 원칙에 따라 여기서는 기록만 한다.

## 확인되지 않은 사항

- 층 1의 정확한 문턱 (`UNKNOWN`, 16 < B ≤ 33으로만 좁혀짐). 격자에 B 20, 24, 28, 32가 없었다.
- 층 1이 hit을 보고한 요청이 실제로 prefix를 재계산했는지 (`UNKNOWN`). prefill token 수를 분리 계측하지 않았다.
- eviction 수가 `B − 6`이 아니라 `B − 5`인 이유 (`UNKNOWN`).
- prefix가 outer block 1개를 **넘는** 경우(> 8,192 token)의 부분 생존 거동 (`UNKNOWN`). `max_seq_len`이 8,192이라 현재 artifact로 관측 불가.
- 배경 요청 길이를 바꿨을 때의 거동 (`UNKNOWN`). 전 배경 요청이 2,000 token이었다. 8,192 token에 가까운 배경 요청이라면 층 1과 층 2 문턱이 가까워질 것으로 보이나 측정하지 않았다.
- 동시성 > 1에서의 거동 (`UNKNOWN`). 전 요청이 순차였다.
- **재현성** (`UNKNOWN`). 조건당 1 trial의 파일럿이다.
- `LRUEvictionPolicy`가 선택되는 경로가 있는지 (`UNKNOWN`). 현재 `__init__`에 FIFO가 하드코딩되어 있다.

## 실패 / 무효 시도

- 무효로 판정한 측정은 없다. 9개 trial 전부 전 요청 status 200이고 token 수가 설계와 일치했다.
- 예측 6이 부분 오답이었다. 사후에 예측을 수정하지 않고 그대로 기록한다.
- 선등록한 판정 metric(층 1 `prefix_cache_hits_total`)이 실제 재사용을 나타내지 않는다는 것이 측정 중 드러났다. **판정 기준을 바꾸지 않고**, 선등록 metric의 결과와 층 2의 결과를 **둘 다** 보고한다.
- Device·RSD·package·patch 변경은 없었다. 9개 server lifecycle 모두 종료 후 device memory `0.0B` 복귀.

## 연구 원칙에 미치는 영향

- **metric이 "무엇을 세는지"와 "무엇을 알고 싶은지"가 다를 수 있다.** `prefix_cache_hits_total`은 [TASK09](TASK09.md)·[TASK11](TASK11.md)에서 값이 실제로 움직이는 것을 확인해 채택했지만, 그것이 곧 device 재사용을 뜻하지는 않았다. **신호 검증의 다음 단계는 "값이 움직이는가"가 아니라 "이 값이 내가 묻는 것을 세는가"다.**
- **두 층 구조에서는 두 층을 모두 계측한다.** 한 층만 보면 정반대 결론이 나온다.
- **자원의 단위를 실측으로 확인한다.** token 총량이 자연스러운 단위처럼 보였지만 실제 binding 자원은 outer block 개수였다. source 조사가 이를 미리 잡아 격자를 고칠 수 있었다.
- **확신도가 낮다고 표시한 예측이 맞을 수도 있다.** 예측 3과 7은 확신도가 낮다고 명시했는데 둘 다 적중했다. 표시의 목적은 사후 합리화 방지이지 예측의 품질 표시가 아니다.
- cache 판정에 latency를 쓰지 않는다는 원칙을 지켰다. latency는 결론과 일관됐지만 근거로 쓰지 않았다.

## 다음 작업

1. **층 1 문턱 좁히기** — B ∈ {20, 24, 28, 32}를 추가한다. 층 1과 층 2 문턱의 비가 pool 비(512/16 vs 8/1)와 맞는지 확인한다.
2. **재계산 확인** — 층 1이 hit을 보고했는데 층 2가 실패한 요청이 실제로 prefix를 재계산하는지 prefill token 수로 확인한다. 발견 3의 실무적 의미가 여기에 달려 있다.
3. **재현성** — 조건당 trial을 늘린다. 현재는 파일럿 1 trial이다.
4. **배경 요청 길이 sweep** — 배경 요청을 8,192 token에 가깝게 하면 두 문턱이 수렴하는지 본다.
5. 이후 모든 cache 실험에서 `[PFX] [CACHE-HIT]`/`[CACHE-PARTIAL]`을 실제 재사용의 1차 신호로 쓰고 `prefix_cache_hits_total`은 층 1 지표로만 쓴다.

사용자 지시 없이 다음 TASK를 자동 시작하지 않는다.

## 재현 정보

- 선등록 commit: `85c146bc34b14195d61b7b0ca881f95c7de75995`
- **측정 시작 시각: 2026-08-19 20:08:10 KST.** 선등록 commit 시각은 2026-08-19 20:07:52 KST이므로 **선등록이 측정보다 18초 앞선다.**
- 측정 종료 시각: `<RUN>/measurement-end.txt`
- Base commit (측정 중 HEAD): `85c146bc34b14195d61b7b0ca881f95c7de75995`, dirty = untracked `.idea/` 및 gitignored `results/`, `models/`
- **Patch state (측정 전 gate): `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`** — `<RUN>/patch-state.txt`
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)
- Prompt 생성 seed: `derive_block_seed(20260819, "<trial>/<role>")`. 고정 prompt는 `experiments/npu/stage2/gap_prompts.json` (git 추적)
- Raw artifact: `results/npu/stage2/20260819-200800-gap-turnover/`
  - `measurement-start.txt`, `measurement-end.txt`, `patch-state.txt`
  - `server-B{0,3,6,7,8,9,16,33,49}.log` — `[PFX]` 로그 전문
  - `probe/gap_turnover.B*.json` — 요청별 counter 증분과 생존율
  - `probe-B*.log`
  - `rbln-smi-before.txt`, `rbln-smi-final.txt`
- 실행 script: `experiments/npu/stage2/{build_gap_prompts.py,gap_turnover_probe.py}`
- Isolation launcher: `experiments/npu/launch/run_isolated_python.sh`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(**patched**), `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch 2.11.0+cpu`
- Host: `atom-max8`, device `rbln0`–`rbln3`
