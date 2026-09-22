# Reset Sentinel

`codex-resets.com`의 **Latest Codex limit reset** 시각을 확인하고, 새 리셋이 0~50분 이내라면 지정한 Discord 채널로 딱 한 번 알리는 GitHub Actions 봇입니다.

- GitHub repo: `coshaman/resettrackdiscord`
- Discord 표시 이름: **Reset Sentinel**
- 별도 서버 없음
- 별도 API key 없음
- Discord Bot Token 없음 — **Webhook 하나만 사용**
- 기본 검사: 매시 `:07`, `:37` (30분 간격)
- 중복 방지: 알림 성공 후 `data/state.json`을 자동 commit
- 대상 채널 제한: Webhook이 연결된 Discord 채널 하나에만 전송

## 왜 :01 한 번이 아니라 :07 / :37인가?

원래 조건대로 매시 `:01`에만 검사하면서 "0~50분 전 리셋"만 허용하면, 예를 들어 12:05에 리셋된 경우 13:01에는 이미 56분 전이라 영원히 놓칠 수 있습니다.

그래서 기본값은 30분 간격입니다. 정상적인 스케줄이라면 새 리셋을 최대 30분 안에 발견하므로 0~50분 조건 안에 들어옵니다. 또한 GitHub는 매시 정각 부근에 scheduled workflow가 지연될 수 있다고 안내하므로 `:07`, `:37`로 피했습니다.

## 1. Discord Webhook 만들기

알림을 받을 **정확한 채널**에서 Webhook을 만듭니다.

1. Discord 서버 설정 → **연동(Integrations)** → **웹후크(Webhooks)**
2. 새 Webhook 생성
3. 알림 받을 채널을 선택
4. 이름은 `Reset Sentinel` 정도로 지정
5. **Copy Webhook URL**

Webhook URL은 비밀번호처럼 취급하세요. GitHub 파일에 직접 쓰면 안 됩니다.

## 2. GitHub에 repo 만들기

GitHub에서 새 repository를 만듭니다.

- Owner: `coshaman`
- Repository name: `resettrackdiscord`
- 추천 visibility: **Private**
- README / .gitignore / License 자동 생성: **전부 체크하지 않기**

이 ZIP 안에 이미 모두 들어 있습니다.

### Private를 추천하는 이유

GitHub Free는 private repository용 Actions 무료 분량이 월 2,000분입니다. 이 프로젝트는 30분마다 1회, 즉 30일 기준 약 1,440회 실행됩니다. 각 job이 1분 미만이면 GitHub의 분 단위 반올림 기준으로 약 1,440분이므로 여유를 남깁니다.

단, 같은 계정의 다른 private repo에서 Actions 무료 분량을 많이 쓰고 있다면 합산됩니다. 그런 경우 이 repo를 Public으로 두면 standard GitHub-hosted runner 사용은 무료지만, public repo의 scheduled workflow는 장기간 repository activity가 없으면 자동 비활성화될 수 있다는 GitHub 정책이 있습니다.

## 3. Windows에서 ZIP 풀고 push

ZIP을 예를 들어 아래에 풉니다.

```text
C:\Users\<사용자이름>\Downloads\resettrackdiscord
```

PowerShell 또는 Git Bash에서 폴더로 이동합니다.

```bash
cd C:/Users/<사용자이름>/Downloads/resettrackdiscord
```

그 다음:

```bash
git init
git branch -M main
git add .
git commit -m "Initial Reset Sentinel"
git remote add origin https://github.com/coshaman/resettrackdiscord.git
git push -u origin main
```

GitHub 로그인이 필요하면 브라우저 로그인 또는 Git Credential Manager 안내를 따르면 됩니다.

이미 `origin`이 있다고 나오면:

```bash
git remote set-url origin https://github.com/coshaman/resettrackdiscord.git
git push -u origin main
```

## 4. Webhook URL을 GitHub Secret으로 넣기

GitHub에서:

```text
coshaman/resettrackdiscord
→ Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

Name:

```text
DISCORD_WEBHOOK_URL
```

Secret에는 Discord에서 복사한 Webhook URL 전체를 넣습니다.

**Webhook URL을 코드, README, commit message 등에 붙여 넣지 마세요.**

## 5. 연결 테스트

repo의 GitHub 화면에서:

```text
Actions
→ Reset Sentinel
→ Run workflow
→ Send a Discord test message only 체크
→ Run workflow
```

Discord 지정 채널에 다음 메시지가 오면 완료입니다.

```text
✅ Reset Sentinel 테스트 성공
```

테스트 모드는 `data/state.json`을 건드리지 않습니다.

## 실제 동작

매시 `:07`, `:37`에 다음 순서로 실행됩니다.

```text
codex-resets.com 요청
        ↓
"Latest Codex limit reset" 위치 탐색
        ↓
UTC timestamp 파싱
        ↓
현재 시각과 차이 계산
        ↓
0~50분 이내인가?
        ├─ 아니오 → 종료
        └─ 예
             ↓
이미 보낸 timestamp인가?
        ├─ 예 → 종료
        └─ 아니오
             ↓
Discord Webhook 전송
             ↓
전송 성공 후에만 state.json 갱신
             ↓
GitHub Actions가 변경된 state.json commit/push
```

따라서 같은 reset을 `:07`, `:37`에서 반복 발견해도 Discord 메시지는 한 번만 갑니다.

## 알림 예시

```text
🚨 Codex Reset 감지
Codex 사용량 리셋이 감지됐어요.
• 리셋 시각: 2026년 9월 23일 ...
• 감지 지연: 약 12분
• 출처: https://codex-resets.com/
```

Discord `<t:...>` timestamp를 사용하므로 실제 Discord 화면에서는 각 사용자의 local timezone에 맞게 표시됩니다.

## 다른 Discord 채널에는 왜 안 가나?

이 프로젝트에는 Discord 서버 전체를 조작하는 Bot Token이 없습니다. 오직 `DISCORD_WEBHOOK_URL` 하나에 HTTP POST를 보냅니다.

Discord Webhook 자체가 생성할 때 선택한 특정 채널에 연결되므로, Webhook의 채널 설정을 바꾸지 않는 한 코드가 다른 채널을 골라서 메시지를 보내는 경로가 없습니다.

## 로컬 테스트

파서/판정 로직 테스트:

```bash
python -m unittest discover -s tests -v
```

Webhook만 직접 테스트하려면 환경변수를 임시로 넣고:

PowerShell:

```powershell
$env:DISCORD_WEBHOOK_URL="여기에_웹훅_URL"
python reset_tracker.py --test-webhook
Remove-Item Env:DISCORD_WEBHOOK_URL
```

Webhook URL이 PowerShell history에 남을 수 있으므로 GitHub Secret 방식의 테스트를 더 추천합니다.

## 검사 주기 바꾸기

`.github/workflows/reset-sentinel.yml`의 cron만 수정하면 됩니다.

현재:

```yaml
schedule:
  - cron: '7,37 * * * *'
```

정확히 원래 요청처럼 매시 `:01`만 검사하려면:

```yaml
schedule:
  - cron: '1 * * * *'
```

하지만 이 경우 0~50분 조건 때문에 매시간 약 10분의 사각지대가 생길 수 있어 추천하지 않습니다.

Public repo에서 더 자주 확인하고 싶다면 예를 들어 10분마다:

```yaml
schedule:
  - cron: '7,17,27,37,47,57 * * * *'
```

GitHub Actions의 scheduler는 실시간 보장 시스템이 아니므로 실행이 지연되거나 드물게 누락될 가능성은 있습니다.

## 사이트 HTML이 바뀌면

봇은 아무 timestamp나 고르는 대신 **`Latest Codex limit reset` 문구 근처 500자 안에서만 UTC timestamp를 찾습니다.** 구조가 크게 바뀌면 workflow를 실패시키고, 잘못된 Discord 알림을 보내지 않는 방향으로 설계했습니다.

Actions 로그에서 다음과 같은 오류를 보면 parser를 업데이트하면 됩니다.

```text
ERROR: Could not find marker: 'Latest Codex limit reset'
```

## 파일 구조

```text
resettrackdiscord/
├─ .github/
│  └─ workflows/
│     └─ reset-sentinel.yml
├─ data/
│  └─ state.json
├─ tests/
│  └─ test_reset_tracker.py
├─ reset_tracker.py
├─ .gitignore
├─ LICENSE
└─ README.md
```
