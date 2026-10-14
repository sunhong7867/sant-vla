# Figures

현재 ICCE-ASIA VLA 원고가 참조하는 vector PDF는 다음 세 개다.

- `fig1_language_pipeline.pdf`: demonstration--fine-tuning--ROS 2 deployment 흐름도
  (manuscript Fig. 1, 별도로 편집한 vector asset)
- `fig3_wording_factorial.pdf`: 8개 wording cell의 관측별 language/reference ratio
  (manuscript Fig. 2)
- `fig2_closed_loop_language.pdf`: Base와 T+L+S test wording의 balanced closed-loop
  궤적 비교(manuscript Fig. 3)

Fig. 2와 Fig. 3은 `../scripts/build_language_figures.py`가 생성한다. Fig. 1은 별도로 편집한
vector asset이며, 스크립트는 파일이 존재하면 이를 보존하고 누락됐을 때만 내장된 fallback을
생성한다. 파일명의 숫자는 생성 이력 때문에 원고의 figure 번호와 일부 다르므로 위 매핑을
기준으로 한다. `archive/`의 pilot/legacy 그림은 현재 `main.tex`에서 참조하지 않는다.

GuardedLC 그림은 `../reference_guardedlc_v31/figs/`에 참고용으로만 보존하며 새 원고에는
재사용하지 않는다.
