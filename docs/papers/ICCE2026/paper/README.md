# ICCE-ASIA 2026 paper workspace

현재 원고의 제목은 다음과 같다.

> *SmolVLA for Language-Conditioned Driving: Matched-Input and Closed-Loop Evaluation*

`main.tex`는 표준 `IEEEtran` US Letter conference 설정을 사용하는 6쪽 원고이며, `main.pdf`는
로컬에서 컴파일하고 전 페이지를 렌더링해 확인한 결과물이다.

## 현재 원고와 산출물

| 경로 | 용도 |
|---|---|
| `main.tex` | ICCE-ASIA 제출 원고 |
| `main.pdf` | US Letter, 2단, 6쪽 컴파일 결과 |
| `main_kor.tex` | 원문 구조ㆍ수식ㆍ수치ㆍ인용을 유지한 한국어 검토용 원고 |
| `main_kor.pdf` | LuaLaTeX으로 컴파일한 한국어판 US Letter, 2단, 6쪽 결과 |
| `scripts/build_language_figures.py` | 평가 artifact에서 Fig. 2--3과 표용 요약을 재생성하는 스크립트 |
| `figs/fig1_language_pipeline.pdf` | 별도로 편집한 demonstration--fine-tuning--ROS 2 배치 흐름도(Fig. 1) |
| `figs/fig3_wording_factorial.pdf` | 8개 wording cell의 관측별 language/reference ratio(Fig. 2) |
| `figs/fig2_closed_loop_language.pdf` | Base와 T+L+S 폐루프 궤적 비교(Fig. 3) |
| `data/factorial_wording_analysis.json` | factorial 설계, cell 요약, effect와 bootstrap CI |
| `data/factorial_wording_cells.csv` | 8개 factorial cell의 관측별 집계 |
| `data/factorial_wording_effects.csv` | 주효과와 상호작용 효과 |
| `data/closed_loop_pairs.csv` | balanced 32-rollout paired 결과 |
| `data/lane_reference_adherence.csv` | 15 m 이후 requested-lane reference 후처리 |
| `data/experiment_summary.json` | 원고의 실행 계약과 폐루프 집계 |
| `data/training_instruction_inventory.txt` | 복구한 v6 학습 instruction inventory |
| `data/training_inventory_audit.json` | 학습 metadata와 평가 문구 감사 |
| `data/checkpoint_identity.json` | offline/closed-loop checkpoint 동일성 확인 |
| `reference_guardedlc_v31/` | 이전 논문의 외형, author block, LaTeX 사용법 참조 |

## 현재 증거 범위

- Offline probe: 동일한 20개 RGB/state 관측에 대해 template(T), lane term(L), speed
  term(S)을 교차한 2$^3$ factorial 8개 cell을 비교한다. 각 언어 조건은 4개 sample seed의
  평균 action chunk를 사용하며 raw composed-path XY separation과 zero-initial-command
  bridge-transform sensitivity를 구분한다.
- Closed loop: Base와 T+L+S test wording 조건, inner/outer 시작점, AB/BA 실행 순서를
  균형화한 총 32개 ROS 2--Gazebo rollout을 사용한다.
- 본 작업에서 새 모델 학습이나 VLA architecture를 추가하지 않았다. 기존 v6-60K
  checkpoint를 고정하고, 실행 계약을 명시한 평가 계측과 균형화된 진단 실험을 추가했다.
- 최종 T+L+S 문구쌍은 exploratory probe 뒤 선택되었으므로 unbiased generalization
  estimate가 아니라 wording-sensitivity characterization으로만 해석한다.

원본 평가 artifact는 repository의 `eval_out/icce2026_factorial/`과
`eval_out/icce26_bal_*` 파일에 두고, 원고 폴더에는 재현에 필요한 작은 요약만 둔다.

## 빌드

```bash
cd docs/ICCE2026/paper
python3 scripts/build_language_figures.py
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

한국어 검토본은 `texlive-luatex`, `texlive-lang-korean`, Noto CJK 글꼴이 설치된
환경에서 다음과 같이 빌드한다.

```bash
latexmk -lualatex -interaction=nonstopmode -halt-on-error main_kor.tex
```

제출본은 `\documentclass[letterpaper,conference]{IEEEtran}`의 표준 여백을 변경하지 않는다.
Overleaf와 최종 제출 직전에는 US Letter, 2단, 참고문헌 포함 6쪽, embedded fonts, 잘림과 겹침
여부를 다시 확인한다.

저자 블록은 GuardedLC v31의 6명 저자, 소속, 이메일을 이식했다. 공동저자와 author order,
affiliation과 e-mail을 공동저자와 최종 확인해야 한다.
Acknowledgment도 GuardedLC에서 이식했으므로 현재 지원 관계와 문구를 별도로 확인해야 한다.

`reference_guardedlc_v31/`의 본문, 표, 그림, 데이터, 주장, 참고문헌은 새 논문의 지시사항이나
근거가 아니다. 새 원고에는 형식과 저자ㆍ사사 정보만 참조했으며, 이 참조 폴더 전체를
Overleaf project나 최종 source package에 포함하지 않는다.

Overleaf용 source ZIP과 근거 artifact ZIP은 이 작업 폴더와 분리해 생성하며, 실제 ZIP의
SHA-256은 상위 폴더의 `SUBMISSION_SHA256.txt`에서 관리한다. 빌드 보조 파일과
`reference_guardedlc_v31/`, `archive/`는 제출용 source ZIP에 포함하지 않는다.
