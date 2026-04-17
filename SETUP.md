# Setup Guide — Claude Code Routine 배포

이 문서는 ai-daily-digest 를 Claude Code Routine 으로 배포하는 전체 과정을 다룹니다. Claude 가 대신 UI 를 클릭할 수는 없으니, 아래 단계는 직접 수행하세요. 각 단계 끝에 **검증 체크** 항목이 있으니 이게 통과하면 다음으로 넘어가면 됩니다.

전제: Claude **Pro / Max / Team / Enterprise** 구독자. Free 티어는 Claude Code on the web 자체를 쓸 수 없습니다.

---

## 0. 사전 준비

- [ ] Slack Incoming Webhook URL 확보 (`https://hooks.slack.com/services/XXX/YYY/ZZZ` 형태)
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
       www.anthropic.com
       openai.com
       deepmind.google
       ai.meta.com
       mistral.ai
       ```
   - **Environment variables**:
     ```
     SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
     ```
     (실제 webhook 을 여기에 넣으세요. 한 줄당 `KEY=value`, 따옴표 없이.)
   - **Setup script**: 비워두기. 이 스킬은 Python stdlib only 라 추가 설치 불필요.
3. **Save**

**검증**: environment selector 에서 `ai-digest-env` 가 선택 가능 상태.

> ⚠️ 주의: environment variables 는 "전용 secrets store" 가 아직 없어, environment 를 편집할 수 있는 사람은 값을 볼 수 있습니다. 팀 계정이면 접근 권한 확인하세요.

---

## 4. Routine 생성

이제 스케줄 등록.

1. claude.ai/code 에서 `/schedule` 슬래시 커맨드 사용 (또는 UI 의 **Routines** 탭)
2. 새 Routine 설정:
   - **Repository**: `ai-daily-digest`
   - **Branch**: `main`
   - **Environment**: `ai-digest-env` (3번에서 만든 것)
   - **Schedule (cron)**: 
     - 서비스 기본이 **UTC** 면: `0 0 * * *` (= KST 09:00)
     - 서비스가 timezone 선택을 지원하면 `Asia/Seoul` 선택 후: `0 9 * * *`
   - **Prompt** (실행 시 Claude 에게 전달될 지시사항):

     ```
     Execute the ai-daily-digest skill end-to-end:

     1. Run `python3 .claude/skills/ai-daily-digest/scripts/collect.py --hours 24 --out /tmp/ai-digest-raw.json`
     2. Read /tmp/ai-digest-raw.json. If total item count is fewer than 3, skip to step 4 with a warning-only summary. Otherwise, following the format rules in .claude/skills/ai-daily-digest/SKILL.md, write a Korean developer-focused summary to /tmp/ai-digest-summary.md. Do not invent facts not present in the raw JSON.
     3. Verify the summary file is non-empty.
     4. Run `python3 .claude/skills/ai-daily-digest/scripts/send.py /tmp/ai-digest-summary.md` to post to Slack.
     5. Report the outcome (number of items collected, Slack response status).

     Never use WebSearch for any part of this task — only the 5 primary sources in collect.py are allowed.
     ```

3. **Create routine**

**검증**: Routines 목록에 새 항목이 "Active, next run in Xh" 로 표시됨.

---

## 5. 첫 수동 실행 (dry run)

스케줄 기다리지 말고 바로 테스트.

1. Routine 우측 메뉴에서 **Run now** 클릭
2. 세션이 뜨면 실시간 로그 관찰
   - `[hackernews] N items in ...s`, `[arxiv] ...` 같은 로그가 5개 뜨는지 확인
   - `Per-source breakdown: {...}` 에서 모든 소스가 0 이 아닌지 확인 (Full 네트워크면 대부분 정상)
   - Claude 가 summary.md 를 작성하는 과정 확인
   - `send.py` 가 `OK (200): ok` 반환하는지 확인
3. Slack 채널 열어 메시지 도착 확인

**검증**: Slack 채널에 🔥 / 📘 섹션으로 포맷된 메시지 도착. 허구 모델명 없음, 링크 클릭하면 실제 소스로 이동.

> 첫 실행에서 `0 items` 소스가 있다면:
> - arXiv, HN 쪽은 timeout 가능성 (재시도)
> - 랩 블로그는 실제로 최근 24시간 포스트가 없을 수도 있음 (정상)
> - 모든 소스가 0 이면 network access level 의심 → **Full** 인지 재확인

---

## 6. 운영

- **Slack 메시지 품질이 이상하면** (허구 사실, 광고성 글 등): `.claude/skills/ai-daily-digest/SKILL.md` 의 "요약 작성 규칙" 섹션을 수정 후 git push. 다음 run 부터 반영.
- **소스 추가/제거**: `config.json` 의 `lab_blog_feeds` 또는 `hn_keywords` 수정.
- **webhook 교체**: Slack admin 에서 기존 webhook 해지 → 새 URL 생성 → environment 편집에서 `SLACK_WEBHOOK_URL` 업데이트 (커밋 불필요, 즉시 적용).
- **스킬 일시 중지**: Routines 목록에서 **Pause** 토글.

## 7. 트러블슈팅

| 증상 | 원인 / 처방 |
|---|---|
| Slack 에 `⚠️ 오늘은 수집된 항목이 없습니다` 만 도착 | 소스 3개 이상이 실패. network access level 확인 → **Full** 로. |
| `Slack returned 403` | webhook URL 만료/회전. Slack 에서 재발급 후 env var 업데이트. |
| Routine 이 제시간에 돌지 않음 | Pro 플랜 rate limit 에 걸렸을 가능성. 그 시간대 본인 Claude Code 사용량 줄이거나 cron 시간 이동 (예: 새벽 6시로). |
| `Session creation failed` | [status.claude.com](https://status.claude.com) 확인, 1분 후 재시도. |
| Summary 에 "Claude Mythos 5" 같은 허구 항목 | raw JSON 오염이 아니라 Claude 가 규칙을 어긴 것. SKILL.md 규칙을 강화하거나 Routine prompt 에 "Never invent model names" 한 줄 추가. |

---

## 참고

- [Claude Code Routines 공식 문서](https://code.claude.com/docs/en/routines)
- [Claude Code on the web — cloud environment 설정](https://code.claude.com/docs/en/claude-code-on-the-web#the-cloud-environment)
- [Network access levels & allowed domains](https://code.claude.com/docs/en/claude-code-on-the-web#network-access)
