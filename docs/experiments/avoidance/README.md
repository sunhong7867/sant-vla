# 장애물 회피 VLA — 개인 연구 폴더 (2026-09-22 ~ 2026-10-03)

2026-10-03 교수님 방향 전환으로 **단기강좌 실습에서 분리**해 개인 연구로 계속한다.
(장애물 회피는 YOLO·라이다 규칙으로도 되는 일이라 "VLA 로만 되는 실습"이 아니라는 판단. 강좌 쪽은 [../단기강좌.md](../../course/단기강좌.md) 개정안 참조.)

연구 질문: **문구 없이(카메라만 보고) SmolVLA 가 우리 차선의 장애물에만 반응해 차선을 바꿀 수 있는가, 그리고 학습 안 한 물체에도 그런가.**

---

## 1. 지금까지 결론 (요약)

| 단계 | 시도 | 결과 |
|---|---|---|
| 정지 시연 (r29~r32) | 장애물 앞 정지 → 관찰 → 추월 | 액션이 장애물에 무반응 |
| 직접 차선 변경 (r33~r39) | 꺾는 시연, 한 자리 | 반응은 시연의 약 35 %, 폐루프 충돌. **위치 prior**(한 자리에서 무조건 꺾음) 발견 |
| 정답 상황 문구 (r40, r41) | 좌표 오라클이 "앞에 장애물" 문구 제공 | 문구가 있으면 꺾음(r41 같은 20 곳 차선 변경 18~20/20, 회피 9/20). 판단은 스크립트 |
| 문구 없이 (r42, sw5~sw80) | 회피 시연 수 스윕 | 시연이 늘수록 회피도, **빈 차선 꺾기 습관**도 함께 증가 |
| 같은 자리 짝 (r43~r47) | 회피 + 같은 자리 직진 짝 | 자리 습관은 사라짐(빈 차선 0/20), 회피도 0/20. 짝 137 쌍에서 장애물 반응 +0.27 m. r47(짝 286, 2차선·왼쪽만)은 장애물 무관 왼쪽 쏠림 1.1 m |
| 다장애물 주행 설계 | 1·2차선 출발, 한 바퀴 장애물 3 개, 꺾기 거리·폭 무작위 | 시범 6 바퀴 통과(양방향 회피·복귀·충돌 0). **120 바퀴 본 수집은 8 ep 에서 중단**(방향 전환) |

핵심 교훈: **회피 비중은 "얼마나 자주 꺾나", 같은 자리 짝은 "언제 꺾나"를 정한다. 한쪽 방향만 보여 주면 방향 편향이 생긴다.**
상세: [종합표](20261002_1354_avoidance-models-summary.md) · [지름길 학습 개념](20261002_1414_shortcut-learning.md) · [문제 풀이 종합](20261001_1029_avoidance-problem-solving-summary.md)

---

## 2. 문서 (시간순)

| 날짜 | 문서 |
|---|---|
| 08-28 | [장애물 회피 설계 — 무엇이 코드이고 무엇이 VLA인가](obstacle_avoidance_design.md) (VLM 목격 + 좌표 차선 판정 감독) |
| 09-22 | [다중 물체 회피 홀드아웃 — 수집 인프라](20260922_2113_multiobj-avoidance-holdout.md) · [강좌 테스트 자산 색인 (당시)](course_assets_index.md) |
| 09-29 | [차선변경 램프](20260929_1131_lane-ramp-swerve.md) · [데이터 스케일링 계획](20260929_1503_avoid-data-scaling-plan.md) · [폐루프 충돌 원인](20260929_1823_closed-loop-avoid-failure.md) |
| 09-30 | [위치 이동 r38/r39 — 위치 prior](20260930_1530_ramp70-relocation-result.md) · [상황 문구 설계 r40](20260930_1601_situation-conditioned-action-design.md) · [curv_boost 와 부정 대조](20260930_1953_curv-boost-and-negative-control.md) · [정답 문구 1단계](20260930_2107_oracle-situation-stage1-partial.md) · [위치 다양화 r41](20260930_2302_div-corpus-pose-stream-and-clips.md) |
| 10-01 | [문제 풀이 종합](20261001_1029_avoidance-problem-solving-summary.md) · [영상·충돌 판정 수정](20261001_1108_clips-and-collision-judge-fix.md) · [자기 인지 A vs B](20261001_1317_self-perception-a-vs-b.md) · [시연 수 스윕](20261001_2226_box-demo-scaling-sweep.md) |
| 10-02 | [r43 묶음 + 100 곳 평가](20261002_1006_r43-paired-groups-stat-eval.md) · [위치 스트림 수정 + r44 계획](20261002_1038_pose-stream-fix-and-r44-plan.md) · [r44](20261002_1225_r44-half-avoid-result.md) · [종합표](20261002_1354_avoidance-models-summary.md) · [지름길 학습](20261002_1414_shortcut-learning.md) · [2 주 계획](20261002_1634_avoidance-next-plan.md) · [r45](20261002_1729_r45-pair60-result.md) · [r46](20261002_1857_r46-pair137-result.md) · [r41 정답 문구 20 곳](20261002_2020_r41-oracle-20spots.md) · [다장애물 주행 설계](20261002_2106_multi-obstacle-run-design.md) |
| 10-03 | [r47 + 다장애물 시범](20261003_0940_r47-multiobj-pairs-and-pilot.md) · [관련 연구](20261003_0944_vla-shortcut-related-work.md) · [VLA 문제점 28 가지](20261003_0958_vla-failure-modes-and-fixes.md) · [파인튜닝 방식](20261003_1014_finetuning-recipe.md) |

---

## 3. 코드·도구 (이동하지 않음 — 경로 그대로)

| 용도 | 위치 |
|---|---|
| 수집기 (단일·다장애물) | `src/sant_vla_pkg/scripts/collect_corpus.py` (`--obstacle-groups`, `--multi-groups/-trigger/-ramp/-back`) |
| 라벨 | `src/sant_vla_pkg/scripts/label_reasoning.py` (다장애물: 프레임별 대상 장애물 선택) |
| 수집 래퍼 | `tools/collect_multiobj_avoid.sh`, `tools/div_run.sh`, `tools/multi_run.sh`, `tools/multi_chain.sh` |
| 체인 | `tools/r4{4,5,6,7}_chain.sh`, `tools/pair_collect_chain.sh`, `tools/mpair_collect_chain.sh`, `tools/mrun_sweep_chain.sh`(미실행), `tools/mpilot_after_r47.sh` |
| 평가 | `tools/eval/stat_eval.sh`(조건 ours/adj/empty/held/heldcar/ours1/adj1/empty1/held1), `tools/eval/stat_analyze.py`, `tools/eval/avoidance_trial.py`(`--oracle-situation`, `--start-lane`), `tools/eval/multiobj_heldout_eval.sh` |
| 서버 변환·학습 | `server/code/course/convert_v4*r.sh`, `launch_r4*.sh`, `convert_mrun.sh`, `launch_mrun.sh` |
| 학습 옵션 | `server/code/train_reasoning.py` (`--contrast-twin-boost`, `--obstacle-boost`, `sampled share by variant` 로그) |
| 정리 | `tools/sim_log_janitor.sh` (gz 로그 폭증 대응), `tools/cleanup_artifacts.sh` (`KEEP_TRIALS` 기본 100 000) |

## 4. 데이터·체크포인트

| 종류 | 위치 |
|---|---|
| 학습 묶음 (로컬 + 서버) | `data_course_multiobj/packed_{boxtri,boxpair,boxpair2,mpair,mpilot,div,boxv1,ramp70,...}` / 서버 `~/sunhong/nav-vla/data/course/` |
| 원본 세션 | 로컬 삭제됨 (2026-10-03, 사용자 승인 — packed 로 대체) |
| 체크포인트 (1TB USB 보관) | USB `/media/sh/75D7-DC5F/nav-vla/avoidance-research-models/` (2026-10-05 노트북에서 이동, 4.1 G) — `r40`(한 자리 학습 → 위치 습관 사례), `r41`(정답 상황 문구 조향, 회피 9/20), `r46`(문구 없이 장애물 반응 최대 +0.27 m), `r47`(왼쪽 쏠림 사례). 각 `pretrained_model/`, 서버 원본과 sha256 일치 확인(2026-10-03). r45 는 r46 에 포함돼 보관 안 함 |
| 서버 사본 | 2026-10-03 정리 대상 (runs/course, data/course 의 packed·lerobot). 학습 묶음은 로컬 `data_course_multiobj/packed_*` 와 에피소드 수 일치 확인 |
| 평가 결과 | `eval_out/course/stat_r4*.log`, `eval_out/course/multiobj_eval/` (r46·r47 일부 궤적 로그는 정리 스크립트로 소실) |

## 5. 다시 시작할 때

1. 다장애물 120 바퀴 수집: `TAG=mrun NRUNS=120 bash tools/multi_chain.sh` (약 3 h 예상이었으나 실제 속도는 더 느림 — 첫 43 분에 8 ep, 원인 미확인).
2. 40/80/120 바퀴 스윕: `bash tools/mrun_sweep_chain.sh` (서버 접속 필요, r48a~c).
3. 평가는 2차선(ours/adj/empty) + 1차선(ours1/empty1) + 미학습(held) 으로 빈 차선 대조를 항상 같이.
4. 진행 기록은 이 폴더에 `YYYYMMDD_HHMM_*.md` 로 추가하고 2 절 표에 한 줄.
