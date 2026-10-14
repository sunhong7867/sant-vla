# VLA-native 꼬깔 목표 이동 설계 (v1, 2026-09-19)

다중 지점 A→B가 안 되는 이유(트랙 시각 균일 → 카메라로 존 구분 불가)를
우회: **보이는 꼬깔(시각 랜드마크)로 servoing**. 사용자 분해 = "보이면
정렬 후 직진" = visual servoing(연속 조향, 학습 쉬움).

## feasibility (통과, 2026-09-19)
- 새 cone 모델(`src/simulation_pkg/models/cone/`, 주황 <cone> 1.0 m) 스폰 OK
  (gz create). ego 카메라에 **뚜렷이 보임**(주황 vs 회색). 12 m서 작음 →
  v1은 **크게(1.8 m)** + 근접 시작.
- r28(신호) 교훈 필수: **narration 라벨에 단서(꼬깔) 없으면 접지 실패** →
  label_reasoning에 꼬깔 fact 반드시 포함.

## v1 스코프 (사용자 확정)
어려운 부분(탐색·정차)은 분리, 연속 조향만.

| 요소 | 결정 |
|---|---|
| 동작 | 보이는 꼬깔로 **정렬+직진**(servoing), "최단거리" |
| 탐색(둘러보기) | **생략** — 꼬깔은 시작 시 항상 전방 FOV 안 (v3로) |
| 차선따라 변형 | v2로 (v1은 direct 하나) |
| 도착 정차 | **뺀다** — "꼬깔 근처(~2 m) 접근"까지만 (정차=희소-정지, 분리) |
| 지시문 | 상수 "go to the cone" (꼬깔 위치는 매번 다름 → 이미지가 조향 결정) |
| **꼬깔 위치** | **잔디 제외**, 회색 트랙 영역 + **가운데 주차공간 가로질러**. 목표는 **차선 위 임의 지점**(→ v2 차선따라도 가능). 최단거리는 주로 주차공간 가로지름 |
| 오라클 | point-goal: 꼬깔 (x,y)로 직선 시연, 다양한 방위(±30~40°)·거리 |
| 라벨 | narration에 꼬깔 방위/거리 fact("cone ahead-left — heading toward it") |
| 마커 | 꼬깔 1.8 m, 밝은 주황, 주행 가능면만 |
| eval | 학습에 없던 꼬깔 위치 → 조향해 접근하는가 |

## 구현 TODO (다음 세션)
1. cone 모델 확대(1.8 m). 잔디 밖 배치 헬퍼(트랙+주차공간, 목표=차선 위 점).
2. route_oracle **point-goal 모드**(꼬깔 (x,y)로 직선 pure-pursuit/Stanley).
   현재 lane/zone/parking만 있음 — 점 목표 추가.
3. collect_corpus **cone 축**(`--cone-groups`): 여러 꼬깔 위치·방위, 상수
   지시문, 오라클 point-goal 접근, intent_slots에 cone 좌표/방위 기록.
   run_episode에 cone 스폰 훅(gz create, v0 despawn).
4. **label_reasoning에 cone fact** 추가(방위·거리 → "cone ahead-left …").
5. 코퍼스 → v29r(v3y+v9+Stanley + cone) → r29 학습(cone-action 부스트).
6. eval: 신규 꼬깔 위치서 조향·접근 확인 + counterfactual(꼬깔 위치 바꾸면
   목표도 바뀌는가).

## 리스크
- servoing 접근은 유망(연속 조향). **도착 정차는 미포함**(별개 난제).
- 접지: 꼬깔이 유일 예측변수가 되도록 위치 다양화(위치 prior 차단).
- 물리: 잔디 제외(주행 검증된 면만) — 사용자 확정.

## 확장 로드맵
v2: 차선따라 꼬깔(지시 조건화) / v3: 탐색(둘러보기) + 도착 정차.
연결: 꼬깔 servoing이 되면 "시각 단서→조건부 액션" 계열(신호정지·회피)과
같은 접지 원리 공유.
