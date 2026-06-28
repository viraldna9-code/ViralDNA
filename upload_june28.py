#!/usr/bin/env python3
"""
Direct upload script for already-produced VDNA 3.0 videos.
Uses checkpoint metadata + YouTubeUploader for dedup, thumbnails, comments, playlists.
"""
import os
import sys
import json
import re
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

PROJECT_ROOT = "/home/jay/ViralDNA"
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "modules"))

import config
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build as gbuild
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

IST = ZoneInfo("Asia/Kolkata")

# ── Videos to upload ──
TOPIC_SLUG = "Ketan_Agarwal_murder_case_New_twist"
TOPIC_TITLE = "Ketan Agarwal murder case: New twist as viral cricket stadium video puts Siya Goyal, Chetan Chaudhary back in the hot seat"
SOURCE = "The Times of India"

VIDEO_FILES = {
    "main": os.path.join(PROJECT_ROOT, "videos", f"{TOPIC_SLUG}_Main.mp4"),
    "short_1": os.path.join(PROJECT_ROOT, "videos", f"{TOPIC_SLUG}_Short1.mp4"),
    "short_2": os.path.join(PROJECT_ROOT, "videos", f"{TOPIC_SLUG}_Short2.mp4"),
}

THUMBNAIL_FILES = {
    "main": os.path.join(PROJECT_ROOT, "thumbnails", f"{TOPIC_SLUG}_branded.jpg"),
}

# Title variants from checkpoint
TITLE_VARIANTS = {
    "main": [
        {"title": "Viral Twist: Cricket Stadium Footage REOPENS Ketan Agarwal Murder Case - New Evidence?", "score": 38},
        {"title": "Ketan Agarwal Murder Case: Viral Cricket Stadium Video Reopens Investigation - Siya Goyal & Chetan Chaudhary", "score": 33},
        {"title": "Cricket Stadium Video EXPLODES Ketan Agarwal Murder Case! New Twist!", "score": 30},
    ],
    "short_1": [
        {"title": "SHOCKING VIDEO! Ketan Agarwal Case REOPENED?", "score": 57},
    ],
    "short_2": [
        {"title": "Agarwal Murder: Did This VIDEO Change Everything?", "score": 52},
    ],
}

# Script content from checkpoint (for description)
MAIN_SCRIPT = """A shocking video is shaking up the Ketan Agarwal murder investigation, potentially changing everything we thought we knew! You might think this is just another crime story, but the fallout could impact how justice is served in Andhra Pradesh. We've got a new twist that puts Siya Goyal and Chetan Chaudhary right back in the spotlight, thanks to a viral clip from a cricket stadium. The authorities are now re-examining the evidence after this video surfaced, showing Goyal and Chaudhary at the stadium. This footage, according to reports from The Times of India, is creating a major stir."""


def build_fresh_service():
    """Build YouTube service with auto-refresh token."""
    cred_file = os.path.join(config.DRIVE.get("CREDENTIALS", "credentials"), "youtube_token.json")
    if not os.path.exists(cred_file):
        cred_file = "credentials/youtube_token.json"
    
    YOUTUBE_SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]
    
    creds = Credentials.from_authorized_user_file(cred_file, YOUTUBE_SCOPES)
    if creds and creds.refresh_token:
        needs_refresh = creds.expired
        if not needs_refresh and hasattr(creds, 'expiry') and creds.expiry:
            now_utc = datetime.now(timezone.utc)
            expiry = creds.expiry
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            needs_refresh = expiry < now_utc + timedelta(minutes=10)
        if needs_refresh:
            print("  🔄 Refreshing YouTube token...")
            creds.refresh(Request())
            with open(cred_file, "w") as f:
                f.write(creds.to_json())
            print("  ✅ Token refreshed and saved")
    
    return gbuild("youtube", "v3", credentials=creds)


def build_description(title_raw, is_short=False):
    """Build YouTube description with growth-optimized layout."""
    year = datetime.now().year
    today_str = datetime.now().strftime("%B %d, %Y")
    
    if is_short:
        desc_lines = [
            f"🔔 SUBSCRIBE → https://www.youtube.com/@TheViralDNA",
            f"{title_raw} ({today_str})",
            "",
            MAIN_SCRIPT[:200].strip() + "...",
            "",
            "📺 Watch the full story on TheViralDNA",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📺 TheViralDNA — Real News. Real Voices. Built with AI.",
            "🕘 New videos daily at 9:00 AM & 7:00 PM IST",
            "👍 Like • 💬 Comment • 📤 Share",
            "📧 viraldna9@gmail.com",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "Ketan Agarwal murder, Ketan Agarwal case, Siya Goyal, Chetan Chaudhary, cricket stadium video, viral video, Andhra Pradesh news, Indian crime, 2026",
            "",
            "🤖 ALTERED CONTENT DISCLOSURE:",
            "This video was produced using AI-assisted tools: AI script generation,",
            "AI voice synthesis, algorithmic video assembly.",
            "©️ Produced by TheViralDNA.",
        ]
    else:
        desc_lines = [
            f"🔔 SUBSCRIBE & hit the bell → https://www.youtube.com/@TheViralDNA",
            f"{title_raw} ({today_str})",
            "",
            MAIN_SCRIPT.strip()[:300],
            "",
            "⏱️ CHAPTERS:",
            "  0:00 The Viral Video Twist",
            "  1:20 Ketan Agarwal Case Background",
            "  2:40 Siya Goyal & Chetan Chaudhary Connection",
            "",
            f"SOURCE: {SOURCE}",
            "",
            f"🔑 TOPICS: Ketan Agarwal murder, Siya Goyal, Chetan Chaudhary, cricket stadium video, viral video, Andhra Pradesh news",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📺 TheViralDNA — Real News. Real Voices. Built with AI.",
            "🕘 New videos daily at 9:00 AM & 7:00 PM IST",
            "👍 Like • 💬 Comment • 📤 Share",
            "📧 viraldna9@gmail.com",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "#KetanAgarwal #SiyaGoyal #ChetanChaudhary #ViralVideo #AndhraPradesh #News2026",
            "",
            "🤖 ALTERED CONTENT DISCLOSURE:",
            "This video was produced using AI-assisted tools: AI script generation,",
            "AI voice synthesis, algorithmic video assembly. Visuals may",
            "include AI-generated imagery. Labeled per YouTube synthetic media policies.",
            "©️ Produced by TheViralDNA.",
        ]
    
    return "\n".join(desc_lines)


def build_tags(is_short=False):
    """Build tags list."""
    tags = [
        "Ketan Agarwal murder", "Siya Goyal", "Chetan Chaudhary",
        "cricket stadium video", "viral video", "Andhra Pradesh news",
        "Indian crime news", "breaking news 2026", "crime investigation",
        "TheViralDNA", "telugu varthalu", "trending India 2026",
        "News & Politics", "True Crime India",
    ]
    if is_short:
        tags.extend(["YouTube Shorts", "Shorts News", "Telugu Shorts", "#Shorts"])
    return tags


def upload_video(service, video_path, title, description, tags, thumbnail_path, is_short=False):
    """Upload a single video to YouTube."""
    category_id = "25"  # News & Politics
    
    # Schedule rule: main +1hr, shorts +30min from upload time
    now_ist = datetime.now(IST)
    if is_short:
        publish_time = now_ist + timedelta(minutes=30)
    else:
        publish_time = now_ist + timedelta(hours=1)
    
    utc_publish = publish_time.astimezone(timezone.utc)
    publish_at = utc_publish.isoformat().replace("+00:00", "Z")
    
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en-IN",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "publishAt": publish_at,
        },
    }
    
    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
    )
    
    print(f"   📤 Uploading: {os.path.basename(video_path)} ({os.path.getsize(video_path) / 1024 / 1024:.1f}MB)")
    print(f"   📝 Title: {title[:70]}...")
    print(f"   ⏰ Scheduled: {publish_time.strftime('%Y-%m-%d %H:%M')} IST")
    
    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )
    
    response = request.execute()
    video_id = response.get("id", "")
    print(f"   ✅ Uploaded! Video ID: {video_id}")
    
    # Set thumbnail
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
            ).execute()
            print(f"   🖼️  Thumbnail set: {os.path.basename(thumbnail_path)}")
        except Exception as e:
            print(f"   ⚠️ Thumbnail upload failed: {e}")
    
    return video_id


def post_pinned_comment(service, video_id):
    """Post a subscribe CTA as pinned comment."""
    try:
        comment_response = service.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": "🔔 Subscribe to TheViralDNA for daily news analysis → https://www.youtube.com/@TheViralDNA\n\n💬 What do you think about this new twist in the Ketan Agarwal case? Comment below!"
                        }
                    }
                }
            }
        ).execute()
        
        # Pin the comment
        comment_id = comment_response.get("id", "")
        if comment_id:
            try:
                service.comments().setModerationStatus(
                    id=comment_id,
                    moderationStatus="published",
                    banAuthor=False
                ).execute()
            except Exception:
                pass
    except Exception as e:
        print(f"   ⚠️ Comment failed: {e}")


def main():
    print("=" * 60)
    print("  VIRALDNA 3.0 — Direct YouTube Upload")
    print("=" * 60)
    print(f"  Topic: {TOPIC_TITLE}")
    print(f"  Time: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")
    print()
    
    # Verify files
    for slot, path in VIDEO_FILES.items():
        if os.path.exists(path):
            print(f"  ✅ {slot}: {os.path.basename(path)} ({os.path.getsize(path)/1024/1024:.1f}MB)")
        else:
            print(f"  ❌ MISSING: {path}")
            sys.exit(1)
    
    main_thumb = THUMBNAIL_FILES.get("main", "")
    if main_thumb and os.path.exists(main_thumb):
        print(f"  ✅ thumbnail: {os.path.basename(main_thumb)}")
    else:
        print(f"  ⚠️ No branded thumbnail found — will use auto-generated")
        main_thumb = ""
    
    # Build service
    print("\n  🔑 Authenticating with YouTube...")
    service = build_fresh_service()
    print("  ✅ Authenticated")
    
    # Check for duplicates
    print("\n  🔍 Checking for duplicate titles...")
    try:
        channel_resp = service.channels().list(part="id", mine=True).execute()
        channel_id = channel_resp.get("items", [{}])[0].get("id", "")
        if channel_id:
            search_resp = service.search().list(
                part="snippet",
                channelId=channel_id,
                type="video",
                order="date",
                maxResults=20
            ).execute()
            existing_titles = [item.get("snippet", {}).get("title", "") for item in search_resp.get("items", [])]
            best_title = TITLE_VARIANTS["main"][0]["title"]
            for et in existing_titles:
                # Simple word overlap check
                new_words = set(best_title.lower().split())
                ex_words = set(et.lower().split())
                if new_words and ex_words:
                    overlap = len(new_words & ex_words) / len(new_words | ex_words)
                    if overlap >= 0.5:
                        print(f"  ⚠️ DUPLICATE DETECTED ({overlap:.0%} similar): '{et}'")
                        print(f"  ⏭️ Skipping upload to avoid duplicate content.")
                        sys.exit(0)
            print("  ✅ No duplicates found")
    except Exception as e:
        print(f"  ⚠️ Dedup check failed: {e} — proceeding anyway")
    
    # Upload main video
    print("\n" + "=" * 40)
    print("  UPLOADING MAIN VIDEO")
    print("=" * 40)
    main_title = TITLE_VARIANTS["main"][0]["title"]
    main_desc = build_description(main_title, is_short=False)
    main_tags = build_tags(is_short=False)
    
    main_id = upload_video(
        service, VIDEO_FILES["main"], main_title, main_desc, main_tags,
        main_thumb, is_short=False
    )
    
    # Upload Short 1
    print("\n" + "=" * 40)
    print("  UPLOADING SHORT 1")
    print("=" * 40)
    short1_title = TITLE_VARIANTS["short_1"][0]["title"]
    short1_title_2026 = f"{short1_title} (2026) #Shorts"
    short1_desc = build_description(short1_title, is_short=True)
    short1_tags = build_tags(is_short=True)
    
    short1_id = upload_video(
        service, VIDEO_FILES["short_1"], short1_title_2026, short1_desc, short1_tags,
        main_thumb, is_short=True
    )
    
    # Upload Short 2
    print("\n" + "=" * 40)
    print("  UPLOADING SHORT 2")
    print("=" * 40)
    short2_title = TITLE_VARIANTS["short_2"][0]["title"]
    short2_title_2026 = f"{short2_title} (2026) #Shorts"
    short2_desc = build_description(short2_title, is_short=True)
    short2_tags = build_tags(is_short=True)
    
    short2_id = upload_video(
        service, VIDEO_FILES["short_2"], short2_title_2026, short2_desc, short2_tags,
        main_thumb, is_short=True
    )
    
    # Post pinned comments
    print("\n  💬 Posting pinned comments...")
    if main_id:
        post_pinned_comment(service, main_id)
    
    # Summary
    print("\n" + "=" * 60)
    print("  UPLOAD COMPLETE")
    print("=" * 60)
    print(f"  Main:  {main_id} | https://youtu.be/{main_id}")
    print(f"  Short1: {short1_id} | https://youtu.be/{short1_id}")
    print(f"  Short2: {short2_id} | https://youtu.be/{short2_id}")
    print(f"  Privacy: private (scheduled)")
    print("=" * 60)

    # Write manifest for pipeline blog-publish (decoupled from upload gate)
    manifest_dir = os.path.join(os.path.dirname(__file__), ".vdna2", "manual_uploads")
    os.makedirs(manifest_dir, exist_ok=True)
    manifest = {
        "topic_slug": TOPIC_SLUG,
        "youtube_url": f"https://youtu.be/{main_id}" if main_id else "",
        "video_id": main_id,
        "shorts": [
            {"video_id": short1_id, "youtube_url": f"https://youtu.be/{short1_id}"},
            {"video_id": short2_id, "youtube_url": f"https://youtu.be/{short2_id}"},
        ],
        "uploaded_at": datetime.now().isoformat(),
        "source": "upload_june28.py",
    }
    manifest_path = os.path.join(manifest_dir, f"{TOPIC_SLUG}.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  📋 Manifest written: {manifest_path}")


if __name__ == "__main__":
    main()
