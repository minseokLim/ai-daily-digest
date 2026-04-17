#!/usr/bin/env python3
"""
AI Daily Digest — Slack Sender

Reads a markdown summary file and posts it to the Slack Incoming Webhook.

Webhook URL resolution order:
  1. --webhook CLI flag (highest priority, for ad-hoc overrides)
  2. SLACK_WEBHOOK_URL environment variable (recommended for Routines)
  3. slack_webhook_url in config.json (fallback for local dev only)

In Claude Code Routines, set SLACK_WEBHOOK_URL in the cloud environment's
Environment variables. Don't commit the webhook URL to config.json or any
other file in the repo.

Slack mrkdwn supports a subset of markdown: *bold*, _italic_, ~strike~,
`code`, ```code block```, and <URL|text> links. We pass the body through
mostly as-is — the summarizer is expected to follow that dialect.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def resolve_webhook(cli_webhook: str | None, config_path: Path) -> str:
    if cli_webhook:
        return cli_webhook.strip()
    env_val = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if env_val:
        return env_val
    try:
        config = json.loads(config_path.read_text())
    except FileNotFoundError:
        return ""
    return (config.get("slack_webhook_url") or "").strip()


def post_to_slack(webhook_url: str, text: str) -> tuple[int, str]:
    payload = json.dumps({
        "text": text,
        "unfurl_links": False,
        "unfurl_media": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary_file", help="Path to the markdown summary to send")
    parser.add_argument("--config", type=str, default=str(CONFIG_PATH))
    parser.add_argument("--webhook", type=str, default=None, help="Override webhook URL (beats env + config)")
    parser.add_argument("--dry-run", action="store_true", help="Print payload, do not POST")
    args = parser.parse_args()

    webhook = resolve_webhook(args.webhook, Path(args.config))
    if not webhook or "REPLACE_ME" in webhook:
        print(
            "ERROR: no Slack webhook URL found.\n"
            "  Set SLACK_WEBHOOK_URL env var (recommended),\n"
            "  or pass --webhook, or add slack_webhook_url to config.json (local dev).",
            file=sys.stderr,
        )
        return 2

    body = Path(args.summary_file).read_text().strip()
    if not body:
        print("ERROR: summary file is empty", file=sys.stderr)
        return 2

    if args.dry_run:
        print("--- DRY RUN ---")
        print(body)
        print("--- (would POST above to Slack webhook) ---")
        return 0

    status, resp = post_to_slack(webhook, body)
    if status >= 400:
        print(f"Slack returned {status}: {resp}", file=sys.stderr)
        return 1
    print(f"OK ({status}): {resp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
