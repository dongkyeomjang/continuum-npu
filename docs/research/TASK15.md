# TASK15 — B = 7 절벽 재현과 resume attribution 확정

## 상태

DONE

## 판정

- **판정 1 (절벽 재현): 재현됨.** B ∈ {5, 6}의 6 trial 전부 층 2 재사용 = 1,920, B ∈ {7, 8}의 6 trial 전부 = 0. **12/12 일치**, 예외 없음.
- **판정 2 (metric 거짓 양성 재현): 재현됨.** B ∈ {7, 8}의 6 trial 전부에서 `prefix_cache_hits_total` = 1,920 **이면서** 층 2 재사용 = 0.
- **판정 3 (실제 재계산): 재계산 확정.** 다만 선등록한 1차 채널의 **산술 전제가 깨져** 선등록한 fallback 규칙(`PARTIAL`, 채널 2·3으로 기술)을 적용했고, 여기에 device-side 독립 증거를 추가했다. 종합 판정은 확정이며 근거는 아래에 분리해 기록한다.

## 날짜

2026-08-19

## 목적

[TASK14](TASK14.md) 파일럿의 두 헤드라인 후보(절벽, metric 거짓 양성)를 반복 측정으로 굳히고, [TASK14](TASK14.md)가 `UNKNOWN`으로 남긴 "층 1 hit / 층 2 miss 상태에서 실제로 재계산이 일어나는가"를 확정한다.

## 배경

관련 TASK:

- [TASK14](TASK14.md) — 파일럿. 조건당 1 trial이었고 재계산 여부는 `UNKNOWN`이었다.
- [TASK11](TASK11.md) — hit 산식과 `prompt_tokens_cached_total`의 `UNKNOWN`.
- [TASK13](TASK13.md) — PREFILL/DECODE METRICS 채널의 선례.

선등록 문서: [CLIFF_REPRO_PREREG.md](CLIFF_REPRO_PREREG.md)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `2d79431917510dbc161541e1bd46d5353a32bf05`
- Git dirty: untracked `.idea/`만
- **Substrate: patched** (SHA256 `70942d16…`). 측정 전 gate 통과
- Host: `atom-max8`. Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(patched), `optimum-rbln 0.11.1`
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)
- Device: 32 visible ID 전부 idle, port 8000 비어 있음

## 수행 내용

1. **측정 전 source 조사로 각 Prometheus 채널의 층 귀속을 확정**했다 (선등록 문서에 추적 경로 기록).
2. 그 결과를 [TASK14](TASK14.md)의 raw artifact에 적용해 사후 검증했다 — `prompt_tokens_cached_total`이 `[PFX]` 로그와 정확히 일치함을 확인했다.
3. probe의 counter 목록을 층별로 확장하고, prompt 생성기에 replicate를 추가했다. base seed를 20260819 → **20260820**으로 바꿔 prompt를 새로 뽑았다 (재현이지 반복이 아니어야 하므로).
4. 선등록 문서·script·prompt를 **측정 시작 전에** commit했다 (`2d79431`).
5. Patch state gate 통과 후 trial 12개를 **trial마다 fresh server**로 실행했다.
6. 채널 6종을 대조해 판정했다.

재compile, download, patch 변경, RSD 변경은 없었다.

## 변경된 파일

선등록 commit `2d79431`:

- `docs/research/CLIFF_REPRO_PREREG.md` (신규)
- `experiments/npu/stage2/build_gap_prompts.py` (`--replicates` 추가)
- `experiments/npu/stage2/gap_turnover_probe.py` (counter 목록을 층별로 확장)
- `experiments/npu/stage2/cliff_prompts.json` (신규, tokenizer 실측 고정)

이번 기록 commit:

- `docs/research/TASK15.md` (신규)
- `docs/research/INDEX.md` (`prompt_tokens_cached_total` 서술 정정 포함)

Raw artifact는 `.gitignore` 대상인 `results/npu/stage2/20260819-204900-cliff-repro/`에 있다.

## 실험 또는 검증 방법

`<RUN>` = `results/npu/stage2/20260819-204900-cliff-repro`

trial 12개(`B5r0`…`B8r2`) 각각:

```bash
env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG VLLM_RBLN_METRICS=1 \
  vllm serve /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb \
  --host 127.0.0.1 --port 8000 --enable-prefix-caching > <RUN>/server-<K>.log 2>&1 &

env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage2/gap_turnover_probe.py \
  --base-url http://127.0.0.1:8000 \
  --prompts-file /home/rebel/continuum-npu/experiments/npu/stage2/cliff_prompts.json \
  --trial <K> --max-tokens 8 --seed 20260819 \
  --output-dir /home/rebel/continuum-npu/<RUN>/probe

# PID 특정 후 SIGTERM
```

## 결과

### 조건 분리

- `requested_condition`: B ∈ {5,6,7,8} × 3 trial, target·배경 각 2,000 token(유일), suffix 8 token, `max_tokens=8`, greedy, seed 20260819, 동시성 1, `enable_prefix_caching=True`, trial마다 fresh server.
- `observed_condition`: 전 요청 status 200. resume prompt 2,008 token. patch state 전 구간 `patched`. 배경 token 합이 `B × 2,000`.
- `condition_reached`: `YES`.

### 관찰 — 채널 6종 (12 trial)

Population: trial 12개의 resume 요청. Unit: token, 초, 개수. Source: `/metrics` 증분, server DEBUG 로그, `VLLM_RBLN_METRICS`. Device scope: `rbln0`–`rbln3`.

| trial | B | 층 1 `hits` | 층 2 `cached` | `prefill_kv_computed` | `iteration_tokens` | PREFILL calls | evict | `[PFX]` | resume prefill 시간 | e2e (참고) |
|---|---|---|---|---|---|---|---|---|---|---|
| B5r0/r1/r2 | 5 | 1,920 | **1,920** | **88** | 2,016 | 7 | 0 | `CACHE-HIT` | **0.0274 / 0.0272 / 0.0274 s** | 0.111–0.113 |
| B6r0/r1/r2 | 6 | 1,920 | **1,920** | **88** | 2,016 | 8 | 1 | `CACHE-HIT` | **0.0272 / 0.0275 / 0.0275 s** | 0.111–0.112 |
| B7r0/r1/r2 | 7 | 1,920 | **0** | **2,008** | 2,016 | 9 | 2 | `CACHE-PARTIAL` 0/1920 | **0.3593 / 0.3594 / 0.3589 s** | 0.445–0.446 |
| B8r0/r1/r2 | 8 | 1,920 | **0** | **2,008** | 2,016 | 10 | 3 | `CACHE-PARTIAL` 0/1920 | **0.3590 / 0.3589 / 0.3589 s** | 0.446–0.447 |

**12/12 trial에서 값이 완전히 결정적이다.** 같은 B의 3 trial이 층 1/층 2/계산량 채널에서 동일한 값을 냈고, 시간 채널만 소수 넷째 자리에서 흔들렸다.

### 판정 1 — 절벽 재현: **재현됨**

B ≤ 6에서 층 2 재사용 = 1,920 (6/6), B ≥ 7에서 = 0 (6/6). 부분 생존 구간 없음. [TASK14](TASK14.md)의 파일럿이 새 prompt·새 seed로 그대로 재현됐다.

### 판정 2 — metric 거짓 양성 재현: **재현됨**

B ∈ {7, 8}의 6 trial 전부에서 층 1 `prefix_cache_hits_total` = **1,920**(전량 hit 보고)인데 층 2 실제 재사용 = **0**이다.

### 판정 3 — 실제 재계산 attribution

#### 선등록 1차 채널의 전제 실패

선등록은 `resume_chunks = PREFILL_total_calls − 16 × (B + 1)`로 계산하고 배경·target 요청이 각각 16 chunk를 쓴다고 전제했다. **관측된 `PREFILL Total call counts`는 `B + 2`(7/8/9/10)로 요청 수와 정확히 같았다.**

즉 optimum 경로의 prefill은 **요청 1개당 model forward 1회**다 (`decoder_only.py:forward`의 `self.model.prefill_decoder(**kwargs)`가 prompt 전체를 한 번에 처리하고 chunking은 optimum-rbln 내부에서 일어난다). `max_num_batched_tokens = 128`은 scheduler의 chunk 예산이지 device 호출 횟수가 아니다.

산식이 음수(`−89` 등)를 내므로 **선등록한 fallback 규칙에 따라 이 채널을 판정에서 제외**하고 `PARTIAL`로 표시했다. 산식을 사후에 고쳐 쓰지 않았다.

#### 채널 2·3 (선등록 fallback)

| 채널 | B ≤ 6 | B ≥ 7 | 층 |
|---|---|---|---|
| `vllm:request_prefill_kv_computed_tokens_sum` | **88** | **2,008** | 층 2 파생 |
| `vllm:prompt_tokens_cached_total` | 1,920 | 0 | 층 2 |
| `[PFX]` | `CACHE-HIT` | `CACHE-PARTIAL` REUSED=0/1920 | 층 2 |

`prefill_kv_computed`가 88 → 2,008로 바뀐다. 이는 **선등록 예측 4와 정확히 일치**한다.

#### 독립 device-side 증거 (선등록에서 "보조"로 분류했던 채널)

`vllm:request_prefill_time_seconds` resume 증분:

| B | 5 | 6 | 7 | 8 |
|---|---|---|---|---|
| 초 | 0.0273 | 0.0274 | **0.3592** | **0.3589** |

**13.1배 차이**다. `VLLM_RBLN_METRICS`의 PREFILL mean latency도 같은 것을 보여준다.

| B | PREFILL mean (ms), 3 trial |
|---|---|
| 5 | 310.38 / 310.00 / 309.90 |
| 6 | 316.89 / 315.98 / 316.24 |
| 7 | **356.99 / 357.40 / 357.17** |
| 8 | **357.21 / 356.99 / 357.24** |

B ≤ 6의 mean이 낮은 것은 **빠른 호출 1개(resume, 약 27 ms)가 평균을 끌어내리기 때문**이다. B5는 7회 호출 중 6회가 약 357 ms, 1회가 약 27 ms → 평균 310.3. B6는 8회 중 7회 → 315.8. 산술이 관측과 맞는다. B ≥ 7에서는 그 빠른 호출이 **사라지고** 전 호출이 약 357 ms다.

이 채널은 model forward 실행 시간이므로 **층 1·층 2 어느 쪽의 장부와도 무관**하다.

> **원칙 준수 확인**: 저장소 원칙은 "cache source를 latency로 판정하지 않는다"이다. 이번에 cache hit/miss 판정은 counter와 `[PFX]` 로그로 했고, latency는 **계산량의 크기**를 확인하는 데만 썼다. 두 용도를 구분해 기록한다.

#### 종합

세 계열(층 2 counter, 층 2 파생 계산량, device 실행 시간)이 **전부 같은 방향**이며 서로 모순이 없다. **B ≥ 7에서 resume 요청은 prefix 1,920 token을 실제로 재계산한다.** [TASK14](TASK14.md)의 `UNKNOWN`이 닫혔다.

선등록한 "반증" 조건(B ≥ 7에서 `resume_chunks = 1`, 즉 재계산이 없는데 KV도 없는 정합성 문제)은 **발생하지 않았다.**

### 관찰 — 판정에 쓰지 못한 채널

| 채널 | 결과 | 이유 |
|---|---|---|
| `PREFILL Total call counts` | B+2 (요청 수) | prefill이 요청당 forward 1회. 계산량과 무관 |
| `vllm:iteration_tokens_total_sum` | **전 조건 2,016** | 층 2를 반영하지 않는다. 선등록에서 "층 2 파생"으로 분류한 것은 **오분류**였다 |

`iteration_tokens`가 2,016(= prompt 2,008 + 생성 8)으로 고정된 것은 이 metric이 **제출된 prompt token 수**를 세지 실제 계산량을 세지 않는다는 뜻이다.

### 부수 관측

- eviction 수: B5 → 0, B6 → 1, B7 → 2, B8 → 3. [TASK14](TASK14.md)의 `B − 5`(B ≥ 6)가 재현됐다. 산술 예상 `B − 6`과의 1 차이는 여전히 `UNKNOWN`이다.
- 층 1 문턱(16 < B ≤ 33)의 정밀화는 선등록대로 **하지 않았다.**

### 사전 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| 1 | 절벽 B = 7에서 3/3 재현 | ✓ (실제로는 4개 B × 3 trial = 12/12) |
| 2 | B ≥ 7에서 층 1 = 1,920 & 층 2 = 0 | ✓ 6/6 |
| 3 | resume 계산량 88(B≤6) / 2,008(B≥7) | ✓ (채널 2·3과 device 시간이 지지) |
| 4 | `prefill_kv_computed` = 88 / 2,008 | ✓ 정확히 일치 |
| 5 | `prompt_tokens_cached` = 1,920 / 0 | ✓ |
| 6 | eviction 수 = `B − 5` (B ≥ 6) | ✓ |
| 7 | e2e latency 약 0.11 / 0.45 s | ✓ (판정 미사용) |

7개 전부 적중. 다만 예측을 검증하는 **1차 채널의 전제**가 깨졌고 그 사실을 위에 기록했다.

## 핵심 발견 (층 태그 적용)

층 태그: `silicon`(이 가속기 고유) / `stack`(이 software stack 고유) / `class`(이 종류 일반) / `universal`(무관).

1. **`stack` + `class`** — **재사용 절벽이 결정적으로 재현된다.** 12/12 trial에서 값이 완전히 동일했다. 확률적 현상이 아니라 자원 회계의 결정적 결과다. 절벽의 **존재**(고정 slot pool + 부분 생존 없음)는 이 종류의 stack 일반에서 기대할 수 있고(`class`), FIFO·slot 8이라는 **구체**는 이 stack·인스턴스 고유다(`stack`).
2. **`stack`** — **`prefix_cache_hits_total`은 실제 재사용을 100 % 과대보고할 수 있다.** 이 거짓 양성은 vllm-rbln의 2층 장부 분리에서 나온다. 층이 하나인 stack에서는 발생하지 않는다.
3. **`stack`** — **층 2를 세는 Prometheus metric이 이미 존재한다.** `vllm:prompt_tokens_cached_total`과 `vllm:request_prefill_kv_computed_tokens`가 `prefill_stats`(= `sum(cached_length)`, 층 2)에서 나온다. [TASK14](TASK14.md)는 `[PFX]` DEBUG 로그가 유일한 층 2 채널이라고 보았으나 그렇지 않다. **DEBUG 없이도 층 2를 관측할 수 있다.**
4. **`universal`** — **metric은 "무엇을 세는지"가 아니라 "어느 층에서 세는지"로 검증해야 한다.** 이름과 값의 변화만으로는 부족하다. 같은 이름의 두 metric(`hits` vs `cached`)이 서로 다른 층을 세고 있었다.
5. **`stack`** — **재계산이 실제로 일어난다.** 층 2가 KV 복사원을 잃으면 resume은 prefix 전량을 재계산한다. prefill 실행 시간이 13.1배 늘었고 `prefill_kv_computed`가 88 → 2,008로 바뀌었다. 정합성 문제(계산도 KV도 없는 상태)는 발생하지 않는다.
6. **`stack`** — **prefill은 요청당 device forward 1회다.** `max_num_batched_tokens = 128`은 scheduler의 chunk 예산이며 device 호출 횟수가 아니다. optimum-rbln이 내부에서 chunk한다. 이 때문에 "chunk 수로 계산량을 세는" 접근이 이 경로에서는 통하지 않는다.
7. **`stack`** — **`iteration_tokens_total`은 계산량 지표가 아니다.** 층 2 miss 여부와 무관하게 제출 prompt token 수를 센다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(법칙 후보, 가설)** 관찰을 다음으로 재기술할 수 있다.

  > **생존 ⇔ (target 1 + gap 중 도착 요청 B + resume 1) ≤ `outer_slot_count`**

  이 인스턴스에서 `outer_slot_count = 8`이므로 `B ≤ 6`이고, 관측(B6 생존, B7 소멸)과 정확히 맞는다. resume 자신도 slot을 요구한다는 점이 `−2`의 출처다.

  **이 법칙의 형태는 `class`, 상수 8은 `silicon`/인스턴스**다. 상수를 다른 가속기·구성으로 이식하면 안 된다. `outer_slot_count`는 compile 시 `batch_size`에서 유도되므로([TASK08](TASK08.md)) 같은 하드웨어에서도 구성에 따라 달라진다.

- **(해석)** 발견 3은 관측 비용을 크게 낮춘다. 층 2 관측에 `VLLM_LOGGING_LEVEL=DEBUG`가 필요 없다면 production-like 조건에서도 같은 신호를 얻을 수 있다. 다만 `[PFX]` 로그만 주는 정보(어느 OB/IB가 재사용됐는지)는 metric으로 대체되지 않는다.
- **(해석)** 발견 6은 [TASK13](TASK13.md)의 채널 B 해석에도 적용된다. 그 TASK의 "PREFILL Total call counts"도 chunk 수가 아니라 요청 수였을 것이다. TASK13의 판정은 DECODE 채널로 했으므로 결론은 영향받지 않지만, PREFILL 관련 서술을 인용할 때 주의해야 한다.
- **(hypothesis)** 재계산 시 prefill 시간이 0.359 s인데 이는 배경 요청(2,000 token, cache 없음)의 약 0.357 s와 거의 같다. 즉 **층 1의 hit이 계산을 전혀 절약하지 못했다.** 층 1의 장부가 device 작업에 아무 영향을 주지 못한다는 뜻으로 보이나, 층 1 hit이 있을 때와 없을 때(B33 같은 조건)의 prefill 시간을 직접 비교하지는 않았다.

## 확인되지 않은 사항

- eviction 수가 `B − 6`이 아니라 `B − 5`인 이유 (`UNKNOWN`, [TASK14](TASK14.md)에서 이월, 재현됨).
- 층 1 hit이 **있을 때**와 **없을 때**의 재계산 비용 차이 (`UNKNOWN`). B33 같은 조건과 직접 비교하지 않았다.
- `outer_slot_count`가 8이 아닌 구성(다른 `batch_size`로 compile)에서 법칙 후보가 그대로 성립하는지 (`UNKNOWN`). 재compile이 필요하다.
- target prefix가 outer block 2개 이상을 차지할 때(> 8,192 token) 부분 생존이 생기는지 (`UNKNOWN`). `max_seq_len` 제약으로 현재 artifact에서는 관측 불가.
- 동시성 > 1에서의 거동 (`UNKNOWN`). 전 요청이 순차였다.
- `iteration_tokens_total`이 정확히 무엇을 세는지의 source 확정 (`UNKNOWN`). 값이 제출 prompt token과 일치한다는 관측만 있다.

## 실패 / 무효 시도

1. **선등록한 1차 판정 채널의 산술 전제가 깨졌다.** `PREFILL Total call counts`가 chunk 수라고 전제했으나 요청 수였다. 선등록한 fallback 규칙(`PARTIAL` 표시 후 채널 2·3으로 기술)을 그대로 적용했고 **산식을 사후에 고쳐 쓰지 않았다.**
2. **선등록에서 `iteration_tokens_total`을 "층 2 파생"으로 분류한 것은 오분류였다.** 실측에서 전 조건 2,016으로 고정이었다. 오분류 사실을 기록하고 판정에서 제외했다.
3. 무효로 판정한 측정은 없다. 12 trial 전부 status 200.
4. Device·RSD·package·patch 변경 없음. 12 server lifecycle 모두 종료 후 device memory `0.0B` 복귀, context 소멸.

## 연구 원칙에 미치는 영향

- **채널의 층 귀속을 source에서 확정한 뒤 선등록한다.** 이번에 그렇게 했기 때문에 `prompt_tokens_cached`가 층 2라는 것을 측정 전에 알았고, [TASK14](TASK14.md)의 데이터를 사후 재해석해 [TASK11](TASK11.md)의 `UNKNOWN`까지 닫을 수 있었다.
- **1차 채널이 실패할 때를 대비한 fallback을 선등록에 넣는다.** 이번에 실제로 발동했고, 덕분에 사후에 산식을 고치는 유혹 없이 판정을 마칠 수 있었다.
- **latency의 두 용도를 구분한다.** "cache hit인가"는 latency로 판정하지 않지만 "계산량이 몇 배인가"는 실행 시간으로 재는 것이 자연스럽다. 어느 용도인지 명시한다.
- **재현은 새 난수로 한다.** base seed를 바꿔 prompt를 새로 뽑았기 때문에 이번 결과가 특정 prompt의 우연이 아님을 말할 수 있다.
- **핵심 발견에 층 태그를 붙인다.** 절벽의 형태는 `class`, 상수 8은 인스턴스다. 상수를 클래스로 이식하지 않는다.

## 다음 작업

1. substrate descriptor v0와 층 태깅 규칙의 정식화 (같은 batch의 다음 작업).
2. `outer_slot_count`가 다른 구성에서 법칙 후보 검증 — 재compile 승인이 필요하다.
3. target prefix가 outer block 2개 이상일 때의 부분 생존 — `max_seq_len` 제약 때문에 재compile이 필요하다.
4. 동시성 > 1에서의 절벽 거동.

사용자 지시 없이 다음 TASK를 자동 시작하지 않는다.

## 재현 정보

- 선등록 commit: `2d79431917510dbc161541e1bd46d5353a32bf05`
- **측정 시작 시각: 2026-08-19 20:48:42 KST.** 선등록 commit 시각은 2026-08-19 20:48:24 KST이므로 **선등록이 측정보다 18초 앞선다.**
- 측정 종료 시각: `<RUN>/measurement-end.txt`
- Base commit (측정 중 HEAD): `2d79431917510dbc161541e1bd46d5353a32bf05`, dirty = untracked `.idea/` 및 gitignored `results/`, `models/`
- **Patch state: `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`** — `<RUN>/patch-state.txt`
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)
- Prompt seed: `derive_block_seed(20260820, "<trial>/<role>")`. 고정 prompt는 `experiments/npu/stage2/cliff_prompts.json` (git 추적)
- Raw artifact: `results/npu/stage2/20260819-204900-cliff-repro/`
  - `measurement-start.txt`, `measurement-end.txt`, `patch-state.txt`
  - `server-B{5,6,7,8}r{0,1,2}.log` — `[PFX]` 로그와 PREFILL/DECODE METRICS
  - `probe/gap_turnover.B*.json` — 요청별 counter 증분
  - `probe-B*.log`, `rbln-smi-before.txt`, `rbln-smi-final.txt`
- 실행 script: `experiments/npu/stage2/{build_gap_prompts.py,gap_turnover_probe.py}`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(**patched**), `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch 2.11.0+cpu`
- Host: `atom-max8`, device `rbln0`–`rbln3`
