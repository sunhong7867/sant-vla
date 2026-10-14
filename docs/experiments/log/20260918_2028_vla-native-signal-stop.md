# VLA-native 신호 정지 — 시각 접지 조건부 정지 (2026-09-18)

## 배경·목표

단기강좌 타깃 재설정: 다중 지점 A→B 이동은 **트랙이 시각적으로 균일**해
카메라만으로 존 구분 불가 → 학습 불가(지난 실패의 원리적 이유). 대신
**시각 랜드마크 기반 조건부 정지**로 전환 — "빨간불 보이면 정차, 초록불이면
통과". 이는 신호정지·횡단보도정지·장애물회피가 **한 부류**("시각 단서 →
조건부 액션")임을 이용. 이번 세션의 반복 난관("flow-matching이 희소 조건부
액션을 못 배움")의 정면 돌파.

## 시뮬 feasibility (통과)

ego 카메라(VLA 입력) 실측: 신호등이 **크고 선명한 빨간 원**으로, 횡단보도
줄무늬와 함께 정면에 보임(캡처 확인). → **꼬깔 불필요, 시각 접지 가능.**
실차 카메라-only 우려도 해소(단서만 뚜렷하면 됨).

## 코퍼스 (수집 검증 통과)

`collect_corpus.py --signal-groups N` 축 추가:
- 그룹당 **counterfactual 쌍**: 같은 start·같은 cruise 지시문, 색만 다름.
  - RED: `set_signal red` + 오라클 goal=crosswalk_stop → **정지선 앞 정차**.
  - GREEN: `set_signal green` + 오라클 cruise 18s → **통과**.
- 지시문은 red/green 동일(중립 cruise) → **빛 색만이 유일한 예측변수**
  (위치 아닌 단서에 접지 강제).
- run_episode에 signal 훅(`_set_signal`), intent_slots에 `signal` 기록.
- Stanley 선생(반응위상). 도구: `tools/collect_signal.sh`.

**본수집 40ep → 33 packed (RED 19 / GREEN 14)**. 검증:
- RED: 횡단보도 0.7~3.3 m 앞 정차(end_speed 0.00~0.02).
- GREEN: 통과(22 m+ 진행, 이동 중).
- 학습 프레임에 빨간불 크고 선명(접지용).

주의: red/green이 **결과(정지/통과)도 달라** CMI 쌍-검사가 거부 → 패킹은
resample+package 직접(쌍 불요, 학습용).

## r28 학습

**v28r** = v27r(v3y+v9+Stanley 109) + **packed_signal 33** = 400ep.
train_reasoning 패치: signal(session_20260918) 식별 + `--action-signal-weight`
+ v3y_cruise 제외(20260917/20260918). **r28** = r27 레시피 +
`--action-signal-weight 5.0`(희소 정지 액션 부스트). 로그 확인: SIGNAL-STOP
x5 on 4141 frames(33ep), v3y-cruise/v9 x0. 학습 ~2.6h.

## 합격 게이트 (eval, 학습 후)

- **빨간불**: ego가 신호등 앞 정차(속도→0).
- **초록불**: ego가 통과(정차 안 함).
- 반증: 색 무관하게 항상 정차/항상 통과 = 접지 실패(위치/기타 prior).

## 의미

성공 시: 코드 감독관 신호정지 → **VLA-native 신호정지**로 전환, 단기강좌
핵심 데모. 그리고 "시각 단서 → 조건부 정지" 접지가 되면 횡단보도정지·
장애물회피로 같은 레시피 확장. 실패 시: "왜 flow-matching이 조건부 액션
접지를 못 하나"의 정량 사례(그 자체 논문감).

## r28 판정 — 실패, 근본 원인 규명 (2026-09-18)

eval (r28, 신호등 스폰 + ego 접근 + 중립 cruise 지시):
- **RED**: 정차 안 함, 통과 (min speed 1.45, 23 m 지나감).
- **GREEN**: 통과 (1.48, 23 m). **red/green 동일** — 신호 색 전혀 조건화 못 함.
- **언어(reasoning)도 빨간불 언급 없음** ("Passing … speeding up"만).

**근본 원인 = 라벨링 갭**: `label_reasoning`이 신호등을 모른다 → 신호
에피소드 라벨이 "Passing the T3 crosswalk — slowing/steady"로, **횡단보도와
감속(trend)만 있고 "빨간불"(신호 색)은 전혀 없음.** red/green이 같은
crosswalk 라벨(trend만 다름)이라, 공유 백본이 **"빨간불→정차"를 접지할 단서를
못 받음.** 언어헤드가 "빨간불"을 못 배웠으니 액션도 못 배움(언어-액션 동반
실패). + 정지 액션 희소(19ep, ×5로도 부족)라는 flow-matching 난관도 중첩.

**교훈(논문감)**: 시각 단서가 카메라에 뚜렷해도(빨간불 크고 선명), **narration
라벨에 그 단서가 없으면 공유 백본이 접지하지 못한다** — SANT-VLA의 co-training
구조에서 **언어 접지가 액션 접지의 선행조건**임을 보이는 사례.

## 다음 수 (명확)

1. **`label_reasoning`에 신호 fact 추가** (intent_slots.signal 읽어
   "red light ahead — stopping" / "green light — going through"). 언어헤드는
   존/차선을 잘 접지하므로 신호도 접지할 것.
2. 재라벨 → v28r 재변환 → 재학습(신호 액션 부스트 유지, 필요시 상향).
3. 그래도 액션이 안 서면 → 신호 stop 에피소드 대량 재수집(희소 탈피).

이번 실패가 그 자체로 "언어 접지 → 액션 접지" 순서를 특성화. 도구/코퍼스는
재사용 준비됨(collect_signal.sh, packed_signal).

## 진행

- 20:28 feasibility 확인, 코퍼스 축 구현, 파일럿·본수집 검증(33ep), v28r
  변환, r28 학습. 21:xx **eval: 실패**(red/green 둘 다 통과, 언어도 미언급)
  → 근본원인=라벨 신호 부재. 시뮬 정리(요청대로). 다음: 라벨에 신호 추가+재학습.
