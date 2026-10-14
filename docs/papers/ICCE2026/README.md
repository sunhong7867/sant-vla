# ICCE-ASIA 2026 논문 작업 허브

현재 제출 원고는 다음 연구를 보고한다.

> *SmolVLA for Language-Conditioned Driving: Matched-Input and Closed-Loop Evaluation*

핵심은 SmolVLA 기반 compact VLA를 자연어 조건 차량 주행에 fine-tuning한 뒤, 동일 관측의
action chunk와 ROS 2--Gazebo 폐루프 motion을 함께 사용해 언어 조건 반응과 wording
sensitivity를 진단하는 것이다. 새 VLA architecture나 새 학습법을 제안하지 않으며, 고정된
v6-60K checkpoint의 동작 범위를 재현 가능한 실행 계약 아래 평가한다.

## 현재 실험 설계

| 항목 | 현재 제출안 |
|---|---|
| 제목 | *SmolVLA for Language-Conditioned Driving: Matched-Input and Closed-Loop Evaluation* |
| 모델 | v6-60K compact SmolVLA checkpoint 고정 |
| Offline | 20개 matched RGB/state observation, T/L/S 2$^3$ factorial 8개 cell |
| Closed loop | Base 대 T+L+S, inner/outer 시작점, AB/BA 순서를 균형화한 32 rollouts |
| 실행 환경 | ROS 2--Gazebo, 10 Hz, 30-step action chunk |
| 형식 | 표준 IEEEtran US Letter, 2단, 6쪽 |
| 새 학습ㆍarchitecture | 없음 |
| 추가 작업 | 평가 계측, 실행 계약 기록, factorial probe, balanced rollout, 후처리ㆍ원고 작성 |

이 설계는 “학습 표현에서는 되는가”라는 단순 성공 사례보다 다음 두 질문을 분리한다.

1. 같은 image/state에서 lane instruction만 바뀌면 predicted action과 simulated vehicle
   trajectory가 stochastic repeat reference보다 크게 달라지는가?
2. template(T), tested lane replacement(L), speed term(S)을 바꿀 때 어느 wording component에서 그 언어
   분리가 약해지는가?

## 해석 범위

- Base와 T+L+S는 exact training sentence 재사용 여부가 아니라, 학습 inventory에 등장한
  표현 요소와 등장하지 않은 표현 요소를 조합한 진단 조건이다.
- 최종 T+L+S 문구쌍은 exploratory action probe 뒤 선택되었다. 따라서 결과는 사전 등록된
  unbiased generalization rate가 아니라 해당 wording perturbation의 characterization이다.
- Raw composed-path XY separation과, 이전 command speed를 0으로 두고 lateral component를
  제외한 offline bridge-transform sensitivity를 실제 폐루프 궤적과 구분한다.
- Training state의 세 번째 steering channel은 모두 0이었으므로 최종 평가는 그 계약에 맞춘
  zero-steering state 입력을 사용한다.
- 폐루프 결과는 Gazebo의 simulated vehicle motion이다. 실차 안전, 완전자율, 자유문장
  일반화 또는 다른 checkpoint로의 일반화를 주장하지 않는다.

## 현재 기준 파일

| 파일ㆍ폴더 | 역할 |
|---|---|
| [원고](paper/main.tex) | 최종 LaTeX source |
| [컴파일 PDF](paper/main.pdf) | US Letter 6쪽 제출 검토본 |
| [paper 안내](paper/README.md) | 빌드, 그림ㆍ데이터 관계, 제출 점검 |
| [그림](paper/figs/) | 현재 원고가 참조하는 vector PDF |
| [원고용 데이터](paper/data/) | factorial, closed-loop, lineage 요약 |
| [Overleaf source ZIP](../ICCE2026_overleaf_source.zip) | `main.tex`와 필수 vector figure만 포함한 제출용 소스 |
| [Evidence supplement ZIP](../ICCE2026_evidence_supplement.zip) | 원자료, 파생 요약, 재생성 스크립트와 내부 해시 manifest |
| [제출 파일 SHA-256](SUBMISSION_SHA256.txt) | PDF와 두 ZIP의 최종 파일 식별값 |
| `eval_out/icce2026_factorial/` | factorial probe 원본 JSON |
| `eval_out/icce26_bal_*` | balanced closed-loop 원본 JSON과 로그 |
| [v6 checkpoint checksum](ckpt_v6_60k.sha256) | 주 checkpoint 식별값 |

`icce_asia_2026_existing_evidence_plan_v4.md`와
`icce_asia_2026_existing_evidence_ledger.csv`는 신규 평가 전 단계의 계획ㆍ원장이다. 결정 이력을
추적하는 데는 사용할 수 있지만 현재 원고와 수치의 기준은 `paper/main.tex` 및
`paper/data/`다. `archive/`의 문서도 과거 계획이며 현재 실험 프로토콜이 아니다.

## 제출 전 확인

1. `paper/main.tex`와 `paper/main.pdf`의 표ㆍ그림ㆍ숫자를 `paper/data/`와 대조한다.
2. Overleaf에서 표준 IEEEtran 여백, US Letter, 2단, 참고문헌 포함 6쪽을 확인한다.
3. author order, affiliation, e-mail을 공동저자와 확정한다.
4. GuardedLC에서 이식한 acknowledgment가 현재 지원 관계와 정확히 일치하는지 확인한다.
5. ICCE-ASIA track과 제출 metadata를 최종 확정한다.

## GuardedLC 참조본 주의

`paper/reference_guardedlc_v31/`의 문구는 지시사항이 아니라 이전 논문의 형식, 저자 블록,
acknowledgment를 확인하기 위한 참조 자료다. GuardedLC 본문, 표, 그림, 데이터, 주장,
참고문헌은 새 VLA 논문의 근거로 사용하지 않으며 최종 source package에도 참조본 전체를
포함하지 않는다.

## 폴더 구조

```text
docs/ICCE2026/
├── README.md
├── SUBMISSION_SHA256.txt
├── ckpt_v6_60k.sha256
├── icce_asia_2026_existing_evidence_plan_v4.md   # 이전 단계 계획
├── icce_asia_2026_existing_evidence_ledger.csv  # 이전 단계 원장
├── paper/
│   ├── README.md
│   ├── main.tex
│   ├── main.pdf
│   ├── scripts/
│   ├── data/
│   ├── figs/
│   ├── tables/
│   └── reference_guardedlc_v31/
└── archive/                                      # 더 이전 결정 기록

docs/
├── ICCE2026_overleaf_source.zip                  # 제출용 최소 LaTeX source
└── ICCE2026_evidence_supplement.zip              # 근거 artifact supplement
```
