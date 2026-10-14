# ICCE-ASIA 2026 VLA 연구 계획 v2 (대체됨)

> **상태: 2026-09-01에 v3로 대체됨.** 이번 제출은 v2b parking 중심의 이 계획이 아니라
> v6 하나에서 시스템ㆍ언어ㆍaction commitment를 함께 재수집하는
> [ICCE-ASIA 2026 VLA 시스템 논문 연구 계획 v3](../icce_asia_2026_system_paper_plan_v3.md)와
> [v6 50-run matrix](../icce_asia_2026_v6_eval_matrix.csv)를 공식 protocol로 사용한다.
> 아래 내용은 semantic-suffix 주제의 결정 이력을 보존하기 위한 문서다.

## 0. 최종 결정

| 항목 | 결정 |
|---|---|
| 학회 | IEEE/IEIE ICCE-ASIA 2026 |
| Full paper 마감 | 2026-09-04 |
| 결과 통지 | 2026-09-18 |
| 최종본 마감 | 2026-09-30 |
| 논문 성격 | GuardedLC와 무관한 독립 VLA driving 논문 |
| 주기여 | language-conditioned action suffix가 짧은 execution horizon에 의해 반복 폐기되는 현상 |
| 보조 실험 | 긴 commitment의 추종 비용과 queue-preview 완화 |
| 공식 protocol | v0.2, 2026-09-01 |

공식 조건표는
[icce_asia_2026_semantic_suffix_matrix.csv](icce_asia_2026_semantic_suffix_matrix.csv)에
고정한다. 이전의 172-rollout 통합안은 공식 protocol이 아니다.

### 작업 제목

> **Too Soon to Turn: Semantic Suffix Starvation in Chunked VLA Driving**

보수적인 대체 제목:

> **Execution-Horizon-Induced Instruction Collapse in Chunked VLA Driving**

### 한 문장 주장

언어별 VLA action chunk가 공통 주행 prefix 뒤에서만 갈라지는 상황에서는, 지나치게 짧은
periodic commitment가 더 최신 관측을 제공하면서도 정작 언어를 구분하는 suffix를 매번
실행 전에 폐기해 목표 선택을 붕괴시킬 수 있다.

이 논문은 adaptive horizon selector를 제안하지 않는다. 특정 언어 분기형 navigation에서
발생하는 failure mechanism을 측정하고, 실행 horizon과 언어 분기 위치를 직접 연결한다.

---

## 1. 왜 이 주제를 선택하는가

### 1.1 후보 비교

| 후보 | 최신 문헌과의 차별성 | 현재 증거 | 마감 위험 | 결정 |
|---|---:|---:|---:|---|
| 일반 execution-horizon 최적화 | 낮음 | 높음 | 중간 | 제외 |
| async latency/underrun 개선 | 매우 낮음 | 높음 | 중간 | 제외 |
| queue-preview 단독 방법 | 낮음--중간 | 매우 높음 | 낮음 | 보조 실험 |
| counterfactual instruction robustness | 낮음--중간 | 높음 | 중간 | 진단 도구로만 사용 |
| **semantic suffix starvation** | **중간--높음** | **높음** | **중간** | **주제 확정** |

preview-only 논문은 당장 완성하기 쉽지만, 평균 곡률과 look-ahead는 고전 제어로 보일 수 있고
2026년에는 VLA action execution 연구가 이미 매우 혼잡하다. 반면 현재 저장소에는 다음의
구체적인 역설을 지지하는 파일럿이 있다.

| `refill_at` | 파일럿 명목 실행량 | v2b parking 결과 |
|---:|---:|---|
| 0.93 | 약 6 actions | 지시와 무관한 한 endpoint로 붕괴 |
| 0.70 | 약 12 actions | 중간 bay만 정답 |
| 0.30 | 약 21 actions | commanded bay 8/8 |

이 수치는 동기와 설계에만 사용한다. checkpointㆍ코드ㆍ문장ㆍresetㆍseed를 고정해 다시
수집하기 전에는 논문 결과표에 넣지 않는다.

### 1.2 최신 연구와의 정확한 경계

- [A3](https://arxiv.org/abs/2605.11567)은 여러 chunk의 자기일관성을 검증해 실행할 가장 긴
  prefix를 선택한다.
- [AutoHorizon](https://arxiv.org/abs/2602.21445)은 action attention으로 predictive limit을
  추정한다.
- [PACE](https://arxiv.org/abs/2606.00537)는 속도 profile의 phase transition으로 재계획
  경계를 선택한다.
- [Mixture of Horizons](https://arxiv.org/abs/2511.19433)은 장기 foresight와 단기 정밀도의
  trade-off를 학습ㆍ추론 단계에서 다룬다.
- [RTC](https://arxiv.org/abs/2506.07339),
  [REMAC](https://arxiv.org/abs/2601.20130),
  [FutureRTC](https://arxiv.org/abs/2607.24008),
  [FlashVLA](https://arxiv.org/abs/2608.27384)는 비동기 chunk 생성ㆍ정합ㆍ교정 문제를 다룬다.
- [IntentVLA](https://arxiv.org/abs/2605.14712)는 인접 query가 서로 다른 short-horizon intent를
  재표본화해 충돌하는 현상을 다룬다.
- [ICR-Drive](https://arxiv.org/abs/2604.05378)는 driving instruction의 paraphrase, ambiguity,
  noise, misleading perturbation에 대한 counterfactual robustness를 평가한다.

따라서 다음은 기여로 주장하지 않는다.

- execution commitment 또는 non-monotonic horizon effect의 최초 발견
- 최초 training-free/adaptive/asynchronous VLA executor
- 최초 counterfactual VLA 평가
- 최초 unexecuted action tail 활용
- queue-preview 자체가 semantic starvation을 해결한다는 주장

본 연구의 좁은 차이는 다음 세 조건을 한 인과 사슬로 검증하는 데 있다.

1. 같은 상태에서 다른 지시의 action chunk가 초반에는 거의 같다.
2. 지시별 trajectory divergence가 chunk suffix에서 시작된다.
3. 실제 실행 prefix가 그 시점보다 짧으면, 반복 replanning이 그 분기를 차량에 전달하지 못한다.

안전한 related-work 문장:

> Prior work selects execution horizons from predictive reliability, phase structure, or task-level
> progress. We instead diagnose a language-specific execution pathology: instruction-conditioned
> alternatives can share an early motion prefix and diverge only in the suffix, which periodic
> replanning may repeatedly truncate before it reaches the vehicle.

---

## 2. 연구 문제와 측정 정의

### 2.1 용어

**Semantic suffix starvation**은 언어 지시별 행동 차이가 action chunk의 뒤쪽에서 나타나지만,
실행기가 그 위치보다 앞에서 계속 새 chunk로 교체해 의미적으로 구별되는 행동이 actuator에
도달하지 못하는 현상을 뜻한다.

이 용어는 본 시스템에서 검증할 작업 정의다. “모든 VLA의 일반적 결함”이나 “최초 발견”으로
표현하지 않는다.

### 2.2 위치별 언어 차이

같은 image/state와 같은 policy seed에서 지시만 바꿔 얻은 두 action chunk를 ego-frame
trajectory로 적분한다. action index `j`에서 다음을 계산한다.

```text
D_sem(j)   = distance between two instructions at identical image/state/seed
D_noise(j) = distance for the same instruction under different policy seeds
```

`D_sem(j)`가 `D_noise(j)`의 95th percentile을 3개 연속 action에서 넘는 최초 index를
`decision_onset_idx = j*`로 정의한다.

### 2.3 실제 실행과의 연결

각 plan `t`에 대해 다음 값을 raw telemetry에서 구한다.

- `e_t`: 해당 plan이 splice되기 전 실제로 pop되어 실행된 action 수
- `semantic_margin_t = e_t - j*_t`
- `branch_survived_t = 1[e_t >= j*_t]`
- `semantic_execution_coverage_t = max(0, e_t-j*_t+1) / (H-j*_t+1)`

명목상 `refill_at`을 초 단위 horizon으로 간주하지 않는다. inference latency와 overlap splice가
있으므로 항상 측정된 `e_t`와 plan interval을 보고한다.

### 2.4 연구 질문

- **RQ1:** bay 지시별 action divergence가 chunk suffix에 집중되는가?
- **RQ2:** 실행 prefix가 decision onset보다 짧을 때 target selection이 붕괴하는가?
- **RQ3:** 이 현상은 latency, underrun 또는 queue phase bug로 설명되는가?
- **RQ4 (보조):** 의미 분기를 살리는 긴 commitment의 geometric tracking cost를 residual-queue
  preview가 줄일 수 있는가?

### 2.5 가설

- **H1:** `r030`의 target-selection accuracy가 `r093`보다 높다.
- **H2:** `r093`의 measured execution prefix는 대부분의 pre-turn anchor에서 `j*`보다 짧다.
- **H3:** 실패 rollout은 성공 rollout보다 semantic margin과 coverage가 낮다.
- **H4:** phase-locked oracle replay는 `r093`과 `r030` 모두에서 target path를 보존한다.
- **H5 (보조):** 긴 commitment에서 queue-preview는 direct replay보다 corner-exit p95 lateral
  error와 steering unwind lag를 줄인다.

---

## 3. 대안 설명과 필수 대조군

| 대안 설명 | 구분 실험 | 판단 |
|---|---|---|
| 언어가 애초에 action을 바꾸지 않음 | 동일 상태 counterfactual chunk profile | suffix divergence가 noise보다 커야 함 |
| high refill이 queue phase를 깨뜨림 | absolute-tick oracle replay | oracle도 실패하면 starvation 인과 주장 중단 |
| high refill만 latency/underrun이 큼 | plan/status telemetry | 시스템 결함과 semantic outcome을 분리 보고 |
| stopping skill 실패 | `reached==commanded`와 `stopped` 분리 | target selection을 primary로 사용 |
| seed 또는 reset drift | 같은 seedㆍtarget paired, condition 순서 순환 | run-level paired 분석 |
| preview가 목표를 바꿈 | `r030` replay vs preview parking | 보조 방법을 쓰려면 selection 보존 확인 |

핵심 outcome은 `reached bay == commanded bay`다. v2b의 미세 creep 때문에 기존
`correct = reached + in_bay + stopped`는 semantic success로 사용하지 않는다.

---

## 4. 동결할 실행 스냅샷

### 4.1 checkpoint

- v2b 40K parking checkpoint 원격 경로:
  `/home/autolab_sw/sunhong/nav-vla/runs/navvla_smolvla_v2b/checkpoints/040000/pretrained_model`
- v2b `model.safetensors` SHA-256:
  `86deaa0ac5b90a901512f64268a2c0a483ecd44c27b53b46efd32e6a1af484ac`
- 보조 ring checkpoint: `models/ckpt_v6_60k`
- v6 SHA-256:
  `581773d8ac2c50a921f42930db51be31745c14909103c66910429c11c63ce562`

복원:

```bash
rsync -a \
  autolab_sw@115.145.211.157:~/sunhong/nav-vla/runs/navvla_smolvla_v2b/checkpoints/040000/pretrained_model/ \
  models/ckpt_v2b_40k/
sha256sum models/ckpt_v2b_40k/model.safetensors
```

### 4.2 코드와 환경

문서 작성 시 HEAD는 `70d50cd20ab9514cd9c2c5e8a47216797ad47a0e`지만 worktree가
dirty이므로 commit hash만으로 재현되지 않는다. 공식 run 전에 관련 diff, 전체 실행 명령,
ROS/Gazebo/GPU 버전과 artifact hash를 저장한다.

공식 수집 시작 후 다음을 바꾸지 않는다.

- checkpoint, action chunk length 30, control rate 10 Hz
- `splice_overlap`, camera/preprocessing, state ordering
- 네 canonical slow instruction과 reset pose
- target polygon, timeout, success/exclusion 기준
- seed `0,1,2,3,4`
- 선택한 `refill_at = 0.93, 0.70, 0.30`

허용되는 변경은 평가 crash 수정, control path가 읽지 않는 telemetry, raw-read-only 분석뿐이다.
변경 후에는 S0를 다시 수행하고 protocol snapshot을 갱신한다.

---

## 5. 로직 변경 없는 데이터 수집

### 5.1 behavior-neutral telemetry

정확한 `e_t`를 얻기 위해 `/vla/plan` JSON에 다음 값만 추가하는 것을 권장한다.

- `req`, `seed`, `task`
- `obs_stamp`, `obs_seq`, `state`
- `tick_at_request`, `tick_at_splice`
- `queue_before_splice`, `queue_after_splice`
- `latency_ms`

`/vla/status`에는 raw `popped`, `underruns`, `watchdog_hits`를 남긴다. 어떤 제어 노드도 이
telemetry를 구독하지 않으며 action, splice, steering 계산은 변경하지 않는다. instrumentation은
S0 전에 끝내고 이후 동결한다.

시간이 부족해 telemetry를 추가하지 못하면 `/vla/plan` timestamp로 plan interval만 측정할 수
있다. 이 경우 논문에서 exact executed-action count 또는 semantic coverage를 주장하지 않는다.

### 5.2 rosbag sidecar

모든 closed-loop run에서 다음을 기록한다.

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

S1 anchor를 추출하는 `r093` reference run에서는 `/camera/image_raw`도 추가한다. 전체 60회에
camera를 저장하지 않고, 사전에 정한 anchor용 reference run만 저장한다.

### 5.3 raw 계층

```text
eval_out/icce_asia2026_v2/
  protocol/
    semantic_suffix_matrix.csv
    git_head.txt
    git_status.txt
    code_snapshot.diff
    environment.txt
    artifacts_sha256.txt
  raw/
    S1_profile/
      anchors.json
      queries.jsonl
      chunks.npz
    S2_commit/<condition>/seed00/
      metadata.json
      bay_confusion.json
      probe.log
      bridge.log
      serve.log
      bridge_params.yaml
      rosbag2/
    S3_oracle/<condition>/rep00/
    S4_preview_optional/
  derived/
    run_metrics.csv
    plan_metrics.csv
    chunk_step_metrics.csv
    exclusions.csv
  figures/
  tables/
```

`raw/`는 생성 후 수정하지 않는다. invalid run도 삭제하지 않고 제외 사유와 replacement run
ID를 기록한다.

### 5.4 수집 전용 유틸리티 범위

새로 작성해도 되는 코드는 다음 두 평가 유틸리티뿐이다.

- **run collector:** 고유 run ID 확인, metadata/parameter dump, rosbag 시작ㆍ정상 종료,
  probe exit code와 acceptance 결과 저장
- **suffix profiler:** 저장된 anchor JPEG/state를 exact serving preprocessing으로 다시 보내고,
  instruction/seed별 raw 30-action chunk를 수정 없이 저장

suffix profiler는 새 metric을 policy server에 넣지 않는다. server가 반환한 raw actions를 파일에
쓰고, `D_sem`, `D_noise`, `j*` 계산은 별도 analysis 단계에서 수행한다. 같은 입력에 대한 기존
server와 profiler의 action array가 일치하는 smoke test를 통과시킨다.

---

## 6. 공식 실험

### 6.1 S0: preflight

1. v2b checkpoint hash 확인
2. bay1--bay4를 `refill_at=0.30`, seed 0으로 각 1회
3. reset error, pose 누락, mid-run watchdog, queue underrun 확인
4. target selection 3/4 이상이면 본 수집 진행

현재 `probe_policy_counterfactual.py`에는 initializer 위치 회귀가 있다. 이는 optional ring
실험 전에만 필요하다. core bay 실험은 `probe_policy_bays.py` smoke를 별도로 통과시킨다.

### 6.2 S1: position-wise counterfactual profile

`r093`의 한 reference trajectory에서 결과를 보기 전에 정한 네 progress anchor를 사용한다.

- common approach 시작
- approach 1/3
- approach 2/3
- 첫 bay turn 직전

각 anchor의 동일 JPEG/state에 bay1--bay4 instruction과 seed 0--4를 넣는다.

```text
4 anchors x 4 instructions x 5 seeds = 80 offline chunk queries
```

policy output이나 controller를 바꾸지 않는 evaluation-only query다. 각 chunk의 30 actions를
누적 trajectory로 바꾸고 `D_sem`, `D_noise`, `j*`를 계산한다. anchor 위치는 world geometry로
사전 고정하고 결과에 맞춰 이동하지 않는다.

### 6.3 S2: closed-loop commitment sweep

고정:

- checkpoint `ckpt_v2b_40k`
- `track_mode=replay`
- shaping OFF: `curv_slow_alat=0`, `curv_boost=1.0`, `speed_scale=1.0`
- canonical bay1--bay4 slow instructions
- reset `(-12.30, -22.16, 1.112)`
- seed 0--4

조건:

| condition | refill | targets x seeds | rollouts |
|---|---:|---:|---:|
| r093 | 0.93 | 4 x 5 | 20 |
| r070 | 0.70 | 4 x 5 | 20 |
| r030 | 0.30 | 4 x 5 | 20 |

합계 60 closed-loop rollouts다. seed별 condition 순서는 Latin square 또는 ABBA로 순환하고
metadata에 실제 순서를 남긴다.

Primary:

- target-selection accuracy
- 4x4 commanded-to-reached confusion matrix
- ordinal bay error `|reached-commanded|`
- rollout별 semantic margin과 coverage

Secondary:

- endpoint error, in-bay, stopped, stop time
- measured execution prefix와 plan interval
- inference latency, underrun, watchdog

### 6.4 S3: phase-locked oracle control

기존 `stub_policy_server.py --mode replay`와 absolute request `tick`을 사용한다.

- bay1 episode: `corpus_v2_train__ep_0041`
- bay4 episode: `corpus_v2_train_b__ep_0012`
- `refill_at=0.93`과 `0.30`
- 각 cell 3회 reset
- S2의 v2b median latency를 `--latency-ms`로 주입

```text
2 targets x 2 refill x 3 repeats = 12 rollouts
```

oracle도 high refill에서 실패하면 queue/phase 문제가 남아 있는 것이므로 semantic suffix
starvation이라는 인과 주장을 중단한다.

### 6.5 S4: optional preview semantic-preservation check

Gate A를 통과하고 core figure가 먼저 완성된 경우에만 수행한다.

- v2b, `refill_at=0.30`, `track_mode=preview`
- bay1--bay4 x seed0--4 = 20 rollouts
- replay r030과 target selection 및 endpoint error 비교

preview가 target accuracy를 10 percentage points 이상 낮추면 “의미 선택을 보존한다”고 쓰지
않는다.

### 6.6 S5: optional geometric mitigation

마감 시간이 남을 때만 v6 ring에서 `replay`와 single-window `preview`를 비교한다.

- `refill_at=0.30`, normal instruction, shaping OFF
- `preview_dual=false`, `curv_boost=1.0`, `curv_slow_alat=0`
- inner/outer lanes x seed0--4 x 2 modes = 20 meaningful rollouts

Primary는 사전 고정한 corner-exit 2--3 m window의 rollout별 lateral-error p95와 steering
unwind lag다. legacy 0.70 m segment count를 실제 lane contact로 부르지 않는다.

현재 `ring_map_probe.sh`는 각 map에서 SAME-instruction noise pair도 두 번 주행한다. optional
S5에서는 evaluator-only `--skip-same`을 추가해 위 20회만 수집하거나, wrapper를 그대로 쓰면
실제 simulator 주행은 40회이고 분석 대상 lane rollouts만 20회라고 명시한다.

### 6.7 workload

| 구분 | closed-loop rollouts | offline queries | 우선순위 |
|---|---:|---:|---|
| S0 smoke | 4 | 0 | gate |
| S1 counterfactual profile | 0 | 80 | core |
| S2 commitment sweep | 60 | 0 | core |
| S3 oracle control | 12 | 0 | core |
| **core 합계** | **72** | **80** | 제출 필수 |
| S4 preview preservation | 20 | 0 | optional |
| S5 ring mitigation | 20 | 0 | optional |

optional 실험 때문에 core 분석과 원고 작성을 미루지 않는다.

---

## 7. 그림과 표

### 필수 그림

**Fig. 1 — Mechanism.** 네 instruction의 누적 chunk trajectory, action-index별 `D_sem`과
`D_noise`, 각 refill의 measured execution cutoff를 한 그림에 배치한다.

**Fig. 2 — Closed-loop consequence.** refill별 4x4 confusion matrix와 target accuracy/ordinal
error를 표시한다. 각 seed/target 점과 95% CI를 함께 보인다.

**Fig. 3 — Plan-to-outcome link.** rollout별 semantic margin 또는 coverage와 target outcome을
표시하고, 우측에 learned policy와 oracle replay를 비교한다. optional S5가 강하면 Fig. 3의 작은
panel로 corner-exit result를 추가하되 core 결과를 밀어내지 않는다.

### 표

- **Table I:** checkpoint hash, chunk/rate, refill, seed, reset, latency, invalid criteria
- **Table II:** target x/N, ordinal error, measured prefix, coverage, latency/underrun, oracle result

### 통계 단위

- 독립 단위는 action step이 아니라 rollout이다.
- binary target outcome: Wilson 95% CI와 target/seed-paired exact test
- ordinal error: paired permutation 또는 paired bootstrap CI
- 사전 비교: `.30 vs .93`, `.30 vs .70`; Holm correction
- 80 offline chunks는 메커니즘 profile이며 80개의 독립 closed-loop 성공 사례로 세지 않는다.

---

## 8. validity와 중단 조건

### invalid run

- reset failure 또는 pose 누락
- checkpoint hash 불일치
- instruction publish 실패
- model server crash/timeout
- 첫 plan과 첫 nonzero command 이후 watchdog
- 같은 평가 window에서 queue underrun 1% 이상
- 계획하지 않은 parameter/code version
- raw artifact 누락

첫 plan 이전 startup watchdog는 invalid로 세지 않는다. 목표를 잘못 선택하거나 정지에
실패한 rollout은 결과이지 invalid가 아니다.

### Gate A: 2026-09-02 12:00 KST

다음을 모두 만족하면 semantic suffix starvation 논문을 유지한다.

- r030 target accuracy >= 0.75
- r093 target accuracy <= 0.50
- 다른 instruction의 suffix divergence가 same-instruction noise를 반복적으로 초과
- r093 measured prefix가 주요 pre-turn anchor의 `j*`보다 짧음
- oracle replay가 r093/r030 모두에서 target path를 보존
- high-refill failure가 underrun/watchdog 차이만으로 설명되지 않음

불충족 시 원인을 고치기 위해 policy/controller를 튜닝하지 않는다.

- divergence는 있지만 위치가 suffix가 아니면 제목을 **Execution-Horizon Sensitivity in
  Language-Conditioned VLA Driving**으로 낮춘다.
- oracle도 실패하면 semantic 인과 주장을 버린다.
- r030/r093 차이가 재현되지 않으면 S5 preview-only fallback을 사용하되, 신규성이 더 약하다는
  사실을 감수하고 executor 시스템 논문으로 축소한다.

---

## 9. 일정

### 2026-09-01

- [x] 독립 VLA 주제로 재결정
- [x] 최신 execution-horizon/async/counterfactual 연구와 경계 설정
- [x] core workload를 72 rollouts로 축소
- [ ] v2b checkpoint 복원
- [ ] telemetry-only fields 및 수집 wrapper 동결
- [ ] S0 smoke

### 2026-09-02

- [ ] S2 60 rollouts 수집
- [ ] S3 oracle 12 rollouts 수집
- [ ] S1 80 offline query 추출
- [ ] Gate A 판정
- [ ] Fig. 1--2와 Table I 생성
- [ ] Introduction, Method, Setup 초안

### 2026-09-03

- [ ] Fig. 3와 Table II 생성
- [ ] Results, Discussion, Limitations 작성
- [ ] 시간이 남으면 S4/S5 중 필요한 것만 수행
- [ ] IEEE A4 2단 6쪽 초안 완성

### 2026-09-04

- [ ] raw-to-number audit
- [ ] related-work 과대주장 점검
- [ ] font/embed/page-limit 검사
- [ ] 제출 buffer 확보

---

## 10. 6쪽 구성

1. **Page 1:** 반직관적 failure example, 문제, 기여 3개
2. **Page 2:** execution horizon 관련연구, semantic suffix 정의
3. **Page 3:** paired chunk profile, measured execution coverage, controls
4. **Page 4:** SmolVLA/Gazebo setup, protocol, validity
5. **Page 5:** confusion matrices, plan-to-outcome, oracle result
6. **Page 6:** optional mitigation, limitation, conclusion, references

권장 기여는 다음 세 개로 제한한다.

1. action chunk 안에서 instruction-conditioned divergence가 시작되는 위치의 측정
2. 그 위치와 실제 plan replacement schedule을 연결하는 closed-loop failure 진단
3. model/controller를 바꾸지 않는 oracle 및 paired-run 검증 protocol

preview 결과가 충분히 강한 경우에만 세 번째를 “long-commitment tracking cost에 대한
residual-queue preview ablation”으로 바꾼다.

---

## 11. 금지할 주장

- 모든 VLA가 semantic suffix starvation을 겪는다.
- 짧은 horizon은 일반적으로 해롭다.
- 모델이 언어를 이해했다 또는 grounding을 증명했다.
- A3, AutoHorizon, PACE, RTC가 이 task에서 실패한다.
- preview가 새 visual feedback을 사용하거나 starvation을 해결한다.
- simulator 결과가 실차 안전을 보장한다.
- single checkpoint 결과로 model-agnostic이라고 주장한다.
- pilot 8/8을 공식 결과처럼 재사용한다.

안전한 결론 범위:

> In the evaluated four-way language-fork driving task, excessively short periodic commitment
> repeatedly truncated the suffix in which instruction-conditioned trajectories diverged, and this
> truncation was associated with target-selection collapse under the tested SmolVLA deployment.

---

## 12. 바로 다음 순서

1. v2b checkpoint를 복원하고 SHA-256을 확인한다.
2. telemetry-only plan counters와 수집 wrapper만 보강한다.
3. bay smoke를 통과시킨다.
4. seed별로 r093/r070/r030 순서를 순환하며 S2를 수집한다.
5. oracle control과 offline anchor query를 완료한다.
6. Gate A를 판정하고 그날 바로 논문 제목과 claim을 동결한다.
7. core figure/table이 완성된 뒤에만 preview 실험을 고려한다.

이번 논문의 핵심은 새로운 주행 로직을 더 만드는 것이 아니다. **이미 학습된 VLA가 언어별
행동을 계획하고도, 실행 스케줄 때문에 그 차이가 차량에 전달되지 않는 순간을 측정하는 것**이다.
