# TASK12 — 결정 3 집행: decoder bucket 관측 patch 적용과 검증

## 상태

DONE

## 판정

**세 관문 모두 통과.** 신호를 채택하고 patch를 **적용된 상태로 유지**한다. [INDEX](INDEX.md)의 결정 3을 해소됨으로 갱신했다. `patches/` 정책의 첫 실전 적용이며 절차 전체가 문서화됐다.

## 날짜

2026-08-19

## 목적

[INDEX](INDEX.md) **결정 3**이 승인됐다. [TASK10](TASK10.md)이 "관측 불가"로 판정한 per-step `(실제 요청 수, 선택된 decoder bucket)`을 hash-guarded observation-only patch로 노출시키고, **그 신호가 실제로 의미하는 바를 채택 전에 검증한다.** Track A(bucket characterization) 진입 gate다.

## 배경

관련 TASK:

- [TASK08](TASK08.md) — bucket 선택 지점이 `optimum/model_base.py:preprocess_for_decoder`와 `utils/optimum/bucket.py:select_bucket_size`임을 source로 확정했다. `select_bucket_size`에 `@cache`가 걸려 있어 함수 wrapping은 첫 호출만 잡힌다는 것도 여기서 나왔다.
- [TASK10](TASK10.md) — 선등록으로 한정한 4개 수단을 모두 검색해 관측 불가를 판정하고 결정 3을 신설했다. patch 대상·규모·근거·대안 표가 그 결과다.

선등록 문서: [BUCKET_PATCH_PREREG.md](BUCKET_PATCH_PREREG.md)
Patch 정책 문서: [patches/vllm_rbln-0.11.1/README.md](../../patches/vllm_rbln-0.11.1/README.md)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `1ca902c10bd4104e384a99d787cd046fa8095405`
- Git dirty: untracked `.idea/`만
- Host: `atom-max8`. Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`, `optimum-rbln 0.11.1`
- 대상 파일 상태: `pristine` (SHA256 `46ce1675a2b55e36d4d6dd0154edae793cd3874ed1fbe16e74a40ed7c809298e`)
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (`decoder_batch_sizes=[8,4,2,1]`, 재compile 없음)
- Device: 전 32 ID idle, port 8000 비어 있음

## 수행 내용

1. Patch 파일, hash-guarded `apply.sh`, `patches/` 정책 7항목 문서를 작성하고 **site-packages가 아닌 사본**에서 apply → revert 왕복 SHA256을 검증했다.
2. 검증 관문 3개와 사전 예측 7개를 담은 선등록 문서를 **측정 시작 전에** commit했다 (`1ca902c`).
3. **run A** (patch 미적용): server 기동 → 동시성 1/2/3/5/8 sweep → 종료 확인.
4. Patch 적용. 대상 파일이 `root:root`이고 이 세션에 사용 가능한 sudo가 없어 **사용자가 별도 터미널에서 실행**했다 (아래 "실패 / 무효 시도" 참조).
5. 적용 상태와 **Python이 실제로 load하는 코드**에 patch가 반영됐는지 확인했다.
6. **run B** (patch 적용): run A와 동일 조건으로 sweep → 종료 확인.
7. `[BUCKET]` 로그를 집계해 관문 1을 판정하고, run A/B wall-clock을 대조해 관문 2를 판정했다.
8. 사용자가 `revert` → `apply`를 실행해 관문 3을 판정하고 적용 상태를 복원했다.

재compile, download, RSD 변경, patch 이외의 site-packages 수정은 없었다.

## 변경된 파일

선등록 commit `1ca902c`:

- `docs/research/BUCKET_PATCH_PREREG.md` (신규)
- `patches/vllm_rbln-0.11.1/decoder_bucket_observe.patch` (신규)
- `patches/vllm_rbln-0.11.1/apply.sh` (신규)
- `patches/vllm_rbln-0.11.1/README.md` (신규, 정책 7항목)

이번 기록 commit:

- `docs/research/TASK12.md` (신규)
- `docs/research/INDEX.md` (결정 3 해소, 관측 신호 갱신)

Raw artifact는 `.gitignore` 대상인 `results/npu/stage1/20260819-182600-bucket-patch/`에 있다.

**site-packages 변경**: `vllm_rbln/model_executor/models/optimum/model_base.py`가 patch된 상태로 유지된다. Git이 추적하지 않으므로 `apply.sh status`가 유일한 상태 출처다.

## Patch 내용

```diff
@@ -391,6 +391,15 @@
                     padded_batch_size = select_bucket_size(
                         request_nums, self.decoder_batch_sizes
                     )
+                # [continuum-npu observation patch] Emit the per-step decode
+                # batch and the bucket chosen for it. Read-only: it reads
+                # values this function already computed and changes no control
+                # flow, scheduling, batch selection, or KV allocation.
+                logger.debug(
+                    "[BUCKET] request_nums=%s padded_batch_size=%s",
+                    input_ids.shape[0] if input_ids is not None else None,
+                    padded_batch_size,
+                )
```

**추가 9줄(주석 4 + 코드 5), 기존 줄 수정 0, 삭제 0.** [TASK10](TASK10.md)이 결정 3에서 제안한 "추가 3–5줄"과 규모가 일치한다(주석 포함 9줄).

[TASK08](TASK08.md)이 지적한 대로 `select_bucket_size`를 감싸지 않고 **caller에서 결과를 읽기만** 했다. 그 함수의 `@cache`가 첫 호출만 잡는 문제를 피하기 위해서다.

## 실험 또는 검증 방법

`<RUN>` = `results/npu/stage1/20260819-182600-bucket-patch`

```bash
# 상태 확인 (root 불필요)
bash patches/vllm_rbln-0.11.1/apply.sh status

# run A / run B 공통 (patch 적용 여부만 다름)
env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG vllm serve \
  /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb \
  --host 127.0.0.1 --port 8000 > <RUN>/server-run{A,B}.log 2>&1 &

env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage1/concurrency_probe.py \
  --base-url http://127.0.0.1:8000 \
  --prompt-file /home/rebel/continuum-npu/experiments/npu/stage1/prompt.txt \
  --max-tokens 128 --seed 20260819 --levels 1,2,3,5,8 \
  --output-dir /home/rebel/continuum-npu/<RUN>/probe-run{A,B}

# 적용 / 복구 (root 필요)
sudo bash patches/vllm_rbln-0.11.1/apply.sh apply
sudo bash patches/vllm_rbln-0.11.1/apply.sh revert
```

`concurrency_probe.py`는 [TASK10](TASK10.md)의 script를 **변경 없이** 재사용했다.

## 결과

### 조건 분리

- `requested_condition`: 동시성 1/2/3/5/8, `max_tokens=128`, greedy, seed 20260819, `VLLM_LOGGING_LEVEL=DEBUG`(run A·B 동일), `RBLN_DEVICES` 미설정, 동일 artifact.
- `observed_condition`: run A는 `state: pristine`, run B는 `state: patched`. 두 run의 요청 status는 전부 200이고 `running` peak가 요청한 동시성과 정확히 일치했다(1/2/3/5/8).
- `condition_reached`: `YES`.

### 관찰 — patch 적용 상태 전이

| 시점 | SHA256 | state | 확인 방법 |
|---|---|---|---|
| 측정 시작 | `46ce1675…` | `pristine` | `apply.sh status` |
| run A 중 | `46ce1675…` | `pristine` | 동일 |
| apply 후 | `70942d16…` | `patched` | `apply.sh status` + 사용자 터미널 출력 |
| run B 중 | `70942d16…` | `patched` | 동일 |
| revert 후 | `46ce1675…` | — | 사용자 터미널 출력 (**pristine 기대값과 일치**) |
| 최종 재적용 후 | `70942d16…` | `patched` | `apply.sh status` |

적용 직후 Python이 **실제로 load하는 코드**에 patch가 반영됐는지도 확인했다.

```text
inspect.getsource(RBLNOptimumDecoderMixin.preprocess_for_decoder) 에 "[BUCKET]" 포함: True
```

`__pycache__`의 `.pyc`는 2026-08-11자 그대로이고 디렉터리가 쓰기 불가라 갱신되지 않지만, Python이 source의 mtime/size 불일치를 감지해 메모리에서 재컴파일하므로 patch가 적용된 코드가 실행된다. 위 `inspect` 확인이 그 증거다.

### 관문 1 — 의미론 검증: **통과 (전건 일치)**

Population: run B의 decode step 635회. Unit: 요청 수(정수). Source: patch가 emit한 DEBUG 로그. Device scope: `rbln0`–`rbln3`.

`[BUCKET]` 로그 **635줄** = 5개 수준 × 127 step. 관측된 쌍은 5종이며 전부 기대 사상과 일치했다.

| `request_nums` | 관측 `padded_batch_size` | 기대(사상표) | 빈도 | 판정 |
|---|---|---|---|---|
| 1 | 1 | 1 | 127 | ✓ |
| 2 | 2 | 2 | 127 | ✓ |
| 3 | **4** | 4 | 127 | ✓ |
| 5 | **8** | 8 | 127 | ✓ |
| 8 | 8 | 8 | 127 | ✓ |

**불일치 쌍은 0개다.** 선등록이 별도로 요구한 bucket 경계 사상 `3 → 4`와 `5 → 8`이 **둘 다 실제로 관측**됐으므로 `PARTIAL` 조건에 걸리지 않는다.

`request_nums=None`인 줄은 하나도 없었다(예측 7 적중). 즉 decode 경로에서 `input_ids`는 항상 존재했다.

수준당 정확히 127 step인 것은 `max_tokens=128`에서 첫 token이 prefill로 나오고 나머지 127개가 decode step이기 때문이다.

### 관문 2 — 관찰자 효과: **통과**

Population: 동시성 수준 5개, 각 1회. Unit: 초. Source: probe의 wall-clock.

| 수준 | run A (미적용) | run B (적용) | 비 | 자릿수 동일 |
|---|---|---|---|---|
| 1 | 1.339 s | 1.460 s | 1.091 | ✓ |
| 2 | 1.417 s | 1.507 s | 1.063 | ✓ |
| 3 | 1.487 s | 1.503 s | 1.011 | ✓ |
| 5 | 1.837 s | 1.858 s | 1.011 | ✓ |
| 8 | 1.960 s | 1.961 s | 1.000 | ✓ |

전 수준에서 같은 자릿수다. **n = 1 비교이므로 비율 자체에 통계적 의미를 두지 않으며**, 선등록대로 자릿수만 판정했다. 두 run 모두 `VLLM_LOGGING_LEVEL=DEBUG`였으므로 DEBUG 자체의 비용은 상쇄된다.

### 관문 3 — 복구 검증: **통과**

`revert` 후 SHA256이 `46ce1675a2b55e36d4d6dd0154edae793cd3874ed1fbe16e74a40ed7c809298e`로, pristine 기대값과 **일치**했다. 이어진 `apply`가 `70942d16…`로 복원했다.

### 부수 관측 — bucket padding 낭비의 정량화

이 신호가 Track A에서 무엇을 주는지 보이는 관측이다.

| `request_nums` | bucket | 낭비 slot / step | 지속 step | 낭비율 |
|---|---|---|---|---|
| 1 | 1 | 0 | 127 | 0 % |
| 2 | 2 | 0 | 127 | 0 % |
| 3 | 4 | **1** | 127 | 25 % |
| 5 | 8 | **3** | 127 | 37.5 % |
| 8 | 8 | 0 | 127 | 0 % |

낭비율은 `(bucket − request_nums) / bucket`이다. 이는 slot 기준 산술이며 **실제 연산·시간 낭비를 측정한 값이 아니다.** 그 관계는 Track A의 측정 대상이다.

### 선등록 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| 1 | run A에 `[BUCKET]` 0줄 | ✓ (0줄) |
| 2 | run B에 decode step마다 1줄 | ✓ (635 = 5 × 127) |
| 3 | 관측 쌍이 사상표와 전건 일치 | ✓ |
| 4 | `3 → 4`, 낭비 1 slot | ✓ |
| 5 | `5,6,7 → 8` | 부분 확인 — `5 → 8`만 관측됐다. 6·7은 이번 격자에서 발생하지 않았다 |
| 6 | latency 자릿수 무변화 | ✓ |
| 7 | `request_nums=None` 없음 | ✓ |

예측 5는 격자가 6·7을 만들지 않아 **일부만 확인**됐다. 사상표의 나머지 항목은 `UNKNOWN`으로 남긴다.

## 핵심 발견

1. **per-step decoder bucket이 이제 관측된다.** [TASK10](TASK10.md)에서 "관측 불가"였던 값이 로그 1줄로 노출됐고, 관측된 사상이 `select_bucket_size` 산식과 전건 일치했다. **Track A 진입 gate가 열렸다.**
2. **신호의 의미론이 채택 전에 검증됐다.** 값이 나온 것과 그 값이 옳은 것은 다르다. bucket 경계를 넘는 `3 → 4`, `5 → 8`을 격자에 일부러 넣어 흥미로운 부분을 실제로 관측했다.
3. **관찰자 효과가 자릿수 수준에서 없다.** 추가된 것이 `logger.debug` 1회뿐이므로 예상된 결과지만, 확인 없이 가정하지 않았다.
4. **`.pyc` 캐시가 patch를 무력화하지 않는다.** `__pycache__`가 쓰기 불가라 갱신되지 않지만 Python이 source 변경을 감지해 재컴파일한다. `inspect.getsource`로 load된 코드를 직접 확인하는 것이 이 종류 patch의 필수 검증 단계다.
5. **`patches/` 정책이 실전에서 작동한다.** version guard, SHA256 guard, 적용 후 문법 검사, 복구 후 hash 검증이 모두 예상대로 동작했고, 사본에서 왕복을 먼저 검증한 덕에 site-packages에는 단 한 번의 성공적 적용만 일어났다.
6. **bucket padding 낭비가 정량화된다.** 동시성 3에서 slot 25 %, 5에서 37.5 %가 padding이다. 이는 slot 산술이며 시간 비용과의 관계는 아직 측정되지 않았다.
7. **이번 격자에서는 수준 안에서 `request_nums`가 변하지 않았다.** 모든 요청이 같은 prompt·같은 `max_tokens`라 동시에 시작해 동시에 끝났기 때문이다. 요청이 순차로 빠지며 bucket이 **전이**하는 상황은 관측되지 않았다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(해석)** 발견 7은 Track A 설계에 직접 영향을 준다. 이번 격자는 "정상 상태에서 bucket이 무엇으로 고정되는가"만 보여준다. bucket **전이**(예: 8 → 4 → 2 → 1)를 관측하려면 요청들의 생성 길이를 서로 다르게 만들어 순차로 빠지게 해야 한다. `max_tokens`를 요청마다 다르게 주는 방식이 가장 단순하다.
- **(해석)** 낭비율 표는 slot 기준이다. RBLN decoder가 compile된 batch 크기로 고정 실행된다면 slot 낭비가 곧 연산 낭비일 수 있지만, 그것은 가정이지 관측이 아니다. Track A는 낭비 slot과 step latency의 관계를 실제로 재야 한다.
- **(hypothesis)** `request_nums=6` 또는 `7`이 발생하는 상황은 요청이 순차로 빠질 때 자연히 생긴다. 그때도 `→ 8`이 나올 것으로 예상하지만 관측되지 않았으므로 `UNKNOWN`이다.
- **(해석)** patch가 site-packages에 남아 있다는 것은 **이 host의 substrate가 더 이상 pristine이 아니라는 뜻**이다. 이후 모든 run은 `apply.sh status`를 artifact에 남겨 patch 적용 여부를 provenance로 기록해야 한다. 이것이 정책 7항목의 마지막 항목이 요구하는 바다.

## 확인되지 않은 사항

- `request_nums`가 6, 7일 때의 bucket (`UNKNOWN`). 이번 격자에서 발생하지 않았다.
- bucket **전이**가 실제로 일어나는 상황의 거동 (`UNKNOWN`). 발견 7 참조.
- slot 낭비와 step latency·연산량의 관계 (`UNKNOWN`). Track A의 측정 대상이다.
- prefill 단계의 `padded_batch_size`는 이 patch가 다루지 않는다. `is_prompt` 분기는 항상 1이며 patch 지점 밖이다.
- `select_bucket_size`의 `@cache`가 장시간 실행에서 메모리를 얼마나 쓰는지 (`UNKNOWN`, 인자 조합이 유한하므로 문제되지 않을 것으로 보이나 확인하지 않았다).
- patch가 적용된 상태에서 package가 재설치·업그레이드되면 어떻게 되는지 (`UNKNOWN`). `apply.sh`의 version guard가 잡아주지만 재설치 자체를 막지는 않는다.

## 실패 / 무효 시도

1. **이 세션에서 patch를 직접 적용하지 못했다.** 대상 파일과 상위 디렉터리가 전부 `root:root drwxr-xr-x`이고, 실제 `touch` 시험도 `Permission denied`였다. 사용자는 `sudo` 그룹(gid 27)에 속하지만 `sudo -n true`와 `sudo -n -l`이 모두 `a password is required`였고, Bash 도구에 TTY가 없어 비밀번호를 받을 수 없었다. 세션 안의 `!` 실행도 같은 이유로 `a terminal is required to read the password`로 실패했다.
   - 사용자가 **별도 터미널에서** `apply` 1회, `revert && apply` 1회를 실행했다. 두 출력 전문을 `<RUN>/patch-state-reverted.txt`에 원문 그대로 보존했다.
   - 대안으로 `PYTHONPATH` + import hook 기반 runtime observation adapter(root 불필요)를 제시했으나, 사용자가 선등록한 file-patch 방식 유지를 선택했다. 선등록 절차를 사후에 바꾸지 않았다.
2. `git diff --check`가 patch 파일에서 trailing whitespace 1건을 경고한다. 이는 unified diff의 **빈 context 줄**(공백 1칸)이며 `patch` 적용에 필요하다. 제거하면 patch가 깨지므로 그대로 두었다.
3. 무효로 판정한 측정은 없다. 두 run 모두 전 요청 status 200.
4. Device·RSD·package 변경은 없었다. patch 이외의 site-packages 수정도 없었다.

## 연구 원칙에 미치는 영향

- **관측 수단을 추가했으면 그 수단의 의미론을 채택 전에 검증한다.** 값이 나오는 것과 값이 옳은 것은 다르다. 이번에는 기대 사상표를 선등록하고 전건 일치를 요구했다.
- **검증 격자는 흥미로운 경계를 포함해야 한다.** 동시성 1/2/4/8만 돌렸다면 사상이 항등처럼 보였을 것이다. 3과 5를 넣었기 때문에 `3 → 4`, `5 → 8`이 드러났다.
- **관찰자 효과를 가정하지 않고 잰다.** 자릿수 판정만 하고 n=1 비교에 통계적 주장을 붙이지 않는다.
- **site-packages를 바꿨으면 그 사실이 provenance가 된다.** 이후 모든 측정 run은 `apply.sh status` 출력을 artifact에 남긴다. Git이 추적하지 않는 상태 변경은 명시적으로 기록해야 재현이 가능하다.
- **적용 전에 사본에서 왕복을 검증한다.** site-packages에 실패한 적용이 남는 것을 피할 수 있다.
- **권한이 없어 agent가 수행할 수 없는 단계는 우회하지 않고 보고한다.** 승인된 방식을 임의로 다른 방식으로 바꾸지 않았다.

## 다음 작업

Track A(decoder bucket characterization)의 진입 조건이 갖춰졌다. 착수 시 이월할 사항:

1. **bucket 전이를 만들려면 요청별 생성 길이를 다르게 해야 한다.** 이번 격자는 정상 상태만 보여줬다.
2. **`request_nums` 6, 7의 사상은 아직 미관측**이다.
3. **slot 낭비와 시간 비용의 관계가 Track A의 실제 측정 대상**이다. 낭비율 표는 산술일 뿐이다.
4. 모든 run에 `apply.sh status` 출력을 provenance로 남긴다.

Stage 2 repeated-prefix baseline도 독립적으로 진행 가능하며 설계 제약은 [TASK11](TASK11.md)의 "다음 작업" 절에 있다.

사용자 지시 없이 다음 TASK를 자동 시작하지 않는다.

## 재현 정보

- 선등록 commit: `1ca902c10bd4104e384a99d787cd046fa8095405`
- **측정 시작 시각: 2026-08-19 18:26:1x KST.** 선등록 commit 시각은 2026-08-19 18:26:04 KST이므로 **선등록이 측정보다 앞선다.**
- 측정 종료 시각: 2026-08-19 19:31:37 KST
- Base commit (측정 중 HEAD): `1ca902c10bd4104e384a99d787cd046fa8095405`, dirty = untracked `.idea/` 및 gitignored `results/`, `models/`
- **Patch 적용 상태 (측정 종료 시점): `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`**
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)
- Raw artifact: `results/npu/stage1/20260819-182600-bucket-patch/`
  - `measurement-start.txt`, `measurement-end.txt`
  - `patch-state-{before,applied,reverted,final}.txt`
  - `server-runA.log`, `server-runB.log`
  - `probe-runA/`, `probe-runB/` — `concurrency_probe.json`, `concurrency_summary.json`
  - `bucket-log-count.txt`(635), `bucket-pairs.txt`(쌍 빈도표)
  - `rbln-smi-before.txt`, `rbln-smi-after-runB.txt`
- Patch: `patches/vllm_rbln-0.11.1/{decoder_bucket_observe.patch,apply.sh,README.md}` (git 추적)
- 실행 script: `experiments/npu/stage1/concurrency_probe.py`(변경 없이 재사용), `experiments/npu/stage1/prompt.txt`
- Isolation launcher: `experiments/npu/launch/run_isolated_python.sh`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(**patched**), `optimum-rbln 0.11.1`, `rebel-compiler 0.11.1.post1`, `torch 2.11.0+cpu`
- Host: `atom-max8`, device `rbln0`–`rbln3`
