# ROS 그래프 비교 — YOLO 스택 vs VLA 스택 (2026-08-07)

같은 시뮬레이터(가제보 트랙)에서 두 주행 스택을 각각 켜고 rqt_graph로 저장한
노드/토픽 그래프. 원본: `yolo/`, `vla/` 폴더의 PNG.

## 한눈 비교

| | YOLO 스택 | VLA 스택 |
|---|---|---|
| 판단 경로의 노드 수 | **7개 릴레이** (yolov8 → lane_info_extractor → path_planner → motion_planner → simulation_sender) | **1개** (vla_bridge) + ROS 밖 정책 서버 |
| 중간 표현 | 사람이 설계한 4단계 (detections → lane_info → path → control_signal) | 없음 (픽셀 → 행동 직결) |
| 언어 인터페이스 | 없음 | /vla/instruction · /vla/plan · /vla/status · /vla/narration |
| 카메라 소비자 | yolov8_node | vla_bridge (JPEG로 압축해 ZMQ로 전달) |
| 공통 하부 (액추에이션) | /cmd_vel → gz_bridge_control · ackermann_cmd_adapter → /front_steer_cmd, /odom | 동일 |

## YOLO 스택 — 손으로 설계한 릴레이

```
/camera/image_raw → yolov8_node → /detections → lane_info_extractor → /yolov8_lane_info
  → path_planner → /path_planning_result → motion_planner → /topic_control_signal
  → simulation_sender → /cmd_vel → (공통 하부)
```

- 각 화살표가 **사람이 정의한 인터페이스**다: "차선은 이런 구조체다", "경로는
  이런 포맷이다"를 전부 개발자가 미리 결정했다.
- 다섯 노드 중 하나라도 죽거나 인식이 틀리면 뒤 전체가 연쇄로 무너진다
  (yolov8이 차선을 놓치면 path_planner는 입력이 없다).
- 언어 입력이 들어갈 자리가 없다 — 차선 변경 같은 지시는 별도 상태 토픽
  (lane_mode_state)과 코드 수정으로만 가능.

## VLA 스택 — 픽셀에서 행동으로 직결

```
/camera/image_raw → vla_bridge ↔ (ZMQ, 그래프에 안 보임) SmolVLA 정책 서버
                       ↓
                    /cmd_vel → (공통 하부)
/vla/instruction → vla_bridge          ← chat_gui (자연어 → 정규 문장)
vla_bridge → /vla/plan, /vla/status    → narrator (한국어 해설), 관측용
navigator: /nav_goal, /nav_status      (지점 도착 정차 감독 — 주행 비개입)
```

- 판단은 전부 **그래프 밖의 정책 서버**에서 일어난다. rqt_graph에 두뇌가 안
  보이는 것 자체가 이 구조의 특징이다 — ROS(시스템 파이썬)와 lerobot(torch)
  의존성 충돌 때문에 ZMQ로 분리했고, ROS 세계에는 vla_bridge 하나만 보인다.
- 중간 표현이 없으므로 "차선 구조체"도 "경로 포맷"도 없다. 대신 언어 토픽
  4종이 새 인터페이스다: 명령(instruction), 계획 미러(plan), 상태(status),
  해설(narration).
- 보조 노드는 판단에 개입하지 않는다: navigator는 좌표 도착 정차만,
  narrator는 관측·해설만 한다.

## 공통 하부가 같다는 것의 의미

두 그래프 모두 끝단은 `/cmd_vel → gz_bridge_control · ackermann_cmd_adapter →
/front_steer_cmd`, 상태는 `/odom`으로 동일하다. **차량 입장에서 두 스택은
완전히 교체 가능**하고, 이 덕분에:
- 데이터 수집 때 YOLO 스택(선생)이 몰던 차를 그대로 VLA(학생)에게 넘겨
  같은 인터페이스로 평가할 수 있었다
- 실차 전이 때도 이 경계(/cmd_vel 아래)만 실차 드라이버로 바꾸면 된다

## 관찰 메모

- VLA 그래프에 yolov8_visualizer_node·path_visualizer_node가 떠 있지만
  들어오는 발행자가 없다(비활성 잔재) — VLA 주행 중 YOLO 계열은 실제로
  아무 데이터도 흘리지 않는다는 방증. 원인은 launch의
  `use_debug_visualizers` 기본값 true. **2026-08-21부터 데모·프로브
  스크립트가 `use_debug_visualizers:=false`를 명시**하므로 이후 그래프에는
  이 두 노드가 아예 나타나지 않는다. 인지판단제어 본체(yolov8, 차선 추출,
  경로/모션 계획, 송신)는 원래부터 `use_perception_pipeline:=false` 조건으로
  프로세스 자체가 뜨지 않았다.
- VLA 그래프의 /camera와 /vla_camera 두 카메라 중 브리지는 반드시
  `/camera/image_raw`를 봐야 한다(학습 시점과 동일 시야 — 다른 광각을 보면
  주행이 무너지는 사고가 실제로 있었다).
