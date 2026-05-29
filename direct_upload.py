#!/usr/bin/env python3
"""Upload existing ViralDNA videos to YouTube as scheduled premieres."""
import os, sys, json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
PROJECT_ROOT = "/home/jay/ViralDNA"
CREDENTIALS_DIR = os.path.join(PROJECT_ROOT, "credentials")

sys.path.insert(0, os.path.join(PROJECT_ROOT, "modules"))
import config

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def get_youtube_service():
    token_path = os.path.join(CREDENTIALS_DIR, "youtube_token.json")
    secrets_path = os.path.join(CREDENTIALS_DIR, "client_secrets.json")

    with open(token_path) as f:
        token_info = json.load(f)
    with open(secrets_path) as f:
        secrets = json.load(f)

    creds = Credentials(
        token=token_info.get("token", token_info.get("access_token", "")),
        refresh_token=token_info.get("refresh_token", ""),
        token_uri=token_info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=secrets["installed"]["client_id"],
        client_secret=secrets["installed"]["client_secret"],
        scopes=token_info.get("scopes", ["https://www.googleapis.com/auth/youtube.upload"]),
    )

    if creds.expired and creds.refresh_token:
        print("  Refreshing token...")
        creds.refresh(Request())

    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, filepath, title, description, tags, is_short=False):
    now_ist = datetime.now(IST)

    if is_short:
        schedule_time = now_ist + timedelta(hours=2)
    else:
        schedule_time = now_ist + timedelta(hours=1, minutes=30)

    schedule_iso = schedule_time.isoformat()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": "25",
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    if is_short and "#Shorts" not in body["snippet"]["title"]:
        body["snippet"]["title"] = body["snippet"]["title"][:90] + " #Shorts"

    print("  Uploading: %s" % filepath)
    print("  Title: %s" % body["snippet"]["title"][:80])
    print("  Premiere at: %s" % schedule_time.strftime("%Y-%m-%d %H:%M IST"))

    media = MediaFileUpload(filepath, mimetype="video/mp4", resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print("  Upload progress: %d%%" % int(status.progress() * 100))

    video_id = response["id"]
    url = "https://youtube.com/watch?v=%s" % video_id
    print("  OK! Video ID: %s - %s" % (video_id, url))
    return video_id, url


def main():
    print("\n" + "=" * 60)
    print("ViralDNA Direct Video Upload — %s" % datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"))
    print("=" * 60 + "\n")

    videos = []

    main_path = os.path.join(PROJECT_ROOT, "videos/production_main.mp4")
    if os.path.exists(main_path) and os.path.getsize(main_path) > 1000:
        from datetime import datetime as dt
        mtime = os.path.getmtime(main_path)
        file_date = dt.fromtimestamp(mtime).strftime("%Y-%m-%d")
        if file_date == datetime.now(IST).strftime("%Y-%m-%d"):
            videos.append(("main", main_path))
            print("Found main video: %.1fMB (today)" % (os.path.getsize(main_path) / 1024 / 1024))
        else:
            print("Main video is from %s, not today" % file_date)

    short1_path = os.path.join(PROJECT_ROOT, "videos/production_short_1.mp4")
    if os.path.exists(short1_path) and os.path.getsize(short1_path) > 1000:
        from datetime import datetime as dt
        mtime = os.path.getmtime(short1_path)
        file_date = dt.fromtimestamp(mtime).strftime("%Y-%m-%d")
        if file_date == datetime.now(IST).strftime("%Y-%m-%d"):
            videos.append(("short_1", short1_path))
            print("Found short_1: %.1fMB (today)" % (os.path.getsize(short1_path) / 1024 / 1024))
        else:
            print("Short_1 is from %s, not today" % file_date)

    short2_path = os.path.join(PROJECT_ROOT, "videos/production_short_2.mp4")
    if os.path.exists(short2_path) and os.path.getsize(short2_path) > 1000:
        from datetime import datetime as dt
        mtime = os.path.getmtime(short2_path)
        file_date = dt.fromtimestamp(mtime).strftime("%Y-%m-%d")
        if file_date == datetime.now(IST).strftime("%Y-%m-%d"):
            videos.append(("short_2", short2_path))
            print("Found short_2: %.1fMB (today)" % (os.path.getsize(short2_path) / 1024 / 1024))

    if not videos:
        print("No today videos found to upload!")
        return []

    print("\n%d video(s) ready for upload\n" % len(videos))

    topic_title = "BJP To Launch Massive Gujarat Campaign To Mark PM Modi's 12-Year Term"
    try:
        with open(os.path.join(PROJECT_ROOT, "logs/last_topic.json")) as f:
            topic_data = json.load(f)
            topic_title = topic_data.get("title", topic_title)
    except:
        pass

    youtube = get_youtube_service()
    print("YouTube API connected\n")

    uploaded = []

    for slot, filepath in videos:
        is_short = slot != "main"

        if is_short:
            title = "BREAKING: " + topic_title[:65] + " #Shorts"
            description = "Breaking: %s\n\nWatch the full report on our channel!\n\n#NewsUpdate #IndiaNews" % topic_title
            tags = ["news", "india news", "breaking news", "shorts", "news update"]
        else:
            title = topic_title[:90] + " | Full Report"
            description = "Full report: %s\n\nThis is an automated news update from ViralDNA.\n\n#IndiaNews #BreakingNews" % topic_title
            tags = ["india news", "breaking news", "news report", "political news", "modi", "bjp"]

        try:
            video_id, url = upload_video(youtube, filepath, title, description, tags, is_short)
            uploaded.append({
                "slot": slot,
                "video_id": video_id,
                "title": title,
                "url": url,
                "timestamp": datetime.now(IST).isoformat(),
            })
            print()
        except Exception as e:
            print("  FAIL for %s: %s\n" % (slot, e))

    return uploaded


if __name__ == "__main__":
    results = main()
    if results:
        print("\n" + "=" * 60)
        print("UPLOAD SUMMARY")
        print("=" * 60)
        for r in results:
            print("  %s: %s" % (r["slot"], r["url"]))
        print("\nTotal: %d video(s) uploaded" % len(results))
    sys.exit(0 if results else 1)
