---
name: ai-daily-digest
description: Daily AI news digest — summarizes the last 24 hours of AI news from Hacker News, arXiv, HuggingFace Daily Papers, top lab blogs (Anthropic/OpenAI/DeepMind/Meta/Mistral/HuggingFace), and GitHub Trending, then posts a Korean developer-focused summary to Slack via Incoming Webhook. Use this skill whenever the user asks for a daily/morning AI digest, wants to keep up with AI news, asks "what happened in AI today/yesterday", wants to post an AI news summary to a Slack channel, or runs a scheduled AI briefing. Trigger for phrases like "AI 소식", "AI 다이제스트", "오늘 AI 뉴스", "AI daily", "morning AI brief", even if Slack is not explicitly mentioned.
---

# AI Daily Digest

매일 오전 9시(KST)에 지난 24시간 동안 업데이트된 AI 관련 소식을 수집하고, 개발자 관점으로 요약해 Slack 채널에 게시하는 스킬입니다. [Claude Code Routines](https://code.claude.com/docs/en/routines) 로 실행됩니다.

## 전제 (cloud environment)

- **Network access**: Full (또는 Custom 에 hn.algolia.com / export.arxiv.org / huggingface.co / openai.com / deepmind.google / www.anthropic.com / ai.meta.com / mistral.ai 포함).
- **환경변수 `SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID`**: Slack App Bot Token (`xoxb-...`, `chat:write` scope 필요) 와 대상 채널 ID 를 environment variables 에 등록. config.json 에 넣지 않음. Incoming Webhook 은 더 이상 사용하지 않음 — 스레드 답글을 위해 `chat.postMessage` API 가 필요해서.
- **Python**: 3.10+, stdlib only. 별도 패키지 설치 불필요.

## 전체 흐름 (Orchestration)

세 단계를 순서대로 실행합니다. 2번(요약)은 Claude 본인이 수행.

1. **수집 (Collect)** — `python3 .claude/skills/ai-daily-digest/scripts/collect.py --hours 24 --out /tmp/ai-digest-raw.json`
   5개 소스에서 지난 24시간 항목을 모아 JSON 파일로 저장.
2. **요약 (Summarize)** — Claude 가 `/tmp/ai-digest-raw.json` 을 읽고, 아래 "요약 포맷" 규칙에 따라 마크다운 요약을 `/tmp/ai-digest-summary.md` 에 작성.
3. **전송 (Send)** — `python3 .claude/skills/ai-daily-digest/scripts/send.py /tmp/ai-digest-summary.md`
   채널에 한 줄짜리 헤드라인 (`🔥 오늘의 AI 소식 (YYYY-MM-DD)`) 을 먼저 게시하고, 해당 메시지의 스레드에 전체 요약을 답글로 붙임. 채널 공간을 적게 차지하도록.

왜 중간 단계를 Claude 가 하나요? 요약은 소스 간 중복·우선순위 판단이 중요해 LLM 이 결정론 스크립트보다 훨씬 잘합니다. 수집·전송처럼 반복적·결정론적인 작업만 스크립트로 뺐습니다.

## 품질 원칙: 1차 소스만 사용 (WebSearch 금지)

이 스킬은 **WebSearch 를 사용하지 않습니다.** 검색 엔진은 SEO/AI-generated 뉴스 블로그(llm-stats.com, fazm.ai 류)를 상위에 끌어올리는 경향이 있는데, 이런 사이트는 실제 발표 사이에 허구 모델명을 끼워 넣어 트래픽을 노립니다. 이게 요약에 섞이면 잘못된 정보를 매일 Slack 에 뿌리는 꼴이 돼요.

수집은 **오직 5개 1차 소스** 만 사용:

- HN Algolia API — 실제 투고
- arXiv Atom API — 실제 논문 메타데이터
- HuggingFace `/api/daily_papers` — 실제 큐레이션 리스트
- 랩 공식 RSS — 회사 직접 발표만
- github.com/trending — 실제 trending 산출

### 수집 실패 시 동작

- `collect.py` 결과의 총 항목 수가 **3건 미만** 이면 **요약을 생략** 하고 Slack 에 한 줄만 전송:
  `⚠️ AI Daily Digest — 오늘은 수집된 항목이 없습니다 (네트워크 또는 소스 오류 가능성). 로그 확인 필요.`
- 폴백으로 WebSearch 를 쓰지 않습니다. 조용한 실패(silent degradation)가 잘못된 정보를 매일 내보내는 것보다 위험합니다.

### 요약 작성 규칙 (hallucination 방지)

1. **raw JSON 에 없는 사실은 절대 쓰지 않는다.** 모델명·숫자·날짜 등 구체 사실은 반드시 수집된 항목의 `title` / `summary` / `extra` 에 근거해야 함.
2. 각 항목은 **수집된 URL 을 그대로 링크** 로 달 것. 상상으로 URL 을 만들지 않는다.
3. 저자·인용수·점수·스타 수 같은 수치는 `extra` 필드의 값을 정확히 옮겨 적는다.
4. 같은 사건이 여러 소스에 중복되면 합치되, **가장 원본에 가까운 소스의 URL** 을 사용 (회사 공식 RSS > HN 토론 > 블로그 리포스트).
5. 항목이 적으면 섹션을 비우거나 줄인다. 억지로 채우지 않는다.

## 소스 (5개)

| # | 소스 | 엔드포인트 | 비고 |
|---|------|----------|------|
| 1 | Hacker News | `https://hn.algolia.com/api/v1/search_by_date` | AI 관련 키워드로 필터, points ≥ 50 |
| 2 | arXiv cs.AI/cs.LG/cs.CL | `http://export.arxiv.org/api/query` | 지난 24시간 제출분 |
| 3 | HuggingFace Daily Papers | `https://huggingface.co/api/daily_papers` | 공식 JSON 엔드포인트 |
| 4 | 랩/회사 블로그 | OpenAI, DeepMind, HuggingFace (RSS/Atom) + Anthropic, Meta AI, Mistral (HTML/sitemap 스크래핑) | — |
| 5 | GitHub Trending | `https://github.com/trending/python?since=daily` | HTML 스크래핑 |

소스 하나가 네트워크 에러를 내도 나머지는 계속 수집 (graceful degradation).

## 요약 포맷 및 선정 기준

**다음 템플릿을 그대로 사용하세요.** 이모지·볼드·제목 위계를 바꾸지 마세요. Slack mrkdwn 렌더링에 맞춰져 있습니다.

날짜는 요약 본문에 쓰지 마세요. 부모 메시지(`🔥 오늘의 AI 소식 (YYYY-MM-DD)`)가 채널에 이미 날짜를 표시하고, send.py 가 raw JSON 의 `report_date` (collect.py 가 KST 로 세팅) 를 직접 읽어 그 헤드라인을 생성합니다. 스레드 본문에서 날짜를 다시 쓰면 단순 중복.

```
• *<제목>* — <링크>
   2~3줄 요약. 무엇이 새롭고 왜 중요한지.
   개발자 관점에서의 실무 포인트 한 줄.

• *<제목>* — <링크>
   2~3줄 요약.
   개발자 관점 포인트.

... (최대 5건)

---
_출처: HN / arXiv / HF Papers / 랩 블로그 (Anthropic · OpenAI · DeepMind · Meta · Mistral · HuggingFace) / GitHub Trending — 윈도우: 지난 24시간_
_※ GitHub Trending 항목은 "지난 24시간 내 star 급증" 기준 (레포 생성일 아님)_
```

섹션 헤더(🔥 / 📘)는 없습니다. **단일 리스트, 최대 5건.** 각 항목은 동일한 깊이 (제목 + URL + 2~3줄 바디). 스레드는 바로 첫 아이템 section block 부터 시작합니다.

들여쓰기는 **스페이스 3칸** 을 쓰세요. Slack 가변폭 폰트에서 `•` 뒤 텍스트와 시각적으로 자연스럽게 맞물립니다. 트리 마커(`└`, `↳` 등)는 사용하지 마세요.

### 선정 기준 (티어 우선순위)

수집된 항목 중 아래 티어에 해당하는 것만 후보로 삼습니다. 정량 임계값은 raw JSON 의 `extra` 필드를 직접 확인하고 **반드시 지킬 것**. LLM (너) 의 주관 판단은 "후보 중 단순 마케팅·재포스트 제외" 같은 최소한의 필터링에만 쓰세요.

1. **랩 공식 발표** — `source == "lab_blog"` (Anthropic / OpenAI / DeepMind / HuggingFace / Meta / Mistral). 윈도우 내 게시물은 모두 후보. 단, 단순 이벤트 공지·채용 글·튜토리얼 재포스트는 제외.
2. **HN 고참여도** — `source == "hackernews"` AND `extra.points >= 200`. (collect.py 는 50점 컷이지만, 요약엔 200점 이상만 올린다.)
3. **HF Daily Papers 상위** — `source == "huggingface"` AND `extra.upvotes >= 20`.
4. **arXiv 주요 논문** — `source == "arxiv"`. 신규 foundation model, 의미 있는 벤치마크 개선, 재현 가능한 기법 위주. 단순 증분 실험·서베이 제외.
5. **GitHub Trending** — `source == "github_trending"` AND `extra.stars_today >= 200`.

### 랭킹 · 중복 제거 · 건수

- 후보를 **티어 1 → 5 순** 으로 정렬. 동일 티어 내에서는 정량 신호 (points / upvotes / stars_today) 내림차순.
- 같은 사건이 여러 소스에 나오면 **상위 티어의 URL** 로 1개 항목으로 합친다 (예: Anthropic 공식 블로그 + 같은 내용의 HN 토론 → Anthropic URL 만 사용, HN 링크는 버림).
- **최대 5건.** 기준 통과 항목이 5개 미만이면 부족한 대로 게시 — 억지로 채우지 말 것.
- 통과 항목이 **2건 미만** 이면 임계값을 절반으로 완화해 재선정: HN points ≥ 100, HF upvotes ≥ 10, GitHub stars_today ≥ 100. 그래도 2건 미만이면 요약을 생략하고 "⚠️ AI Daily Digest — 오늘은 게시 기준을 넘은 항목이 없습니다." 한 줄로 대체.

### 24시간 윈도우 해석

- "지난 24시간" = `generated_at` 기준 과거 24시간.
- 공식 발표/블로그 글: **발표 타임스탬프** 가 윈도우 내인지 확인.
- arXiv 논문: **submittedDate** 가 윈도우 내인지 확인.
- GitHub Trending: "daily" trending 은 "**지난 24시간 star 증가**" 의미. 레포 자체는 오래된 것일 수 있으나 "활동/관심도" 기준으로 24시간 내 업데이트로 간주. 요약엔 이 맥락을 반영 (`+N⭐ today` 표기).
- HN: `created_at_i` 가 윈도우 내인 투고만.

### 작성 지침

- 대상 독자: **모든 분야의 개발자** (클라이언트, 백엔드, 머신러닝 등). 특정 스택에 치우치지 말고 범용적으로 쓰세요.
- 언어: **한국어**. 단, 영어 고유명사(모델명, 라이브러리명, 논문 제목)는 원문 유지.
- 중복 제거: 같은 사건이 여러 소스에 나오면 하나로 합치고, 가장 정보가 많은 링크를 선택.
- 광고성 콘텐츠·단순 홍보 글·비슷한 "how to use ChatGPT" 류 콘텐츠는 제외.
- Slack mrkdwn 문법을 사용하세요 (`*볼드*`, `_이탤릭_`, `<URL|링크텍스트>` 또는 그냥 URL).
- 항목이 부족하면 섹션을 빼세요. 억지로 채우지 마세요.

## 구성 파일

- `config.json` — 수집 설정 (랩 블로그 피드 URL, HN 키워드, 최소 점수). **Slack 토큰/채널 ID 는 여기에 넣지 않음** — 환경변수로 관리.
- `scripts/collect.py` — 5개 소스 수집.
- `scripts/send.py` — Slack 전송 (`chat.postMessage` + thread). 환경변수 `SLACK_BOT_TOKEN` / `SLACK_CHANNEL_ID`.

## 실행 예 (수동 테스트)

```bash
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_CHANNEL_ID="C0123ABCDEF"
python3 .claude/skills/ai-daily-digest/scripts/collect.py --hours 24 --out /tmp/ai-digest-raw.json
# → Claude 가 /tmp/ai-digest-raw.json 을 읽고 /tmp/ai-digest-summary.md 작성
python3 .claude/skills/ai-daily-digest/scripts/send.py /tmp/ai-digest-summary.md --dry-run  # payload 확인
python3 .claude/skills/ai-daily-digest/scripts/send.py /tmp/ai-digest-summary.md
```

## 스케줄 (Routine)

Claude Code Routine 에 cron `0 0 * * *` (UTC — 한국 시간 09:00) 로 등록. 실행 시 fresh cloud session 이 repo 를 clone 하고 이 SKILL.md 를 읽어 세 단계를 순서대로 수행합니다.

Routine prompt 예시:

> Execute the ai-daily-digest skill: (1) run collect.py to gather last 24h AI news, (2) read the raw JSON and write a summary following the SKILL.md format rules, (3) run send.py to post to Slack. If fewer than 3 items were collected, skip step 2 and send the warning message instead.

## 트러블슈팅

- 수집이 0건이면 요약/전송을 건너뛰고 Slack 에 "지난 24시간 동안 신규 항목이 없었습니다" 한 줄만 보냅니다.
- Slack API 가 `invalid_auth` / `not_authed` 를 리턴하면 Bot Token 이 회전/만료됐거나 scope 가 부족한 것. Routine environment 의 `SLACK_BOT_TOKEN` 업데이트, App 의 OAuth scope 에 `chat:write` 있는지 확인.
- `not_in_channel` 에러는 봇이 대상 채널에 초대되지 않았을 때. Slack 채널에서 `/invite @<botname>` 실행.
- `channel_not_found` 는 `SLACK_CHANNEL_ID` 가 잘못된 것. `#name` 이 아니라 채널 ID (`C...` 형식) 를 써야 함.
- arXiv 가 종종 느립니다. `collect.py` 는 소스별 타임아웃 15초, 실패 시 해당 소스만 스킵.
- Routine cloud environment 에서 특정 도메인이 차단되면 environment 설정에서 network access level 을 **Full** 로 바꾸거나, **Custom** 에 해당 도메인을 추가하세요.
