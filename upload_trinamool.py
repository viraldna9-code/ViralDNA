#!/usr/bin/env python3
"""
Standalone upload script for Trinamool Rebel 10 MPs Meet BJP topic.
Approved by Jay on 2026-06-09.
Uploads: Main video + 2 Shorts to YouTube.
"""
import os
import sys
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# Setup paths
DRIVE_BASE = "/home/jay/ViralDNA"
sys.path.insert(0, DRIVE_BASE)
sys.path.insert(0, os.path.join(DRIVE_BASE, "modules"))

# Load config
from modules import config

# YouTube auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

IST = ZoneInfo("Asia/Kolkata")

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
]

TOKEN_PATH = os.path.join(DRIVE_BASE, "credentials", "youtube_token.json")

def get_youtube_service():
    if not os.path.exists(TOKEN_PATH):
        print(f"❌ YouTube token missing: {TOKEN_PATH}")
        return None
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, YOUTUBE_SCOPES)
    if creds and creds.expired and creds.refresh_token:
        print("🔄 Refreshing YouTube token...")
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    if creds:
        return build("youtube", "v3", credentials=creds)
    return None

def upload_video(youtube, video_path, title, description, thumbnail_path=None, is_short=False, tags=None):
    """Upload a single video to YouTube."""
    if not os.path.exists(video_path):
        print(f"❌ Video not found: {video_path}")
        return None

    # Build metadata
    if is_short and "#Shorts" not in title:
        title = f"{title} #Shorts"
    
    # Truncate title to 100 chars
    if len(title) > 100:
        title = title[:97] + "..."

    body = {
        "snippet": {
            "title": title,
            "description": description[:5000],
            "tags": tags or [],
            "categoryId": "25",  # News & Politics
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
            "publicStatsViewable": True,
        },
    }

    file_size = os.path.getsize(video_path) / (1024 * 1024)
    print(f"📤 Uploading: {os.path.basename(video_path)} ({file_size:.1f} MB)")
    print(f"   Title: {title[:80]}")

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        chunksize=10 * 1024 * 1024,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    # Execute resumable upload with retry
    response = None
    retries = 0
    max_retries = 3
    while response is None and retries < max_retries:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"   Progress: {int(status.progress() * 100)}%")
        except Exception as e:
            retries += 1
            print(f"   ⚠️ Retry {retries}/{max_retries}: {e}")
            time.sleep(5)

    if response and "id" in response:
        video_id = response["id"]
        video_url = f"https://youtube.com/watch?v={video_id}"
        print(f"   ✅ Uploaded! ID: {video_id} — {video_url}")

        # Upload thumbnail (main videos only)
        if thumbnail_path and not is_short and os.path.exists(thumbnail_path):
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
                ).execute()
                print(f"   🖼️ Thumbnail set")
            except Exception as e:
                print(f"   ⚠️ Thumbnail failed: {e}")

        return {"status": "success", "youtube_id": video_id, "youtube_url": video_url}
    else:
        print(f"   ❌ Upload failed")
        return {"status": "failed"}

def main():
    print("=" * 60)
    print("ViralDNA Manual Upload — Trinamool Rebel 10 MPs Meet BJP")
    print(f"Time: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=" * 60)

    youtube = get_youtube_service()
    if not youtube:
        print("❌ Cannot connect to YouTube API. Aborting.")
        sys.exit(1)

    # Topic info
    topic_title = "Trinamool Rebel, 10 MPs Meet BJP Leaders As Mamata Banerjee Attends INDIA Meet"
    topic_url = "https://feeds.feedburner.com/ndtvnews-top-stories"
    
    # Video files
    videos_dir = os.path.join(DRIVE_BASE, "videos")
    thumbnails_dir = os.path.join(DRIVE_BASE, "thumbnails")
    
    main_video = os.path.join(videos_dir, "Trinamool_Rebel_10_MPs_Meet_BJP_Main.mp4")
    short1_video = os.path.join(videos_dir, "Trinamool_Rebel_10_MPs_Meet_BJP_Short1.mp4")
    short2_video = os.path.join(videos_dir, "Trinamool_Rebel_10_MPs_Meet_BJP_Short2.mp4")
    main_thumbnail = os.path.join(thumbnails_dir, "Trinamool_Rebel_10_MPs_Meet_BJP_branded.jpg")

    # Common tags
    base_tags = [
        "Trinamool", "BJP", "Mamata Banerjee", "INDIA bloc", "Sukhendu Sekhar Ray",
        "political crisis", "West Bengal", "Rajya Sabha", "political news",
        "India news 2026", "breaking news", "TheViralDNA",
        "telugu news", "తెలుగు వార్తలు",
    ]

    # Main video description
    main_desc = f"""{topic_title}

In a dramatic political development, 10 Trinamool Congress rebel MPs met BJP leaders even as Mamata Banerjee attended the INDIA bloc meeting. This meeting signals a major shift in West Bengal politics.

📰 Source: NDTV
🔗 {topic_url}

━━━━━━━━━━━━━━━━━━━━
📌 The ViralDNA — Breaking News & Political Analysis
🔔 Subscribe for daily news updates: https://youtube.com/@TheViralDNA
━━━━━━━━━━━━━━━━━━━━

#Trinamool #BJP #MamataBanerjee #INDIAbloc #PoliticalCrisis #WestBengal #News2026"""

    results = {}

    # 1. Upload Main Video
    print("\n" + "─" * 40)
    print("1️⃣ MAIN VIDEO")
    print("─" * 40)
    results["main"] = upload_video(
        youtube=youtube,
        video_path=main_video,
        title=topic_title,
        description=main_desc,
        thumbnail_path=main_thumbnail,
        is_short=False,
        tags=base_tags,
    )

    if results["main"] and results["main"]["status"] == "success":
        main_video_url = results["main"]["youtube_url"]
        time.sleep(10)  # Rate limit

        # 2. Upload Short 1
        print("\n" + "─" * 40)
        print("2️⃣ SHORT 1")
        print("─" * 40)
        short1_title = "Trinamool 10 MPs Meet BJP Leaders 🔥 #Shorts"
        short1_desc = f"10 Trinamool rebel MPs met BJP leaders as Mamata attended INDIA meet.\n\n🎥 Watch full story: {main_video_url}\n\n#TheViralDNA #Trinamool #BJP #Shorts"
        results["short_1"] = upload_video(
            youtube=youtube,
            video_path=short1_video,
            title=short1_title,
            description=short1_desc,
            is_short=True,
            tags=["Trinamool", "BJP", "Shorts", "TheViralDNA", "political crisis"],
        )

        time.sleep(10)  # Rate limit

        # 3. Upload Short 2
        print("\n" + "─" * 40)
        print("3️⃣ SHORT 2")
        print("─" * 40)
        short2_title = "Mamata's Own MPs Rebel — BJP Meeting Shocker 😱 #Shorts"
        short2_desc = f"Trinamool MPs break ranks and meet BJP while Mamata is at INDIA bloc meet.\n\n🎥 Full story: {main_video_url}\n\n#TheViralDNA #Trinamool #MamataBanerjee #Shorts"
        results["short_2"] = upload_video(
            youtube=youtube,
            video_path=short2_video,
            title=short2_title,
            description=short2_desc,
            is_short=True,
            tags=["Trinamool", "Mamata Banerjee", "rebel MPs", "Shorts", "TheViralDNA"],
        )

    # Summary
    print("\n" + "=" * 60)
    print("📊 UPLOAD SUMMARY")
    print("=" * 60)
    for key, result in results.items():
        if result and result.get("status") == "success":
            print(f"  ✅ {key}: {result['youtube_url']}")
        else:
            print(f"  ❌ {key}: FAILED — {result}")

    # Save results
    results_path = os.path.join(DRIVE_BASE, "output", "runtime", "upload_results_trinamool.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n💾 Results saved to: {results_path}")

    return results

if __name__ == "__main__":
    main()
