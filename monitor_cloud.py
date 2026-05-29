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
    "corruption": 3, "scandal": 4, "viral": 3,
}

# Celebrity/political names that drive engagement (Telugu audience)
BIG_NAMES = [
    "pawan kalyan", "kalyan", "ntr", "jr ntr", "balakrishna",
    "mahesh babu", "prabhas", "allu arjun", "ram charan",
    "chiranjeevi", "nagarjuna", "venkatesh", "ravi teja",
    "jagan", "chandrababu", "nara", "kcr", "revanth",
    "cm revanth", "bmpi", "tdp", "ysrcp", "tollywood",
    "devara", "salaar", "pushpa", "rrr", "bahubali",
    "anirudh", "koratala", "ss rajamouli", "trivikram",
    "diven", "vijay sethupathi", "suriya", "ajith",
    "modi", "rahum", "gandhi", "sonia",
]

# India national news that affects Telugu people
INDIA_RELEVANT = [
    "petrol", "diesel", "fuel", "price", "inflation", "tax", "gst", "income tax",
    "exam", "result", "ssc", "upsc", "neet", "jee", "gate", "cat",
    "job", "recruitment", "vacancy", "railway", "bank", "government job",
    "visa", "passport", "immigration", "h1b", "us visa", "green card",
    "gold", "silver", "sensex", "nifty", "stock", "market",
    "budget", "rbi", "interest rate", "loan", "emi",
    "weather", "cyclone", "flood", "rain", "drought", "heat wave",
    "cricket", "ipl", "world cup", "match", "cric",
    "hospital", "health", "covid", "vaccine", "medicine",
    "farmers", "crop", "mandi", "fertilizer", "pension",
    "bank holiday", "strike", "bandh", "bundh",
    "bjp", "congress", "aap", "election", "vote", "poll",
    "supreme court", "high court", "judge", "verdict",
]

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
    """Score a topic for channel growth potential (0-30).
    
    New scoring: ANY India news is relevant to Telugu people.
    Celebrity/political names get highest scores.
    """
    t = title.lower()
    score = 0
    breakdown = []

    # 1. Big names bonus — celebrity/political (+10)
    name_matches = [n for n in BIG_NAMES if n in t]
    if name_matches:
        score += 10
        breakdown.append("BIG_NAME +10 (" + name_matches[0] + ")")

    # 2. AP/Telangana direct relevance (+6) — bonus on top of name
    if any(term in t for term in AP_TE_TERMS):
        score += 6
        breakdown.append("AP/TS +6")

    # 3. India national relevance — affects Telugu people (+4)
    india_matches = [n for n in INDIA_RELEVANT if n in t]
    if india_matches:
        score += 4
        breakdown.append("IndiaRel +4 (" + india_matches[0] + ")")

    # 4. Channel growth topics (+3) — festivals, immigration, etc.
    if any(term in t for term in CHANNEL_GROWTH_TOPICS):
        score += 3
        breakdown.append("ChannelGrowth +3")

    # 5. Viral keyword bonus (max +5)
    kw_score = 0
    for kw, pts in VIRAL_KEYWORDS.items():
        if kw in t:
            kw_score += pts
    if kw_score > 0:
        kw_score = min(kw_score, 5)
        score += kw_score
        breakdown.append("ViralKW +" + str(kw_score))

    # 6. Cross-source bonus (max +4)
    src_count = sum(1 for topics in source_topics.values() if any(
        title.lower() == tl.lower() or title.lower() in tl.lower() or tl.lower() in title.lower()
        for tl in topics
    ))
    if src_count >= 3:
        score += 4
        breakdown.append("CrossSrc(3+) +4")
    elif src_count >= 2:
        score += 2
        breakdown.append("CrossSrc(2) +2")

    # 7. Title length sweet spot (+2) — 40-80 chars = good headline
    if 40 <= len(title) <= 80:
        score += 2
        breakdown.append("TitleLen +2")

    return min(score, 30), breakdown


def poll_rss():
    """Poll RSS feeds for trending topics."""
    feeds = [
        ("The Hindu", "https://www.thehindu.com/news/national/?service=rss"),
        ("The Hindu AP/TS", "https://www.thehindu.com/news/cities/Hyderabad/?service=rss"),
        ("TOI", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"),
        ("Google News IN", "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"),
        ("Google News Telugu", "https://news.google.com/rss/search?q=telugu+news&hl=te&gl=IN&ceid=IN:te"),
        ("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories"),
        ("Indian Express", "https://indianexpress.com/feed/"),
        ("Sakshi", "https://www.sakshi.com/rss/feed"),
        ("Eenadu", "https://www.eenadu.net/rss/feed"),
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
    produce_topics = [t for t in scored if t["score"] >= 10]
    consider_topics = [t for t in scored if 7 <= t["score"] < 10]

    print("\nPRODUCE topics (>=10): " + str(len(produce_topics)))
    print("CONSIDER topics (7-9): " + str(len(consider_topics)))

    # Show top 5
    print("\nScore | Topic")
    print("-" * 60)
    for t in scored[:5]:
        marker = "PRODUCE" if t["score"] >= 10 else ("CONSIDER" if t["score"] >= 7 else "low")
        print("  [" + marker + "] [" + str(t['score']).zfill(2) + "] " + t['title'][:60])

    # Alert logic
    alert_topic = None
    if produce_topics and cooldown_passed:
        alert_topic = produce_topics[0]
        print("\nPRODUCE: " + alert_topic['title'][:70])
    elif consider_topics and cooldown_passed:
        alert_topic = consider_topics[0]
        print("\nCONSIDER: " + alert_topic['title'][:70])

    if alert_topic:
        score = alert_topic["score"]
        title = alert_topic["title"]
        source = alert_topic["source"]
        breakdown = " | ".join(alert_topic.get("breakdown", []))

        rec = "PRODUCE — Open laptop and tell Hermes: build" if score >= 10 else "CONSIDER — worth covering"

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
