# Manuscript data

원본 평가 artifact에서 현재 원고의 그림, 표, 본문 수치를 재생성하는 작은 CSV/JSON과
lineage 기록을 둔다.

- `factorial_wording_analysis.json`: 20개 matched observation과 8개 cell의 factorial 설계,
  raw/zero-initial-command bridge-transform 결과, 50,000회 paired bootstrap 효과
- `factorial_wording_cells.csv`: factorial cell별 요약
- `factorial_wording_effects.csv`: T, L, S 주효과와 상호작용 효과
- `closed_loop_pairs.csv`: Base와 T+L+S, inner/outer 시작점, AB/BA 순서를 균형화한
  32개 rollout의 paired distance와 실행 유효성
- `lane_reference_adherence.csv`: 각 rollout의 15 m 이후 requested-lane reference 거리
- `experiment_summary.json`: 원고에서 사용하는 실행 계약과 폐루프 집계
- `training_instruction_inventory.txt`: 복구한 v6 학습 instruction 목록
- `training_inventory_audit.json`: dataset metadata, steering-state 통계, 평가 문구 포함 여부,
  test wording pair 선택 시점 기록
- `checkpoint_identity.json`: offline probe와 closed-loop 평가 checkpoint의 SHA-256 동일성

원본 factorial JSON은 `eval_out/icce2026_factorial/`에, balanced closed-loop JSON과 로그는
`eval_out/icce26_bal_*`에 보존한다. `archive/`에는 현재 원고에서 사용하지 않는 pilot 또는
legacy 요약만 둔다.
