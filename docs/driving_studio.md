# Driving Studio — 통합 VLA 콘솔

```bash
sh /home/sh/ROS2_project/sant-vla/smolvla_demo.sh
```

하나의 PySide6 창 안에 실제 Gazebo 3D, BEV, 전방 카메라, 드라이빙 채팅,
모델 reasoning을 표시합니다. 창이 먼저 열리고 시뮬레이터와 모델이 준비되는
단계가 표시됩니다. 제어 브리지 연결 전에는 출발을 전송하지 않습니다.
시뮬레이션은 왼쪽의 가장 큰 영역을 사용하고, 속도·목표 차선·주행 상태·추론
지연과 시점·경기 설정은 오른쪽의 작은 제어 패널에 모았습니다.
탑뷰에서는 창과 구역 크기를 바꾸면 트랙 전체가 보이도록 배율을 다시 맞춥니다.

## 모델 연결

기본 원격 모델은 랩서버의
`runs/navvla_reasoning_r11/checkpoints/025000/pretrained_model`입니다.
이전 v6 기본 경로는 서버에서 삭제되어 GUI만 열리고 정책 서버가 시작되지
않았습니다. 새 실행 절차는 모델 파일, 정책 서버 준비, SSH 터널,
ROS 제어 브리지 응답을 확인한 뒤 준비 완료로 표시합니다.
체크포인트의 상태 차원을 읽어 r11의 4차원 standstill 입력을 맞춥니다.
`NAVVLA_REASONING_EVERY`는 reasoning 생성 간격이며 기본값은 4입니다.

원격 체크포인트를 바꾸려면 `REMOTE_CKPT`를 지정합니다. 원격 모드에서는
로컬 정책 Python이나 로컬 모델 파일이 필요하지 않습니다.
`LOCAL_VLA=1`이면 로컬 모델을 사용하며 Python 선택 순서는
`NAVVLA_PYTHON` → `NAVVLA_VENV` → 활성 가상환경/Conda → 프로젝트 `.venv`
→ `~/venv/navvla`입니다. `sh smolvla_demo.sh check`는 로컬 실행 조건을
점검합니다(원격 서버 연결 검사는 실제 실행 시 수행).

## 화면과 조작

- **시뮬레이션**: 처음에는 트랙 전체를 위에서 보는 탑뷰입니다.
  전체 탑뷰·대각선·차량 추적·왼쪽 뒤·오른쪽 뒤(차선 밟음 확인용 낮은 대각선 추적) 시점을 지원하며, 휠 확대/축소,
  드래그 이동, Shift+드래그 회전도 가능합니다. 시점 변경은 실제
  `/gui/move_to/pose`와 `/gui/follow` 서비스로 실행합니다.
  `/gui/camera/pose`는 카메라 위치를 읽는 출력 토픽입니다.
- **시뮬레이션 제어**: 시점 도구 아래 별도 줄에 일시정지·재개와
  경기 선택·리셋이 있습니다. 일시정지 중에는 마지막 카메라와 BEV를 유지합니다.
- **BEV**: 기준 차선, 파란 실제 궤적, 민트색 VLA 예측점, 주황색 장애물
  차량을 표시합니다. 차량 중심 보기·지도 회전·확대·이동을 지원합니다.
  장애물은 출발 전에도 표시되며 경기 변경 시 자동 갱신됩니다.
- **차량 카메라**: `/camera/image_raw`의 영상에 VLA 예측 경로 점을
  겹쳐 표시합니다. Prius SDF의 카메라 위치·방향·화각으로 지면 경로를
  투영하며, 카메라 뒤쪽이나 화면 밖의 점은 표시하지 않습니다.
- **채팅**: 사용자 입력은 오른쪽, 주행 응답은 왼쪽입니다. 출발·안쪽·바깥쪽
  단축 버튼은 제거했습니다. 음성 입력을 누르면 녹음하고 다시 누르면
  인식합니다(최대 30초). 인식 후 자동 전송을 끄면 입력란에서 수정할 수
  있습니다. 정지는 느린 명령 해석이나 음성 인식 결과를 취소합니다.
- **Reasoning**: `/vla/reasoning` 모델 출력, 별도 모듈의 장면 해설,
  상태 로그를 각각 표시합니다. 모델 발화는 그대로 표시되므로 내용의
  정확성은 모델 평가 대상입니다.

BEV 기준 차선은 `track_paths.json`입니다. 민트 경로는 영상에서 검출한
차선 분할 결과가 아니라 VLA의 `dx, dy, dyaw` 예측을 누적한 것입니다.
Prius의 전진 방향은 모델 -Y이므로 Gazebo yaw에서 90도를 보정합니다.
제어 브리지의 속도·곡률 보정 전 출력이라 실제 궤적과 다를 수 있습니다.
화면 구역의 경계를 드래그하면 크기를 조절할 수 있습니다.

### 경로의 지속 갱신

현재 r11은 30점, 약 3초 분량을 한 번에 예측합니다. 기존에는 제어 큐가
약 70% 소진된 뒤에만 다시 추론했기 때문에 화면 앞쪽 경로가 짧아지고,
카메라 아래로 사라지는 구간이 있었습니다.

데모는 `display_preview_period:=0.4`로 화면용 모델 예측을 추가로 요청합니다.
`/vla/preview`의 새 예측으로 BEV와 카메라를 지속 갱신하고, 차량 제어는
기존 `/vla/plan`과 제어 큐의 재계획 조건을 유지합니다. 제어 요청이 먼저
처리되며, 여유 시간이 충분할 때 화면용 추론을 수행합니다.
따라서 30점보다 먼 미학습 구간을 덧붙이는 대신 앞으로 볼 수 있는
약 3초 구간을 계속 새롭게 유지합니다.

각 예측에는 추론 요청 당시의 차량 위치를 함께 넣어, 추론 지연 동안
차량이 이동한 거리만큼 표시가 앞으로 밀리지 않도록 했습니다.
정지·경기 리셋·명령 변경 후 늦게 도착한 이전 응답은 버립니다.
브리지 기본값은 `display_preview_period:=0.0`이므로 별도 평가 실행에서는
기존 추론 스케줄을 유지합니다. 원격 서버 코드나 모델 파일 전송은 없습니다.

## 경기 배치

`src/sant_vla_pkg/config/race_scenarios.json`에 Blender 저장 좌표를 정리했습니다.
원본 Blender 파일은 수정하지 않았습니다. 애니메이션 파일은 첫 프레임을
기준으로 하며 장애물 메시의 로컬 회전도 반영합니다.

| 경기 | Blender 원본 (`output/blender/` 기준) | 초기 배치 |
|---|---|---|
| 예선 | `nav_vla_driving_ego_only.blend` | Start 2차선, 자차 1대 |
| 본선·토너먼트 | `tournament/tournament_animated.blend` | Start/T3, 자차와 상대 차량 |
| 미션 1 | `mission/mission_animated_v3.blend` | M3, 장애물 3대, 초록 신호 |
| 미션 2 | `nav_vla_parking.blend` | IN, 주차 기준 차량 4대 |

선택을 바꾸거나 경기 리셋을 누르면 현재 명령을 취소하고, 시뮬레이션을
잠시 정지한 뒤 기존 경기 차량을 제거하고 선택한 배치를 생성합니다.
생성된 차량과 자차의 출발 좌표를 확인한 뒤 시뮬레이션을 재개합니다.
주행은 정지 상태로 유지되며 새 출발 명령이 필요합니다. 실제 궤적과
이전 예측도 지웁니다. 초기 경기는 `NAVVLA_RACE=qualifying|tournament|mission1|mission2`
환경변수로 지정할 수 있습니다.

규정집 v3.1의 예선/본선 출발 지점 및 미션 배치를 참고했습니다.
이는 경기 환경 재설정 기능입니다. 상대 차량 자동 주행, 경기 채점,
신호의 자동 전환, 수직·평행주차 정책 학습을 추가한 것은 아닙니다.
현재 r11 모델은 주차를 지원하지 않으며 미션 2는 배치를 확인할 수 있습니다.

## 설치와 로그

Linux X11 또는 XWayland가 필요합니다.
GUI를 실행하는 Python 환경에 설치하고 패키지를 빌드합니다.

```bash
python3 -m pip install -r requirements-dashboard.txt
source /opt/ros/jazzy/setup.bash
source install/setup.bash
colcon build --packages-select sant_vla_pkg simulation_pkg
```

음성 인식은 CPU의 faster-whisper를 사용하며, 처음 사용하는 모델은
다운로드가 필요할 수 있습니다. `SANT_VLA_WHISPER_MODEL`로 모델을 지정할 수 있습니다.

- 기본 통합 창: `sh smolvla_demo.sh`
- 기존 창 구성: `sh smolvla_demo.sh --legacy-gui`
- 창 없이 실행: `sh smolvla_demo.sh --no-gui`
- 전체 종료: `sh smolvla_demo.sh down`

창을 닫으면 정지 명령을 보내고 자신이 띄운 Gazebo GUI를 종료합니다.
경기 재설정 도중 닫으면 재설정 정리를 마친 뒤 닫습니다.
시뮬레이터·정책 서버까지 종료하려면 `down`을 사용합니다.

실행 단계와 로그는 `eval_out/demo/`의 `startup.json`, `remote_start.log`,
`bridge.log`, `scenario.log`, `chat_gui.log`에 있습니다.
경기 메타데이터는 `scene.json`, 장애물 좌표는 `obstacles.json`입니다.
내장 Gazebo 로그는 `/tmp/navvla-dashboard/gazebo-gui.log`입니다.

## 검증

```bash
PYTHONPATH=src/sant_vla_pkg python3 -m pytest src/sant_vla_pkg/test -q
```

좌표 투영, 0 좌표의 Gazebo 위치 수신, 서비스 실패 처리, 장애물의 중복 센서
제거, 연결 전 출발 차단, 정지 후 늦은 명령·음성 취소, UI 렌더링을 검사합니다.
실제 r11 원격 정책 서버와 통합 GUI로 자연어 '출발' → 9.11m 이동 → 정지를
확인했습니다. 화면용 예측 15회, 제어 경로 3회가 수신됐고, 화면용 갱신 간격은
중앙값 0.42초, 제어 갱신 간격은 2.30초였습니다. 주행 중 확인한 50개 화면
샘플에서 경로가 사라진 경우는 없었고, 전방 예측은 최소 4.58m 남아 있었습니다.
추론 지연은 약 101ms였습니다. 원래 모델 출력인 30점을 계속 사용합니다.
1540×960 창에서 시뮬레이션 영역은 1082×572이며, 작은 창에서도 제어 항목과
보조 패널이 보이는지 확인했습니다. 자동 검사 19개가 통과했습니다.

모델 reasoning 수신, 세 가지 시점, 네 가지 경기 재배치, 일시정지 중 화면
유지와 시뮬레이션 시간 정지·재개도 확인한 기능입니다.
전 경기 완주 성능과 실제 사람의 음성 인식 정확도를 평가한 변경은 아닙니다.

구현 참고: [Gazebo CameraTracking](https://github.com/gazebosim/gz-gui/blob/gz-gui8/src/plugins/camera_tracking/CameraTracking.cc),
[Qt 외부 창 임베딩](https://doc.qt.io/qt-6/qtdoc-demos-windowembedding-example.html).

## 화면 언어 (한국어 / English)

오른쪽 상단에서 화면 언어를 선택합니다. 01~05 항목 제목은 영어로 고정하고,
한글 모드는 나머지 메뉴·채팅·추론을 한글로, 영어 모드는 영어로 표시합니다.
이전 대화와 추론 기록도 다시 표시하며, 선택은 `eval_out/demo/ui_language.json`에
저장됩니다. 입력 중인 문장과 실제 차량에 전달하는 명령, 모델 출력 원문은
수정하지 않습니다. 전송한 사용자 메시지는 대화창에서 선택한 언어로 번역됩니다.

기본 메뉴는 내장 번역을 사용합니다. 자유 문장과 reasoning은 기존 장면/명령
해석 서버의 모델을 이용해 별도 작업에서 번역합니다. 번역 대기·연결 실패를
명시하며 실패 시 재시도합니다. 번역 요청이나 언어 변경은 주행 명령을 발행하지
않습니다. 번역 문장은 원본 모델 출력을 화면에 표시하기 위한 언어 변환입니다.
