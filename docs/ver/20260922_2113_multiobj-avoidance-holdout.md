# 다중 물체 회피 홀드아웃 실험 — 수집 인프라 (2026-09-22 21:13)

단기강좌 3일차 "학습 안 한 상황에서 동작" 요구(교수님, 로봇팔 빨강→파랑 비유)에
대한 시뮬 선검증. 질문은 하나다:

> 회피를 **차량**으로만 배운 정책과 **여러 종류 물체**로 배운 정책 중, 학습에
> 없던 물체(사람)가 차선에 있을 때 어느 쪽이 회피하는가.

가설: 단일 종류 학습은 "차 모양 → 회피"에 과적합, 다종 학습은 "차선 위 뭔가 →
회피"로 일반화. 로봇팔에서 여러 색으로 학습하고 한 색을 빼는 것과 같은 구조.

## 바뀐 것

| 파일 | 변경 |
|---|---|
| `src/simulation_pkg/models/ob_{box,barrel,cone,barrier,person}/` | 프리미티브 정적 장애물 5종. 원점이 **지면**이라 해치백과 같은 z(0.01265)로 teleport 가능. `ob_cone`은 서보잉용 `cone`(중심 원점, 1.0 m)과 별개 |
| `collect_corpus.py` | `--obstacle-models a,b,c`로 플릿 교체(`set_obstacle_fleet`). 스펙에 `noun` 추가(`ob_noun()`: hatchback/prius→car, ob_*→box/barrel/…, 그 외→obstacle) |
| `label_reasoning.py` | 회피 문장이 noun 사용("A stopped box ahead…", "Past the stationary barrel…"). noun 없는 구 v9 코퍼스는 "car" 그대로 |
| `tools/eval/avoidance_trial.py` | `--models ob_person` 으로 물체 지정, `--no-supervisor` 로 감독 대기·재발행 없이 정책 자체 반응만 관찰 |
| `tools/collect_multiobj_avoid.sh` | 신규. train 플릿 수집 → 플릿 제거 → heldout 플릿 수집 → 각각 finalize |

train 과 heldout 플릿을 **같은 월드에 동시에 두지 않는다**. 파킹 스팟(60,60)은
카메라 밖이지만 "한 번도 존재한 적 없음"을 보장하는 쪽이 논쟁의 여지가 없다.

## 실험 설계 (한 쌍)

```bash
# 대조군: 차량만
TAG=carsonly TRAIN_MODELS=hatchback_red,hatchback_blue,hatchback_yellow \
  HELDOUT_MODELS=ob_person,hatchback_green bash tools/collect_multiobj_avoid.sh
# 실험군: 다종 물체
TAG=multi TRAIN_MODELS=hatchback_red,hatchback_blue,ob_box,ob_barrel,ob_cone,ob_barrier \
  HELDOUT_MODELS=ob_person,hatchback_green bash tools/collect_multiobj_avoid.sh
```

기본 36 train 그룹(물체당 6 스타트, 108 에피소드) + 8 heldout. v9 실측
(40그룹 ≈ 2 h)으로 한 조건당 약 2 h. heldout 에 `hatchback_green`을 같이 두는
이유: 색만 다른 차(쉬운 일반화)와 사람(어려운 일반화)을 같은 배치에서 비교.

학습: 두 packed 를 각각 v3y+v9 기반 베이스에 얹어 r-시리즈로 학습(서버).
평가:
1. 개방루프 — heldout packed 에서 v1(사람 우리 차선) 프레임의 조향/속도 예측이
   회피 시연과 같은 방향인지 (`probe_policy_counterfactual.py` 계열).
2. 폐루프 — `avoidance_trial.py --models ob_person --no-supervisor` 로 직선
   (lane2:0.25)·곡선에서 각 3회. 결과 SUCCESS/COLLISION/STUCK 집계.

판정: multi 가 사람에 회피하고 carsonly 가 못 하면 강좌 3일차 과제 성립.
둘 다 못 하면 물체 종류를 더 늘리거나(8종+) 과제를 "학습 안 한 구간"으로 후퇴.

## 주의

- 정지선(OB_STOP_MARGIN 12 m 중심 거리)과 충돌 가드(arc 4.8 m)는 차 반길이
  기준이라 작은 물체엔 보수적이다. 시연 일관성을 위해 그대로 둔다 — 물체마다
  다른 거리에 서면 "물체 종류"가 정지 거리의 예측 변수가 돼 버린다.
- 사람 모델은 마네킹(원기둥+구)이다. 실차 강좌의 진짜 사람과는 다르다. 시뮬
  결과는 "종류 다양성이 일반화를 만드는가"에 대한 답이지 실차 보장이 아니다.
- 파일럿 실행 결과는 이 문서 하단에 추가.

## 파일럿 결과 (2026-09-22 21:14~21:19)

`TAG=pilot TRAIN_MODELS=hatchback_red,ob_box,ob_cone HELDOUT_MODELS=ob_person`,
train 1그룹 + heldout 1그룹.

- 6/6 에피소드 success, finalize 양쪽 OK, 종료 후 잔존 프로세스 0.
- 프리미티브 모델 gz create·teleport·remove 전부 통과. 카메라 프레임에서
  마네킹(빨간 상체·검은 하체·살색 머리)이 잔디·회색 배경과 뚜렷이 구분됨.
- heldout v1 라벨: "A stopped person ahead in our outer lane — slowing down." →
  "The person has not moved — passing it in the inner lane." → "Past the
  stationary person — returning to the outer lane." noun 전파 확인.
- 관찰: v2(옆 차선) 에피소드에 "beside" 문장이 없었다. 시작이 T3 횡단보도
  직후 급커브라 옆 차선 물체가 카메라 원뿔 밖이었던 것으로 보임. v9 와 같은
  로직이므로 본수집(36그룹, 다양한 스타트)에서는 일부 그룹에 나올 것. 본수집
  후 비율 확인 필요.
- 파일럿 데이터(`data_multiobj/packed_pilot*`)는 학습에 쓰지 말 것 — 스모크용.

## lecture_test.sh — GUI 로 장애물 테스트 (2026-09-22 21:40 추가)

`sh /home/sh/ROS2_project/nav-vla/lecture_test.sh` (nav-vla 는 sant-vla 심볼릭 링크).
기존 Driving Studio 스택(`smolvla_demo.sh`)을 그대로 쓰고, 장애물만 바꾼다.

- `race_scenarios.json` 에 `lecture` 시나리오를 매번 다시 써 넣는다 → GUI 경기
  선택기에 "강좌 · 장애물 테스트" 로 뜨고 리셋 버튼으로 재배치 가능. 설치본
  config 는 심볼릭 링크로 소스를 가리킴(확인).
- 기본 장애물은 **prius_hybrid** = ego 와 같은 모델·색 (기존 mission1 과 같은
  방식, `static_model` 이 센서·플러그인 제거). `--model ob_person` 등으로 교체.
- `--avoidance off` 는 `chat_gui` 의 `avoid_enable:=false` (감독의 VLM 목격→문장
  교체 차단, 정책 자체 반응만 관찰). 이를 위해 `smolvla_demo.sh` 에
  `NAVVLA_GUI_ARGS` 패스스루를 추가했다.
- yaw 규약: prius 는 주행방향 +π/2 (qualifying ego·mission1 장애물과 대조해
  일치 확인), 해치백·프리미티브는 주행방향 그대로(collect_corpus teleport 규약).
- 등록(`obstacles.json`)의 kind 는 모델과 무관하게 vehicle — 감독 좌표 백스톱이
  vehicle 만 읽으므로 사람·박스도 차선 귀속이 되게 한다.
- 실제 스택 기동은 아직 안 돌려봤다(랩서버 서빙·RAM 5G 필요). `check` 만 통과.

## GUI 장애물 편집 (2026-09-22 22:05, 22:40 개정)

`lecture_test.sh` 가 `chat_gui` 에 `lecture_mode:=true` 를 넘기면 Driving Studio 가:

- 경기 선택기를 숨긴다(단기강좌엔 경기 종류가 필요 없음). 리셋 버튼은 "출발
  위치로 리셋" — `lecture` 배치로 되돌린다(GUI 로 추가한 `obstacleN` 도 정리됨).
- 사이드바 팔레트 **[모델 콤보][지도에 추가][선택 제거]**. "지도에 추가"를 누르고
  BEV 를 클릭하면 그 자리에 생성(십자 커서, 상단 안내 띠, Esc 취소). 장애물
  클릭=선택(흰 테두리), 드래그=이동, Delete/선택 제거=삭제. 빈 곳 드래그는 종전
  대로 화면 이동. 우클릭 메뉴는 사용자 요청으로 뺐다.
- 놓는 자리는 2.5 m 안의 가장 가까운 차선 점에 스냅(yaw 는 주행방향, prius 만
  +90°); 그 밖이면 자유 배치(`lane: parking`).
- gz 호출(`/world/default/create|set_pose|remove`)은 워커 스레드에서 잠금으로
  직렬화하고 각 작업이 잠금 안에서 레지스트리를 다시 읽는다(빠른 연속 추가가
  전부 `obstacle1` 이 되던 경합을 오프스크린 테스트에서 잡음). `obstacles.json`
  atomic 갱신 → 회피 감독과 BEV 가 mtime 으로 즉시 반영. 드래그 중엔 재로드 생략.
- `apply_scenario` 가 `mission1` 이외 배치에서 `avoid_enable` 을 강제로 껐던 것을
  `lecture` 에선 런처가 준 값을 유지하도록 고침(`--avoidance on|off` 가 실제로 먹게).
- **장애물 차량 위 카메라 제거**: `race_scenarios.static_model` 이 센서·플러그인만
  떼고 카메라/라이다 링크의 시각 메시는 남겨서 지붕 위에 카메라 몸체가 떠 있었다.
  이름에 camera/lidar 가 든 링크와 그 조인트를 통째로 제거. mission1 장애물에도
  같이 적용됨. 남는 링크: chassis, 바퀴 4, steering_wheel, rear_axle, base_link.

검증: 오프스크린 Qt 로 픽셀↔월드 왕복, 히트테스트, 합성 마우스/키 이벤트로
놓기·드래그 이동·클릭 선택·Delete 삭제·빈 곳 pan; gz 요청을 가짜로 바꾼
추가/이동/제거 → 레지스트리·SDF 생성; `static_model("prius_hybrid")` 링크 목록.
실제 GUI 기동 검증은 아직 없음.

## 본수집 결과 (2026-09-22 22:16 ~ 09-23 00:23)

학습 플릿 7종(prius_hybrid·해치백 빨강/파랑/노랑·박스·꼬깔·바리케이드), 홀드아웃
3종(사람·드럼통·초록 해치백). 오라클 pure-pursuit `lookahead_gain 0.6`(첫 시도는
기본 0.9 로 돌다 1 에피소드 만에 재시작). 장애물은 `static_model` 로 스폰(prius 를
그냥 올리면 카메라 토픽이 ego 와 충돌).

| 배치 | 수집 | finalize 통과 | v1(회피) |
|---|---|---|---|
| train 42그룹 | 126/126 success | 92 (tf 갭 11, 보간오차>6cm 23 드롭) | 23 (모델당 2~5) |
| heldout 9그룹 | 26/27 (reset_failed 1) | 26 | 사람 3 · 드럼통 2 · 초록 3 |

드롭 원인은 v9 때와 같은 tf 스트림 갭("ego re-identified mid-episode", 회전 중
0.4~0.8 s 구멍). v1 이 길어서 더 많이 잃는다 → `V1_ONLY=1` repair 배치 24그룹
추가 수집(TAG=multi_fix, 00:2x 시작). 학습기 `--action-multiobj-weight` 는
session_20260922+ 이면서 우리 차선 장애물인 에피소드(v1)에만 걸리고 v0/v2 는
v3y-cruise 규칙(액션 0)에 묶인다 — pure-pursuit 순항이 Stanley 선생과 섞이지
않게.

## 학습·평가 (2026-09-23)

- **v29r** = v28r 스테이징 + packed_multi(92) + packed_multi_fix(20, v1 만). 499 ep /
  122.9k 프레임. stop-audit 로 v1 일부 제외 → 학습기에 잡힌 회피 에피소드 30.
- **r29** = r28 레시피 + `--action-multiobj-weight 4.0`. 01:14 개시, 0.35~0.39 s/step,
  25k steps ≈ 2.5 h.
- 평가 스크립트 `tools/eval/multiobj_heldout_eval.sh <tag>`: `smolvla_demo.sh --no-gui`
  (chat_gui 없음 = 회피 감독 없음) + `avoidance_trial.py --no-supervisor`, 물체
  5종(홀드아웃 사람·드럼통·초록 해치백 + 학습 박스·prius) × 지점 2(직선 0.35 /
  곡선 0.45) × N회. 출발은 장애물 24 m 뒤(`START_OFF=0.17`).
- 평가 하네스 수정 2건: ① 출발 간격 기본 8.5 m 는 시연 정지선(12 m) 안쪽 →
  24 m 로. ② 중심거리 2 m 충돌 판정은 차량 전용 — 마네킹을 들이받고 물리로 멈춘
  것을 "2.16 m 정지"로 읽었다. ego 직사각형 × 물체 footprint 기하 판정 추가
  (차량은 종방향 4.6 m 미만 = 범퍼 접촉, r10 규칙).

### r28 베이스라인 (다중물체 미학습, v9 액션 0) — N=2 × 2지점

| 물체 | 결과 |
|---|---|
| 사람 (홀드아웃) | 4/4 충돌 (2.4~2.8 m 중심거리) |
| 드럼통 (홀드아웃) | 4/4 충돌 |
| 초록 해치백 (홀드아웃) | 4/4 범퍼 접촉 후 정지 (3.56 m 중심) |
| 박스 (학습 물체) | 4/4 충돌 |
| prius (학습 물체) | 4/4 범퍼 접촉 후 정지 (3.87 m) |

r28 은 감독 없이는 어떤 물체도 피하지 않는다 — 차량조차. 이게 "코드 감독이
회피를 담당"하던 구조의 정직한 모습이고, r29 와의 비교 기준.

### r29 @12500 (중간 체크포인트, 02:30) — 전부 충돌

사람 4/4, 드럼통 4/4, **박스(학습 물체) 4/4**, prius 범퍼 접촉. 홀드아웃 이전에
학습 물체조차 안 피한다 → 일반화 문제가 아니라 **회피 액션 자체가 안 배워진 것**.

원인(학습기 코드 확인): `--action-multiobj-weight` 를 `aw[i] *= 4.0` 으로 넣었는데
`resample-comp` 는 `aw = 1/w` 로 시작하고 회피 프레임은 obstacle-boost 로
w = 4~24 라, 실효 액션 가중치가 0.17~1.0. 즉 "x4" 가 사실상 자연 빈도 이하였다.
signal(x5)은 boost 대상이 아니라 w=1 이어서 그대로 5 가 먹었던 것과 다르다.

**r30** (02:44, 4070Ti 에서 r29 와 병렬, 같은 v29r): 플래그를 절대값으로 바꿔
`aw[i] = 8.0` (회피 30 ep, 11.5k 프레임). ETA ≈ 05:35. r29 최종(03:50)도 같은
평가를 돌려 비교.

평가 하네스 메모: gz `create` 서비스가 트라이얼 9번째에서 타임아웃(v9 수집 때의
create/remove 누적 wedge 와 같은 현상) → 스택 재기동 후 잔여분 재실행. 한 스택당
트라이얼 ~8회 안쪽으로 나누는 게 안전.

### 개방루프 제동 프로브 (`code/probe_obstacle_brake.py`, 서버)

"ahead" 프레임(우리 차선 장애물 6~14 m, 시연자가 제동 중) 40개 vs 장애물 없는
프레임 40개에서 3 s 청크의 전진 거리. 제동 지수 = ahead 예측 / clear 예측
(시연 0.74).

| ckpt | ahead pred/demo | clear pred/demo | 제동 지수 |
|---|---|---|---|
| r28 | 1.00 | 0.85 | 0.87 |
| r29 @12500 | 1.04 | 0.83 | 0.93 |
| r29 @25000 (최종, 03:52) | 1.08 | 0.86 | 0.93 |

r29 는 중간·최종 모두 r28 과 구별되지 않는다 — 폐루프 20/20 충돌과 일치. r29
최종의 폐루프 평가는 생략(프로브가 동일하면 결과도 같다). r30 (절대 가중치 8) 의
중간 체크포인트에서 이 지수가 시연(0.74) 쪽으로 내려가는지가 첫 판정.

### r30 @12500 (절대 가중치 8, 04:14) — 여전히 제동 없음

- 프로브 v1 제동 지수 0.99 (r28 0.87, r29 0.93). 단 v1 지수는 "현재 속도
  유지"와 "장애물 반응"을 못 가른다(ahead 프레임은 시연자가 이미 느린 상태라
  state 속도만 따라가도 진행거리가 맞는다).
- **프로브 v2** (청크 내부 속도 변화 dv, 창 6~22 m): ahead 시연 dv −0.28 m/s
  (오라클 제동이 0.55 m/s² 로 완만해 청크당 변화가 작다).
  r28 ahead dv +0.00 / clear +0.01 → 반응 없음.
  r30@12500 ahead dv −0.10 / clear −0.18 → 장애물 특이 감속 없음(clear 에서 더 감속).
- 폐루프 r30@12500: 박스 첫 트라이얼 충돌(3.30 m).

해석: 가중치 문제만이 아니다. resample-comp 계열(r15+)은 액션 손실에서 리샘플링을
상쇄하도록 설계됐고, 8× 를 얹어도 제동이 안 나온다. 반면 r8~r11(`sampler`:
리샘플링이 액션·CE 양쪽) 은 폐루프에서 "차 앞에 정지 후 안 떠남"까지 갔다 —
제동은 배웠던 레시피. **r31** = v29r + `--boost-target sampler --obstacle-boost 4`
(04:18, 3090, save 6250 마다). 차선중심 회귀는 감수. 또 하나의 후보 원인은 시연
자체가 너무 완만하다는 것(청크당 −0.28 m/s) — r31 도 실패하면 다음은 오라클
제동을 세게(accel 1.5 m/s², 정지선 8 m) 해서 재수집.

r30 @12500 폐루프: 박스 4/4 · 사람 4/4 충돌 (04:17~04:26). 프로브와 일치.

### 강한 제동 시연 재수집 (multi_hard, 04:30 시작)

가설 B(시연이 너무 완만)를 r31 결과와 무관하게 병렬로 검증: `OB_ACCEL=1.5`
(오라클 accel_limit 도 같이), `OB_STOP_MARGIN=9`, v1 만 36그룹 + 홀드아웃 6그룹.
1.4 m/s 에서 정지까지 ~1 s → 청크당 감속 −1 m/s 이상. collect_corpus 에
`--ob-accel/--ob-stop-margin` 추가. 라벨 임계(OB_WATCH 11 m)는 9 m 정지에 그대로
맞는다.

r31 @6250 프로브 v2: ahead dv −0.06 / clear −0.08 (시연 −0.28). 아직 없음.
12500 에서 재확인. multi_hard 가 오면 v32r(= v29r + hard v1) → r32(sampler) 로.

multi_hard 결과 (04:27~05:05): train 36/36 success → finalize 24 (tf 갭), heldout 6 → 3.
시연 강도 확인: 가장 센 3 s 구간 dv 중앙값 **−1.96 m/s** (완만 코퍼스 −0.28).
단 오라클이 9 m 정지선을 지나쳐 정지 중심거리 중앙값 6.4 m, 최소 2.75 m — 6 m
stop-audit 이면 절반이 빠져서 hard 만 **4.8 m(차체 접촉선)** 로 완화. 생존 17/24
(바리케이드 0/3, prius 2/5 가 접촉선 안쪽). 회피 시연 합계 = 30(완만) + 17(강함).
v32r 변환 05:1x 시작, r32(sampler) 는 r30 이 GPU0 을 비우면(05:35) 개시.

r31 @12500 프로브 v2 (05:50): ahead dv −0.04 / clear −0.09. sampler 부스트도 완만
시연에선 제동을 못 뽑는다 → 가설 A(가중치)는 기각 쪽, 가설 B(시연 강도)가 남는다.
r32 = v32r + sampler, r30 종료 직후 GPU0 개시.

r30 최종 05:50 종료(3.12 h). **r32** = v32r(516 ep, 강한 제동 v1 17 포함) + sampler
부스트, GPU0 05:52 개시 (save 6250 마다; 첫 체크포인트 ≈ 06:45). 판정 순서:
① 프로브 v2 에서 ahead dv 가 시연(hard 프레임 포함) 쪽으로 내려가는가 →
② 폐루프 박스(학습) → ③ 사람·드럼통·초록(홀드아웃).

r32 @6250 프로브 v2 (06:48): 완만 프레임 ahead dv −0.05 (시연 −0.28); **hard 프레임**
ahead dv −0.11 (시연 −0.48). 아직 없음. 12500(≈07:40)·최종(≈09:00) 에서 재확인.
hard 프레임의 시연 dv 평균이 −0.48 에 그치는 것은 6~22 m 창의 대부분이 제동
전 구간이기 때문(제동 자체는 9~10 m 에서 1 s 안에 끝난다).

r31 최종 (07:10, 2.86 h) 프로브 v2: ahead dv −0.04 / clear −0.09. **완만 시연으로는
어떤 레시피(r29 곱셈 4 / r30 절대 8 / r31 sampler)로도 제동이 안 나온다** — 확정.

### 쌍대 반사실 프로브 (`probe_obstacle_counterfactual.py`, 07:15)

같은 그룹의 v0(빈 차선)/v1(우리 차선 장애물) 프레임을 **같은 k, 같은 state** 로
넣고 청크를 비교(장애물 12~25 m 전방, 시연 제동 전). r31 최종, n=18:
progress(v1)−progress(v0) = **−0.04 m** (sd 0.19), dv 차 −0.01 m/s, 횡 끝점 차 0.18 m.
→ 액션 전문가는 장애물 유무에 **전혀 반응하지 않는다** (본 뒤 무시가 아니라
액션 경로에 시각 정보가 안 닿는 수준). 언어 헤드는 같은 백본에서 장애물을
서술하므로(r5~ 100% 언급) 문제는 인식이 아니라 **flow-matching 액션 헤드의
조건부 접지** — r28 신호정지 실패와 같은 결론.

r32 @12500 (07:26): hard 프레임 ahead dv −0.12 (시연 −0.48); 쌍대 반사실 −0.05 m.
강한 시연을 넣어도 12.5k 까지 변화 없음. **r32 최종(08:31)**: hard ahead dv −0.15
(시연 −0.48), 쌍대 반사실 −0.06 m (sd 0.22) — 결론 불변.

## 밤샘 결론 (2026-09-23 07:30 시점)

| 런 | 데이터 | 부스트/가중치 | 제동(프로브 v2) | 반사실 | 폐루프 |
|---|---|---|---|---|---|
| r28 (기준) | v28r | v9 액션 0 | 없음 | — | 20/20 충돌·접촉 |
| r29 | +multi(완만) | 곱셈 4 (실효 0.17~1) | 없음 | — | 20/20 |
| r30 | 〃 | 절대 8 | 없음 | — | 8/8 |
| r31 | 〃 | sampler ×4 (r8~r11식) | 없음 | −0.04 m | — |
| r32 | +multi_hard | sampler ×4 | 없음(최종 08:31: hard dv −0.15 / 시연 −0.48) | −0.06 m | — |

**판정: 현재 파이프라인(SmolVLA flow-matching 액션 헤드 + 반응형 시연)으로는
장애물 조건부 제동이 학습되지 않는다.** 가중치 방식 3종, 시연 강도 2종 모두 무효.
쌍대 반사실이 0 이라 "홀드아웃 일반화" 질문은 아직 물을 수 없는 단계다.
언어 헤드는 장애물을 서술하므로(기존 r5~ 결과) 인식은 되나 액션으로 안 흐른다 —
r28 신호정지 실패와 동일한 구조적 한계.

### 단기강좌에 대한 함의

1. 3일차 "학습 안 한 물체 회피"를 **VLA 액션의 일반화**로 보여주는 것은 지금
   불가능하다. 물체를 바꾸기 전에 학습 물체부터 안 피한다.
2. 되는 경로는 **인식의 일반화**: 회피 판단은 VLM/코드 감독(이미 4/6 SUCCESS)이
   맡고, 감독의 VLM 이 학습에 없던 물체(사람·드럼통)를 보고 차선변경 문장을
   내리는지를 보인다. "장애물 차량으로 만든 회피 스택이 사람에게도 동작한다"는
   교수님 요구의 형태는 유지되고, 일반화하는 부품이 VLM 이라는 점을 명시한다.
3. VLA 액션 접지를 살리려면 별도 연구 항목이다: 후보는 (a) 장애물 거리를 state 에
   넣는 대신 **정지 목표를 언어로 조건화**(감독이 "stop behind the box" 문장을
   주고 VLA 가 정지 동작만 학습 — 조건부가 아니라 명령 추종이 되어 접지 부담이
   사라짐), (b) 액션 헤드에 시각 토큰 cross-attn 강화(qwen3 cross-attn 함정 참조),
   (c) 데이터 양을 한 자릿수 늘리기. 강좌 전에 끝날 일은 아니다.

### 이번 밤에 만든 인프라 (재사용)

- 수집: `tools/collect_multiobj_avoid.sh` (플릿·홀드아웃·V1_ONLY·OB_ACCEL·OB_STOP_MARGIN)
- GUI: `lecture_test.sh` + Driving Studio lecture 모드(클릭 배치·드래그·삭제)
- 평가: `tools/eval/multiobj_heldout_eval.sh`(폐루프, 기하 충돌 판정, 24 m 출발),
  서버 `code/probe_obstacle_brake.py`(v2 dv), `code/probe_obstacle_counterfactual.py`
- 학습: `code/convert_v29r.sh`/`v32r`, `launch_r29~r32.sh`, `train_reasoning.py`
  (`--action-multiobj-weight` 절대값, noun-agnostic 부스트)
- 데이터: 서버 `data/packed_multi{,_fix,_hard}{,_heldout}`, `lerobot/v29r`, `v32r`

## 정리·분리 (2026-09-23 08:40~09:00)

강좌 테스트 자산을 주행 모델과 분리: 서버 `runs/course/`, `data/course/`, `logs/course/`,
`code/course/`; 로컬 `data_course_multiobj/`, `eval_out/course/`, `server/code/course/`.
r32 최종(08:31) 프로브: hard dv −0.15 / 반사실 −0.06 m — 불변. 색인과 정리 이력은
[docs/course/README.md](../course/README.md).

## 2026-09-28 — 직접 차선변경 시연 (swerve), 위치 고정, r26 에서 1 h resume

사용자 결정: 정지·관찰을 빼고 **가까이서 바로 옆 차선으로** 옮기는 시연만 가르친다
(정지는 r29~r32 에서 안 배워진 부분; 차선변경 동작은 정책이 이미 명령으로 수행).
위치는 lane2 인덱스 142(아래쪽 직선) 고정, 출발은 20~30 m 상류 지터.

- collect_corpus `--ob-swerve-only`(정지 분기 우회) + `--ob-fixed-index`, 발동 거리
  `OB_SWERVE_TRIGGER_M`: 18 → 12 → **8 m**(사용자: 근접해서 회피). 8 m 는 빠른 티어
  2.9 m/s 에서 2.8 s 로 차선변경(~3 s)에 빠듯하지만 72/72 success, 충돌 0.
  첫 시도는 정지 판단 거리(16.2 m)가 발동 거리보다 커서 옛 시연이 돌았다 → 정지
  분기를 swerve 모드에서 완전히 비활성화하고 재수집.
- 라벨: "A box ahead in our outer lane — moving over to the inner lane." /
  "Passing the box in the inner lane." / "Past the stationary box — returning…".
- 결과 `packed_swerve`: 24그룹 × v0/v1/v2 = 72 ep 전부 finalize 통과(짧아서 tf 갭
  없음). v1 = 모델당 3~4. 홀드아웃 배치는 플릿 교체 직후 gz create 가 wedge 되어
  스폰 실패 → 미수집(폐루프 평가는 자체 스폰이라 무관; 반사실 프로브는 train 쌍으로).
- 학습 **r33** = r26(데모 기본) 에서 resume, 데이터 v33s = Stanley 109 + swerve 72,
  8000 steps ≈ 1 h(학생 예산과 동일), sampler 부스트 ×4. 판정: 반사실 횡방향 끝점
  차 → 박스 폐루프 → 사람·드럼통.

### r33 @4000 (14:50) — 처음으로 장애물에 반응

쌍대 반사실(같은 k·같은 state, 빈 차선 vs 장애물, `packed_swerve` 학습 쌍, n=24):

| 창 | PRED 횡 끝점 차 | DEMO | 비 |
|---|---|---|---|
| 12~25 m (발동 전, 멀리) | 0.14 m | 0.35 | 0.40 |
| **8~11 m (발동 직전, 아직 차선 안)** | **0.48 m** | 1.36 | 0.35 |
| 5~8 m (발동 직후) | 0.75 m | 1.05 | 0.72 |
| 3~10 m | 0.62 m | 1.15 | 0.54 |

8~11 m 창은 ego 가 두 변형 모두 차선 중앙에 있고 이미지 차이가 장애물 픽셀뿐인데
0.48 m 가 나온다(r29~r32 는 모든 창에서 0.04~0.06 m). **액션 헤드가 장애물을 보고
조향을 바꾸기 시작한 첫 증거.** 학습 프레임이라 과적합 검사 수준이며, 폐루프
(박스, 학습 지점 0.35 + 새 지점 0.45)가 진짜 판정. 최종(8000) 프로브 자동 실행.

r33 최종 (8000, 15:15): 8~11 m 창 0.50 m(비 0.36), 5~8 m 0.74(0.70), 12~25 m 0.14 —
중간과 동일, **정체**. 폐루프 r33@4000 박스 4/4 충돌(학습 지점·새 지점 모두);
최종 폐루프는 충돌 시 횡 오프셋 기록 추가해 재실행. **r34** = 같은 v33s·r26,
부스트 ×8 / 16k steps(15:16, GPU1) — 노출을 올리면 비가 오르는지.

r33 최종 폐루프 (박스, 15:20): 4/4 충돌. 충돌 순간 횡 오프셋 +0.14 / +0.34(학습 지점),
−0.24 / −0.24(새 지점) — 회피 방향(lane1 = +)으로 0.3 m 안쪽. 개방루프 0.5 m 반응이
폐루프(3 s 청크·2.1 s 커밋)에선 차선 유지에 묻힌다. 필요한 건 1.6 m.

r34 @4000 (부스트 ×8, 15:43): 8~11 m 0.48 m(비 0.35), 5~8 m 0.74 — r33 과 동일.
노출을 2배 올려도 반응 크기가 안 변한다 → 데이터 노출 문제 아님. **r35** = 과적합
검사(v35s = swerve 72 ep 만, 순항 코퍼스 제거, r26 에서 4000 steps, 15:49 GPU0):
비가 1.0 근처로 가면 혼합 문제, 0.35 에 머물면 모델 한계.

r34 @8000 (16:08): 0.53 m(비 0.39). **r35 과적합 검사 (16:23)**: 회피 쌍만 학습해도
2000 step 0.40 / 4000 step 0.42 m(비 0.30~0.31). 순항 데이터를 다 빼도 같은 천장.

## 2026-09-28 판정

| 런 | 데이터 | 부스트/steps | 8~11 m 반사실 (시연 1.36 m) | 폐루프 박스 |
|---|---|---|---|---|
| r29~r32 (정지 시연) | multi(+hard) | 여러 방식 | 0.04~0.06 m | 20/20, 8/8 충돌 |
| r33 | Stanley+swerve, r26 resume | ×4 / 8k | 0.48 → 0.50 m (0.36) | 4/4 충돌, 횡 0.1~0.3 m |
| r34 | 〃 | ×8 / 16k | 0.48 → 0.53 m (0.39) | — |
| r35 | swerve 만 (과적합) | ×4 / 4k | 0.40~0.42 m (0.31) | — |

- 직접 차선변경 시연으로 바꾸자 **액션 헤드가 장애물 픽셀에 반응하기 시작**했다
  (정지 시연 시절 0.05 m → 0.5 m). 이건 오늘의 진짜 성과이고, 시연 설계가 원인의
  절반이었다는 뜻이다.
- 그러나 반응 크기가 시연의 30~40% 에서 **천장**에 걸린다. 스텝(4k→16k), 노출(×4→×8),
  데이터 혼합(순항 제거)을 바꿔도 0.4~0.5 m. 폐루프에선 차선 유지에 묻혀 0.1~0.3 m
  이동 후 충돌. 남은 변수는 모델 쪽(청크 3 s 안에서 flow-matching 이 두 모드—유지/
  회피—를 평균내는 경향, 시각 토큰→액션 경로 용량)이라 강좌 전 해결은 아니다.
- **강좌 결론 유지**: 3일차 미학습 물체 과제는 VLM 감독의 인식 일반화로. VLA-native
  회피는 "반응은 하지만 부족하다"는 정량 사례로 논문 재료(반사실 0.36 vs 시연).

다음에 시도할 것(연구 항목): ① 청크를 짧게(1.5 s)·커밋 짧게 해 폐루프 시각 보정
빈도 ↑, ② 회피 구간만 별도 헤드/명령 토큰으로 조건화("swerve left" 문장을 감독이
주는 하이브리드), ③ 시연 횡 이동을 크게(2차선 폭 3.16 m 전부 쓰는 완만한 S) 해
0.4 m 반응이라도 충돌을 피하게.
