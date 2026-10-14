# 해설로 동작 조건화(situation prompt) — 분석 요약·설계·r40 (2026-09-30 16:01)

직전 문서 [20260930_1530](20260930_1530_ramp70-relocation-result.md) 의 분석 사슬을 요약하고, 거기서 나온
"해설로 동작을 조건화" 설계와 구현, r40 검증을 기록한다. 이 실험은 계획서
[20260929_1503](20260929_1503_avoid-data-scaling-plan.md) 의 스케일링 스윕 **시작 조건**(학습한 박스를
폐루프에서 한 번은 피한다)을 통과시키려는 시도다. 스윕 자체가 아니다.

## 1. 분석 요약 — 왜 이 설계인가

| 단계 | 관측 | 근거 |
|---|---|---|
| 폐루프 | r38/r39 15/15 충돌. 학습 물체 앞 1.1~1.4 m 만 비킴, 미학습 0.3 m | 1530 문서 폐루프 절 |
| 반사실 | 장애물 있음/없음 차이가 시연의 18~28% | probe_ramp70 |
| 위치 prior | **빈 차선(v0)에서도 +0.65~0.70 m** 회피 예측, state=0 동일 | probe_fit |
| 위치에 묶임 | 장애물이 한 번도 없던 순항 영상: 학습 위치 70 에서 +0.76 m, 학습 데이터가 지나간 구간 +0.3~0.57, 안 지나간 330 은 베이스와 같음 | probe_bg |
| **해설은 본다** | r38 해설의 장애물 언급: v1 10–14 m 43~47%(state=0 동일), v0·순항 0~3% | probe_narr |
| 구조 | 액션 전문가는 해설 토큰을 보지 않는다(해설은 prefix 위 두 번째 트렁크 패스). v0/v1 은 명령어·state 가 같아 단서가 장애물 픽셀뿐 | reasoning_policy.py docstring |

결론: 병목은 "못 봄"보다 **"봐도 동작이 안 씀"**. 위치 다양화는 배경 지름길을 없애지만 이 전달 문제는
건드리지 않고, 명령어를 모든 에피소드에 같은 문장으로 바꾸는 것도 v0/v1 을 가르는 정보가 없어 무효다.
반면 이 모델은 **명령어 문장에 따라 조향을 바꾸는 것은 잘 한다**(차선 명령 반사실 등). 그래서 해설을
검출기로 쓰고 그 결과를 문장으로 동작에 넣는다 — VLM 감독이 문장을 바꾸는 현재 구조를 모델 안으로
옮기는 것과 같다.

## 2. 설계

### 상황 문구 (고정 4종, 학습·서빙이 같은 함수 `situation_of`)

| 단계 | 해설/라벨 앞머리 | 문구 | v38r 프레임 비율 |
|---|---|---|---|
| ahead | `A (stopped) {noun} ahead in our …` | `Situation: obstacle ahead in our lane.` | 4.7% |
| passing | `Passing the {noun} …` (T3 crosswalk 제외), `The {noun} has not moved …` | `Situation: passing the obstacle.` | 5.9% |
| past | `Past the …` | `Situation: past the obstacle.` | 3.7% |
| 그 외 | 나머지 | `Situation: road clear.` | 85.6% |

명사는 버린다 — 해설은 박스·콘·사람도 거의 항상 "car" 라고 한다.

### 학습 (`train_reasoning.py --situation-prompt`)

- 데이터셋이 skeleton(`variants[0]`)에서 문구를 만들고, 학습 루프가 **동작 패스의 task 뒤에** 붙인다.
- **해설 패스는 원래 task 를 본다.** 같은 prefix 를 공유하면 해설 헤드가 영상 대신 task 에 적힌 정답 문구를
  베끼게 되고(검출기 붕괴), 서빙에선 자기 이전 출력을 다시 읽는 되먹임이 생긴다. 그래서 원래 task 를
  따로 토큰화해 `reasoning_lang_tokens` 로 넘기고, 정책은 이게 있으면 해설 패스용 prefix 를 따로 만든다
  (비전 인코더를 두 번 돌리는 비용: step 0.28 → 0.47 s).
- r40 = r38 레시피(v38r, r26 에서 8000 step, sampler 부스트 x4, 짝 부스트) + 이 플래그 하나.

### 서빙 (`vla_policy_server.py --situation-from-reasoning`)

- 기존 해설 워커를 그대로 쓰되 12 토큰만 생성(단계는 앞머리로 판별). 매 요청 갱신(`--reasoning-every 1`).
- 해설이 ahead/passing/past 면 그 문구로 전환하고 마지막 검출 후 3 s 유지(`--situation-hold-s`), 아니면
  road clear. 해설 워커는 원래 task, 동작 패스만 `task + 문구`.
- 응답에 `situation` 필드, `--reasoning-log` 에 문구 기록. 데모/평가: `NAVVLA_SITUATION=1`
  (`smolvla_demo.sh` → `server/start_demo_policy.sh` 3번째 인자), `SITUATION=1 bash tools/eval/ramp70_eval.sh`.

### 알려진 위험

- **노출 격차**: 학습은 정답 문구(완벽한 검출기), 서빙은 모델 해설(10–14 m 검출률 약 40~47%)로 조건화한다.
  검출이 늦으면 회피도 늦다. v1 은 증강 없이 측정하고, 필요하면 문구 전환 시점 지연 증강을 v2 로.
- 해설 검출기 자체가 학습 위치에 묶일 가능성 — r38 에선 v0 0~3% 라 아직은 아님.

## 3. 변경 파일

| 파일 | 변경 |
|---|---|
| `server/code/reasoning_vla/reasoning_dataset.py` | `situation_of()`, 문구 상수, item["situation"], collate 키 |
| `server/code/reasoning_vla/reasoning_policy.py` | `REASONING_LANG_TOKENS/MASK` — 있으면 해설 패스용 prefix 분리(학습·`generate_reasoning` 둘 다). 없으면 기존과 동일 |
| `server/code/train_reasoning.py` | `--situation-prompt`: 원래 task 별도 토큰화(텐서 복제 후 preproc), 동작 task 에 문구 |
| `server/code/vla_policy_server.py` | `--situation-from-reasoning`, `--situation-tokens`, `--situation-hold-s` |
| `server/start_demo_policy.sh`, `smolvla_demo.sh`, `tools/eval/ramp70_eval.sh` | SITUATION 전달 |
| `server/code/course/launch_r40.sh`, `probe_situation.py` (신규) | 학습, 오프라인 검증 |
| `src/sant_vla_pkg/reasoning_vla/*`, `src/sant_vla_pkg/scripts/vla_policy_server.py` | 서버 코드 사본 동기화 |

서버의 이전 코드는 `~/sunhong/nav-vla/backup_20260930/` 에 백업. 새 플래그를 안 쓰면 기존 경로와 같다.

## 4. 검증

### 스모크 (16:00)

20 step 학습·저장·decode 정상. 0.47 s/step.

### 기준: r38 에 `probe_situation.py` (문구를 모르는 모델, 셀당 10)

| r38 | 창 | 문구 clear | 문구 ahead | 검출기 non-clear |
|---|---|---|---|---|
| v1 | 10–14 m | +0.96 | +1.00 | 4/10 |
| v1 | 6–10 m | +1.56 | +1.60 | 9/10 |
| v0 | 10–14 m | +0.75 | +0.76 | 0/10 |
| v0 | 6–10 m | +0.36 | +0.38 | 0/10 |

문구를 바꿔도 차이 ±0.04 m — 문구로 학습하지 않은 모델은 문구를 무시한다(예상대로). 12 토큰 decode 의
검출률은 60 토큰(probe_narr)과 비슷하다.

### r40

학습: 16:00~16:56 (0.92 h), GPU0. 로그 `logs/course/navvla_reasoning_r40.log`.

#### 오프라인 — `probe_situation.py` (셀당 30, 인덱스 70, 3 s 청크 끝 횡이동 m, + = 회피 쪽)

| r40 | 창 | 문구 clear | 문구 ahead | 문구 passing | 검출기 non-clear | 서빙 경로 |
|---|---|---|---|---|---|---|
| v1 | 14–20 m | +0.27 | +1.02 | +0.61 | 5/30 | +0.42 |
| v1 | 10–14 m | +0.34 | +1.43 | +0.94 | 14/30 | +0.86 |
| v1 | 6–10 m | +0.95 | +1.46 | +1.31 | 30/30 | +1.45 |
| v0 | 14–20 m | +0.27 | +0.98 | +0.59 | 0/30 | +0.27 |
| v0 | 10–14 m | +0.33 | +1.34 | +0.87 | 1/30 | +0.35 |
| v0 | 6–10 m | +0.32 | +1.18 | +0.69 | 0/30 | +0.32 |
| 미학습 v1 (n=2) | 10–14 m | +0.44 | +1.88 | +1.32 | 2/2 | +1.88 |

읽는 법:

1. **문구가 동작을 결정한다.** 빈 차선(v0) 영상에 "ahead" 를 주면 +1.34 m, 장애물(v1) 영상에 "clear" 를 주면
   +0.34 m. r38 은 문구를 바꿔도 ±0.04 m 였다.
2. **위치 prior 가 줄었다**: r38 v0 10–14 m +0.65~0.70 → r40 "clear" +0.33. 그러나 시연(+0.04)보다 여전히 크다 —
   잔여 편향.
3. v1 6–10 m 에서 "clear" 가 +0.95 인 건 이미 꺾는 중인 구간이라 조향 state 로 맞추는 몫이다(r38 에서도 확인).
4. **서빙 경로**(모델 자신의 12 토큰 해설 → 문구): v1 − v0 차이가 10–14 m 에서 +0.51 m(r38 반사실 약 0.2).
   10–14 m 검출률 14/30 이 평균을 깎는다. 6–10 m 는 30/30, v0 오탐 1/90.

#### 폐루프 — `SITUATION=1 RUNS=r40 bash tools/eval/ramp70_eval.sh` (16:57~17:05, 격리, 저속 지시문, 감독 없음)

**8/8 충돌.** 스윕 시작 조건은 여전히 미통과.

| 물체 | r38 횡 편차 | r40 횡 편차 | r40 서빙 상황 문구 (`logs/situation_serve.jsonl`) |
|---|---|---|---|
| 박스 (학습) | 1.13, 1.36 m | 1.04, 1.02 m | 출발 직후(요청 2번째)부터 ahead, 충돌까지 유지 |
| 빨강 해치백 (학습) | 1.12, 1.08 m | 0.88, 0.86 m | 접근 중 ahead |
| 사람 (미학습) | 0.27, 0.32 m | 0.20, 0.20 m | **ahead 한 번도 안 나옴** — 검출 실패 |
| 드럼통 (미학습) | 0.32, 0.32 m | **0.81, 0.87 m** | 출발 직후 ahead ("A car ahead") |

읽는 법:

1. **검출된 미학습 물체(드럼통)는 반응이 커졌다** (0.32 → 0.84 m). 해설이 "car" 로 부르든 "ahead" 문구만 나오면
   동작이 따라간다 — 설계 의도대로의 신호. 검출 못 한 사람은 그대로(0.2 m).
2. **그러나 "ahead" 가 접근 내내 켜져 있어도 1 m 안팎에서 멈춘다.** 오프라인에선 같은 문구로 3 s 에 +1.0~1.4 m 를
   예측했다. 즉 남은 병목은 검출이 아니라 **문구 → 폐루프 차선변경 완수** 구간이다.
3. 이 구간의 후보 원인 (미검증):
   - **학습 분포 밖의 "ahead"**: 학습에선 ahead 문구가 10–14 m 부터 나오는데, 서빙에선 약 22 m 정지 상태부터 켜졌다.
     일찍 옆으로 흘렀다가 두 차선 사이의 낯선 영상·state 에서 복귀하는 진동일 수 있다.
   - **브리지 후처리**: `curv_boost_slow 0.85`(저속 지시문의 곡률을 85% 로), `refill_at 0.3`(청크의 약 70%, 약 2 s 를
     재예측 없이 실행 — 트라이얼당 청크 7개). 램프 문서 미해결 3 번과 같은 항목.
   - 트라이얼 로그에 궤적이 없어 어느 쪽인지 가를 수 없다.

### 다음 (제안)

1. **궤적 기록**: `avoidance_trial.py` 보고서에 0.5 s 간격 (장애물까지 거리, ego 횡 편차, 서빙 문구)을 추가해 멈추는
   지점과 모양(일정하게 1 m / 갔다가 복귀)을 본다.
2. **브리지 변형 2 개** (박스 × 2 씩): `REFILL_AT=0.6`, `curv_boost_slow 1.0`. 둘 다 서빙 코드 변경 없이 파라미터만.
3. 1·2 로도 안 되면 학습 쪽: "ahead" 문구 전환 시점 증강(학습에서 12~22 m 사이 무작위로 ahead 를 앞당김) —
   서빙에서 일찍 켜지는 상황을 학습 분포 안으로.
4. 사람 검출 실패는 해설 라벨·데이터에 사람이 없어서다(명사 편향 "car"). 강좌 3일차 결론(미학습 물체 인식은 VLM
   감독)은 유지.

### 이후 — 궤적 기록·브리지 변형·부정 대조

별도 문서로 분리: [20260930_1953](20260930_1953_curv-boost-and-negative-control.md) — 1 m 에서 막던 건
`curv_boost_slow 0.85`, 풀면 "성공"하지만 옆 차선 장애물 대조에서도 똑같이 꺾어 충돌(위치 prior).
