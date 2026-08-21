# 선등록 — bucket 격자 정렬 법칙: 관측 완성과 개입 검증

## 문서 성격

[CLAUDE.md](../../CLAUDE.md) 실행 원칙 16과 [TASK_GUIDE.md](TASK_GUIDE.md)가 요구하는 **선등록(preregistration)** 이다. 이 문서를 담은 commit 이후에 측정을 시작한다. 측정 후 판정 기준을 완화하지 않는다.

## 연구 질문과 법칙 후보

**RQ**: gap의 utilization 효과 **부호**는 conventional steady-state batch의 **padding**이 결정하는가?

[TASK20](TASK20.md)이 N=6에서 3블록 전부 역전(pooled 1.150)을 관측하고 기전을 제시했다 — CONVENTIONAL은 N개가 동시에 돌아 bucket 8에 실리고, AGENTIC은 gap이 batch를 padding 0인 크기로 쪼갠다.

**법칙 후보**: `padding_slots(N) = bucket_for(N) − N`이 클수록 AGENTIC이 유리하다.

현재 격자 `(1, 2, 4, 8)`에서:

| N | bucket | padding | padding 비율 | [TASK20](TASK20.md) pooled ratio |
|---|---|---|---|---|
| 3 | 4 | 1 | 0.25 | 미측정 |
| 4 | 4 | 0 | 0.00 | 1.041 |
| 5 | 8 | **3** | **0.375** | 미측정 |
| 6 | 8 | 2 | 0.25 | **1.150** |
| 7 | 8 | 1 | 0.125 | 미측정 |
| 8 | 8 | 0 | 0.00 | 0.925 |

## 승인 범위 (사용자 판정, 2026-08-21)

serving 기동·종료(예상 40회 내외), localhost 요청, 기존 관측 스택 전부, 코드 추가·수정, **재compile 최대 2회** (2b 명시 격자 한정 + 실패 시 진단 1회).

**예산**: compile 회당 30분, `models/` 상한 80 GiB(현재 21 GiB).

범위 밖: download, patch 추가·수정, RSD 변경, remote push 자동 수행.

## Substrate 상태

측정 전 `apply.sh status`가 `patched`(SHA256 `70942d16…`)가 아니면 시작하지 않는다.

## 2a — 관측 완성 (기존 b8 artifact, 재compile 전)

### 격자

| 항목 | 값 |
|---|---|
| N | **3, 5, 7** × 3블록(b0–b2) **+ N=8** × 3블록(**신규 seed b5–b7**) |
| arm | AGENTIC / CONVENTIONAL (짝, `zero_gaps()` 파생) |
| 총 조합 | 3×2×3 + 1×2×3 = **24** |
| 세션 구조·분포·gap | [TASK20](TASK20.md)과 **완전히 동일** |
| plan seed | `base_seed=20260841`, `block_id = n<N>b<B>` (arm 간 동일) |
| server | 조합마다 fresh, `--enable-prefix-caching --enable-prompt-tokens-details` |

### 블록별 arm 순서

`balanced_arm_orders(["AGENTIC","CONVENTIONAL"], rounds=3, base_seed=20260841, block_id="task23a")` → b0 A→C, b1 C→A, b2 A→C

N=8 추가 블록: `... block_id="task23a-n8"` → b5 A→C, b6 C→A, b7 C→A

### 판정 밴드

[TASK20](TASK20.md)과 **동일**: 동치 밴드 `[0.97, 1.03]`.

| N | 판정 규칙 |
|---|---|
| 3, 5, 7 | 전 3블록 방향 일치 **그리고** pooled가 밴드 밖 → "저하 존재"(< 0.97) 또는 "역전"(> 1.03). 전 블록이 밴드 안이면 "동치". 그 외 `INCONCLUSIVE` |
| **8** | **8블록 합산**([TASK20](TASK20.md) b0–b4 + 신규 b5–b7). **8블록 중 7블록 이상이 같은 방향 그리고 pooled가 밴드 밖**이면 채택. 그 외 `INCONCLUSIVE` |

N=8의 "7/8 이상" 요건은 **완화가 아니라 사전 정의**다. [TASK20](TASK20.md)에서 5블록 중 4블록이 저하 방향이었고 1블록만 반대여서 "전부" 요건에 걸렸는데, 블록 수가 늘면 "전부"는 표본이 커질수록 만족하기 어려워지는 비대칭 기준이 된다. 8블록에서 7/8을 요구하는 것은 같은 엄격도를 유지하기 위한 조정이며 **측정 전에 고정한다.**

[TASK20](TASK20.md)의 N=8 5블록 결과는 **분리 보고**한다: 블록별 ratio `[0.8489, 0.8966, 0.9270, 0.9580, 1.0229]`, pooled `0.9253`.

### 사전 예측 (판정 기준 아님)

법칙 후보에서 유도한다.

| # | 예측 | 근거 |
|---|---|---|
| a | **N=5 → 역전, N=6보다 큰 폭** | padding 비율 0.375 > 0.25 |
| b | **N=7 → 약한 역전 또는 동치** | padding 비율 0.125 |
| c | **N=3 → 역전** | bucket 4, padding 비율 0.25 |
| d | N=8 8블록 합산은 "저하 존재" | padding 0, [TASK20](TASK20.md) 경향 |

## 2b — 개입 검증 (재compile)

### Compile

```bash
timeout 1800 optimum-rbln-cli \
  --model-id Qwen/Qwen3-4B \
  --output-dir /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb6 \
  --batch_size 8 --decoder_batch_sizes 1,2,4,6,8 \
  --max_seq_len 8192 --num_devices 4
```

**bucket 6만 추가하고 나머지는 b8과 동일하다.** compile wall-clock과 artifact 크기를 기록한다 ([TASK10](TASK10.md)의 bucket 수 스케일 데이터에 관측점 추가 — 4 bucket → 5 bucket).

승인된 파라미터로 실패하면 **파라미터를 바꿔 재시도하지 않고** 실패 증거를 기록한 뒤 진단 재시도 1회만 쓴다.

### 사상표 재검증 (본 실행 전)

새 artifact에서 `[BUCKET]` 로그로 사상을 확인한다. **동시성 5, 6, 7을 각각 1회** 보내고(생성 길이 고정) 관측 사상을 기록한다.

**기대**: 5 → **6**, 6 → **6**, 7 → 8.

**사상이 기대와 다르면 그 자체를 기록하고 판정 설계를 조정한다** — 예를 들어 bucket 6이 만들어지지 않았다면 2b의 개입이 성립하지 않으므로 그 사실을 결과로 보고하고 N=6 비교를 하지 않는다.

### 격자

| 항목 | 값 |
|---|---|
| N | **6, 8** × 2 arm × 3블록 |
| 총 조합 | **12** |
| artifact | 새 `...-mb6` |
| plan seed | `base_seed=20260842`, `block_id = n<N>b<B>` |
| 그 외 | 2a와 동일 |

블록별 arm 순서: `balanced_arm_orders([...], rounds=3, base_seed=20260842, block_id="task23b")` → b0 C→A, b1 C→A, b2 A→C

### 핵심 예측 (개입의 인과 검증)

**bucket 6이 존재하면 N=6의 CONVENTIONAL padding이 0이 되므로 N=6 역전이 소멸한다** — ratio가 동치 밴드 안이거나 1 미만이 된다.

N=8은 격자 변경과 무관하므로 [TASK20](TASK20.md) 경향(저하 방향)을 유지한다.

| 결과 | 해석 |
|---|---|
| N=6 역전 소멸 **그리고** N=8 경향 유지 | **격자 법칙의 인과 증거** |
| N=6 역전 유지 | 법칙 기각 — 역전의 원인이 padding이 아니다 |
| N=6 소멸했으나 N=8도 함께 바뀜 | 법칙 수정 필요 — 격자 변경이 다른 것도 바꿨다 |

**어느 쪽이든 결과다.** 판정은 2a와 같은 밴드·같은 방향 요건(3블록 전부)으로 한다.

## 불변식 (fail-loud, 위반 조합은 `INVALID`)

P1(짝 plan 동일성), I1–I5는 [NSLOTS_SWEEP_PREREG.md](NSLOTS_SWEEP_PREREG.md)와 동일하다. 2b에서는 I3·I4의 bucket 집합이 **`{1,2,4,6,8}`** 로 바뀐다.

## 층 태그 방침

법칙의 **형태**("padding이 클수록 gap이 유리하다")는 `class` 후보다 — 기전이 고정 bucket 격자라는 설계 범주에서 나온다. **문턱과 크기는 `stack`** 이다 — 격자 `(1,2,4,8)`과 `max_num_seqs=8`에 의존한다.

## 필수 측정 항목

조합별: per-request JSONL, plan summary, `[BUCKET]`·`[PFX]` 로그 전문, `/metrics` 덤프, utilization JSON. 2b 추가: compile 로그·wall-clock·artifact 크기·`rbln_config.json`, 사상 재검증 결과. 전체: patch state, `rbln-smi`, disk 사용량, provenance.

## 실행 절차 (측정 전 고정)

`<RUN2a>` = `results/npu/stage2/<timestamp>-grid-observe`, `<RUN2b>` = `.../<timestamp>-grid-intervene`

1. `apply.sh status` → `patched` 확인
2. **2a**: N 3→5→7→8 순서로 블록별 arm 순서표대로 `run_sweep.sh` 실행 (`SWEEP_BASE_SEED=20260841`). background + 완료 표식
3. **2b**: compile → disk·크기 기록 → 사상 재검증 → N 6→8 sweep (`SWEEP_BASE_SEED=20260842`, 새 artifact)
4. 조합마다 `utilization.py --cost-model` (2b는 `--buckets 1,2,4,6,8`)
5. P1 확인 후 판정표 작성

`run_sweep.sh`가 artifact 경로를 하드코딩하고 있어 `SWEEP_ARTIFACT` 환경변수로 분리했다 (기본값은 기존 b8 artifact이므로 2a와 이전 sweep의 재현성은 바뀌지 않는다). **이 수정은 2b 측정 시작 전에 commit했다.**

```bash
SWEEP_BASE_SEED=20260842 \
SWEEP_ARTIFACT=/home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb6 \
  bash experiments/npu/stage2/run_sweep.sh <RUN2b> <ARM> <6|8> <B> <none|zero>
```

## 관련 문서

- [TASK20](TASK20.md) — 법칙 후보의 출처, N=8 5블록 기준선
- [TASK13](TASK13.md) — 사상표와 step 비용 모형
- [TASK10](TASK10.md) — compile cost 스케일 기준선 (165 s / 9.08 GiB → 349 s / 11.50 GiB)
- [TASK08](TASK08.md) — `decoder_batch_sizes` 규칙
