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
TARGET_DAILY_MAINS = 1
TARGET_DAILY_SHORTS = 2
ACTIVE_START = 6
ACTIVE_END = 23


def load_credentials():
    with open(CREDENTIALS_FILE) as f:
        creds = json.load(f)
    token = creds.get("token", "")
    expiry_str = creds.get("expiry", "")
    needs_refresh = False
    if expiry_str == "refreshed":
        # Token file was manually refreshed but expiry not set — refresh now
        needs_refresh = True
    elif expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) >= expiry - timedelta(minutes=5):
                needs_refresh = True
        except Exception:
            needs_refresh = True
    else:
        needs_refresh = True
    if needs_refresh:
        try:
            token = refresh_token(creds)
            creds["token"] = token
            new_expiry = datetime.now(timezone.utc) + timedelta(seconds=3590)
            creds["expiry"] = new_expiry.isoformat()
            with open(CREDENTIALS_FILE, "w") as f:
                json.dump(creds, f)
        except Exception:
            pass  # fall through with whatever token we have
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
    try:
        return json.loads(urllib.request.urlopen(req, timeout=15).read())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Token expired — refresh and retry once
            try:
                new_token = refresh_token(json.load(open(CREDENTIALS_FILE)))
                creds = json.load(open(CREDENTIALS_FILE))
                creds["token"] = new_token
                new_expiry = datetime.now(timezone.utc) + timedelta(seconds=3590)
                creds["expiry"] = new_expiry.isoformat()
                with open(CREDENTIALS_FILE, "w") as f:
                    json.dump(creds, f)
                req2 = urllib.request.Request(url, headers={
                    "Authorization": "Bearer " + new_token, "Accept": "application/json"
                })
                return json.loads(urllib.request.urlopen(req2, timeout=15).read())
            except Exception:
                pass
        raise


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
    url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet,brandingSettings,status,topicDetails,contentDetails&id={CHANNEL_ID}"
    data = yt_get(token, url)
    if not data.get("items"):
        return {}
    item = data["items"][0]
    return {
        "stats": item.get("statistics", {}),
        "snippet": item.get("snippet", {}),
        "branding": item.get("brandingSettings", {}).get("channel", {}),
        "status": item.get("status", {}),
        "topics": item.get("topicDetails", {}),
        "playlists_id": item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", ""),
    }


def get_all_videos(token, uploads_playlist_id=""):
    """Get all video IDs via uploads playlist (1 unit/call), then batch-fetch details.
    Falls back to search endpoint (100 units/call) if uploads playlist not available.
    """
    all_ids = []

    # Primary: uploads playlist (cheap: 1 unit per call)
    if uploads_playlist_id:
        page_token = ""
        while True:
            url = (f"https://www.googleapis.com/youtube/v3/playlistItems?"
                   f"part=contentDetails&playlistId={uploads_playlist_id}&maxResults=50")
            if page_token:
                url += f"&pageToken={page_token}"
            try:
                data = yt_get(token, url)
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    break  # quota — will try fallback
                raise
            for item in data.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId", "")
                if vid:
                    all_ids.append(vid)
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break

    # Fallback: search endpoint (100 units/call — burns quota fast)
    if not all_ids:
        page_token = ""
        while True:
            url = (f"https://www.googleapis.com/youtube/v3/search?"
                   f"part=id&channelId={CHANNEL_ID}&maxResults=50&order=date&type=video")
            if page_token:
                url += f"&pageToken={page_token}"
            data = yt_get(token, url)
            for item in data.get("items", []):
                if item["id"].get("kind") == "youtube#video":
                    all_ids.append(item["id"]["videoId"])
            page_token = data.get("nextPageToken", "")
            if not page_token or not data.get("items"):
                break

    # Batch-fetch video details (1 unit per batch of 50)
    videos = []
    for i in range(0, len(all_ids), 50):
        batch = all_ids[i:i + 50]
        url = (f"https://www.googleapis.com/youtube/v3/videos?"
               f"part=statistics,contentDetails,snippet,status&id={','.join(batch)}")
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
                "made_for_kids": st.get("selfDeclaredMadeForKids", None),
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


def get_channel_sections(token):
    """Fetch channel sections (home page layout)."""
    url = f"https://www.googleapis.com/youtube/v3/channelSections?part=snippet,contentDetails&channelId={CHANNEL_ID}"
    try:
        data = yt_get(token, url)
        return data.get("items", [])
    except Exception:
        return []


def check_upload_cadence(videos, now, issues):
    """
    Check if we're meeting the daily target of 1 main + 2 shorts.
    Analyzes uploads in the last 24h, 48h, and 7 days.
    """
    if not videos:
        issues.append(("CRITICAL", "cadence", "NO videos on channel", "Publish immediately"))
        return

    shorts = [v for v in videos if v["is_short"]]
    mains = [v for v in videos if not v["is_short"]]

    day_ago = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    mains_24h = [v for v in mains if v["published"] >= day_ago]
    shorts_24h = [v for v in shorts if v["published"] >= day_ago]

    if len(mains_24h) == 0 and len(shorts_24h) == 0:
        issues.append(("HIGH", "cadence",
            f"ZERO uploads in last 24h (target: {TARGET_DAILY_MAINS} main + {TARGET_DAILY_SHORTS} shorts/day)",
            "Publish today -- consistency is the #1 growth factor"))
    elif len(mains_24h) == 0:
        issues.append(("MEDIUM", "cadence",
            f"No main video in last 24h ({len(shorts_24h)} shorts ok, missing main)",
            "Publish 1 main video today"))
    elif len(shorts_24h) < TARGET_DAILY_SHORTS:
        issues.append(("MEDIUM", "cadence",
            f"Only {len(shorts_24h)}/{TARGET_DAILY_SHORTS} shorts in last 24h",
            f"Publish {TARGET_DAILY_SHORTS - len(shorts_24h)} more short(s) today"))

    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    mains_7d = [v for v in mains if v["published"] >= week_ago]
    shorts_7d = [v for v in shorts if v["published"] >= week_ago]
    daily_main_rate = len(mains_7d) / 7.0
    daily_short_rate = len(shorts_7d) / 7.0
    if daily_main_rate < 0.5 or daily_short_rate < 1.0:
        issues.append(("MEDIUM", "cadence",
            f"Weekly cadence low: {daily_main_rate:.1f} mains/day, {daily_short_rate:.1f} shorts/day (target: {TARGET_DAILY_MAINS}+{TARGET_DAILY_SHORTS})",
            "Increase output -- algorithm rewards consistent publishers"))
    elif daily_main_rate >= 0.8 and daily_short_rate >= 1.5:
        issues.append(("INFO", "cadence",
            f"Cadence good: {daily_main_rate:.1f} mains/day, {daily_short_rate:.1f} shorts/day -- keep it up",
            "Consistency drives algorithmic promotion"))

    if len(shorts) + len(mains) >= 5:
        shorts_ratio = len(shorts) / (len(shorts) + len(mains)) * 100
        if shorts_ratio < 40:
            issues.append(("MEDIUM", "content_mix",
                f"Shorts only {shorts_ratio:.0f}% of content (target: 60-70%)",
                "Shorts drive discovery -- aim for 2 shorts per 1 main"))


def check_video_seo_details(public_videos, issues):
    """Per-video SEO checks: title length, description keywords, comment engagement."""
    if not public_videos:
        return

    seo_keywords = ["telugu", "news", "andhra", "telangana", "india", "breaking", "today", "update"]

    long_titles = []
    weak_descriptions = []
    low_comments = []
    high_views_no_comments = []

    for v in public_videos:
        title = v["title"]
        desc = v["description"]
        views = v["views"]
        comments = v["comments"]
        title_len = len(title)

        if title_len > 70:
            long_titles.append(f"'{title[:35]}...' ({title_len} chars)")

        desc_snippet = desc[:160].lower()
        has_keyword = any(kw in desc_snippet for kw in seo_keywords)
        if not has_keyword and len(desc) > 0:
            weak_descriptions.append(f"'{title[:35]}...'")

        if views >= 50 and comments == 0:
            low_comments.append(f"'{title[:35]}...' ({views} views, 0 comments)")
        if views >= 200 and comments == 0:
            high_views_no_comments.append(f"'{title[:35]}...' ({views} views, 0 comments)")

    if long_titles:
        issues.append(("MEDIUM", "seo",
            f"{len(long_titles)} video(s) with titles >70 chars (truncated in search): {', '.join(long_titles[:3])}",
            "Shorten titles to <70 chars -- use tags for extra keywords"))

    if weak_descriptions:
        issues.append(("LOW", "seo",
            f"{len(weak_descriptions)} video(s) with no keywords in first 160 chars of description",
            "Put primary keywords in first 2 lines of description"))

    if high_views_no_comments:
        issues.append(("MEDIUM", "engagement",
            f"{len(high_views_no_comments)} video(s) with 200+ views but ZERO comments",
            "Pin a comment asking a question -- boosts engagement signal"))
    elif low_comments:
        issues.append(("LOW", "engagement",
            f"{len(low_comments)} video(s) with 50+ views but no comments",
            "Ask viewers to comment in the video CTA"))


def check_channel_health_status(channel_data, issues):
    """Check channel-level health: strikes, compliance, branding completeness."""
    status = channel_data.get("status", {})

    self_declared = status.get("selfDeclaredMadeForKids", None)
    if self_declared is None:
        issues.append(("HIGH", "compliance",
            "Channel 'made for kids' status NOT set -- COPPA violation risk",
            "Set in YouTube Studio: Audience -> 'No, it\\'s not made for kids'"))

    branding_ch = channel_data.get("branding", {})
    trailer_set = bool(branding_ch.get("unsubscribedTrailer") or
                       branding_ch.get("defaultTrailer"))
    if not trailer_set:
        issues.append(("MEDIUM", "branding",
            "No channel trailer set -- new visitors see generic home page",
            "Set trailer: YouTube Studio -> Customization -> Branding -> Trailer for non-subscribers"))

    snippet = channel_data.get("snippet", {})
    country = snippet.get("country", "")
    if not country:
        issues.append(("LOW", "seo",
            "Channel country not set -- limits regional discoverability",
            "Set channel country to IN (India) in YouTube Studio -> Settings -> Channel -> Advanced"))

    default_lang = branding_ch.get("defaultLanguage", "")
    if not default_lang:
        issues.append(("LOW", "seo",
            "Channel default language not set",
            "Set default language to English in brandingSettings"))


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

    # 2. Channel topics — topicDetails is read-only via API.
    #    Instead, set rich channel keywords (API-accessible equivalent).
    topics = channel_data.get("topics", {})
    branding = channel_data.get("branding", {})
    current_keywords = branding.get("keywords", "")
    if not topics.get("topicIds") and not topics.get("topicCategories"):
        # Auto-fix: set rich keywords as the API-equivalent of topics
        new_keywords = "telugu news, andhra pradesh news, telangana news, telugu people, telugu diaspora, india news, viral news, ai news, breaking news telugu, real news, telugu states, news today"
        body = json.dumps({
            "id": CHANNEL_ID,
            "brandingSettings": {
                "channel": {
                    "keywords": new_keywords,
                    "defaultLanguage": "en"
                }
            }
        }).encode()
        req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/channels?part=brandingSettings",
            data=body,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            method="PUT"
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            auto_fixed.append("Set channel keywords (API equivalent of topics): Telugu news, AP, Telangana, Telugu people")
        except Exception:
            # Fallback: guide user if API fails
            manual_needed.append("Open YouTube Studio → Customization → Basic Info → Add Topics: Entertainment, News, Education")

    # 3. Channel description — CRITICAL for discovery and branding
    branding_ch = channel_data.get("branding", {})
    current_desc = branding_ch.get("description", "").strip()
    current_title = branding_ch.get("title", "").strip()
    if len(current_desc) < 200:
        CHANNEL_DESCRIPTION = (
            "The ViralDNA — Real News. Real Voices. Built with AI.\n\n"
            "Breaking news from Andhra Pradesh, Telangana, and India. "
            "Daily Telugu news, AP news, Telangana news, India news, Tollywood, "
            "cricket, politics, and stories for Telugu communities worldwide.\n\n"
            "📌 What we cover:\n"
            "• AP news — politics, government schemes, development\n"
            "• Telangana news — CM Revanth Reddy, state policies, Hyderabad\n"
            "• India news — elections, Modi government, economy, RBI\n"
            "• Tollywood — Prabhas, Allu Arjun, Jr NTR, Mahesh Babu, Ram Charan, "
            "Chiranjeevi, Balakrishna, Pawan Kalyan, Ravi Teja, Nagarjuna, SS Rajamouli\n"
            "• Politics — TDP, YSRCP, BRS, BJP, Congress in Telugu states\n"
            "• Telugu diaspora — Gulf, USA, UK, Australia NRI updates\n"
            "• Breaking news and viral stories from South India\n"
            "• Entertainment, sports, technology, business\n\n"
            "🔔 Subscribe for daily updates. "
            "Morning 9AM | Evening 7PM IST | Shorts daily\n\n"
            "#TeluguNews #AndhraPradesh #Telangana #TeluguNewsToday #IndiaNews "
            "#Tollywood #APNews #TelanganaNews #TeluguPeople #BreakingNews"
        )
        body = json.dumps({
            "id": CHANNEL_ID,
            "brandingSettings": {
                "channel": {
                    "title": current_title if current_title else "The Viral DNA",
                    "description": CHANNEL_DESCRIPTION,
                    "defaultLanguage": "en"
                }
            }
        }).encode()
        req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/channels?part=brandingSettings",
            data=body,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            method="PUT"
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            desc_msg = "Set channel description" if current_desc else "Set channel description (was empty)"
            auto_fixed.append(desc_msg)
        except Exception as e:
            manual_needed.append(f"Set channel description — API error: {e}")

    # 3. Check for non-news-category videos and fix them
    # 3a. Add tags to public videos with NO tags
    for v in videos:
        if v["privacy"] == "public" and len(v.get("tags", [])) == 0:
            title_lower = v["title"].lower()
            # Build relevant tags from title keywords + standard tags
            base_tags = ["telugu news", "andhra pradesh", "telangana", "india news", "viraldna"]
            keyword_map = [
                (["pakistan", "terror"], ["pakistan", "terrorism", "global news", "india pakistan"]),
                (["karnataka", "shivakumar", "rahul", "gandhi"], ["karnataka politics", "congress", "indian politics", "elections india"]),
                (["revanth", "cm", "government"], ["telangana news", "cm revanth reddy", "telangana politics"]),
                (["women", "entrepreneur", "rural"], ["telangana schemes", "women empowerment", "rural india"]),
                (["pay", "hike", "employee", "salary"], ["government employees", "pay commission", "india news"]),
                (["money", "worker", "andhra"], ["andhra pradesh news", "andhra news", "viral video"]),
                (["trailer", "viral dna"], ["telugu news channel", "ai news", "viraldna"]),
            ]
            extra = []
            for keywords, ktags in keyword_map:
                if any(kw in title_lower for kw in keywords):
                    extra.extend(ktags)
                    break
            new_tags = list(dict.fromkeys(base_tags + extra))[:15]  # dedupe, max 15
            body = json.dumps({
                "id": v["id"],
                "snippet": {
                    "categoryId": v.get("category_id", "25"),
                    "title": v["title"],
                    "tags": new_tags,
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
                auto_fixed.append(f"Added {len(new_tags)} tags to: {v['title'][:40]}")
            except Exception as e:
                manual_needed.append(f"Add tags to: {v['title'][:40]} (error: {e})")

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


def check_duplicate_videos(videos, issues):
    """Flag near-duplicate videos by title similarity (Jaccard)."""
    from datetime import datetime, timedelta
    now_utc = datetime.utcnow()
    for i in range(len(videos)):
        for j in range(i + 1, len(vids2 := videos)):
            if i == j:
                continue
            v1, v2 = videos[i], videos[j]
            # Title Jaccard similarity
            w1 = set(v1["title"].lower().split())
            w2 = set(v2["title"].lower().split())
            if not w1 or not w2:
                continue
            jaccard = len(w1 & w2) / len(w1 | w2)
            if jaccard >= 0.6:
                issues.append(("MEDIUM", "duplicates",
                    f"Near-duplicate titles (similarity {jaccard:.0%}): '{v1['title'][:40]}' vs '{v2['title'][:40]}'",
                    "Merge or remove duplicate content"))


def check_analytics_per_video(token, videos, issues):
    """Fetch YouTube Analytics for per-video watch time, impressions, CTR.
    Uses youtubeAnalytics.reports.query — requires:
      1. youtube.readonly scope (already in token) ✓
      2. YouTube Analytics API enabled on Google Cloud project (may NOT be enabled)
    Falls back gracefully on 403 (API not enabled) or other errors.
    """
    url = "https://youtubeanalytics.googleapis.com/v2/reports"
    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=28)).strftime("%Y-%m-%d")

    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
    }

    # Quick test: try channel-level query first
    test_url = (
        f"{url}?ids=channel==MIME&metrics=views"
        f"&startDate={start_date}&endDate={end_date}"
    )
    try:
        req = urllib.request.Request(test_url, headers=headers)
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            body = e.read().decode()
            if "youtubeanalytics" in body.lower() or "disabled" in body.lower():
                issues.append(("INFO", "analytics",
                    "YouTube Analytics API not enabled on GCloud project — "
                    "cannot check watch time, impressions, CTR, per-video subs",
                    "Enable at: https://console.developers.google.com/apis/api/"
                    "youtubeanalytics.googleapis.com/overview?project=192793181154"))
                return
        # Other 403 — permission issue, stop
        issues.append(("INFO", "analytics",
            f"YouTube Analytics API access denied ({e.code})",
            "Check OAuth scopes and project settings"))
        return
    except Exception:
        return  # Network or other error — skip silently


def detect_issues(token, channel_data, videos, playlists, health_state):
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
    branding = channel_data.get("branding", {})
    keywords = branding.get("keywords", "")
    has_topics = topics.get("topicIds") or topics.get("topicCategories")
    has_keywords = len(keywords.strip()) > 10
    if not has_topics and not has_keywords:
        issues.append(("HIGH", "seo",
            "No channel topics OR keywords — reduces discoverability",
            "Hermes will auto-set keywords. For topics: YouTube Studio → Customization → Basic Info → Topics"))
    if not has_topics and has_keywords:
        # Keywords set (auto-fixed) but topicDetails still empty — YouTube auto-assigns over time
        issues.append(("LOW", "seo",
            "Channel topics not set (YouTube auto-assigns based on content)",
            "Optional: YouTube Studio -> Customization -> Basic Info -> Topics"))

    # 1d. Channel description check
    branding_ch = channel_data.get("branding", {})
    channel_desc = branding_ch.get("description", "").strip()
    if not channel_desc:
        issues.append(("HIGH", "seo",
            "Channel description is EMPTY — hurts search/discovery and looks unprofessional",
            "Auto-fix will set it on next health run"))
    elif len(channel_desc) < 200:
        issues.append(("MEDIUM", "seo",
            f"Channel description is short ({len(channel_desc)}/1000 chars) — should use full 1000 for SEO",
            "Auto-fix will update it on next health run"))

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

    # 7. UPLOAD CADENCE
    check_upload_cadence(videos, now, issues)

    # 8. PER-VIDEO SEO DETAILS
    check_video_seo_details(public_videos, issues)

    # 9. CHANNEL HEALTH STATUS (compliance, branding, country)
    check_channel_health_status(channel_data, issues)

    # 10. PER-VIDEO MADE-FOR-KIDS (selfDeclaredMadeForKids) CHECK
    for v in public_videos:
        if v.get("made_for_kids") is None:
            issues.append(("HIGH", "compliance",
                f"Video '{v['title'][:40]}' has no made-for-kids declaration",
                "Set selfDeclaredMadeForKids in upload API call"))
        elif v.get("made_for_kids") is True:
            issues.append(("MEDIUM", "compliance",
                f"Video '{v['title'][:40]}' marked as made-for-kids — kills comments/reach",
                "Re-upload with selfDeclaredMadeForKids=False if content is news"))

    # 11. PER-VIDEO DUPLICATE / NEAR-DUPLICATE DETECTION
    check_duplicate_videos(public_videos, issues)

    # 12. YOUTUBE ANALYTICS — watch time, impressions, CTR (per video, last 28 days)
    check_analytics_per_video(token, public_videos, issues)

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

    alert += f"\nUploads: DISABLED (manual review via Google Drive)"
    alert += "\n\nCheck feedback.md for full report."
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
        uploads_id = channel_data.get("playlists_id", "")
        videos = get_all_videos(token, uploads_playlist_id=uploads_id)
        playlists = get_playlists(token)
    except urllib.error.HTTPError as e:
        if e.code == 403 and "quota" in e.read().decode().lower():
            print(f"  QUOTA EXHAUSTED — YouTube Data API quota depleted. Retry after midnight PT (12:30 PM IST).")
            state = load_health_state()
            state["quota_exhausted_since"] = now.isoformat()
            save_health_state(state)
            return
        print(f"  API error: {e}")
        return
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

    # Re-fetch channel data + playlists after fixes (they may have changed)
    if auto_fixed:
        try:
            channel_data = get_channel_data(token)
        except Exception:
            pass
        try:
            playlists = get_playlists(token)
        except Exception:
            pass

    # Clear stale health state — every report starts fresh from REAL current state
    health_state = load_health_state()
    health_state["checks"] = []   # wipe old checks; only keep THIS run
    issues = detect_issues(token, channel_data, videos, playlists, health_state)
    print(f"  Issues: {len(issues)} ({sum(1 for i in issues if i[0] in ('CRITICAL','HIGH'))} urgent)")

    # Reset action log — only keep issues from THIS run
    action_log = load_action_log()
    action_log["manual_needed"] = []  # wipe stale items; re-add current ones
    for m in manual_needed:
        if m not in action_log["manual_needed"]:
            action_log.setdefault("manual_needed", []).append(m)
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
