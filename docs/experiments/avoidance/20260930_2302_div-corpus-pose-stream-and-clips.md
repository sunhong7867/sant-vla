# 위치 다양화 + v2 코퍼스(r41) 시작, 위치 스트림 탈락 원인(CPU 절전), 확대 영상 (2026-09-30 23:02)

1단계(정답 문구 오라클) 미통과([20260930_2107](20260930_2107_oracle-situation-stage1-partial.md)) 이후 2단계b:
동작 모델의 위치 쏠림을 끊는 코퍼스로 r41 을 학습한다. 그 과정에서 시범 수집 탈락률이 89% 로 튀어 원인을 찾았고,
사용자 요청으로 실패/성공 확대 영상을 만들었다.

## 1. 확대 영상

`eval_out/course/clips/` (r40, 좌표 정답 문구, curv_boost_slow 1.0, 박스, 저속):

| 파일 | 내용 |
|---|---|
| `avoid_zoom.mp4` (21 s) | 우리 차선 박스 → 문구 ahead → 회피 성공 |
| `crash_zoom.mp4` (15 s) | 옆 차선 박스 → 문구 clear → 그래도 차선 변경, 충돌 |
| `compare_stacked.mp4` | 위아래 비교 |

방법: 월드 `top_camera`(640×480, 화각 1.10 rad)를 `set_pose` 로 (−17.5, −6.5, 15 m) 수직 하향에 옮기고,
`ros_gz_bridge` 로 `/top_camera` 를 따로 브리지해 프레임 저장 → 차가 움직이는 구간만 자르고 아래 트랙 밖 회색 띠
크롭, 1.5 배, 나눔스퀘어 자막. 재현: `bash tools/eval/record_clip.sh` (+ `tools/eval/record_topic_frames.py`).
트리밍·자막 명령은 이 문서 끝 재현 절.

## 2. 코퍼스 설계 (packed_div)

| 항목 | 값 |
|---|---|
| 장애물 위치 | 에피소드마다 트랙 전체 무작위(`--ob-fixed-index` 없음), 출발은 장애물 20~30 m 상류 |
| 변형 | v0(빈 차선) / v1(우리 차선, 회피) / **v2(옆 차선 장애물, 차선 유지)** |
| 문구 | v2 라벨 "A {noun} stationary in the inner lane — keeping our outer lane" → `situation_of` = road clear |
| 시연 | Stanley, 트리거 10 m, 램프 9 m, 2 차선 출발 |
| 규모 | 학습 72 그룹(216 ep, 물체 7 종) + 홀드아웃 6 그룹(드럼통·사람) |
| 스크립트 | `tools/div_run.sh`(격리 + RAM 감시 + 정리, `TAG`/`TRAIN_GROUPS`/…) |

## 3. 시범 수집 탈락 원인 — CPU 절전 프로필

| 시범 | 조건 | 수집 → 통과 | tf Hz | cli Hz | 0.3 s 넘는 공백/ep (tf/cli) |
|---|---|---|---|---|---|
| (참고) ramp70 본 수집, 낮 | — | 192 → 142 (74%) | 54.7 | 23.4 | 3 / 4 |
| divpilot, 22:22 | balanced | 18 → 2 | 40.7 | 15.7 | 9.5 / 12 |
| divpilot2, 22:44 | balanced + 레코더 수정 | 9 → 2 | 47.5 | 17.4 | 5 / 8 |
| **divpilot3, 22:54** | **performance** + 레코더 수정 | **9 → 7 (78%)** | 52.1 | 20.3 | 4 / 6 |

- 탈락 사유 두 가지 모두 **위치 스트림 공백**에서 나온다: (a) tf 메시지가 ~1 s 늦게 와 그 사이 1.1~1.8 m 움직인
  ego 를 "인덱스가 바뀌었다"로 오판 → 재식별 → tf gap 무효, (b) 라벨용 CLI 위치(`--pose-source cli`)가 곡선에서
  0.4~0.8 s 끊겨 보간 오차 게이트(6 cm) 초과.
- 수집 중 CPU: `episode_recorder` 118~127%(MultiThreadedExecutor), `ruby`(CLI 위치 폴러) 90~118%. governor
  `powersave`, 프로필 `balanced`, 평균 1.97 GHz(최대 4.83). 온도 51 ℃ — 과열 아님.
- **`powerprofilesctl set performance`**(사용자 승인) 후 같은 시드로 78%. 전원 프로필이 원인. 체인 끝에서 balanced 로 복구.
- 보간 오차 추정(`w·v·gap²/8`)이 공백 0.36 s 에서 20 cm 를 내는 것은 heading 이 튄 결과(초당 약 9 rad 에 해당)로
  보인다 — 추정식 자체의 과대평가 가능성, 미해결.

### 레코더 수정 (`src/sant_vla_pkg/sant_vla_pkg/episode_recorder_node.py`)

tf 점프 판정 허용치를 `tf_jump_tol(1.0 m) + tf_jump_speed(4.0 m/s) × (마지막 수신 이후 경과 sim 시간)` 으로.
늦게 온 메시지를 인덱스 교체로 오판하지 않는다. 시뮬 자체가 멈춘 경우(sim 시간 정지)엔 허용치가 늘지 않는다.
divpilot2 에서 재식별 15 → 1 건.

## 4. r41 체인 (`tools/r41_chain.sh`, 23:02 대기 시작)

수집 완료 → `label_reasoning` → 서버 전송 → `convert_v41r.sh`(Stanley 순항 + packed_div) → `launch_r41.sh`(r40 레시피 +
`--situation-prompt`, GPU0) → `probe_situation.py`(인덱스 70 의 packed_ramp70 프레임 — r41 이 한 번도 학습 안 한 위치)
→ 로컬 정답 문구 폐루프: 인덱스 70·142 × 우리 차선/옆 차선 × curv_boost_slow 0.85/1.0 (박스 × 2) → 전원 프로필 balanced.

판정(스윕 시작 조건): 우리 차선 회피 2/2 **그리고** 옆 차선 유지 2/2, 두 위치 모두.

## 재현

```bash
powerprofilesctl set performance          # 수집 전 (끝나면 balanced)
TAG=divpilot3 TRAIN_GROUPS=3 HELDOUT_GROUPS=0 TRAIN_MODELS=hatchback_red,ob_box,ob_cone SEED_TRAIN=20261012 bash tools/div_run.sh
TAG=div bash tools/div_run.sh              # 본 수집
bash tools/r41_chain.sh                    # 이후 전부
bash tools/eval/record_clip.sh             # 영상 (r40, 기본 CLIPS="lane2:avoid lane1:crash")
# 트리밍·크롭·자막 (프레임 번호는 움직임 구간에서 고름)
F=/usr/share/fonts/truetype/nanum/NanumSquareB.ttf
ffmpeg -framerate 27.61 -start_number 952 -i frames_avoid/%05d.jpg -frames:v 588 \
  -vf "crop=640:384:0:0,scale=960:576:flags=lanczos,drawbox=x=0:y=ih-78:w=iw:h=78:color=black@0.55:t=fill,drawtext=fontfile=$F:textfile=cap_avoid.txt:fontcolor=white:fontsize=28:x=20:y=h-70" \
  -c:v libx264 -pix_fmt yuv420p avoid_zoom.mp4
```

## 미해결

1. 수집 중 전원 프로필 의존 — `div_run.sh` 에 프리플라이트(`powerprofilesctl get` 가 performance 가 아니면 경고)를 넣을지.
2. 레코더 MultiThreadedExecutor busy-wait(메모리 기록된 Jazzy 이슈) — 코어 하나를 계속 먹는다.
3. CLI 위치 폴러(ruby 한 코어) — 라벨이 CLI 소스라 끌 수 없음. tf/CLI yaw 불일치(회전 중 슬립각 차이) 정리 후 tf 로 전환 검토.
4. 보간 오차 추정식의 과대평가 여부.

## 결과 (2026-10-01 03:28 체인 종료, 10:10 정리)

### 수집

- 학습 216 수집(214 success) → **109 통과(50%)**: v0 38, **v1 27**, v2 44. 탈락: 곡선 보간 오차 79, tf gap 25, 공백 1.
  시범(78%)보다 낮다 — 레코더 재식별 28 건이 남았고, 밤새 부하 변동 추정(미확인).
- 살아남은 장애물 위치는 트랙 전체(인덱스 50 칸 구간 8 개 모두에 v1 2~5, v2 4~8)에 퍼져 있다 — 다양화 목적은 유지.
- 홀드아웃은 gz 스폰 실패(`OBSTACLE_SPAWN_FAIL`, 서비스 wedge)로 없음.
- 체인 로그의 Traceback 은 서버 기본 python3(lerobot 없음)으로 문구 통계를 출력하다 난 것 — 학습과 무관.

### 학습

r41: 02:03~02:58 (0.89 h), GPU0, v41r.

### 오프라인 — `probe_situation.py` (인덱스 70, packed_ramp70 프레임 = r41 이 학습하지 않은 위치)

| | 창 | 문구 clear | 문구 ahead | 해설 검출 | (r40 clear / ahead) |
|---|---|---|---|---|---|
| v1 | 10–14 m | +0.26 | +1.01 | 4/30 | +0.34 / +1.43 |
| v0 | 10–14 m | +0.26 | +0.94 | 0/30 | +0.33 / +1.34 |
| v0 | 6–10 m | +0.25 | +0.91 | 0/30 | +0.32 / +1.18 |

- 빈 차선 쏠림: r38 +0.65 → r40 +0.33 → **r41 +0.25**(창과 무관하게 일정 — 위치 특이적 정점이 사라짐).
- 문구 효과(ahead − clear)는 r40 약 1.0 m → r41 약 0.7 m 로 줄었다. 해설 검출은 약해짐(10–14 m 4/30, r40 14/30) — YOLO
  경로에선 무관.

### 폐루프 — 좌표 정답 문구, 박스 × 2

| 위치 | 장애물 | curv_boost_slow 0.85 | curv_boost_slow 1.0 |
|---|---|---|---|
| 인덱스 70 | 우리 차선 (ahead) | 충돌 2/2 (0.38 m) | **충돌 2/2 (1.91~1.94 m, 최근접 1.95~2.15 m)** |
| 인덱스 70 | **옆 차선 (clear)** | **유지 2/2** (0.21~0.23) | **유지 2/2** (0.46) |
| 인덱스 142 | 우리 차선 (ahead) | 충돌 2/2 (0.68~0.76) | **회피 2/2** (2.18~2.29) |
| 인덱스 142 | **옆 차선 (clear)** | **유지 2/2** (0.24~0.25) | **유지 2/2** (0.05) |

판정:

1. **부정 대조 통과** — 옆 차선 장애물에서 문구 clear 면 두 위치·두 설정 모두 차선 유지 8/8. r40 은 이 조건에서 4/4 충돌.
   위치 쏠림이 폐루프에서 되먹임으로 커지던 문제는 코퍼스(위치 무작위 + v2)로 풀렸다.
2. **회피는 1.0 에서 3/4 조건** — 인덱스 142 는 2/2, 인덱스 70 은 오프셋 1.9 m 까지 가서 박스 모서리에 걸림(필요 약 1.8 m +
   여유). 문구가 호 14 m 에서 ahead 로 바뀐 뒤 오프셋은 12 m +0.4 → 8 m +1.6 → 6 m +2.2 m 로, 시연(3.15 m 차선변경)보다
   작고 늦다. 0.85 에선 어디서도 못 피함.
3. **스윕 시작 조건(두 위치 모두 회피 + 유지)은 아슬아슬하게 미통과.** 그러나 이제 측정이 유효하다 — 부정 대조가
   통과하므로 회피가 나오면 위치 암기가 아니다. v1 이 27 개뿐이라는 점이 회피 폭 부족의 유력 후보이고, 이것이 바로
   스케일링 스윕이 답할 질문이다.

### 다음 후보

- **v1 을 늘린 코퍼스**: 같은 설정으로 v1 위주(`V1_ONLY`) 추가 수집 → v1 27 → 80+. 스윕(5/10/20/40/80, 정답 문구)으로 바로 이어짐.
- curv_boost_slow 1.0 을 회피 평가의 기본으로 할지 — 순항 곡선 회귀 확인 필요.
- 문구 ahead 전환 거리(라벨 14 m)를 늘린 라벨로 재학습하면 회피가 일찍 시작될 수 있음(미검증).
