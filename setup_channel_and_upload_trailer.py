#!/usr/bin/env python3
"""
THE VIRAL DNA — Channel Trailer Upload + Channel Metadata Setup
Uploads trailer_v7_final.mp4 and sets:
  1. Video as channel trailer
  2. Channel description (about)
  3. Channel keywords
  4. Channel default language
"""

import json
import os
import sys
import time
import subprocess

# ── Setup paths ──
BASE = "/home/jay/ViralDNA"
CRED = os.path.join(BASE, "credentials", "youtube_token.json")
TRAILER = os.path.join(BASE, "videos", "trailer", "v7", "trailer_v7_final.mp4")

# ── Channel metadata ──
CHANNEL_TITLE = "The Viral DNA"

CHANNEL_DESCRIPTION = """The Viral DNA — Telugu News. Real News. Real Voices. Built with AI.

ViralDNA is an autonomous Telugu news channel delivering daily news coverage from Andhra Pradesh, Telangana, and around the world — all powered by artificial intelligence.

Coverage includes:
• Andhra Pradesh News
• Telangana News
• Politics, Entertainment, Sports, Tech & Business
• Telugu people news worldwide

No newsroom. No anchors. No agenda. Just AI delivering what matters to Telugu people everywhere.

📰 Real News. Real Voices. Built with AI.
🔔 Subscribe. One click. Every day."""

CHANNEL_KEYWORDS = [
    "telugu news", "andhra pradesh news", "telangana news",
    "telugu live news", "telugu breaking news",
    "viral dna", "ai news", "telugu people",
    "telugu diaspora", "telugu world news",
    "telugu daily news", "ap news", "ts news"
]

CHANNEL_DEFAULT_LANGUAGE = "en"

VIDEO_TITLE = "The Viral DNA — Channel Trailer | Real News. Real Voices. Built with AI."
VIDEO_DESCRIPTION = CHANNEL_DESCRIPTION
VIDEO_TAGS = CHANNEL_KEYWORDS + ["channel trailer", "telugu channel", "ai news channel"]
VIDEO_CATEGORY = "25"  # News & Politics
VIDEO_PRIVACY = "private"  # Private first, switch to public after verification


def check_deps():
    """Verify google-api-python-client is installed."""
    try:
        import googleapiclient
        print("[OK] googleapiclient installed")
    except ImportError:
        print("[INSTALL] google-api-python-client not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install",
                        "google-api-python-client", "google-auth-oauthlib", "-q"],
                       check=True)
        print("[OK] Installed.")


def get_youtube():
    """Build YouTube API client from stored OAuth token."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    with open(CRED) as f:
        cred_data = json.load(f)

    creds = Credentials(
        token=cred_data["token"],
        refresh_token=cred_data["refresh_token"],
        token_uri=cred_data["token_uri"],
        client_id=cred_data["client_id"],
        client_secret=cred_data["client_secret"],
        scopes=cred_data["scopes"],
    )

    # Refresh if expired
    if creds.expired:
        print("[AUTH] Token expired, refreshing...")
        creds.refresh(Request())
        # Save refreshed token
        cred_data["token"] = creds.token
        with open(CRED, "w") as f:
            json.dump(cred_data, f, indent=2)
        print("[AUTH] Token refreshed and saved.")

    from googleapiclient.discovery import build
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    return youtube


def verify_token(youtube):
    """Verify token works by reading channel info."""
    resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    if not resp.get("items"):
        print("[ERROR] Token cannot read channel. Scopes may be insufficient.")
        print("  Required: youtube.readonly or youtube.force-ssl")
        sys.exit(1)
    ch = resp["items"][0]
    print(f"[OK] Channel: {ch['snippet']['title']}")
    print(f"     ID: {ch['id']}")
    print(f"     Subs: {ch['statistics'].get('subscriberCount', '?')}")
    return ch["id"]


def upload_trailer(youtube, channel_id):
    """Upload trailer video."""
    print(f"\n[S1] Uploading trailer...")
    print(f"  File: {TRAILER}")
    print(f"  Size: {os.path.getsize(TRAILER) / 1024 / 1024:.1f} MB")

    if not os.path.exists(TRAILER):
        print(f"[ERROR] File not found: {TRAILER}")
        sys.exit(1)

    body = {
        "snippet": {
            "title": VIDEO_TITLE,
            "description": VIDEO_DESCRIPTION,
            "tags": VIDEO_TAGS,
            "categoryId": VIDEO_CATEGORY,
            "defaultLanguage": CHANNEL_DEFAULT_LANGUAGE,
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": VIDEO_PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }

    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(TRAILER, mimetype="video/mp4", resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print("  Uploading (resumable)...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Progress: {pct}%", end="\r")

    video_id = response["id"]
    print(f"\n  [OK] Uploaded! Video ID: {video_id}")
    print(f"  URL: https://youtube.com/watch?v={video_id}")
    return video_id


def set_channel_trailer(youtube, channel_id, video_id):
    """Set the uploaded video as channel trailer."""
    print(f"\n[S2] Setting channel trailer...")

    # Method: channels().update with brandingSettings
    # Retrieve current branding first
    current = youtube.channels().list(
        part="brandingSettings",
        id=channel_id,
    ).execute()

    if not current.get("items"):
        print("[ERROR] Cannot read channel branding settings")
        sys.exit(1)

    # Update with new trailer
    update_body = {
        "id": channel_id,
        "brandingSettings": {
            "channel": {
                "unsubscribedTrailer": video_id,
            }
        }
    }

    resp = youtube.channels().update(
        part="brandingSettings",
        body=update_body,
    ).execute()

    # Verify
    trailer_set = resp.get("brandingSettings", {}).get("channel", {}).get("unsubscribedTrailer")
    if trailer_set == video_id:
        print(f"  [OK] Trailer set: {video_id}")
    else:
        print(f"  [WARN] Trail set response: {trailer_set}")
        print("  [INFO] Trailer may need manual verification in YouTube Studio")


def set_channel_metadata(youtube, channel_id):
    """Set channel description, keywords, default language."""
    print(f"\n[S3] Updating channel description & keywords...")

    body = {
        "id": channel_id,
        "snippet": {
            "title": CHANNEL_TITLE,
            "description": CHANNEL_DESCRIPTION,
            "defaultLanguage": CHANNEL_DEFAULT_LANGUAGE,
        },
        "brandingSettings": {
            "channel": {
                "keywords": " ".join(CHANNEL_KEYWORDS),
                "defaultLanguage": CHANNEL_DEFAULT_LANGUAGE,
                "profileColor": "#CC0000",
            }
        }
    }

    resp = youtube.channels().update(
        part="snippet,brandingSettings",
        body=body,
    ).execute()

    desc = resp.get("snippet", {}).get("description", "")
    kws = resp.get("brandingSettings", {}).get("channel", {}).get("keywords", "")

    print(f"  [OK] Description: {len(desc)} chars")
    print(f"  [OK] Keywords: {len(kws.split())} keywords set")
    return resp


def verify_all(youtube, channel_id, video_id):
    """Final verification."""
    print(f"\n[S4] Verifying everything...")

    # Check trailer
    ch = youtube.channels().list(
        part="brandingSettings",
        id=channel_id,
    ).execute()
    trailer = ch["items"][0].get("brandingSettings", {}).get("channel", {}).get("unsubscribedTrailer")
    print(f"  Trailer: {trailer} {'✓' if trailer == video_id else '✗'}")

    # Check description
    ch2 = youtube.channels().list(
        part="snippet", id=channel_id,
    ).execute()
    desc = ch2["items"][0]["snippet"].get("description", "")
    print(f"  Description: {'set ✓' if 'Real News' in desc else 'MISSING ✗'}")
    keywords = ch["items"][0].get("brandingSettings", {}).get("channel", {}).get("keywords", "")
    print(f"  Keywords: {'set ✓' if keywords else 'MISSING ✗'}")

    # Check video exists
    vid = youtube.videos().list(part="snippet,status", id=video_id).execute()
    if vid.get("items"):
        v = vid["items"][0]
        print(f"  Video: {v['snippet']['title']}")
        print(f"  Privacy: {v['status']['privacyStatus']}")
        print(f"  Status: {'uploaded ✓' if v['status'].get('uploadStatus') == 'processed' else 'processing...'}")
    else:
        print(f"  Video: NOT FOUND (still processing)")

    return trailer == video_id


def main():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  THE VIRAL DNA — Channel Setup")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    check_deps()
    youtube = get_youtube()
    channel_id = verify_token(youtube)

    print(f"\n  Channel:  {channel_id}")
    print(f"  Trailer:  {TRAILER}")
    print(f"  Size:     {os.path.getsize(TRAILER) / 1024 / 1024:.1f} MB")

    # 1. Upload trailer
    video_id = upload_trailer(youtube, channel_id)

    # Small delay for YouTube to register
    print("\n  Waiting 5s for YouTube to register video...")
    time.sleep(5)

    # 2. Set as trailer
    set_channel_trailer(youtube, channel_id, video_id)

    # 3. Set channel description + keywords
    set_channel_metadata(youtube, channel_id)

    # 4. Verify
    time.sleep(3)
    ok = verify_all(youtube, channel_id, video_id)

    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if ok:
        print("  ✓ ALL DONE — Channel fully configured")
    else:
        print("  ~ MOSTLY DONE — Some items need manual check")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Video ID:  {video_id}")
    print(f"  Watch:     https://youtube.com/watch?v={video_id}")
    print(f"  Channel:   https://youtube.com/channel/{channel_id}")
    print()

    return video_id


if __name__ == "__main__":
    main()
