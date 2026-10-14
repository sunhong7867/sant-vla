# docs — 폴더 안내

> 2026-10-07 재배치. 예전 경로 → 새 경로는 맨 아래 표 참고.

| 폴더 | 무엇을 두나 | 예 |
|---|---|---|
| [guides/](guides/) | **사용법·시스템 구조.** 실행 방법, 서버, 입출력 계약, 패키지 역할 | [quickstart](guides/quickstart.md), [servers](guides/servers.md), [io_contract](guides/io_contract_state_action_twist.md), [VLA 완전 정복 가이드](guides/vla_complete_guide_ko.md) |
| [plans/](plans/) | **계획서·로드맵.** 앞으로 할 일의 설계 | [sim_vla_plan](plans/sim_vla_plan.md), [vla_readiness_and_roadmap](plans/vla_readiness_and_roadmap.md) |
| [experiments/](experiments/) | **실험 기록.** 아래 하위 폴더로 나눔 | |
| ├ [log/](experiments/log/README.md) | 날짜별 변경·실험 기록 (`YYYYMMDD_HHMM_제목.md`, 메인 노트북) | |
| ├ [log_thor/](experiments/log_thor/README.md) | 같은 형식, Jetson Thor 세션에서 쓴 기록 | |
| ├ [avoidance/](experiments/avoidance/README.md) | 장애물 회피 연구 묶음 | |
| ├ [goto_object/](experiments/goto_object/README.md) | 말로 지정한 물체로 가기 (강좌 실습 연구) | |
| ├ [model_compression/](experiments/model_compression/) | 양자화 실험 계획·결과 | [SmolVLA PTQ 실험계획](experiments/model_compression/smolvla_ptq_실험계획.md) |
| └ [reports/](experiments/reports/) | 날짜 파일이 아닌 종합 보고서·버전 대장·능력표 | [reasoning_versions](experiments/reports/reasoning_versions.md), [nl_capability_matrix](experiments/reports/nl_capability_matrix.md), [10-03~10-08 경과](experiments/reports/research_report_20261003_20261008.md), [일반화 3축·주행 VLA 연구](experiments/reports/20261009_1530_generalization-axes-and-driving-vla-related-work.md), [조합 일반화 홀드아웃 설계](experiments/reports/20261009_1559_composition-generalization-holdout-plan.md), [조합 일반화 홀드아웃 결과](experiments/reports/20261010_0212_composition-generalization-holdout-result.md) |
| [study/](study/) | **내 공부 정리.** 연구 결과가 아닌 개념 학습 | [양자화·프루닝 개념정리](study/model_compression/양자화_프루닝_개념정리.md) |
| [course/](course/) | **단기강좌** 기획·실습·강의용 설명 자료 | [단기강좌](course/단기강좌.md), [실습 정하기](course/실습%20정하기.md) |
| [papers/](papers/) | 논문 원고·증빙 (ICCE 2026) | [ICCE2026](papers/ICCE2026/README.md) |
| [assets/](assets/) | 그림 등 문서에서 쓰는 파일 | rosgraph |

## 어디에 쓸까

- 코드를 바꿨거나 실험을 한 번 돌렸다 → `experiments/log/` 에 날짜 파일 추가 (README 목록에도 한 줄, `tools/check_ver_index.sh` 로 확인)
- 한 주제로 여러 번 실험한다 → `experiments/<주제>/` 폴더를 만든다 (avoidance, goto_object, model_compression 처럼)
- 실험 전에 설계만 정리한다 → 주제 폴더 안에 계획 문서, 전체 방향이면 `plans/`
- 남에게 설명하거나 다시 볼 사용법 → `guides/`
- 공부한 개념 → `study/<주제>/`

## 예전 경로 → 새 경로

| 예전 | 새 경로 |
|---|---|
| `docs/ver/` | `docs/experiments/log/` |
| `docs/ver2/` | `docs/experiments/log_thor/` |
| `docs/avoidance_research/` | `docs/experiments/avoidance/` |
| `docs/model_compression/plan/` | `docs/experiments/model_compression/` |
| `docs/model_compression/theory/` | `docs/study/model_compression/` |
| `docs/ICCE2026/`, `ICCE2026_*.zip` | `docs/papers/` |
| `docs/rosgraph/` | `docs/assets/rosgraph/` |
| `docs/course/cleanup.md` | `docs/guides/cleanup.md` |
| 최상위 `*.md` | 내용에 따라 `guides/`, `plans/`, `experiments/reports/`, `course/` |
