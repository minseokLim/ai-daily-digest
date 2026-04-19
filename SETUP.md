# Setup Guide — Claude Code Routine 배포

이 문서는 ai-daily-digest 를 Claude Code Routine 으로 배포하는 전체 과정을 다룹니다. Claude 가 대신 UI 를 클릭할 수는 없으니, 아래 단계는 직접 수행하세요. 각 단계 끝에 **검증 체크** 항목이 있으니 이게 통과하면 다음으로 넘어가면 됩니다.

전제: Claude **Pro / Max / Team / Enterprise** 구독자. Free 티어는 Claude Code on the web 자체를 쓸 수 없습니다.

---

## 0. 사전 준비

- [ ] Slack App Bot Token (`xoxb-...`) 과 채널 ID (`C...`) 확보 — 아래 **부록 A** 참고
- [ ] GitHub 계정
- [ ] 로컬에 git 설치됨
- [ ] 이 repo 가 현재 `/Users/minseoklim/workspace/ai-daily-digest` 에 있음

## 1. GitHub repo 생성 & push

```bash
cd /Users/minseoklim/workspace/ai-daily-digest
git init
git add .
git commit -m "Initial ai-daily-digest skill for Claude Code Routines"

# GitHub CLI 쓰는 경우
gh repo create ai-daily-digest --private --source=. --push

# 수동으로 하는 경우: GitHub 에서 빈 repo 만들고
git remote add origin git@github.com:<your-username>/ai-daily-digest.git
git branch -M main
git push -u origin main
```

**검증**: `git log` 에 커밋 하나, `git remote -v` 에 origin 보임, GitHub 페이지에서 `.claude/skills/ai-daily-digest/SKILL.md` 파일 보임.

---

## 2. Claude Code 에 GitHub 연결

이미 연결돼 있다면 건너뛰세요. 처음이면:

1. [claude.ai/code](https://claude.ai/code) 접속
2. **Connect GitHub** 버튼 클릭 → Claude GitHub App 설치
3. **Only select repositories** 선택 후 `ai-daily-digest` 만 허용 (권장 — 전체 접근 권한 주지 말 것)

또는 로컬 터미널에서 `gh` CLI 로 이미 로그인돼 있으면 `/web-setup` 을 Claude Code CLI 에서 실행해 동기화.

**검증**: claude.ai/code 에서 새 세션 만들 때 repo picker 에 `ai-daily-digest` 가 보이면 성공.

---

## 3. Cloud environment 생성

Routine 이 실행될 환경 설정. 한 번 만들어두면 이후 Routine 들이 재사용합니다.

1. claude.ai/code 에서 repo 선택 → environment selector 열기 → **Add environment** 클릭
2. 필드 입력:
   - **Name**: `ai-digest-env` (아무거나 알아보기 쉽게)
   - **Network access level**: **Full** 선택
     - 이유: 우리 5개 소스(hn.algolia.com, export.arxiv.org, huggingface.co, 랩 RSS 들)가 기본 Trusted 리스트에 없어요. Custom 으로 일일이 넣어도 되지만, 이 스킬은 read-only 수집이라 Full 이 간편.
     - 더 엄격하게 가려면 **Custom** 선택 후 "Also include default list of common package managers" 체크하고 아래 도메인 추가:
       ```
       hn.algolia.com
       export.arxiv.org
       huggingface.co
       openai.com
       deepmind.google
       www.anthropic.com
       ai.meta.com
       mistral.ai
       ```
   - **Environment variables**:
     ```
     SLACK_BOT_TOKEN=xoxb-...
     SLACK_CHANNEL_ID=C0123ABCDEF
     ```
     (한 줄당 `KEY=value`, 따옴표 없이. 토큰/채널 ID 취득법은 **부록 A** 참고.)
   - **Setup script**: 비워두기. 이 스킬은 Python stdlib only 라 추가 설치 불필요.
3. **Save**

**검증**: environment selector 에서 `ai-digest-env` 가 선택 가능 상태.

> ⚠️ 주의: environment variables 는 "전용 secrets store" 가 아직 없어, environment 를 편집할 수 있는 사람은 값을 볼 수 있습니다. 팀 계정이면 접근 권한 확인하세요.

---

## 4. Routine 생성

이제 스케줄 등록. Routine UI 는 2026 초에 개편돼 아래 흐름을 따릅니다 — 전용 페이지 + 프리셋 기반 스케줄.

1. **https://claude.ai/code/routines** 로 바로 이동 (또는 claude.ai/code 좌측 내비에서 **Routines**). 우측 상단 **New routine** 버튼 클릭.

2. 생성 폼 섹션별로 입력:

   - **Name**: `AI Daily Digest` (아무거나)
   - **Prompt** (실행 시 Claude 에게 전달될 지시사항) — 모델 선택기가 같이 있습니다. Sonnet 4.6 / Opus 4.7 추천:

     ```
     Execute the ai-daily-digest skill end-to-end:

     1. Run `python3 .claude/skills/ai-daily-digest/scripts/collect.py --hours 24 --out /tmp/ai-digest-raw.json`
     2. Read /tmp/ai-digest-raw.json. If total item count is fewer than 3, write a one-line warning summary to /tmp/ai-digest-summary.md. Otherwise, following the format rules in .claude/skills/ai-daily-digest/SKILL.md, write a Korean developer-focused summary to /tmp/ai-digest-summary.md. Do not invent facts not present in the raw JSON.
     3. Verify the summary file is non-empty.
     4. Run `python3 .claude/skills/ai-daily-digest/scripts/send.py /tmp/ai-digest-summary.md` to post to Slack (parent headline + Block Kit threaded reply).
     5. Report the outcome (number of items collected, Slack response status).

     Never use WebSearch for any part of this task — only the 5 primary sources in collect.py are allowed.
     ```

   - **Repositories**: `ai-daily-digest` 추가. **Allow unrestricted branch pushes** 는 **체크하지 마세요** — 이 스킬은 git push 를 안 합니다.
   - **Environment**: 3번에서 만든 `ai-digest-env` 선택.
   - **Select a trigger** → **Schedule** 탭:
     - 프리셋에서 **Daily** 선택
     - 시간을 **본인 로컬 타임존(KST) 09:00** 으로 지정. 시스템이 타임존을 자동 변환해주므로 UTC 환산 불필요.
     - 커스텀 cron (`0 9 * * *` 등) 이 필요하면 먼저 Daily 프리셋으로 만든 뒤, CLI 에서 `/schedule update` 실행해 cron 수정. 최소 주기는 1시간.
   - **Connectors**: 연결된 MCP connector 가 기본적으로 전부 포함됩니다. 이 스킬은 Slack 을 자체 Web API 로 쏘므로 MCP connector 는 전부 제거해도 무방 (권한 최소화 차원에서 권장).

3. **Create** 클릭.

**검증**: `/routines` 목록에 새 항목이 "Next run in Xh" 로 표시. 상세 페이지에 Prompt / Repositories / Environment / Schedule 이 설정대로 보임.

---

## 5. 첫 수동 실행 (dry run)

스케줄 기다리지 말고 바로 테스트.

1. Routine 상세 페이지에서 **Run now** 클릭. 새 세션이 열립니다.
2. 세션에서 실시간 로그 관찰:
   - `[hackernews] N items in ...s`, `[arxiv] ...` 같은 소스별 수집 로그 8줄 (HN, arXiv, HF, lab_blogs, anthropic_news, meta_blog, mistral_news, github_trending)
   - `Per-source breakdown: {...}` 에서 합계 확인 (Full 네트워크면 수집 건수 > 3건이 정상)
   - Claude 가 `/tmp/ai-digest-summary.md` 작성하는 과정 확인
   - `send.py` 가 `OK: posted parent ts=... + thread reply (N blocks) to <channel>` 반환 확인
3. Slack 채널 열어 메시지 도착 확인. 헤드라인 메시지 + 스레드에 Block Kit 본문.

**검증**: Slack 에 `🔥 오늘의 AI 소식 (YYYY-MM-DD)` 한 줄이 채널에 뜨고, 그 메시지 스레드를 열면 `📰 오늘의 AI 소식` 헤더 + 최대 5개의 아이템 섹션 블록. 허구 모델명 없음, 링크 클릭하면 실제 소스로 이동.

> 첫 실행에서 `0 items` 소스가 있다면:
> - arXiv, HN 쪽은 timeout 가능성 (재시도)
> - 랩 블로그/스크래퍼는 실제로 최근 24시간 포스트가 없을 수도 있음 (정상)
> - 모든 소스가 0 이면 network access level 의심 → **Full** 인지 재확인

---

## 6. 운영

- **Slack 메시지 품질이 이상하면** (허구 사실, 광고성 글 등): `.claude/skills/ai-daily-digest/SKILL.md` 의 "요약 작성 규칙" 섹션을 수정 후 git push. 다음 run 부터 반영.
- **소스 추가/제거**: `config.json` 의 `lab_blog_feeds` 또는 `hn_keywords` 수정.
- **Bot Token 교체**: Slack App 페이지 (`api.slack.com/apps`) → 해당 App → **OAuth & Permissions** → **Rotate** (또는 재설치) → 새 `xoxb-...` 복사 → environment 편집에서 `SLACK_BOT_TOKEN` 업데이트 (커밋 불필요).
- **다른 채널로 교체**: `SLACK_CHANNEL_ID` 만 바꾸면 됨. 새 채널에도 `/invite @<botname>` 필요.
- **스킬 일시 중지**: Routines 목록에서 **Pause** 토글.

## 7. 트러블슈팅

| 증상 | 원인 / 처방 |
|---|---|
| Slack 에 `⚠️ 오늘은 수집된 항목이 없습니다` 만 도착 | 소스 3개 이상이 실패. network access level 확인 → **Full** 로. |
| `invalid_auth` / `not_authed` | Bot Token 이 회전/만료됐거나 scope 부족. App 의 OAuth scope 에 `chat:write` 확인, 필요 시 재설치. |
| `not_in_channel` | 봇이 채널에 없음. Slack 채널에서 `/invite @<botname>`. |
| `channel_not_found` | `SLACK_CHANNEL_ID` 가 `#name` 으로 돼 있거나 오타. 반드시 채널 ID (`C...`) 형식. |
| Routine 이 제시간에 돌지 않음 | Pro 플랜 rate limit 에 걸렸을 가능성. 그 시간대 본인 Claude Code 사용량 줄이거나 cron 시간 이동 (예: 새벽 6시로). |
| `Session creation failed` | [status.claude.com](https://status.claude.com) 확인, 1분 후 재시도. |
| Summary 에 "Claude Mythos 5" 같은 허구 항목 | raw JSON 오염이 아니라 Claude 가 규칙을 어긴 것. SKILL.md 규칙을 강화하거나 Routine prompt 에 "Never invent model names" 한 줄 추가. |

---

## 참고

- [Claude Code Routines 공식 문서](https://code.claude.com/docs/en/routines)
- [Claude Code on the web — cloud environment 설정](https://code.claude.com/docs/en/claude-code-on-the-web#the-cloud-environment)
- [Network access levels & allowed domains](https://code.claude.com/docs/en/claude-code-on-the-web#network-access)
- [Slack API — chat.postMessage](https://api.slack.com/methods/chat.postMessage)

---

## 부록 A — Slack App 생성 & 토큰 획득

이 스킬은 **Incoming Webhook 이 아니라 `chat.postMessage` Web API** 를 씁니다. 한 줄 헤드라인을 채널에 먼저 올리고 상세 요약을 그 메시지의 **스레드** 에 붙이기 위해서입니다 (webhook 은 메시지 `ts` 를 반환하지 않아 스레드를 걸 수 없습니다).

### A-1. Slack App 생성

1. https://api.slack.com/apps → **Create New App** → **From scratch**
   - App Name: `AI Daily Digest` (아무거나)
   - Workspace: 메시지 보낼 워크스페이스

2. 좌측 **OAuth & Permissions** → **Scopes** → **Bot Token Scopes** 섹션에서 **Add an OAuth Scope** → `chat:write` 추가
   - ⚠️ **User Token Scopes** 아니라 **Bot Token Scopes** 여야 함

3. 페이지 상단 **Install to Workspace** → 권한 허용 → **Bot User OAuth Token** (`xoxb-...`) 복사 → `SLACK_BOT_TOKEN` 으로 사용

### A-2. Bot 을 채널에 초대

Slack 에서 메시지 받을 채널 열고:

```
/invite @AI Daily Digest
```

(앱 이름 기준. 봇 이름이 다르면 Slack App 관리 페이지 → **App Home** → **Your App's Presence in Slack** 에서 확인)

### A-3. 채널 ID 찾기

Slack 채널 이름 **우클릭** → **View channel details** → 팝업 하단 스크롤 → **Channel ID** (`C0123ABCDEF` 형식, 11자) 복사 → `SLACK_CHANNEL_ID` 로 사용.

- `#name` (채널 이름) 은 API 에서 인식 안 됨. 반드시 `C...` ID 사용.

### A-4. 로컬 테스트

```bash
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_CHANNEL_ID="C0123ABCDEF"
echo "*Test* (2026-04-17)" > /tmp/test-summary.md
python3 .claude/skills/ai-daily-digest/scripts/send.py /tmp/test-summary.md
```

성공하면 `OK: posted parent ts=<...> + thread reply to <channel>` 출력. Slack 채널에 헤드라인 + 스레드 답글 확인.
