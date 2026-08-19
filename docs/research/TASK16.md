# TASK16 — substrate descriptor v0와 관찰 층 태깅 규칙

## 상태

DONE

## 날짜

2026-08-19

## 목적

"연구 질문은 클래스 수준, 상수는 인스턴스 수준"이라는 보편성 지시를 **코드와 기록 체계에 구조화**한다. 지금까지 TASK11–15가 쌓은 상수들이 어느 층에 속하는지 문서와 자료구조 양쪽에서 강제한다.

측정이 없는 구조화 작업이므로 선등록 대상이 아니다.

## 배경

관련 TASK:

- [TASK13](TASK13.md) — decode step 비용을 `f(bucket) + g(actual)`로 분해. `step_cost_model`의 출처.
- [TASK14](TASK14.md) — 두 층의 pool 크기와 eviction 정책. `outer_slot_count`, 정책 field의 출처.
- [TASK15](TASK15.md) — 절벽 재현과 층 태그의 첫 적용. 이 TASK가 그 규칙을 정식화한다.
- [TASK11](TASK11.md) — hit 산식의 출처.
- [TASK08](TASK08.md) — block 크기 기본값의 source 근거.

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- Git commit: `8e4c5db995a89dddaf26f3e9aea9405c89958478` (TASK15 직후)
- Git dirty: untracked `.idea/`만
- 기존 `src/continuum/`: `workload/paired.py`, `analysis/validation.py`, `metrics/schema.py`, `policy/`
- Substrate: `patched` (측정을 하지 않으므로 gate 대상은 아니나 provenance로 기록)

## 수행 내용

1. `src/continuum/substrate/descriptor.py`를 신설했다. 가속기·vendor·stack 이름이 들어가지 않는 accelerator-neutral 코드다.
2. RBLN CA25 인스턴스를 `experiments/npu/substrate/`에 두어 neutral / backend 경계를 지켰다. TASK13/14/15 실측값으로 채웠다.
3. `TASK_GUIDE.md`에 "핵심 발견의 층 태그" 절을 신설하고 `## 핵심 발견` 구조 설명에 태그 의무를 명시했다.
4. TASK11–15의 핵심 발견에 대한 층 태그 일람표를 아래에 작성했다. **기존 TASK 문서 원문은 수정하지 않았다.**

## 변경된 파일

- `src/continuum/substrate/__init__.py` (신규)
- `src/continuum/substrate/descriptor.py` (신규)
- `experiments/npu/substrate/rbln_ca25_vllm_rbln_0111.py` (신규)
- `docs/research/TASK_GUIDE.md` (층 태그 절 신설)
- `docs/research/TASK16.md` (신규)
- `docs/research/INDEX.md`

## 1. Substrate descriptor v0

### 설계 원칙

**모든 기술 field가 `Provenance`를 요구하고, 누락되면 생성이 실패한다.** 이것이 이 모듈의 존재 이유다 — 출처 없는 상수가 descriptor에 들어가지 못하게 한다.

```python
missing = [f.name for f in fields(self)
           if f.name not in self._UNATTRIBUTED and f.name not in self.provenance]
if missing:
    raise ValueError(f"missing provenance for: {sorted(missing)}")
```

`Provenance`는 `layer`(4개 태그 중 하나), `origin`(값을 확정한 TASK), `kind`(`measured` / `derived` / `source-read`), `note`를 갖는다. `layer`와 `kind`는 허용 집합 밖이면 즉시 `ValueError`다.

### 필드

| 필드 | 뜻 |
|---|---|
| `bucket_sizes` | compile된 decode batch bucket의 오름차순 tuple |
| `step_cost_model` | `fixed_s_by_bucket` + `intercept_s` + `marginal_s_per_request`. `step_time(actual) = fixed[bucket(actual)] + intercept + marginal × actual` |
| `outer_slot_count`, `outer_slot_tokens` | 상위 block pool의 개수와 크기 |
| `inner_block_tokens`, `inner_block_count` | 하위 block의 크기와 개수 |
| `outer_eviction_policy`, `inner_eviction_policy` | 두 층의 정책 (서로 다를 수 있다) |
| `hit_formula` | `floor(min(shared, query−1)/block) × block` |
| `kv_pool_tokens` | 물리 KV pool 용량 |
| `provenance` | field 이름 → `Provenance` |
| `notes` | 이 인스턴스에 붙는 경고·단서 |

### 파생 연산

| 메서드 | 내용 |
|---|---|
| `bucket_for(actual)` | actual 이상인 최소 bucket |
| `padding_slots(actual)` | `bucket − actual` |
| `step_time_s(actual)` | 비용 모형 적용 |
| `bucket_crossing_cost_s(actual)` | 아래 bucket 대비 고정비 증가분. **slot당 단가는 정의하지 않는다** — padding된 크기의 bucket이 존재하지 않아 비교 대상이 없기 때문이다 |
| `outer_slots_for(tokens)` | 요청 1개가 차지하는 상위 slot 수 |
| `survives_gap(...)` | [TASK15](TASK15.md)의 법칙 후보. docstring에 **가설이지 불변식이 아님**을 명시했다 |
| `layer_summary()` | field를 층별로 묶어 반환 |

`__post_init__`은 bucket 오름차순·유일성, 양수성, `outer_slot_tokens % inner_block_tokens == 0`, `hit_formula.block_tokens == inner_block_tokens`를 검사한다.

### 인스턴스의 자기 반증 장치

`experiments/npu/substrate/rbln_ca25_vllm_rbln_0111.py`는 [TASK13](TASK13.md)의 관측 ITL과 [TASK14](TASK14.md)·[TASK15](TASK15.md)의 관측 생존을 파일 안에 함께 담고, 실행 시 모형 예측과 대조해 잔차를 출력한다. 상수를 나중에 손대면 표에서 바로 드러난다.

```text
 actual  bucket  padding  model (ms)  observed   resid  crossing (ms)
      1       1        0      10.412    10.379   0.033          0.000
      2       2        0      11.004    10.975   0.029          0.550
      3       4        1      11.450    11.482  -0.032          0.405
      4       4        0      11.491    11.569  -0.078          0.405
      5       8        3      13.678    13.632   0.046          2.145
      6       8        2      13.719    13.696   0.023          2.145
      7       8        1      13.760    13.785  -0.025          2.145
      8       8        0      13.801    13.795   0.006          2.145
  worst |residual| = 0.078 ms

gap survival: B=0,3,5,6 model=live observed=live / B=7,8 model=dead observed=dead  (6/6 ok)
```

**최대 잔차 0.078 ms (0.7 %)**, 생존 예측은 관측이 있는 6개 지점에서 **6/6 일치**한다.

### 층 요약

```text
class    : hit_formula, inner_eviction_policy
silicon  : step_cost_model
stack    : bucket_sizes, inner_block_count, inner_block_tokens,
           kv_pool_tokens, outer_eviction_policy, outer_slot_count,
           outer_slot_tokens
```

## 2. 층 태깅 규칙 (`TASK_GUIDE.md` 개정)

`## 핵심 발견`의 각 항목에 태그를 **의무화**했다.

| 태그 | 뜻 | 판정 기준 |
|---|---|---|
| `silicon` | 이 가속기 하드웨어 고유 | 다른 가속기로 바꾸면 값이 달라진다고 볼 근거가 있다 |
| `stack` | 이 software stack·버전·compile 구성 고유 | 같은 하드웨어라도 stack/구성을 바꾸면 달라진다 |
| `class` | 이 종류 일반에 적용될 것으로 보이는 성질 | 기전이 특정 구현이 아니라 설계 범주에서 나온다. 추론이므로 근거를 함께 적는다 |
| `universal` | 가속기·stack과 무관 | 방법론·측정 원칙 |

핵심 작성 규칙 5개를 명문화했다. 그중 3·4가 이 작업의 요점이다.

> **3. 인스턴스 상수를 클래스로 이식하지 않는다.** `class` 태그는 *형태*(법칙의 모양, 기전)에만 붙이고 *값*에는 붙이지 않는다. "outer slot이 8개다"는 절대 `class`가 아니다.
>
> **4.** `class`로 태그하려면 **왜 이 구현에 국한되지 않는지**를 한 줄로 적는다. 적을 수 없으면 `stack`이다.

## 3. TASK11–15 핵심 발견의 층 태그 일람

기존 TASK 문서 원문은 수정하지 않았다. 이 표가 소급 태깅의 단일 출처다.

### TASK11 — prefix cache hit 경계

| # | 발견 요약 | 태그 | 근거 |
|---|---|---|---|
| 1 | hit 단위가 inner block이고 양이 `floor((n−1)/128)×128` | `class`(산식) + `stack`(128) | 산식은 vLLM `find_longest_cache_hit`의 형태이므로 vLLM 계열 일반. 128은 `prefill_chunk_size` 기본값 |
| 2 | 짧은 prompt에서 hit이 구조적으로 0 | `class` | `max_num_blocks = (n−1) // block`이라는 형태에서 나온다. 문턱값 129는 `stack` |
| 3 | `get_one_block`의 중복 block 요구가 binding이 아님 | `stack` | 이 override는 vllm-rbln 고유 |
| 4 | `prompt_tokens_cached_total`이 hits와 같았다 | **정정됨** | [TASK15](TASK15.md)가 층 2가 항상 hit하던 regime의 과잉일반화임을 밝혔다. 실제로는 `stack` — 두 metric이 다른 층을 센다 |
| 5 | APC OFF/ON이 단일 인자 토글이 아님 (block 입도 동반 변화) | `stack` | `update_block_size`의 else 분기가 vllm-rbln 고유 |
| 6 | `[PFX] [CACHE-HIT]`가 OB/IB ID를 노출 | `stack` | vllm-rbln 로그 |
| 7 | 조건 간 prefix 오염 | `universal` | 실험 설계의 문제이지 substrate 문제가 아니다 |

### TASK12 — bucket 관측 patch

| # | 발견 요약 | 태그 | 근거 |
|---|---|---|---|
| 1 | per-step bucket이 관측 가능해짐 | `stack` | patch 대상이 vllm-rbln 고유 함수 |
| 2 | 신호 의미론을 채택 전에 검증 | `universal` | 방법론 |
| 3 | 관찰자 효과가 자릿수 수준에서 없음 | `stack` | 이 patch·이 경로에 대한 관측 |
| 4 | `.pyc` 캐시가 patch를 무력화하지 않음 | `universal` | CPython 동작 |
| 5 | `patches/` 정책이 실전에서 작동 | `universal` | 절차 |
| 6 | bucket padding 낭비의 정량화 | `class`(현상) + `stack`(값) | 고정 bucket을 쓰는 어느 stack에서나 padding이 생긴다. 25 %/37.5 %는 이 bucket 격자의 값 |

### TASK13 — decode step 비용 모형

| # | 발견 요약 | 태그 | 근거 |
|---|---|---|---|
| 1 | 같은 bucket 안에서도 end-to-end ITL이 다름 | `class` | per-request host 작업이 있는 어느 stack에서나 기대된다 |
| 2 | model span은 bucket 결정적, actual 의존은 engine overhead에 있음 | `class`(분해 형태) + `silicon`/`stack`(값) | static compiled graph라면 어디서나 성립할 형태. 9.51/10.05/10.355/12.4025 ms는 이 하드웨어·모델 값 |
| 3 | bucket 효과가 actual 효과를 지배 | `stack` | 두 항의 비는 bucket 격자와 구현에 달려 있다 |
| 4 | `4 → 5` 전이가 +17.8 %로 가장 큼 | `stack` | 이 bucket 격자의 값 |
| 5 | sampler도 bucket 결정적 | `stack` | RBLN sampler 구현 |
| 6 | 채널 C가 client threading에 오염되지 않음 | `universal` | 측정 방법론 |
| 7 | 1초 해상도 로그도 교차 확인에 쓸 만함 | `universal` | 방법론 |
| 8 | `[BUCKET]` 사상표 완성 | `stack` | `select_bucket_size`와 이 bucket 격자 |

### TASK14 — 생존/eviction 파일럿

| # | 발견 요약 | 태그 | 근거 |
|---|---|---|---|
| 1 | 체제 경계의 첫 좌표 (B = 7) | `stack` | slot 수 8에 직접 의존 |
| 2 | 생존을 결정하는 것이 token 총량이 아니라 요청 개수 | `class`(형태) + `stack`(조건) | 고정 크기 slot에 요청을 매핑하는 어느 구조에서나 생기는 현상. "8,192 이하면 1개"는 이 구성 |
| 3 | `prefix_cache_hits_total`이 실제 재사용을 과대보고 | `stack` | 2층 장부 분리가 vllm-rbln 고유 |
| 4 | 두 층의 문턱이 4~5배 차이 | `stack` | 두 pool 크기의 비 |
| 5 | eviction이 FIFO이고 target이 먼저 희생 | `stack` | `FIFOEvictionPolicy` 하드코딩 |
| 6 | 부분 생존 구간 없음 | `class`(형태) + `stack`(조건) | prefix가 slot 1개에 통째로 들어가면 all-or-nothing. 2,000 ≤ 8,192가 그 조건 |
| 7 | 층 1의 hit이 시간을 절약하지 못함 | `stack` | 발견 3의 귀결 |

### TASK15 — 절벽 재현과 attribution

| # | 발견 요약 | 태그 | 근거 |
|---|---|---|---|
| 1 | 절벽이 12/12 결정적으로 재현 | `stack` + `class` | 절벽의 존재(고정 slot + 부분 생존 없음)는 `class`, FIFO·slot 8은 `stack` |
| 2 | metric 거짓 양성 100 % | `stack` | 2층 장부 분리 |
| 3 | 층 2를 세는 Prometheus metric이 이미 존재 | `stack` | `prefill_stats` 배선이 vllm-rbln 고유 |
| 4 | metric은 "어느 층에서 세는지"로 검증해야 한다 | `universal` | 방법론 |
| 5 | 층 2 miss 시 실제 재계산이 일어남 | `stack` | 이 stack의 복구 경로 |
| 6 | prefill이 요청당 device forward 1회 | `stack` | optimum-rbln 내부 chunking |
| 7 | `iteration_tokens_total`이 계산량 지표가 아님 | `class` | vLLM 계열 공통 metric의 의미 |

### 태그 분포

| 태그 | 항목 수 |
|---|---|
| `stack` (단독) | 20 |
| `class` (단독 또는 병기) | 11 |
| `universal` | 7 |
| `silicon` (병기) | 1 |

**대부분이 `stack`이다.** 이는 지금까지의 발견이 대체로 이 software stack의 구조에 대한 것이며, 다른 substrate로 옮기기 전에 재측정이 필요하다는 뜻이다. `class`로 태그한 11개가 이식 후보이고, 그중에서도 *형태*만 이식 가능하며 값은 다시 재야 한다.

## 핵심 발견

1. **`universal`** — **상수에 출처를 강제하면 층 혼동이 구조적으로 막힌다.** `SubstrateDescriptor`는 provenance 없는 field로는 생성되지 않는다. 문서 규칙만으로는 지키기 어려운 원칙을 자료구조가 강제한다.
2. **`universal`** — **descriptor에 관측값을 함께 담으면 모형이 반증 가능해진다.** 인스턴스 파일이 예측·관측·잔차를 함께 출력하므로 상수를 손대면 즉시 드러난다. 최대 잔차 0.078 ms, 생존 예측 6/6 일치.
3. **`stack`** — **지금까지의 발견 39개 중 20개가 `stack` 단독이다.** 다른 가속기·stack으로 결론을 옮기려면 대부분을 다시 재야 한다. 이식 후보는 `class` 11개의 *형태*뿐이다.
4. **`universal`** — **`class` 태그에는 "왜 이 구현에 국한되지 않는가"를 요구해야 한다.** 그 한 줄을 쓸 수 없으면 `stack`이다. 이 규칙이 없으면 `class`가 희망사항 표시로 변질된다.
5. **`class`** — **padding의 slot당 단가는 정의할 수 없다.** padding된 크기의 bucket이 존재하지 않아 비교 대상이 없다. 관측 가능한 것은 bucket 사이의 계단뿐이며, descriptor는 `bucket_crossing_cost_s`만 제공한다. 고정 bucket을 쓰는 어느 substrate에서나 같은 제약이 생긴다.

## 해석

이하는 관찰이 아닌 해석이다.

- **(해석)** `step_cost_model`을 `silicon`으로 태그했지만 엄밀히는 `silicon` + `stack` + 모델 크기의 합성이다. 같은 CA25에서 다른 모델을 compile하면 값이 달라진다. 단일 태그를 강제한 것이 아니라 **주된 의존처**를 표시한 것으로 읽어야 하며, `note`에 "hardware and model specific"을 남겼다.
- **(해석)** `inner_eviction_policy`를 `class`로 태그한 것은 그 값(LRU)이 vLLM upstream의 것이어서 vLLM 계열 어느 build에서나 같기 때문이다. 반대로 `outer_eviction_policy`(FIFO)는 vllm-rbln 고유라 `stack`이다. **같은 종류의 field라도 층이 다를 수 있다**는 예다.
- **(해석)** `survives_gap`을 descriptor의 메서드로 넣은 것은 법칙 후보를 코드로 고정해 이후 측정이 그것을 반증할 수 있게 하기 위해서다. docstring에 "hypothesis about this substrate's shape, not a proven invariant"를 명시했다.

## 확인되지 않은 사항

- `class`로 태그한 11개 항목이 실제로 다른 substrate에서 성립하는지 (`UNKNOWN`). 이식 검증은 다른 가속기·stack이 있어야 가능하다.
- `step_cost_model`의 값이 모델 크기에 어떻게 의존하는지 (`UNKNOWN`). 단일 모델에서만 쟀다.
- descriptor의 field 집합이 충분한지 (`UNKNOWN`). v0이며 이후 측정이 요구하면 확장한다. 특히 prefill 비용, host↔device 전송, 동시성 하의 거동을 담는 field가 아직 없다.
- `bucket_crossing_cost_s`가 fixed cost 차이만 보는 것이 적절한지 (`UNKNOWN`). marginal 항은 actual에만 의존하므로 bucket 전이와 무관하다는 [TASK13](TASK13.md) 분해에 기댄 선택이다.

## 실패 / 무효 시도

- 초기 `padding_cost_s` 구현이 "padding된 크기의 bucket"과 비교하려다 정의되지 않은 양을 계산했고 사용하지 않는 지역 변수까지 남았다. `bucket_crossing_cost_s`로 교체하고 slot당 단가를 정의할 수 없는 이유를 docstring에 남겼다.
- 측정이 없으므로 무효 측정도 없다. Device·RSD·package·patch 변경 없음.

## 연구 원칙에 미치는 영향

- **핵심 발견에 층 태그를 붙이는 것이 이제 필수다** (`TASK_GUIDE.md`).
- **`class` 태그는 근거 한 줄을 동반해야 한다.** 없으면 `stack`으로 내린다.
- **상수를 코드로 옮길 때는 출처를 함께 옮긴다.** provenance 없는 상수는 descriptor에 들어가지 못한다.
- **모형은 관측과 함께 저장한다.** 예측만 담긴 모형은 나중에 조용히 틀려진다.
- accelerator-neutral 코드(`src/continuum/`)와 backend 인스턴스(`experiments/npu/`)의 경계를 유지한다.

## 다음 작업

1. agentic workload generator v0와 bucket 전이 첫 관측 (같은 batch의 다음 작업).
2. descriptor field 확장은 필요가 생길 때 한다. 미리 넓히지 않는다.
3. `class` 태그 항목의 이식 검증은 다른 substrate가 생길 때까지 보류한다.

사용자 지시 없이 다음 TASK를 자동 시작하지 않는다.

## 재현 정보

- Base commit: `8e4c5db995a89dddaf26f3e9aea9405c89958478` (이 TASK의 commit이 그 다음)
- 선등록 commit: 해당 없음 (측정이 없는 구조화 TASK)
- 신규 코드: `src/continuum/substrate/{__init__.py,descriptor.py}`, `experiments/npu/substrate/rbln_ca25_vllm_rbln_0111.py`
- 인스턴스 확인: `env -u PYTHONPATH python3 experiments/npu/substrate/rbln_ca25_vllm_rbln_0111.py`
- 상수의 출처: [TASK08](TASK08.md), [TASK11](TASK11.md), [TASK13](TASK13.md), [TASK14](TASK14.md), [TASK15](TASK15.md)
- Substrate 상태: `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01` (측정은 없으나 상수가 이 상태에서 측정됐다)
- Host: `atom-max8`
