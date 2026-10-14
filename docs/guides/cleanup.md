# 실행 잔여물 자동 정리

`tools/cleanup_artifacts.sh`. 수집·평가·학습 체인이 끝날 때 **자동으로 호출**된다
(2026-09-28 추가). 손으로 부를 일은 서버 정리(`--server`)나 원본 세션 정리
(`--sessions`) 때뿐이다.

## 등급

| 등급 | 대상 | 언제 |
|---|---|---|
| **안전 (기본)** | gz 시뮬 로그, `/tmp` 런타임 월드 사본, 정적 모델 SDF 캐시, `__pycache__`, ROS 런치 로그(최근 5개만), 데모 해설 로그 세션(최근 `KEEP_SCENE=3`개만), 폐루프 트라이얼 원본 로그(최근 `KEEP_TRIALS=40`개만) | 수집·평가 끝날 때 **자동** |
| `--server` | 변환 스테이징 심볼릭 디렉터리, **완료된** 런의 중간 체크포인트(`last` 가 가리키는 것만 보존), 50 MB 넘는 서빙 로그 truncate | 학습 체인 끝날 때 **자동** |
| `--sessions` | 로컬 30 Hz 원본 `session_*` 중 대응 `packed_*` 가 있는 것 | **수동만** |

`--dry-run` 으로 먼저 볼 수 있다: `bash tools/cleanup_artifacts.sh --all --dry-run`.

## 안 지우는 것 (의도적)

- **학습 중인 런**: `checkpoints/last` 가 없거나 로그에 `done in` 이 없으면 통째로
  건너뛴다. r34 가 돌 때 중간 체크포인트를 지워 프로브를 못 하게 되는 사고 방지.
  (부작용: `train_smolvla.sh` 계열 로그는 `done in` 을 안 찍어 `navvla_smolvla_v3y`
  가 항상 건너뛰어진다 — 베이스라 오히려 안전.)
- **원본 세션**: `packed_*` 는 10 Hz 서브셋이라 30 Hz 원본을 재생성할 수 없다.
  `--sessions` 는 v10·stanley·signal 등 **서버에 raw 사본이 없는 코퍼스**도 지우므로
  (dry-run 기준 로컬 18.5 GB) 반드시 먼저 `--dry-run` 으로 목록을 확인할 것.
- `packed_*`, `data/lerobot/*`, `logs/course/*.txt`(프로브 결과), `eval_out/*/**.jsonl`
  (평가 요약) — 전부 결과물이라 유지.

## 실측 (2026-09-28 첫 실행)

- 서버 5.2 GB 회수(완료 런 r33/r34/r35 의 중간 체크포인트 5개 + 스테이징 6개) →
  여유 14 GB → 19 GB.
- 로컬: 데모 해설 로그 262 MB → 1.3 MB, `__pycache__` 전부.
