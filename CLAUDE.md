# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A single Claude Code **skill** (`.claude/skills/ai-daily-digest/`) designed to run as a scheduled Routine on Claude Code on the web. It posts a Korean, developer-focused AI news digest to Slack every morning at 09:00 KST. There is no application code outside the skill — the whole repo exists to ship this one skill.

The skill's own spec lives in `.claude/skills/ai-daily-digest/SKILL.md`; operational setup for deploying it as a Routine lives in `SETUP.md`. When changing behavior, read SKILL.md first — it holds the contract both future Routine runs and `send.py`'s Block-Kit parser rely on.

## Architecture: 3-stage pipeline, only stage 2 is the LLM

```
collect.py (deterministic)  →  /tmp/ai-digest-raw.json
          ↓
   Claude reads raw JSON, writes /tmp/ai-digest-summary.md  ← LLM judgment
          ↓
send.py (deterministic)     →  Slack (headline + threaded Block Kit reply)
```

Stages 1 and 3 are Python stdlib-only scripts. Stage 2 is Claude itself, following the format rules in SKILL.md. This split is deliberate: ranking / dedupe across sources needs LLM judgment, but fetching and Slack posting do not — and keeping them as scripts means they're cheap, reproducible, and debuggable without a model in the loop.

### collect.py — 5 primary sources, graceful per-source failure

`fetch_*` functions for: Hacker News (Algolia search-by-date, keyword loop, `points ≥ 50`), arXiv (cs.AI/cs.LG/cs.CL Atom feed), HuggingFace Daily Papers (`/api/daily_papers`), lab blogs (OpenAI/DeepMind/HuggingFace RSS + Anthropic/Meta/Mistral HTML scrape — they have no RSS), GitHub Trending (Python daily, filtered by AI keyword list). One source's exception doesn't abort the run — failures print to stderr and the source returns `[]`.

Output JSON carries `generated_at` (UTC) and `report_date` (**KST**, pinned explicitly). The two are intentionally different — see the "Critical invariants" section.

### send.py — chat.postMessage, not Incoming Webhook

Posts a one-line parent headline (`🔥 오늘의 AI 소식 (YYYY-MM-DD)`) to the channel, then replies in that message's thread with the full Block Kit summary. Needs `chat.postMessage` (not webhooks) because only that returns the parent `ts` needed for threading.

`markdown_to_blocks()` parses the SKILL.md markdown format into Block Kit. This parser is tightly coupled to the SKILL.md output template: headers are `*<emoji> <title>*`, items are `• *title* — url`, body lines are indented under items, the footer is `_..._` context lines, divider is `---`. **If you change the summary format in SKILL.md, update this parser in lockstep** or threaded replies will render as raw text.

## Commands

```bash
# Collect (writes /tmp/ai-digest-raw.json)
python3 .claude/skills/ai-daily-digest/scripts/collect.py --hours 24 --out /tmp/ai-digest-raw.json

# [Stage 2 is Claude — read raw JSON, write summary per SKILL.md format rules]

# Send — dry-run first to inspect Block Kit payload
export SLACK_BOT_TOKEN="xoxb-..."       # Bot User OAuth Token, chat:write scope
export SLACK_CHANNEL_ID="C0123ABCDEF"   # channel ID, not #name
python3 .claude/skills/ai-daily-digest/scripts/send.py /tmp/ai-digest-summary.md --dry-run
python3 .claude/skills/ai-daily-digest/scripts/send.py /tmp/ai-digest-summary.md
```

Python 3.10+. stdlib only — do not introduce external dependencies; the cloud environment runs with an empty setup script.

No test suite, no linter configured. Verification is manual via `--dry-run` on `send.py` and inspecting `/tmp/ai-digest-raw.json`.

## Critical invariants (these have bit us before)

1. **No WebSearch, ever.** SEO/AI-generated news sites inject hallucinated model names (e.g. "Claude Mythos 5") to hijack trending. The 5 primary sources are the whitelist; the Routine prompt in SETUP.md explicitly forbids WebSearch.

2. **Summary facts must come from raw JSON only.** `title` / `summary` / `extra` / `url` are the only legal sources of specific claims (model names, numbers, authors, stars). No "I recall that…" inference.

3. **`report_date` is KST, not derived from `generated_at`.** The Routine fires at 09:00 KST = 00:00 UTC. If the summarizer derives the date from `generated_at` (UTC) it will be off-by-one (yesterday) whenever the run lands before midnight UTC. Always copy `report_date` from the raw JSON.

4. **`<3` collected items ⇒ skip summary, send a one-line warning.** Better a visible degradation than a hallucinated digest.

5. **Lab blog scrapers (Anthropic/Meta/Mistral) are fragile by design.** They parse HTML. When a site rebuilds, these functions are expected to break and should be fixed independently without touching the RSS path.

## Where to change what

- Summary format / section rules / hallucination rules → `.claude/skills/ai-daily-digest/SKILL.md` (and keep `send.py`'s parser in sync).
- HN keywords, min-points threshold, lab RSS feed list → `config.json`.
- Adding a new source → new `fetch_*` in `collect.py` + entry in the `sources` list in `main()`. Match the existing item schema (`source`, `title`, `url`, `published_at`, `summary`, `extra`).
- Secrets (`SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`) → the Routine's cloud environment variables, never `config.json`.
- Routine deployment / Slack App setup → `SETUP.md`.
