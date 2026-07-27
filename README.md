# DigiTokenBar

Claude Code로 쓴 토큰이 **디지몬**으로 자라는 터미널 도구. 원본
[PokeTokenBar](https://github.com/chattymin/PokeTokenBar)(macOS 메뉴바 앱, 포켓몬)의
핵심 로직만 파이썬으로 옮기고, 포켓몬 → 디지몬으로 바꿔 WSL/Linux 터미널에서 돌아가게 만든 것이다.

토큰을 쓸수록 디지타마(알)가 부화하고, 정통 진화 라인을 따라(분기 랜덤) 진화하며,
최종 진화체가 되면 도감에 등록되고 새 알이 온다.

## 요구사항

- Python 3.9+ (표준 라이브러리 + Pillow, requests)
- 트루컬러 지원 터미널(Windows Terminal 등). 스프라이트를 반블록 아트로 그린다.
- Claude Code 로그(`~/.claude` ~ `~/.claude-6`의 `projects/**/*.jsonl`)

의존성 설치가 필요하면:

```bash
pip install --user pillow requests
```

## 실행

`~/.local/bin/digimon` 심볼릭 링크가 걸려 있어 아무 폴더에서나 `digimon` 으로 실행된다.

**그냥 `digimon` 을 치면 대화형 TUI(전체화면 앱)가 뜬다.** 키 하나로 이동하니 명령어를 외울 필요가 없다.

```
[S]상점  [B]가방  [D]도감  [G]미니게임  [←→]계정전환  [R]새로고침  [Q]나가기
```

미니게임 3종: **누구야?!**(실루엣 맞히기 → 🍬), **배틀**(야생 디지몬과 턴제 → 🍬), **트레이닝**(타이밍 → 성장 보너스).

### 고화질 이미지 (sixel)

sixel 지원 터미널(VS Code 통합 터미널·Windows Terminal 등)에서는 반블록 대신 **진짜 비트맵**으로
디지몬을 그린다. TUI는 실행 시 지원 여부를 감지해 자동 사용하고, 홈에서 `[I]`로 켜고 끌 수 있다.
한 방에 크게 보려면 `digimon img`. sixel 이 안 뜨면 VS Code 설정 `terminal.integrated.enableImages`
를 켜거나 `digimon img --force` 로 강제 출력한다. 미지원 터미널은 고해상도 반블록으로 폴백.

명령어로도 쓸 수 있다(상태줄·스크립트용):

```bash
digimon status       # 상태줄 한 줄 (= --statusline)
digimon card         # 정적 카드 1회 출력(TUI 대신)
digimon dex          # 도감
digimon shop         # 상점
digimon buy candy    # 구매 (buy mint | buy charm)
digimon candy        # 사탕 사용
digimon reset        # 초기화(전 계정)
digimon --account 4  # 특정 계정 지정
```

처음 실행하면 그 시점의 누적 토큰을 **기준선**으로 잡고 알 하나를 준다. 이후 실행할 때마다
지난 실행 이후 새로 쓴 토큰만 성장에 반영된다(과거 사용량은 소급하지 않는다).

### 계정별 펫 (6마리)

계정마다 **각자 디지몬**을 키운다. 상태는 `state/<계정>.json`에 따로 저장되고, 각 펫은 그 계정에서
쓴 토큰으로만 자란다. 상태줄은 Claude Code가 넘기는 `transcript_path`로 자기 창이 어느 계정인지
자동 감지하므로 **창마다 다른 펫·다른 한도**가 뜬다. 수동 실행 시에는 `--account 4`(또는 `.claude-4`)로
계정을 지정한다. statusLine은 6개 계정 `settings.json`에 모두 설정돼 있다.

## Claude Code 상태줄 연동

`~/.claude/settings.json`(원하는 계정)에 아래를 넣으면 코딩 중 하단에 디지몬이 상시 표시된다.
웜런 0.07초라 매 렌더마다 실행돼도 부담 없다.

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /home/knbank189/Seongjin/3_개인/디지몬/digimon.py --statusline"
  }
}
```

## 게임 규칙 (원본 밸런스 이식)

- **부화**: 500만 토큰을 쓰면 알이 깨진다. 부화 종은 희귀도 가중 랜덤.
- **진화**: 단계마다 임계 토큰을 넘으면 진화. 방향은 그 형태의 정통 분기 중 랜덤
  (예: Agumon → Greymon → MetalGreymon → WarGreymon / 또는 Greymon → SkullGreymon).
- **졸업 총량**(희귀도별, heavy use 기준): 커먼 7.5억(≈3일) · 언커먼 18.75억 · 레어 30억.
  같은 희귀도면 진화 단계 수와 무관하게 총량이 같고, 단계가 오를수록 비용이 커진다.
- **이로치(✨)**: 1/64 확률로 색이 다르게 부화(진화해도 유지). 데이터 부적 보유 시 1/48.
- **암흑진화(🌑)**: 진화 시 1/40 확률로 정통 다크폼으로 강제진화(원작 오마주). 라인별 정통
  다크폼이 있는 경우만 발동 — Agumon→Skull Greymon, Guilmon→Megidramon, Gabumon→Metal
  Garurumon(Black), Dorumon→Death-X-mon. 없는 라인은 발동하지 않는다.
- **성격**: 25종 중 하나 확정(표시용).
- **도감**: 최종 진화체(또는 다크폼)가 되면 등록되고 새 알이 온다.

### 공식 한도 (자동)

Claude OAuth usage API(`/api/oauth/usage`)에서 5시간/7일 사용률 %와 리셋 시각을 **자동으로**
가져온다(상한 입력 불필요). 6계정 각각 조회해 현재 계정(`~/.claude-current-index`)을 대표로 보여주고,
증가율로 5시간 한도 100% 도달 시각을 예측한다. 캐시 60초.

### 경제

- **재화** = 설치 이후 쓴 토큰 − 상점 지출. 성장 미터(누적)는 소비해도 줄지 않는다.
- **상점**: 이상한 사탕(성장 +100M) · 민트(성격 재추첨) · 데이터 부적(영구 이로치 확률↑).
- **이상한 사탕**은 한도(5시간=1개·7일=5개) 100% 도달 시 보상으로도 지급된다(가방 → `digimon candy`).

- **알림**: 부화/진화/암흑진화/졸업 시 터미널 벨 + Windows 토스트(WSL, best-effort).
- **비용 분해**: 카드에 오늘 모델별(opus/sonnet/haiku…) 토큰·비용 상위 표시.

수록 라인: 커먼 17 · 언커먼 10 · 레어 5 = **총 32개**(어드벤처·02·테이머즈·세이버즈 등 정통 라인, 분기 포함).
라인 목록·분기는 `digitoken/linedata.json`, 편집은 `tools/build_lines.py` 후 재빌드.

## 데이터 소스 · 주의

- 토큰/비용·한도는 로컬 로그 + 본인 OAuth 토큰으로 조회한다. 외부로 데이터를 보내지 않는다.
  토큰 dedup은 `(message.id, requestId)`, 로컬 날짜는 Asia/Seoul.
- 디지몬 이미지·진화 정보는 [digi-api.com](https://digi-api.com)에서 가져와 `cache/`에 캐시한다
  (최초 1회만 네트워크, 이후 오프라인).
- 비상업 팬메이드. 디지몬 IP는 반다이/도에이 소유.

## 라인 데이터 다시 굽기

진화 라인을 바꾸거나 추가하려면 `tools/build_lines.py`의 `LINES`를 수정하고:

```bash
python3 tools/build_lines.py   # digi-api로 id·이미지 해석 → digitoken/linedata.json
```
