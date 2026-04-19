#!/usr/bin/env python3
"""
AI Daily Digest — Slack Sender (chat.postMessage + Block Kit + threading)

Posts a short headline to the channel, then drops a Block Kit–formatted
summary as a reply in that message's thread. Block Kit gives proper header
styles, dividers, and blockquote indentation so the thread is scannable
instead of a wall of plain text.

Requires a Slack App with a Bot Token (xoxb-...) that has the `chat:write`
scope AND is a member of the target channel (`/invite @<botname>` in Slack).

Required env vars (set these in the Routine's cloud environment):
  - SLACK_BOT_TOKEN   — xoxb-... Bot User OAuth Token
  - SLACK_CHANNEL_ID  — target channel ID (e.g. C0123ABCDEF, NOT the #name)

CLI flags override env vars when given. Do NOT commit either value.

Why chat.postMessage instead of Incoming Webhook: webhooks don't return the
message `ts`, so we can't thread a reply to the message we just posted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

SLACK_API = "https://slack.com/api/chat.postMessage"


def post_chat_message(token: str, channel: str, text: str,
                      blocks: list | None = None,
                      thread_ts: str | None = None) -> dict:
    payload: dict = {
        "channel": channel,
        "text": text,  # fallback for notifications and clients without Block Kit
        "unfurl_links": False,
        "unfurl_media": False,
    }
    if blocks:
        payload["blocks"] = blocks
    if thread_ts:
        payload["thread_ts"] = thread_ts
    req = urllib.request.Request(
        SLACK_API,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')} (full: {data})")
    return data


def extract_date(summary: str, raw_json_path: str | None = None) -> str:
    """Resolve the YYYY-MM-DD for the parent headline.

    Priority: raw JSON's `report_date` (KST, pinned by collect.py) >
    a `(YYYY-MM-DD)` token in the summary body > today KST. Preferring
    raw JSON means the summary body no longer needs a redundant date
    header — collect.py is already the single source of truth.
    """
    if raw_json_path:
        try:
            data = json.loads(Path(raw_json_path).read_text())
            report_date = data.get("report_date")
            if isinstance(report_date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
                return report_date
        except Exception:
            pass
    m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", summary[:500])
    if m:
        return m.group(1)
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")


# ---------- markdown -> Block Kit ----------

_HEADER_RE = re.compile(r"^\*(?P<emoji>[🔥📘📰🧠⚙️✨]*)\s*(?P<title>[^*]+?)\s*\*(?:\s*\([^)]+\))?\s*$")
_ITEM_RE = re.compile(r"^•\s*\*(?P<title>.+?)\*\s*—\s*(?P<url>https?://\S+)\s*$")
_CONTEXT_LINE_RE = re.compile(r"^_(?P<text>.+)_\s*$")


def _flush_item(blocks: list, title: str, url: str, body_lines: list[str]) -> None:
    # Section block: title as bold link + body as blockquote lines
    title_line = f"*<{url}|{title}>*"
    if body_lines:
        body = "\n".join(f"> {line}" for line in body_lines)
        text = f"{title_line}\n{body}"
    else:
        text = title_line
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
    })


def markdown_to_blocks(summary: str) -> list[dict]:
    """Parse the SKILL.md-format summary into Slack Block Kit blocks.

    Known input shape (see SKILL.md):
      *🔥 오늘의 핵심* (YYYY-MM-DD)

      • *title* — url
         body line 1
         body line 2

      *📘 주목할 만한 소식*
      • ...

      ---
      _footer_
    """
    blocks: list[dict] = []
    cur_title: str | None = None
    cur_url: str | None = None
    cur_body: list[str] = []
    context_lines: list[str] = []

    def flush() -> None:
        nonlocal cur_title, cur_url, cur_body
        if cur_title and cur_url:
            _flush_item(blocks, cur_title, cur_url, cur_body)
        cur_title = cur_url = None
        cur_body = []

    for raw in summary.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue  # collapse blank lines; structure comes from block types

        # Section header: *🔥 ...* or *📘 ...*
        hm = _HEADER_RE.match(line.strip())
        if hm and hm.group("emoji"):
            flush()
            header_text = f"{hm.group('emoji')} {hm.group('title')}".strip()
            blocks.append({
                "type": "header",
                "text": {"type": "plain_text", "text": header_text, "emoji": True},
            })
            continue

        # Item start: • *title* — url
        im = _ITEM_RE.match(line.strip())
        if im:
            flush()
            cur_title = im.group("title").strip()
            cur_url = im.group("url").strip()
            continue

        # Divider line
        if line.strip() == "---":
            flush()
            blocks.append({"type": "divider"})
            continue

        # Context line (italic _..._)
        cm = _CONTEXT_LINE_RE.match(line.strip())
        if cm:
            flush()
            context_lines.append(cm.group("text").strip())
            continue

        # Otherwise: body line for the current item (strip leading whitespace)
        if cur_title:
            cur_body.append(line.strip())

    flush()

    if context_lines:
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "_" + line + "_"} for line in context_lines
            ],
        })

    return blocks


_STATS_LABELS: list[tuple[str, str]] = [
    ("hackernews", "HN"),
    ("arxiv", "arXiv"),
    ("huggingface", "HF"),
    ("lab_blogs", "LabRSS"),
    ("anthropic_news", "Anthropic"),
    ("meta_blog", "Meta"),
    ("mistral_news", "Mistral"),
    ("github_trending", "GH"),
]


def load_stats_and_errors(raw_json_path: str) -> tuple[dict | None, dict]:
    """Return (stats, errors) from raw JSON. errors defaults to {} if absent."""
    try:
        data = json.loads(Path(raw_json_path).read_text())
    except Exception:
        return None, {}
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else None
    errors = data.get("errors") if isinstance(data.get("errors"), dict) else {}
    return stats, errors


def format_stats_line(stats: dict, errors: dict | None = None) -> str:
    """Format per-source counts, appending ⚠️ when a source had fetch errors —
    so a genuine empty-window 0 is visibly different from a silently-broken 0."""
    errors = errors or {}
    parts = []
    for key, label in _STATS_LABELS:
        n = stats.get(key, 0)
        mark = "⚠️" if errors.get(key, 0) > 0 else ""
        parts.append(f"{label} {n}{mark}")
    return "📊 수집: " + " · ".join(parts)


def append_stats_context(blocks: list[dict], stats_line: str) -> None:
    """Append stats_line as an italic element on the trailing context block
    (or add a new context block if none exists)."""
    element = {"type": "mrkdwn", "text": "_" + stats_line + "_"}
    if blocks and blocks[-1].get("type") == "context":
        blocks[-1]["elements"].append(element)
    else:
        blocks.append({"type": "context", "elements": [element]})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary_file", help="Path to the markdown summary to send")
    parser.add_argument("--token", type=str, default=None, help="Override SLACK_BOT_TOKEN")
    parser.add_argument("--channel", type=str, default=None, help="Override SLACK_CHANNEL_ID")
    parser.add_argument("--raw-json", type=str, default="/tmp/ai-digest-raw.json",
                        help="Path to raw JSON; its 'stats' dict is appended as a footer context line")
    parser.add_argument("--dry-run", action="store_true", help="Print payload, do not POST")
    args = parser.parse_args()

    token = (args.token or os.environ.get("SLACK_BOT_TOKEN", "")).strip()
    channel = (args.channel or os.environ.get("SLACK_CHANNEL_ID", "")).strip()

    body = Path(args.summary_file).read_text().strip()
    if not body:
        print("ERROR: summary file is empty", file=sys.stderr)
        return 2

    date_str = extract_date(body, args.raw_json)
    headline = f"🔥 오늘의 AI 소식 ({date_str})"
    blocks = markdown_to_blocks(body)

    # Append per-source collection counts so silent scraper failures become visible
    # in every Slack thread. Error-count marker (⚠️) distinguishes "0 items because
    # fetch failed" from "0 items because the 24h window was empty".
    stats, errors = load_stats_and_errors(args.raw_json)
    if stats:
        append_stats_context(blocks, format_stats_line(stats, errors))

    if args.dry_run:
        print("--- DRY RUN ---")
        print(f"[parent] channel={channel or '(unset)'} text={headline!r}")
        print(f"[thread reply] {len(blocks)} blocks, {len(body)} chars fallback text")
        print(json.dumps(blocks, ensure_ascii=False, indent=2))
        print("--- (would POST parent then thread reply with blocks) ---")
        return 0

    if not token or not token.startswith("xoxb-"):
        print("ERROR: SLACK_BOT_TOKEN missing or not a Bot User token (expected xoxb-...).",
              file=sys.stderr)
        return 2
    if not channel:
        print("ERROR: SLACK_CHANNEL_ID missing. Use the channel ID (e.g. C0123ABCDEF), "
              "not the #name.", file=sys.stderr)
        return 2

    try:
        parent = post_chat_message(token, channel, headline)
        thread_ts = parent["ts"]
        post_chat_message(token, channel, body, blocks=blocks, thread_ts=thread_ts)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: HTTP/network failure: {e}", file=sys.stderr)
        return 1

    print(f"OK: posted parent ts={thread_ts} + thread reply ({len(blocks)} blocks) to {channel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
