# AI Daily Digest

매일 아침 9시(KST)에 지난 24시간의 AI 관련 소식을 수집해 개발자 관점으로 요약하고 Slack 채널에 게시하는 Claude Code 스킬입니다. [Claude Code Routines](https://code.claude.com/docs/en/routines) 위에서 실행되도록 설계됐습니다.

## 소스 (5개, 1차 소스만)

1. **Hacker News** — Algolia search-by-date API, AI 키워드 필터, 50pt 이상
2. **arXiv** — cs.AI / cs.LG / cs.CL 최신 제출 논문
3. **HuggingFace Daily Papers** — 공식 큐레이션 API
4. **랩 공식 블로그** — OpenAI / DeepMind / HuggingFace (RSS) + Anthropic / Meta AI / Mistral (HTML 스크래핑 — RSS 미제공)
5. **GitHub Trending** — Python daily trending 중 AI 관련 레포

WebSearch 는 의도적으로 사용하지 않습니다. SEO/AI-generated 뉴스 블로그가 가상 모델명(예: "Claude Mythos 5", "Nemotron 3 Super" 등)을 섞어 넣어 trending 을 탈취하는 사례가 자주 보여, 1차 소스만 신뢰합니다.

## 동작 방식 (3-stage)

| 단계 | 담당 | 산출물 |
|---|---|---|
| 1. 수집 | `scripts/collect.py` (결정론) | `/tmp/ai-digest-raw.json` |
| 2. 요약 | Claude 본인 (LLM 판단) | `/tmp/ai-digest-summary.md` |
| 3. 전송 | `scripts/send.py` (결정론) | Slack POST |

요약은 소스 간 중복 판정·우선순위 판단이 필요해 LLM 에 맡기고, 결정론적 작업만 스크립트로 분리했습니다.

## 품질 가드레일

- 수집된 항목 < 3개 → 요약 건너뛰고 Slack 에 경고 1줄만 전송 (hallucination 방지).
- 요약 작성은 raw JSON 의 `title` / `summary` / `extra` / `url` 필드에만 근거 (SKILL.md 규칙).
- 스크립트는 stdlib only, 외부 패키지 불필요.

## 셋업

[SETUP.md](./SETUP.md) 참고. 대략:

1. 이 repo 를 GitHub 에 push
2. [claude.ai/code](https://claude.ai/code) 에서 cloud environment 생성 (network: Full 또는 Custom)
3. 환경변수 `SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID` 등록
4. Routine 생성, cron `0 0 * * *` (UTC — KST 9am)
5. "Run now" 로 1회 수동 실행 → Slack 도착 확인

## 수동 실행 (로컬)

```bash
export SLACK_BOT_TOKEN="xoxb-..."      # Slack App Bot Token (chat:write scope 필요)
export SLACK_CHANNEL_ID="C0123ABCDEF"  # 채널 ID (#name 아님)
python3 .claude/skills/ai-daily-digest/scripts/collect.py --hours 24 --out /tmp/ai-digest-raw.json
# → Claude 또는 직접 /tmp/ai-digest-summary.md 작성
python3 .claude/skills/ai-daily-digest/scripts/send.py /tmp/ai-digest-summary.md --dry-run  # 먼저 payload 확인
python3 .claude/skills/ai-daily-digest/scripts/send.py /tmp/ai-digest-summary.md
```

Slack 에는 한 줄 헤드라인 (`🔥 오늘의 AI 소식 (YYYY-MM-DD)`) 이 채널에 올라가고, 전체 요약은 그 메시지의 스레드에 답글로 붙습니다. Slack App 설정은 [SETUP.md 부록 A](./SETUP.md#부록-a--slack-app-생성--토큰-획득) 참고.

Python 3.10+.

## 파일 트리

```
ai-daily-digest/
├── README.md                 이 파일
├── SETUP.md                  Routine 등록 가이드
├── .gitignore
└── .claude/
    ├── settings.json
    └── skills/
        └── ai-daily-digest/
            ├── SKILL.md           오케스트레이션 + 요약 포맷 규칙
            ├── config.json        비밀 아닌 설정 (피드 URL, 키워드)
            └── scripts/
                ├── collect.py
                └── send.py
```
