#!/usr/bin/env python3
"""
ViralDNA Spike Monitor — GitHub Actions Edition
================================================
Runs every 30 min on GitHub Actions (cloud).
Polls RSS + Google Trends + Reddit, scores topics editorially.
Sends Telegram alert if a topic scores >= 14/30.
Saves best topics to topics.json (persisted in repo via git push).

Credentials: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID from GitHub Secrets.
"""

import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

# ── Config ──
IST = timezone(timedelta(hours=5, minutes=30))
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "viraldna9-code/ViralDNA")

TOPICS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
TOPICS_FILE = os.path.join(TOPICS_DIR, "topics_history.json")

# Viral keywords (high engagement potential)
VIRAL_KEYWORDS = {
    "shocking": 4, "breakthrough": 4, "exclusive": 4, "alert": 3,
    "crisis": 3, "massive": 3, "urgent": 3, "breaking": 3,
    "dead": 5, "death": 4, "murder": 5, "scam": 4, "fraud": 4,
    "arrest": 4, "rape": 5, "suicide": 4, "accident": 3,
    "bomb": 5, "terror": 5, "war": 4, "protest": 3, "riot": 4,
    "corruption": 3, "scandal": 4, "viral": 3, "shocking": 4,
}

# AP/Telangana relevance
AP_TE_TERMS = [
    "andhra", "telangana", "telugu", "amaravati", "visakhapatnam", "vijayawada",
    "guntur", "kurnool", "nellore", "tirupati", "kadapa", "anantapur",
    "warangal", "nizamabad", "karimnagar", "khammam", "mahbubnagar",
    "hyderabad", "secunderabad", "nampally", "rayalaseema", "coastal andhra",
    "tollywood", "telugu cinema", "telugu actor", "telugu actress",
    "tdp", "ysrcp", "bjp", "congress", "chandrababu", "jagan", "kcr",
    "cm", "chief minister", "mla", "mp", "minister", "andhra pradesh",
    "telangana rashtra", "andhra university", "jntu", "iit tirupati",
    "ongole", "srikakulam", "vizianagaram", "eluru", "bhimavaram",
    "rajahmundry", "machilipatnam", "kakinada", "narasaraopet",
    "gadwal", "nalgonda", "rangareddy", "sangareddy", "nagarkurnool",
    "palamuru", "wanaparthy", "jogulamba", "vikarabad", "medak",
    "siddipet", "jangaon", "bhuvanagiri", "yal", "app", "ts",
]

CHANNEL_GROWTH_TOPICS = [
    "cricket", "tollywood", "telugu cinema", "weather", "flood",
    "cyclone", "exam results", "jobs", "visa", "immigration",
    "farmers", "bundh", "strike", "bandh", "temple", "festival",
    "sankranti", "ugadi", "dasara", "deepavali", "bathukamma",
]


def score_editorial(title, source_topics):
    """Score a topic for channel growth potential (0-30)."""
    t = title.lower()
    score = 0
    breakdown = []

    # 1. AP/Telangana direct relevance (+10)
    if any(term in t for term in AP_TE_TERMS):
        score += 10
        breakdown.append("DIRECT AP/TELANGANA +10")

    # 2. Channel growth topic (+6)
    if any(term in t for term in CHANNEL_GROWTH_TOPICS):
        score += 6
        breakdown.append("ChannelGrowth +6")

    # 3. Viral keyword bonus (max +6)
    kw_score = 0
    for kw, pts in VIRAL_KEYWORDS.items():
        if kw in t:
            kw_score += pts
    if kw_score > 0:
        kw_score = min(kw_score, 6)
        score += kw_score
        breakdown.append(f"ViralKW +{kw_score}")

    # 4. Cross-source bonus (max +4)
    src_count = sum(1 for topics in source_topics.values() if title in topics)
    if src_count >= 3:
        score += 4
        breakdown.append("CrossSrc(3+) +4")
    elif src_count >= 2:
        score += 2
        breakdown.append("CrossSrc(2) +2")

    return min(score, 30), breakdown


def poll_rss():
    """Poll RSS feeds for trending topics."""
    feeds = [
        ("The Hindu", "https://www.thehindu.com/news/national/?service=rss"),
        ("TOI", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"),
        ("Google News", "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"),
        ("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories"),
        ("Indian Express", "https://indianexpress.com/feed/"),
    ]
    topics = []
    for name, url in feeds:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            root = ET.fromstring(resp.read())
            items = root.findall(".//item")[:10]
            for item in items:
                title = item.findtext("title", "").strip()
                if title and len(title) > 10:
                    topics.append({"title": title, "source": name, "url": item.findtext("link", "")})
        except Exception:
            pass
    return topics


def poll_google_trends_rss():
    """Poll Google Trends via RSS (pytrends workaround)."""
    topics = []
    try:
        url = "https://trends.google.com/trending/rss?geo=IN"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        root = ET.fromstring(resp.read())
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title", "").strip()
            if title:
                topics.append({"title": title, "source": "GoogleTrends", "url": item.findtext("link", "")})
    except Exception:
        pass
    return topics


def poll_reddit():
    """Poll Reddit for trending topics."""
    topics = []
    subs = ["india", "AndhraPradesh", "telangana", "tollywood", "hyderabad"]
    for sub in subs:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=10"
            req = urllib.request.Request(url, headers={"User-Agent": "ViralDNA-Monitor/1.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            for post in data.get("data", {}).get("children", []):
                title = post.get("data", {}).get("title", "").strip()
                if title and len(title) > 10:
                    topics.append({"title": title, "source": f"Reddit/r/{sub}", "url": ""})
        except Exception:
            pass
    return topics


def send_telegram(message):
    """Send Telegram message via bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  Telegram: no credentials, skipping")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        return result.get("ok", False)
    except Exception as e:
        print(f"  Telegram error: {e}")
        return False


def load_topics_history():
    """Load previously seen topics."""
    os.makedirs(TOPICS_DIR, exist_ok=True)
    if os.path.exists(TOPICS_FILE):
        with open(TOPICS_FILE) as f:
            return json.load(f)
    return {"topics": [], "last_alert": None}


def save_topics_history(history):
    """Save topics history."""
    os.makedirs(TOPICS_DIR, exist_ok=True)
    with open(TOPICS_FILE, "w") as f:
        json.dump(history, f, indent=2)


def main():
    now = datetime.now(IST)
    now_str = now.strftime("%Y-%m-%d %H:%M IST")
    print(f"ViralDNA Spike Monitor — {now_str}")
    print("=" * 50)

    # ── Poll all sources ──
    print("\n[1/3] Polling RSS feeds...")
    rss_topics = poll_rss()
    print(f"  → {len(rss_topics)} topics from RSS")

    print("[2/3] Polling Google Trends...")
    gt_topics = poll_google_trends_rss()
    print(f"  → {len(gt_topics)} topics from Google Trends")

    print("[3/3] Polling Reddit...")
    reddit_topics = poll_reddit()
    print(f"  → {len(reddit_topics)} topics from Reddit")

    all_topics = rss_topics + gt_topics + reddit_topics
    print(f"\nTotal raw topics: {len(all_topics)}")

    # ── Dedup ──
    seen = set()
    deduped = []
    for t in all_topics:
        key = re.sub(r'^(breaking|update|news|latest)[:\\s]+', '', t["title"].lower().strip(), flags=re.IGNORECASE).strip()
        if key not in seen and len(key) > 10:
            seen.add(key)
            deduped.append(t)
    print(f"After dedup: {len(deduped)}")

    # ── Score ──
    source_topics = {
        "rss": [t["title"] for t in rss_topics],
        "google_trends": [t["title"] for t in gt_topics],
        "reddit": [t["title"] for t in reddit_topics],
    }

    scored = []
    for t in deduped:
        score, breakdown = score_editorial(t["title"], source_topics)
        scored.append({**t, "score": score, "breakdown": breakdown})

    scored.sort(key=lambda x: x["score"], reverse=True)

    # ── Load history, check cooldown ──
    history = load_topics_history()
    last_alert_time = None
    if history.get("last_alert"):
        try:
            last_alert_time = datetime.fromisoformat(history["last_alert"])
        except Exception:
            pass

    cooldown_passed = True
    if last_alert_time:
        elapsed = (now - last_alert_time).total_seconds() / 3600
        if elapsed < 3:  # 3-hour cooldown between alerts
            cooldown_passed = False
            print(f"\n  Cooldown active: {elapsed:.1f}h since last alert (need 3h)")

    # ── Find best topic ──
    produce_topics = [t for t in scored if t["score"] >= 18]
    consider_topics = [t for t in scored if 14 <= t["score"] < 18]

    print(f"\nPRODUCE topics (>=18): {len(produce_topics)}")
    print(f"CONSIDER topics (14-17): {len(consider_topics)}")

    # Show top 5
    print("\nScore | Topic")
    print("-" * 60)
    for t in scored[:5]:
        marker = "🟢" if t["score"] >= 18 else ("🟡" if t["score"] >= 14 else "🔴")
        print(f"  {marker} [{t['score']:2d}] {t['title'][:60]}")

    # ── Alert logic ──
    alert_topic = None
    if produce_topics and cooldown_passed:
        alert_topic = produce_topics[0]
        print(f"\n🟢 PRODUCE: {alert_topic['title'][:70]}")
    elif consider_topics and cooldown_passed:
        # Only alert on CONSIDER if it's AP/Telangana specific
        ap_topics = [t for t in consider_topics if any(term in t["title"].lower() for term in AP_TE_TERMS)]
        if ap_topics:
            alert_topic = ap_topics[0]
            print(f"\n🟡 CONSIDER: {alert_topic['title'][:70]}")

    if alert_topic:
        score = alert_topic["score"]
        title = alert_topic["title"]
        source = alert_topic["source"]
        breakdown = " | ".join(alert_topic.get("breakdown", []))

        rec = "🟢 PRODUCE — Open laptop and tell Hermes: build" if score >= 18 else "🟡 CONSIDER — AP/Telangana relevant"

        alert_text = (
            f"🎬 <b>ViralDNA — Topic Alert</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 {now_str}\n"
            f"📊 Editorial Score: <b>{score}/30</b>\n"
            f"{rec}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📰 <b>{title[:100]}</b>\n"
            f"📡 Source: {source}\n"
            f"🔍 {breakdown}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💻 Open laptop → Tell Hermes: <b>build</b>\n"
            f"❌ Not interested? Ignore this alert.\n"
            f"⏰ Next check in 30 min."
        )

        sent = send_telegram(alert_text)
        print(f"\nTelegram alert sent: {sent}")

        if sent:
            history["last_alert"] = now.isoformat()
            # Keep last 50 topics
            history["topics"] = scored[:50]
            save_topics_history(history)
    else:
        print("\nNo alert sent (cooldown or no good topics)")

    # Always save topics for reference
    history["topics"] = scored[:50]
    history["last_run"] = now.isoformat()
    save_topics_history(history)

    print(f"\nDone. Next run in 30 min.")


if __name__ == "__main__":
    main()
