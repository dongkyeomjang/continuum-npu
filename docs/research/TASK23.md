# TASK23 — bucket 격자 정렬 법칙: 관측 완성과 재compile 개입 검증

## 상태

DONE

## 판정

선등록 문서: [GRID_ALIGNMENT_PREREG.md](GRID_ALIGNMENT_PREREG.md) (commit `d5dfc7f`)

### 2a — 관측 완성 (기존 격자 `(1,2,4,8)`)

| N | bucket | padding | padding/bucket | 블록별 ratio | pooled | 판정 |
|---|---|---|---|---|---|---|
| 3 | 4 | 1 | 0.250 | 1.0926 / 1.1360 / **1.0232** | 1.0820 | `INCONCLUSIVE` (역전 방향) |
| 5 | 8 | 3 | 0.375 | 1.0700 / 1.0433 / 1.2695 | **1.1336** | **역전** |
| 7 | 8 | 1 | 0.125 | **0.9928** / **1.0229** / 1.0481 | 1.0220 | `INCONCLUSIVE` (밴드 근처) |
| 8 | 8 | 0 | 0.000 | 8블록 중 7블록이 `< 0.97` | **0.9205** | **저하 존재** |

`ratio = util(AGENTIC) / util(CONVENTIONAL)`, 동치 밴드 `[0.97, 1.03]`. 굵은 값은 밴드 안에 들어 3블록 전건 요건을 깬 블록이다.

**pooled의 정의**: [TASK20](TASK20.md)과 동일하게 **step 가중**이다 — arm별로 블록을 합쳐 `Σ(request_nums) / Σ(padded_batch_size)`를 구한 뒤 두 arm의 비를 잡는다. 블록별 utilization의 산술평균이나 utilization 합의 비가 아니다. 세 정의는 이 자료에서 최대 0.003 차이가 나며, 그 차이가 판정을 바꾸는 경계 사례가 아래 N=6에 하나 있다.

### 2b — 재compile 개입 (격자 `(1,2,4,6,8)`)

| N | 개입 전 pooled | 개입 후 블록별 ratio | 개입 후 pooled | 판정 |
|---|---|---|---|---|
| **6** | **1.1504** ([TASK20](TASK20.md)) | 0.9488 / **1.0029** / 0.9547 | **0.9717** | `INCONCLUSIVE` (동치 밴드 안) |
| 8 | 0.9253 (5블록) | 0.9400 / 0.9558 / 0.9559 | **0.9508** | **저하 존재** |

**핵심 예측 적중: N=6 역전이 소멸했다.** 선등록한 핵심 예측은 "bucket 6이 존재하면 N=6 역전이 소멸한다 — ratio가 동치 밴드 안이거나 1 미만"이었다. pooled가 1.1504 → **0.9717**로 내려가 **동치 밴드 안**에 들어왔고, 역전 방향(`> 1.03`) 블록이 3/3에서 **0/3**이 됐다. N=8은 저하 방향을 유지했다(3/3, pooled 0.9508). 선등록 표의 "N=6 역전 소멸 **그리고** N=8 경향 유지" 칸에 해당하므로 이는 **격자 법칙의 인과 증거**다.

경계 사례를 밝혀 둔다: 개입 후 N=6 pooled는 step 가중 정의로 **0.9717**(밴드 안)이지만 utilization 합의 비로는 **0.9685**(밴드 바로 아래)다. 어느 정의를 쓰든 **역전 소멸**이라는 결론은 같고, 바뀌는 것은 "동치"인지 "저하 방향"인지뿐이다. 본 TASK는 [TASK20](TASK20.md)과 비교 가능하도록 step 가중을 쓴다.

불변식: 2a 24조합·2b 12조합 **전건 통과**(P1, I1–I5). 단 2a `CONVENTIONAL.n7.b0`은 [TASK22](TASK22.md) 이후 발생한 인프라 사고로 1회 `INVALID`가 났고 같은 선등록 칸을 재실행해 `VALID`로 대체했다(아래 실패/무효 시도).

## 날짜

2026-08-21

## 목적

[TASK20](TASK20.md)이 N=6에서 관측한 utilization 역전(AGENTIC이 15 % 높음)이 **compiled decoder bucket 격자와 N의 정렬**로 설명되는지 확인한다. 관측을 미측정 N으로 확장하고(2a), 격자 자체를 바꾸는 개입으로 인과를 검증한다(2b).

## 배경

관련 TASK:

- [TASK20](TASK20.md) — 법칙 후보의 출처. N=6 pooled 1.1504, N=8 5블록 pooled 0.9253
- [TASK13](TASK13.md) — 사상표(`bisect_left`)와 decode step 비용 모형
- [TASK10](TASK10.md) — compile cost 스케일 기준선 (165 s / 9.083 GiB → 349 s / 11.501 GiB)
- [TASK08](TASK08.md) — `decoder_batch_sizes` 규칙
- [TASK22](TASK22.md) — prefill 배타 실행과 비용 모델 v2

판정 규칙의 차이를 밝혀 둔다. [TASK20](TASK20.md)의 선등록 규칙에는 **"역전"이라는 판정 범주가 없었다** — "저하 존재"(밴드 아래)와 "동치"(밴드 안)만 있어서, 3블록 전부가 밴드 **위**였던 N=6도 `INCONCLUSIVE`로 분류됐다. 본 TASK의 선등록은 "역전"(`> 1.03`)을 판정 범주로 추가했다. 따라서 "[TASK20](TASK20.md)의 N=6 역전"이라고 쓸 때 그것은 본 TASK의 규칙을 소급 적용한 표현이며, 관측값(3블록 전부 1.11–1.17, pooled 1.1504) 자체는 [TASK20](TASK20.md)이 보고한 그대로다. [TASK20](TASK20.md)의 pooled 값 6개는 이번에 원시 artifact에서 전부 재계산해 소수 넷째 자리까지 일치함을 확인했다.

**법칙 후보**: `padding_slots(N) = bucket_for(N) − N`이 클수록 AGENTIC이 유리하다. CONVENTIONAL은 N개가 동시에 돌아 하나의 bucket에 실리고, AGENTIC은 gap이 batch를 padding이 작은 크기로 쪼갠다.

## 시작 상태

- 선등록 commit: `d5dfc7f8bebd44d3c329bc4fc9ead2cabc12bb21` (2026-08-21T22:02:42+09:00)
- 측정 시작: 2a `2026-08-21T22:18:15+09:00`, 2b `2026-08-21T23:18:02+09:00` — **둘 다 선등록 이후**
- Substrate: **patched** (SHA256 `70942d16…`). 2a·2b 각각 측정 전 gate 통과
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`
- 측정 시작 시점 commit: `1620ff6` (script 수정 2건이 2b 측정 전에 commit됨)

## 수행 내용

1. **2a**: 기존 b8 artifact로 N ∈ {3,5,7} × 3블록 + N=8 × 신규 3블록(b5–b7) = **24 조합**을 선등록 arm 순서대로 측정했다.
2. **재compile 1회**: `decoder_batch_sizes=1,2,4,6,8`로 bucket 6을 추가한 artifact를 만들었다.
3. **사상표 재검증**: 새 artifact에서 동시성 5·6·7을 각각 보내 `[BUCKET]` 사상을 확인했다.
4. **2b**: 새 artifact로 N ∈ {6,8} × 2 arm × 3블록 = **12 조합**을 측정했다.
5. 조합마다 `utilization.py --cost-model`(2b는 `--buckets 1,2,4,6,8`)을 돌리고 P1·I1–I5를 확인했다.

## 변경된 파일

- `docs/research/TASK23.md` (신규)
- `docs/research/INDEX.md`

측정 전에 별도 commit한 script 수정(선등록 문서에 기록):

- `experiments/npu/stage2/run_sweep.sh` — artifact 경로를 `SWEEP_ARTIFACT`로 분리 (`fae321d`), server 종료를 pattern이 아니라 PID 기준으로 변경 (`1620ff6`)

Raw artifact는 `.gitignore` 대상이다.

## 실험 또는 검증 방법

```bash
# 2a (기존 b8 artifact)
SWEEP_BASE_SEED=20260841 \
  bash experiments/npu/stage2/run_sweep.sh <RUN2a> <ARM> <3|5|7|8> <B> <none|zero>

# 재compile
timeout 1800 optimum-rbln-cli --model-id Qwen/Qwen3-4B \
  --output-dir models/Qwen3-4B-rbln-b8-s8192-d4-mb6 \
  --batch_size 8 --decoder_batch_sizes 1,2,4,6,8 --max_seq_len 8192 --num_devices 4

# 사상표 재검증
experiments/npu/stage1/concurrency_probe.py --levels 5,6,7 --max-tokens 64 ...

# 2b (새 artifact)
SWEEP_BASE_SEED=20260842 SWEEP_ARTIFACT=$PWD/models/Qwen3-4B-rbln-b8-s8192-d4-mb6 \
  bash experiments/npu/stage2/run_sweep.sh <RUN2b> <ARM> <6|8> <B> <none|zero>
```

세션 구조·분포·gap은 [TASK20](TASK20.md)과 동일하다. 짝은 `zero_gaps()` 파생이므로 두 arm의 prompt·생성 길이 계획이 같다(P1).

`requested_condition` / `observed_condition` / `condition_reached`:

| 항목 | requested | observed | reached |
|---|---|---|---|
| 2a 조합 수 | 24 | 24 (그중 1칸 1회 재실행) | `YES` |
| 2b 조합 수 | 12 | 12 | `YES` |
| 재compile 횟수 | 최대 2 | **1** | `YES` |
| compile wall-clock | ≤ 1800 s | **416.0 s** | `YES` |
| `models/` 사용량 | ≤ 80 GiB | **33 GiB** | `YES` |
| 새 격자에 bucket 6 존재 | 필요 | **존재, 실제 사용됨** | `YES` |

## 결과

### 관측 1 — 사상표 재검증 (본 실행 전 gate)

동시성 5·6·7 각각 63 decode step씩 관측했다.

| 요청 동시성 | 기대 bucket | **관측 bucket** |
|---|---|---|
| 5 | 6 | **6** |
| 6 | 6 | **6** |
| 7 | 8 | **8** |

**기대와 완전히 일치**했다. `bisect_left` 사상([TASK13](TASK13.md))이 새 격자에서도 그대로 성립하며, 개입이 성립함을 본 실행 전에 확인했다.

### 관측 2 — 2a utilization (원시값)

| 조합 | AGENTIC | CONVENTIONAL | ratio |
|---|---|---|---|
| n3.b0 / b1 / b2 | 0.8446 / 0.9547 / 0.8957 | 0.7730 / 0.8403 / 0.8754 | 1.0926 / 1.1360 / 1.0232 |
| n5.b0 / b1 / b2 | 0.8460 / 0.7855 / 0.8523 | 0.7906 / 0.7529 / 0.6714 | 1.0700 / 1.0433 / 1.2695 |
| n7.b0 / b1 / b2 | 0.8313 / 0.8344 / 0.8764 | 0.8373 / 0.8157 / 0.8362 | 0.9928 / 1.0229 / 1.0481 |
| n8.b5 / b6 / b7 | 0.8535 / 0.8537 / 0.7973 | 0.8823 / 0.9399 / 0.9131 | 0.9674 / 0.9083 / 0.8733 |

N=8 8블록 전체: `0.8489 0.8966 0.9270 0.9580 1.0229 | 0.9674 0.9083 0.8733` (앞 5개는 [TASK20](TASK20.md)). **7블록이 `< 0.97`, 1블록이 밴드 안, 밴드 위는 0블록.** 8블록 pooled `0.9205`, 신규 3블록만 보면 `0.9132`. 선등록한 7/8 요건을 충족한다.

### 관측 3 — 2b utilization (원시값)

| 조합 | AGENTIC | CONVENTIONAL | ratio |
|---|---|---|---|
| n6.b0 / b1 / b2 | 0.9073 / 0.9391 / 0.9165 | 0.9563 / 0.9364 / 0.9600 | 0.9488 / 1.0029 / 0.9547 |
| n8.b0 / b1 / b2 | 0.9020 / 0.9469 / 0.9248 | 0.9596 / 0.9907 / 0.9675 | 0.9400 / 0.9558 / 0.9559 |

### 관측 4 — 개입 전후 arm별 절대 utilization

| N | arm | 개입 전 평균 | 개입 후 평균 | 배율 |
|---|---|---|---|---|
| 6 | CONVENTIONAL | 0.7650 | **0.9492** | **1.241×** |
| 6 | AGENTIC | 0.8801 | 0.9224 | 1.048× |
| 8 | CONVENTIONAL | 0.9086 | 0.9727 | 1.071× |
| 8 | AGENTIC | 0.8407 | 0.9248 | 1.100× |

N=6 CONVENTIONAL의 상한은 padding이 완전히 사라졌을 때의 `1/0.75 = 1.333×`이고 실측은 `1.241×`다. 나머지는 동시성이 6이 아닌 구간(`1→1`, `2→2`, `3→4` 등)이 남아 있기 때문이다.

### 관측 5 — decode step의 bucket 점유 히스토그램 (기전의 직접 관측)

값은 decode step 비율이다.

| N=6 | `5→b` | `6→b` |
|---|---|---|
| CONVENTIONAL 개입 전 | `5→8` 10.7 % | **`6→8` 42.2 %** |
| CONVENTIONAL 개입 후 | `5→6` 13.6 % | **`6→6` 46.3 %** |
| AGENTIC 개입 전 | `5→8` 1.5 % | **`6→8` 9.0 %** |
| AGENTIC 개입 후 | `5→6` 5.5 % | **`6→6` 8.0 %** |

N=8에서도 tail 구간이 바뀌었다. CONVENTIONAL: `5→8` 8.7 % + `6→8` 3.7 % (개입 전) → `5→6` 8.9 % + `6→6` 8.2 % (개입 후).

### 관측 6 — compile 비용 (부수 관측점)

| bucket 수 | compiled model 수 | wall-clock | artifact 총 크기 |
|---|---|---|---|
| 1 ([TASK06](TASK06.md)) | 2 | 165.0 s | 9.083 GiB |
| 4 ([TASK10](TASK10.md)) | 5 | 349.0 s | 11.501 GiB |
| **5 (이번)** | **6** | **416.0 s** | **12.306 GiB** |

[TASK10](TASK10.md)이 관측점 2개로 세운 모형의 외삽 결과:

| 모형 | 예측 | 실측 | 오차 |
|---|---|---|---|
| 시간 `42.3 + 61.33 × models` | 410.3 s | 416.0 s | **+1.4 %** |
| 크기 `8.276 + 0.806 × buckets` GiB | 12.308 GiB | 12.306 GiB | **−0.009 %** |

파일 단위로도 맞는다: `prefill.rbln` = 8.288 GiB(절편 8.276), `decoder_batch_6.rbln` = 0.805 GiB(기울기 0.806).

## 핵심 발견

1. **`class`(형태) + `stack`(값) — bucket 격자와 N의 정렬이 gap 효과의 부호를 결정한다는 것이 개입으로 확인됐다.** 격자에 bucket 6을 추가하자 N=6의 pooled ratio가 1.1504 → 0.9717로 내려가 역전이 사라졌고, 역전 방향 블록이 3/3 → 0/3이 됐다. 워크로드·seed·모델·slot 수를 고정하고 **격자만** 바꿨으므로 상관이 아니라 개입 증거다. *형태*를 `class`로 태그하는 근거: 기전이 "고정된 이산 batch 크기 집합에 실제 batch를 올림한다"는 설계 범주에서 나오며 특정 구현 상수에 의존하지 않는다. 문턱과 크기(격자 `(1,2,4,8)`, `max_num_seqs=8`, 1.15/0.97 같은 값)는 `stack`이다.

2. **`stack` — 개입의 이득은 CONVENTIONAL에 집중됐다.** N=6에서 CONVENTIONAL utilization은 1.241× 올랐는데 AGENTIC은 1.048×에 그쳤다. 히스토그램이 이유를 직접 보여준다: CONVENTIONAL은 decode step의 **42.2 %** 를 `6→8`(padding 2)로 보냈지만 AGENTIC은 **9.0 %** 뿐이었다. gap이 이미 batch를 padding이 작은 조각으로 쪼개 두었으므로 격자를 고쳐 줄 padding 자체가 적었다.

3. **`stack` — padding 비율과 pooled ratio는 단조에 가깝지만 완전 단조는 아니다.** 격자 `(1,2,4,8)`에서 padding/bucket 0.375(N=5) → 1.1336, 0.25(N=6) → 1.1504, 0.25(N=3) → 1.0820, 0.125(N=7) → 1.0220, 0(N=4) → 1.0414, 0(N=8) → 0.9205. 부호가 padding 0 근처에서 뒤집히는 것은 대체로 일관되지만 예외가 둘 있다. (i) padding 비율이 가장 큰 N=5(0.375)의 역전이 N=6(0.25)보다 **작다**. (ii) padding 0인 N=4의 pooled가 1.0414로 **1 위**다([TASK20](TASK20.md)에서도 `INCONCLUSIVE`였다). 따라서 **padding 비율 하나로 크기를 예측하는 모형은 성립하지 않으며**, padding 0이 곧 저하를 뜻하지도 않는다.

4. **`stack` — 격자 변경은 N=8의 절대 utilization도 올렸다.** 선등록은 "N=8은 격자 변경과 무관"이라고 가정했으나 양 arm 모두 7–10 % 올랐다. N=8에서도 세션이 빠지는 tail 구간에서 동시성이 5–6이 되어 새 bucket 6을 쓰기 때문이다. **ratio의 방향과 판정은 유지**됐으므로(3/3 저하, pooled 0.9253 → 0.9508) 개입 검증 자체는 무효화되지 않지만, "무관"이라는 전제는 틀렸다.

5. **`stack` — [TASK10](TASK10.md)의 compile 비용 모형이 3번째 관측점에서 유지됐다.** 관측점 2개로 세운 외삽이 시간 +1.4 %, 크기 −0.009 % 오차로 맞았다. [TASK10](TASK10.md)이 남긴 "bucket 수를 크게 늘렸을 때 모형이 유지되는가"라는 미지수가 5 bucket까지는 `YES`로 좁혀졌다.

6. **`universal` — 선등록한 "전 블록 동방향" 요건은 표본이 커질수록 만족하기 어려운 비대칭 기준이다.** 2a의 N=3(pooled 1.0820)과 2b의 N=6(pooled 0.9717)은 각각 3블록 중 1블록만 밴드 안에 걸려 `INCONCLUSIVE`가 됐다. pooled와 방향은 분명한데 판정만 미결이다. 이 문제는 [TASK20](TASK20.md)에서도 같은 형태로 나타났고, 이번에 N=8에만 7/8 규칙을 선등록해 부분적으로 대응했다.

## 해석

- **(해석)** 법칙의 핵심 주장 — "gap의 utilization 효과 부호는 conventional steady-state batch의 padding이 결정한다" — 은 **부호 수준에서 인과적으로 지지된다.** padding이 있으면(N=3,5,6) AGENTIC이 유리하고, padding이 0이면(N=8, 그리고 개입 후 N=6) 불리하다. padding을 인위적으로 제거하자 효과가 사라졌다.
- **(해석)** 그러나 **크기 수준의 모형은 아직 없다.** 발견 3이 보여주듯 padding 비율 단독으로는 pooled ratio의 크기를 설명하지 못한다. gap 분포가 batch를 어떤 크기로 쪼개는지(히스토그램 전체 모양)가 들어가야 할 것으로 보이며, 이는 아직 세우지 않은 모형이다.
- **(해석)** 발견 4는 설계 교훈이다. "이 축은 개입과 무관하다"는 대조군 가정을 세울 때, 그 축에서도 **tail 구간의 동시성이 격자에 닿는지**를 먼저 확인해야 한다. N=8은 "항상 8개가 돌아간다"가 아니라 "최대 8개"였다.
- **(해석)** 실무적으로: 고정 bucket 격자를 쓰는 substrate에서 **격자를 워크로드의 정상 상태 동시성에 맞추는 것**이 gap 유무보다 큰 효과를 낼 수 있다. N=6에서 bucket 6 추가는 CONVENTIONAL을 **24 %** 개선했는데, 이는 이 실험에서 관측된 어떤 arm 간 차이보다 크다.

## 확인되지 않은 사항

- pooled ratio의 **크기**를 예측하는 모형 (`UNKNOWN`). padding 비율만으로는 부족하다(발견 3).
- N=3과 N=7의 판정 (`INCONCLUSIVE`). 블록을 늘리면 결론이 날 가능성이 있으나 이번 예산에서 하지 않았다.
- 개입 후 N=6이 "동치"인지 "저하 존재"인지 (`INCONCLUSIVE`). pooled가 밴드 경계 0.97에 붙어 있어 pooling 정의에 따라 안팎이 갈린다.
- 다른 격자(예: bucket 3, 5, 7까지 추가한 조밀 격자)에서 법칙이 유지되는지 (`UNKNOWN`). 재compile 예산 1회를 남겼으나 사용하지 않았다.
- 격자를 조밀하게 만들 때의 비용 균형 (`UNKNOWN`). compile 시간·artifact 크기는 bucket 수에 선형이지만(관측 6) 기동 시간과 host memory 영향은 이번에 재지 않았다.
- [TASK21](TASK21.md)의 gap 분산 축과 이번 격자 축의 상호작용 (`UNKNOWN`, 아래 이월 참조).

## 실패 / 무효 시도

### 인프라 사고 — 실행 중인 script 수정으로 인한 연쇄 실패

2a sweep이 **실행 중일 때** `run_sweep.sh`를 편집했다. Bash가 부분 기록된 파일을 읽어 일시적 syntax error가 났고, 진행 중이던 조합이 중간에 죽으면서 server가 누수됐다. 당시 종료 로직이 `ps | grep | head -1` pattern 기반이었기 때문에 **다음 조합이 자기 server가 아니라 누수된 server를 죽였고**, 이후 6개 조합이 연쇄로 무너졌다.

수습: background job 중단 → 모든 `vllm` process `SIGKILL` → `rbln-smi`로 device가 `0.0B`이고 잔여 context가 없음을 확인 → 종료 로직을 **`$SRV` PID 기준**으로 고쳐 commit(`1620ff6`) → 재시작. 완료 표식 덕분에 이미 끝난 4개 조합은 보호됐다.

잔여 피해는 **`CONVENTIONAL.n7.b0` 1칸**이었다. 이 칸은 완료 표식(`22:34:40`)이 재시작(`22:36:45`) **이전**이고, server 로그가 누수된 EngineCore(pid 1179357)를 가리키며, `[BUCKET]` 줄이 0개였다. 14개 요청이 전부 HTTP 200을 받았지만 **다른 server가 처리한 것**이다. `utilization.py`가 `I1 no [BUCKET] lines found`와 `I5 sum(request_nums)=0 != 1853`으로 fail-loud하게 잡아냈다.

**대체가 아니라 같은 선등록 칸의 재실행으로 처리했다.** 표식을 지우고 동일 seed·동일 arm 순서로 다시 돌려 `VALID`(438 decode step, 위반 0)를 얻었다. 24개 완료 표식과 `[BUCKET]` 개수를 전수 감사해 **이 1칸만** 손상됐음을 확인했다(나머지는 197–770줄).

교훈 두 가지를 기록한다. **(1) 실행 중인 실험의 script를 편집하지 않는다.** **(2) 자기 자원은 pattern이 아니라 자기가 만든 handle로 정리한다** — pattern 정리는 실패가 국소에 머물지 않고 연쇄한다.

### 선등록 예측의 성적

| # | 예측 | 결과 |
|---|---|---|
| a | N=5 역전, **N=6보다 큰 폭** | **부분 적중.** 역전은 맞았으나(1.1336) N=6의 1.1504보다 **작다** |
| b | N=7 약한 역전 또는 동치 | **판정 불가.** pooled 1.0220은 밴드 안이지만 1블록이 밴드 밖이라 `INCONCLUSIVE` |
| c | N=3 역전 | **부분 적중.** pooled 1.0820으로 밴드 위지만 1블록(1.0232)이 밴드 안이라 `INCONCLUSIVE` |
| d | N=8 8블록 합산 저하 존재 | **적중.** 7/8 블록 저하, pooled 0.9205 |
| 2b 핵심 | bucket 6 추가 시 N=6 역전 소멸 | **적중.** 1.1504 → 0.9717 (동치 밴드 안) |
| 2b 대조 | N=8은 격자 변경과 무관 | **전제는 빗나감**(절대값이 양 arm 모두 상승), **판정은 유지**(저하 존재) |

판정 기준은 측정 후 **완화하지 않았다.** N=3과 N=6이 pooled·방향상 분명한데도 `INCONCLUSIVE`로 남긴 것이 그 결과다.

## 연구 원칙에 미치는 영향

1. **실행 중인 실험의 코드·script를 수정하지 않는다.** 수정이 필요하면 실험을 멈춘 뒤 고치고 재시작한다.
2. **자기가 기동한 process는 자기 PID로 종료한다.** `pgrep`/`ps | grep` pattern으로 정리하면 다른 실행 주체의 자원을 죽여 실패가 연쇄한다.
3. **인프라 사고로 무효가 된 칸은 다른 조건으로 대체하지 않고 같은 선등록 칸을 재실행한다.** 대체는 격자를 사후에 바꾸는 것이다.
4. **"이 축은 개입과 무관하다"는 대조군 가정을 검증 없이 쓰지 않는다.** N=8은 격자와 무관할 것이라 가정했으나 tail 동시성이 새 bucket에 닿았다(발견 4).
5. **부호(sign)의 인과와 크기(magnitude)의 모형을 분리한다.** 부호는 개입으로 확정했지만 크기 모형은 아직 없다(발견 3).
6. **선등록의 "전건 동방향" 요건은 표본 수에 따라 비대칭이다.** 이후 실험은 블록 수와 함께 요건을 선등록 시점에 정한다(발견 6).

## 다음 작업

제안만 하며 사용자 지시 없이 실행하지 않는다.

1. **격자 축의 크기 모형** — gap 분포가 만드는 bucket 점유 히스토그램에서 pooled ratio를 예측하는 모형을 세우고 이미 확보한 2a·2b·[TASK20](TASK20.md) 관측점으로 검증한다. 새 측정 없이 가능하다.
2. **N=3 / N=7 / 개입 후 N=6의 판정 확정** — 블록을 3 → 6으로 늘린다. 재compile 불필요.
3. **[TASK21](TASK21.md) gap 분산 축과의 상호작용** — 이번 지시문에서 명시적으로 **이월**됐다(아래).
4. **조밀 격자의 비용/이득 균형** — bucket을 더 추가할 때의 compile·기동·memory 비용 대 utilization 이득. 재compile 승인이 필요하다.

### 이월 사유 기록

이번 batch에서 **[TASK21](TASK21.md)의 b1 블록 추가는 수행하지 않았다.** 사용자 지시문 수정(2026-08-21)이 2a의 범위를 N=8 신규 3블록으로 확장하는 대신 [TASK21](TASK21.md) 블록 추가를 이번 batch에서 제외하도록 명시했기 때문이다. 승인된 serving lifecycle 예산(약 40회) 안에서 2a 24조합 + 재실행 1 + 사상표 1 + 2b 12조합 = 38회를 썼다.

## 재현 정보

- 선등록 commit: `d5dfc7f8bebd44d3c329bc4fc9ead2cabc12bb21`, 2026-08-21T22:02:42+09:00. **2a 측정 시작 22:18:15, 2b 측정 시작 23:18:02 — 둘 다 선등록 이후**
- 측정 전 commit된 script 수정: `fae321d`(artifact 경로 환경변수화), `1620ff6`(PID 기준 server 종료)
- 2a raw artifact: `results/npu/stage2/20260821-222000-grid-observe/`
  - 측정 시작/종료: `measurement-start.txt` / `measurement-end.txt`, 재시작 `restart-at.txt` (`22:36:45`)
  - `CONVENTIONAL.n7.b0` 재실행 시각: `rerun-CONVENTIONAL.n7.b0-at.txt` (`23:11:05`)
- 2b raw artifact: `results/npu/stage2/20260821-231000-grid-intervene/`
  - compile: `compile/{compile.log,started_at.txt,finished_at.txt,exit_code.txt,rbln_config-mb6.json}` (`23:02:23`–`23:09:19`, exit 0)
  - 사상표 재검증: `mapping/{server.log,probe.log,prompt.txt,metrics.prom}`
  - 측정: `23:18:02`–`23:35:45`
- 조합별 산출물: `util.<ARM>.n<N>.b<B>.json`, `server-*.log`, `metrics-*.prom`, `probe/requests.*.jsonl`, `probe/meta.*.json`
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb6/` (gitignored, 12.306 GiB)
- Substrate: `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`
- 실행 script: `experiments/npu/stage2/{run_sweep.sh,session_runner.py}`, `experiments/npu/stage1/concurrency_probe.py`, `experiments/npu/analysis/utilization.py`
- 예산 사용: 재compile **1/2회**, compile wall-clock 416 s / 1800 s 상한, `models/` **33 GiB** / 80 GiB 상한, `/` 사용률 11 %, serving lifecycle 38회 / 약 40회
- 측정 후 device 상태: 전 ID `0.0B / 15.7GiB`, 잔여 context 없음 (`rbln-smi-final.txt`)
