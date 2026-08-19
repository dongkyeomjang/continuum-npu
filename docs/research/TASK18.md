# TASK18 — per-request/per-session 귀속 채널 구축과 검증 게이트

## 상태

DONE

## 판정

**게이트 통과.** G1 **8/8**, G2 **16/16**, G3 **정확히 일치**(server 19,360 == client 19,360). 후속 짝 비교 진입 조건이 충족됐다.

## 날짜

2026-08-19

## 목적

[TASK17](TASK17.md)이 "본 실험 전 필수"로 게이트화한 request id ↔ 세션 매핑을 구축하고, **동시성 하에서 per-request 귀속이 올바름을 구성상 정답이 알려진 실험으로 검증**한다.

## 배경

관련 TASK:

- [TASK17](TASK17.md) — 동시 workload에서 counter 증분의 per-request 귀속이 무효임을 발견하고 이 게이트를 요구했다. runner가 응답 `id`를 기록하지 않아 세션 귀속을 못 했다.
- [TASK15](TASK15.md) — 층 2 채널의 source 경로(`prefill_stats` ← `sum(cached_length)`).
- [TASK13](TASK13.md) — 로그 timestamp 1초 해상도.
- [TASK11](TASK11.md) — hit 문턱 129 token, hit 산식.

선등록 문서: [ATTRIBUTION_GATE_PREREG.md](ATTRIBUTION_GATE_PREREG.md)

## 시작 상태

- Repository / branch: `/home/rebel/continuum-npu` / `main`
- 선등록 commit: `37604b5d26884958083e3b56fc21f9c4b079dcd7`
- Git dirty: untracked `.idea/`만
- **Substrate: patched** (SHA256 `70942d16…`). 측정 전 gate 통과
- Model artifact: `models/Qwen3-4B-rbln-b8-s8192-d4-mb` (재compile 없음)
- Device: 32 visible ID 전부 idle, port 8000 비어 있음

## 수행 내용

1. **측정 전 join 경로를 source에서 확정**했다 (선등록 문서에 기록).
2. `--enable-prompt-tokens-details`가 응답에 층 2 값을 직접 담는다는 것을 source에서 확인하고, 실행 semantics를 바꾸지 않음을 근거와 함께 기록했다.
3. `session_runner.py`(JSONL per-request 기록)와 `join_check.py`(G1/G2/G3 fail-loud 판정)를 작성했다.
4. 선등록 문서·script를 **측정 시작 전에** commit했다 (`37604b5`).
5. Patch gate 통과 후 8 세션 × 2 turn을 동시 실행하고 게이트를 판정했다.

재compile, download, patch 변경, RSD 변경은 없었다.

## 변경된 파일

선등록 commit `37604b5`:

- `docs/research/ATTRIBUTION_GATE_PREREG.md` (신규)
- `experiments/npu/stage2/session_runner.py` (신규)
- `experiments/npu/analysis/join_check.py` (신규)

이번 기록 commit:

- `docs/research/TASK18.md` (신규)
- `docs/research/INDEX.md`

Raw artifact는 `.gitignore` 대상인 `results/npu/stage2/20260819-232300-attribution-gate/`에 있다.

## 1. Join 경로 (측정 전 확정)

```
client 응답 body["id"] = request_id
    completion/serving.py:144  request_id = f"cmpl-{self._base_request_id(...)}"
    completion/serving.py:398,453  응답 id=request_id

engine per-prompt id
    completion/serving.py:180  request_id_item = f"{request_id}-{i}"

server [PFX] 로그  REQUEST=cmpl-<base>-<i>-<suffix8>
```

**client id는 server 로그 id의 strict prefix다.** join은 `server_id.startswith(client_id + "-")`이며 **timestamp 정렬이 필요 없다.** 로그 timestamp는 1초 해상도라 정렬로는 동시 요청을 구분할 수 없다.

말미 8-hex suffix의 출처는 source에서 찾지 못했다 (`UNKNOWN`). join에는 영향이 없으며, **prefix 매칭이 2개 이상이면 즉시 오류**로 처리하도록 `join_check.py`에 fail-loud 검사를 넣었다. 이번 run에서 모호한 join은 없었다.

### per-request 층 2 채널

`--enable-prompt-tokens-details`를 켜면 응답의 `usage.prompt_tokens_details.cached_tokens`가 채워진다.

```
cli_args.py:135          enable_prompt_tokens_details
completion/serving.py:446-448  usage.prompt_tokens_details = PromptTokenUsageInfo(
                                   cached_tokens=num_cached_tokens)
       num_cached_tokens ← RequestOutput.num_cached_tokens
                         ← req_state.num_cached_tokens
                         ← prefill_stats.num_cached_tokens = sum(cached_length)   ← 층 2
```

**client가 자기 응답에서 읽으므로 귀속이 구성상 성립한다.** 로그 파싱도, timestamp 정렬도, counter 증분도 필요 없다.

## 실험 또는 검증 방법

`<RUN>` = `results/npu/stage2/20260819-232300-attribution-gate`

```bash
env -u PYTHONPATH VLLM_LOGGING_LEVEL=DEBUG VLLM_RBLN_METRICS=1 \
  vllm serve /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb \
  --host 127.0.0.1 --port 8000 \
  --enable-prefix-caching --enable-prompt-tokens-details > <RUN>/server.log 2>&1 &

env -u PYTHONPATH experiments/npu/launch/run_isolated_python.sh \
  experiments/npu/stage2/session_runner.py \
  --base-url http://127.0.0.1:8000 \
  --tokenizer-dir /home/rebel/continuum-npu/models/Qwen3-4B-rbln-b8-s8192-d4-mb \
  --arm gate --sessions 8 --turns 2 \
  --first-segment ladder:300:300 --later-segment fixed:8 \
  --generation fixed:32 --gap fixed:2 \
  --base-seed 20260822 --block-id g0 --sampling-seed 20260819 \
  --output-dir /home/rebel/continuum-npu/<RUN>/probe

curl -s http://127.0.0.1:8000/metrics > <RUN>/metrics-final.prom
# PID 특정 후 SIGTERM

env -u PYTHONPATH python3 experiments/npu/analysis/join_check.py \
  --rows <RUN>/probe/requests.gate.g0.jsonl \
  --server-log <RUN>/server.log \
  --metrics-dump <RUN>/metrics-final.prom \
  --output <RUN>/join_check.json
```

## 결과

### 조건 분리

- `requested_condition`: 8 세션 동시, 2 turn, 첫 segment ladder 300–2,400 token(300 간격), 이후 segment 8 token, 생성 32 고정, gap 2 초 고정, `--enable-prefix-caching --enable-prompt-tokens-details`, plan seed 20260822, sampling seed 20260819.
- `observed_condition`: 전 16 요청 status 200. turn 1 `prompt_tokens`가 정확히 300/600/…/2,400, turn 2가 340/640/…/2,440(첫 segment + 생성 32 + 새 segment 8). `cached_tokens` 필드가 실제로 채워졌다. patch state `patched`.
- `condition_reached`: `YES`.

### 게이트 판정

| 게이트 | 내용 | 결과 |
|---|---|---|
| **G1** | turn 1의 `cached_tokens = 0`이고 `kv_computed`가 그 세션 고유 prompt 길이와 일치 | **8/8 통과** |
| **G2** | id prefix join으로 찾은 `[PFX]` 결과가 `cached_tokens`와 모순 없음 | **16/16 통과** |
| **G3** | per-request `kv_computed` 합 = server `request_prefill_kv_computed_tokens_sum` 총계 | **19,360 == 19,360, 일치** |

모호한 join 0건, `request_id` 누락 0건. `[PFX]` 항목은 8개(turn 2 요청 수와 일치)였고 turn 1 요청 8개는 prefix cache 조회 대상이 아니라 항목이 없었다.

### 관찰 — per-request 귀속표

| 세션 | turn 1 prompt | turn 1 `cached` | turn 1 `kv_computed` | turn 2 prompt | turn 2 `cached` | 전생존 기대 | 결과 |
|---|---|---|---|---|---|---|---|
| 0 | 300 | 0 | **300** | 340 | 0 | 256 | miss |
| 1 | 600 | 0 | **600** | 640 | 0 | 512 | miss |
| 2 | 900 | 0 | **900** | 940 | 0 | 896 | miss |
| 3 | 1,200 | 0 | **1,200** | 1,240 | **1,152** | 1,152 | **HIT** |
| 4 | 1,500 | 0 | **1,500** | 1,540 | **1,408** | 1,408 | **HIT** |
| 5 | 1,800 | 0 | **1,800** | 1,840 | 0 | 1,792 | miss |
| 6 | 2,100 | 0 | **2,100** | 2,140 | 0 | 2,048 | miss |
| 7 | 2,400 | 0 | **2,400** | 2,440 | 0 | 2,304 | miss |

turn 1의 `kv_computed`가 8개 모두 **세션 고유값과 정확히 일치**한다. 이것이 G1이며, 동시 실행 중에도 per-request 귀속이 섞이지 않았음을 구성상 증명한다.

**HIT한 두 세션(3, 4)의 `cached_tokens`가 전생존 기대값과 정확히 같다** (1,152 / 1,408). [TASK11](TASK11.md)의 hit 산식이 다시 확인됐다.

`[PFX]` 집계: `CACHE-HIT` 2, `CACHE-PARTIAL` 6 — client가 본 2 HIT / 6 miss와 전건 일치한다(G2).

eviction OB 순서: `0, 1, 2, 3, 4, 5, 6, 7`. 8개 세션의 turn 2가 각각 slot 1개를 요구해 FIFO로 순차 evict됐다.

### 사전 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| 1 | G1 8/8 통과 | ✓ |
| 2 | `cached_tokens`가 실제로 채워진다 | ✓ (세션 3·4에서 1,152 / 1,408) |
| 3 | turn 2에서 일부 세션만 `cached > 0` | ✓ (2/8) |
| 4 | G2 전건 일치 | ✓ 16/16 |
| 5 | G3 일치 | ✓ 정확히 |
| 6 | 짧은 prompt 세션(300)의 turn 2도 재사용 가능 | ✗ **재사용 실패.** 다만 문턱 때문이 아니라 slot eviction 때문이다 (전생존 기대 256 > 0이었으나 slot이 사라졌다) |

6개 중 5개 적중. 예측 6은 "가능하다"는 뜻이었으나 이번 배치에서는 slot 압력 때문에 실현되지 않았다.

## 핵심 발견 (층 태그)

1. **`class`** — **per-request 귀속은 client 응답에서 읽는 것이 가장 견고하다.** `usage.prompt_tokens_details.cached_tokens`는 그 요청의 응답에 담겨 오므로 귀속이 구성상 성립한다. 로그 파싱·timestamp 정렬·counter 증분이 모두 불필요하다. 동시성이 얼마든 무관하다. OpenAI 호환 API를 내는 어느 stack에서나 같은 접근이 가능하다.
2. **`stack`** — **client id가 server 로그 id의 strict prefix다.** 이 관계 덕분에 로그를 세션에 join할 수 있다. 1초 해상도 timestamp로는 불가능한 일이다.
3. **`universal`** — **귀속 채널은 "정답을 구성으로 아는" 실험으로 검증해야 한다.** 세션마다 prompt 길이를 유일하게 만들어 turn 1의 계산량이 알려진 값이 되게 했다. 채널이 섞였다면 8개 값 중 하나라도 어긋났을 것이다.
4. **`universal`** — **세 게이트가 서로 다른 실패 양식을 잡는다.** G1은 귀속 뒤섞임, G2는 채널 간 모순, G3는 누락·중복을 잡는다. 하나만으로는 부족하다.
5. **`stack`** — **8 세션 = 8 outer slot에서 turn 2 재사용이 2/8로 떨어졌다.** [TASK17](TASK17.md)의 4/8보다 낮다. 이번에는 gap이 전 세션 동일(2 초)이라 turn 2가 **거의 동시에** 도착했고, [TASK17](TASK17.md)에서는 gap이 1–6 초로 흩어져 도착이 순차적이었다. [TASK17](TASK17.md)의 "gap 분포가 재사용률을 좌우한다"는 hypothesis와 방향이 일치한다.

## 해석

이하는 관찰이 아닌 해석·hypothesis다.

- **(해석)** 발견 5는 [TASK17](TASK17.md)의 가설을 지지하는 두 번째 데이터점이다. 다만 두 실험은 prompt 길이 구성도 달라(2,000 고정 vs 300–2,400 ladder) 단독 비교로 볼 수 없다. gap 분포를 유일한 축으로 삼은 실험이 필요하다.
- **(해석)** 세션 3·4만 살아남은 것은 FIFO pointer 위치와 도착 순서의 상호작용으로 보이나, 도착이 거의 동시(4.51–4.52 s)라 순서를 client 시각으로 구분할 수 없다. 어느 세션이 살아남을지는 이 구성에서 사실상 예측 불가다.
- **(해석)** G3가 정확히 일치한 것은 client 측 `prompt_tokens − cached_tokens`가 server의 `request_prefill_kv_computed_tokens` 산식과 **같은 식**이기 때문이다. 독립 검증이 아니라 **배선 검증**이다. 두 값이 다른 경로로 계산되지만 같은 정의를 쓴다.

## 확인되지 않은 사항

- server 로그 id 말미 8-hex suffix의 출처 (`UNKNOWN`). join에는 무관하다.
- 어느 세션이 살아남을지의 결정 요인 (`UNKNOWN`). 도착이 거의 동시라 순서를 구분할 수 없었다.
- gap 분포만을 축으로 한 재사용률 변화 (`UNKNOWN`). 발견 5는 두 실험의 비교이며 다른 요인이 함께 달랐다.
- `--enable-prompt-tokens-details`가 streaming 응답에서도 같은 값을 주는지 (`UNKNOWN`). 이번엔 non-streaming만 썼다. source상 `:584-589`에 streaming 경로가 있으나 확인하지 않았다.

## 실패 / 무효 시도

- 무효로 판정한 측정은 없다. 16 요청 전부 status 200이고 게이트 세 개가 모두 통과했다.
- 예측 6이 빗나갔다. 사후에 예측을 수정하지 않고 원인(문턱이 아니라 slot eviction)을 기록했다.
- Device·RSD·package·patch 변경 없음. server lifecycle 1회, 종료 후 device memory `0.0B` 복귀·context 소멸.

## 연구 원칙에 미치는 영향

- **per-request 값은 그 요청의 응답에서 읽는다.** 서버 상태를 요청 주변에서 스냅샷하는 방식은 동시성 하에서 무효다 ([TASK17](TASK17.md)). 응답에 실려 오는 값은 그 문제가 없다.
- **채널을 채택하기 전에 "정답을 구성으로 아는" 실험으로 검증한다.** 값이 그럴듯한지가 아니라 알려진 답과 맞는지를 본다.
- **게이트는 서로 다른 실패 양식을 각각 잡도록 여러 개를 둔다.**
- **배선 검증과 독립 검증을 구분한다.** G3는 같은 정의를 쓰는 두 경로의 배선을 확인한 것이지 정의 자체를 독립적으로 검증한 것이 아니다.

## 다음 작업

게이트가 통과했으므로 AGENTIC vs CONVENTIONAL 짝 비교 파일럿으로 진행한다. 이월할 사항:

1. `session_runner.py`의 JSONL이 per-request 1차 채널이다. `[BUCKET]` 로그는 step 단위 집계(utilization) 전용이다.
2. gap 분포가 재사용률을 좌우한다는 가설이 두 번째 데이터점을 얻었다. 짝 비교에서 gap을 유일한 축으로 두면 세 번째가 된다.
3. `--enable-prompt-tokens-details`를 계속 켠다.

## 재현 정보

- 선등록 commit: `37604b5d26884958083e3b56fc21f9c4b079dcd7`
- **측정 시작 시각: 2026-08-19 23:23:18 KST.** 선등록 commit 시각은 2026-08-19 23:23:05 KST이므로 **선등록이 측정보다 13초 앞선다.**
- 측정 종료 시각: `<RUN>/measurement-end.txt`
- Base commit (측정 중 HEAD): `37604b5d26884958083e3b56fc21f9c4b079dcd7`, dirty = untracked `.idea/` 및 gitignored `results/`, `models/`
- **Patch state: `patched`, SHA256 `70942d16d561d92a8aaf153ea5ce91109863b6d765862c9bcd7e71594301cc01`**
- Server flag: `--enable-prefix-caching --enable-prompt-tokens-details`
- plan seed: `base_seed=20260822`, `block_id=g0`
- Raw artifact: `results/npu/stage2/20260819-232300-attribution-gate/`
  - `measurement-start.txt`, `measurement-end.txt`, `patch-state.txt`
  - `server.log` — `[PFX]`·`[BUCKET]` 로그
  - `probe/requests.gate.g0.jsonl` — per-request 기록 16행
  - `probe/meta.gate.g0.json` — plan summary
  - `metrics-final.prom`, `join_check.json`
  - `rbln-smi-before.txt`, `rbln-smi-final.txt`
- 신규 코드: `experiments/npu/stage2/session_runner.py`, `experiments/npu/analysis/join_check.py`
- Package: `vllm 0.22.0+cpu`, `vllm-rbln 0.11.1`(**patched**), `optimum-rbln 0.11.1`, `torch 2.11.0+cpu`
- Host: `atom-max8`, device `rbln0`–`rbln3`
