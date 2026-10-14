# 일반화 3가지(시각·의미·행동)와 주행 VLA 일반화 연구 정리 — 우리 문제와의 대응 (2026-10-09 15:30)

관련: [학습하지 않은 상황 — 종류와 대응](../../course/학습하지않은상황_종류와_대응.md) ·
[일반화의 경계와 열린 질문](generalization_limits_and_questions.md) ·
[지름길·VLA 벤치마크 비판 관련 연구 (10-03)](../avoidance/20261003_0944_vla-shortcut-related-work.md) ·
[10-03 ~ 10-08 경과 보고서](research_report_20261003_20261008.md) ·
[g4 무효·s2 음성·s3 계획 (10-08 22:37)](../goto_object/20261008_2237_g4-void-s2-negative-s3-plan.md)

> "일반화 3가지"는 로봇 VLA 분야에서 표준으로 쓰이는 **STAR-Gen 의 시각(Visual)·의미(Semantic)·행동(Behavioral)** 분류로
> 해석했다. 우리 문서가 써 온 다른 분류(표현/방향/환경 축, A~H 종류)는 1.3 절에서 이 세 축에 대응시켰다.
> 논문 수치는 2026-10-09 에 arXiv 초록·본문(HTML)으로 확인한 것이고, 검색 요약에만 기댄 항목은 6 절에 따로 적었다.

---

## 0. 한 페이지 요약

1. **세 축의 뜻.** 시각 = 관측만 바뀜(조명·시점·배경·새 물체 외형), 의미 = 지시문만 바뀜(동의어·공간 지칭·새 이름),
   행동 = 필요한 동작이 바뀜(시연에 없는 움직임, 관측 안 되는 물성). 셋의 조합으로 7 범주가 된다(1.2 절).
2. **우리 문제는 '의미'와 '행동'에 몰려 있고, 의미 축은 일반화 이전 단계에서 막혀 있다.** 학습 분포 **안**의 물체 이름·섹터
   문장조차 상수 문장 대조군과 구별되지 않는다(b1 22/42 vs b0 23/42; s2 38/55 vs s2n 41/55, p = 0.672).
   따라서 우리 상태는 "의미 일반화 실패"가 아니라 **"의미 조건화 실패"**로 적어야 정확하다(2 절).
3. **주행 VLA 논문에서 같은 문제를 다룬 것**(3 절):
   - SimLingo(CVPR 2025): post-hoc 라벨은 행동이 시각만으로 추론되므로 언어가 무시된다고 진단하고, 같은 관측에 다른
     지시→다른 행동 짝을 **합성**(Action Dreaming)해 지시 준수 24.5 % → 81.1 %(차선 변경 3.2 % → 83.0 %).
   - Fail2Drive(2026-04): 폐루프 주행 일반화 벤치마크. 7 모델 평균 성공률 −22.8 %p, **행동 일반화 −53.6 %p**.
     모델은 "외운 차선 추종"으로 되돌아간다 — 우리 자리 습관·정차 실패와 같은 모양.
   - ICR-Drive(CVPRW 2026): 지시문 네 교란. 패러프레이즈만으로 LMDrive DS −14.9, 오도 지시 −33.6.
   - LinkVLA·DriveMA·GRAVA(2026): "왼쪽 차선 변경이라 말하고 차선 유지 궤적을 낸다"는 **말-행동 격차**를 명시하고 푼다.
   - BLUE(EMNLP 2026): 언어가 행동을 바꾸는 프레임은 소수 — 우리 14.1 절 관찰과 같다.
   - 로봇 쪽 CAG(2026-02): 언어 **무조건** 모델과 대비해 유도 → 반사실 실패 감소. 우리 b0 가 바로 그 무조건 모델이다.
4. **가장 직접적인 시사점 셋**(5 절): (a) 반사실 짝은 '합성 행동'(SimLingo)과 '합성 언어'(CAST) 두 길이 있고 우리
   cf-sidecar 는 전자에서 실패했으므로 차이 변수를 좁혀야 한다. (b) 미세조정이 베이스 반응을 지우는 현상(r26 0.82 → s2 0.04)은
   VLM→VLA 망각 연구(ReVLA, MAPS)와 같은 현상이다. (c) Fail2Drive 의 짝 라우트와 ICR-Drive 의 네 교란은 우리 같은-자리
   대조군과 A3 를 체계화할 틀이다.

---

## 1. 일반화 3가지 — 정의와 우리 트랙 대응

### 1.1 STAR-Gen 의 세 교란 (Gao, Belkhale, Dasari, Balakrishna, Shah, Sadigh; arXiv 2503.01238, 2025-03)

"기준 과제(base task)에 대한 교란"으로 일반화를 정의한다. 무엇이 바뀌고 무엇이 고정되는지가 핵심이다.

| 축 | 바뀌는 것 | 고정되는 것 | 로봇 예 | 실도로 예 | 우리 트랙 예 |
|---|---|---|---|---|---|
| **시각 (V)** | 관측 이미지 | 지시문, 필요한 행동 | 조명, 카메라 시점, 방해 물체, 배경 | 비·야간·역광, 처음 가는 도시 | 바닥 무늬·조명 변경, 교차 트랙, 실차 카메라 |
| **의미 (S)** | 지시문 | 이미지, 필요한 행동 | 동사 동의어, 공간 관계 서술, 색 지칭 | "천천히" → "느긋하게", 한국어 | A3 패러프레이즈, 학습 안 한 물체 이름, "멸종한 생물" |
| **행동 (B)** | 필요한 행동 | 이미지, 지시문 | 관측 안 되는 물성(질량·마찰) | 노면 마찰, 차량 응답 차이 | Thor 실차 응답, 시연에 없는 동작(역방향·U턴) |

### 1.2 조합 7 범주

| 범주 | 예 (STAR-Gen) | 우리 사례 |
|---|---|---|
| V | 이미지 증강, 장면 변경, 물체 외형, 시점 | 교차 트랙, 조명 |
| S | 물체 속성 지칭, 재표현, 다중 물체 공간 지칭, 인터넷 지식 | A3 재표현, "멸종한 생물" |
| B | 숨은 물체·장면 속성 | 실차 응답 |
| **VB** | **물체 포즈**, 장면 요소 상호작용, 변형 물체, **체화 변경**, 대칭 | **자리 바뀐 장애물, 역방향 주행**, Thor 이식 |
| **SB** | 동작 부사, 공간 다중 물체 지칭, **명사 접지**, 행동 동사 | **"왼쪽 물체로", "〈이름〉 앞에 멈춰"** |
| VS | 속성 의존 물체 변경 | "초록 차" |
| VSB | 물체 통째 교체 | 학습 안 한 물체를 이름으로 지정해 가기 |

STAR-Gen 의 BridgeV2-STAR 평가(OpenVLA·MiniVLA·π0, 13 축, 1,600+ 시행)에서 **세 모델 모두 의미 축이 가장 약했다.**
교차 체화 데이터를 늘리면 여러 축이 좋아지지만 "가장 약한 축에는 이득이 제한적"이라고 보고한다. 우리가 겪는 것과 같은 축이다.

> **출처 주의 (2026-10-13 추가)**: 위 1.1·1.2 의 V/S/B 분류는 **로봇팔 벤치마크**(STAR-Gen / BridgeV2)에서
> 온 것이다. 그쪽은 로봇이 고정돼 있고 책상 위 물체가 여럿이라 **의미 축(S: 못 본 명사·재표현)이 1 급 홀드아웃**이다.
> **자율주행 벤치마크는 그 축을 숨기지 않는다** — 3.2 절의 도메인 관습 비교를 먼저 읽을 것. 이 표를 주행 실습의
> 홀드아웃 설계에 그대로 쓰면 축이 틀어진다(실제로 10-03 강좌 5페이지가 그렇게 틀어졌고 10-13 에 고쳤다).

### 1.3 우리 문서의 분류와의 대응

| 우리 분류 | 출처 | STAR-Gen 축 |
|---|---|---|
| A 환경 / ⑤ 환경 변화 | 종류와 대응 2·5 절 | V |
| B 물체(피하기) | 〃 | VB (포즈) · VSB (새 물체) |
| B 물체(무엇인지 알기) / ③ 학습 안 한 이름 | 〃 | S · VS |
| C 상황의 의미 / F 새 언어 지시 / ③ 표현 일반화 | 〃 | S · SB |
| E 새 조합 (물체 × 행동) | 〃 | SB |
| G 지름길이 깨지는 상황 | 〃 | VB (허위 상관) |
| H 새 동작 | 〃 | B · VB |
| 표현 축 / 방향 축 / 환경 축 | generalization_limits 3 절 | S / VB / V |
| 로봇 논문의 4 단계(표현·조합·물체·의미) | 종류와 대응 4 절 | S / SB / VS / S(인터넷 지식) |

### 1.4 주의: "일반화" 앞에 "조건화"가 있다

STAR-Gen 은 모델이 기준 과제를 수행한다는 전제 위에서 교란을 준다. 우리 goto 과제는 그 전제가 아직 없다 —
학습 분포 **안**의 문장으로도 행동이 바뀌지 않는다(2 절 1번). 그래서 우리 문제를 적을 때는 두 층을 나눠야 한다.

| 층 | 질문 | 우리 상태 |
|---|---|---|
| 조건화 (in-distribution) | 학습한 문장 형식이 행동을 바꾸는가 | 차선·속도 이산 모드(2 × 3)는 바뀜(+2.51 m, 바닥 +0.05 m). 물체 이름·섹터는 **안 바뀜** |
| 일반화 (out-of-distribution) | 처음 보는 문장·장면·동작에서도 되는가 | 표현(A3) 실패, 역방향 실패, 교차 트랙 미측정 |

---

## 2. 지금 연구에서 생긴 문제를 세 축에 놓기

| # | 문제 | 근거 | 축 | 논문에서 부르는 이름 |
|---|---|---|---|---|
| 1 | 문장 유무가 행동을 못 가른다 | b1 22/42 vs b0 23/42; s2 38/55 vs s2n 41/55 (p = 0.672); 두 런의 손실 곡선 거의 동일 | S (조건화) | instruction blindness, counterfactual failure, language-action gap |
| 2 | 모드 단어는 듣고 물체 이름·섹터는 못 듣는다; 효과 크기 부족 | 방향 단어 효과 0.55 m vs 물체 간격 2.73 m (0.2 배); 지속 커밋 없음 | SB (명사 접지) | noun grounding, effect magnitude |
| 3 | 처음 보는 표현 실패 | A3: 학습 표현 +2.51 m, 처음 보는 표현 +0.36 / +0.06 m, 주차 0/8 | S (재표현) | language rephrasing |
| 4 | 자리 습관·방향 편향 | r44 빈 차선 10/20 꺾음, 출발 거리 바꿔도 같은 자리; r47 장애물 무관 왼쪽 1.1 m | VB (허위 상관) | shortcut / spurious correlation / memorized lane-following |
| 5 | 홀드아웃 물체·배치에 무반응 | 다장애물 홀드아웃 r29~r35 (시연의 35 % 천장); 학습 안 한 물체 회피 0/20 | VB · VSB | object pose, novel object |
| 6 | 시연에 없는·희소한 행동을 못 만든다 | 역방향 주행 불가(시계방향 시연 0); 정지 행동 미획득(24 배 오버샘플, seed 8 종 전진); 정차 STRICT 0/120 | B | behavioral generalization, rare behavior, inertia problem |
| 7 | 미세조정이 베이스 반응을 지운다 | r26 예측/시연 0.82 → s2 0.04 / s2n 0.16 / b1 0.06 (문장 유무 무관) | (일반화 이전) 사전 능력 손실 | catastrophic forgetting in VLM→VLA transfer |
| 8 | 해설은 맞고 행동은 안 바뀐다 | 회피 실험 서술은 물체를 맞힘, 조향 무반응; action expert 는 해설 토큰을 읽지 않는 구조 | 말-행동 격차 | language-action gap, reasoning-action misalignment |
| 9 | 교차 트랙·실차 미검증 | 단일 트랙 코퍼스; 교차 트랙 제로샷 계획만 있음 | V (+VB 체화) | cross-dataset / cross-embodiment transfer |

세 축으로 보면 **4·5·6 이 한 묶음(시각+행동, 시연 분포 밖)**, **1·2·3 이 한 묶음(의미)**, 7·8 은 축이 아니라 학습·구조의 문제다.
7 은 특히 중요하다 — 1·2 의 실패 런(r50~r54, b1, s2)이 모두 7 을 동반했으므로, 7 을 분리하기 전에는 1·2 의 원인을 말할 수 없다.

---

## 3. 주행 VLA 논문 정리 (주제별)

### 3.1 서베이 — 일반화를 어떻게 적는가

| 논문 | 내용 | 우리와의 거리 |
|---|---|---|
| Jiang et al., *A Survey on VLA Models for Autonomous Driving* (ICCVW 2025; arXiv 2506.24044) | 열린 과제로 30 Hz 급 추론, 언어 조건 정책의 형식 검증, 롱테일 일반화, sim-to-real 을 든다 | "언어 조건 정책 검증"이 우리 반사실 프로브와 같은 문제의식 |
| *VLA Models for AD: Past, Present, and Future* (arXiv 2512.16760, 2025-12; 목록 github.com/worldbench/awesome-vla-for-ad) | E2E VLA 와 Dual-System VLA(VLM 숙고 + 경량 실행기) 두 패러다임. 6.1.2 "Data and Generalization": 희소 상황 취약, 학습-배포 분포 불일치 | **action head 가 언어를 무시하는 문제는 다루지 않는다.** 서베이의 빈칸이 우리 문제다 |
| *Beyond Textual CoT: Action-Grounded Reasoning in AD* (arXiv 2609.01659) | 추론이 행동에 접지되는지의 서베이 | 3.4 절 주제 |

### 3.2 폐루프 일반화 벤치마크 (시각·행동 축)

#### 3.2.0 도메인별 홀드아웃 관습 — 주행은 상황을, 로봇팔은 명사를 숨긴다 (2026-10-13 추가)

| | 홀드아웃 축 | 대표 벤치마크 | 왜 그 축인가 |
|---|---|---|---|
| **로봇팔 VLA** | **못 본 명사·지시 표현** | LIBERO 계열, BridgeV2-STAR, RT-2 | 로봇 고정, 책상 위 물체 여럿 → 문장이 "어느 것"을 고르는 게 과제의 본질 |
| **자율주행** | **못 본 상황·배치·행동** | Bench2Drive, **Fail2Drive**, NAVSIM, nuScenes 제로샷 | 지시가 사실상 하나("가라"), 변하는 것은 장면 |

- Fail2Drive 의 네 교란 범주(behavioral · visual-lateral · visual-longitudinal · robustness)에 **어휘 축이 없다.**
  "처음 보는 원인 물체 앞 제동"조차 **지각 OOD** 이고 문장은 그 물체를 말하지 않는다.
- 언어가 들어간 주행 연구도 지시는 **닫힌 명령 집합**이다. SimLingo 는 5 종(faster / slower / target speed /
  lane change / object-centric)이고, 숨기는 것은 각 범주 안의 **장면**이다. LMDrive·DriveLM 도 명령 집합은 닫혀 있고
  홀드아웃은 장면·QA 다.
- **우리에게 주는 결론 세 개**
  1. 우리가 VLA 에 요구할 언어는 넓어도 **닫힌 명령 집합**(차선 · 속도 · 경로 모드)이다. SimLingo 가 고른 범위와 같다.
     그 축은 조합 일반화로 성립했다 — c1 = 시연의 0.81, 바닥 0.34, 짝 58/70, p = 2.3e−08.
  2. **현행 강좌 설계(점 목표 원시 동작 `g5d`)는 그보다 더 간다 — VLA 에 어휘를 아예 주지 않는다**(문장 상수 `Target.`,
     목표는 state 의 `[goal_bearing, goal_dist]`). 그래서 어휘 홀드아웃이 개념상 불가능하고 홀드아웃이 전부 상황이다.
     측정: 분포 안 P2 20/20, 목표 바꿔 20/20, 목표 채널 0 이면 0/20, **학습에 없는 목표점**(물체 1.5 m 비킴) P3b 18/20,
     통로 P3a 0/20 기각 ([goto_object/20261013_1104](../goto_object/20261013_1104_goal-reaching-plan-and-g5d-result.md)).
  3. **"멸종한 생물" 류의 열린 의미 지칭은 VLA 축이 아니다.** 주행 VLA 문헌에서 그 역할은 큰 VLM 이 맡거나
     (SimLingo InternVL2-1B, GRAVA 8B) 축에 아예 없다. Qwen2.5-VL 을 앞에 두는 것은 타협이 아니라 기본 배치다.
     (SmolVLA 를 미세조정해 이 역할까지 흡수할 수 있는지 = 음성 전망: 백본 SmolVLM2-500M 의 텍스트 디코더 32 층 중
     `num_vlm_layers = 16` 만 쓰므로 추상 지칭이 사는 깊은 층이 그래프에 없고, goto 미세조정은 베이스의 언어 반응을
     **더하지 않고 뺐다**(r26 0.82 → s2 0.04, 상수 문장 런 s2n 0.16 도 같이 하락).)
- 우리 c1 설계는 Fail2Drive 의 **짝 라우트** 패턴과 같은 꼴이다: 저쪽은 각 교란 라우트에 분포 안 짝을 붙이고,
  우리는 `cn`(문장 없앤 바닥) / `c0`(조합 본 천장) 사이에서 `c1` 을 읽는다. 규모만 작고 구조는 같다.
- 반영: [단기강좌 5페이지](../../course/단기강좌.md) 10-13 개정.

**Fail2Drive** (Gerstenecker, Geiger, Renz; arXiv 2604.08535, 2026-04)
- CARLA, 200 라우트, 새 시나리오 17 종. **각 교란 라우트에 분포 안 짝 라우트**를 붙여 효과를 분리한다.
- 네 범주: robustness(운전과 무관해야 할 요소: 옆 차선 콘, 인도 위 보행자), visual-lateral(차선 변경이 필요한 처음 보는 배치),
  visual-longitudinal(처음 보는 원인 물체 앞 제동: 보행자 대신 동물, 질감 바뀐 정지 표지판), behavioral(막힌 도로에서 정지,
  느린 보행자 뒤 거리 유지 같은 드문 행동).
- 7 모델(TCP, UniAD, ORION, HiP-AD, SimLingo, TransFuser++, PlanT 2.0) + 규칙 전문가. 평균 성공률 −22.8 %p.
  **behavioral −53.6 %p, visual-lateral −33.6 %p, visual-longitudinal −7.2 %p**, robustness 는 가장 작음.
- 결론: 모델이 "hard-coded pattern associations"에 기대고, 새 상황에서 **외운 차선 추종으로 되돌아가며**, LiDAR 에 분명히
  보이는 물체를 무시하고, 빈 공간/점유 공간 개념을 배우지 못했다. LiDAR 융합(TransFuser++)이 가장 강했다(조화 평균 67.5).
- **우리와의 대응**: 짝 라우트 = 우리 같은-자리 대조군(장애물 있음/옆 차선/없음). "외운 차선 추종 복귀" = 자리 습관(4), 정차
  못 함(6). behavioral 축이 가장 크게 무너진다는 수치는 "VLA 가 넓히는 것은 의미, 행동은 시연 범위"라는 강좌 한 문장의 근거가 된다.

**Impromptu VLA** (NeurIPS 2025 D&B; arXiv 2505.23757)
- 8 개 공개 데이터셋 2M 클립에서 80k 클립 선별. 비정형 4 범주: 경계 불명 도로, 임시 규칙 변경, 비전형 동적 장애물, 험한 노면.
  QA + 궤적 주석. 이 데이터로 학습하면 폐루프·개루프 모두 개선.
- 환경(V)·새 물체(VSB)·상황 의미(S) 축을 **데이터로** 메우는 쪽. 우리 종류 A·B·C 의 실도로판.

**Poutine** (arXiv 2506.11234, 2025-06; Waymo E2E 2025 1위)
- 3B VLM. 비전·언어·궤적(VLT) 다음 토큰 예측 사전학습(CoVLA 정상 주행 83 h + Waymo 롱테일 11 h) 뒤 GRPO(선호 라벨 500 프레임 미만).
  RFS 7.99(사전학습만 7.91). 롱테일에 둘 다 필요하다고 보고.
- 희소 상황(B·VB)을 **사전학습 데이터 + RL 후학습**으로 푸는 쪽.

**DriveVA** (ECCV 2026; arXiv 2604.04198)
- 비디오 생성 모델의 사전을 써서 미래 영상과 행동을 같이 디코딩. NAVSIM PDM 90.9. **제로샷** nuScenes(L2 −78.9 %, 충돌 −83.3 %),
  Bench2Drive(L2 −52.5 %, 충돌 −52.4 %). 시각 축 일반화의 원천을 "비디오 사전"으로 설명.

**Towards Zero-Shot Transfer Across Embodiments for Driving VLAs** (arXiv 2609.02341, 2026-09)
- 다른 카메라 리그·데이터셋으로 제로샷. 다중 데이터셋 학습 + BEV-Forcing(BEV 공간 정보를 백본에 넣는 보조 과제).
  체화 수가 적을 때 ID·OOD 모두 개선, 체화 수가 늘면 이득 감소. **데이터 확장만으로는 안 된다**고 명시.
- 우리 Thor 실차 이식(V + 체화)에 해당.

**VLA-R** (KAIST Shim 랩; arXiv 2511.12405, 2025-11)
- 고정 VLM(개방 검출·분할) + Q-Former + 비전-행동 대조 학습으로 **행동을 검색**. 비정형 실외 실로봇, 적은 데이터로 unseen 환경.
- 우리와 규모가 비슷한 소형 플랫폼 사례. "인지는 고정 VLM, 행동은 검색"이라는 분업이 우리 "인지 VLM·이동 VLA"와 닮았다.

### 3.3 지시문 교란·반사실 — 주행 (의미 축)

**LMDrive / LangAuto** (CVPR 2024; arXiv 2312.07488)
- 폐루프 언어 주행 벤치마크. 내비 지시를 LLM 으로 다양하게 바꾸고, notice 지시(실시간 보조)와 **오도 지시 5 %(1~2 초)**를 섞어
  모델이 무시해야 하게 만든다.

**ICR-Drive** (Hamid, Cui, Liang; CVPRW 2026; arXiv 2604.05378)
- 네 교란 가족: Paraphrase, Ambiguity, Noise, Misleading. 시뮬 설정·시드를 고정해 지시문 변화만 분리. LMDrive·BEVDriver.
- LangAuto-Tiny: LMDrive 는 **패러프레이즈만으로 DS −14.9, RC −15.3**; 오도 지시 DS −33.6. BEVDriver 오도 지시 DS −32.5, RC −38.0.
- 두 실패 양상: goal-conflicting collapse(오도 지시를 과추종해 경로 이탈), goal-preserving modulation(모호·잡음 지시가
  회전 커밋 시점을 늦추거나 드리프트).
- **우리와의 대응**: A3(표현 축 실패)를 네 교란으로 체계화할 수 있다. 다만 LMDrive 는 지시를 **너무** 듣고(오도 지시에 끌려감),
  우리는 **안** 듣는다. 같은 축의 양 끝이다.

**SimLingo** (Renz et al.; CVPR 2025 spotlight; arXiv 2503.09594; CARLA 챌린지 2024 우승)
- InternVL2-1B(InternViT-300M + Qwen2-0.5B), 카메라 전용. Bench2Drive DS 85.07 ± 0.95, SR 67.27 ± 2.11 %(이전 최고 DriveAdapter 64.22 / 33.08 %).
- **진단**: "기존 전문가 데이터에 post-hoc 으로 지시-행동 쌍을 붙이면 행동이 시각 단서만으로 추론되므로" 모델이 언어를 무시한다.
  VQA 가 맞아도 행동과 불일치할 수 있고, **정렬된 언어-행동 쌍만이 인과 증거**라고 적는다.
- **Action Dreaming**: 수집 때 시뮬 상태를 저장해 두고, 운동학 자전거 모델 + PID 로 같은 관측에 대한 **다른 지시의 궤적을
  실행 없이 합성**(다른 에이전트는 비반응, 충돌 가능성 검사). 5 종: faster, slower, target speed(0~35 m/s), lane change
  (인도·주차 차선·역방향 포함), object-centric(특정 물체로 향함, 충돌 포함).
- 결과: 드리밍 데이터 없이 평균 **24.5 %**(lane change 3.2 %, objects 21.0 %) → 포함 **81.1 %**(lane change 83.0 %, objects 58.5 %).
- 학습 규모: 3.1M 샘플(4 fps), 8×A100, 14 epoch. 백본 LLM 은 LoRA.
- **우리와의 대응**: 우리 cf-sidecar(운동학 교사로 모든 물체에 반사실 행동 라벨 합성, rp3)는 **같은 발상인데 22/42 로 실패**했다.
  차이 변수: ① 규모(3.1M vs 수만 프레임, 1B vs 450M), ② 지시 종류의 다양성(5 종 vs 이름 하나), ③ 합성 궤적의 물리·충돌 검증,
  ④ 평가(SimLingo 는 dreaming 벤치마크가 오프라인, 우리는 폐루프), ⑤ 7번 문제(미세조정 망각)가 우리 런에 겹쳐 있었음.
  cf-sidecar 실패를 "합성 반사실은 안 된다"로 읽을 수 없고, ①~⑤ 중 무엇인지 좁혀야 한다.

**CAST** (Glossop, Chen, Bhorkar, Shah, Levine; arXiv 2508.13446, 2025-08)
- VLM 으로 같은 관측에 **대체 언어 라벨**을 합성한다(행동은 그대로). 내비 3 환경 + 방해물 조작. 비증강 대비 성공률 2 배.
- SimLingo 는 **행동**을 합성하고 CAST 는 **언어**를 합성한다. 우리 cf-sidecar 는 행동 쪽이었다. 언어 쪽(한 프레임에 여러 참 문장)은
  우리 섹터 프레임별 재라벨(10-08, 23 % 정정)이 부분적으로 해당한다.

### 3.4 말-행동 격차 — 해설은 맞는데 행동이 안 바뀜

| 논문 | 문제 정의 | 방법 | 결과 | 우리와의 대응 |
|---|---|---|---|---|
| **LinkVLA** (arXiv 2603.01441, 2026-03) | "change lane left 라고 결정하고 lane keep 궤적을 낸다" | 언어·행동 공용 이산 코드북 + **행동→언어 캡션 보조 목표(양방향)** + coarse-to-fine 생성 | 지시 준수율·주행 점수 개선, 추론 시간 86 % 단축 | 우리 8번. SANT 의 해설 헤드는 관측→언어 한 방향이고 action expert 가 해설을 읽지 않는다 |
| **DriveMA** (Hang Zhao 그룹; arXiv 2605.31271, 2026-05) | language-action gap | **검증 가능한 meta-action**(미래 자차 운동을 언어 의도로 요약, 규칙으로 궤적과 대조) + 턴 단위 RL | Waymo RFS 8.060(2B) / 8.079(4B) | "해설이 행동과 맞는지"를 규칙으로 검증하는 틀. 우리 해설 정확도(lane 68 % / speed 69 %)는 서술 정확도지 행동 일치율이 아니다 |
| **GRAVA** (arXiv 2609.15169, 2026-09) | 추론이 장면 증거에 약하게 접지되고 행동과 느슨히 연결 | 행동 관련 언어를 2D 영역·물리 상태에 접지, 궤적 앵커 그래프, 사전학습→IL→RL | action-only 대비 key-object compliance +19.3 %, closed-loop DS +20.5 % | 8B 급. "접지된 추론이 행동을 바꾼다"는 주장은 우리 규모에서 검증 안 됨 |
| **BLUE** (EMNLP 2026; arXiv 2606.08684) | 언어가 중요한 프레임은 **소수**, 매 프레임 생성은 낭비 | 0.11M 게이트가 VLA 은닉 상태에서 프레임별 언어 생성 여부 결정 | Bench2Drive SR 76.2 %, 2.54× 가속, 백본 대비 +8.9 % | 우리 08 문서 14.1 "문장이 행동을 바꾸는 프레임은 일부라 평균 손실에서 비중 작음"과 같은 관찰. 손실 재가중의 근거 |
| **Rethinking Language's Role in Efficient VLA for AV** (arXiv 2608.30144, 2026-08) | 언어를 "쓸까"가 아니라 "추론 시 언제·어디서" | L1(학습 때만) / L2(잠재 추론) / L3(조건부 호출) / L4(매 프레임 생성) | 분류·비용 분석 | SANT 해설 헤드는 학습 시 L4, 서빙 시 L1. 해설이 행동에 기여하려면 L2 이상이어야 하는데 구조상 L1 이다 |
| **SteerVLA** (Finn·Levine·Sadigh 그룹; arXiv 2602.08440, 2026-02) | 롱테일 추론과 반응 제어의 결합 | VLM 이 상세 언어 지시를 생성해 VLA 를 조향; VLM 주석으로 데이터 증강 | 폐루프 DS +4.77, 롱테일 +8.04 | 우리 "인지 VLM·이동 VLA" 분업과 같은 구조. 단 **VLA 가 지시를 따른다는 전제**가 필요하고 우리는 그 전제(1·2번)가 아직 없다 |

### 3.5 로봇 VLA 의 반사실·지름길 연구 — 우리 문제에 직접 닿는 것 (10-03 문서 보충)

| 논문 | 핵심 | 우리와의 대응 |
|---|---|---|
| **When Vision Overrides Language** (Fang … Ding; arXiv 2602.17659, 2026-02) | "counterfactual failure" = 언어를 무시하고 잘 배운 행동·자주 본 물체로 간다. LIBERO-CF 벤치마크. **CAG**: 언어 **무조건** vision-action 모듈을 같이 두고 결정 때 대비(새 데이터·구조 변경 없음) → π0.5 언어 정확도 +9.7 %(추가 학습 +15.5 %), 실로봇 반사실 실패 −9.4 % | 우리 b0(상수 문장 모델)가 바로 그 무조건 모듈이다. POLICY_GUIDE(w=3: 27 → 43 %, CI 가 우연 포함)는 같은 계열의 CFG 식 유도 |
| CFG 계열 (언어 드롭아웃 + classifier-free guidance; ACG arXiv 2510.22201, Guided Action Flow arXiv 2607.02092 등) | flow matching 정책에 추론 시 유도. 조건/무조건 속도장 결합 | 우리 w 스윕(w=6 진행)이 이 계열. 학습 때 언어 드롭아웃을 넣었는지가 차이 |
| **VLA-Trace** (arXiv 2605.30117, 2026-05) | π0.5·OpenVLA 의 표현 변화(커널 정렬)·주의 개입·행동 프로브로 모달리티 경로 추적. 시각 접지 궤적은 잘 내지만 **fine-grained semantic following 약함** | 우리 열린 질문 1("action expert 가 prefix 문장 정보를 왜 안 쓰나")을 재는 방법론 |
| **FocusVLA** (arXiv 2603.28740, 2026-03) | VLA-Adapter 식 혼합 주의가 action-query 지름길을 만들어 시각 세부를 건너뜀 → Modality Cascaded Attention 으로 순차 경로 강제 | 구조 자체가 지름길을 허용한다는 관점. SmolVLA cross-attn 경로에서 언어가 어디서 끊기는지 |
| **Evidence-Gated Regularization** (arXiv 2609.03142, 2026-09) | 적은 시연 → "modality entanglement"(센서 간 허위 상관). 프레임·센서별 증거 신호로 불변성/단일 센서 충분성 정규화 | 우리 문장 모달리티를 "증거가 있는 프레임에서만" 강제하는 발상과 같다 |
| STAR-Gen, LIBERO-PRO/Plus/X, DILL, Stable Language Guidance | 1 절·10-03 문서 | — |

### 3.6 미세조정이 사전학습 능력을 지운다 (7번 문제)

| 논문 | 발견 | 처방 | 우리와의 대응 |
|---|---|---|---|
| **ReVLA** (arXiv 2409.15250, 2024-09) | OpenVLA 의 비전 인코더(DINOv2·SigLIP)가 로봇 데이터 미세조정으로 OOD 물체를 못 본다 | 인코더를 사전학습 가중치로 되돌림 → 시각 OOD grasp +77 %, lift +66 % | 우리 v3y 1단계는 비전 인코더까지 전체 학습했다. "사전학습 지식이 파인튜닝 후 얼마나 남는가"(열린 질문 4) |
| **MAPS** (Kira 그룹; arXiv 2511.19878, 2025-11) | 단순 미세조정이 VLM 표현을 깨고 일반화를 해친다; 동결은 과제약 | 모듈별 근접 제약 스케줄(비전은 사전학습 근처, 행동 쪽 언어층은 자유) → ID/OOD 최대 +30 % | s2 에서 r26 방향 반응이 0.82 → 0.04 로 사라진 것은 비전 동결 상태였으므로 **언어모델·action expert 쪽 망각**이다 |
| *Can VLA Learn Continually without Forgetting?* (arXiv 2605.26820) | 실세계 지속 학습에서 망각 | — | r26 → goto 미세조정이 지속 학습 상황 |

7번은 1·2번과 얽혀 있다. r50~r54·b1·s2 가 모두 베이스 반응을 지운 상태에서 측정됐으므로, **망각을 막은 런(stock 베이스 s3,
또는 근접 제약 런)에서 다시 재야** "문장을 읽는가"를 말할 수 있다. 10-08 22:37 계획의 s3/s3n 이 그 첫 시험이고, 결과는 이 문서
작성 시점(10-09 15:30)에 아직 기록되지 않았다.

### 3.7 RL 후학습과 분포 밖 (6번 문제의 후보)

- AlphaDrive(GRPO 를 주행에 처음 도입), ReCogDrive·DriveFine(SFT → NAVSIM 에서 RFT), Poutine, DriveMA, GRAVA 가 공통으로
  "IL 은 반례의 음성 감독이 없어 OOD 에 약하다 → RL 로 보완"을 말한다.
- 우리 정차(교사 standoff 2.2 m 를 못 지킴, STRICT 0/120)나 희소 정지 행동처럼 **시연 평균으로는 안 나오는 정밀 행동**에
  보상 기반 후학습이 후보다. 단 위 연구는 1B~8B 급이고 시뮬레이터 보상이 필요하다. 우리 Gazebo 폐루프에서 가능한지는 별도 문제.

---

## 4. 우리 문제 ↔ 논문 대응표

| #   | 우리 문제                   | 같은 문제를 다룬 논문                                                                    | 그 논문의 처방                               | 우리에게 남는 질문                     |
| --- | ----------------------- | ------------------------------------------------------------------------------- | -------------------------------------- | ------------------------------ |
| 1   | 문장 유무 구별 안 됨            | SimLingo, When Vision Overrides Language, LIBERO-Plus, Stable Language Guidance | 같은 관측에 다른 지시→다른 행동 짝(합성), 무조건 모델 대비 유도 | cf-sidecar 는 왜 실패했나(3.3 절 ①~⑤) |
| 2   | 이름·섹터는 못 듣고 효과 크기 0.2 배 | STAR-Gen(SB 명사 접지가 가장 약함), VLA-Trace, CAG                                       | 추론 시 유도, 경로 추적                         | 유도로 2.73 m 간격을 넘을 수 있나; 지속 커밋  |
| 3   | 처음 보는 표현 실패             | ICR-Drive, LangAuto, CAST                                                       | 패러프레이즈 다양화 데이터, 네 교란 평가                | A3 를 네 교란으로 재평가                |
| 4   | 자리 습관·방향 편향             | Fail2Drive("외운 차선 추종"), Is Ego Status All You Need, 카피캣, DILL                   | 짝 라우트 평가, 허위 상관 분리 표현                  | 짝 시연 외의 처방(표현 분리) 시험 안 함       |
| 5   | 홀드아웃 배치 무반응             | Fail2Drive(visual-lateral −33.6 %p), LIBERO-PRO(위치 교란 0 %)                      | 데이터 다양화(LIBERO-Plus 2만 궤적), LiDAR 융합   | 교수님 방침: E2E 만, 인지 분리형 금지       |
| 6   | 희소·새 행동 미획득             | Fail2Drive(behavioral −53.6 %p), Codevilla 관성 문제, RL 후학습 계열                     | 보상 기반 후학습                              | Gazebo 에서 RL 보상 루프 가능한가        |
| 7   | 미세조정이 베이스 반응 파괴         | ReVLA, MAPS                                                                     | 되돌림, 근접 제약                             | s3(stock 베이스) 결과; 근접 제약 런      |
| 8   | 해설은 맞고 행동 무반응           | LinkVLA, DriveMA, GRAVA, BLUE, Rethinking Language's Role                       | 양방향 목표, 검증 가능한 메타 행동, 언어 중요 프레임 게이트    | SANT 해설 헤드는 L1 — 행동에 닿는 경로가 없다 |
| 9   | 교차 트랙·실차                | DriveVA, Zero-Shot Across Embodiments, VLA-R                                    | 비디오 사전, BEV 보조, 검색                     | 교차 트랙 제로샷 미측정                  |

---

## 5. 시사점 (가설 단계 — 실험 전에 기각선을 적는다)

1. **반사실 짝 데이터는 두 길이 있다.** 합성 행동(SimLingo, 24.5 → 81.1 %)과 합성 언어(CAST, 2 배). 우리 cf-sidecar 는
   합성 행동 쪽에서 22/42 로 실패했는데, 당시 런은 7번(망각)을 동반했고 지시 종류가 하나였다. "합성 반사실은 안 된다"는
   결론은 아직 성립하지 않는다. 먼저 7번을 뺀 베이스에서 같은 cf-sidecar 를 다시 재는 것이 가장 싸다.
   - 기각선 예: 망각 없는 베이스 + cf-sidecar 가 상수 문장 대조군과 n=42 에서 유의 차 없으면 합성 행동 길은 접는다.
2. **무조건 모델 대비 유도(CAG)는 이미 재료가 있다.** b0/s3n 이 무조건 모델이다. CAG 는 "학습 없이 +9.7 %"를 보고했으므로
   우리 w 스윕과 같은 실험이다. 단 CI 가 우연을 포함하면(현재 w=3) 효과로 적지 않는다.
3. **언어가 중요한 프레임만 가중.** BLUE 의 관찰(언어가 행동을 바꾸는 프레임은 소수)은 우리 14.1 절과 같다. 섹터 전환·분기
   프레임의 행동 손실만 가중하는 것은 데이터 재수집 없이 가능하다.
4. **망각 분리가 선행.** ReVLA·MAPS 가 보여 주듯 미세조정은 사전 능력을 지운다. 1·2번의 모든 실패 런이 7번과 겹쳐 있었으므로,
   s3/s3n(stock 베이스) 결과가 나오기 전에는 "SmolVLA 는 이름을 못 듣는다"고 쓸 수 없다. 쓸 수 있는 것은 "r26 에서 출발한
   goto 미세조정은 베이스 방향 반응을 지우며, 그 상태에서 문장 효과는 측정되지 않았다"까지다.
5. **평가 틀은 이미 논문과 같다.** Fail2Drive 의 짝 라우트 = 같은-자리 대조군, ICR-Drive 의 네 교란 = A3 의 체계화,
   CAG/LIBERO-CF 의 반사실 = 우리 문장 반사실 프로브. 이 대응을 논문·강좌에서 그대로 인용하면 된다.
6. **강좌 한 문장의 근거 수치.** "VLA 가 넓히는 것은 의미, 행동은 시연 범위" 에 Fail2Drive 의 behavioral −53.6 %p 와
   STAR-Gen 의 "의미 축이 가장 약함"을 붙이면, 두 축이 **둘 다** 어렵다는 것까지 정직하게 말할 수 있다.

---

## 6. 범위와 출처

**확인 수준.** 아래 논문은 2026-10-09 에 arXiv 초록 또는 HTML 본문을 읽고 수치를 옮겼다: STAR-Gen, Fail2Drive, ICR-Drive, SimLingo,
CAST, When Vision Overrides Language, LinkVLA, DriveMA, GRAVA, BLUE, Rethinking Language's Role, SteerVLA, VLA-R, DriveVA,
Zero-Shot Across Embodiments, VLA-Trace, Evidence-Gated Regularization, MAPS, Past-Present-Future 서베이.
**검색 요약에만 기댄 것**(인용 전 원문 대조 필요): LangAuto 세부(오도 지시 5 %), AlphaDrive·ReCogDrive·DriveFine, FocusVLA,
ReVLA 수치(+77 / +66 %), Jiang 서베이의 열린 과제 목록, Impromptu VLA·Poutine 세부. LIBERO 계열·DILL·고전 BC 연구는 10-03 문서를 따른다.

**우리 수치의 범위.** 모두 Gazebo 단일 트랙, SmolVLA 약 450M, 폐루프 n=30~55 다. 언어 조건은 열린 자연어가 아니라 이산 모드
(차선 2 × 속도 3; goto 는 섹터 3분류)다. s3/s3n 결과는 이 문서에 없다.

**링크.**
- STAR-Gen: https://arxiv.org/abs/2503.01238 · 사이트 https://stargen-taxonomy.github.io/
- Fail2Drive: https://arxiv.org/abs/2604.08535
- ICR-Drive: https://arxiv.org/abs/2604.05378
- SimLingo: https://arxiv.org/abs/2503.09594 · 코드 https://github.com/RenzKa/simlingo
- CAST: https://arxiv.org/abs/2508.13446
- When Vision Overrides Language (CAG): https://arxiv.org/abs/2602.17659
- LinkVLA: https://arxiv.org/abs/2603.01441
- DriveMA: https://arxiv.org/abs/2605.31271
- GRAVA: https://arxiv.org/abs/2609.15169
- BLUE: https://arxiv.org/abs/2606.08684
- Rethinking Language's Role: https://arxiv.org/abs/2608.30144
- SteerVLA: https://arxiv.org/abs/2602.08440
- VLA-R: https://arxiv.org/abs/2511.12405
- DriveVA: https://arxiv.org/abs/2604.04198
- Zero-Shot Across Embodiments: https://arxiv.org/abs/2609.02341
- VLA-Trace: https://arxiv.org/abs/2605.30117
- Evidence-Gated Regularization: https://arxiv.org/abs/2609.03142
- FocusVLA: https://arxiv.org/abs/2603.28740
- ReVLA: https://arxiv.org/abs/2409.15250 · MAPS: https://arxiv.org/abs/2511.19878 · 지속학습: https://arxiv.org/abs/2605.26820
- Impromptu VLA: https://arxiv.org/abs/2505.23757 · Poutine: https://arxiv.org/abs/2506.11234
- LMDrive: https://arxiv.org/abs/2312.07488
- 서베이: Jiang et al. https://arxiv.org/abs/2506.24044 · Past/Present/Future https://arxiv.org/abs/2512.16760 ·
  Action-grounded reasoning https://arxiv.org/abs/2609.01659
- CFG 계열: ACG https://arxiv.org/abs/2510.22201 · Guided Action Flow https://arxiv.org/abs/2607.02092
