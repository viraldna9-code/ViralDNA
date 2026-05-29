#!/usr/bin/env python3
"""
ViralDNA Stage 1+2: Viral News Monitor + Telegram Alerts
===========================================================
Runs every 30 minutes via cron.
Polls RSS + Google Trends + Reddit, scores topics with editorial filter.

STRATEGY:
  - 1 main video per day (morning ~9 AM IST)
  - 2 shorts per day (afternoon ~3 PM + evening ~6:30 PM IST)
  - Monitor runs every 30 min accumulating topics
  - Only alerts when a topic scores >= 18/30 AND is AP/Telangana relevant
  - User approves via Telegram reply before production starts

Usage:
  python3 monitor_and_alert.py           # full monitoring run
  python3 monitor_and_alert.py --dry-run # scan only, don't send alerts
"""
import sys
import os
import json
import re as _re
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

# ── Bootstrap ──
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    load_dotenv(os.path.expanduser("~/.env"))
except ImportError:
    pass

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
IST = ZoneInfo("Asia/Kolkata")
ALERT_STATE_FILE = os.path.join(PROJECT_ROOT, "logs", "alert_state.json")
TOPICS_ACCUMULATOR_FILE = os.path.join(PROJECT_ROOT, "logs", "topics_accumulator.json")

# ── Import editorial scorer ──
from modules.editorial_scorer import editorial_score

# ── Telegram ──
def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ⚠️ Telegram credentials missing")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        return result.get("ok", False)
    except Exception as e:
        print(f"  ⚠️ Telegram send failed: {e}")
        return False

# ── Alert State (dedup: don't re-alert same topic within 6h) ──
def load_alert_state():
    os.makedirs(os.path.dirname(ALERT_STATE_FILE), exist_ok=True)
    if os.path.exists(ALERT_STATE_FILE):
        try:
            with open(ALERT_STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"alerted_topics": {}}

def save_alert_state(state):
    os.makedirs(os.path.dirname(ALERT_STATE_FILE), exist_ok=True)
    with open(ALERT_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def is_already_alerted(topic_title: str, state: dict) -> bool:
    key = topic_title.lower().strip()
    if key in state.get("alerted_topics", {}):
        last_alert = datetime.fromisoformat(state["alerted_topics"][key])
        if datetime.now(IST) - last_alert < timedelta(hours=6):
            return True
    return False

def mark_alerted(topic_title: str, state: dict):
    state.setdefault("alerted_topics", {})[topic_title.lower().strip()] = datetime.now(IST).isoformat()
    cutoff = datetime.now(IST) - timedelta(hours=24)
    state["alerted_topics"] = {
        k: v for k, v in state["alerted_topics"].items()
        if datetime.fromisoformat(v) > cutoff
    }

# ── Source 1: RSS ──
def poll_rss():
    import feedparser
    sources = [
        "https://www.thehindu.com/news/national/andhra-pradesh/feeder/default.rss",
        "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
        "https://news.google.com/rss/search?q=Andhra+Pradesh&hl=en-IN&gl=IN&ceid=IN:en",
        "https://feeds.feedburner.com/ndtvnews-top-stories",
        "https://www.thehindu.com/news/national/feeder/default.rss",
    ]
    topics = []
    for url in sources:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                title = entry.get("title", "").strip()
                if title:
                    topics.append({
                        "title": title,
                        "source": url.split("/")[2],
                        "link": entry.get("link", ""),
                        "num_sources": 1,
                    })
        except Exception as e:
            print(f"    ⚠️ RSS fail: {url[:40]} | {e}")
    return topics

# ── Source 2: Google Trends (via RSS — pytrends API 404 workaround) ──
def poll_google_trends():
    topics = []
    try:
        url = "https://trends.google.com/trending/rss?geo=IN"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        page = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="replace")
        titles = _re.findall(r"<title><!\[CDATA\[(.*?)\]\]>", page)
        titles += _re.findall(r"<title>(.*?)</title>", page)
        for t in titles:
            t = t.strip()
            if t and t != "Daily Search Trends" and len(t) > 2:
                topics.append({
                    "title": t,
                    "source": "Google Trends India",
                    "link": f"https://news.google.com/search?q={t.replace(' ', '+')}",
                    "num_sources": 1,
                    "trending_score": "high",
                })
    except Exception as e:
        print(f"    ⚠️ Google Trends fail: {e}")
    return topics

# ── Source 3: Reddit ──
def poll_reddit():
    topics = []
    subreddits = ["india", "AndhraPradesh", "tollywood", "telangana", "hyderabad"]
    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=5"
            req = urllib.request.Request(url, headers={"User-Agent": "ViralDNABot/1.0"})
            resp = urllib.request.urlopen(req, timeout=8)
            data = json.loads(resp.read())
            for post in data.get("data", {}).get("children", []):
                p = post.get("data", {})
                title = p.get("title", "")
                if title:
                    topics.append({
                        "title": title,
                        "source": f"Reddit r/{sub} [{p.get('score', 0)} upvotes]",
                        "link": "https://reddit.com" + p.get("permalink", ""),
                        "num_sources": 1,
                    })
        except Exception as e:
            print(f"    ⚠️ Reddit r/{sub} fail: {e}")
    return topics

# ── Dedup ──
def deduplicate(topics: list) -> list:
    seen = {}
    for t in topics:
        key = _re.sub(r'^(breaking|update|news|latest)[:\\s]+', '', t["title"].lower().strip(), flags=_re.IGNORECASE).strip()
        if key not in seen:
            seen[key] = t
        else:
            seen[key]["num_sources"] = seen[key].get("num_sources", 1) + 1
    return list(seen.values())

# ── Main ──
def main():
    dry_run = "--dry-run" in sys.argv
    now = datetime.now(IST)
    print(f"\n{'='*60}")
    print(f"  ViralDNA Monitor — {now.strftime('%Y-%m-%d %H:%M IST')}")
    print(f"{'='*60}")

    if dry_run:
        print("  [DRY RUN — no alerts will be sent]")

    # ── Poll all sources ──
    print("\n  [1/4] Polling RSS feeds...")
    rss_topics = poll_rss()
    print(f"        → {len(rss_topics)} topics from RSS")

    print("  [2/4] Polling Google Trends...")
    gt_topics = poll_google_trends()
    print(f"        → {len(gt_topics)} topics from Google Trends")

    print("  [3/4] Polling Reddit...")
    reddit_topics = poll_reddit()
    print(f"        → {len(reddit_topics)} topics from Reddit")

    # ── Merge + dedup ──
    all_topics = rss_topics + gt_topics + reddit_topics
    print(f"\n  Total raw topics: {len(all_topics)}")
    all_topics = deduplicate(all_topics)
    print(f"  After dedup: {len(all_topics)}")

    # ── Editorial score each topic ──
    for t in all_topics:
        result = editorial_score(t)
        t["editorial_score"] = result["score"]
        t["editorial_reasons"] = result["reasons"]
        t["recommendation"] = result["recommendation"]

    # Sort by editorial score
    all_topics.sort(key=lambda x: x.get("editorial_score", 0), reverse=True)

    # ── Print ALL topics with scores ──
    print(f"\n  {'Score':>5} | {'Rec':4} | Topic")
    print(f"  {'-'*5} | {'-'*4} | {'-'*50}")
    for t in all_topics:
        s = t["editorial_score"]
        rec = t["recommendation"][:4]
        mark = "★" if s >= 18 else " "
        print(f"  {s:>5} | {rec:4} | {mark} {t['title'][:60]}")
        if s >= 14:
            print(f"        |      |   └─ {' | '.join(t['editorial_reasons'][:3])}")

    # ── Find THE ONE topic worth producing ──
    # Criteria: editorial score >= 18 (max 30)
    PRODUCE_THRESHOLD = 18
    produce_topics = [t for t in all_topics if t["editorial_score"] >= PRODUCE_THRESHOLD]

    # Also find "consider" topics (14-17) as backups
    consider_topics = [t for t in all_topics if 14 <= t["editorial_score"] < PRODUCE_THRESHOLD]

    print(f"\n  ─── PRODUCE topics (≥{PRODUCE_THRESHOLD}): {len(produce_topics)} ───")
    for t in produce_topics[:3]:
        print(f"    🟢 [{t['editorial_score']}] {t['title'][:70]}")
        print(f"       {' | '.join(t['editorial_reasons'])}")

    print(f"\n  ─── CONSIDER topics (14-{PRODUCE_THRESHOLD-1}): {len(consider_topics)} ───")
    for t in consider_topics[:3]:
        print(f"    🟡 [{t['editorial_score']}] {t['title'][:70]}")

    if not produce_topics and not consider_topics:
        print("\n  ✅ No topics worth producing. Channel stays quiet.")
        print(f"{'='*60}\n")
        return

    # ── Pick THE ONE best topic ──
    best_topic = (produce_topics or consider_topics)[0]

    # Check if already alerted
    state = load_alert_state()
    if is_already_alerted(best_topic["title"], state):
        print(f"\n  ⏭️ Best topic already alerted (6h): {best_topic['title'][:50]}")
        print(f"{'='*60}\n")
        return

    print(f"\n  🔔 BEST TOPIC: [{best_topic['editorial_score']}] {best_topic['title']}")
    print(f"     {' | '.join(best_topic['editorial_reasons'])}")

    if dry_run:
        print(f"\n  [DRY] Would alert on: {best_topic['title'][:60]}")
        print(f"{'='*60}\n")
        return

    # ── Save last topic for reply handler ──
    from modules.pipeline_trigger import save_last_topic
    save_last_topic(best_topic)

    # ── Send Telegram alert for THE ONE topic ──
    now_str = now.strftime("%d %b %H:%M IST")
    score = best_topic["editorial_score"]
    title = best_topic["title"]
    source = best_topic["source"]
    link = best_topic.get("link", "")
    rec = best_topic["recommendation"]
    reasons = best_topic["editorial_reasons"]

    alert_text = (
        f"🎬 <b>ViralDNA — Topic Alert</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {now_str}\n"
        f"📊 Editorial Score: <b>{score}/30</b>\n"
        f"{rec}\n\n"
        f"📰 <b>{title}</b>\n"
        f"📡 Source: {source}\n"
        f"🔗 {link}\n\n"
        f"📋 <b>Scoring:</b>\n"
    )
    for r in reasons[:5]:
        alert_text += f"  • {r}\n"

    # Add backup topics if any
    if consider_topics:
        alert_text += "\n📌 <b>Backup topics:</b>\n"
        for t in consider_topics[:2]:
            alert_text += f"  🟡 [{t['editorial_score']}] {t['title'][:60]}\n"

    alert_text += (
        f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Production plan: 1 main + 2 shorts</b>\n"
        f"⏰ Morning upload slot: ~9 AM IST\n\n"
        f"Reply <b>YES</b> to start production.\n"
        f"Reply <b>NO</b> to skip."
    )
    sent = send_telegram(alert_text)
    if sent:
        mark_alerted(best_topic["title"], state)
        save_alert_state(state)
        print(f"  ✅ Telegram alert sent!")
    else:
        print("  ❌ Telegram alert failed — will retry next cycle")

    print(f"\n{'='*60}")
    print(f"  Monitor complete — {datetime.now(IST).strftime('%H:%M:%S IST')}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
