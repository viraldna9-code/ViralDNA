#!/usr/bin/env python3
"""
ViralDNA — Upload on Approval Script
Reads approved topics from approval_queue.json and uploads them to YouTube.

Usage:
  python3 upload_approved.py              # Upload all approved, not-yet-uploaded topics
  python3 upload_approved.py VDNA196      # Upload specific topic
  python3 upload_approved.py --list       # List pending/approved/rejected
  python3 upload_approved.py --approve VDNA196   # Approve + upload
  python3 upload_approved.py --reject VDNA196    # Reject
"""
import os
import sys
import json

# Add project root to path so `import config` works when run from any directory
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_MODULES_DIR = os.path.join(_PROJECT_ROOT, "modules")
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
DRIVE_BASE = os.environ.get("DRIVE_BASE", "/home/jay/ViralDNA")
QUEUE_PATH = os.path.join(DRIVE_BASE, "output", "runtime", "approval_queue.json")


def load_queue():
    if os.path.exists(QUEUE_PATH):
        with open(QUEUE_PATH) as f:
            return json.load(f)
    return {"pending": {}, "approved": {}, "rejected": {}}


def save_queue(queue):
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    with open(QUEUE_PATH, "w") as f:
        json.dump(queue, f, indent=2, default=str)


def upload_topic(topic_id: str, item: dict, schedule_slot: str | None = None) -> dict:
    """Upload a single approved topic to YouTube.
    schedule_slot: 'morning' (main=09:00, shorts=09:30) or 'evening' (main=19:00, shorts=19:30) IST
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    import config
    from youtube_uploader import YouTubeUploader

    video_files = item.get("video_files", [])
    thumbnail_files = item.get("thumbnail_files", [])

    if not video_files:
        return {"status": "error", "message": "No video files found"}

    # Verify files exist
    for vf in video_files:
        if not os.path.exists(vf):
            return {"status": "error", "message": f"Video file not found: {vf}"}

    # Build YouTube service with auto-refresh
    token_path = os.path.join(config.DRIVE["CREDENTIALS"], "youtube_token.json")
    YOUTUBE_SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]

    def _build_fresh_service():
        """Build YouTube service, refreshing token if expired or about to expire."""
        creds = Credentials.from_authorized_user_file(token_path, YOUTUBE_SCOPES)
        if creds and creds.refresh_token:
            # Refresh if expired OR if token expires within 10 minutes
            from datetime import datetime, timezone, timedelta
            needs_refresh = creds.expired
            if not needs_refresh and hasattr(creds, 'expiry') and creds.expiry:
                from datetime import datetime, timezone, timedelta
                now_utc = datetime.now(timezone.utc)
                # Handle both offset-aware and offset-naive expiry
                expiry = creds.expiry
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                needs_refresh = expiry < now_utc + timedelta(minutes=10)
            if needs_refresh:
                print("  🔄 Refreshing YouTube token...")
                creds.refresh(Request())
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
                print("  ✅ Token refreshed")
        return build("youtube", "v3", credentials=creds)

    service = _build_fresh_service()

    # Configure schedule based on slot
    schedule_config = dict(config.YOUTUBE_UPLOAD_CONFIG)
    if schedule_slot == "morning":
        schedule_config["main_publish_time_ist"] = "09:00"
        schedule_config["shorts_publish_time_ist"] = "09:30"
    elif schedule_slot == "evening":
        schedule_config["main_publish_time_ist"] = "19:00"
        schedule_config["shorts_publish_time_ist"] = "19:30"

    uploader = YouTubeUploader(service, schedule_config)

    # Build selected_topic from item
    selected_topic = {
        "id": topic_id,
        "title": item.get("topic_title", "Unknown"),
        "source": item.get("topic_source", "Unknown"),
        "url": item.get("topic_url", ""),
        "score": item.get("topic_score", 0),
    }

    # Upload
    publish_decision = item.get("publish_decision")

    # The YouTubeUploader expects generic filenames (production_main.mp4, production_branded.jpg)
    # but our pipeline uses topic-slug-based names. Create symlinks with expected names.
    import tempfile, shutil
    videos_dir = os.path.dirname(video_files[0])
    thumbnails_dir = os.path.dirname(thumbnail_files[0]) if thumbnail_files else ""

    # Create symlinks: production_main.mp4 -> actual Main video
    main_video = next((vf for vf in video_files if "_Main.mp4" in os.path.basename(vf)), video_files[0])
    short_videos = sorted([vf for vf in video_files if "_Short" in os.path.basename(vf)])

    # Remove stale symlinks from previous uploads
    for stale in ["production_main.mp4", "production_short_1.mp4", "production_short_2.mp4", "production_short_3.mp4"]:
        stale_path = os.path.join(videos_dir, stale)
        if os.path.islink(stale_path):
            os.remove(stale_path)

    prod_main_link = os.path.join(videos_dir, "production_main.mp4")
    os.symlink(os.path.abspath(main_video), prod_main_link)

    # Symlink shorts: production_short_1.mp4, production_short_2.mp4, ...
    for i, sv in enumerate(short_videos, 1):
        link_path = os.path.join(videos_dir, f"production_short_{i}.mp4")
        os.symlink(os.path.abspath(sv), link_path)

    # Symlink thumbnail: production_branded.jpg -> best branded thumbnail
    if thumbnail_files:
        # Prefer branded_v3 > branded_v2 > branded
        def _brand_priority(p):
            b = os.path.basename(p)
            if "_branded_v3" in b: return 0
            if "_branded_v2" in b: return 1
            if "_branded." in b: return 2
            return 3
        best_thumb = min(thumbnail_files, key=_brand_priority)
        prod_thumb_link = os.path.join(thumbnails_dir, "production_branded.jpg")
        if os.path.islink(prod_thumb_link):
            os.remove(prod_thumb_link)
        os.symlink(os.path.abspath(best_thumb), prod_thumb_link)

    # Build a minimal script_payload for the uploader
    # The uploader needs main_title_variants (non-empty) to proceed
    from types import SimpleNamespace
    topic_title_short = selected_topic["title"][:100] if selected_topic.get("title") else "BREAKING NEWS"
    # Strip source names (e.g., " - The Hindu", " | NDTV")
    import re as _re
    topic_title_short = _re.sub(r'\s*[-|]\s*(The Hindu|NDTV|Times of India|India Today|Firstpost|Scroll\.in|The Wire|News18|CNBC|BBC|CNN|Al Jazeera|Reuters|AP|AFP|PTI|ANI|Google News|RSS).*$', '', topic_title_short, flags=_re.IGNORECASE).strip()
    short_title = topic_title_short[:60] + " #Shorts"
    sp_kwargs = dict(
        main_clean=selected_topic.get("title", ""),
        main_duration=0,
        main_title_variants=[{"title": topic_title_short, "description": "A detailed news report from ViralDNA."}],
    )
    # Convert publish_decision dict to SimpleNamespace for attribute access
    if isinstance(publish_decision, dict):
        publish_decision = SimpleNamespace(**publish_decision)

    # Add per-short attributes expected by uploader
    num_shorts = getattr(publish_decision, "num_shorts", 1) if publish_decision else 1
    for i in range(1, num_shorts + 1):
        short_key = f"short_{i}"
        sp_kwargs[f"{short_key}_title_variants"] = [{"title": short_title}]
        sp_kwargs[f"{short_key}_raw"] = selected_topic.get("title", "")
        sp_kwargs[f"{short_key}_duration"] = 0
    script_payload = SimpleNamespace(**sp_kwargs)

    # Convert publish_decision dict to SimpleNamespace for attribute access
    if isinstance(publish_decision, dict):
        publish_decision = SimpleNamespace(**publish_decision)

    try:
        results = uploader.upload_production_slot(
            selected_topic,
            videos_dir,
            thumbnails_dir,
            script_payload=script_payload,
            publish_decision=publish_decision,
        )
        return {"status": "success", "results": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_status():
    """List all topics by status."""
    queue = load_queue()

    print("\n=== PENDING APPROVAL ===")
    if not queue.get("pending"):
        print("  (none)")
    for tid, item in queue.get("pending", {}).items():
        print(f"  {tid}: {item.get('topic_title', 'Unknown')[:60]}")
        print(f"    Videos: {len(item.get('video_files', []))} | Requested: {item.get('requested_at', 'N/A')}")

    print("\n=== APPROVED (not yet uploaded) ===")
    if not queue.get("approved"):
        print("  (none)")
    for tid, item in queue.get("approved", {}).items():
        print(f"  {tid}: {item.get('topic_title', 'Unknown')[:60]}")
        print(f"    Approved: {item.get('approved_at', 'N/A')}")

    print("\n=== REJECTED ===")
    if not queue.get("rejected"):
        print("  (none)")
    for tid, item in queue.get("rejected", {}).items():
        print(f"  {tid}: {item.get('topic_title', 'Unknown')[:60]}")
        print(f"    Rejected: {item.get('rejected_at', 'N/A')}")


def main():
    parser = argparse.ArgumentParser(description="ViralDNA Upload on Approval")
    parser.add_argument("topic_id", nargs="?", help="Topic ID to upload")
    parser.add_argument("--list", action="store_true", help="List all topics by status")
    parser.add_argument("--approve", metavar="ID", help="Approve a pending topic")
    parser.add_argument("--reject", metavar="ID", help="Reject a pending topic")
    parser.add_argument("--upload-all", action="store_true", help="Upload all approved topics")
    parser.add_argument("--schedule", metavar="SLOT", choices=["morning", "evening"],
                        help="Set publish schedule: morning (main=9AM, shorts=9:30AM) or evening (main=7PM, shorts=7:30PM)")
    args = parser.parse_args()

    if args.list:
        list_status()
        return

    queue = load_queue()

    if args.approve:
        topic_id = args.approve
        if topic_id not in queue.get("pending", {}):
            print(f"❌ {topic_id} not found in pending queue")
            return
        item = queue["pending"][topic_id]
        item["status"] = "approved"
        item["approved_at"] = datetime.now(IST).isoformat()
        queue.setdefault("approved", {})[topic_id] = item
        del queue["pending"][topic_id]
        save_queue(queue)
        print(f"✅ Approved: {topic_id} — {item.get('topic_title', '')[:60]}")
        print(f"   Run: python3 upload_approved.py {topic_id}")
        return

    if args.reject:
        topic_id = args.reject
        if topic_id not in queue.get("pending", {}):
            print(f"❌ {topic_id} not found in pending queue")
            return
        item = queue["pending"][topic_id]
        item["status"] = "rejected"
        item["rejected_at"] = datetime.now(IST).isoformat()
        queue.setdefault("rejected", {})[topic_id] = item
        del queue["pending"][topic_id]
        save_queue(queue)
        print(f"❌ Rejected: {topic_id} — {item.get('topic_title', '')[:60]}")
        return

    # Upload specific topic or all approved
    if args.topic_id:
        topic_id = args.topic_id
        if topic_id in queue.get("approved", {}):
            item = queue["approved"][topic_id]
        elif topic_id in queue.get("pending", {}):
            print(f"⚠️ {topic_id} is still pending approval. Use --approve first.")
            return
        else:
            print(f"❌ {topic_id} not found in queue")
            return

        print(f"🚀 Uploading {topic_id}...")
        result = upload_topic(topic_id, item, schedule_slot=args.schedule)
        if result["status"] == "success":
            print(f"✅ Upload complete: {topic_id}")
            # Move to uploaded
            item["uploaded_at"] = datetime.now(IST).isoformat()
            item["upload_results"] = result.get("results", {})
            queue.setdefault("uploaded", {})[topic_id] = item
            if topic_id in queue.get("approved", {}):
                del queue["approved"][topic_id]
            save_queue(queue)
        else:
            print(f"❌ Upload failed: {result.get('message', 'Unknown error')}")
    elif args.upload_all:
        approved = queue.get("approved", {})
        if not approved:
            print("No approved topics to upload")
            return
        failed = []
        for topic_id, item in approved.items():
            print(f"\n🚀 Uploading {topic_id}...")
            result = upload_topic(topic_id, item, schedule_slot=args.schedule)
            if result["status"] == "success":
                print(f"✅ Upload complete: {topic_id}")
                item["uploaded_at"] = datetime.now(IST).isoformat()
                item["upload_results"] = result.get("results", {})
                queue.setdefault("uploaded", {})[topic_id] = item
            else:
                print(f"❌ Upload failed: {result.get('message', 'Unknown error')}")
                failed.append(topic_id)
        # Only clear successfully uploaded items from approved
        for topic_id in list(approved.keys()):
            if topic_id not in failed:
                del queue["approved"][topic_id]
        save_queue(queue)
        if failed:
            print(f"\n⚠️ {len(failed)} upload(s) failed, kept in approved queue for retry: {', '.join(failed)}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
