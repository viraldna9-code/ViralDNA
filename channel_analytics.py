#!/usr/bin/env python3
"""
ViralDNA YouTube Channel Analytics
===================================
Pulls real channel data from YouTube Data API.
Tracks metrics over time to measure growth.

Current capabilities (without Analytics API scope):
- Channel stats: views, subscribers, video count
- Per-video stats: views, likes, comments, duration, privacy status
- Tracks metrics history locally in analytics/metrics_history.json

Note: YouTube Analytics API (detailed demographics, traffic sources,
watch time, impressions) requires additional scope:
    https://www.googleapis.com/auth/youtube.analytics.readonly
To enable: re-authorize OAuth with that scope added.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(PROJECT_ROOT, "credentials", "youtube_token.json")
METRICS_FILE = os.path.join(PROJECT_ROOT, "analytics", "metrics_history.json")
CHANNEL_ID = "UCkW7fqkJiaej2PeNcP4PejQ"
HISTORY_DAYS = 90  # keep 90 days of history

# Monetization thresholds
MONETIZATION = {
    "subscribers": 1000,
    "watch_hours": 4000,
    "shorts_views_90d": 10_000_000,  # alternative path
}


def load_credentials():
    """Load and refresh YouTube OAuth credentials if needed."""
    with open(CREDENTIALS_FILE) as f:
        creds = json.load(f)

    # Check expiry
    expiry_str = creds.get("expiry", "")
    token = creds.get("token", "")

    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if now >= expiry - timedelta(minutes=5):
                print("  Token expired, refreshing...")
                token = refresh_token(creds)
                creds["token"] = token
                save_credentials(creds)
        except Exception:
            pass

    return token


def refresh_token(creds):
    """Refresh OAuth token using refresh_token."""
    import urllib.parse

    data = urllib.parse.urlencode(
        {
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode()

    req = urllib.request.Request(creds["token_uri"], data=data)
    resp = urllib.request.urlopen(req, timeout=15)
    new_creds = json.loads(resp.read())
    return new_creds["access_token"]


def save_credentials(creds):
    """Save updated credentials."""
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(creds, f)


def yt_get(token, url):
    """Make authenticated YouTube API GET request."""
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())


def get_channel_stats(token):
    """Get current channel statistics."""
    data = yt_get(
        token,
        f"https://www.googleapis.com/youtube/v3/channels?part=statistics&id={CHANNEL_ID}",
    )
    if data.get("items"):
        return data["items"][0]["statistics"]
    return {}


def get_all_channel_videos(token):
    """Get all videos from the channel (handles pagination)."""
    videos = []
    page_token = ""

    while True:
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={CHANNEL_ID}&maxResults=50&order=date&type=video"
        if page_token:
            url += f"&pageToken={page_token}"

        data = yt_get(token, url)
        videos.extend(data.get("items", []))
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break

    return videos


def get_video_stats(token, video_ids):
    """Get detailed statistics for a list of videos."""
    stats = {}
    # API allows max 50 IDs per request
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        ids = ",".join(batch)
        url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,contentDetails,snippet,status&id={ids}"
        data = yt_get(token, url)
        for item in data.get("items", []):
            stats[item["id"]] = {
                "statistics": item.get("statistics", {}),
                "duration": item.get("contentDetails", {}).get("duration", ""),
                "privacy": item.get("status", {}).get("privacyStatus", ""),
                "title": item.get("snippet", {}).get("title", ""),
                "published": item.get("snippet", {}).get("publishedAt", ""),
                "thumbnail": item.get("snippet", {})
                .get("thumbnails", {})
                .get("high", {})
                .get("url", ""),
            }
    return stats


def load_metrics_history():
    """Load historical metrics data."""
    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)
    if os.path.exists(METRICS_FILE):
        with open(METRICS_FILE) as f:
            return json.load(f)
    return {"channel_id": CHANNEL_ID, "snapshots": []}


def save_metrics_history(history):
    """Save metrics history."""
    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)
    with open(METRICS_FILE, "w") as f:
        json.dump(history, f, indent=2)


def take_snapshot(token):
    """Take a snapshot of current channel metrics."""
    now = datetime.now(IST)
    print(f"Taking metrics snapshot: {now.strftime('%Y-%m-%d %H:%M IST')}")

    # Channel-level stats
    channel_stats = get_channel_stats(token)
    print(
        f"  Channel: {channel_stats.get('viewCount', 0)} views, "
        f"{channel_stats.get('subscriberCount', 0)} subs, "
        f"{channel_stats.get('videoCount', 0)} videos"
    )

    # Video-level stats
    video_items = get_all_channel_videos(token)
    video_ids = [
        item["id"]["videoId"]
        for item in video_items
        if item.get("id", {}).get("kind") == "youtube#video"
    ]
    print(f"  Found {len(video_ids)} videos")

    video_stats = get_video_stats(token, video_ids)

    # Aggregate video stats
    total_views = 0
    total_likes = 0
    total_comments = 0
    public_videos = 0
    shorts_count = 0

    videos_data = []
    for vid, vs in video_stats.items():
        s = vs["statistics"]
        views = int(s.get("viewCount", 0))
        likes = int(s.get("likeCount", 0))
        comments = int(s.get("commentCount", 0))
        total_views += views
        total_likes += likes
        total_comments += comments

        if vs["privacy"] == "public":
            public_videos += 1

        # Detect shorts (< 60 seconds)
        dur = vs["duration"]
        seconds = parse_duration(dur)
        is_short = seconds > 0 and seconds <= 60
        if is_short:
            shorts_count += 1

        videos_data.append(
            {
                "id": vid,
                "title": vs["title"][:80],
                "views": views,
                "likes": likes,
                "comments": comments,
                "privacy": vs["privacy"],
                "published": vs["published"],
                "is_short": is_short,
                "duration_seconds": seconds,
            }
        )

    # Sort by views descending
    videos_data.sort(key=lambda x: x["views"], reverse=True)

    snapshot = {
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "channel": {
            "total_views": int(channel_stats.get("viewCount", 0)),
            "subscribers": int(channel_stats.get("subscriberCount", 0)),
            "video_count": int(channel_stats.get("videoCount", 0)),
        },
        "videos": {
            "total": len(video_ids),
            "public": public_videos,
            "shorts": shorts_count,
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
        },
        "top_videos": videos_data[:10],
    }

    return snapshot


def parse_duration(iso_duration):
    """Parse ISO 8601 duration (PT1M30S) to seconds."""
    import re

    if not iso_duration:
        return 0
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def compute_daily_changes(history, today_snapshot):
    """Compute changes vs yesterday's snapshot."""
    snapshots = history.get("snapshots", [])
    if not snapshots:
        return None

    # Find yesterday's snapshot
    today_date = today_snapshot["date"]
    yesterday = None
    for s in reversed(snapshots):
        if s["date"] < today_date:
            yesterday = s
            break

    if not yesterday:
        return None

    changes = {
        "views_delta": today_snapshot["channel"]["total_views"]
        - yesterday["channel"]["total_views"],
        "subscribers_delta": today_snapshot["channel"]["subscribers"]
        - yesterday["channel"]["subscribers"],
        "video_count_delta": today_snapshot["channel"]["video_count"]
        - yesterday["channel"]["video_count"],
        "video_views_delta": today_snapshot["videos"]["total_views"]
        - yesterday["videos"]["total_views"],
        "likes_delta": today_snapshot["videos"]["total_likes"]
        - yesterday["videos"]["total_likes"],
        "prev_date": yesterday["date"],
    }
    return changes


def compute_weekly_changes(history, today_snapshot):
    """Compute changes vs 7 days ago."""
    snapshots = history.get("snapshots", [])
    today_date = today_snapshot["date"]

    week_ago = None
    for s in reversed(snapshots):
        if s["date"] <= today_date:
            from datetime import date as dt_date

            d1 = dt_date.fromisoformat(today_date)
            d2 = dt_date.fromisoformat(s["date"])
            if (d1 - d2).days >= 7:
                week_ago = s
                break

    if not week_ago:
        return None

    changes = {
        "views_delta": today_snapshot["channel"]["total_views"]
        - week_ago["channel"]["total_views"],
        "subscribers_delta": today_snapshot["channel"]["subscribers"]
        - week_ago["channel"]["subscribers"],
        "video_count_delta": today_snapshot["channel"]["video_count"]
        - week_ago["channel"]["video_count"],
        "video_views_delta": today_snapshot["videos"]["total_views"]
        - week_ago["videos"]["total_views"],
        "likes_delta": today_snapshot["videos"]["total_likes"]
        - week_ago["videos"]["total_likes"],
        "prev_date": week_ago["date"],
        "days_diff": 7,
    }
    return changes


def compute_monetization_progress(snapshot):
    """Compute progress toward YouTube monetization thresholds."""
    subs = snapshot["channel"]["subscribers"]
    # Note: watch hours and shorts views require Analytics API
    # We estimate from available data

    progress = {
        "subscribers": {
            "current": subs,
            "target": MONETIZATION["subscribers"],
            "pct": min(100, round(subs / MONETIZATION["subscribers"] * 100, 1)),
            "remaining": max(0, MONETIZATION["subscribers"] - subs),
        },
        "estimated_watch_hours": {
            "note": "Requires YouTube Analytics API scope. Currently estimated from video views.",
            "estimated_from_views": round(
                snapshot["videos"]["total_views"] * 0.5 / 60, 1
            ),  # rough: 30s avg watch per view
            "target": MONETIZATION["watch_hours"],
        },
        "shorts_path": {
            "note": "10M shorts views in 90 days (alternative monetization path)",
            "current_shorts": snapshot["videos"]["shorts"],
            "target_views": MONETIZATION["shorts_views_90d"],
        },
    }
    return progress


def format_daily_report(snapshot, changes, monetization):
    """Format a daily analytics report."""
    now = datetime.now(IST)
    ch = snapshot["channel"]
    vi = snapshot["videos"]

    report = f"""📊 The Viral DNA — Daily Analytics Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 {now.strftime('%A, %B %d, %Y')}

📡 CHANNEL METRICS
  Views:      {ch['total_views']:,}
  Subscribers: {ch['subscribers']}
  Videos:      {ch['video_count']}

📹 VIDEO PERFORMANCE
  Total Videos: {vi['total']} ({vi['public']} public, {vi['shorts']} shorts)
  Total Views:  {vi['total_views']:,}
  Total Likes:  {vi['total_likes']:,}
  Total Comments: {vi['total_comments']:,}"""

    if changes:
        arrow = lambda v: ("📈 +" if v >= 0 else "📈 ") + str(v)
        report += f"""

📊 VS YESTERDAY ({changes['prev_date']})
  Views:      {arrow(changes['views_delta'])}
  Subscribers: {arrow(changes['subscribers_delta'])}
  Videos:     {arrow(changes['video_count_delta'])}
  Video Views: {arrow(changes['video_views_delta'])}
  Likes:      {arrow(changes['likes_delta'])}"""

    report += f"""

💰 MONETIZATION PROGRESS
  Subscribers: {monetization['subscribers']['current']}/{monetization['subscribers']['target']} ({monetization['subscribers']['pct']}%)
  Est. Watch Hours: ~{monetization['estimated_watch_hours']['estimated_from_views']}h / {monetization['estimated_watch_hours']['target']}h needed
  Shorts: {monetization['shorts_path']['current_shorts']} published

🏆 TOP VIDEOS
"""
    for i, v in enumerate(snapshot["top_videos"][:5], 1):
        short_tag = " [SHORT]" if v.get("is_short") else ""
        report += f'  {i}. {v["title"][:45]}{short_tag}\n'
        report += f'     👁 {v["views"]:,} views | 👍 {v["likes"]} | 💬 {v["comments"]}\n'

    report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n💻 Open laptop → Tell Hermes: build"
    return report


def format_weekly_report(snapshot, changes, monetization, history):
    """Format a weekly comparison report."""
    now = datetime.now(IST)
    ch = snapshot["channel"]
    vi = snapshot["videos"]

    # Count new videos this week
    snapshots = history.get("snapshots", [])
    week_ago_date = changes.get("prev_date", "") if changes else ""

    report = f"""📊📈 The Viral DNA — WEEKLY REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Week ending {now.strftime('%A, %B %d, %Y')}

📡 CHANNEL SNAPSHOT
  Views:      {ch['total_views']:,}
  Subscribers: {ch['subscribers']}
  Videos:      {ch['video_count']}"""

    if changes:
        arrow = lambda v: ("📈 +" if v >= 0 else "📉 ") + str(v)
        report += f"""

📊 WEEKLY COMPARISON (vs {changes['prev_date']})
  Views:      {arrow(changes['views_delta'])}
  Subscribers: {arrow(changes['subscribers_delta'])}
  Videos:     {arrow(changes['video_count_delta'])}
  Video Views: {arrow(changes['video_views_delta'])}
  Likes:      {arrow(changes['likes_delta'])}"""

    # Growth rate
    snapshots = history.get("snapshots", [])
    daily_subs = 0
    if len(snapshots) >= 2:
        first = snapshots[0]
        days_total = max(
            1,
            (
                datetime.fromisoformat(snapshot["timestamp"])
                - datetime.fromisoformat(first["timestamp"])
            ).days,
        )
        total_view_growth = ch["total_views"] - first["channel"]["total_views"]
        total_sub_growth = ch["subscribers"] - first["channel"]["subscribers"]
        daily_views = round(total_view_growth / max(1, days_total))
        daily_subs = round(total_sub_growth / max(1, days_total), 2)

        report += f"""

📈 TRACKING (since {first['date']})
  Days tracked: {days_total}
  View growth: {total_view_growth:,} (~{daily_views}/day)
  Sub growth: {total_sub_growth} (~{daily_subs}/day)"""

    report += f"""

💰 MONETIZATION PROGRESS
  Subscribers: {monetization['subscribers']['current']}/{monetization['subscribers']['target']} ({monetization['subscribers']['pct']}%)
  Need {monetization['subscribers']['remaining']} more subscribers
  Est. Watch Hours: ~{monetization['estimated_watch_hours']['estimated_from_views']}h / {monetization['estimated_watch_hours']['target']}h
"""

    if monetization["subscribers"]["remaining"] > 0:
        daily_subs_for_est = max(0.1, daily_subs)
        days_to_monetize = round(
            monetization["subscribers"]["remaining"] / daily_subs_for_est
        )
        est_date = now + timedelta(days=days_to_monetize)
        report += f"  📅 Est. monetization date (subscriber path): {est_date.strftime('%B %d, %Y')}\n"
        report += (
            f"     (at current rate of ~{daily_subs_for_est:.1f} subs/day)\n"
        )

    report += "\n🏆 TOP 5 VIDEOS (all time)\n"
    for i, v in enumerate(snapshot["top_videos"][:5], 1):
        short_tag = " [SHORT]" if v.get("is_short") else ""
        report += f'  {i}. {v["title"][:45]}{short_tag}\n'
        report += f'     👁 {v["views"]:,} | 👍 {v["likes"]} | 💬 {v["comments"]}\n'

    report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n💡 Weekly review complete. Keep building!"
    return report


def main():
    """Main: take snapshot, compute changes, generate reports."""
    import argparse

    parser = argparse.ArgumentParser(description="ViralDNA Channel Analytics")
    parser.add_argument(
        "--mode",
        choices=["snapshot", "daily", "weekly"],
        default="snapshot",
        help="snapshot: just save data. daily: daily report. weekly: weekly report.",
    )
    args = parser.parse_args()

    print("ViralDNA Channel Analytics")
    print("=" * 40)

    # Load and refresh token
    token = load_credentials()

    # Take current snapshot
    snapshot = take_snapshot(token)

    # Load history
    history = load_metrics_history()

    # Dedup: don't save if we already have a snapshot for today
    today = snapshot["date"]
    existing_dates = [s["date"] for s in history["snapshots"]]

    if args.mode == "snapshot":
        if today not in existing_dates:
            history["snapshots"].append(snapshot)
            save_metrics_history(history)
            print(f"Snapshot saved. Total snapshots: {len(history['snapshots'])}")
        else:
            print(f"Snapshot for {today} already exists, skipping save.")

    elif args.mode == "daily":
        # Save snapshot
        if today not in existing_dates:
            history["snapshots"].append(snapshot)
        else:
            # Update today's snapshot
            for i, s in enumerate(history["snapshots"]):
                if s["date"] == today:
                    history["snapshots"][i] = snapshot
                    break

        save_metrics_history(history)

        # Compute changes
        changes = compute_daily_changes(history, snapshot)
        monetization = compute_monetization_progress(snapshot)

        # Format and print report
        report = format_daily_report(snapshot, changes, monetization)
        print("\n" + report)
        return report

    elif args.mode == "weekly":
        # Save snapshot
        if today not in existing_dates:
            history["snapshots"].append(snapshot)
        else:
            for i, s in enumerate(history["snapshots"]):
                if s["date"] == today:
                    history["snapshots"][i] = snapshot
                    break

        save_metrics_history(history)

        # Compute weekly changes
        changes = compute_weekly_changes(history, snapshot)
        monetization = compute_monetization_progress(snapshot)

        report = format_weekly_report(snapshot, changes, monetization, history)
        print("\n" + report)
        return report


if __name__ == "__main__":
    main()
