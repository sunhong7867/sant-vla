# ICCE-ASIA 2026 기존 증거 기반 논문 계획 v4

## 0. 결정 요약

| 항목 | 결정 |
|---|---|
| 논문 형태 | compact VLA 차량 배치에 대한 version-scoped system case study |
| 새 알고리즘 | 제안하지 않음 |
| 새 코드ㆍ로직 | 수정하지 않음 |
| 새 학습ㆍ주행 | 수행하지 않음 |
| 주 checkpoint | `models/ckpt_v6_60k` |
| 다른 checkpoint | 버전을 명시한 진단ㆍ경계 사례로만 사용 |
| 공식 수치 장부 | [existing evidence ledger](icce_asia_2026_existing_evidence_ledger.csv) |

### 작업 제목

> **Deploying a Compact VLA for Simulated Vehicle Control: A Version-Scoped ROS 2/Gazebo System Case Study**

더 보수적인 대체 제목:

> **From Checkpoint to Closed Loop: A ROS 2/Gazebo System Case Study of Compact VLA Vehicle Control**

`Action-Chunk Commitment`는 제목과 주 기여에서 제외한다. 현재 저장된 기록만으로는 최신
v6 시스템에 대해 충분히 통제되고 반복된 commitment 실험을 구성할 수 없기 때문이다.

### 연구 질문

> What was demonstrated by the recorded compact-VLA vehicle deployment, and which observation,
> data, and execution contracts bounded the validity of its closed-loop results?

### 주장 초안

> We document a compact VLA deployment that outputs 30-step incremental SE(2) chunks through a
> 10-Hz ROS 2--Gazebo command loop. Holding v6 weights fixed, we summarize eight recorded 115-s trajectories
> under a predefined 5-m ring-departure threshold and descriptively compare four direct-replay
> and four queue-preview target-lane trajectories using offset proxies. Historical,
> version-scoped diagnostics identify camera-topic mismatch and off-ring demonstrations as
> potential confounds. The evidence is limited to one track and start and does not establish
> general robustness or executor superiority.

---

## 1. 이번 제출에서 하지 않는 일

이 절은 편집 중 범위가 다시 커지는 것을 막는 hard gate다.

### 금지

- `src/`, `server/`, `tools/`, launch, vehicle model의 코드 또는 파라미터 변경
- evaluator 초기화 수정, single-run mode, telemetry, queue lineage, sidecar logger 추가
- checkpoint 재학습, corpus 재생성, 새 데이터 수집
- Gazebo 신규 rollout, seed 반복, refill/commitment sweep, oracle 실험
- 과거 버전의 수치를 v6 결과와 합쳐 하나의 factorial ablation으로 표현
- 기록되지 않은 latencyㆍhardwareㆍreset 수치를 추정

### 허용

- 기존 소스와 문서를 읽어 system contract를 정확히 기술
- 이미 저장된 JSON/log에 기존 evaluator를 다시 실행해 수치 확인
- 기존 artifact로 figure/table 생성
- 수치의 checkpoint, snapshot, config, sample count, limitation을 정정
- LaTeX 작성, 인용 확인, A4/page-count/가독성 검수

즉, 앞으로 생기는 산출물은 모두 **문서와 기존 결과의 재표현**이며 차량의 동작을 바꾸는
산출물은 없다.

---

## 2. 논문의 정확한 위치

GuardedLC는 `utterance -> symbolic intent -> command gate`를 다뤘다. 이 논문은 그
인터페이스를 확장하지 않고 다음 경계를 다룬다.

```text
front camera + English instruction + vehicle state
                         |
                         v
                compact SmolVLA policy
                         |
               30 x [dx, dy, dyaw]
                         |
                         v
        ROS 2 bridge / queue / low-level tracking
                         |
                         v
                 Gazebo vehicle motion
```

평가 단위도 다르다.

| GuardedLC | 이번 논문 |
|---|---|
| intent exact match, refusal/OOS, command false positive | closed-loop trajectory, ring departure, lane-offset proxy |
| rule--LLM router | fine-tuned compact VLA와 ROS 2 실행층 |
| symbolic command boundary | action chunk에서 차량 motion까지의 배치 경계 |

### 예상 기여

1. **Versioned vehicle embodiment.** 이미지ㆍ영어 문장ㆍ3차원 차량 상태에서 30-step
   incremental SE(2) action chunk를 출력하도록 이전에 파인튜닝된 compact VLA checkpoint를
   10 Hz command loop의 ROS 2--Gazebo 폐루프에 배치한 구성을 문서화한다.
2. **Frozen-weight executor characterization.** v6 weights를 유지한 채 저장된 direct replay와
   queue-preview artifact를 condition당 4개 target-lane trajectory의 offset proxy로 서술적으로
   비교한다.
3. **Cross-layer deployment diagnostics.** C급 historical camera-topic comparison과 confounded
   demonstration audit을 A급 v6 결과와 분리해 잠재적 deployment confound로 보고한다.

기여 동사는 `propose`, `solve`, `guarantee`가 아니라 `document`, `characterize`, `report`를
사용한다.

---

## 3. 증거 사용 체계

모든 숫자는 [증거 원장](icce_asia_2026_existing_evidence_ledger.csv)의 ID를 가진다.

| 등급 | 조건 | 본문 사용 |
|---|---|---|
| A | raw artifact와 현재 checkpoint가 남아 있고 기존 analyzer로 재확인 가능 | 주 결과 표ㆍ그림 가능 |
| B | raw는 남았지만 checkpoint/manifest 일부가 없거나 비교가 탐색적임 | 보조 결과ㆍ진단에 사용 |
| C | 당시 문서만 남았거나 여러 변화가 혼입됨 | 역사적 진단ㆍ한계에만 사용 |

등급은 **수치의 추적 가능성**을 뜻하며 run validity를 보증하지 않는다. 특히 E02/E03은 raw와
checkpoint가 남아 A급이지만, bridge log의 startup watchdog 때문에 현재 코드가 정의한
`watchdog activations == 0` valid-run 조건을 충족하지 않는다.

### 3.1 주 증거 1: v6-60K 폐루프 기록

현재 남은 `v6r1_map.json`과 `v6r2_map.json`에는 115초 trajectory가 각각 4개씩 있다.
기존 `compare_segments.py`로 재확인하면 ring centerline에서 5 m를 넘는 trajectory는 0/8이며,
두 artifact의 최악 거리는 각각 2.99 m와 3.64 m다.

허용 문장:

> No trajectory exceeded the evaluator's 5-m ring-departure threshold across eight recorded
> 115-s v6 rollouts; the largest recomputed ring-center distance was 3.64 m.

금지 문장: `zero lane violations`, `safe driving`, `robust over long horizons`.

각 bridge log에는 평가 instruction 직후 1--4회의 startup watchdog activation이 남아 있다.
현재 bridge 주석과 구현은 한 번의 activation도 eval-invalid로 정의한다. 따라서 trajectory와
threshold 수치는 재계산할 수 있지만 이를 `valid evaluation run` 또는 최종 benchmark라고
부르지 않는다. 이번 무신규-run 원칙에서는 이 결함을 숨기지 않고 system-contract 교훈으로
포함한다.

중요한 감사 결과가 하나 있다. 2026-08-06 문서의 lane median 0.48--0.54/0.26--0.36 m와
max 1.36--1.46 m는 당시 `y6v` artifact가 남아 있지 않고, 현재 남은 `v6r1/r2`를 다시 계산한
값과도 일치하지 않는다. 따라서 이 수치는 주 결과 표에서 제외하고, 필요하면 “당시 문서
보고값”으로만 별도 표기한다.

### 3.2 주 증거 2: 동일 v6의 replay와 queue-preview

`v6r1/r2`와 `v6pv1/pv2`의 DIFFERENT-instruction target trajectories를 비교한다. lane
median/max는 lane별 condition당 2개 trajectory, 합산 segment 수는 condition당 4개 target
trajectory에서 나온다. departure는 SAME과 DIFFERENT를 모두 포함한 condition당 8개 저장
trajectory를 센다. teacher-corpus reference line을 사용한 기존 analyzer의 기록은 다음과 같다.

| 지표 | replay r1/r2 | queue preview r1/r2 |
|---|---|---|
| outer median absolute offset | 0.48 / 0.44 m | 0.30 / 0.26 m |
| inner maximum segment offset | 1.21 / 1.27 m | 0.79 / 0.93 m |
| segments over 0.5 m, inner+outer | 16 / 19 | 8 / 10 |
| 5 m ring-departure threshold, all saved trajectories | 0/8 | 0/8 |

이는 동일 v6 weights와 fast instruction에서 얻은 두 번의 기록이다. 다만 sequential tuning,
단일 track/start, 당시 full-size vehicle snapshot, teacher-derived reference line이라는 한계가 있다.
`preview가 일반적으로 우월하다`가 아니라 `recorded v6 probes에서 offset proxy가 감소했다`고
쓴다. 네 bridge log 모두 evaluated instruction 시작 직후 nonzero watchdog activation을 포함하므로
현재 validity rule 아래 contract-valid comparison이라고 부르지 않는다.

preview는 남은 VLA action queue를 적분해 전방 구간의 평균 곡률을 계산하는 저수준 추종층이다.
모델 구조나 학습법의 기여로 포장하지 않는다.

### 3.3 보조 진단: 기하학적 threshold 기록

`geometric_lane_check.py`는 당시 폭 1.75 m 차량에서 기하학적 차선 중앙 대비 구간 중앙값
절대 편차가 0.70 m를 넘는 segment를 셌다.

| 설정 | artifact 수 | 초과 segment 수 | inner/outer 최대 구간 중앙값 |
|---|---:|---|---|
| replay + fast | 2 | 8, 8 | 1.13/1.07, 1.40/1.72 m |
| queue preview + fast | 2 | 2, 5 | 0.77/0.99, 0.98/0.74 m |
| replay + normal | 1 | 5 | 1.17/0.81 m |
| queue preview + normal | 1 | 1 | 0.75/0.69 m |
| preview + normal + curvature speed cap | 1 | 0 | 0.65/0.68 m |
| preview + normal + speed/steering shaping | 2 | 0, 0 | 0.69/0.47, 0.66/0.45 m |

이 표는 historical selected-artifact characterization이다. 현재 vehicle은 0.85 scale로
변경되어 0.70 m가 현재 물리 접촉 threshold라는 뜻이 아니다. speed cap과 steering boost는
고전 제어이며, `pure VLA`, `lane-safe`, `zero lane touch` 표현을 쓰지 않는다.

### 3.4 언어 조건 반응: v3y-40K 경계 사례

같은 정준 출발점의 문서 기록에서 학습 표현 inner/outer 쌍은 +2.51 m의 횡방향 분리를 보였고,
동일 문장 반복은 +0.05 m였다. 두 test 표현 쌍은 +0.36 m와 +0.06 m, test 속도 표현은
2.33 대 2.31 m/s로 기록됐다.

이 결과는 다음처럼만 해석한다.

- 평가한 학습 표현에서는 instruction-conditioned differentiation이 관찰됨.
- 두 test 표현과 속도 표현에는 같은 정도의 반응이 유지되지 않음.
- v3y 결과이며 v6 폐루프 수치와 동일 실험이 아님.
- raw trajectory와 정확한 반복 수가 남아 있지 않으므로 C급 historical diagnostic임.
- 자연어 일반화나 semantic grounding을 말하지 않음.

### 3.5 관측 계약: v3y camera diagnostic

학습 카메라와 다른 `/vla_camera/image_raw`의 30K/35K/40K sweep 요약에서 inner/outer 차선
중심 오차가 3.8/1.8 m로 기록됐고, 40K checkpoint를 학습 때 사용한
`/camera/image_raw`로 맞춘 뒤 0.19--0.26/0.15 m로 기록됐다. mismatch 값이 여러 checkpoint의
sweep 요약이므로 same-40K controlled comparison이라고 부르지 않는다. 반복 수와 raw 전체도
현재 복구되지 않아 C급 version-scoped diagnostic으로만 사용하며 v6 최종 성능과 분리한다.

### 3.6 데이터 계약: tail contamination diagnostic

감사에서 off-ring trajectory가 16 episodes, 약 1,600 frames(약 2%) 발견됐다. 이후 clean v5는
오염 제거뿐 아니라 junction data 병합도 포함했다. 따라서 다음 연결은 금지한다.

```text
오염 제거 하나만으로 0/8을 달성했다  # 인과 주장 불가
```

안전한 표현은 다음과 같다.

> The audit identified 16 off-ring episodes (about 1,600 frames, roughly 2%). A subsequent
> cleaned-and-augmented lineage recorded no persistent departure in eight probes, but the
> intervention was confounded by simultaneous data addition.

### 3.7 DAgger 결과의 역할

v6와 v7 raw map은 각각 8개의 115초 trajectory를 포함하며 ring departure가 0/8이었다.
v7의 -1.88 m에서 -1.45 m 변화는 r2 outer trajectory의 단일 paired S-curve segment다.
전역 lane median은 대체로 나빠졌다. v7 checkpoint와 완전한 manifest가 현재 없으므로 B급
보조 진단으로만 사용하며, S-curve 수치를 8회 반복 효과처럼 표현하지 않는다.

---

## 4. 연구 질문별 답변 범위

### RQ1. compact VLA 차량 배치가 실제 폐루프에서 무엇을 수행했는가?

v6-60K의 저장된 8개 115초 trajectory와 시스템 구조를 보고한다. 답은 단일 ring track,
start, 당시 simulator/vehicle snapshot에 한정하며, startup watchdog 때문에 contract-valid
benchmark라고 부르지 않는다.

### RQ2. replay와 queue preview에서 기록된 offset proxy는 어떻게 달랐는가?

동일 v6와 fast instruction에서 replay와 queue preview의 raw-backed offset proxy를 비교한다.
반복 수와 sequential tuning을 공개하고 일반적 우월성이나 새 controller novelty를 주장하지 않는다.

### RQ3. 어떤 잠재적 cross-layer deployment confound가 기록되었는가?

camera alignment는 historical comparison, contamination은 confounded audit로 증거 유형을
나누어 답한다.

### RQ4. 무엇이 아직 증명되지 않았는가?

- 다른 map, traffic, weather, sensor, vehicle에 대한 일반화
- 실차 주행
- 자유문장 또는 한국어 지시 이해
- 장애물 회피를 VLA가 직접 학습했다는 주장
- 실시간 deadline 보장
- 차선 접촉ㆍ충돌ㆍ기능 안전 보장
- 특정 executor가 일반적으로 우월하다는 통계적 결론

---

## 5. 논문 구성과 페이지 예산

| 분량 | 내용 |
|---:|---|
| 0.8쪽 | Introduction: 문제, 범위, 기여 |
| 0.6쪽 | Related Work: compact VLA, driving VLA, ROS 2 embodiment |
| 1.2쪽 | System: 입력, SmolVLA, SE(2) chunk, ROS 2 queue, simulator |
| 0.7쪽 | Evidence Protocol: version boundary, metrics, evidence grade |
| 1.4쪽 | Results: v6 closed loop, v6 executor, historical diagnostics |
| 0.7쪽 | Discussion and Limitations |
| 0.2쪽 | Conclusion |
| 0.4쪽 | References |
| **6.0쪽 이내** | A4 최종 PDF 기준 |

### 그림과 표

- **Fig. 1:** camera + instruction + state -> SmolVLA -> 30-step SE(2) queue -> ROS 2 command.
- **Fig. 2:** `v6r1/r2`와 `v6pv1/pv2`의 대표 trajectory 또는 segment-offset 비교.
- **Table I:** checkpoint, corpus, camera, action, rate, simulator, metric 정의.
- **Table II:** evidence ID, version, `n`, result, limitation을 한 행씩 정리.

새 결과처럼 보이는 장식용 plot은 만들지 않는다. caption에도 checkpoint와 기록된 run 수를 쓴다.

---

## 6. 용어와 문장 규칙

| 피할 표현 | 사용할 표현 |
|---|---|
| autonomous driving | simulated vehicle control |
| end-to-end/pure VLA | VLA-guided closed-loop control; executor를 구체적으로 명시 |
| robust | observed in the recorded N runs |
| semantic grounding | instruction-conditioned differentiation for the evaluated expressions |
| held-out generalization | response to two test expressions |
| zero lane touch / lane-safe | zero threshold-exceedance segments in the recorded artifact |
| data cleaning caused stability | cleaned-and-augmented lineage was associated with the recorded outcome |
| preview preserves the exact VLA path | preview derives current steering from the remaining VLA queue |
| real-time | 10-Hz command loop; latency guarantee not evaluated |
| first | 삭제 |

`SmolVLA-450M`은 프로젝트 문서의 모델 명칭을 따르되, 실제 parameter count 표기와 공식 모델
명칭은 최종 인용 시 다시 확인한다.

---

## 7. 원고 작성 순서와 완료 기준

1. 원장의 A급 artifact와 C급 문서 수치를 source와 다시 대조한다.
2. Fig. 1과 Table I처럼 결과에 의존하지 않는 시스템 부분을 먼저 작성한다.
3. Table II를 원장 ID 순서로 작성하고 각 행에 checkpoint/snapshot과 `n`을 넣는다.
4. Results는 `v6 closed loop -> v6 replay/preview -> historical diagnostics` 순서로 작성한다.
5. Discussion에서 language boundary, contamination, DAgger를 짧게 다룬다.
6. abstract와 conclusion은 본문 표가 확정된 뒤 작성한다.
7. author, funding, 공식 트랙은 공동저자 확인 전까지 placeholder로 둔다.
8. Overleaf에서 A4 페이지 크기, 6쪽 이하, unreadable table scaling 부재를 확인한다.

완료 조건:

- runtime/code diff가 이번 논문 작업으로 추가되지 않음
- 본문의 모든 숫자가 원장 ID와 source를 가짐
- 서로 다른 checkpoint 결과가 한 비교 효과로 합쳐지지 않음
- 결과 표의 각 행에 sample unit과 `n` 또는 `not recorded`가 있음
- abstract에 `first`, `safe`, `robust`, `generalization`, `real-time` 과장 표현이 없음
- 최종 PDF가 A4이며 참고문헌을 포함해 6쪽 이하
