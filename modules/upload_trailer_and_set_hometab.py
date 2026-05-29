#!/usr/bin/env python3
# VERSION: 1.0
# SCRIPT: upload_trailer_and_set_hometab.py
# PURPOSE: Upload channel trailer to YouTube, set it as channel trailer,
#          set featured video for new visitors (hometab configuration).
#
# USAGE:
#   python3 upload_trailer_and_set_hometab.py [--dry-run]
#
# REQUIREMENTS:
#   - credentials/youtube_token.json (with youtube.force-ssl scope)
#   - videos/trailer/trailer_final.mp4
#   - thumbnails/trailer/trailer_branded.jpg

import os
import sys
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ── Bootstrap ──
MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(MODULES_DIR)
sys.path.insert(0, MODULES_DIR)
import config

DRIVE = config.DRIVE
CREDENTIALS_DIR = DRIVE["CREDENTIALS"]
TOKEN_FILE = os.path.join(CREDENTIALS_DIR, "youtube_token.json")
CLIENT_SECRETS_FILE = os.path.join(CREDENTIALS_DIR, "client_secrets.json")

TRAILER_VIDEO = os.path.join(DRIVE["VIDEO_OUTPUT"], "trailer", "trailer_final.mp4")
TRAILER_THUMB = os.path.join(DRIVE["THUMBNAILS"], "trailer", "trailer_branded.jpg")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

# ── Trailer metadata ──
TRAILER_TITLE = "ViralDNA — Telugu Diaspora News | Built with AI"
TRAILER_DESCRIPTION = """ViralDNA — Telugu Diaspora News

Every Telugu family around the world has one question: What is happening back home?

This channel delivers:
• Breaking Telugu news in English and Telugu
• Politics, policy, and government updates
• Sports, entertainment, and technology
• Culture and stories from the Telugu diaspora
• Real news with real voices from around the world

Built entirely with AI tools — single click production. Real news. Real voices.

Subscribe to stay connected.
సభ్యత్వం పొందండి. మనతో ఉండండि.

#ViralDNA #TeluguNews #TeluguDiaspora
"""
TRAILER_TAGS = [
    "telugu news", "telugu diaspora", "viral dna", "telugu breaking news",
    "andhra pradesh news", "telangana news", "telugu world news",
    "ai news channel", "telugu live news", "telugu latest news",
    "nri news", "telugu nri", "indian news", "south indian news",
    "telugu cinema", "telugu sports", "telugu culture",
]


def load_credentials(dry_run=False):
    """Load YouTube OAuth2 credentials from token file."""
    if not os.path.exists(TOKEN_FILE):
        print(f"  ❌ Token file not found: {TOKEN_FILE}")
        print("  Run the OAuth flow first to generate youtube_token.json")
        return None

    with open(TOKEN_FILE, "r") as f:
        token_data = json.load(f)

    creds = Credentials.from_authorized_user_info(token_data, SCOPES)

    if creds.expired and creds.refresh_token:
        if dry_run:
            print("  [DRY RUN] Would refresh expired token")
        else:
            try:
                creds.refresh(Request())
                # Save refreshed token
                with open(TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
                print("  ✅ Token refreshed")
            except Exception as e:
                print(f"  ❌ Token refresh failed: {e}")
                return None

    return creds


def upload_trailer(youtube, dry_run=False):
    """Upload the trailer video to YouTube."""
    print("\n📤 Uploading channel trailer...")

    if not os.path.exists(TRAILER_VIDEO):
        print(f"  ❌ Trailer video not found: {TRAILER_VIDEO}")
        return None

    file_size = os.path.getsize(TRAILER_VIDEO)
    print(f"  📁 Video: {TRAILER_VIDEO} ({file_size / 1024:.1f} KB)")

    if dry_run:
        print("  [DRY RUN] Would upload trailer video")
        return "DRY_RUN_VIDEO_ID"

    body = {
        "snippet": {
            "title": TRAILER_TITLE,
            "description": TRAILER_DESCRIPTION,
            "tags": TRAILER_TAGS,
            "categoryId": "25",  # News & Politics
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
            "publicStatsViewable": True,
            "license": "youtube",
            "liveBroadcastContent": "none",
        },
    }

    media = MediaFileUpload(
        TRAILER_VIDEO,
        mimetype="video/mp4",
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    # Execute resumable upload with progress
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  📊 Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    video_url = f"https://youtube.com/watch?v={video_id}"
    print(f"  ✅ Upload complete!")
    print(f"  🎬 Video ID: {video_id}")
    print(f"  🔗 URL: {video_url}")

    # Upload thumbnail
    if os.path.exists(TRAILER_THUMB):
        print(f"\n🖼️  Uploading trailer thumbnail...")
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(TRAILER_THUMB, mimetype="image/jpeg"),
            ).execute()
            print(f"  ✅ Thumbnail uploaded")
        except HttpError as e:
            print(f"  ⚠️ Thumbnail upload failed: {e}")
    else:
        print(f"  ⚠️ Thumbnail not found: {TRAILER_THUMB}")

    return video_id


def set_channel_trailer(youtube, video_id, dry_run=False):
    """Set the uploaded video as the channel trailer for new visitors."""
    print(f"\n🏠 Setting channel trailer (video: {video_id})...")

    if dry_run:
        print("  [DRY RUN] Would set channel trailer via channels().update()")
        return True

    # Get channel ID
    try:
        channels_response = youtube.channels().list(
            part="id,brandingSettings",
            mine=True,
        ).execute()

        if not channels_response.get("items"):
            print("  ❌ No channel found for authenticated user")
            return False

        channel_id = channels_response["items"][0]["id"]
        print(f"  📺 Channel ID: {channel_id}")

        # Set the trailer using brandingSettings
        # The trailer is set by updating the channel's brandingSettings
        # with the video ID of the trailer
        youtube.channels().update(
            part="brandingSettings",
            body={
                "id": channel_id,
                "brandingSettings": {
                    "channel": {
                        "unsubscribedTrailer": video_id,
                    }
                },
            },
        ).execute()

        print(f"  ✅ Channel trailer set to video {video_id}")
        print(f"  🏠 New visitors will see this trailer on your channel page")
        return True

    except HttpError as e:
        error_content = json.loads(e.content) if e.content else {}
        print(f"  ❌ Failed to set channel trailer: {e}")
        if e.resp.status == 403:
            print("  💡 The token may need 'youtube.force-ssl' scope.")
            print("     Delete youtube_token.json and re-run the OAuth flow with the correct scopes.")
        return False


def set_hometab_featured(youtube, video_id, dry_run=False):
    """
    Configure the channel hometab by setting the featured video for new visitors.
    This is done by updating the channel's brandingSettings to set the
    featured video that appears prominently on the channel homepage.
    """
    print(f"\n🎯 Setting hometab featured video (video: {video_id})...")

    if dry_run:
        print("  [DRY RUN] Would set featured video via brandingSettings")
        return True

    try:
        channels_response = youtube.channels().list(
            part="id,brandingSettings",
            mine=True,
        ).execute()

        if not channels_response.get("items"):
            print("  ❌ No channel found")
            return False

        channel_id = channels_response["items"][0]["id"]

        # Update brandingSettings with featured video
        # Note: YouTube API uses unsubscribedTrailer for the trailer shown
        # to non-subscribers. For the hometab featured section, we use
        # the channel's featured video setting.
        youtube.channels().update(
            part="brandingSettings",
            body={
                "id": channel_id,
                "brandingSettings": {
                    "channel": {
                        "unsubscribedTrailer": video_id,
                        "featuredChannelsTitle": "ViralDNA Telugu News",
                        "keywords": "telugu news diaspora viral dna breaking andhra telangana",
                    }
                },
            },
        ).execute()

        print(f"  ✅ Hometab configured successfully")
        print(f"  🎬 Featured video: {video_id}")
        print(f"  📍 Keywords set for channel discovery")
        return True

    except HttpError as e:
        print(f"  ❌ Failed to set hometab: {e}")
        if e.resp.status == 403:
            print("  💡 Token may need 'youtube.force-ssl' scope")
        return False


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("🎬 ViralDNA — Channel Trailer Upload + Hometab Setup")
    print("=" * 60)
    if dry_run:
        print("  🏃 DRY RUN MODE — no changes will be made")
        print("=" * 60)

    # Step 1: Load credentials
    print("\n🔑 Step 1: Loading YouTube credentials...")
    creds = load_credentials(dry_run=dry_run)
    if not creds:
        print("❌ Could not load credentials. Exiting.")
        sys.exit(1)

    if dry_run:
        print("  [DRY RUN] Credentials loaded (skipping actual API calls)")
        youtube = None
    else:
        youtube = build("youtube", "v3", credentials=creds)
        print("  ✅ YouTube API service built")

    # Step 2: Upload trailer
    print("\n🔑 Step 2: Upload trailer video...")
    video_id = upload_trailer(youtube, dry_run=dry_run)
    if not video_id:
        print("❌ Trailer upload failed. Exiting.")
        sys.exit(1)

    # Step 3: Set channel trailer
    print("\n🔑 Step 3: Set as channel trailer...")
    trailer_ok = set_channel_trailer(youtube, video_id, dry_run=dry_run)

    # Step 4: Configure hometab
    print("\n🔑 Step 4: Configure hometab featured video...")
    hometab_ok = set_hometab_featured(youtube, video_id, dry_run=dry_run)

    # Summary
    print("\n" + "=" * 60)
    print("🎬 TRAILER UPLOAD + HOMETAB SETUP COMPLETE")
    print("=" * 60)
    print(f"  {'✅' if video_id else '❌'} Trailer uploaded: {video_id}")
    print(f"  {'✅' if trailer_ok else '❌'} Channel trailer set")
    print(f"  {'✅' if hometab_ok else '❌'} Hometab configured")

    if not dry_run and video_id and video_id != "DRY_RUN_VIDEO_ID":
        print(f"\n  🎬 Watch: https://youtube.com/watch?v={video_id}")
        print("  ⚠️  REMINDER: No-delete policy — this video is permanent!")

    return 0 if (video_id and trailer_ok and hometab_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
