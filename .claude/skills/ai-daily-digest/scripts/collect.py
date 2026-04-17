#!/usr/bin/env python3
"""
AI Daily Digest — Source Collector

Collects items from 5 sources for the past N hours and writes a normalized
JSON file. Designed to fail gracefully: if one source breaks, the rest still
proceed.

Output schema (list of items):
  {
    "source": "hackernews" | "arxiv" | "huggingface" | "lab_blog" | "github_trending",
    "title": str,
    "url": str,
    "published_at": ISO8601 str | None,
    "summary": str | None,            # short text snippet if available
    "extra": dict                     # source-specific metadata (points, authors, stars, etc.)
  }
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 15
USER_AGENT = "ai-daily-digest/1.0 (+https://github.com/anthropic-cowork)"

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


# ---------- helpers ----------

def _http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _json_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    return json.loads(_http_get(url, timeout=timeout).decode("utf-8"))


def _strip_html(s: str) -> str:
    # Cheap-and-cheerful HTML stripper for RSS summaries.
    s = re.sub(r"<[^>]+>", "", s)
    return unescape(re.sub(r"\s+", " ", s)).strip()


def _within_window(published_iso: str | None, since: datetime) -> bool:
    if not published_iso:
        return True  # if unknown, keep it; downstream summarizer can decide.
    try:
        dt = datetime.fromisoformat(published_iso.replace("Z", "+00:00"))
        return dt >= since
    except Exception:
        return True


# ---------- sources ----------

def fetch_hackernews(since: datetime, keywords: list[str], min_points: int) -> list[dict]:
    """Hacker News via Algolia search-by-date. One query per keyword, dedup by objectID."""
    seen: dict[str, dict] = {}
    since_ts = int(since.timestamp())
    for kw in keywords:
        url = (
            "https://hn.algolia.com/api/v1/search_by_date"
            f"?query={urllib.parse.quote(kw)}"
            f"&tags=story&numericFilters=created_at_i>{since_ts},points>={min_points}"
            "&hitsPerPage=30"
        )
        try:
            data = _json_get(url)
        except Exception as e:
            print(f"  [hn:{kw}] fetch error: {e}", file=sys.stderr)
            continue
        for hit in data.get("hits", []):
            oid = hit.get("objectID")
            if not oid or oid in seen:
                continue
            link = hit.get("url") or f"https://news.ycombinator.com/item?id={oid}"
            seen[oid] = {
                "source": "hackernews",
                "title": hit.get("title") or "(no title)",
                "url": link,
                "published_at": hit.get("created_at"),
                "summary": None,
                "extra": {
                    "points": hit.get("points"),
                    "num_comments": hit.get("num_comments"),
                    "hn_url": f"https://news.ycombinator.com/item?id={oid}",
                    "matched_keyword": kw,
                },
            }
    items = sorted(seen.values(), key=lambda x: x["extra"].get("points") or 0, reverse=True)
    return items[:25]


def fetch_arxiv(since: datetime) -> list[dict]:
    """arXiv cs.AI + cs.LG + cs.CL, recent submissions."""
    url = (
        "http://export.arxiv.org/api/query"
        "?search_query=cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL"
        "&sortBy=submittedDate&sortOrder=descending&max_results=40"
    )
    try:
        raw = _http_get(url)
    except Exception as e:
        print(f"  [arxiv] fetch error: {e}", file=sys.stderr)
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(raw)
    items: list[dict] = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link_el = entry.find('a:link[@rel="alternate"]', ns) or entry.find("a:link", ns)
        link = link_el.get("href") if link_el is not None else None
        published = entry.findtext("a:published", default=None, namespaces=ns)
        summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
        authors = [a.findtext("a:name", default="", namespaces=ns) for a in entry.findall("a:author", ns)]
        if not link or not _within_window(published, since):
            continue
        items.append({
            "source": "arxiv",
            "title": re.sub(r"\s+", " ", title),
            "url": link,
            "published_at": published,
            "summary": re.sub(r"\s+", " ", summary)[:1200],
            "extra": {"authors": authors[:8]},
        })
    return items


def fetch_huggingface_papers() -> list[dict]:
    """HuggingFace Daily Papers."""
    try:
        data = _json_get("https://huggingface.co/api/daily_papers")
    except Exception as e:
        print(f"  [hf] fetch error: {e}", file=sys.stderr)
        return []
    items: list[dict] = []
    for entry in data[:30]:
        paper = entry.get("paper") or {}
        pid = paper.get("id")
        if not pid:
            continue
        items.append({
            "source": "huggingface",
            "title": paper.get("title") or entry.get("title") or "(no title)",
            "url": f"https://huggingface.co/papers/{pid}",
            "published_at": entry.get("publishedAt"),
            "summary": (paper.get("summary") or "")[:1200],
            "extra": {
                "upvotes": paper.get("upvotes"),
                "num_comments": entry.get("numComments"),
                "arxiv_id": pid,
            },
        })
    items.sort(key=lambda x: x["extra"].get("upvotes") or 0, reverse=True)
    return items[:15]


def fetch_lab_blogs(feeds: list[dict], since: datetime) -> list[dict]:
    items: list[dict] = []
    for feed in feeds:
        try:
            raw = _http_get(feed["url"])
        except Exception as e:
            print(f"  [blog:{feed['name']}] fetch error: {e}", file=sys.stderr)
            continue
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            print(f"  [blog:{feed['name']}] parse error: {e}", file=sys.stderr)
            continue
        # Handle both RSS 2.0 and Atom
        for entry in root.iter():
            tag = entry.tag.rsplit("}", 1)[-1]
            if tag not in ("item", "entry"):
                continue
            title_el = next((c for c in entry if c.tag.rsplit("}", 1)[-1] == "title"), None)
            link_el = next((c for c in entry if c.tag.rsplit("}", 1)[-1] == "link"), None)
            pub_el = next((c for c in entry if c.tag.rsplit("}", 1)[-1] in ("pubDate", "published", "updated")), None)
            desc_el = next((c for c in entry if c.tag.rsplit("}", 1)[-1] in ("description", "summary", "content")), None)
            title = (title_el.text or "").strip() if title_el is not None else ""
            link = (link_el.get("href") if (link_el is not None and link_el.get("href")) else (link_el.text if link_el is not None else "")) or ""
            pub_raw = (pub_el.text or "").strip() if pub_el is not None else ""
            # Try to normalize a few date formats
            pub_iso = None
            for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    pub_iso = datetime.strptime(pub_raw, fmt).astimezone(timezone.utc).isoformat()
                    break
                except Exception:
                    continue
            if pub_iso is None and pub_raw:
                pub_iso = pub_raw  # keep raw, summarizer can ignore
            if not _within_window(pub_iso, since):
                continue
            items.append({
                "source": "lab_blog",
                "title": title,
                "url": link.strip(),
                "published_at": pub_iso,
                "summary": _strip_html(desc_el.text or "")[:600] if (desc_el is not None and desc_el.text) else None,
                "extra": {"lab": feed["name"]},
            })
    return items


_MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
           "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _parse_human_date(s: str) -> str | None:
    """Parse 'Apr 16, 2026' or 'April 16, 2026' -> ISO 8601 UTC. Return None if unparseable."""
    m = re.search(r"\b([A-Z][a-z]{2,8})\s+(\d{1,2}),\s*(\d{4})\b", s)
    if not m:
        return None
    mon = _MONTHS.get(m.group(1)[:3])
    if not mon:
        return None
    try:
        dt = datetime(int(m.group(3)), mon, int(m.group(2)), tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def fetch_anthropic_news(since: datetime) -> list[dict]:
    """Anthropic /news — HTML scrape (no RSS feed available)."""
    try:
        html = _http_get("https://www.anthropic.com/news").decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [blog:Anthropic] fetch error: {e}", file=sys.stderr)
        return []
    items: list[dict] = []
    seen: set[str] = set()
    # Each card is an <a href="/news/<slug>" ...>...</a> containing title + <time>.
    for m in re.finditer(r'<a[^>]*href="(/news/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        slug = m.group(1)
        if slug in seen:
            continue
        block = m.group(2)
        title_match = re.search(r'<h2[^>]*>([^<]+)</h2>', block) or \
                      re.search(r'<span[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</span>', block)
        time_match = re.search(r'<time[^>]*>([^<]+)</time>', block)
        if not title_match or not time_match:
            continue
        pub_iso = _parse_human_date(time_match.group(1))
        if not _within_window(pub_iso, since):
            continue
        seen.add(slug)
        items.append({
            "source": "lab_blog",
            "title": _strip_html(title_match.group(1)),
            "url": "https://www.anthropic.com" + slug,
            "published_at": pub_iso,
            "summary": None,
            "extra": {"lab": "Anthropic"},
        })
    return items


def fetch_meta_blog(since: datetime) -> list[dict]:
    """Meta AI /blog — HTML scrape (no RSS feed available).

    Cards contain an <a href="https://ai.meta.com/blog/<slug>/"> with the title
    as inner text, followed by a sibling <div> with a 'Mon DD, YYYY' date.
    """
    try:
        html = _http_get("https://ai.meta.com/blog/").decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [blog:Meta AI] fetch error: {e}", file=sys.stderr)
        return []
    items: list[dict] = []
    seen: set[str] = set()
    # Title-text anchors: <a ... href=".../blog/<slug>/">TITLE</a>. The date appears in a
    # sibling <div> within a few hundred chars after </a> (markup varies between featured
    # and list cards, so search a window instead of requiring an adjacent tag).
    anchor_pattern = re.compile(
        r'<a[^>]*href="(https://ai\.meta\.com/blog/([^/"]+)/)"[^>]*>([^<]{3,})</a>',
        re.DOTALL,
    )
    for m in anchor_pattern.finditer(html):
        url, slug, title = m.group(1), m.group(2), m.group(3)
        if slug in seen:
            continue
        tail = html[m.end():m.end() + 500]
        pub_iso = _parse_human_date(tail)
        if not pub_iso:
            continue
        if not _within_window(pub_iso, since):
            continue
        seen.add(slug)
        items.append({
            "source": "lab_blog",
            "title": _strip_html(title).strip(),
            "url": url,
            "published_at": pub_iso,
            "summary": None,
            "extra": {"lab": "Meta AI"},
        })
    return items


def fetch_mistral_news(since: datetime) -> list[dict]:
    """Mistral /news — sitemap.xml for URL+lastmod, then per-page fetch for og:title.

    Mistral's news list is client-rendered, so HTML scraping of /news gives nothing.
    The sitemap lists every news article with a lastmod timestamp we can filter on.
    """
    try:
        raw = _http_get("https://mistral.ai/sitemap.xml")
    except Exception as e:
        print(f"  [blog:Mistral] fetch error: {e}", file=sys.stderr)
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"  [blog:Mistral] sitemap parse error: {e}", file=sys.stderr)
        return []
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    candidates: list[tuple[str, str]] = []  # (url, lastmod_iso)
    for url_el in root.findall("sm:url", ns):
        loc = (url_el.findtext("sm:loc", default="", namespaces=ns) or "").strip()
        lastmod = (url_el.findtext("sm:lastmod", default="", namespaces=ns) or "").strip()
        if "/news/" not in loc:
            continue
        # Skip listing pages and non-article paths
        if loc.rstrip("/").endswith("/news"):
            continue
        if not _within_window(lastmod, since):
            continue
        candidates.append((loc, lastmod))
    # Fetch og:title for each candidate (keep small — filter is already tight)
    items: list[dict] = []
    for url, pub_iso in candidates[:10]:
        try:
            page = _http_get(url).decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  [blog:Mistral:{url}] fetch error: {e}", file=sys.stderr)
            continue
        tm = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', page)
        if not tm:
            continue
        title = _strip_html(tm.group(1))
        # Strip trailing " | Mistral AI" boilerplate
        title = re.sub(r"\s*\|\s*Mistral AI\s*$", "", title).strip()
        items.append({
            "source": "lab_blog",
            "title": title,
            "url": url,
            "published_at": pub_iso,
            "summary": None,
            "extra": {"lab": "Mistral"},
        })
    return items


def fetch_github_trending() -> list[dict]:
    """GitHub Trending (Python, daily). HTML scrape — best-effort."""
    try:
        html = _http_get("https://github.com/trending/python?since=daily").decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [gh] fetch error: {e}", file=sys.stderr)
        return []
    items: list[dict] = []
    # Each repo block contains <h2 class="h3 lh-condensed"> with an <a href="/owner/repo">
    repo_blocks = re.findall(
        r'<h2[^>]*class="h3 lh-condensed"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>(.*?)(?=<article|</main)',
        html, re.DOTALL)
    for href, name_html, body in repo_blocks[:25]:
        name = re.sub(r"\s+", "", _strip_html(name_html))
        desc_match = re.search(r'<p[^>]*class="col-9[^"]*"[^>]*>(.*?)</p>', body, re.DOTALL)
        desc = _strip_html(desc_match.group(1)) if desc_match else ""
        stars_today_match = re.search(r"(\d[\d,]*)\s*stars today", body)
        stars_today = int(stars_today_match.group(1).replace(",", "")) if stars_today_match else None
        # Filter for AI-ish repos: simple keyword check on name+desc
        blob = (name + " " + desc).lower()
        ai_kw = ("llm", "ai", "gpt", "claude", "agent", "rag", "transformer", "diffusion",
                 "ml", "neural", "model", "vision", "speech", "embedding", "retrieval",
                 "prompt", "inference", "fine-tun", "training")
        if not any(k in blob for k in ai_kw):
            continue
        items.append({
            "source": "github_trending",
            "title": name,
            "url": "https://github.com" + href,
            "published_at": None,
            "summary": desc[:400] if desc else None,
            "extra": {"stars_today": stars_today},
        })
    return items


# ---------- main ----------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--out", type=str, default="/tmp/ai-digest-raw.json")
    parser.add_argument("--config", type=str, default=str(CONFIG_PATH))
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text())
    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    print(f"Collecting AI news since {since.isoformat()}")

    sources = [
        ("hackernews", lambda: fetch_hackernews(since, config["hn_keywords"], config["hn_min_points"])),
        ("arxiv", lambda: fetch_arxiv(since)),
        ("huggingface", lambda: fetch_huggingface_papers()),
        ("lab_blogs", lambda: fetch_lab_blogs(config["lab_blog_feeds"], since)),
        ("anthropic_news", lambda: fetch_anthropic_news(since)),
        ("meta_blog", lambda: fetch_meta_blog(since)),
        ("mistral_news", lambda: fetch_mistral_news(since)),
        ("github_trending", lambda: fetch_github_trending()),
    ]
    all_items: list[dict] = []
    stats: dict[str, int] = {}
    for name, fn in sources:
        t0 = time.time()
        try:
            items = fn() or []
        except Exception as e:
            print(f"[{name}] FAILED: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            items = []
        dt = time.time() - t0
        stats[name] = len(items)
        print(f"[{name}] {len(items)} items in {dt:.1f}s")
        all_items.extend(items)

    now_utc = datetime.now(timezone.utc)
    # report_date: the human-facing date the digest represents. KST, since the
    # routine targets Korean readers and fires at 09:00 KST. Using UTC here
    # produced off-by-one headlines whenever the routine ran before 09:00 KST
    # (== before 00:00 UTC), so we pin it to KST explicitly.
    report_date = now_utc.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    output = {
        "generated_at": now_utc.isoformat(),
        "report_date": report_date,
        "lookback_hours": args.hours,
        "stats": stats,
        "items": all_items,
    }
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\nWrote {len(all_items)} total items to {args.out}")
    print(f"Per-source breakdown: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
