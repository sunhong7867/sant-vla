# 바퀴 카운터 + 속도-트렌드 서술 실측화 (2026-09-15)

데모(r21) 주행 관찰에서 나온 두 건. 둘 다 **코드 감독관** 계층 수정이며
VLA 모델·학습(r23)과 완전히 독립이다. 대시보드 재시작 한 번으로 반영된다.

## 1. 속도-트렌드 서술을 실측 명령속도로 덮어쓰기

### 증상
`Start driving in the left lane, at a normal speed`(보통 속도) 명령인데
서술이 급곡선·직선·곡선 가릴 것 없이 거의 매 프레임 "속도를 올립니다"로
떴다. 실측 `cmd_vel ≈ 1.89~2.04 m/s`로 평평하게 유지(가속 아님).

### 원인
"속도를 올립니다"는 **모델 언어헤드가 생성한 트렌드 단어("speeding up")를
그대로 번역**한 것(`dashboard_language._R_TAIL`). 트렌드는 heldout 정확도가
가장 낮은 항목(~28%)이라 다수 클래스로 기본 쏠림. 대시보드는 충실히 옮겼을
뿐, 접지 실패는 모델 쪽.

### 수정 (코드 전용, 재학습 불요)
속도 트렌드는 **코드 감독관이 정확히 아는 값**(명령 속도의 기울기)이므로
하이브리드 설계대로 코드가 실측으로 덮어쓴다. 차선/존/곡선 서술(모델의
접지된 인식)은 그대로 둔다.

- `driving_dashboard.attach_telemetry`: `/cmd_vel` 구독, 2 s 롤링 창에서
  최근 0.6 s 평균 − 과거(≥1.4 s) 평균 = `dv`. `dv>0.15→up`, `<−0.15→down`,
  그 외 `hold`를 `telemetry["speed_trend"]`에 기록.
- `DashboardWindow.refresh`: 매 틱 `display_language.speed_trend`에 주입
  (2 s 이내 신선한 값만; 없으면 None→모델 원문 유지).
- `dashboard_language.reasoning_ko(text, speed_trend)`: "머리 — 꼬리"에서
  **순수 트렌드 꼬리 3종**(올림/줄임/유지)만 실측값으로 교체. 인과적 꼬리
  ("곡선 구간이라 속도를 줄입니다", "목적지 정차를 위해…")는 의미가 있어
  보존.

### 결과 (오프라인 검증)
| 모델 출력 | 실측 | 화면 |
|---|---|---|
| speeding up | hold | …곡선 주행 중 — **속도를 유지합니다** |
| speeding up | down | — **속도를 줄입니다** |
| speeding up | up | — **속도를 올립니다** |
| slowing for the curve | (인과) | — **곡선 구간이라 속도를 줄입니다** (보존) |

## 2. 바퀴 카운터 + "N바퀴 주행 후 정차"

### 요구
① 지금 몇 바퀴째 주행 중인지 표시, ② "2바퀴 주행해" → 2바퀴 돌고 정차.

### 설계 — 신호등·"도착 정지" 감독관과 동형
필요한 부품이 전부 기존에 존재:
- 위치: `WorldPoseStream`(gz 지상진실) — `_ego_pose_stream` 공유.
- 바퀴 판정: 차선이 닫힌 루프 + **누적 호길이**(`_lane_cumlen`, 이미 계산).
- 정지 발행: 빈 지시 `""` + `nav_goal "stop"` — 좌표 감독 도착 정지와 동일.

`chat_gui_node`:
- `parse_lap_count` / `LAP_RE`: "2바퀴", "두 바퀴", "drive 3 laps" 파싱
  (숫자 + 한글 수사 한~열). 명령에서 lap 토큰 제거 후 나머지("1차선",
  "빠르게")는 정상 파싱, 맨 "N바퀴"는 기본 크루즈로.
- `_lap_worker`(5 Hz 데몬 스레드, 회피/장면 cadence와 독립) → `_lap_tick`:
  ego 포즈를 **출발 시 고정한 차선**에 투영해 호길이 `s`. 전진량만 누적
  (`ds>0`), 루프 이음새(`s`가 loop→0으로 점프)는 언랩. `progress // loop`가
  완료 바퀴. Start 위치가 아니라 **출발 지점 기준 루프 한 바퀴 = 360°**
  (사용자 결정).
- 재-무장 규칙: 새 크루즈가 정지→주행으로 시작하거나 lap 숫자가 주어질 때만
  카운트 리셋. 주행 중 차선/속도 변경은 진행 중 카운트·목표를 보존.
- 완주 시: `_vla_mode=idle`, 빈 지시 + nav stop, "🏁 목표 N바퀴 완주 —
  정차합니다." 각 바퀴 완료마다 "🏁 N바퀴 완료." 이벤트.
- `/vla/lap`(latched JSON `{lap,target,pct}`) 발행.

`driving_dashboard`:
- `/vla/lap` 구독(transient_local) → `telemetry["lap"]`.
- BEV 상태줄에 `🏁 N바퀴째 xx% / 목표 M바퀴` 접두 표시.

### 정지 지점
출발 지점 기준 정확히 N 루프 전진 시점 → 출발했던 위치 부근에서 정차.

## 변경 파일
- `src/sant_vla_pkg/sant_vla_pkg/dashboard_language.py`
- `src/sant_vla_pkg/sant_vla_pkg/driving_dashboard.py`
- `src/sant_vla_pkg/sant_vla_pkg/chat_gui_node.py`

## 남은 확인 (실차 검증 필요)
- 실제 데모에서 트렌드가 곡선 감속 때 "줄입니다", 출발 램프 때 "올립니다",
  순항 때 "유지합니다"로 뜨는지.
- 바퀴 seam 언랩이 실주행 궤적에서 오검출 없이 정확히 +1 하는지(투영
  지터). 필요 시 `ds>0` 문턱을 소량 상향.
- lane1/lane2 loop 길이 차이는 무시(출발 차선 하나로 파라미터화).
