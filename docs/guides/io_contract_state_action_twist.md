# 입출력 표현 3종 — state / action chunk / Twist가 서로 다른 이유

작성 2026-09-12. 짝 문서: 스택 전체 책임 분담은
[code_vs_vla_responsibilities.md](code_vs_vla_responsibilities.md),
직행 위임 결정은 [ver/20260824_1138](ver/20260824_1138_direct-nav-architecture-decision.md).

이 문서가 답하는 질문: **"학습 입력(속도·yaw rate·조향·정지시간), 정책 출력
(3초 경로 dx/dy/dyaw), 구동 명령(선속도·각속도)이 왜 다 다른가? 하나로
통일하면 안 되나?"**

결론부터: 세 개는 같은 것의 세 표현이 아니라 **층이 다른 세 계약**이다.
그리고 물리량으로 보면 실제로는 이미 하나다 — 같은 (v, ω)를 **과거 누적 /
현재 순간 / 미래 3초 적분**의 세 시간 스케일로 보고 있을 뿐이다.
통일이 안 되는 진짜 이유는 단 하나, **곡률과 속도를 분리해 둬야 서빙
단계의 안전 셰이핑이 궤적을 망가뜨리지 않는다**는 것이다.

---

## 1. 세 계약의 정의 (코드 기준)

| | 형태 | 정의 위치 | 층 |
|---|---|---|---|
| **observation.state** | `float32[3..6]` — speed m/s, yaw rate rad/s, steer rad (+ bearing·dist, +standstill_s) | [to_lerobot.py:19](../src/sant_vla_pkg/scripts/to_lerobot.py#L19), [:248-253](../src/sant_vla_pkg/scripts/to_lerobot.py#L248-L253) | 관측 (고유수용감각) |
| **action** | `float32[3]` × 30 — ego-frame SE(2) 델타 `[dx_m, dy_m, dyaw_rad]` | [to_lerobot.py:20](../src/sant_vla_pkg/scripts/to_lerobot.py#L20), [:254-255](../src/sant_vla_pkg/scripts/to_lerobot.py#L254-L255) | 계획 (궤적) |
| **`/cmd_vel`** | `geometry_msgs/Twist` — `linear.x`, `angular.z` | [vla_bridge_node.py:804-806](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L804-L806) | 구동 (액추에이터) |

`chunk_len=30`, `rate_hz=10` → 한 청크가 정확히 **3.0초**를 덮는다
([vla_bridge_node.py:214-215](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L214-L215)).
ZMQ 와이어 계약은 `-> {jpeg, state, task, seed, req}` / `<- {actions: [[dx,dy,dyaw], ...]}`
([:11-12](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L11-L12)).

---

## 2. 사실 확인: state와 action은 이미 같은 양이다

리샘플러가 둘을 **같은 SE(2) 델타 하나에서** 만든다
([resample_episodes.py:334-350](../src/sant_vla_pkg/scripts/resample_episodes.py#L334-L350)):

```python
dx  =  dxw*cos(h) + dyw*sin(h)
dy  = -dxw*sin(h) + dyw*cos(h)
dyaw = wrap_pi(b.heading - a.heading)
a["action"] = [dx, dy, dyaw]
a["state"]  = [hypot(dx, dy) * fps,   # speed   = |Δp| / dt
               dyaw * fps,            # yaw rate= Δyaw / dt
               oracle_steer_rad]
```

즉 **state = action / dt**. 학습 데이터에서 state[k]는 "직전 스텝의
action을 시간으로 나눈 것"이고, 서빙에서도 대칭이다:

| 방향 | 변환 | 위치 |
|---|---|---|
| odom → state | `steer = atan2(ω·L, v)` (자전거 모델 역산, L=2.86 m) | [vla_bridge_node.py:472-476](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L472-L476) |
| action → Twist | `v = dx/dt`, `ω = dyaw/dt` | [vla_bridge_node.py:633-634](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L633-L634) |

state의 3채널 중 조향은 **실제 센서가 아니라 v, ω에서 유도한 프록시**다.
그래서 "세 표현"이 아니라 "하나의 (v, ω)에 대한 세 시점"이라고 읽는 쪽이
정확하다:

```
   과거 누적            현재 순간              미래 3초 적분
   standstill_s   →   state[v, ω, δ]   →   action[30×(dx,dy,dyaw)]
        └─ 이미지에 안 보임          브릿지가 다시 미분 ─┘ → Twist(v, ω)
```

---

## 3. 왜 출력을 (v, 조향)으로 통일하면 안 되는가 — 핵심 근거

**출력이 ego-frame 델타여야 곡률 k = dyaw/dx 가 속도와 분리된다.**
[vla_bridge_node.py:636-639](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L636-L639)
주석이 이 원칙을 명시한다:

> The action's path geometry lives in its curvature k = ω/v. Any speed shaping
> must preserve k (same line, different pace), so ω is recomputed from k after
> v is final — scaling v alone would flatten every turn by the same factor.

이 분리 덕분에 브릿지는 **궤적의 "선"을 건드리지 않고 "페이스"만** 바꿀 수
있다. 실제로 제어 경로에서 v에 손대는 셰이핑이 다섯 종류나 걸려 있다:

| 셰이핑 | 하는 일 | 위치 |
|---|---|---|
| `speed_scale` | 전역 속도 배율 | [:640](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L640) |
| `max_speed` 클램프 | 물리 상한 (기본 2.0, 데모 2.25) | [:644](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L644) |
| `speed_slew` | 틱당 가감속 제한 | [:645-650](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L645-L650) |
| `curv_slow_alat` | 횡가속 한계 기반 코너 감속 `v ≤ √(a_lat/|k|)` | [:676-684](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L676-L684) |
| `_speed_cap_ahead` | 예측 경로 전방을 미리 보고 **코너 진입 전** 제동 | [:690-698](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L690-L698) |

그리고 이 전부가 끝난 뒤 마지막 줄이 `w = k * v`
([:685](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L685)) — 속도를 아무리
깎아도 **같은 선**을 그린다.

만약 정책이 (속도, 조향각)을 직접 뱉었다면 위 다섯 개 중 어느 하나만
작동해도 그 코너가 통째로 펴진다. 속도와 경로가 한 변수에 얽혀 있기 때문이다.

### 실측된 음성 결과 — 이 원칙을 어겼을 때

[vla_bridge_node.py:625-632](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L625-L632)
에 기록된 사고:

- `v = hypot(dx, dy)/dt`로 **횡방향 성분까지 속도에 접어 넣었더니** 턴 구간
  commanded speed가 **약 8% 과대**.
- k = ω/v 이므로 곡률이 같은 비율로 **축소** → 전 구간 under-turn.
- 결과: **오라클 자신의 액션을 리플레이했는데 주차 베이를 횡방향 4 m 빗나감.**
- 원인을 한동안 정책 탓으로 오진했음.

교훈: action의 `dy`는 모델 기준점(후축에서 전방 1.554 m)의 **횡슬립**이고,
차량 기하가 알아서 재현한다. 속도에는 `dx`만 쓴다.

---

## 4. 왜 입력을 델타로 통일하면 안 되는가

### 4-1. 이미지에 안 보이는 것을 넣는 자리가 state다

`standstill_s`(정지 경과 초, cap 5)는 **누적 히스토리**다
([to_lerobot.py:139-142](../src/sant_vla_pkg/scripts/to_lerobot.py#L139-L142),
[vla_bridge_node.py:462-470](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L462-L470)):

> the v9 watch-then-avoid GO trigger, **unobservable from image+[v, w, steer]**

단일 프레임 + 현재 속도만으로는 "목표 앞에 서서 끝난 상태"와 "서 있다가 곧
출발할 상태"가 구분되지 않는다. 실제로 r6 라이브 데모가 멈춘 뒤 재출발하지
못한 원인이 이것이었고, 그래서 채널이 추가됐다.

같은 이유로 골 조건부 체크포인트(v8g+)는 `[bearing_to_goal_rad, dist_to_goal_m]`
2채널을 state에 붙인다([to_lerobot.py:125-129](../src/sant_vla_pkg/scripts/to_lerobot.py#L125-L129),
[vla_bridge_node.py:196-197](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L196-L197)).
**전부 입력 전용이고 출력에는 대응물이 없다.** 델타로 통일하면 이들을 넣을
자리 자체가 사라진다.

### 4-2. state 차원은 체크포인트마다 다르다 (호환 부채)

| 체크포인트 | state dim | 구성 |
|---|---|---|
| v6 | 3 | v, ω, **steer 상수 0** (`force_zero_steer_state`) |
| v8g+ | 5 | v, ω, steer, bearing, dist |
| r8+ | 4 | v, ω, steer, standstill_s |

브릿지가 파라미터로 이 조합을 맞춘다
([:183-197](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L183-L197),
[:869-877](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L869-L877)).
입력은 **버전마다 늘어나는 슬롯**이고 출력은 **항상 3차원 고정**이다 —
이 비대칭 자체가 두 계약이 분리돼야 하는 실무적 증거다.

---

## 5. 왜 출력을 순간 명령으로 통일하면 안 되는가 — 청크 스플라이싱

새 청크는 큐의 겹치는 꼬리와 **선형 램프로 블렌딩**된다
([vla_bridge_node.py:143-157](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L143-L157),
`splice_overlap=5`):

```python
w = (i + 1) / (n + 1)      # 0 -> 1 across the overlap
```

이게 없으면 `chunk_len` 틱마다 조향이 튀고, 그 트위치가 **`D_same`
(재현성 노이즈 플로어)를 부풀린다** — 모든 divergence 수치의 분모다
([:34-38](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L34-L38)).

상대 변위 시퀀스는 두 예측을 섞어도 기하학적으로 의미가 있다(두 경로의
가중 평균 = 중간 경로). **순간 (v, ω) 명령열은 그렇게 섞으면 물리적 의미가
없다.** 3초 지평을 한 번에 내놓고 부드럽게 이어붙이는 구조 자체가 델타
표현을 요구한다.

덤: 델타 시퀀스이기 때문에 브릿지가 경로를 **적분해서 앞을 내다볼 수** 있다
— pure pursuit / preview 곡률([:725-800](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L725-L800)),
전방 감속(`_speed_cap_ahead`). 순간 명령열로는 불가능한 연산이다.

---

## 6. Twist는 선택지가 아니다

`/cmd_vel`의 Twist는 설계 결정이 아니라 **하류 인터페이스의 요구**다.
`ackermann_cmd_adapter_node`가 Twist를 조향각/구동으로 바꾼다
([code_vs_vla_responsibilities.md §1](code_vs_vla_responsibilities.md)).
브릿지는 이 변환의 유일한 소유자이고, 평가 중 `/cmd_vel`을 만지는 건
브릿지뿐이다([:1](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L1)).

주의: 시뮬 twist 인터페이스에서 `angular.z`는 **조향각이 아니라 yaw rate**다.
"조향 유지"를 ω 유지로 구현했다가 v=0 상태에서 차가 계속 회전해 리셋 구간에
**0.15 m 크리프**가 측정됐고, 그래서 워치독은 v·ω **둘 다 0**을 낸다
([:615-620](../src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py#L615-L620)).

---

## 7. 통일안별 손익 정리

| 통일안 | 잃는 것 |
|---|---|
| 출력을 (v, steer) 순간값으로 | §3 전부 — 속도 셰이핑 5종이 궤적을 왜곡. 실측 under-turn 4 m |
| 출력을 (v, ω) 순간 명령열로 | 청크 스플라이싱 불가 → 경계 트위치, `D_same` 악화. 전방 예측 감속 불가 |
| 입력을 델타로 | standstill_s·bearing·dist 채널 자리 소멸 → 정지 후 재출발/골 조건화 불가 |
| 입력을 Twist 그대로 | 사실상 현재와 동일(이미 odom v, ω 기반). steer 프록시만 빠짐 |
| Twist를 경로 메시지로 | ackermann 어댑터 재작성 필요. 얻는 것 없음 |

---

## 8. 미해결 / 주의

- **steer 채널의 가치가 불분명하다.** v6은 상수 0으로 학습됐는데도 차선
  무접촉 주행에 성공했다. v, ω에서 유도한 프록시라 독립 정보가 거의 없다 —
  제거 실험을 한 적은 없다.
- **dt 하드코딩.** `action → Twist`가 `dt = 1/rate_hz`를 쓰므로 코퍼스 fps와
  서빙 `rate_hz`가 어긋나면 속도가 통째로 스케일된다. 둘 다 10 Hz라는 전제가
  코드 어디에도 강제돼 있지 않다. 어서션을 넣을 가치가 있다.
- **state dim 협상이 수동이다.** `force_zero_steer_state` / `standstill_state`
  / 골 채널을 파라미터로 맞춰야 한다. 체크포인트 메타데이터에서 자동 판정하는
  경로가 [vla_policy_server.py:211-214](../src/sant_vla_pkg/scripts/vla_policy_server.py#L211-L214)
  에 일부 있으나 브릿지 쪽은 아직 수동이다.

## 재현 — 계약 확인 명령어

```bash
# 학습 데이터의 두 계약 정의
sed -n '17,25p'    src/sant_vla_pkg/scripts/to_lerobot.py
sed -n '334,352p'  src/sant_vla_pkg/scripts/resample_episodes.py   # state = action/dt

# 서빙의 변환과 곡률 보존
sed -n '620,690p'  src/sant_vla_pkg/sant_vla_pkg/vla_bridge_node.py

# 실행 중 실제 계약 값
ros2 topic echo /vla/status --once      # rate_hz, chunk_len, splice_overlap, track_mode
```
