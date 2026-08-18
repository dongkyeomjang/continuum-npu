# Rebellions NPU 실행 환경

- 조사일: 2026-08-18 (Asia/Seoul)
- Hostname: `rebel-pcie-0123`
- 저장소: `/home/rebel/vllm-continuum`
- Branch / HEAD: `dev` / `8e64d1340cd15f925b89b484fe9f64caaa552805`
- 조사 원칙: read-only 조회. package, driver, firmware, RSD를 변경하지 않았다.

## 1. OS와 Python

| 항목 | 확인값 |
|---|---|
| OS | Ubuntu 22.04.5 LTS |
| Kernel | `6.8.0-40-generic` |
| Architecture | `x86_64` |
| Python | `/usr/bin/python3`, Python 3.10.12 |
| pip | system installation |
| 활성 virtual environment | 없음 |

복사된 `.venv` venv는 원래 환경 `/home/csdc/...`를 가리키며 현 서버에서 `encodings`를 찾지 못해 실행되지 않았다. 삭제하지 않았고 `probably stale`로 분류한다.

## 2. NPU hardware

| 항목 | 확인값 |
|---|---|
| Model | RBLN-CA25 |
| Physical card | 8 |
| RBLN-visible device ID | 32 (`rbln0`–`rbln31`) |
| Device memory | ID당 15.7 GiB로 CLI에 표시 |
| 조사 시 할당 / 활용률 | 전 ID 0 MiB / 0% |
| Physical card 내 ID | 4 |

`rbln-smi` 표시의 32 ID를 32개 physical card로 해석하면 안 된다. 현 호스트는 8개 CA25 card가 card당 4개 RBLN-visible ID를 제공한다.

## 3. Topology, NUMA, RSD

- NUMA node 0: `rbln0`–`rbln15`
- NUMA node 1: `rbln16`–`rbln31`
- topology distance class:
  - `4`: 같은 physical card 내
  - `8`: 서로 다른 card, 같은 NUMA node
  - `12`: cross-NUMA
- RSD group 0에 32 ID가 모두 포함된 상태로 관찰됨

위 distance는 구조적 topology 증거일 뿐이다. bandwidth/latency 비균질성은 측정하지 않았으므로 `UNKNOWN`이다. RSD를 변경하지 않았다.

## 4. 설치 software stack

| Package | Version |
|---|---|
| `vllm-rbln` | 0.11.1 |
| `vllm` distribution | 0.22.0+cpu |
| `vllm.__version__` | 0.22.0 |
| `optimum-rbln` | 0.11.1 |
| `rebel-compiler` | 0.11.1.post1 |
| `torch-rbln` | 0.3.0 |
| `torch` | 2.11.0+cpu |

`vllm-rbln 0.11.1`의 package dependency는 `vllm==0.22.0+cpu`를 요구한다. Python module version은 local version tag `+cpu`를 표시하지 않으므로 harness는 module version `0.22.0`과 distribution version `0.22.0+cpu`를 별도로 검증한다.

`lmcache-rbln`, `lmcache`, `nixl-rbln`, `nixl`은 설치되지 않았다. 이는 Stage 2에서 external KV connector가 활성화되지 않았다는 구성 증거가 될 수 있지만, runtime의 모든 hidden path가 없다는 증거로 일반화하지 않는다.

## 5. 관리·benchmark tool

| Tool | 상태 |
|---|---|
| `rbln-smi` | 사용 가능 |
| `rbln-stat` | 사용 가능 |
| `rblnBandwidthLatencyTest` | 사용 가능, version 3.2.2 |

`rblnBandwidthLatencyTest --test_env_info`는 현 RSD 상태에서 enabled system device를 얻지 못했다. RSD 변경 금지 원칙에 따라 bandwidth test를 위해 구성을 바꾸지 않았다. Host↔NPU, NPU↔NPU 성능은 현재 `UNKNOWN`이다.

## 6. Source resolution 위험

저장소 root에서 일반 `python3`를 실행하면 `/home/rebel/vllm-continuum/vllm`이 site-packages보다 먼저 import된다. 이 local tree는 vLLM 0.10.2-family CUDA research fork이며 NPU substrate가 아니다.

격리 launcher의 실측 결과:

```text
cwd: /tmp/vllm-continuum-rbln.<random>
vllm.__file__: /usr/local/lib/python3.10/dist-packages/vllm/__init__.py
vllm.__version__: 0.22.0
vllm distribution version: 0.22.0+cpu
vllm_rbln.__file__: /usr/local/lib/python3.10/dist-packages/vllm_rbln/__init__.py
vllm-rbln version: 0.11.1
isolation invariant: PASS
```

## 7. Model artifact

`/home/rebel/.cache/huggingface`, `/home/rebel/.cache/rebellions`, `/mnt`, `/opt`에서 depth 5까지 `rbln_config.json`, `.rbln`, `config.json`을 탐색했으나 검증된 precompiled RBLN model을 찾지 못했다. 설치 package에도 즉시 실행 가능한 example/model은 포함되지 않았다.

결론: 대용량 download나 runtime compilation 승인 없이 실행할 수 있는 Stage 0 model은 **확인되지 않음**.
