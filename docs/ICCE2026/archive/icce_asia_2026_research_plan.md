# ICCE-ASIA 2026 연구 진행 계획 (대체된 v0.1)

> **상태: 2026-09-01에 대체됨.** 공식 수집에는 이 문서나 v2 계획이 아니라
> [ICCE-ASIA 2026 VLA 시스템 논문 연구 계획 v3](../icce_asia_2026_system_paper_plan_v3.md)와
> [v6 50-run matrix](../icce_asia_2026_v6_eval_matrix.csv)를 사용한다.
> 아래 내용은 결정 이력을 보존하기 위한 이전 통합안이다.

## 0. 문서 상태

| 항목 | 내용 |
|---|---|
| 학회 | IEEE/IEIE ICCE-ASIA 2026 |
| Full paper 마감 | 2026-09-04 |
| 결과 통지 | 2026-09-18 |
| 최종본 마감 | 2026-09-30 |
| 우선 트랙 | Automotive CE Applications (CEA) |
| 보조 트랙 | AIM 또는 RDA |
| 논문 길이 | 2--6쪽, A4, 2단, 10 pt 이상 |
| 문서 버전 | Protocol v0.1, 2026-09-01 |
| 현재 단계 | 파일럿 근거 확인 완료, 공식 재수집 전 |

이 문서는 과거의 성공 사례를 정리하는 회고가 아니라, 2026-09-04 제출 논문을 위한
**사전 실험 계획**이다. 아래에서 `pilot`으로 표시한 수치는 동기와 실험 설계에만 사용하며,
동일한 체크포인트ㆍ코드 스냅샷ㆍ평가 조건으로 다시 수집하기 전에는 본문 최종 결과표에
합치지 않는다.

관련 조건표는 [icce_asia_2026_experiment_matrix.csv](icce_asia_2026_experiment_matrix.csv)에
기계가 읽을 수 있는 형태로 함께 고정한다.

---

## 1. 이번 논문의 결정

### 1.1 작업 제목

> **Too Frequent to Follow: Preventing Semantic Decision Starvation in Chunked Vision--Language--Action Driving**

### 1.2 한 문장 주장

비동기 VLA를 너무 자주 재계획하면 action chunk 후반의 언어 조건 분기를 실행하기 전에
새 chunk로 교체되어 공통 prefix만 반복할 수 있으며, 충분한 commitment와 남은 queue의
기하를 이용하는 preview 실행을 결합하면 목표 선택과 차선 추종을 함께 보존할 수 있다.

인과 관계는 두 단계로 제한한다. **긴 commitment가 starvation을 피하고, preview는 그 긴
commitment에서 생기는 tracking cost를 줄인다.** Preview가 semantic starvation 자체를
해결한다고 주장하지 않는다.

### 1.3 핵심 용어

**Semantic decision starvation**은 서로 다른 지시가 만든 action chunk들이 초반에는 같은
경로를 공유하고 후반에서 갈라질 때, 실행기가 그 분기 이전까지만 반복 실행하여 언어가
선택한 행동이 실제 차량에 전달되지 않는 현상이다.

이 이름은 관찰할 현상을 가리키기 위한 작업 용어다. 선행연구 전체를 검토하기 전까지
“최초 발견”이라고 쓰지 않는다.

### 1.4 연구 질문

- **RQ1.** commitment가 짧아질수록 언어별 목표 선택 정확도가 감소하는가?
- **RQ2.** 그 감소는 지시별 chunk가 갈라지는 decision onset보다 먼저 chunk가 교체되는
  경우에 집중되는가?
- **RQ3.** 의미 분기에 충분한 commitment를 유지할 때, queue-preview 실행이 raw replay보다
  현재 차량 치수 기준의 경계 초과와 횡오차를 줄이는가?
- **RQ4.** preview가 목표 선택을 보존하면서 안전성만 개선하는가, 아니면 정책의 의도를
  바꾸는가?

### 1.5 검증할 가설

- **H1:** `refill_at=0.3`의 target-selection accuracy가 `0.93`보다 높다.
- **H2:** instruction-paired first chunk의 누적 SE(2) 경로 차이는 공통 prefix 뒤에서 커진다.
- **H3:** `preview`, `curv_boost=1.0`, speed cap OFF가 `replay`보다 corner-exit steering
  unwind lag와 횡오차 p95를 낮춘다.
- **H4:** `preview + curv_slow_alat=0.8`은 preview-only보다 추가 안전 여유를 주지만,
  이는 VLA 자체 성능이 아니라 별도의 물리 safety envelope로 분리된다.

---

## 2. GuardedLC와의 범위 경계

기존 GuardedLC의 연구 경계는 다음과 같다.

```text
passenger utterance -> symbolic intent -> rule/LLM gate -> ROS 2 command
```

새 논문의 연구 경계는 그 다음 단계다.

```text
image + language + state -> 30-step action chunk -> queue/executor -> vehicle trajectory
```

따라서 다음 항목은 새 논문의 기여로 다시 주장하지 않는다.

- rule-first LLM routing
- refusal/OOS interception
- LC-Utt v1.0 자체
- 44% LLM 호출률 또는 GuardedLC의 latency 개선
- GuardedLC의 L1/L2 rescue gap
- 기존 GuardedLC pipelineㆍPareto figureㆍL1/L2 표의 재포장

GuardedLC는 “승객 발화를 어떤 typed command로 허가할 것인가”를 다뤘고, 본 논문은
“이미 조건화된 VLA의 계획 중 어느 부분이 실제 연속 제어에 살아남는가”를 다룬다.

---

## 3. 현재 확보된 근거와 정직한 한계

### 3.1 파일럿 근거

| 관찰 | 파일럿 결과 | 출처 | 공식 결과로 재사용 여부 |
|---|---:|---|---|
| v2b parking, `refill_at=0.93` | 모든 trial이 한 endpoint로 붕괴 | `docs/ver/20260730_0910_bay-diagonal.md` | 재수집 필요 |
| v2b parking, `refill_at=0.7` | bay2/3만 정답 | 같은 문서 | 재수집 필요 |
| v2b parking, `refill_at=0.3` | commanded bay `8/8` | 같은 문서 | 재수집 필요 |
| v6 ring, replay + fast | legacy 0.70 m 초과 구간 8개 | `docs/vla_lane_keeping_ablation.md` | 재수집 필요 |
| v6 ring, preview + normal | legacy 0.70 m 초과 구간 1개 | 같은 문서 | 재수집 필요 |
| v6 ring, preview + speed cap | legacy 0.70 m 초과 구간 0개 | 같은 문서 | 재수집 필요 |
| counterfactual corpus | 264 episodes, 263 valid, 329 pairs | `docs/ver/20260729_1856_corpus-v2-complete.md` | method 설계에 사용 가능 |

파일럿의 방향성은 강하지만 반복 수, 체크포인트, 속도 문구와 executor 조건이 서로 다르다.
따라서 서로 다른 과거 표의 수치를 한 표에 합쳐 통계 검정을 하지 않는다.

### 3.2 체크포인트 상태

- `models/ckpt_v6_60k`: 로컬에 존재. ring executor 실험에 사용한다.
- `models/ckpt_v8g_60k`: 로컬에 존재하지만 본 논문의 공식 실험에는 사용하지 않는다.
- v2b 40K parking checkpoint: 로컬에는 없지만 학습 서버에 존재함을 확인했다.
  - 원격 경로:
    `/home/autolab_sw/sunhong/nav-vla/runs/navvla_smolvla_v2b/checkpoints/040000/pretrained_model`
  - 크기: 약 865 MB
  - `model.safetensors` SHA-256:
    `86deaa0ac5b90a901512f64268a2c0a483ecd44c27b53b46efd32e6a1af484ac`
- v6 60K `model.safetensors` SHA-256:
  `581773d8ac2c50a921f42930db51be31745c14909103c66910429c11c63ce562`

공식 수집 전에 다음처럼 로컬 복사본을 만든 뒤 해시를 다시 확인한다.

```bash
rsync -a \
  autolab_sw@115.145.211.157:~/sunhong/nav-vla/runs/navvla_smolvla_v2b/checkpoints/040000/pretrained_model/ \
  models/ckpt_v2b_40k/
sha256sum models/ckpt_v2b_40k/model.safetensors
```

### 3.3 현재 실행 스냅샷

문서 작성 시점의 HEAD는 `70d50cd20ab9514cd9c2c5e8a47216797ad47a0e`지만 working tree가
dirty이므로 이 hash만으로는 실행 환경을 재현할 수 없다. 특히 현재 simulator vehicle은
8월 7일 파일럿과 다르다.

| 항목 | 현재 working tree |
|---|---:|
| Prius mesh scale | 0.0085 |
| chassis collision width | 약 1.49 m |
| wheel separation | 1.3345 m |
| wheel radius | 0.2657525 m |
| 차선 중심 간격/폭 근사 | 3.16 m |
| 축소 차량의 정렬 상태 중심-offset 여유 | 약 0.835 m |

8월 7일의 original-scale 차량, single-window preview 결과와 현재 축소 차량 결과를 한 통계표에
합치지 않는다. 이번 논문은 **현재 스냅샷에서 모든 조건을 재수집**하며, preview는
`preview_dual=false`인 single-window 방법으로 명시적으로 고정한다.

### 3.4 현재 평가 하네스 blocker

현재 working tree의 `src/nav_vla_pkg/scripts/probe_policy_counterfactual.py`에서
`idx`, `status`, `reset` 초기화가 `_reasoning_cb()` 내부로 들어가 있다. reasoning을 내보내지
않는 plain v6 checkpoint에서는 callback이 호출되지 않으므로 `ring_map_probe.sh`가 실행 전에
실패할 수 있다.

이것은 VLA 또는 제어 로직 문제가 아니라 **평가 하네스 회귀**다. 현재 사용자 변경을
덮어쓰지 않기 위해 이 문서 작성 시점에는 수정하지 않았다. 공식 수집은 다음을 만족한 뒤에만
시작한다.

1. 평가 전용 initializer 위치를 복구한다.
2. plain v6 checkpoint로 smoke map 1개를 만든다.
3. map JSON acceptance gate와 reset 로그 검사를 통과한다.

### 3.5 기존 산출물의 품질 주의

- 기존 `eval_out`의 map JSON 44개 중 일부는 0--1 row만 가진 불완전 파일이다.
- 파일이 존재한다는 사실만으로 성공 처리하지 않는다.
- `geometric_lane_check.py`의 순간 최대값에는 공통 시작점 artifact가 포함될 수 있다.
- 이 도구의 0.70 m threshold는 original-scale 차량용 legacy 값이다. 현재 0.85-scale 차량의
  물리 여유는 약 0.835 m이므로, 0.70 m 결과를 실제 “lane touch”라고 부르지 않는다.
- v2b의 미세 creep 때문에 기존 `correct` 필드는 target selection뿐 아니라 정지까지 섞는다.

따라서 semantic commitment의 **주 지표는 `reached == commanded`**로 두고, `in_bay`와
`stopped`는 별도 열로 보고한다.

---

## 4. 변경 동결 원칙

공식 실험을 시작한 뒤에는 다음을 변경하지 않는다.

- policy checkpoint와 checkpoint contents
- camera topicㆍpreprocessingㆍstate ordering
- action chunk 길이와 control rate
- `splice_overlap`
- bay geometry와 physical-boundary threshold
- instruction 문장
- reset pose와 timeout
- 성공/실패 판정 기준
- 선택한 seed 목록

허용되는 변경은 다음 세 종류뿐이다.

1. 평가 하네스의 명백한 crash 수정
2. control path가 구독하지 않는 sidecar logging
3. raw data를 읽기만 하는 분석/그림 생성 코드

공식 수집 중 위 항목이라도 바뀌면 protocol version을 올리고 영향받은 **모든 조건을
처음부터 다시 수집**한다. 좋은 결과가 나온 조건만 재실행하거나 파라미터를 사후 조정하지
않는다.

---

## 5. 데이터 수집 설계

### 5.1 원칙: 제어 로직이 아니라 sidecar를 추가한다

현재 bridge는 이미 다음 telemetry를 publish한다.

- `/vla/plan`: model이 보낸 raw action chunk와 publish monotonic time
- `/vla/status`: queue length, chunk count, 평균 latency, underrun, watchdog count
- `/cmd_vel`: 최종 차량 명령
- `/odom`: 속도와 pose
- `/vla/instruction`: 해당 trial의 원문 지시
- `/world/default/dynamic_pose/info`: simulator world trajectory
- `/clock`: simulator time

따라서 핵심 실험에는 policy, bridge 또는 controller 계산식을 추가할 필요가 없다. 각 조건의
probe와 동시에 다음 topic만 rosbag sidecar로 기록한다.

```bash
ros2 bag record -o <RUN_DIR>/rosbag2 \
  /clock \
  /vla/instruction \
  /vla/plan \
  /vla/status \
  /cmd_vel \
  /odom \
  /world/default/dynamic_pose/info
```

전체 image topic은 저장량이 크고 본 논문의 정량 그림에 필요하지 않으므로 공식 전체 run에는
기록하지 않는다. 논문 qualitative figure용으로 조건별 대표 1회만 camera를 별도 기록한다.

#### 권장 telemetry-only instrumentation

논문의 핵심은 “몇 번째 action까지 실행된 뒤 새 plan으로 교체됐는가”이므로 timestamp 근사보다
정확한 counter가 좋다. control calculation은 그대로 두고 `/vla/plan`과 `/vla/status` JSON에
다음 key만 추가하는 것은 허용한다.

- `/vla/plan`: `req`, `tick_at_request`, `tick_at_splice`, `queue_before_splice`,
  `queue_after_splice`, `latency_ms`
- `/vla/status`: raw `popped`, raw `underruns`, `watchdog_hits`

어떤 control node도 `/vla/plan`을 구독해 행동을 바꾸지 않으므로 이는 behavior-neutral
instrumentation이다. 추가한다면 S0 이전에 끝내고 code snapshot에 포함하며, publish overhead가
control rate와 inference latency를 바꾸지 않는지 smoke에서 확인한다. 시간이 부족하면 코드를
건드리지 않고 기존 plan timestamp와 rosbag을 사용하되, 논문에는 measured interval이라고만
표현하고 정확한 executed-action count라고 쓰지 않는다.

### 5.2 세 단계 데이터 계층

```text
eval_out/icce_asia2026/
  protocol/
    experiment_matrix.csv
    git_head.txt
    git_status.txt
    code_snapshot.diff
    environment.txt
    artifacts_sha256.txt
  raw/
    S2_commit/<condition>/seed00/
      metadata.json
      bay_confusion.json
      probe.log
      bridge.log
      serve.log
      sim.log
      bridge_params.yaml
      rosbag2/
    S3_executor/<condition>/seed00/
      metadata.json
      run_map.json
      run_probe.log
      run_bridge.log
      run_serve.log
      run_sim.log
      bridge_params.yaml
      rosbag2/
  derived/
    run_metrics.csv
    chunk_step_metrics.csv
    lane_segment_metrics.csv
    exclusions.csv
  figures/
  tables/
```

- `raw/`는 생성 후 수정하지 않는다.
- `derived/`, `figures/`, `tables/`는 raw에서 언제든 재생성할 수 있어야 한다.
- invalid run도 삭제하지 않고 `exclusions.csv`에 이유와 재실행 run ID를 남긴다.

### 5.3 run ID

다음 형식을 사용한다.

```text
<study>_<condition>_seed<NN>_<YYYYMMDDTHHMMSSKST>
```

예:

```text
S2_r030_replay_seed02_20260902T031500KST
S3_preview_cap_normal_seed01_20260903T011000KST
```

`r01`처럼 refill과 repetition을 혼동할 수 있는 이름은 사용하지 않는다. 같은 prefix를 다시
사용하면 기존 로그가 덮어써질 수 있으므로 timestamp를 항상 붙인다.

### 5.4 trial 단위 manifest 필드

최종 `derived/run_metrics.csv`에는 적어도 다음 열이 있어야 한다.

#### Provenance

- `run_id`, `study_id`, `condition_id`, `timestamp_kst`
- `git_head`, `protocol_version`, `dirty_worktree`
- `checkpoint_name`, `checkpoint_sha256`
- `gpu_name`, `ros_distro`, `gazebo_version`
- `full_command`, `bridge_params_path`, `raw_artifact_dir`

#### 고정/조작 변수

- `seed`, `repeat`, `instruction_id`, `instruction_text`
- `start_x`, `start_y`, `start_yaw`
- `chunk_len`, `rate_hz`, `refill_at`, `splice_overlap`
- `track_mode`, `preview_dual`
- `curv_slow_alat`, `curv_boost`, `speed_scale`, `speed_slew`
- `commanded_target`, `commanded_lane`, `speed_word`

#### 결과 변수

- `target_reached`, `target_correct`, `endpoint_error_m`
- `in_bay`, `stopped`, `stop_time_s`
- `d_shape_m`, `same_instruction_floor_m`, `shared_prefix_m`
- `ring_completed`, `departure`
- `aligned_margin_m`, `any_aligned_margin_exceedance`,
  `aligned_margin_exceeding_segment_count`
- `any_footprint_boundary_overlap` (pose yaw까지 확보된 경우)
- `legacy_070_segment_count`
- `abs_lateral_median`, `abs_lateral_p95`, `abs_lateral_max`
- `mean_speed_mps`, `speed_p95_mps`, `jerk_rms`
- `chunk_count`, `plan_interval_median_s`
- `latency_mean_ms`, `latency_p95_ms`
- `underrun_pct`, `watchdog_hits`
- `valid`, `exclusion_reason`, `replacement_run_id`

현재 `/vla/status`의 `latency_ms`는 running mean이며 p95가 아니다. per-request latency p95는
server가 정상 종료될 때 출력하는 summary 또는 sidecar가 요청/응답 시각을 읽어 계산한다.
이를 얻기 위해 action 또는 control 계산을 바꾸지 않는다.

### 5.5 수집 하네스에만 허용할 최소 작업

새 policy나 controller 기능을 만들지 않고, evaluator/wrapper에 다음 lifecycle만 보강한다.

1. run directory와 `metadata.json`을 먼저 만들고, 이미 같은 run ID가 있으면 실패한다.
2. simulatorㆍserverㆍbridge가 준비된 뒤 rosbag sidecar를 시작한다.
3. probe 시작 전에 `/vla_bridge` parameter dump를 저장한다.
4. probe 종료 코드를 기록하고 rosbag에는 `SIGINT`를 보내 index를 정상 마감한다.
5. 가능하면 model server에도 `SIGINT`를 보내 latency summary를 보존한다.
6. acceptance gate를 자동 실행하되 raw 파일은 수정하거나 삭제하지 않는다.

이는 행동 경로를 바꾸지 않는 **수집 전용 변경**이다. 이 보강도 S0 전에 끝내고 이후에는
동결한다. 시간이 부족하면 별도 orchestration wrapper 하나만 추가하고 기존 policy, bridge,
controller 파일은 수정하지 않는다.

---

## 6. 공식 실험 매트릭스

### 6.1 S0: preflight gate

#### S0-A. v2b 복원 및 bay smoke

- checkpoint: `models/ckpt_v2b_40k`
- bridge: `track_mode=replay`, `refill_at=0.3`, 모든 shaping OFF
- seed: 0
- canonical bay1--bay4 각 1회
- 요구조건:
  - reset error 0
  - pose 누락 0
  - commanded target 기준 3/4 이상
  - checkpoint hash 일치

정지 실패는 smoke blocker로 사용하지 않는다. v2b에 이미 알려진 creep와 semantic target
selection을 분리하기 위해서다.

#### S0-B. v6 ring smoke

- checkpoint: `models/ckpt_v6_60k`
- bridge: `track_mode=preview`, `refill_at=0.3`, `curv_slow_alat=0`,
  `curv_boost=1.0`, `preview_dual=false`
- speed phrase: `normal`
- 요구조건:
  - map JSON 2 rows
  - 각 trajectory point 5개 이상
  - reset failure와 `too few points` 없음
  - ring departure 없음

S0-B가 실패하면 본 수집 전에 평가 하네스만 수리한다. 실험 결과를 좋게 만들기 위한 bridge
파라미터 수정은 하지 않는다.

### 6.2 S1: instruction-conditioned chunk decision profile

별도 주행을 추가하지 않고 S2의 rosbag에서 각 trial의 첫 `/vla/plan`을 추출한다. 주 분석에는
`r030`의 instruction/seed별 첫 plan 하나만 사용해 세 refill 조건을 중복 표본으로 세지 않는다.
`r070`과 `r093`의 첫 plan은 refill 설정이 최초 policy output을 바꾸지 않았는지 확인하는
consistency check로만 쓴다.

1. 동일 reset poseㆍseed에서 bay1--bay4 instruction의 첫 30-step raw chunk를 얻는다.
2. 각 chunk의 `(dx, dy, dyaw)`를 누적해 ego-frame SE(2) path를 만든다.
3. instruction pair별 step-wise path distance를 계산한다.
4. `D_sem(j)`는 같은 image/state/seed에서 문장만 바꾼 step `j`의 action/누적 경로 차이로
   정의한다.
5. `D_noise(j)`는 같은 문장, 다른 seed의 차이로 정의하고 95th percentile을 noise
   threshold로 둔다.
6. `D_sem(j)`가 noise threshold를 **3개 연속 step** 넘는 첫 위치를
   `decision_onset_idx`로 기록한다.

산출물:

- `derived/chunk_step_metrics.csv`
- **Fig. 1a:** bay별 first-chunk 누적 경로 overlay
- **Fig. 1b:** action index별 paired divergence와 commitment horizon 수직선

주의: first chunk 한 개만 골라 예시로 주장하지 않는다. seed별 profile과 same-instruction
noise band를 함께 제시한다.

### 6.3 S2: semantic commitment sweep

고정 조건:

- checkpoint: v2b 40K
- `track_mode=replay`
- chunk length 30, control 10 Hz
- `curv_slow_alat=0`, `curv_boost=1.0`, `speed_scale=1.0`
- canonical bay1--bay4 문장
- reset pose `(-12.30, -22.16, 1.112)`
- seed `0,1,2,3,4`

조작 변수:

| condition | `refill_at` | nominal observation | trials |
|---|---:|---|---:|
| r093 | 0.93 | very short commitment | 4 bays x 5 seeds = 20 |
| r070 | 0.70 | short commitment | 20 |
| r030 | 0.30 | long commitment | 20 |

명목상 commitment step/seconds만 표에 쓰지 않는다. 비동기 inference와 splice 때문에 실제
교체 간격이 달라질 수 있으므로 `/vla/plan` timestamp에서 measured plan interval을 함께
보고한다.

주 지표:

1. `target_accuracy = mean(reached == commanded)`
2. 4x4 commanded-to-reached confusion matrix
3. endpoint error
4. plan interval과 decision onset의 관계

보조 지표:

- in-bay rate
- stop rate와 stop time
- underrun, watchdog, inference latency

`fully correct = target + in_bay + stopped`는 stopping skill을 함께 재므로 semantic starvation의
주 지표로 사용하지 않는다.

### 6.4 S2-O: oracle replay sanity control

`refill_at` 효과가 queue/bridge 자체의 phase bug인지, 매번 다시 예측된 VLA chunk의 shared
prefix 때문인지 분리한다.

- 기존 `stub_policy_server.py --mode replay` 사용
- canonical slow 문장과 일치하는 parking oracle episode를 각각 복원
  - bay1: `data/packed_v2_parking/corpus_v2_train__ep_0041`
  - bay4: `data/packed_v2_parking/corpus_v2_train_b__ep_0012`
- `refill_at=0.93`과 `0.30`
- 각 cell reset 3회: 2 bays x 2 refill x 3 = 12 rollouts
- S2에서 측정한 v2b median latency를 `--latency-ms`에 넣어 serving 조건을 맞춤

stub은 request의 absolute `tick`으로 기록 action을 이어서 내보낸다. oracle replay도
refill에 따라 무너지면 semantic starvation이라는 인과 주장을 중단하고, 결과를 bridge
refill sensitivity로 낮춰 표현한다.

두 episode는 체크포인트와 같은 학습 서버의
`/home/autolab_sw/sunhong/nav-vla/` 아래에 있다. raw actions를 바꾸지 않고 episode directory
전체를 protocol snapshot과 함께 복사한다.

기존 `probe_policy_bays.py`는 항상 네 bay를 모두 실행한다. oracle sanity에서는 evaluator에
behavior-neutral `--targets bay1,bay4` 필터를 추가하거나, 동일 reset/판정 함수를 쓰는 수집
sidecar로 해당 target만 실행한다. 이 변경은 policyㆍbridgeㆍcontroller에는 닿지 않는다.

### 6.5 S2-P: combined method semantic regression

S2에서 가장 좋은 commitment인 `refill_at=0.3`을 유지한 채 `track_mode=preview`로
4 bays x 5 seeds = 20 trials를 추가한다.

목적은 preview가 target selection을 보존하는지 확인하는 것이다. preview의 target accuracy가
replay보다 10 percentage points 이상 떨어지면 “목표 선택을 보존한다”고 주장하지 않는다.

### 6.6 S3: ring executor ablation

고정 조건:

- checkpoint: `models/ckpt_v6_60k`
- `refill_at=0.3`
- speed phrase: `normal`
- `curv_boost=1.0`
- `preview_dual=false`
- wrapper의 `max_speed=3.2`, `speed_slew=0.08`
- inner/outer lane을 동일 reset에서 paired evaluation
- seed `0,1,2,3,4`; 각 condition당 5 map, map당 4 rollouts

| condition | 설정 | 역할 |
|---|---|---|
| replay | `track_mode=replay`, cap 0 | raw action replay baseline |
| pursuit | `track_mode=pursuit`, cap 0 | chord-aiming geometric baseline |
| preview | `track_mode=preview`, cap 0 | 주 방법, 손규칙 없는 비교 |
| preview_cap | `track_mode=preview`, `curv_slow_alat=0.8` | 별도 safety envelope |

시간이 남으면 동일 네 조건을 `fast` phrase에서 extension으로 반복한다. normal core를 끝내기
전에 fast extension을 시작하지 않는다.

주 지표:

1. 사전에 고정한 corner-exit 후 2--3 m window의 rollout별 absolute lateral error p95
2. steering unwind lag
3. departure/completion rate

보조 지표:

- 전체 ring absolute lateral error p95/max
- aligned-margin exceeding segment count
- footprint-boundary overlap rate (pose yaw까지 확보된 경우)
- segment-median maximum
- arclength/completion
- mean speed, speed p95, jerk RMS
- latency, underrun, watchdog

`preview_cap`의 결과는 학습 정책 자체의 개선으로 합치지 않고, 물리 cap을 추가했을 때의
operating point로 별도 표시한다.

corner-exit window는 결과를 보기 전에 `track_paths.json`의 기하만 이용해 T2와 Slot4 주변에서
정의하고, 정확한 start/end index를 protocol metadata에 저장한다. timestep이나 segment 수를
독립 표본처럼 사용하지 않고 rollout을 통계 단위로 둔다.

### 6.7 총 core workload

| 구분 | rollouts |
|---|---:|
| S2 commitment sweep | 60 |
| S2-O oracle sanity | 12 |
| S2-P semantic regression | 20 |
| S3 executor ablation | 80 |
| 합계 | 172 |

smoke run과 선택적 fast extension은 합계에서 제외한다. 모든 run을 동일한 GPU에서 순차 실행해
다른 프로세스의 GPU contention을 피한다.

---

## 7. raw 수집 방법

### 7.1 환경 snapshot

첫 공식 run 전에 다음 정보를 `eval_out/icce_asia2026/protocol/`에 저장한다.

```bash
git rev-parse HEAD > eval_out/icce_asia2026/protocol/git_head.txt
git status --short > eval_out/icce_asia2026/protocol/git_status.txt
git diff -- \
  src/nav_vla_pkg/nav_vla_pkg/vla_bridge_node.py \
  src/nav_vla_pkg/scripts/probe_policy_bays.py \
  src/nav_vla_pkg/scripts/probe_policy_counterfactual.py \
  src/nav_vla_pkg/config/track_paths.json \
  src/simulation_pkg/models/prius_hybrid/model.sdf \
  src/simulation_pkg/launch/driving_sim.launch.py \
  tools/eval/ring_map_probe.sh \
  > eval_out/icce_asia2026/protocol/code_snapshot.diff
sha256sum models/ckpt_v2b_40k/model.safetensors \
  models/ckpt_v6_60k/model.safetensors \
  src/nav_vla_pkg/config/track_paths.json \
  src/simulation_pkg/models/prius_hybrid/model.sdf \
  > eval_out/icce_asia2026/protocol/artifacts_sha256.txt
```

현재 worktree가 dirty이므로 commit hash만 저장하면 재현되지 않는다. 관련 파일의 diff도 반드시
보관한다.

### 7.2 bay 수집

기존 `probe_policy_bays.py`를 그대로 사용한다. condition/seed마다 bridge만 해당 parameter로
재기동하고 다음을 실행한다.

```bash
python3 src/nav_vla_pkg/scripts/probe_policy_bays.py \
  --repeats 1 --timeout 75 \
  --out <RUN_DIR>/bay_confusion.json \
  > <RUN_DIR>/probe.log 2>&1
```

각 seed의 한 호출은 bay1--bay4 네 trial을 순서대로 만든다. 동시에 rosbag sidecar를 실행하고,
종료 후 `ros2 param dump /vla_bridge > <RUN_DIR>/bridge_params.yaml`을 남긴다.

### 7.3 ring 수집

하네스 smoke가 통과한 뒤 기존 wrapper를 사용한다. 예시는 preview-only condition이다.

```bash
SPEED_WORD=normal \
EXTRA_BRIDGE_ARGS="-p seed:=0 -p refill_at:=0.3 -p track_mode:=preview -p preview_dual:=false -p curv_slow_alat:=0.0 -p curv_boost:=1.0" \
tools/eval/ring_map_probe.sh \
  models/ckpt_v6_60k \
  icce_asia2026/raw/S3_executor/preview/seed00/run
```

주의사항:

- wrapper는 관련 Gazebo/bridge/server process를 전역 종료한다. 다른 Gazebo 작업과 병행하지 않는다.
- wrapper는 `~/.gz/sim/log`를 지운다.
- server 준비 loop에 timeout이 없는 버전이므로 별도 wall-time guard를 둔다.
- output prefix directory는 미리 생성한다.
- 같은 prefix를 재사용하지 않는다.

### 7.4 기존 geometry evaluator 재사용

```bash
python3 tools/eval/geometric_lane_check.py \
  eval_out/icce_asia2026/raw/S3_executor/*/seed*/run_map.json \
  > eval_out/icce_asia2026/derived/geometric_all.txt
```

위 도구의 기본 정의는 `(lane width - car width) / 2 = 0.70 m`이며, 20-index segment의
중앙값이 이를 넘으면 해당 segment를 센다. 하지만 이는 original-scale 차량용 legacy
threshold다. 현재 frozen geometry에서 정렬 상태의 중심-offset 여유 근사는
`(3.16 - 1.48971) / 2 = 0.835 m`다. analysis-only aggregator는 이 값을 별도 열로 계산한다.

0.835 m 역시 차량이 차선 방향과 정렬됐다는 근사다. rosbag pose의 yaw와 SDF collision box를
사용해 차체 footprint와 lane corridor의 겹침을 계산할 수 있으면 이를 실제 물리 경계의 주
지표로 쓰고, 고정 0.835 m는 보조 지표로 둔다. footprint 계산을 이번 마감까지 검증하지
못하면 “차체 접촉”이라 부르지 않고 **aligned-margin exceedance**라고만 쓴다.

0.70 m 결과는 **legacy boundary-violating segment**로만 병기한다. “충돌”, “안전 사건” 또는
“lane touch”로 과장하지 않는다.

CSV와 plot을 위해서는 raw JSON과 rosbag만 읽는 analysis-only aggregator를 별도 작성한다.
controller, bridge output 또는 evaluator threshold는 건드리지 않는다.

---

## 8. run acceptance와 제외 기준

### 8.1 ring map acceptance gate

각 map은 다음을 모두 만족해야 valid다.

```bash
jq -e 'length == 2 and
  (all(.[]; (.track_a|length) >= 5 and (.track_b|length) >= 5)) and
  ([.[].case] | sort ==
   ["DIFFERENT bay","SAME sentence (noise floor)"])' \
  <RUN_DIR>/run_map.json

! rg -n "reset failed|too few points" <RUN_DIR>/run_probe.log
```

`DIFFERENT bay`는 probe의 오래된 label일 뿐 ring 실험에서는 inner/outer lane pair를 뜻한다.
논문 표에 이 문자열을 의미 있는 bay 결과처럼 표시하지 않는다.

### 8.2 공통 invalid 기준

- reset failure
- model server crash 또는 timeout
- pose point 부족
- instruction이 bridge에 전달되지 않음
- checkpoint hash 불일치
- ghost `/cmd_vel` publisher
- 첫 `/vla/plan`과 첫 nonzero `/cmd_vel` 이후 평가 window에서 watchdog 발생
- 위 평가 window의 queue underrun 1% 이상
- 계획하지 않은 parameter 또는 code version 사용
- raw file 일부 누락

invalid run은 결과값을 본 뒤 선택적으로 제외하지 않는다. 위 사전 기준에 해당할 때만 제외하고
같은 condition/seed로 한 번 재실행한다.

첫 plan 전에 발생하는 startup watchdog는 invalid 판정에 넣지 않는다. high-refill 조건에서만
latency/underrun이 증가하면 semantic 결과와 분리해 함께 보고한다.

### 8.3 결과를 보고도 valid로 남겨야 하는 사례

- 목표와 다른 bay 도달
- boundary violation 또는 track departure
- 높은 same-instruction noise
- preview가 replay보다 나쁜 결과
- 정지 실패 또는 creep

이들은 시스템 실패가 아니라 연구 결과다.

---

## 9. 그림과 표를 위한 data-to-claim map

| 논문 요소 | 필요한 raw data | derived 열 | 지지하는 주장 |
|---|---|---|---|
| Fig. 1a: first-chunk path overlay | `/vla/plan`, instruction, seed | cumulative x/y per action index | 지시별 계획은 후반에서 갈라짐 |
| Fig. 1b: divergence vs action index | 같은/다른 instruction chunk | pair distance, noise band, decision onset | short commitment가 분기 전에 끝남 |
| Fig. 2a: target accuracy vs commitment | bay JSON + plan timestamps | target accuracy, measured plan interval | 잦은 replanning이 target 선택을 약화 |
| Fig. 2b: confusion matrices | bay JSON | commanded x reached counts | endpoint collapse의 형태 |
| Fig. 3a: ring trajectory overlay | ring map JSON | aligned trajectory, lane center | preview가 corner exit를 일찍 풀어줌 |
| Fig. 3b: corner-exit error distribution | ring map + track geometry | post-exit p95, unwind lag | replay 대비 tracking improvement |
| Table I: setup | metadata + bridge params | fixed parameters | 재현성ㆍ공정 비교 |
| Table II: commitment | S2 metrics | accuracy, endpoint, latency, underrun | semantic starvation 정량화 |
| Table III: executor | S3 metrics | post-exit p95, unwind lag, footprint/aligned/legacy 경계 지표, speed | preview와 safety cap 분리 |

가능하면 bar chart보다 trial 점을 함께 보이는 dot/interval plot을 사용한다. 표본이 작으므로
평균 막대만 제시하지 않는다.

### 통계 처리

- binary rate: Wilson 95% confidence interval과 seed-paired difference
- continuous paired metric: seed/lane-stratified bootstrap 또는 exact paired permutation
- S2 전체 refill 비교: pre-registered ordinal trend 또는 logistic regression
- 계획한 비교는 `.30 vs .93`, `.30 vs .70` 두 개이며 Holm correction
- `p > .05`를 동등성으로 해석하지 않는다.

---

## 10. 논문 진행/중단 게이트

### Gate A: 2026-09-02 12:00 KST

다음을 모두 만족하면 semantic starvation + preview 통합 논문을 유지한다.

- v2b checkpoint smoke 성공
- `r030` target accuracy >= 0.75
- `r093` target accuracy <= 0.50
- first-chunk profile에서 alternative instruction divergence가 same-instruction noise를 넘는
  후반 구간이 반복 관찰됨
- oracle replay가 `.93`과 `.30` 모두에서 target path를 보존함

만족하지 않으면 원인을 고치기 위해 policy/controller를 튜닝하지 않는다. 논문을 다음 fallback으로
즉시 축소한다.

> **A Training-Free Queue-Preview Executor for Chunked VLA Lane Keeping**

이 경우 S3를 seed 0--4로 확대하고, semantic starvation은 향후 연구 또는 motivating pilot로만
남긴다.

### Gate B: 2026-09-03 12:00 KST

preview-only가 replay보다 corner-exit unwind lag와 lateral p95 중 어느 것도 일관되게
개선하지 못하면 preview 우월성을 주장하지 않는다. pursuit 실패나 preview-cap 성공만 골라
논문을 만들지 않는다.

---

## 11. 일정

### 2026-09-01

- [x] 주제와 scope 확정
- [x] 과거 근거와 관련 evaluator 확인
- [x] v2b remote checkpoint 존재ㆍhash 확인
- [x] 실험 매트릭스 사전 고정
- [ ] v2b local 복원
- [ ] counterfactual probe 평가 하네스 회귀 수정
- [ ] S0 smoke 2종 통과

### 2026-09-02

- [ ] S2 commitment sweep 60 rollouts
- [ ] S2-O oracle replay sanity 12 rollouts
- [ ] S1 first-chunk profile 추출
- [ ] Gate A 판정
- [ ] S2-P preview semantic regression 20 rollouts
- [ ] Introduction, Problem Formulation, Method 초안

### 2026-09-03

- [ ] S3 executor core 80 rollouts
- [ ] raw acceptance/exclusion audit
- [ ] `run_metrics.csv`와 3개 figure 생성
- [ ] Table I--III 생성
- [ ] Results, Discussion, Limitation 작성
- [ ] 6쪽 전체 초안 완성

### 2026-09-04

- [ ] 실패/invalid cell만 사전 기준대로 보충
- [ ] 수치-raw 파일 역추적 audit
- [ ] 과대주장ㆍGuardedLC 중복 점검
- [ ] IEEE A4 2단 6쪽 및 PDF font 검사
- [ ] 오후 마감 전에 제출 buffer 확보

---

## 12. 6쪽 원고 구성

1. **Page 1:** 문제, 반직관적 실패 예, 기여 3개
2. **Page 2:** 관련연구와 semantic decision starvation 정의
3. **Pages 2--3:** commitment/preview executor와 측정 방법
4. **Page 4:** 두 checkpointㆍ두 taskㆍ실험 프로토콜
5. **Pages 4--5:** commitment sweep, chunk profile, executor ablation
6. **Page 6:** 한계, 결론, 참고문헌

권장 기여 문장은 세 개를 넘기지 않는다.

1. 언어 조건 분기가 chunk 후반에 있을 때 발생하는 semantic decision starvation의 폐루프 측정
2. target outcome과 step-wise counterfactual plan profile을 연결하는 진단 프로토콜
3. 재학습이나 별도 verifier 없이 commitment와 queue-preview를 결합한 실행 평가

---

## 13. 금지할 과대주장

- adaptive action chunking을 최초 제안했다.
- preview가 semantic starvation 자체를 해결한다.
- 모든 VLA 또는 모든 navigation task에 같은 decision onset이 존재한다.
- 시뮬레이션 결과로 실차 안전성을 보장한다.
- speed cap 결과를 VLA policy 자체의 성능으로 본다.
- trajectory divergence가 곧 semantic grounding 또는 task understanding이다.
- single/few-run 파일럿의 0건 실패가 안전 보장이다.
- 서로 다른 checkpoint의 수치를 한 모델의 end-to-end ablation처럼 표현한다.

두 checkpoint를 사용하는 이유는 명시해야 한다. v2b는 shared-prefix 이후 여러 parking 목표를
선택하는 semantic task이고, v6는 같은 SmolVLA/ROS 2 실행 구조에서 지속적인 ring tracking을
검증하는 complementary task다. 최종 표에서는 checkpoint와 task 경계를 항상 표시한다.

---

## 14. 바로 다음 실행 순서

1. v2b 40K checkpoint를 로컬로 복원하고 SHA-256을 확인한다.
2. 현재 counterfactual probe의 initializer 회귀를 평가 코드에서만 복구한다.
3. 환경/코드/checkpoint snapshot을 저장한다.
4. bay/ring smoke를 각각 1회 실행해 output acceptance gate를 확인한다.
5. S2를 `r093 -> r070 -> r030` 고정 순서로 몰아서 실행하지 않고 seed별로 condition 순서를
   순환한다. 고정 Latin-square 또는 ABBA 순서를 metadata에 남겨 시간대/GPU 온도 confound를
   줄인다.
6. S2 완료 즉시 Gate A를 판정하고, 논문 범위를 더 이상 넓히지 않는다.
7. S3 core를 끝낸 뒤에만 fast extension을 고려한다.

핵심 원칙은 단순하다. **이번 주에는 policy를 더 좋게 만드는 연구를 하지 않고, 이미 관찰한
현상을 같은 조건에서 반복 가능하게 측정해 figure와 table로 바꾸는 연구만 한다.**
