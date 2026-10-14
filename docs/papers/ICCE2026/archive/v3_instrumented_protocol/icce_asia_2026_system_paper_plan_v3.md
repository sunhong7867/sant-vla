# ICCE-ASIA 2026 VLA 시스템 논문 연구 계획 v3

## 0. 이번 제출안의 최종 결정

| 항목 | 결정 |
|---|---|
| 학회 | IEEE/IEIE ICCE-ASIA 2026 |
| Full paper 마감 | 2026-09-04 |
| 결과 통지 | 2026-09-18 |
| 최종본 마감 | 2026-09-30 |
| 우선 트랙 | Automotive CE Applications (CEA) |
| 보조 트랙 | AIM 또는 RDA |
| 형식 | 2--6쪽, A4, 2단, 10 pt 이상 |
| 논문 성격 | 기존 GuardedLC와 독립적인 compact VLA closed-loop driving 실증 논문 |
| 공식 checkpoint | `models/ckpt_v6_60k` 하나만 사용 |
| 공식 closed-loop 표본 | 5 paired restart blocks, 총 50 rollouts |
| experiment protocol ID | `icce_v3` |
| protocol revision | v0.4, 2026-09-01 |

공식 run sheet는
[icce_asia_2026_v6_eval_matrix.csv](icce_asia_2026_v6_eval_matrix.csv)에 고정한다.
rawㆍderived field와 각 Figure/Table의 연결은
[icce_asia_2026_data_dictionary.csv](icce_asia_2026_data_dictionary.csv)에 고정한다.
이 문서보다 앞서 작성된 통합안과 semantic-suffix v2 계획은 결정 이력이며, 이번 제출의
공식 수집 protocol이 아니다.

### 작업 제목

> **Making SmolVLA Drive: Paired-Instruction Evaluation of Action-Chunk Commitment in ROS 2**

실행 commitment 결과가 명확하지 않을 때 사용할 보수적 제목:

> **Making SmolVLA Drive: Paired-Instruction Evaluation of a Compact VLA in ROS 2 Closed-Loop Control**

`Counterfactual`은 제목에서 뺀다. ICR-Drive가 이미 동일 routeㆍseed에서 instruction만 바꾸는
closed-loop counterfactual robustness 평가를 제시했기 때문이다. 본 논문에서는 필요한 곳에만
`paired instruction intervention`이라는 조작적 표현을 쓴다.

### 논문의 한 문장 질문

> 450M SmolVLA가 만든 30-step SE(2) action chunk의 언어 차이는 실제 ROS 2 폐루프 차량
> 궤적까지 전달되는가, 그리고 test paraphrase와 짧은 action commitment에서는 그 차이가
> 얼마나 보존되는가?

### 결과 수집 전 한 문장 주장 템플릿

> We instantiate a 450M SmolVLA as a 30-step SE(2) vehicle policy in an asynchronous ROS 2
> closed loop and use matched-start paired instructions to separate learned language influence,
> test-paraphrase behavior, and execution-contract effects.

수집 전에는 `2.51 m`, `0.05 m`, `0/8`을 이 문장에 넣지 않는다. 이 수치들은 서로 다른
checkpoint 또는 과거 simulator snapshot에서 나온 파일럿이다.

---

## 1. 왜 이 프레이밍으로 가는가

단순한 “SmolVLA로 자율주행을 구현했다”는 구현 보고로는 약하다. 반대로 새로운 VLA 구조나
학습 로직을 마감 직전에 추가하면 재학습ㆍ재검증 비용이 크다. 따라서 완성된 시스템을
그대로 사용하되, 논문의 중심을 다음의 **측정 가능한 질문**으로 좁힌다.

```text
같은 checkpoint + 같은 시작 상태 + 같은 policy seed
                         |
                         +-- instruction만 변경
                         |
                         v
30-step action chunk -> 실제 실행 prefix -> ROS 2 차량 궤적
```

이 구조는 기존 연구 자산을 많이 재사용하면서도 단순 데모와 구분된다.

1. 차량용 incremental SE(2) action chunk와 ROS 2 비동기 폐루프를 하나의 동결된 시스템으로
   명세한다.
2. 동일 문장 반복을 repeatability floor로 두고, 학습 문장과 두 종류의 test paraphrase를 같은 시작점에서
   비교한다.
3. 제어 로직을 바꾸지 않고 `refill_at`만 바꿔 실제 action commitment가 언어 분화와 주행
   결과에 미치는 영향을 계측한다.
4. 카메라ㆍ데이터ㆍ실행 계약에서 발견한 과거 실패는 version-scoped diagnostic case로만
   정리한다.

### 예상 기여 세 가지

1. **Vehicle embodiment case study.** SmolVLA를 30-step incremental SE(2) action policy로
   파인튜닝하고 ROS 2--Gazebo 비동기 폐루프 차량에 배치한 시스템과 실행 계약을 명세한다.
2. **Paired-instruction measurement.** 같은 시작 상태와 seed에서 상호 배타적인 두 유효 차선
   지시를 비교하고, 동일 문장 반복 floorㆍ학습 표현ㆍtest paraphrase를 분리해 보고한다.
3. **Plan-to-motion characterization.** action-index별 언어 차이, plan마다 실제 실행된 prefix,
   최종 lane occupancy를 연결해 action commitment가 언어 효과를 차량에 전달하는 범위를
   실증한다.

이는 새 model architecture나 범용 benchmark의 제안이 아니다. ICCE-ASIA의 응용ㆍ시스템
성격에 맞춘, 하나의 compact VLA deployment에 대한 재현 가능한 실증 연구다.

---

## 2. 선행연구와 주장 경계

### 2.1 직접 겹치는 연구

- [SmolVLA](https://arxiv.org/abs/2506.01844)는 450M compact VLA와 action chunk 기반
  asynchronous inference를 제안한다. 따라서 비동기 chunk 실행 자체를 기여로 주장하지 않는다.
- [ROS2SmolVLA](https://arxiv.org/abs/2608.23320)는 SmolVLA용 ROS 2 interface를 공개하고
  UR10e pick-and-place에서 검증했다. 따라서 “최초의 ROS 2 SmolVLA”라고 쓰지 않는다.
- [OpenDriveVLA](https://arxiv.org/abs/2503.23463)는 autonomous-driving VLA와 nuScenes
  open-loop planning 결과를 제시한다. 따라서 “최초의 소형 driving VLA”라고 쓰지 않는다.
- [ICR-Drive](https://arxiv.org/abs/2604.05378)는 동일 CARLA routeㆍseed에서 paraphrase,
  ambiguity, noise, misleading instruction을 비교한다. 따라서 “최초 counterfactual driving
  evaluation”이라고 쓰지 않는다.

### 2.2 남는 차별점

ICR-Drive는 같은 navigation goal을 표현하는 문장을 교란해 **robustness/invariance**를 묻는다.
본 연구의 주 대조는 서로 다른 두 유효 차선 목표가 실제로 다른 행동을 만들어야 하는
**sensitivity/differentiation**이며, 그 차이가 30-step action chunk의 어느 index에서 나타나고
executor가 실제로 그 index까지 실행했는지를 함께 측정한다.

OpenDriveVLA는 architecture와 open-loop dataset 성능이 중심이다. 본 연구는 frozen compact
policy가 ROS 2 차량 폐루프에서 보이는 plan-to-motion 전달과 deployment contract가 중심이다.

### 2.3 금지하거나 조건부로만 사용할 표현

| 표현 | 사용 여부 | 안전한 대체 표현 |
|---|---|---|
| first ROS 2 SmolVLA | 금지 | a ROS 2 vehicle embodiment of SmolVLA |
| first small driving VLA | 금지 | a compact 450M VLA adapted to vehicle control |
| first counterfactual driving evaluation | 금지 | matched-start paired-instruction evaluation |
| fully autonomous / end-to-end driving | 금지 | language-conditioned closed-loop vehicle control |
| free-form language understanding | 금지 | response within the trained expression set |
| semantic grounding | 조건부 | target-consistent instruction differentiation |
| real-time | 조건부 | 측정한 hardware와 p50/p95 latency를 함께 보고 |
| safety guarantee / lane-safe | 금지 | measured ring departure and lateral-error statistics |
| general VLA failure | 금지 | behavior of the evaluated v6 SmolVLA deployment |

`semantic grounding`은 다른 문장이 다른 궤적을 만든 것만으로 쓰지 않는다. 방향이 각 문장의
목표 차선과 일치하고, run repeatability floor보다 충분히 크며, 반복 block에서 재현될 때만 쓴다.

---

## 3. 현재 증거 장부: 무엇을 재사용하고 무엇을 다시 모으는가

| 기존 관찰 | 정확한 귀속 | 근거 상태 | 논문에서의 사용 |
|---|---|---|---|
| 406 episodes, 약 93.7K frames | v6 = v5 372 + y6o 34 | 문서 보고값; 현 checkout에 packed 원본 없음 | reported training provenance |
| 115초 주행의 ring departure 0/8 | v6-60K, 과거 simulator snapshot | 문서와 `v6r1/r2_map.json` 감사 가능 | pilot/motivation만 사용 |
| 학습 차선 문장 +2.51 m, SAME +0.05 m | v3y-40K | 문서만 있고 raw JSON 없음 | pilot; v6 결과로 쓰지 않음 |
| held-out +0.36 m, +0.06 m; speed 실패 | v3y-40K | 문서만 있음 | pilot; 최종 v6에서 재확인 |
| camera mismatch 3.8/1.8 m, matched 0.15--0.26 m | v3y-40K | 문서 기반 diagnostic | observation-contract 사례 |
| 16 episodes, 약 1,600 frames의 off-ring contamination | v4 계보 | 제거와 junction data 추가가 동시 수행됨 | confounded diagnostic 사례 |

로컬 근거:

- [v6 학습 provenance](../ver/20260805_1640_v5-demo-speed-shaping-v6.md)
- [v6 과거 평가](../ver/20260806_0140_v6-eval-demo-final.md)
- [v3y A3 언어 평가](../ver/20260804_1056_y5j-junction-pack-a3-driving.md)
- [카메라 불일치 진단](../ver/20260803_1223_camera-mismatch-resolved.md)
- [데이터 오염 진단](../ver/20260804_1830_cruise-off-ring-poison-found.md)
- [전체 파이프라인](../vla_training_comparison.md)

중요한 표현 교정:

- 과거 v6의 `0/8`은 **ring centerline에서 5 m를 넘는 영구 이탈 0/8**이다. 차선 표시 접촉
  0/8이나 safety guarantee가 아니다.
- 과거의 `2.51 m`는 v3y-40K 결과다. v6-60K의 406-episode 학습 결과와 한 문장에 합쳐
  같은 experiment처럼 쓰지 않는다.
- 데이터 오염 제거 뒤 개선은 다른 데이터 추가와 혼입되어 있으므로 controlled ablation이
  아니라 diagnostic case study다.

---

## 4. 연구 질문과 사전 판정 기준

### RQ1. 학습된 차선 지시는 실제 폐루프 궤적을 바꾸는가?

동일한 시작점ㆍcheckpointㆍseed에서 canonical inner/outer 문장만 바꾼다. 각 차선 문장을
두 번 반복해 same-instruction run repeatability floor를 얻는다.

- **단일 primary contrast:** canonical `r030`의 block별 inner/outer median signed-lateral
  separation `Delta_can`. 각 run 값은 모든 system outcome을 포함할 수 있도록 75초 run의
  마지막 30초(`t=45--75 s`) signed offset median으로 고정한다.
- secondary outcome: 15 m warm-up 이후 target-lane occupancy, lateral error p50/p95,
  ring departure.
- 성공 해석: 두 문장이 각 target lane 방향으로 일관되게 분리되고, separation이 run repeatability floor보다
  명확히 커야 한다.

### RQ2. config에서 test용으로 분리한 표현에도 같은 차선 선택이 유지되는가?

두 test paraphrase pair를 별도로 평가한다.

1. lexical: `innermost / outermost`
2. spatial description: `lane closer to the centre / edge`

현재 checkout에는 packed v6 training corpus가 없어 실제 episode-level instruction inventory를
감사할 수 없다. 수집 전 training manifest를 복구해 두 pair가 정말 비포함임을 확인한 경우에만
`held-out`이라고 쓴다. 복구하지 못하면 논문 전체에서 `two test paraphrase pairs`라고 부르고
generalization 또는 retention을 주장하지 않는다. test pair가 실패해도 결과를 삭제하지 않는다.
CSV의 `heldout_*` condition key는 기존 config와의 호환을 위한 내부 식별자일 뿐, 비포함 증거로
사용하지 않는다.

### RQ3. 짧은 action commitment가 언어 차이의 전달 범위를 바꾸는가?

제어ㆍ모델은 그대로 두고 `refill_at`만 `0.30`과 `0.93`으로 비교한다. `0.93`을 몇 초 또는
몇 action의 commitment라고 미리 단정하지 않는다. inference latency와 queue splice 때문에
각 plan의 action index가 actuator command에 기여한 범위를 lineage telemetry로 측정한다.

### RQ4. 어떤 deployment contract를 지키지 않으면 결과가 무효가 되는가?

- observation contract: 학습과 서빙 cameraㆍpreprocessing 일치
- data contract: episode label과 track invariant, off-ring tail 검사
- execution contract: action chunk lineage, max executed index, latency, underrun, watchdog 기록

RQ4의 과거 수치는 version-scoped diagnostic table에만 넣는다. v6 최종 통계표와 합치지 않는다.

### 제목ㆍ주장 gate

다음 다섯 조건이 모두 맞을 때만 제목에 `Action-Chunk Commitment`를 유지한다.

1. canonical `r030`의 paired lane separation이 same-instruction repeatability floor보다 반복적으로 크고 target
   direction과 일치한다.
2. `r093`에서 effective max executed action index 또는 suffix mass가 줄어들며 lane separation 또는 target occupancy가
   `r030`보다 일관되게 감소한다.
3. 그 차이가 watchdogㆍunderrunㆍreset 실패만으로 설명되지 않는다.
4. request snapshotㆍoffline reproductionㆍlineage coverage가 각각 99% 이상이다.
5. absolute-tick oracle의 inner/outer trajectory가 `r030/r093`에서 보존된다.

action-index별 divergence onset보다 실제 cutoff가 짧고 outcome collapse까지 연결될 때만 본문에서
`semantic suffix starvation`을 제한적으로 사용한다. 이 인과 사슬이 성립하지 않으면 보수적
제목으로 바꾸고, 결과를 commitment sensitivity가 아닌 system characterization으로 보고한다.

---

## 5. 동결할 시스템 스냅샷

### 5.1 checkpoint와 모델

| 항목 | 동결값 |
|---|---|
| checkpoint | `models/ckpt_v6_60k` |
| `model.safetensors` SHA-256 | `581773d8ac2c50a921f42930db51be31745c14909103c66910429c11c63ce562` |
| model class | SmolVLA-450M |
| action | 30 × `[dx, dy, dyaw]` incremental SE(2) |
| control rate | 10 Hz |

406 episodesㆍ93.7K frames는 checkpoint 내용에서 역산한 값이 아니라 기존 training log의 보고값임을
명시한다.

### 5.2 evaluator와 bridge

| 항목 | core 값 |
|---|---:|
| outer start pose | `(-1.49, 24.55, -1.571)` |
| inner start pose | `(-1.49, 21.396, -1.571)` |
| duration | 75 s/run |
| camera | `/camera/image_raw` |
| track mode | `replay` |
| max speed | 3.2 m/s |
| speed slew | 0.08 per tick |
| splice overlap | 5 actions |
| `refill_at` | 0.30 또는 0.93만 사용 |
| seeds / restart blocks | 0, 1, 2, 3, 4 |

문서 작성 시 HEAD는 `70d50cd20ab9514cd9c2c5e8a47216797ad47a0e`지만 working tree가
dirty이고 현재 차량 치수도 과거 v6 파일럿과 다르다. 따라서 commit hash만 저장하면 부족하다.
공식 수집 직전에 다음을 protocol 폴더에 저장한다.

- 관련 source 전체 diff와 그 SHA-256
- vehicle SDF, world, launch, bridge, server, evaluator 각각의 SHA-256
- checkpoint config와 weights hash
- ROS 2ㆍGazeboㆍCUDAㆍPyTorchㆍGPU 정보
- 모든 launch 인수와 환경변수

공식 수집을 시작한 뒤 modelㆍvehicleㆍcameraㆍpreprocessingㆍinstructionㆍmetric threshold를
바꾸면 protocol version을 올리고 영향받은 조건을 전부 다시 수집한다.

---

## 6. 최종 closed-loop 수집: 정확히 50회

5개의 독립 restart block에서 아래 10회를 수행한다. block마다 policy seed를 하나 고정하고,
모든 paired comparison은 같은 block 안에서 수행한다. 각 block 시작 시 simulator와 policy
server를 새로 시작한다. `seed`와 `refill_at`은 bridge 시작 인수이므로 **모든 run에서 bridge를
같은 절차로 재시작**하고 matrix의 값을 적용한다. 그 뒤 vehicle과 instruction queue를 지정 pose로
reset한다. 특정 조건에서만 bridge를 재시작해 process-warmth를 confound로 만들지 않는다.

outer 시작에서는 outer 지시가 stay이고 inner 지시가 transition이므로, 한 시작 pose만 쓰면
언어와 maneuver 난도가 결합된다. 이를 줄이기 위해 `B0/B2/B4`는 outer start,
`B1/B3`는 inner start를 사용한다. 5 blocks라 완전한 50:50 균형은 아니므로 start lane별 raw
결과도 함께 보이고, 결과를 범용 lane-selection accuracy로 과장하지 않는다.

각 run 시작 acceptance contract는 다음과 같다.

- fresh bridge process, `req=0`, 지정 seed/refill/camera 확인
- 빈 instruction 상태, action queue empty, pending request 없음
- cumulative `popped=0`, `underruns=0`, `watchdog_hits=0`
- vehicle poseㆍyawㆍlinear/angular velocity 허용오차 통과
- 첫 non-empty instruction 뒤 첫 policy reply의 `req=0` 확인

| family | block당 run | 5 blocks | 목적 |
|---|---:|---:|---|
| canonical inner, 동일 문장 2회 | 2 | 10 | inner repeatability floor |
| canonical outer, 동일 문장 2회 | 2 | 10 | outer repeatability floor |
| test lexical inner/outer | 2 | 10 | config-designated test lane word |
| test spatial inner/outer | 2 | 10 | config-designated test description |
| canonical inner/outer, `refill_at=0.93` | 2 | 10 | 짧은 commitment 대조 |
| **합계** | **10** | **50** | core final evaluation |

core canonical과 test-paraphrase 조건은 `refill_at=0.30`이다. 정확한 문장과 block별 실행 순서는
[icce_asia_2026_v6_eval_matrix.csv](icce_asia_2026_v6_eval_matrix.csv)에 들어 있다.

### 제목 gate용 oracle과 선택 실험

core 50회가 acceptance gate를 모두 통과하고 분석이 끝난 뒤에만 수행한다.

1. **commitment 제목을 위한 필수 oracle 8회:** `inner/outer × r030/r093 × 2 repeats`. absolute `tick`으로
   phase-locked된 deterministic ring trajectory가 두 refill에서 모두 보존되는지 확인한다.
   policy의 `r093`만 붕괴하고 oracle은 보존될 때 queue phase bug라는 대안 설명을 줄일 수 있다.
   core에서 commitment effect가 없으면 실행하지 않아도 되지만 보수적 제목을 사용한다. effect가
   있고 commitment를 제목ㆍ주결론에 쓰려면 이 8회는 필수이며 총 closed-loop 수집은 58회가 된다.
2. **우선순위 2, speed 10회:** slow/fast canonical pair를 5 blocks × 2로 추가한다.

선택 실험의 결과가 약해도 실행 사실을 숨기지 않는다. `optional experiment performed`로 기록한
뒤 보조자료 또는 limitation으로 보고한다.

### no-language와 shuffled-language를 core에서 제외한 이유

- 현재 bridge에서 빈 instruction은 queue를 flush하고 inference를 중단한다. 따라서 빈 문자열
  주행은 language ablation이 아니라 **hands-off stop**이다.
- 임의의 placeholder 문장은 no-language가 아니라 OOD instruction이다.
- 목표가 텍스트에만 주어진 현재 task에서 shuffled label은 독립된 정답 목표가 없어
  wrong-command following과 policy failure를 구분하기 어렵다.

따라서 가장 방어적인 통제군은 같은 문장을 같은 조건에서 두 번 실행한 repeatability floor다.
빈 문장이나 shuffled 조건은 이번 core 표에 넣지 않는다.

---

## 7. 모든 plan을 연결하는 request-snapshot offline replay

20개 대표 anchor만 query하면 다른 live plan에 `j*_t`를 부여할 수 없다. 따라서 50회 모든
policy request에서 **서버가 실제 받은 JPEG bytes, state, task, seed, req**를 저장한다. 전체
camera stream이 아니라 request 시점 JPEG만 비동기 writer로 저장하므로 예상 용량은 작다.
writer가 inference loop를 막지 않았는지는 smoke의 logging ON/OFF latency로 확인한다.
snapshot writer dropㆍoriginal replay mismatch는 trajectory run 자체를 사후 제외하는 이유가
아니며, plan-to-motion coverage로 별도 보고한다. coverage가 99% 미만이면 commitment 제목 gate를
통과하지 못한 것으로 처리한다.

각 accepted plan request `t`를 차량을 움직이지 않고 동일 checkpoint로 재생한다.

| query | 목적 |
|---|---|
| original instruction + original seed | 저장ㆍpreprocessing 재현 검증 |
| paired valid instruction + original seed | plan별 `D_sem,t(j)` |
| original instruction + fixed alternate seed | plan별 policy-seed action noise |

paired instruction은 condition 안에서 inner와 outer를 서로 바꾼다. alternate seed는 사전에
`1000 + policy_seed`로 고정한다. original replay가 저장된 raw action과 tolerance 안에서
재현되지 않으면 해당 request의 `j*`를 계산하지 않고 preprocessing mismatch로 표시한다.
재현 tolerance는 30×3 action 전체의 `max_abs_error <= 1e-5`로 동결한다.

30개 `[dx,dy,dyaw]`를 ego-frame trajectory로 적분하고 action index `j`마다 계산한다.

```text
D_sem,t(j)  = exact same JPEG/state/seed, paired valid instruction
D_seed,t(j) = exact same JPEG/state/instruction, alternate policy seed
```

여기서 `D_seed`는 **policy-seed action noise**다. closed-loop에서 같은 seedㆍ문장을 다시 실행한
`repeatability floor`와 다른 양이며 두 값을 같은 variability baseline으로 합치지 않는다.

`D_sem,t(j)`가 같은 condition의 pooled `D_seed(j)` 95th percentile을 3개 연속 index에서 넘는
첫 index를 `decision_onset_idx = j*_t`로 사전 정의한다. threshold를 결과를 본 뒤 바꾸지 않는다.

queue item에는 action 값과 별도로 `(source_req_id, source_action_idx, blend_weight)`의
가변-length lineage list를 태깅하고 control tick마다 기록한다. 이미 blend된 item이 다시
blend될 수 있으므로 source를 두 개로 제한하지 않는다. 숫자 action과 splice 계산은 바꾸지 않는다. 이를 통해
plan `t`가 supersede되기 전 실제 actuator command에 기여한 최대 action index와 suffix weight를
복원한다.

```text
max_executed_idx_t = plan t가 weight>0으로 기여한 최대 source_action_idx
branch_touched_t   = 1[max_executed_idx_t >= j*_t]
suffix_mass_t      = sum of plan-t blend weights for source_action_idx >= j*_t

effective_max_idx_t = cumulative contribution >= 0.5 action-equivalent인
                      가장 큰 source_action_idx
effective_branch_t  = 1[suffix_mass_t >= 0.5 action-equivalent]
```

`suffix_mass`의 단위는 action-equivalent control ticks다. 작은 blend weight 하나도 구분하기 위해
`branch_touched`는 instrumentation diagnostic으로만 남긴다. **주 execution 지표는 continuous
`suffix_mass`와 0.5 action-equivalent 기준의 `effective_max_idx/effective_branch`**다. threshold를
결과를 본 뒤 바꾸지 않는다.

lineage instrumentation을 구현하지 못하면 `branch_touched`, `suffix_mass`, semantic-starvation
인과 주장을 모두 삭제한다. 그 경우에는 두 splice 사이 control tick 수만 `inter_splice_ticks`로
보고하고, 이를 raw plan action 실행 개수라고 부르지 않는다.

offline replay 수는 실제 valid request 수에 따라 결정되며, 독립 rollout 수로 세지 않는다.
추론 통계 단위는 여전히 5 restart blocks다.

---

## 8. 허용되는 measurement-only 수정

정책, action 값, steering 계산, queue splice 규칙은 바꾸지 않는다. 공식 수집 전에 다음의
평가ㆍ기록 계층 수정만 허용한다.

1. `probe_policy_counterfactual.py`의 `idx/status/reset` 초기화가 reasoning callback 안으로 들어간
   회귀를 복구한다. plain v6에서는 reasoning topic이 오지 않으므로 현재 상태로는 실패할 수 있다.
2. evaluator에 `pair-only` 또는 `single-run` 모드를 추가해 run sheet의 정확한 50회를 실행한다.
   현재 evaluator 한 번은 `A,A,A,B` 네 rollout을 강제로 만들어 50회를 구성할 수 없다.
3. `/vla/plan`에 아래 telemetry를 추가한다. 어떤 control node도 이 필드를 구독하지 않는다.

```text
run_id, req, seed, task
obs_stamp, obs_seq
request_mono_s, splice_mono_s
tick_at_request, tick_at_splice
queue_before_splice, queue_after_splice
latency_ms
actions[30][3]
```

4. request JPEG/state를 non-blocking writer로 저장하고 pathㆍSHA-256ㆍdrop count를 plan log에 남긴다.
5. queue action에 control-neutral lineage metadata를 붙이고 tick별 source request/index/blend weight를
   기록한다. 숫자 actionㆍpop 순서ㆍblend weight 계산은 기존과 bitwise-equivalent여야 한다.
6. sidecar logger가 poseㆍcommandㆍinstructionㆍplanㆍstatus를 JSONL 또는 rosbag으로 기록하게 한다.

수정 뒤 smoke 1회를 통과하고 diff/hash를 동결한다. smoke 결과는 최종 50회에 포함하지 않는다.

measurement-neutrality smoke도 사전에 통과해야 한다.

- deterministic stub에서 lineage OFF/ON의 numeric queue action과 `/cmd_vel` sequence가 동일
- request snapshot logging ON의 inference p95가 OFF 대비 5% 넘게 증가하지 않음
- 모든 lineage list의 weight 합이 `1 +/- 1e-6`
- snapshot writer drop 0

### rosbag sidecar 권장 토픽

```text
/clock
/vla/instruction
/vla/plan
/vla/status
/cmd_vel
/odom
/world/default/dynamic_pose/info
```

전체 camera topic을 rosbag으로 저장할 필요는 없다. 대신 server가 실제 받은 request JPEG만
비동기로 저장한다.

---

## 9. 데이터 폴더와 run acceptance

### 9.1 폴더 구조

```text
eval_out/icce_asia2026_v3/
  protocol/
    v6_eval_matrix.csv
    source.diff
    hashes.txt
    environment.txt
    instructions_snapshot.json
    protocol.yaml
  raw/
    B0_01_can_inner_r1/
      manifest.json
      pose.jsonl
      cmd.jsonl
      plan.jsonl
      status.jsonl
      sim.log
      server.log
      bridge.log
    ...
  requests/
    request_manifest.csv
    images/
    original_actions.jsonl
    replay_queries.jsonl
  derived/
    run_summary.csv
    paired_summary.csv
    chunk_profile.csv
    exclusions.csv
  figures/
```

기존 `ring_map_probe.sh`처럼 같은 prefix를 재사용해 JSON을 덮어쓰지 않는다. `run_id`는 matrix의
고유값을 그대로 쓴다.

### 9.2 infrastructure acceptance gate

다음만 invalid run의 사전 정의된 이유다.

- checkpointㆍsourceㆍcamera hash 불일치
- reset 실패 또는 시작 pose 허용오차 초과
- start velocity, empty-queue, pending-request 또는 first-`req=0` contract 실패
- camera/pose/command stream 자체가 뜨지 않음
- ghost `/cmd_vel` publisher 또는 다른 controller 동시 실행
- evaluator crash, 파일 누락, 지정 duration 전에 simulator 종료

watchdog, underrun, 정지, 이탈, 짧은 이동은 model/system outcome이므로 임의로 제외하지 않는다.
invalid run은 같은 `run_id`에 attempt 번호를 붙여 재실행하고, 실패 attempt도 `exclusions.csv`에
남긴다.

---

## 10. 최종 지표와 통계 단위

### 10.1 trajectory 처리

ring centerline에 각 pose를 투영해 progress `s`와 signed lateral offset `l`을 얻는다.
각 block의 시작 lane은 matrix로 고정하며 첫 15 m는 stay/transition 공통 warm-up으로 제외한다.
15 m에 도달하지 못한 run도 마지막 30초 pose로 primary separation을 계산하며
`non_progress=1`, target-lane occupancy `0`으로 처리한다. post-warm-up lateral p50/p95는 `NA`로
남기고 non-progress count를 Table II에 별도 보고한다.

| 지표 | 정의 | 역할 |
|---|---|---|
| paired lane separation | 마지막 30초 median offset 기반 canonical `Delta_can` | **single primary** |
| target-lane occupancy | warm-up 뒤 target lane centerline에 더 가까운 sample 비율 | secondary |
| run repeatability floor | 같은 seed/lane 반복 두 run의 median offset 차이 | control |
| lateral error p50/p95/max | target lane centerline까지 거리 | tracking quality |
| progress at 75 s | unwrapped ring arclength | speed/schedule |
| ring departure | ring centerline 거리 > 5 m 여부와 지속시간 | gross failure |
| full-lap completion | unwrapped progress ≥ 한 바퀴 길이 | stability |

기존 multi-lap world-coordinate Fréchet 값은 phase 차이에 크게 부풀 수 있으므로 주 지표로 쓰지
않는다. 필요하면 progress-aligned trajectory distance만 보조로 사용한다.

### 10.2 runtime 지표

- inference latency p50/p95/max
- plan interval과 observation age p50/p95
- lineage 기반 max executed action index와 suffix mass 분포
- underrun percentage와 watchdog hits
- queue length at request/splice

`real-time`이라는 표현은 hardware와 p95 latency, deadline miss를 함께 보고할 수 있을 때만 쓴다.

### 10.3 통계 보고

- 독립 단위는 frame이 아니라 5 restart blocks다.
- 각 figure에 block별 raw dot을 모두 표시한다.
- 이 연구를 `n=5` descriptive case study로 명시하고 medianㆍrangeㆍpaired block difference를 보고한다.
- frame 수를 표본 수처럼 사용한 작은 p-value를 만들지 않는다.
- inferential p-value나 불안정한 95% bootstrap CI를 주결론으로 사용하지 않는다.

### 10.4 핵심 파생값

각 block `b`에서 run 마지막 30초의 median signed offset을 `m`이라 할 때 다음을 고정한다.

```text
m_in,b  = (m_inner_R1,b + m_inner_R2,b) / 2
m_out,b = (m_outer_R1,b + m_outer_R2,b) / 2

Delta_can,b = abs(m_out,b - m_in,b)                         # primary
F_in,b      = abs(m_inner_R1,b - m_inner_R2,b)
F_out,b     = abs(m_outer_R1,b - m_outer_R2,b)
F_repeat,b  = (F_in,b + F_out,b) / 2
Excess_b    = Delta_can,b - F_repeat,b

Delta_commit,b = Delta_can,b - abs(m_outer_r093,b - m_inner_r093,b)
Test_gap,b      = Delta_can,b - Delta_test_pair,b
```

signed direction도 함께 검사해 inner/outer label과 일치하는지 보고한다. 작은 denominator에서
폭발하는 ratio는 주지표로 사용하지 않는다.

---

## 11. 그래프와 표를 바로 만들기 위한 데이터 설계

### Figure 1. 시스템과 paired evaluation

```text
camera + [speed,yaw-rate,steer] + instruction
                  |
                  v
             SmolVLA-450M
                  |
          30 x [dx,dy,dyaw]
                  |
     async queue/splice/executor -----> cmd_vel -----> Gazebo vehicle
                  |
        plan/status telemetry
```

그림에는 “language only intervention”, action-index `j*`, plan/action lineage와 실제 실행
cutoff를 함께 표시한다.

### Figure 2. 언어가 만든 폐루프 궤적

세 panel로 제한한다.

1. canonical `r030`: inner/outer와 same-run 반복
2. test lexical/spatial: 목표 차선 reference와 함께 표시
3. canonical `r093`: 짧은 commitment에서의 변화

한두 개 예시만 고르지 말고 5 blocks 전부를 얇은 선으로, block median을 굵은 선으로 그린다.

### Figure 3. plan-to-motion 연결

- 왼쪽: action index별 `D_sem(j)`와 `D_seed(j)` ribbon, `j*` 표시
- 오른쪽: `r030/r093`의 `effective_max_idx`, `suffix_mass`, plan별 `j*`를 함께 표시

이 그림이 강하면 action-commitment 제목을 유지한다. 두 분포가 겹치지 않거나 closed-loop
outcome과 연결되지 않으면 이 그림을 과장하지 않는다.

### Table I. 시스템ㆍ학습 명세

- model 450M, v6 checkpoint/hash
- reported 406 episodes / ~93.7K frames
- observation 1 front camera + 3D state + English instruction
- 30-step incremental SE(2), 10 Hz
- ROS 2/ZMQ async serving, GPU, measured p50/p95 latency

### Table II. 동일 v6 최종 결과

행은 `canonical-r030`, `test-lexical`, `test-spatial`, `canonical-r093` 네 개만 둔다.
열은 paired separation, repeatability floor, target occupancy, lateral p95, departure, progress,
runtime validity다.

### Table III 또는 discussion box. Deployment contracts

| contract | 관찰 | 증거 등급 | 논문 표현 |
|---|---|---|---|
| observation | camera 불일치 시 큰 편향 | v3y diagnostic | version-scoped case |
| data | 약 2% off-ring tail 발견 | confounded diagnostic | audit lesson, not ablation |
| execution | commitmentㆍqueueㆍlatency | current v6 controlled/telemetry | final experiment |

6쪽이 부족하면 Table III를 discussion의 세 문장으로 압축한다.

---

## 12. 6쪽 논문 구성

| 분량 | 내용 |
|---:|---|
| 0.7쪽 | 문제, gap, 기여 3개 |
| 0.6쪽 | SmolVLA/ROS2SmolVLA/driving VLA/ICR-Drive 관련연구 |
| 1.0쪽 | data, 30-step SE(2), ROS 2 async system |
| 1.0쪽 | paired protocol, contracts, metrics |
| 1.7쪽 | 50-rollout 결과 + offline chunk profile |
| 0.7쪽 | diagnostic lessons, limitations |
| 0.3쪽 | 결론 |

limitations에는 다음을 명시한다.

- simulator 한 개, track 한 개, checkpoint 한 개
- training provenance의 packed raw dataset이 현 checkout에는 없음
- test paraphrase는 각 family 한 쌍이며 training inventory를 복구한 경우에만 held-out이라 부름
- 과거 camera/data 사례는 서로 다른 version의 diagnostic이고 current v6 통계와 합치지 않음
- collision avoidance, destination reasoning, 실차 safety는 평가하지 않음

---

## 13. 9월 1--4일 실행 일정

### 9월 1일

- 이 protocol과 50-run matrix 동결
- evaluator initializer와 single-run mode 수정
- request snapshotㆍrecursive lineageㆍbehavior-neutral telemetry와 sidecar logger 준비
- smoke 1회, output acceptance 자동 검사
- source/checkpoint/environment hash 저장

### 9월 2일

- 5 restart blocks × 10 = 50 closed-loop rollouts 수집
- block이 끝날 때마다 파일 수ㆍdurationㆍresetㆍtopicㆍhash 검사
- 모든 accepted plan request를 original/paired/alternate-seed로 offline replay
- 실패 run은 사전 정의된 infrastructure 사유일 때만 재실행

### 9월 3일

- `run_summary.csv`, `paired_summary.csv`, `chunk_profile.csv` 생성
- Figure 1--3, Table I--II 완성
- 제목 gate 판단
- 6쪽 초안 완성, 주장마다 checkpoint/version 확인

### 9월 4일

- 오전에 공동저자 검토와 수치 역추적
- 템플릿ㆍ페이지 수ㆍ참고문헌ㆍ익명화/저자 규칙 확인
- PDF 시각 검사 후 가능하면 마감 시각보다 앞서 제출

---

## 14. 중단 규칙과 최종 체크리스트

### 수집 중단 규칙

- smoke에서 reset 또는 plain-v6 evaluator가 실패하면 50회를 시작하지 않는다.
- source/hash가 바뀌면 같은 protocol id 아래 이어서 수집하지 않는다.
- 한 condition의 결과를 본 뒤 문장ㆍthresholdㆍduration을 바꾸지 않는다.
- 좋은 run만 남기거나 실패 run을 infrastructure failure로 재분류하지 않는다.

### 논문 수치 체크

- [ ] 모든 최종 수치는 v6 protocol v0.4의 raw run으로 역추적 가능
- [ ] v3y의 2.51/0.05/0.36/0.06을 v6 결과처럼 쓰지 않음
- [ ] 0/8을 lane violation이나 safety로 표현하지 않음
- [ ] 406/93.7K는 reported provenance라고 명시
- [ ] data contamination은 controlled ablation으로 표현하지 않음
- [ ] frame을 독립 표본으로 세지 않음
- [ ] latency p50/p95, underrun, watchdog을 함께 보고
- [ ] no-language라는 잘못된 이름을 쓰지 않음
- [ ] first/fully autonomous/generalization/safety guarantee 표현 제거

### 최종 초록 수치 문장 템플릿

```text
Across five matched restart blocks (50 closed-loop rollouts), trained inner/outer
instructions produced [X] m of paired lateral separation relative to a [Y] m
same-instruction repeatability floor, with target-lane occupancy of [A/B]%. Two test
paraphrase pairs changed paired separation by [C/D] m. Increasing
the refill threshold reduced the median effective maximum executed action index from [E] to [F]
and changed paired separation by [G] m, while runtime validity was [H].
```

대괄호는 50회 수집 뒤에만 채운다. 기대와 다른 값도 그대로 보고한다.
