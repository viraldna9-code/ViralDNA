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


def upload_topic(topic_id: str, item: dict) -> dict:
    """Upload a single approved topic to YouTube."""
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

    # Build YouTube service
    token_path = os.path.join(config.DRIVE["CREDENTIALS"], "youtube_token.json")
    YOUTUBE_SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]
    creds = Credentials.from_authorized_user_file(token_path, YOUTUBE_SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    service = build("youtube", "v3", credentials=creds)
    uploader = YouTubeUploader(service, config)

    # Build selected_topic from item
    selected_topic = {
        "id": topic_id,
        "title": item.get("topic_title", "Unknown"),
        "source": item.get("topic_source", "Unknown"),
        "url": item.get("topic_url", ""),
        "score": item.get("topic_score", 0),
    }

    # Upload
    try:
        results = uploader.upload_production_slot(
            selected_topic,
            os.path.dirname(video_files[0]),
            os.path.dirname(thumbnail_files[0]) if thumbnail_files else "",
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
        result = upload_topic(topic_id, item)
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
            result = upload_topic(topic_id, item)
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
