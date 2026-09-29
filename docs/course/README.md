# 단기강좌(Physical AI) 테스트 자산 색인

강좌용으로 만든 모델·데이터·스크립트는 **주행 데모 모델과 분리**해 둔다. 이 문서가
그 경계다. 갱신: 2026-09-23.

## 1. 주행 모델 (건드리지 않는 것)

| 용도 | 서버 위치 | 비고 |
|---|---|---|
| 데모 기본 정책 | `runs/navvla_reasoning_r26/checkpoints/last` | `smolvla_demo.sh` 기본값. Stanley 순항 선생, 차선중심 정상 |
| 신호정지 실험 | `runs/navvla_reasoning_r27`, `r28` | r28 = 신호정지 실패 사례(docs/ver/20260918_2028) |
| 베이스 | `runs/navvla_smolvla_v3y` | 모든 r-시리즈의 `--base-checkpoint` |
| 코퍼스 | `data/packed_v3y`, `packed_v9*`, `packed_stanley`, `packed_signal`, `data/lerobot/v28r` | 주행 학습 스테이징 |

## 2. 강좌 테스트 자산 (2026-09-22/23, 다중 물체 회피 홀드아웃 실험)

질문: 여러 물체로 회피를 배우면 학습 안 한 물체도 피하는가. **결과: 학습 물체조차
안 피함 — 액션 헤드가 장애물에 무반응.** 상세 [docs/ver/20260922_2113](../ver/20260922_2113_multiobj-avoidance-holdout.md).

### 서버 (`autolab_sw@115.145.211.157:~/sunhong/nav-vla`)

| 종류 | 위치 | 내용 |
|---|---|---|
| 학습 런 | `runs/course/` (비어 있음) | r29~r32 는 전부 실패 런이라 09:1x 삭제(사용자 결정). 로그·프로브 결과는 `logs/course/` 에 남아 있고 `code/course/launch_*.sh` 로 재현 가능 |
| 데이터 | `data/course/packed_multi{,_fix,_hard}` | 학습 플릿 회피 코퍼스 (완만 92+20, 강함 24) |
| 홀드아웃 | `data/course/packed_multi_heldout`, `packed_multi_hard_heldout` | 사람·드럼통·초록 해치백 — 학습 금지 |
| LeRobot | `data/course/lerobot/v32r` | v28r 스테이징 + multi + fix + hard. v29r 은 삭제(v32r 이 상위집합, convert 로 재생성 가능) |
| 로그 | `logs/course/` | 학습 로그 4개 + 프로브 결과 `probe_brake_*.txt`, `probe_cf_*.txt` |
| 스크립트 | `code/course/` | `convert_v29r/v32r.sh`, `launch_r29~r32.sh`, `probe_obstacle_brake.py`(v2 dv), `probe_obstacle_counterfactual.py` |

### 로컬 (`~/ROS2_project/sant-vla`)

| 종류 | 위치 | 내용 |
|---|---|---|
| 원본 세션 | `src/sant_vla_pkg/data_course_multiobj/session_*` (5개, 3.1 GB) | packed 의 30 Hz 원본. gitignore |
| packed | `src/sant_vla_pkg/data_course_multiobj/packed_*` | 서버 사본과 동일 |
| 수집 | `tools/collect_multiobj_avoid.sh` | 플릿/홀드아웃/`V1_ONLY`/`OB_ACCEL`/`OB_STOP_MARGIN`/`LG` |
| 학습 체인 | `tools/multiobj_train_chain.sh`, `tools/multiobj_hard_chain.sh` | 라벨 → rsync → convert → launch |
| 폐루프 평가 | `tools/eval/multiobj_heldout_eval.sh` | `smolvla_demo.sh --no-gui` + `avoidance_trial.py --no-supervisor`; 결과 `eval_out/course/multiobj_eval/` |
| 수집 로그 | `eval_out/course/multiobj_multi{,_fix,_hard}/` | collect/finalize 로그 |
| GUI | `lecture_test.sh` | Driving Studio lecture 모드(경기 선택기 숨김, 장애물 클릭 배치·드래그·삭제) |
| 모델 | `src/simulation_pkg/models/ob_{box,barrel,cone,barrier,person}` | gitignore(`models/`)에 걸림 — `git add -f` 필요 |
| 학습기 | `server/code/train_reasoning.py` | `--action-multiobj-weight`(절대값), noun-agnostic 부스트. 서버 `code/` 와 동일 |

## 3. 재실행 방법

```bash
# 수집 (강한 제동, v1 만)
TAG=multi_hard V1_ONLY=1 OB_ACCEL=1.5 OB_STOP_MARGIN=9 TRAIN_GROUPS=36 HELDOUT_GROUPS=6 \
  bash tools/collect_multiobj_avoid.sh
# 서버 변환 + 학습
bash tools/multiobj_hard_chain.sh          # v32r → r32 (GPU0)
# 프로브 (서버)
CUDA_VISIBLE_DEVICES=1 ./venv/bin/python code/course/probe_obstacle_brake.py \
  runs/course/navvla_reasoning_r32/checkpoints/last/pretrained_model \
  --packed data/course/packed_multi_hard_heldout data/course/packed_multi_hard --n 40
# 폐루프
CKPT=runs/course/navvla_reasoning_r32/checkpoints/last/pretrained_model N=2 \
  bash tools/eval/multiobj_heldout_eval.sh r32
```

## 3.5 자동 정리

수집·평가·학습 체인은 끝날 때 `tools/cleanup_artifacts.sh` 를 자동 호출해 캐시·로그를
지운다(학습 중인 런과 원본 세션은 건드리지 않는다). 등급과 주의점은
[docs/course/cleanup.md](cleanup.md).

## 4. 정리 이력 (2026-09-23)

(서버 전체 정리·모델 백업은 [docs/ver/20260923_1050](../ver/20260923_1050_server-cleanup-and-model-backup.md))

- 서버: r29~r32 중간 체크포인트 8개(8.8 GB) 삭제, `lerobot/v29r`(361 MB)·스테이징
  심볼릭 디렉터리 삭제, 나머지를 `runs/course`·`data/course`·`logs/course`·`code/course`
  로 이동. 이어서 r29~r32 최종 체크포인트(4.4 GB)도 삭제(사용자 결정, 09:1x).
  디스크 100% → 약 14 GB 여유.
- 로컬: 파일럿 packed/세션, 중단된 세션(`_aborted`) 삭제(약 150 MB). `data_multiobj`
  → `data_course_multiobj` 개명, 평가/수집 로그를 `eval_out/course/` 로 이동.
- gz 시뮬 로그(`~/.gz/sim/log`)는 수집·데모 스크립트가 매번 지운다.

## 5. 강좌 설계에 남기는 결론

VLA 액션의 "미학습 물체 일반화"는 현재 스택에서 시연 불가. 3일차 과제는 VLM
감독의 인식 일반화(학습 안 한 물체를 보고 차선변경 문장을 내리는가)로 설계한다.
