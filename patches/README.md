# Patch 관리 정책

설치된 `vllm-rbln` 또는 관련 package의 관찰 지점이 부족하더라도 site-packages를 직접 수정하지 않는다.

Patch를 추가할 때는 다음을 모두 기록한다.

1. 대상 package와 exact version
2. upstream file path와 적용 전 SHA256
3. patch가 scheduler, batch selection, KV allocation semantics를 바꾸지 않는다는 근거
4. observation-only 변경을 우선했다는 검토 결과
5. 적용 명령과 복구 명령
6. version/hash drift 발생 시 fail-loud로 중단하는 방법
7. patch 적용 여부를 run metadata에 남기는 방법

현재 실제 patch는 없다.
