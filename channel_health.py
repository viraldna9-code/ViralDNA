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
Auto-fixes what it can, reports what needs manual action.

Runs every 2 during active hours (6AM-11PM IST).
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(PROJECT_ROOT, "credentials", "youtube_token.json")
HEALTH_FILE = os.path.join(PROJECT_ROOT, "analytics", "health_state.json")
FEEDBACK_FILE = os.path.join(PROJECT_ROOT, "analytics", "feedback.md")
ACTION_LOG = os.path.join(PROJECT_ROOT, "analytics", "actions_taken.json")
CHANNEL_ID = "UCkW7fqkJiaej2PeNcP4PejQ"
ALERT_COOLDOWN_FILE = os.path.join(PROJECT_ROOT, "analytics", "last_alert.txt")

MONETIZATION_SUBS = 1000
MONETIZATION_WATCH_HOURS = 4000
ACTIVE_START = 6
ACTIVE_END = 23


def load_credentials():
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


def yt_delete(token, url):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token
    }, method="DELETE")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return True, resp.status
    except urllib.error.HTTPError as e:
        return False, e.code


def parse_duration(iso_dur):
    if not iso_dur:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_dur)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def get_channel_data(token):
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
    """Get all videos with full stats. Retries on empty results."""
    all_ids = []
    import time
    for attempt in range(3):
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
        if all_ids:
            break
        time.sleep(2)
        print(f"  Retry {attempt+1}: video search returned 0")

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
            })
    return videos


def get_playlists(token):
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
            })
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break
    return playlists


def load_health_state():
    if os.path.exists(HEALTH_FILE):
        with open(HEALTH_FILE) as f:
            return json.load(f)
    return {"checks": [], "issues": [], "last_check": None}


def save_health_state(state):
    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)
    with open(HEALTH_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_action_log():
    if os.path.exists(ACTION_LOG):
        with open(ACTION_LOG) as f:
            return json.load(f)
    return {"auto_fixed": [], "manual_needed": [], "last_updated": None}


def save_action_log(log):
    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)
    log["last_updated"] = datetime.now(IST).isoformat()
    with open(ACTION_LOG, "w") as f:
        json.dump(log, f, indent=2)


def can_send_alert():
    if not os.path.exists(ALERT_COOLDOWN_FILE):
        return True
    try:
        last = open(ALERT_COOLDOWN_FILE).read().strip()
        last_dt = datetime.fromisoformat(last)
        return (datetime.now(timezone.utc) - last_dt).total_seconds() > 14400
    except Exception:
        return True


def mark_alert_sent():
    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)
    with open(ALERT_COOLDOWN_FILE, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())


def auto_fix(token, channel_data, videos, playlists):
    """
    Automatically fix what we can via API.
    Returns list of fix descriptions and list of manual-action items.
    """
    auto_fixed = []
    manual_needed = []

    # 1. Delete empty playlists
    empty_playlists = [p for p in playlists if p["item_count"] == 0]
    for p in empty_playlists:
        ok, code = yt_delete(token, f"https://www.googleapis.com/youtube/v3/playlists?id={p['id']}")
        if ok:
            auto_fixed.append(f"Deleted empty playlist: {p['title']}")
        else:
            manual_needed.append(f"Delete empty playlist: {p['title']} (API error {code})")

    # 2. Channel topics — CANNOT be set via API (read-only)
    topics = channel_data.get("topics", {})
    if not topics.get("topicIds") and not topics.get("topicCategories"):
        manual_needed.append("Set channel topics in YouTube Studio: News, Entertainment, Education (API cannot set this)")

    # 3. Check for non-news-category videos and fix them
    for v in videos:
        if v["privacy"] == "public" and v.get("category_id") != "25":
            # Update to News & Politics (25)
            body = json.dumps({
                "id": v["id"],
                "snippet": {
                    "categoryId": "25",
                    "title": v["title"],
                }
            }).encode()
            req = urllib.request.Request(
                "https://www.googleapis.com/youtube/v3/videos?part=snippet",
                data=body,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                method="PUT"
            )
            try:
                urllib.request.urlopen(req, timeout=10)
                auto_fixed.append(f"Set category to News (25): {v['title'][:40]}")
            except Exception as e:
                manual_needed.append(f"Set category to News (25): {v['title'][:40]} (error: {e})")

    return auto_fixed, manual_needed


def detect_issues(channel_data, videos, playlists, health_state):
    issues = []
    stats = channel_data.get("stats", {})
    channel_status = channel_data.get("status", {})

    total_views = int(stats.get("viewCount", 0))
    subscribers = int(stats.get("subscriberCount", 0))
    total_videos = len(videos)
    shorts = [v for v in videos if v["is_short"]]
    mains = [v for v in videos if not v["is_short"]]
    public_videos = [v for v in videos if v["privacy"] == "public"]
    now = datetime.now(IST)

    # 1. CHANNEL CONFIG
    if not channel_status.get("isChannelMonetizationEnabled", False):
        issues.append(("INFO", "monetization",
            f"Monetization NOT enabled ({subscribers}/{MONETIZATION_SUBS} subs)",
            f"Need {MONETIZATION_SUBS - subscribers} more subscribers"))

    topics = channel_data.get("topics", {})
    if not topics.get("topicIds") and not topics.get("topicCategories"):
        issues.append(("HIGH", "seo",
            "No channel topics set — reduces discoverability",
            "Set channel topics in YouTube Studio: Entertainment, News, Education"))

    empty_playlists = [p for p in playlists if p["item_count"] == 0]
    if empty_playlists:
        issues.append(("MEDIUM", "organization",
            f"{len(empty_playlists)} empty playlist(s): {', '.join(p['title'] for p in empty_playlists[:3])}",
            "Delete empty playlists — they hurt channel SEO"))

    # 2. CONTENT VOLUME
    if total_videos < 5:
        issues.append(("HIGH", "content",
            f"Only {total_videos} videos published. YouTube rewards consistency.",
            "Target: 1 main + 2 shorts daily"))

    if len(shorts) == 0 and total_videos > 0:
        issues.append(("HIGH", "content",
            "NO shorts published. Shorts are the fastest growth lever.",
            "Publish at least 2 shorts per day"))
    elif len(shorts) < 4 and total_videos >= 3:
        issues.append(("MEDIUM", "content",
            f"Only {len(shorts)} short(s). Recommend 2/day minimum.",
            "Increase short output"))

    recent = [v for v in videos if v["published"] >= (now - timedelta(days=1)).strftime("%Y-%m-%d")]
    if not recent and total_videos > 0:
        issues.append(("HIGH", "consistency",
            "NO new video in last 24 hours",
            "Publish at least 1 video today"))

    # 3. VIDEO PERFORMANCE
    if shorts and mains:
        avg_s = sum(v["views"] for v in shorts) / len(shorts)
        avg_m = sum(v["views"] for v in mains) / len(mains)
        if avg_s > avg_m * 2:
            issues.append(("INFO", "performance",
                f"Shorts outperforming mains ({avg_s:.0f} vs {avg_m:.0f} avg views)",
                "Double down on shorts"))
        elif avg_m > avg_s * 2:
            issues.append(("INFO", "performance",
                f"Mains outperforming shorts ({avg_m:.0f} vs {avg_s:.0f} avg views)",
                "Keep the 1+2 balance"))

    zero_views = [v for v in public_videos if v["views"] == 0]
    if zero_views:
        issues.append(("HIGH", "seo",
            f"{len(zero_views)} public video(s) with ZERO views",
            "Check titles, thumbnails, descriptions"))

    for v in public_videos[:10]:
        if v["views"] >= 50:
            like_rate = v["likes"] / v["views"] * 100
            if like_rate < 1:
                issues.append(("MEDIUM", "engagement",
                    f"Low like rate ({like_rate:.1f}%) on '{v['title'][:40]}'",
                    "Improve thumbnails and titles"))

    # 4. SEO
    no_tags = [v for v in public_videos if not v["tags"]]
    if no_tags:
        issues.append(("MEDIUM", "seo",
            f"{len(no_tags)} public video(s) have NO tags",
            "Add 10-15 relevant tags per video"))

    short_desc = [v for v in public_videos if len(v["description"]) < 100]
    if short_desc:
        issues.append(("LOW", "seo",
            f"{len(short_desc)} video(s) with short descriptions (<100 chars)",
            "Descriptions should be 200+ chars with keywords"))

    # 5. GROWTH RATE
    checks = health_state.get("checks", [])
    if checks:
        last = checks[-1]
        last_views = last.get("total_views", total_views)
        last_subs = last.get("subscribers", subscribers)
        hours_since = 2
        if "timestamp" in last:
            try:
                last_t = datetime.fromisoformat(last["timestamp"])
                hours_since = max(0.5, (now - last_t).total_seconds() / 3600)
            except Exception:
                pass

        view_growth = total_views - last_views
        sub_growth = subscribers - last_subs

        if view_growth == 0 and total_views > 0:
            issues.append(("MEDIUM", "growth",
                f"ZERO view growth in last {hours_since:.0f}h",
                "Check if latest video is getting impressions"))
        elif view_growth > 0:
            daily = view_growth / hours_since * 24
            issues.append(("INFO", "growth",
                f"Growing: ~{daily:.0f} views/day — GOOD",
                "Current trajectory is positive. Consistency matters."))

        if sub_growth > 0:
            issues.append(("INFO", "growth",
                f"+{sub_growth} new subscriber(s) since last check!",
                "Sub growth detected. Keep cadence."))

    # 6. MONETIZATION
    sub_pct = min(100, subscribers / MONETIZATION_SUBS * 100)
    if subscribers < MONETIZATION_SUBS:
        remaining = MONETIZATION_SUBS - subscribers
        issues.append(("INFO", "monetization",
            f"Monetization: {subscribers}/{MONETIZATION_SUBS} subs ({sub_pct:.1f}%). Need {remaining} more.",
            "Sub milestone is the main blocker"))

    return issues


def update_feedback_file(issues, channel_data, videos, auto_fixed, manual_needed):
    stats = channel_data.get("stats", {})
    subscribers = int(stats.get("subscriberCount", 0))
    total_views = int(stats.get("viewCount", 0))
    total_videos = len(videos)
    shorts = [v for v in videos if v["is_short"]]
    now = datetime.now(IST)

    critical = [i for i in issues if i[0] == "CRITICAL"]
    high = [i for i in issues if i[0] == "HIGH"]
    medium = [i for i in issues if i[0] == "MEDIUM"]
    low = [i for i in issues if i[0] == "LOW"]
    info = [i for i in issues if i[0] == "INFO"]

    f = f"# ViralDNA Channel Health Report\n"
    f += f"### Last updated: {now.strftime('%A, %B %d %Y — %H:%M IST')}\n\n"
    f += f"## Channel: The Viral DNA\n"
    f += f"- **Views:** {total_views:,} | **Subscribers:** {subscribers} | **Videos:** {total_videos} ({len(shorts)} shorts)\n"
    f += f"- **Monetization:** {subscribers}/{MONETIZATION_SUBS} subs ({min(100, subscribers/MONETIZATION_SUBS*100):.1f}%)\n\n"

    if auto_fixed:
        f += "## AUTO-FIXED THIS CHECK\n"
        for item in auto_fixed:
            f += f"- [FIXED] {item}\n"
        f += "\n"

    # Show manual needed from action log (cumulative)
    action_log = load_action_log()
    all_manual = action_log.get("manual_needed", [])
    # Filter out items that might have been auto-fixed just now
    # Keep items that are still relevant
    still_manual = []
    for item in all_manual:
        # Check if any auto-fixed item addresses this
        addressed = False
        for fix in auto_fixed:
            if item.lower()[:30] in fix.lower() or fix.lower()[:30] in item.lower():
                addressed = True
                break
        if not addressed:
            still_manual.append(item)

    if still_manual:
        f += "## MANUAL ACTION NEEDED\n"
        for i, item in enumerate(still_manual, 1):
            f += f"{i}. {item}\n"
        f += "\n"

    if critical:
        f += "## 🔴 CRITICAL (Act Immediately)\n"
        for sev, cat, msg, action in critical:
            f += f"- **[{cat.upper()}]** {msg}\n  -> {action}\n"

    if high:
        f += "\n## 🟠 HIGH PRIORITY (Fix Today)\n"
        for sev, cat, msg, action in high:
            f += f"- **[{cat.upper()}]** {msg}\n  -> {action}\n"

    if medium:
        f += "\n## 🟡 MEDIUM (This Week)\n"
        for sev, cat, msg, action in medium:
            f += f"- **[{cat.upper()}]** {msg}\n  -> {action}\n"

    if low:
        f += "\n## 🔵 LOW (Nice to Have)\n"
        for sev, cat, msg, action in low:
            f += f"- **[{cat.upper()}]** {msg}\n  -> {action}\n"

    if info:
        f += "\n## ℹ️ INFO\n"
        for sev, cat, msg, action in info:
            f += f"- **[{cat.upper()}]** {msg}\n"

    f += f"\n---\n*Next check: ~2h | Hermes auto-fixes what it can | Reply 'fixed [#]' after manual actions*\n"

    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)
    with open(FEEDBACK_FILE, "w") as fh:
        fh.write(f)

    return f


def format_telegram_alert(issues, auto_fixed, manual_needed, channel_data):
    stats = channel_data.get("stats", {})
    subscribers = int(stats.get("subscriberCount", 0))
    total_views = int(stats.get("viewCount", 0))
    now = datetime.now(IST)

    alert = f"The ViralDNA — Channel Health\n"
    alert += f"{now.strftime('%d %b, %H:%M IST')}\n"
    alert += f"Views: {total_views:,} | Subs: {subscribers}\n\n"

    if auto_fixed:
        alert += "AUTO-FIXED:\n"
        for item in auto_fixed:
            alert += f"  FIXED: {item}\n"
        alert += "\n"

    # Collect unaddressed manual items
    action_log = load_action_log()
    all_manual = action_log.get("manual_needed", [])
    if all_manual:
        alert += "MANUAL ACTION NEEDED:\n"
        for i, item in enumerate(all_manual, 1):
            alert += f"  {i}. {item}\n"
        alert += "\n"

    critical = [i for i in issues if i[0] in ("CRITICAL", "HIGH")]
    medium = [i for i in issues if i[0] == "MEDIUM"]

    if critical:
        alert += "URGENT:\n"
        for sev, cat, msg, action in critical[:3]:
            alert += f"  [{cat.upper()}] {msg}\n"
            alert += f"    DO: {action}\n"

    if medium:
        alert += "\nTHIS WEEK:\n"
        for sev, cat, msg, action in medium[:2]:
            alert += f"  [{cat.upper()}] {msg}\n"

    good_info = [i for i in issues if i[0] == "INFO" and "outperforming" in i[2].lower() or "growing" in i[2].lower()]
    if good_info:
        alert += "\nGOOD:\n"
        for sev, cat, msg, action in good_info[:2]:
            alert += f"  {msg}\n"

    if not critical and not medium and not all_manual:
        alert += "  All clear. Channel healthy.\n"

    alert += "\nCheck feedback.md for full report."
    alert += "\nReply 'fixed [#]' after doing manual tasks."

    return alert


def send_telegram(message):
    env = {}
    try:
        with open(os.path.expanduser("~/.env")) as fh:
            for line in fh:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({
        "chat_id": chat_id, "text": message,
        "parse_mode": "HTML", "disable_web_page_preview": True
    }).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}),
            timeout=15)
        return True
    except Exception:
        return False


def main():
    now = datetime.now(IST)
    hour = now.hour

    if hour < ACTIVE_START or hour >= ACTIVE_END:
        print(f"[{now.strftime('%H:%M IST')}] Outside active hours, skipping.")
        return

    print(f"[{now.strftime('%H:%M IST')}] ViralDNA Channel Health Check...")
    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)

    try:
        token = load_credentials()
    except Exception as e:
        print(f"  Token error: {e}")
        return

    try:
        channel_data = get_channel_data(token)
        videos = get_all_videos(token)
        playlists = get_playlists(token)
    except Exception as e:
        print(f"  API error: {e}")
        return

    stats = channel_data.get("stats", {})
    print(f"  Channel: {stats.get('viewCount', 0)} views, {stats.get('subscriberCount', 0)} subs, {len(videos)} videos")

    # AUTO-FIX what we can
    auto_fixed, manual_needed = auto_fix(token, channel_data, videos, playlists)
    for fix in auto_fixed:
        print(f"  AUTO-FIXED: {fix}")
    for m in manual_needed:
        print(f"  MANUAL: {m}")

    # Re-fetch playlists after fixes (they may have been deleted)
    if auto_fixed:
        try:
            playlists = get_playlists(token)
        except Exception:
            pass

    health_state = load_health_state()
    issues = detect_issues(channel_data, videos, playlists, health_state)
    print(f"  Issues: {len(issues)} ({sum(1 for i in issues if i[0] in ('CRITICAL','HIGH'))} urgent)")

    # Merge new manual needs with existing action log
    action_log = load_action_log()
    existing = set(action_log.get("manual_needed", []))
    for m in manual_needed:
        if m not in existing:
            action_log.setdefault("manual_needed", []).append(m)
    # Remove resolved items (if issue no longer detected)
    # Keep items that haven't been explicitly marked fixed
    save_action_log(action_log)

    update_feedback_file(issues, channel_data, videos, auto_fixed, manual_needed)
    print(f"  Updated {FEEDBACK_FILE}")

    health_state["checks"].append({
        "timestamp": now.isoformat(),
        "total_views": int(stats.get("viewCount", 0)),
        "subscribers": int(stats.get("subscriberCount", 0)),
        "video_count": len(videos),
        "shorts_count": sum(1 for v in videos if v["is_short"]),
        "issues_count": len(issues),
        "critical_count": sum(1 for i in issues if i[0] in ("CRITICAL", "HIGH")),
        "auto_fixed": auto_fixed,
    })
    health_state["checks"] = health_state["checks"][-100:]
    save_health_state(health_state)

    alert = format_telegram_alert(issues, auto_fixed, manual_needed, channel_data)
    if alert and (can_send_alert() or auto_fixed):
        sent = send_telegram(alert)
        if sent:
            mark_alert_sent()
            print(f"  Telegram sent!")
        else:
            print(f"  Telegram FAILED")
    else:
        print(f"  No alert needed (cooldown or nothing new)")

    print("  Done.")


if __name__ == "__main__":
    main()
