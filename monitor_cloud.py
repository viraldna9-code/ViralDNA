#!/usr/bin/env python3
"""
ViralDNA Spike Monitor — GitHub Actions Edition
================================================
Runs every 30 min on GitHub Actions (cloud).
Polls RSS + Google Trends + Reddit, scores topics editorially.
Sends Telegram alert if a topic scores >= 20/30 (truly viral).
Saves best topics to topics.json (persisted in repo via git push).

Credentials: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID from GitHub Secrets (or .env for local).
"""

import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

# Load .env for local/WSL runs (GitHub Actions sets env vars directly)
try:
    from dotenv import load_dotenv
    _env_loaded = False
    for _candidate in (
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(os.path.expanduser("~"), ".env"),
        ".env",
    ):
        if os.path.isfile(_candidate):
            load_dotenv(_candidate, override=False)
            _env_loaded = True
            break
except ImportError:
    pass

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

# ── Calendar of known high-traffic events for Telugu audience ──
# Format: (MM, DD, "event_name", bonus_points)
# These are dates when search volume SPIKES for Telugu people
CALENDAR_EVENTS = [
    # National events
    (1, 26, "republic day", 8),
    (8, 15, "independence day", 8),
    (10, 2, "gandhi jayanti", 5),
    # Telugu state events
    (6, 2, "telangana formation day", 10),   # HUGE for our audience
    (11, 1, "andhra pradesh formation day", 10),  # HUGE for our audience
    # Major festivals (approximate — covers the week)
    (1, 14, "sankranti", 8),
    (3, 22, "ugadi", 8),
    (10, 2, "dasara", 6),
    (11, 12, "deepavali", 6),
    (10, 6, "bathukamma", 7),
    # Exam/result seasons (broad windows)
    (3, 1, "exam results season", 5),   # March-April
    (4, 1, "exam results season", 5),
    (5, 1, "exam results season", 5),
    (6, 1, "exam results season", 5),
    (7, 1, "exam results season", 5),
    # Budget season
    (2, 1, "union budget", 6),
    # Election seasons (update year-to-year)
    (4, 1, "election season", 7),
    (5, 1, "election season", 7),
]

# Keywords that indicate a calendar event is being discussed
# MUST be specific — generic words like "result" or "election" cause false positives
CALENDAR_KEYWORDS = {
    "telangana formation day": ["formation day", "telangana day", "statehood day", "telangana rashtra", "12th anniversary telangana"],
    "andhra pradesh formation day": ["andhra formation", "andhra day", "andhra pradesh formation"],
    "sankranti": ["sankranti", "pongal", "makara sankranti"],
    "ugadi": ["ugadi", "telugu new year", "yugadi"],
    "dasara": ["dasara", "dussehra", "vijayadashami"],
    "deepavali": ["deepavali", "diwali"],
    "bathukamma": ["bathukamma"],
    "republic day": ["republic day", "republicday", "26 january"],
    "independence day": ["independence day", "15 august", "august 15"],
    "union budget": ["union budget", "finance minister budget", "budget 2026", "income tax budget"],
    "exam results season": ["ssc results", "inter results", "btech results", "exam results declared", "results declared", "toss results"],
    "election season": ["election results", "voting today", "polling day", "election 2026", "campaign rally"],
}

# Celebrity/political names that drive engagement (Telugu audience)
# Matched as whole words only using word boundary regex
BIG_NAMES = [
    "pawan kalyan", "jr ntr", "balakrishna",
    "mahesh babu", "prabhas", "allu arjun", "ram charan",
    "chiranjeevi", "nagarjuna", "venkatesh", "ravi teja",
    "jagan", "chandrababu", "kcr", "revanth",
    "cm revanth", "devara", "salaar", "pushpa", "rrr", "bahubali",
    "anirudh", "koratala", "ss rajamouli", "trivikram",
    "vijay sethupathi", "suriya", "ajith",
    "modi", "rahul gandhi", "sonia gandhi", "amit shah", "yogi",
    "arvind kejriwal", "mamata banerjee",
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


def score_editorial(title, source_topics, topic_date=None, reddit_velocity=0):
    """Score a topic for channel growth potential (0-30).

    Channel-growth-focused scoring:
    - Freshness matters most: today's breaking news beats 3-day-old news
    - Local AP/TS stories can score high WITHOUT big names
    - Calendar events (Formation Day, festivals) get big bonuses
    - Viral velocity (Reddit, Google Trends) signals real-time demand
    - Big names still help but don't dominate (+6 not +10)
    - Cross-source confirms real news importance

    Args:
        title: Topic title string
        source_topics: Dict of {source_name: [titles]} for cross-source check
        topic_date: Date string YYYYMMDD or None (freshness bonus)
        reddit_velocity: Number of Reddit posts mentioning this topic (0+)
    """
    t = title.lower()
    score = 0
    breakdown = []
    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")
    month = now.month
    day = now.day

    # ── 1. FRESHNESS / AGE (max +7) — the #1 growth signal ──
    # Today's news gets full bonus, yesterday gets half, 2+ days ago gets penalty
    freshness_score = 0
    if topic_date:
        try:
            topic_dt = datetime.strptime(topic_date, "%Y%m%d").replace(tzinfo=IST)
            age_hours = (now - topic_dt).total_seconds() / 3600
            if age_hours < 3:
                freshness_score = 7      # Breaking: <3 hours old
                breakdown.append("Fresh(BREAKING) +7")
            elif age_hours < 12:
                freshness_score = 5      # Today: <12 hours old
                breakdown.append("Fresh(TODAY) +5")
            elif age_hours < 24:
                freshness_score = 3      # Yesterday
                breakdown.append("Fresh(Y'DAY) +3")
            elif age_hours < 48:
                freshness_score = 1      # 2 days ago — barely relevant
                breakdown.append("Fresh(2d) +1")
            else:
                freshness_score = -3     # 3+ days old — stale, penalize
                breakdown.append(f"Stale({int(age_hours/24)}d) -3")
        except Exception:
            pass
    else:
        # No date info = assume recent (RSS feeds are usually today)
        freshness_score = 3
        breakdown.append("Fresh(assume) +3")

    score += freshness_score

    # ── 2. CALENDAR EVENT BONUS (max +10) — today's special events ──
    # Check if today matches a known high-traffic calendar date
    calendar_bonus = 0
    calendar_name = ""
    for (evt_month, evt_day, evt_name, evt_bonus) in CALENDAR_EVENTS:
        if month == evt_month and abs(day - evt_day) <= 2:  # ±2 day window
            # Check if title mentions THIS specific event's keywords
            # Use the event name to look up relevant keywords
            matched = False
            for ck, keywords in CALENDAR_KEYWORDS.items():
                # Only check keywords for events that are actually in window
                if ck in evt_name or evt_name in ck:
                    for kw in keywords:
                        if kw.lower() in t:
                            matched = True
                            break
                if matched:
                    break
            if matched and evt_bonus > calendar_bonus:
                calendar_bonus = evt_bonus
                calendar_name = evt_name

    if calendar_bonus > 0:
        score += calendar_bonus
        breakdown.append(f"Calendar({calendar_name}) +{calendar_bonus}")

    # ── 3. BIG NAMES (+6) — celebrity/political, reduced from +10 ──
    # Still valuable but shouldn't dominate local stories
    name_matches = []
    for n in BIG_NAMES:
        pattern = r'\b' + re.escape(n) + r'\b'
        if re.search(pattern, t):
            name_matches.append(n)
    if name_matches:
        score += 6
        breakdown.append("BIG_NAME +6 (" + name_matches[0] + ")")

    # ── 4. AP/TELANGANA DIRECT RELEVANCE (+6) — our home turf ──
    ap_te_pattern = '|'.join(re.escape(term) for term in sorted(AP_TE_TERMS, key=len, reverse=True))
    if re.search(rf'\b(?:{ap_te_pattern})\b', t):
        score += 6
        breakdown.append("AP/TS +6")

    # ── 5. INDIA NATIONAL RELEVANCE (+4) — affects Telugu people ──
    india_matches = [n for n in INDIA_RELEVANT if re.search(rf'\b{re.escape(n)}\b', t)]
    if india_matches:
        score += 4
        breakdown.append("IndiaRel +4 (" + india_matches[0] + ")")

    # ── 6. CHANNEL GROWTH TOPICS (+3) — always-strong interest areas ──
    if any(re.search(rf'\b{re.escape(term)}\b', t) for term in CHANNEL_GROWTH_TOPICS):
        score += 3
        breakdown.append("ChannelGrowth +3")

    # ── 7. VIRAL KEYWORD BONUS (max +5) — clickbait signals ──
    kw_score = 0
    matched_kws = []
    for kw, pts in VIRAL_KEYWORDS.items():
        if re.search(r'\b' + re.escape(kw) + r'\b', t):
            kw_score += pts
            matched_kws.append(kw)
    if kw_score > 0:
        kw_score = min(kw_score, 5)
        score += kw_score
        breakdown.append(f"ViralKW +{kw_score} ({matched_kws[0]})")

    # ── 8. VELOCITY / VIRAL SIGNAL (max +4) — Reddit/Twitter buzz ──
    # High Reddit activity = real-time audience interest
    if reddit_velocity >= 5:
        score += 4
        breakdown.append(f"Velocity(HOT) +4 (reddit:{reddit_velocity})")
    elif reddit_velocity >= 3:
        score += 2
        breakdown.append(f"Velocity(WARM) +2 (reddit:{reddit_velocity})")

    # ── 9. CROSS-SOURCE CONFIRMATION (max +4) ──
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

    # ── 10. TITLE QUALITY (+2) — SEO-friendly headline length ──
    if 40 <= len(title) <= 80:
        score += 2
        breakdown.append("TitleLen +2")

    return min(score, 30), max(score, 0), breakdown


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
    return {"topics": [], "last_alert": None, "pending_review": []}


def save_topics_history(history):
    """Save topics history."""
    os.makedirs(TOPICS_DIR, exist_ok=True)
    with open(TOPICS_FILE, "w") as f:
        json.dump(history, f, indent=2)


def update_pending_review(history, produce_topics, now_str):
    """Add all >=20 topics to pending_review list.
    Deduplicates by ID. Marks whether alert was sent or blocked by cooldown."""
    pending = history.get("pending_review", [])
    existing_ids = {p["id"] for p in pending}
    for t in produce_topics:
        if t["id"] not in existing_ids:
            pending.append({
                "id": t["id"],
                "title": t["title"][:80],
                "score": t["score"],
                "source": t["source"],
                "date": now_str,
                "alert_sent": False,
            })
            existing_ids.add(t["id"])
    # Mark topics that were just alerted as sent
    alerted_ids = {t["id"] for t in produce_topics}
    for p in pending:
        if p["id"] in alerted_ids:
            p["alert_sent"] = True
    # Keep last 20 pending topics
    history["pending_review"] = pending[-20:]


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
        key = re.sub(r'^(breaking|update|news|latest)[:\s]+', '', t["title"].lower().strip(), flags=re.IGNORECASE).strip()
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
    # Build Reddit velocity map: count how many Reddit posts mention each topic
    reddit_velocity_map = {}
    for rt in reddit_topics:
        rt_title = rt["title"].lower()
        for t in deduped:
            tl = t["title"].lower()
            if tl in rt_title or rt_title in tl or tl == rt_title:
                key = t["title"]
                reddit_velocity_map[key] = reddit_velocity_map.get(key, 0) + 1

    date_prefix = now.strftime("%Y%m%d")
    for t in deduped:
        vel = reddit_velocity_map.get(t["title"], 0)
        score, raw_score, breakdown = score_editorial(
            t["title"], source_topics,
            topic_date=date_prefix,
            reddit_velocity=vel
        )
        scored.append({**t, "score": score, "breakdown": breakdown})

    # ── Edge scoring: break ties with growth intelligence ──
    # Each topic gets a decimal edge (0.1-0.9) based on:
    #   search demand, velocity, channel fit, competition gap,
    #   engagement potential, geographic breadth, feedback analytics
    try:
        from modules.edge_scorer import batch_score_topics
        scored = batch_score_topics(scored)
        # Use final_score (base + edge) for sorting; keep base 'score' for display
        scored.sort(key=lambda x: x.get("final_score", x.get("score", 0)), reverse=True)
        print(f"  → Edge scoring applied: {len(scored)} topics scored with growth intelligence")
    except Exception as e:
        print(f"  → Edge scoring failed (falling back to base sort): {e}")
        scored.sort(key=lambda x: x["score"], reverse=True)

    # ── Assign persistent VDNA topic IDs ──
    # Load existing topics to preserve IDs
    existing_topics = load_topics_history()
    existing_map = {}
    for t in existing_topics.get("topics", []):
        if "id" in t:
            # Map by normalized title for matching
            key = re.sub(r'^(breaking|update|news|latest)[:\s]+', '', t.get("title","").lower().strip(), flags=re.IGNORECASE).strip()
            existing_map[key] = t["id"]

    # Find next available ID number
    max_id_num = 0
    for t in existing_topics.get("topics", []):
        tid = t.get("id","")
        if tid.startswith("VDNA"):
            try:
                num = int(tid[4:])
                if num > max_id_num:
                    max_id_num = num
            except ValueError:
                pass

    # Assign IDs: reuse existing for same topic, new ID for new topics
    date_prefix = now.strftime("%Y%m%d")
    for t in scored:
        key = re.sub(r'^(breaking|update|news|latest)[:\s]+', '', t["title"].lower().strip(), flags=re.IGNORECASE).strip()
        if key in existing_map:
            t["id"] = existing_map[key]
        else:
            max_id_num += 1
            t["id"] = f"VDNA{max_id_num:03d}"
        t["date"] = date_prefix

    # ── Load history, check cooldown + daily cap ──
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
        if elapsed < 4:  # 4-hour cooldown between alerts
            cooldown_passed = False
            print(f"\n  Cooldown active: {elapsed:.1f}h since last alert (need 4h)")

    # Max 3 spike alerts per day (prioritized by score)
    daily_alert_count = history.get("daily_alert_count", 0)
    daily_alert_date = history.get("daily_alert_date", "")
    today_str = now.strftime("%Y-%m-%d")
    if daily_alert_date != today_str:
        daily_alert_count = 0  # reset on new day
        daily_alert_date = today_str
        history["daily_alert_count"] = 0
        history["daily_alert_date"] = today_str
    max_daily_alerts = 3
    daily_cap_ok = daily_alert_count < max_daily_alerts
    if not daily_cap_ok:
        print(f"\n  Daily cap reached: {daily_alert_count}/{max_daily_alerts} alerts today")

    # ── Find best topics ──
    # Threshold >= 20: need multiple strong signals (e.g. big name + AP/TS + viral keyword)
    # Typical scores: routine news = 0-9, interesting = 10-19, truly viral = 20-30
    produce_topics = [t for t in scored if t["score"] >= 20]

    print("\nPRODUCER topics (>=20): " + str(len(produce_topics)))
    print("\nScore  | Edge | Final | Topic")
    print("-" * 80)
    for t in scored[:5]:
        marker = "PRODUCE" if t["score"] >= 20 else "low"
        edge = t.get("edge_score", 0)
        final = t.get("final_score", t["score"])
        print(f"  [{marker}] [{t['score']:>2}] +{edge:.1f} = {final:.1f}  {t['title'][:55]}")

    # ── Alert logic: alert on ALL produce topics (up to daily cap) ──
    # Each alert consumes 1 daily cap slot. Max 3 alerts/day.
    if produce_topics and cooldown_passed and daily_cap_ok:
        alerts_sent = 0
        max_alerts = min(len(produce_topics), max_daily_alerts - daily_alert_count)
        for alert_topic in produce_topics[:max_alerts]:
            score = alert_topic["score"]
            edge = alert_topic.get("edge_score", 0)
            final = alert_topic.get("final_score", score)
            title = alert_topic["title"]
            source = alert_topic["source"]
            topic_id = alert_topic.get("id", "VDNA???")
            breakdown = " | ".join(alert_topic.get("breakdown", []))

            alert_text = (
                f"🎬 <b>ViralDNA — Topic Alert</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 {now_str}\n"
                f"🆔 Topic ID: <b>{topic_id}</b>\n"
                f"📊 Score: <b>{score}/30</b> + edge {edge:.1f} = <b>{final:.1f}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📰 <b>{title[:100]}</b>\n"
                f"📡 {source}\n"
                f"🔍 {breakdown}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💻 Open laptop → Hermes chat → type:\n"
                f"   <b>{topic_id} Post</b>\n"
                f"❌ Not interested? Ignore.\n"
                f"⏰ Next check in 30 min."
            )

            sent = send_telegram(alert_text)
            if sent:
                alerts_sent += 1
                print(f"\n✅ Alert sent: {topic_id} ({title[:50]})")
            else:
                print(f"\n❌ Alert failed: {topic_id} ({title[:50]})")

        if alerts_sent > 0:
            history["last_alert"] = now.isoformat()
            history["daily_alert_count"] = daily_alert_count + alerts_sent
            history["daily_alert_date"] = daily_alert_date
            print(f"\nTotal alerts sent this run: {alerts_sent}")
    else:
        if not cooldown_passed:
            print("\nNo alert sent: cooldown active")
        elif not daily_cap_ok:
            print("\nNo alert sent: daily cap reached")
        elif not produce_topics:
            print("\nNo alert sent: no topics >= 20")

    # ── Update pending review list ──
    if produce_topics:
        update_pending_review(history, produce_topics, now_str)
        pending_count = len(history.get("pending_review", []))
        print(f"\n📋 Pending review list: {pending_count} topic(s)")

    # ── Merge topics into history (persistent) ──
    # Build map of existing topics by normalized title
    existing_map = {}
    for t in existing_topics.get("topics", []):
        if "id" in t and t.get("title"):
            k = re.sub(r'^(breaking|update|news|latest)[:\s]+', '', t["title"].lower().strip(), flags=re.IGNORECASE).strip()
            existing_map[k] = t

    # Merge: update existing scores, add new topics
    for t in scored:
        k = re.sub(r'^(breaking|update|news|latest)[:\s]+', '', t["title"].lower().strip(), flags=re.IGNORECASE).strip()
        if k in existing_map:
            existing_map[k]["score"] = t["score"]
            existing_map[k]["date"] = t.get("date", "")
            existing_map[k]["breakdown"] = t.get("breakdown", [])
            # Always recompute score_breakdown on each scoring run
            existing_map[k]["score_breakdown"] = t.get("breakdown", [])
            existing_map[k]["rescored_at"] = t.get("date", "")
            # Persist edge scoring (tie-breaking intelligence)
            if "edge_score" in t:
                existing_map[k]["edge_score"] = t["edge_score"]
                existing_map[k]["final_score"] = t["final_score"]
                existing_map[k]["edge_breakdown"] = t.get("edge_breakdown", {})
            if "id" in t:
                existing_map[k]["id"] = t["id"]
        else:
            existing_map[k] = t

    # Sort by final_score (base + edge), keep top 50
    all_topics = sorted(existing_map.values(), key=lambda x: x.get("final_score", x.get("score", 0)), reverse=True)[:50]
    history["topics"] = all_topics
    history["last_run"] = now.isoformat()
    save_topics_history(history)

    print(f"\nDone. Next run in 30 min.")


if __name__ == "__main__":
    main()
