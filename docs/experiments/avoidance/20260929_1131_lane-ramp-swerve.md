# 회피 시연 차선변경 램프 + 오프라인 하니스 검증과 한계 (2026-09-29 11:31)

단기강좌 3일차 "학습 안 한 물체를 VLA 가 회피" 재도전의 첫 단계. r33~r35 가 시연의
30~40% 에서 멈춘 원인 중 **시연 모양** 쪽을 고쳤다. 이전 판정은
[20260922_2113](20260922_2113_multiobj-avoidance-holdout.md) 의 09-28 절.

## 원인: 차선 즉시 교체가 한 프레임 조향 스텝을 만들었다

`packed_swerve` v1 을 열어 보니 회피는 차선변경이 아니라 급조향이었다.

```
ep_0016 hatchback_red 2.16 m/s   fwd = 장애물까지 중심 호 거리
fwd 7.70  lat +0.22  steer +0.105
fwd 7.70  lat +0.22  steer +0.600   ← 한 프레임(0.1 s)에 +0.50 rad
fwd 7.35  lat +0.26  steer +0.600   (약 0.5 s 포화 유지)
```

- 수집기는 트리거 거리에서 goal 의 `lane` 을 바꿨고, route_oracle 은 기준 경로를 그
  틱에 lane1 으로 갈아 끼웠다. pure pursuit(전방주시 약 3.4 m)이 옆으로 3.15 m
  튄 목표점을 보고 곡률 약 0.29 를 요구 → 한계 0.24 에 클램프 → 조향 0.6 포화.
- 24개 v1 전부 조향 피크 0.60, 한 프레임 최대 조향 변화 평균 0.77 rad.
- 3 s 액션 청크는 "언제 꺾이는지"가 조금만 흔들려도 이 스텝을 평균내 작은 완만한
  편향으로 만든다. r33~r35 의 반사실 반응 0.4~0.5 m(시연 1.36 m)와 맞는 설명이지만,
  **이것만으로 천장이 설명된다는 증명은 아니다** — 재학습 결과로 판정한다.

같은 조사에서 나온 부수 사실:

- 트랙 차선 간격은 **3.152 m**(모든 인덱스에서 동일)이고 lane1/lane2 는 인덱스 정렬된
  평행 곡선이다. 1.58 m 로 알고 있던 건 틀렸다.
- 수집기의 `fwd` 는 **중심 대 중심 호 거리**다(`_ob_arc_gap`). 대화 중 "트리거 후
  1.9 s 죽은 시간", "10 m ≈ 중심 14.8 m" 라고 한 건 틀렸다. 실제 반응 지연은 약 0.2~0.3 s.
- 스와브 수집은 기본 제어기 **pure pursuit** 였다. r26 의 순항 선생은 Stanley 라
  v33s(Stanley 109 + swerve 72)는 두 선생 스타일이 섞여 있었다.
- 결정 프레임(20 m 이내, 아직 안 꺾은 프레임)은 v1 전체에서 **203 개**(에피소드당
  8.5), 이미 꺾고 있는 프레임은 2579 개. 후자는 state `[speed, yaw_rate, steer]` 만으로
  맞출 수 있어 부스트가 지름길을 증폭한다 — 학습기 쪽 과제로 남김(미해결 2).

## 바꾼 것

| 파일 | 변경 |
|---|---|
| `sant_vla_pkg/route_oracle_node.py` | goal 에 `lane_ramp_m`(cruise→cruise 차선 전환만). 기준점을 `lerp(이전 차선[k], 새 차선[k], s_k)`, `s` = 호 길이 기준 raised-cosine 0→1. Stanley 는 보간 경로의 접선(횡 이동 포함), pure pursuit 는 보간된 전방주시점을 쓴다. `/oracle_action` 에 `lane_ramp_s` 기록. 기본 0 = 기존 즉시 교체 |
| `scripts/collect_corpus.py` | `--ob-swerve-trigger-m`, `--ob-swerve-ramp-m`(회피와 복귀 둘 다), `--ob-ego-lane`, `--ob-variants`. 기본값은 기존 동작 그대로(8 m, 램프 0, 양 차선, 3 변형) |
| `tools/collect_multiobj_avoid.sh` | `SWERVE_TRIGGER`, `SWERVE_RAMP`, `EGO_LANE`, `OB_VARIANTS`, `CONTROLLER`. Stanley+스와브인데 램프가 없으면 거부 |
| `tools/eval/lane_ramp_sim.py` | 신규 — 오프라인 하니스(아래) |
| `tools/eval/swerve_demo_quality.py` | 신규 — 실제 packed v1 의 조향 스텝·피크·평가기 기하 여유 |

램프가 생기면서 Stanley 로도 차선변경이 된다(즉시 교체에선 3.15 m 오차를 한 번에
봐서 불가). 회피 시연 선생을 r26 순항 선생과 같은 제어기로 맞출 수 있다.

## 오프라인 하니스: 무엇이고 어떻게 비교했나

`tools/eval/lane_ramp_sim.py`. gz 없이 파이썬만으로 추종기를 돌린다.

- **추종기는 실제 코드.** `RouteOracle` 을 import 해 `_goal_cb`/`_control`/`_ref`/
  `_ramp_s` 를 그대로 실행하고, ROS 퍼블리셔·로거만 더미로 바꿨다.
- **차는 수식.** 발행된 `cmd_vel`(v, ω)을 20 Hz 로 적분하는 키네마틱 유니사이클
  (`x += v cos h dt, y += v sin h dt, h += ω dt`). 타이어·관성·지연 없음.
- **트리거는 수집기 흉내.** 장애물(lane2 인덱스 142)까지 중심 호 거리가 트리거 이하가
  되면 차선변경 goal 을 넣는다(램프면 `lane_ramp_m` 포함). 출발은 25 m 상류.
- 비교: 기존(pure pursuit lg0.6, 8 m, 즉시) / 제안(Stanley, 10 m, 램프 9 m) /
  제어기만 기존(pure pursuit, 10 m, 램프 9 m) × 1.0 / 2.16 / 2.9 m/s.

| v (m/s) | 방식 | 조향 피크 | 0.1 s 당 최대 조향 변화 | 클램프 틱 |
|---|---|---|---|---|
| 1.0 | 기존 | 0.60 | 0.52 | 28 |
| 1.0 | Stanley 램프 | 0.60 | 0.29 | 4 |
| 1.0 | PP 램프 | 0.51 | 0.32 | 0 |
| 2.16 | 기존 | 0.60 | 0.51 | 6 |
| 2.16 | Stanley 램프 | 0.57 | **0.17** | 0 |
| 2.16 | PP 램프 | 0.50 | 0.31 | 0 |
| 2.9 | 기존 | 0.60 | 0.51 | 3 |
| 2.9 | Stanley 램프 | 0.55 | **0.13** | 0 |
| 2.9 | PP 램프 | 0.49 | 0.31 | 0 |

`--grid` 로 트리거 10/11/12 m × 램프 8/9/10 m 도 돌렸다(여유 수치는 아래 한계 때문에
결정에 쓰지 않음).

## 하니스 검증과 한계

**맞은 것 — 스텝이 생기는 원리.** 기존 방식에서 조향 0.60 포화와 0.1 s 당 0.51 rad
점프를 재현했다. 실제 데이터의 한 프레임 점프(+0.105 → +0.600)와 같은 현상이다.
매끄러움 개선 폭도 실제 시범 수집(0.77 → 0.21, 아래)과 방향·규모가 비슷했다.

**틀린 것 — 절대 충돌 여유.** 하니스 격자는 기존 시연이 차량과 차체가 약 1 m
겹친다고 했다(차량 여유 −0.78 ~ −1.10 m, 박스도 2.16 m/s 이상에서 음수). 실제
`packed_swerve` v1 24개를 평가기 기하로 재면 **0/24 겹침, 여유 +0.51 ~ +1.27 m**.
원인 둘:

1. 실제 gz 차는 같은 조향에서 하니스보다 약 1.5배 빨리 옆으로 움직였다(2.16 m/s 기존
   방식, 트리거 후 3.2 m 주행 시점 횡이동: 실제 1.32 m, 하니스 0.86 m). 하니스에 차량
   동역학이 없어서 생긴 차이로 추정하며, **정확한 원인은 확인하지 않았다**.
2. 하니스의 여유는 차선 좌표계 기준이다. 평가기(`avoidance_trial.hit_geometric`)는
   차체 방향 기준이라, 차가 비스듬히 틀어져 있으면 옆 거리가 더 크게 잡힌다.

**그래서:** 하니스는 상대 비교(어느 방식이 더 매끄러운지, 포화하는지)에만 쓴다.
트리거·램프 값의 충돌 여유는 실제 gz 수집 데이터에서 `swerve_demo_quality.py` 로 잰다.
하니스 여유를 근거로 트리거를 11 m 로 올리자고 할 뻔했으나 실제 데이터에서 10 m 로
충분했다.

## gz 시범 수집 (packed_ramppilot)

v1 만 6그룹, hatchback_red / ob_box 교대, 속도 3단계 순환, Stanley, 트리거 10 m,
램프 9 m, 2차선 출발 → 1차선. 6/6 success, 패킹 5개(ep_0003 은 finalize 에서
"pose interpolation error 20.1 cm, 선회 중 tf 갭 0.411 s" 로 거부 — 램프와 무관한
기존 검사). 3.7 분.

| | packed_swerve (24) | packed_ramppilot (5) |
|---|---|---|
| 0.1 s 당 최대 조향 변화(평균) | 0.77 rad | **0.21 rad** |
| 조향 피크(평균) | 0.60 (전부 포화) | 0.56 (0.51~0.59) |
| 최소 충돌 여유(평가기 기하) | +0.51 m | **+0.80 m** (차량 1.37 m/s) |
| 겹침 | 0/24 | 0/5 |

가장 불리한 조합(차량, 2.94 m/s)의 궤적:

```
fwd 9.1  lat +0.23  steer +0.40   ← 트리거 약 0.3 s 뒤 반응
fwd 7.0  lat +0.94  steer +0.35
fwd 4.9  lat +2.02  steer +0.05
fwd 2.8  lat +2.91  steer -0.24
fwd 1.4  lat +3.12  steer -0.35   ← 장애물 바로 앞에서 차선변경 완료
```

측정 주의: 첫 분석에서 두 에피소드가 0.60/0.78 스텝으로 나왔는데, 출발 직후 정지
상태(v≈0)에서 Stanley 가 조향을 0.6 으로 포화시킨 것이 분석 창(장애물 14 m 이내)에
걸린 것이었다. 출발 지점이 장애물 11~13 m 앞인 에피소드에서 생긴다.
`swerve_demo_quality.py` 는 처음 3 s 를 건너뛴다(두 코퍼스 모두 같은 기준).

## 재현

```bash
# 하니스 (몇 초)
python3 tools/eval/lane_ramp_sim.py
python3 tools/eval/lane_ramp_sim.py --grid
# 시범 수집 (gz, 약 5 분) — sim-stack-bringup 절차 먼저
TAG=ramppilot SWERVE=1 FIXED_INDEX=142 EGO_LANE=lane2 V1_ONLY=1 \
  SWERVE_TRIGGER=10 SWERVE_RAMP=9 CONTROLLER=stanley \
  TRAIN_MODELS=hatchback_red,ob_box HELDOUT_MODELS=ob_person \
  TRAIN_GROUPS=6 HELDOUT_GROUPS=0 SEED_TRAIN=20260929 \
  bash tools/collect_multiobj_avoid.sh
# 시연 품질 비교
python3 tools/eval/swerve_demo_quality.py \
  src/sant_vla_pkg/data_course_multiobj/packed_swerve \
  src/sant_vla_pkg/data_course_multiobj/packed_ramppilot
```

## 미해결

1. **본 수집**: v0+v1, 학습 물체 7종(hatchback_red/blue/yellow, prius_hybrid, ob_box,
   ob_cone, ob_barrier), ob_barrel·ob_person 은 홀드아웃. 72그룹 ≈ 1.5 h, v1 60+ 예상.
2. **학습기**: 부스트를 onset 전후 창으로 한정, state `yaw_rate/steer` 드롭아웃 —
   결정 프레임 203 개 / 지름길 2579 개 문제.
3. **폐루프 커밋**: `refill_at` 0.3(주차 베이용 튜닝) → 0.6 시험.
4. Stanley 정지 상태 조향 포화 — 회피 구간 밖이고 기존 Stanley 순항 코퍼스에도 있어
   이번엔 손대지 않음.
5. 하니스와 실제 gz 의 횡방향 속도 차이(약 1.5배) 원인 미확인.
6. 코퍼스 전체의 10 Hz 위치 지터(변위 환산 속도 sd 0.8~1.4 m/s, v0 에도 있음) — 별도 조사.
