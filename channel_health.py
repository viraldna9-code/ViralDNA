#!/usr/bin/env python3
"""
ViralDNA Channel Health Monitor
===============================
Continuous monitoring of YouTube channel health.
Checks: metrics growth, video performance, content gaps,
SEO issues, monetization progress, competitor signals,
channel configuration issues.

Only alerts when something ACTIONABLE changes.
Maintains an analytics/feedback.md living document.

Runs every 2 during active hours (6AM-11PM IST).
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(PROJECT_ROOT, "credentials", "youtube_token.json")
HEALTH_FILE = os.path.join(PROJECT_ROOT, "analytics", "health_state.json")
FEEDBACK_FILE = os.path.join(PROJECT_ROOT, "analytics", "feedback.md")
CHANNEL_ID = "UCkW7fqkJiaej2PeNcP4PejQ"
ALERT_COOLDOWN_FILE = os.path.join(PROJECT_ROOT, "analytics", "last_alert.txt")

# Monetization thresholds
MONETIZATION_SUBS = 1000
MONETIZATION_WATCH_HOURS = 4000
MONETIZATION_SHORTS_VIEWS_90D = 10_000_000

# Active hours (IST)
ACTIVE_START = 6   # 6 AM
ACTIVE_END = 23    # 11 PM


def load_credentials():
    """Load and refresh YouTube OAuth token."""
    with open(CREDENTIALS_FILE) as f:
        creds = json.load(f)
    token = creds.get("token", "")
    expiry_str = creds.get("expiry", "")
    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) >= expiry - timedelta(minutes=5):
                token = refresh_token(creds)
                creds["token"] = token
                with open(CREDENTIALS_FILE, "w") as f:
                    json.dump(creds, f)
        except Exception:
            pass
    return token


def refresh_token(creds):
    import urllib.parse
    data = urllib.parse.urlencode({
        "client_id": creds["client_id"], "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"], "grant_type": "refresh_token"
    }).encode()
    req = urllib.request.Request(creds["token_uri"], data=data)
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["access_token"]


def yt_get(token, url):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token, "Accept": "application/json"
    })
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def parse_duration(iso_dur):
    if not iso_dur:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_dur)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def get_channel_data(token):
    """Get comprehensive channel data."""
    # Channel stats + branding + status
    url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics,brandingSettings,status,topicDetails,contentDetails&id={CHANNEL_ID}"
    data = yt_get(token, url)
    if not data.get("items"):
        return {}
    item = data["items"][0]

    return {
        "stats": item.get("statistics", {}),
        "branding": item.get("brandingSettings", {}).get("channel", {}),
        "status": item.get("status", {}),
        "topics": item.get("topicDetails", {}),
        "playlists_id": item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", ""),
    }


def get_all_videos(token):
    """Get all videos with full stats."""
    # First, search for all video IDs
    all_ids = []
    page_token = ""
    while True:
        url = f"https://www.googleapis.com/youtube/v3/search?part=id&channelId={CHANNEL_ID}&maxResults=50&order=date&type=video"
        if page_token:
            url += f"&pageToken={page_token}"
        data = yt_get(token, url)
        for item in data.get("items", []):
            if item["id"].get("kind") == "youtube#video":
                all_ids.append(item["id"]["videoId"])
        page_token = data.get("nextPageToken", "")
        if not page_token or not data.get("items"):
            break

    # Then get full details in batches
    videos = []
    for i in range(0, len(all_ids), 50):
        batch = all_ids[i:i + 50]
        url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,contentDetails,snippet,status&id={','.join(batch)}"
        data = yt_get(token, url)
        for v in data.get("items", []):
            s = v.get("statistics", {})
            sn = v.get("snippet", {})
            cd = v.get("contentDetails", {})
            st = v.get("status", {})
            dur_secs = parse_duration(cd.get("duration", ""))
            videos.append({
                "id": v["id"],
                "title": sn.get("title", ""),
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
                "duration_secs": dur_secs,
                "is_short": 0 < dur_secs <= 60,
                "privacy": st.get("privacyStatus", ""),
                "published": sn.get("publishedAt", "")[:10],
                "tags": sn.get("tags", []),
                "description": sn.get("description", ""),
                "category_id": sn.get("categoryId", ""),
                "default_language": sn.get("defaultLanguage", ""),
                "made_for_kids": st.get("madeForKids", False),
            })
    return videos


def get_playlists(token):
    """Get all channel playlists."""
    playlists = []
    page_token = ""
    while True:
        url = f"https://www.googleapis.com/youtube/v3/playlists?part=snippet,contentDetails&channelId={CHANNEL_ID}&maxResults=50"
        if page_token:
            url += f"&pageToken={page_token}"
        data = yt_get(token, url)
        for p in data.get("items", []):
            playlists.append({
                "id": p["id"],
                "title": p["snippet"]["title"],
                "item_count": p["contentDetails"].get("itemCount", 0),
                "privacy": p["status"].get("privacyStatus", "") if "status" in p else "",
            })
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break
    return playlists


def load_health_state():
    if os.path.exists(HEALTH_FILE):
        with open(HEALTH_FILE) as f:
            return json.load(f)
    return {"checks": [], "issues": [], "last_check": None, "video_count_at_last": 0}


def save_health_state(state):
    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)
    with open(HEALTH_FILE, "w") as f:
        json.dump(state, f, indent=2)


def can_send_alert():
    """Check cooldown: max 1 alert per 4 hours unless critical."""
    if not os.path.exists(ALERT_COOLDOWN_FILE):
        return True
    try:
        last = open(ALERT_COOLDOWN_FILE).read().strip()
        last_dt = datetime.fromisoformat(last)
        return (datetime.now(timezone.utc) - last_dt).total_seconds() > 14400  # 4h
    except Exception:
        return True


def mark_alert_sent(critical=False):
    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)
    with open(ALERT_COOLDOWN_FILE, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())


def detect_issues(channel_data, videos, playlists, health_state):
    """
    Core analysis engine. Detect actionable issues and opportunities.
    Returns list of (severity, category, message, action) tuples.
    Severity: CRITICAL, HIGH, MEDIUM, LOW, INFO
    """
    issues = []
    stats = channel_data.get("stats", {})
    branding = channel_data.get("branding", {})
    channel_status = channel_data.get("status", {})

    total_views = int(stats.get("viewCount", 0))
    subscribers = int(stats.get("subscriberCount", 0))
    api_video_count = int(stats.get("videoCount", 0))
    now = datetime.now(IST)
    total_videos = len(videos)
    shorts = [v for v in videos if v["is_short"]]
    mains = [v for v in videos if not v["is_short"]]
    public_videos = [v for v in videos if v["privacy"] == "public"]

    # ── 1. CHANNEL CONFIGURATION ──────────────────────────────

    # Monetization not enabled
    if not channel_status.get("isChannelMonetizationEnabled", False):
        issues.append(("INFO", "monetization",
            f"Monetization NOT enabled ({subscribers}/{MONETIZATION_SUBS} subs)",
            f"Need {MONETIZATION_SUBS - subscribers} more subscribers to apply"))

    # No channel topics set
    topics = channel_data.get("topics", {})
    if not topics.get("topicIds") and not topics.get("topicCategories"):
        issues.append(("HIGH", "seo",
            "No channel topics set — reduces discoverability",
            "Set channel topics in YouTube Studio: Entertainment, News, Education"))

    # Empty playlists
    empty_playlists = [p for p in playlists if p["item_count"] == 0]
    if empty_playlists:
        issues.append(("MEDIUM", "organization",
            f"{len(empty_playlists)} empty playlist(s): {', '.join(p['title'] for p in empty_playlists[:3])}",
            "Add videos to empty playlists or delete them — empty playlists hurt channel SEO"))

    # ── 2. CONTENT VOLUME & CONSISTENCY ────────────────────────

    # Very few videos
    if total_videos < 5:
        issues.append(("HIGH", "content",
            f"Only {total_videos} videos published. YouTube rewards consistency.",
            "Target: 1 main + 2 shorts daily. Need more content fast."))

    # No shorts
    if len(shorts) == 0 and total_videos > 0:
        issues.append(("HIGH", "content",
            "NO shorts published. Shorts are the fastest growth lever.",
            "Publish at least 2 shorts per day. They get 10-100x more views than long videos for small channels."))

    # Low short count
    elif len(shorts) < 4 and total_videos >= 3:
        issues.append(("MEDIUM", "content",
            f"Only {len(shorts)} short(s). Recommend 2 shorts/day minimum.",
            "Increase short output. Shorts drive subscriber growth for news channels."))

    # Content gap: no video in last 24 hours
    recent_videos = [v for v in videos if v["published"] >= (now - timedelta(days=1)).strftime("%Y-%m-%d")]
    if not recent_videos and total_videos > 0:
        issues.append(("HIGH", "consistency",
            "NO new video in the last 24 hours. YouTube penalizes inactive channels.",
            "Publish at least 1 video today. Consistency is the #1 growth signal."))

    # ── 3. VIDEO PERFORMANCE ANALYSIS ─────────────────────────

    # Best performing video type
    if shorts and mains:
        avg_short_views = sum(v["views"] for v in shorts) / len(shorts)
        avg_main_views = sum(v["views"] for v in mains) / len(mains)
        if avg_short_views > avg_main_views * 2:
            issues.append(("INFO", "performance",
                f"Shorts outperforming mains ({avg_short_views:.0f} vs {avg_main_views:.0f} avg views)",
                "Double down on shorts. They're your growth engine right now."))
        elif avg_main_views > avg_short_views * 2:
            issues.append(("INFO", "performance",
                f"Mains outperforming shorts ({avg_main_views:.0f} vs {avg_short_views:.0f} avg views)",
                "Main videos performing well. Keep the 1+2 balance."))

    # Zero-view videos
    zero_views = [v for v in public_videos if v["views"] == 0]
    if zero_views:
        issues.append(("HIGH", "seo",
            f"{len(zero_views)} public video(s) with ZERO views",
            "Check titles, thumbnails, and descriptions. These need SEO fixes."))

    # Low engagement rate
    for v in public_videos[:10]:
        if v["views"] >= 10:
            like_rate = v["likes"] / v["views"] * 100
            if like_rate < 1 and v["views"] > 50:
                issues.append(("MEDIUM", "engagement",
                    f"Low like rate ({like_rate:.1f}%) on '{v['title'][:40]}'",
                    "Improve thumbnails and titles. First 48 hours are critical."))

    # ── 4. SEO / METADATA ISSUES ──────────────────────────────

    # Videos without tags
    no_tags = [v for v in videos if not v["tags"] and v["privacy"] == "public"]
    if no_tags:
        issues.append(("MEDIUM", "seo",
            f"{len(no_tags)} public video(s) have NO tags",
            f"Add 10-15 relevant tags per video (telugu news, andhra pradesh, telangana, etc.)"))

    # Short descriptions
    short_desc = [v for v in public_videos if len(v["description"]) < 100]
    if short_desc:
        issues.append(("LOW", "seo",
            f"{len(short_desc)} video(s) with very short descriptions (<100 chars)",
            "Descriptions should be 200+ characters with keywords for SEO"))

    # Non-news category
    non_news = [v for v in public_videos if v.get("category_id") != "25"]
    if non_news:
        issues.append(("MEDIUM", "seo",
            f"{len(non_news)} video(s) not in News & Politics category (cat 25)",
            "Set all videos to category 25 (News & Politics)"))

    # ── 5. GROWTH RATE ────────────────────────────────────────

    prev = health_state.get("checks", [])
    if prev:
        last_check = prev[-1]
        last_views = last_check.get("total_views", total_views)
        last_subs = last_check.get("subscribers", subscribers)
        hours_since = 2  # approximate
        if prev and "timestamp" in last_check:
            try:
                last_t = datetime.fromisoformat(last_check["timestamp"])
                hours_since = max(0.5, (now - last_t).total_seconds() / 3600)
            except Exception:
                pass

        view_growth = total_views - last_views
        sub_growth = subscribers - last_subs

        if view_growth == 0 and total_views > 0:
            issues.append(("MEDIUM", "growth",
                f"ZERO view growth in last {hours_since:.0f} hours",
                "Check if latest video is getting impressions. May need SEO improvements."))
        elif view_growth > 0:
            daily_rate = view_growth / hours_since * 24
            if daily_rate < 10:
                issues.append(("LOW", "growth",
                    f"Slow growth: ~{daily_rate:.0f} views/day estimated",
                    "Experiment with trending topics and better thumbnails"))
            else:
                issues.append(("INFO", "growth",
                    f"Growing: ~{daily_rate:.0f} views/day estimated — GOOD",
                    "Current trajectory is positive. Consistency matters most now."))

        if sub_growth > 0:
            issues.append(("INFO", "growth",
                f"+{sub_growth} new subscriber(s) since last check!",
                "Sub growth detected. Keep the content cadence."))

    # ── 6. MONETIZATION TRACKING ──────────────────────────────
    sub_pct = min(100, subscribers / MONETIZATION_SUBS * 100)
    if subscribers < MONETIZATION_SUBS:
        remaining = MONETIZATION_SUBS - subscribers
        issues.append(("INFO", "monetization",
            f"Monetization: {subscribers}/{MONETIZATION_SUBS} subs ({sub_pct:.1f}%). Need {remaining} more.",
            f"At current rate: keep publishing. Sub milestone is the main blocker."))

    return issues


def update_feedback_file(issues, channel_data, videos):
    """Update analytics/feedback.md with living analysis."""
    stats = channel_data.get("stats", {})
    subscribers = int(stats.get("subscriberCount", 0))
    total_views = int(stats.get("viewCount", 0))
    total_videos = len(videos)
    shorts = [v for v in videos if v["is_short"]]
    now = datetime.now(IST)

    # Separate issues by severity
    critical = [i for i in issues if i[0] == "CRITICAL"]
    high = [i for i in issues if i[0] == "HIGH"]
    medium = [i for i in issues if i[0] == "MEDIUM"]
    low = [i for i in issues if i[0] == "LOW"]
    info = [i for i in issues if i[0] == "INFO"]

    feedback = f"""# ViralDNA Channel Health Report
### Last updated: {now.strftime('%A, %B %d %Y — %H:%M IST')}

## Channel: The Viral DNA
- **Views:** {total_views:,} | **Subscribers:** {subscribers} | **Videos:** {total_videos} ({len(shorts)} shorts)
- **Monetization:** {subscribers}/{MONETIZATION_SUBS} subs ({min(100, subscribers/MONETIZATION_SUBS*100):.1f}%)

"""

    if critical:
        feedback += "## 🔴 CRITICAL (Act Immediately)\n"
        for sev, cat, msg, action in critical:
            feedback += f"- **[{cat.upper()}]** {msg}\n  → {action}\n"

    if high:
        feedback += "\n## 🟠 HIGH PRIORITY (Fix Today)\n"
        for sev, cat, msg, action in high:
            feedback += f"- **[{cat.upper()}]** {msg}\n  → {action}\n"

    if medium:
        feedback += "\n## 🟡 MEDIUM (This Week)\n"
        for sev, cat, msg, action in medium:
            feedback += f"- **[{cat.upper()}]** {msg}\n  → {action}\n"

    if low:
        feedback += "\n## 🔵 LOW (Nice to Have)\n"
        for sev, cat, msg, action in low:
            feedback += f"- **[{cat.upper()}]** {msg}\n  → {action}\n"

    if info:
        feedback += "\n## ℹ️ INFO\n"
        for sev, cat, msg, action in info:
            feedback += f"- **[{cat.upper()}]** {msg}\n"

    feedback += f"\n---\n*Next check: ~2 hours* | *Feedback auto-updates* | *Hermes acts on HIGH+*\n"

    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)
    with open(FEEDBACK_FILE, "w") as f:
        f.write(feedback)

    return feedback


def format_alert(issues):
    """Format a Telegram alert with actionable items only."""
    critical = [i for i in issues if i[0] in ("CRITICAL", "HIGH")]
    medium = [i for i in issues if i[0] == "MEDIUM"]

    if not critical and not medium:
        return None

    now = datetime.now(IST)
    alert = f"⚠️ The ViralDNA — Need to Act\n"
    alert += f"🕐 {now.strftime('%d %b, %H:%M IST')}\n\n"

    if critical:
        alert += "🔴 URGENT:\n"
        for sev, cat, msg, action in critical[:3]:
            alert += f"  • {msg}\n"
            alert += f"    → {action}\n"

    if medium:
        alert += "\n🟡 ATTENTION:\n"
        for sev, cat, msg, action in medium[:3]:
            alert += f"  • {msg}\n"
            alert += f"    → {action}\n"

    alert += f"\n📄 Full report: analytics/feedback.md"
    return alert


def send_telegram(message):
    """Send alert via Telegram API."""
    # Load creds from ~/.env
    env = {}
    try:
        with open(os.path.expanduser("~/.env")) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass

    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("  Telegram creds missing, skipping send")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({
        "chat_id": chat_id, "text": message,
        "parse_mode": "HTML", "disable_web_page_preview": True
    }).encode()
    urllib.request.urlopen(
        urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}),
        timeout=15
    )
    return True


def main():
    now = datetime.now(IST)
    hour = now.hour

    # Only run during active hours (6AM-11PM IST)
    if hour < ACTIVE_START or hour >= ACTIVE_END:
        print(f"[{now.strftime('%H:%M IST')}] Outside active hours ({ACTIVE_START}-{ACTIVE_END}), skipping.")
        return # Still a success, just not time yet

    print(f"[{now.strftime('%H:%M IST')}] ViralDNA Channel Health Check...")
    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)

    # Load token
    try:
        token = load_credentials()
    except Exception as e:
        print(f"  Token error: {e}")
        return

    # Gather data
    try:
        channel_data = get_channel_data(token)
        videos = get_all_videos(token)
        playlists = get_playlists(token)
    except Exception as e:
        print(f"  API error: {e}")
        return

    stats = channel_data.get("stats", {})
    print(f"  Channel: {stats.get('viewCount', 0)} views, {stats.get('subscriberCount', 0)} subs, {len(videos)} videos")

    # Load previous state
    health_state = load_health_state()

    # Run analysis
    issues = detect_issues(channel_data, videos, playlists, health_state)
    print(f"  Issues found: {len(issues)} ({sum(1 for i in issues if i[0] in ('CRITICAL','HIGH'))} urgent)")

    # Update feedback file (always)
    update_feedback_file(issues, channel_data, videos)
    print(f"  Updated {FEEDBACK_FILE}")

    # Save state for next comparison
    health_state["checks"].append({
        "timestamp": now.isoformat(),
        "total_views": int(stats.get("viewCount", 0)),
        "subscribers": int(stats.get("subscriberCount", 0)),
        "video_count": len(videos),
        "shorts_count": sum(1 for v in videos if v["is_short"]),
        "issues_count": len(issues),
        "critical_count": sum(1 for i in issues if i[0] in ("CRITICAL", "HIGH")),
    })
    # Keep last 100 checks
    health_state["checks"] = health_state["checks"][-100:]
    health_state["last_check"] = now.isoformat()
    health_state["video_count_at_last"] = len(videos)
    save_health_state(health_state)

    # Send Telegram alert if issues found (with cooldown)
    alert_msg = format_alert(issues)
    if alert_msg and can_send_alert():
        sent = send_telegram(alert_msg)
        if sent:
            mark_alert_sent()
            print(f"  Telegram alert sent!")
        else:
            print(f"  Telegram alert failed to send")
    elif alert_msg:
        print(f"  Alert suppressed (4h cooldown active)")
    else:
        print(f"  No urgent issues — channel healthy")

    print("  Done.")


if __name__ == "__main__":
    main()
