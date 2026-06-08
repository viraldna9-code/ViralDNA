#!/usr/bin/env python3
"""
ViralDNA Approval Gate (v1.0)
Semi-auto upload: pipeline produces video → Telegram alert → user approves → upload.

Flow:
1. Pipeline finishes → calls ApprovalGate.send_approval_request()
2. Sends Telegram message with thumbnail + title + metadata + approve/reject buttons
3. User replies with /approve VDNA196 or /reject VDNA196
4. ApprovalGate processes command → uploads or moves to REJECTED

State stored in: output/runtime/approval_queue.json
"""
import os
import json
import time
import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# ── Paths ──
DRIVE_BASE = os.environ.get("DRIVE_BASE", "/home/jay/ViralDNA")
APPROVAL_QUEUE_PATH = os.path.join(DRIVE_BASE, "output", "runtime", "approval_queue.json")
APPROVAL_LOG_PATH = os.path.join(DRIVE_BASE, "logs", "approval_log.jsonl")

# ── Telegram ──
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.telegram_alert import send_telegram, send_telegram_photo


def _load_queue() -> dict:
    """Load approval queue from disk."""
    if os.path.exists(APPROVAL_QUEUE_PATH):
        with open(APPROVAL_QUEUE_PATH) as f:
            return json.load(f)
    return {"pending": {}, "approved": {}, "rejected": {}}


def _save_queue(queue: dict):
    """Save approval queue to disk."""
    os.makedirs(os.path.dirname(APPROVAL_QUEUE_PATH), exist_ok=True)
    with open(APPROVAL_QUEUE_PATH, "w") as f:
        json.dump(queue, f, indent=2, default=str)


def _log_approval(topic_id: str, action: str, details: str = ""):
    """Log approval action to JSONL."""
    os.makedirs(os.path.dirname(APPROVAL_LOG_PATH), exist_ok=True)
    entry = {
        "timestamp": datetime.now(IST).isoformat(),
        "topic_id": topic_id,
        "action": action,
        "details": details,
    }
    with open(APPROVAL_LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def send_approval_request(
    topic_id: str,
    topic_title: str,
    topic_source: str,
    topic_url: str,
    topic_score: float,
    video_files: list,
    thumbnail_files: list,
    publish_decision: dict | None = None,
    drive_folder: str = "",
) -> str:
    """
    Send a Telegram approval request for a completed video set.
    Returns the approval token.
    """
    # Generate approval token
    token = hashlib.md5(f"{topic_id}{time.time()}".encode()).hexdigest()[:8]

    # Build message
    lines = [
        f"🎬 <b>ViralDNA — Video Ready for Review</b>",
        f"",
        f"📌 <b>Topic:</b> {topic_title}",
        f"📰 <b>Source:</b> {topic_source}",
        f"⭐ <b>Score:</b> {topic_score}",
        f"🆔 <b>ID:</b> <code>{topic_id}</code>",
    ]

    if publish_decision:
        try:
            pd_summary = publish_decision.get("summary", "N/A") if isinstance(publish_decision, dict) else str(publish_decision)
        except Exception as _e:
            import traceback
            print(f"  [ApprovalGate] publish_decision error: {_e}")
            print(f"  [ApprovalGate] type={type(publish_decision)}, value={repr(publish_decision)}")
            traceback.print_exc()
            pd_summary = str(publish_decision)
        lines.append(f"📋 <b>Plan:</b> {pd_summary}")

    lines.append(f"🎥 <b>Videos:</b> {len(video_files)} file(s)")
    for vf in video_files:
        size_mb = os.path.getsize(vf) / (1024 * 1024) if os.path.exists(vf) else 0
        lines.append(f"  • {os.path.basename(vf)} ({size_mb:.1f} MB)")

    if drive_folder:
        lines.append(f"📁 <b>Drive:</b> {drive_folder}")

    lines.extend([
        f"",
        f"⏰ <b>Reply to approve or reject:</b>",
        f"  ✅ <code>/approve {topic_id}</code>",
        f"  ❌ <code>/reject {topic_id}</code>",
        f"  ℹ️ <code>/info {topic_id}</code> — details",
    ])

    message = "\n".join(lines)

    # Send thumbnail + message
    if thumbnail_files and os.path.exists(thumbnail_files[0]):
        try:
            send_telegram_photo(thumbnail_files[0], caption=message[:1024])
        except Exception as e:
            # Fallback: send text only
            send_telegram(message)
    else:
        send_telegram(message)

    # Save to queue
    queue = _load_queue()
    queue["pending"][topic_id] = {
        "token": token,
        "topic_id": topic_id,
        "topic_title": topic_title,
        "topic_source": topic_source,
        "topic_url": topic_url,
        "topic_score": topic_score,
        "video_files": video_files,
        "thumbnail_files": thumbnail_files,
        "publish_decision": publish_decision,
        "drive_folder": drive_folder,
        "requested_at": datetime.now(IST).isoformat(),
        "status": "pending",
    }
    _save_queue(queue)

    _log_approval(topic_id, "request_sent", f"Videos: {len(video_files)}")
    return token


def process_approval_command(command: str, topic_id: str) -> dict:
    """
    Process an approval command.
    Command format: "/approve VDNA196" or "/reject VDNA196" or "/info VDNA196"
    Returns result dict.
    """
    queue = _load_queue()

    if topic_id not in queue["pending"]:
        # Check if already processed
        if topic_id in queue.get("approved", {}):
            return {"status": "already_approved", "topic_id": topic_id}
        if topic_id in queue.get("rejected", {}):
            return {"status": "already_rejected", "topic_id": topic_id}
        return {"status": "not_found", "topic_id": topic_id}

    item = queue["pending"][topic_id]

    if command == "approve":
        item["status"] = "approved"
        item["approved_at"] = datetime.now(IST).isoformat()
        queue.setdefault("approved", {})[topic_id] = item
        del queue["pending"][topic_id]
        _save_queue(queue)
        _log_approval(topic_id, "approved")
        return {
            "status": "approved",
            "topic_id": topic_id,
            "topic_title": item["topic_title"],
            "video_files": item["video_files"],
            "thumbnail_files": item["thumbnail_files"],
            "publish_decision": item.get("publish_decision"),
        }

    elif command == "reject":
        item["status"] = "rejected"
        item["rejected_at"] = datetime.now(IST).isoformat()
        queue.setdefault("rejected", {})[topic_id] = item
        del queue["pending"][topic_id]
        _save_queue(queue)
        _log_approval(topic_id, "rejected")
        return {
            "status": "rejected",
            "topic_id": topic_id,
            "topic_title": item["topic_title"],
        }

    elif command == "info":
        return {
            "status": "info",
            "topic_id": topic_id,
            "item": item,
        }

    else:
        return {"status": "unknown_command", "command": command}


def get_pending_approvals() -> list:
    """Get list of pending approvals."""
    queue = _load_queue()
    return list(queue["pending"].values())


def get_approval_status(topic_id: str) -> dict:
    """Get approval status for a topic."""
    queue = _load_queue()
    for status in ["pending", "approved", "rejected"]:
        if topic_id in queue.get(status, {}):
            return {"status": status, "item": queue[status][topic_id]}
    return {"status": "not_found"}


if __name__ == "__main__":
    # Test: show pending approvals
    pending = get_pending_approvals()
    print(f"Pending approvals: {len(pending)}")
    for p in pending:
        print(f"  {p['topic_id']}: {p['topic_title'][:60]}")
