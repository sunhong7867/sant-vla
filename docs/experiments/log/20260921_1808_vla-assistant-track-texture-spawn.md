# VLA 어시스턴트 답변 · 새 트랙 텍스처 · 출발/주차 위치 · 차선변경 감속 (2026-09-21)

데모 대시보드 세션에서 나온 요청을 하루에 처리한 기록. 커밋 전.

## 1. "주행 도우미" → "VLA 어시스턴트", 답변을 LLM이 문구화

배경: GUI 답변이 f-string 템플릿(`Understood: change_lane[lane2]. → VLA: "..."`)이라
고정 문구로 보였고, 명령이 아닌 말("지금 몇 바퀴?")은 파싱 실패 에러였음.

구조 — **결정은 코드/SmolVLA, 말은 qwen**:

| 역할 | 담당 | 비고 |
|---|---|---|
| 주행 | SmolVLA (`vla_policy_server`) | 유일하게 차를 움직임 |
| 명령 해석 | qwen2.5vl:7b `parse_command` (JSON 스키마) | 기존 |
| 답변 문구화 (신규) | 같은 모델 `assistant_reply` | 명령당 1회 호출, 0.2~1.3 s |
| 장면 해설 | 같은 모델 `scene_llm_line` | 기존, 데모만 |

- `chat_gui_node.py`: `assistant_facts()`(차선·속도 단계·모드·존·바퀴 수·navigator),
  `command_facts(steps, response)`("지금 하는 일: 바깥쪽 2차선을 따라 M2까지 주행,
  도착하면 정차"), `assistant_reply(user_text, event)`, `announce(template, event)`
  (ROS 스레드에서 이벤트 알림 — 도착/감속/예약 단계/바퀴 완료/초록불 — 별도 스레드로
  문구화). 최근 8턴 대화 기록 동봉.
- `driving_dashboard.py`: `phrase_reply()` 워커 + `ResultBus.replied` 시그널.
  `action: none`이면 차량 안 건드리고 상태 근거로 답변. 라벨 `VLA ASSISTANT`.
  `command_summary`의 차선은 smolvla 모드에서 `_vla_lane`(명령 차선) 기준 —
  `/lane_state` 추정이 `current_lane`을 덮어써 "안쪽 1차선" 오표시가 있었음.
- `dashboard_language.py`: `('VLA 어시스턴트', 'VLA ASSISTANT')`.
- 영어 모드는 `node.scene_lang == "en"`이면 **처음부터 영어로 생성**
  (한국어 생성 → 번역기 2단계에서 `Translation unavailable` 줄이 말풍선에 떴음).

측정으로 잡은 함정 (프롬프트/가드에 반영):
- 요약 *문장*을 주면 그대로 베낌 → 사실 목록만 넘김.
- 프롬프트 예문("빠르게 달릴게요")을 복사 → 예문 제거.
- "~해주세요"(운전자에게 지시) → 1인칭 "~할게요/~하겠습니다" 강제.
- 바퀴 수 0을 사실에서 빼면 "three laps" 지어냄 → 항상 넘기고 "물을 때만 언급".
- 로컬 qwen3:4b가 거부("IN은 미학습 존, 전송 안 함")를 "IN으로 가고 있어요"로 뒤집음
  → `ASSISTANT_KEEP_TEMPLATE_RE`에 걸리는 거부/실패는 LLM 안 거치고 템플릿 그대로.
- LLM 실패/타임아웃(6 s)이면 템플릿 폴백. 이모지·한자·언어 불일치 출력은 폴백.

## 2. 파서 수정 (실제 실패 원인)

로그 재현으로 확인:

| 입력 | 전 | 후 |
|---|---|---|
| 최단거리로 가줘 | drive_direct zone=None → 거부 | 직전 목표 `_vla_zone`으로 직행 |
| 1차선 따라 주행하자 | drive_to_zone zone=None → 거부 | change_lane[lane1] (정규식 지름길) |
| 출발지점 2차선으로… 최단거리로 | 2차선 따라 Start | Start 직행 — "최단" 명시 시 차선어보다 우선 |

- `_apply_zoneless_drive`(`_normalize_plan` 첫 단계), `_deterministic_drive_plan`의
  lane-only 분기, `_apply_explicit_lane_override`에 DIRECT 우선.
- 거부 문구 한국어화: "어느 구역으로 갈지 알려주세요 (예: Start, M2, …)". 거부일 땐
  `Understood:` 머리 제거.
- `s1` 별칭은 추가했다가 새 텍스처가 `Start`로 표기돼 **제거**.

## 3. 사고: 리플레이 스크립트가 라이브 데모를 조종함

답변 검증용 스크립트가 실제 `chat_gui_node`를 인스턴스화 → 같은 DDS 도메인에서
`/nav_goal`·`/direct_nav_goal`·`/vla_instruction` 퍼블리시 → 사용자의 `go start line`
이 `idle: cancelled`(navigator.log 44행) 후 IN으로 직행. "Start에서 안 멈춤"은 이것.
→ 메모리 `test-nodes-need-domain-isolation`: 테스트는 `ROS_DOMAIN_ID=77`.
Start 정차 자체는 미검증(재시도 필요).

## 4. 새 트랙 텍스처 (`race_track/materials/textures/track.png`)

- 원본 3594×5228 세로 → 반시계 90° 회전(T3 좌, Start 우, M2 우상, T4 하).
- 여백 비율이 달라 그대로 쓰면 도로가 세로로 4.4% 늘어남 → **도로 외곽 bbox를 기존
  텍스처 픽셀에 일치**시켜 합성(118–2227 × 73–1686). IoU 0.90. 2346×1759 유지.
- 원본 라벨이 기하와 반대로 회전돼 있어 회전 후 거꾸로 보임 → 글자 박스만 180°.
  IN/OUT은 글자만 돌리고 화살표 유지 (`IN →`이 진입선을 가리켜야 함).
- 이전 텍스처 `old_track_s1.png` 보관. gz 재시작 필요.
- 차이: 안쪽 도로 경계 ~0.2 m 안쪽, Start 선 ~0.2 m 이동, 점선 위상, "S1"→"Start".
  VLA 입력 분포가 약간 달라짐 — 차선 유지 이상 시 첫 의심.

## 5. 출발/주차 위치 (`race_scenarios.json`, `012_deploy_lib.driving_ego`)

텍스처→월드: 지면 평면 58.14×43.71 m, yaw 1.57 → 이미지 아래 = +x, 오른쪽 = +y.
프리우스 앞범퍼 = 로컬 **-y** (`front_bumper` pose y=-1.7), 원점에서 ~2.4 m.
yaw -1.57(Start)이면 진행 -x = 이미지 **위** (= "반시계 1바퀴"). 처음에 이걸 거꾸로
봐서 차를 선 앞으로 보냈다가 수정.

| 대상 | 전 | 후 |
|---|---|---|
| Start ego (예선·토너먼트·driving_ego) | x=3.70 | **4.9** (앞범퍼가 Start 선 x=2.27 0.2 m 앞) |
| 토너먼트 T3 상대차 | x=-1.39 | **-2.7** (T3 선 x=-0.06 0.24 m 앞, 횡단보도 진입 전) |
| 수직주차 obstacle4/5 | x=3.68/3.77 | **4.55**, y=-5.74/1.52, yaw 3π/2 |
| 평행주차 obstacle6/7 | x=-7.76/-7.83 | **-7.19**, y=-2.91/8.34, yaw π |

주차 칸 중심은 텍스처 선 실측. 수직 칸 y 중심(-9.37/-5.74/-2.11/1.52)이 Slot1~4
존과 일치해 매핑 검증됨. `driving_ego` 변경으로 오라클/코퍼스 출발점도 1.2 m 뒤.

## 6. 차선 변경 감속 (`vla_bridge_node.py`)

- 지시 차선이 이전과 다르면(inner↔outer) 감속 구간: 실행 속도 ×
  `lane_change_speed_factor`(**0.5**), 곡률 보존(w=k·v), `override="lane_change"`.
- 해제: gz 위치가 새 차선 중심선 `lane_change_done_m`(0.5 m) 이내(1 s 유예) 또는
  `lane_change_max_s`(8 s). 로그 `lane change to lane1: speed factor 0.5 released…`.
- 회피 감독의 차선 재발행도 같은 경로로 감속됨.
- `/vla/status`에 파라미터 노출. 1.0이면 off. 데모 스크립트 기본값 그대로.
- 스텁으로 상태 머신만 검증, 실주행 미확인.

## 미확인 / 다음
- 새 텍스처 + 새 출발 위치로 예선 1바퀴, `go start line` 정차, 차선 변경 감속 실주행.
- 한국어 말투는 qwen2.5vl:7b 한계("주행을 시작하겠습니다"). 랩서버에 한국어 강한
  모델 올리고 `parser_model`만 바꾸면 말투만 바뀜(안전 구조 동일).
