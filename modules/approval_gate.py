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
    """Save approval queue to disk atomically (write temp then rename)."""
    os.makedirs(os.path.dirname(APPROVAL_QUEUE_PATH), exist_ok=True)
    tmp_path = APPROVAL_QUEUE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(queue, f, indent=2, default=str)
    os.replace(tmp_path, APPROVAL_QUEUE_PATH)


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


def _cleanup_stale_queue_entries(queue: dict) -> dict:
    """Remove queue entries whose video files no longer exist on disk.
    Prevents stale entries from previous runs accumulating in the queue."""
    for status in ("pending", "approved", "rejected"):
        stale_ids = []
        for tid, item in queue.get(status, {}).items():
            video_files = item.get("video_files", [])
            if video_files and not any(os.path.exists(vf) for vf in video_files):
                stale_ids.append(tid)
        for tid in stale_ids:
            del queue[status][tid]
    return queue


def _validate_video_files(video_files: list) -> list:
    """Filter video_files to only those that exist on disk. Returns valid files."""
    return [vf for vf in video_files if os.path.exists(vf)]


def send_approval_request(
    topic_id: str,
    topic_title: str,
    topic_source: str,
    topic_url: str,
    topic_score: float,
    video_files: list,
    thumbnail_files: list,
    publish_decision: dict | None = None,
    scene_visuals: list | None = None,
) -> str:
    """
    Send a Telegram approval request for a completed video set.
    Returns the approval token.
    """
    # Generate approval token
    import sys
    print(f"  [ApprovalGate] ENTRY: publish_decision type={type(publish_decision)}, repr={repr(publish_decision)[:150]}", file=sys.stderr, flush=True)
    token = hashlib.md5(f"{topic_id}{time.time()}".encode()).hexdigest()[:8]

    # ── Validate video files exist on disk ──
    valid_videos = _validate_video_files(video_files)
    if not valid_videos:
        print(f"  [ApprovalGate] ⚠️ No valid video files for {topic_id}. Skipping queue entry.", file=sys.stderr, flush=True)
        return token  # Return token but don't queue — prevents ghost entries
    if len(valid_videos) < len(video_files):
        print(f"  [ApprovalGate] ⚠️ {len(video_files) - len(valid_videos)} missing video(s) for {topic_id}. Using {len(valid_videos)} valid.", file=sys.stderr, flush=True)

    # ── Gather video metadata (ffprobe) ──
    video_meta = []
    for vf in valid_videos:
        vf_name = os.path.basename(vf)
        vf_size = os.path.getsize(vf) // 1024 if os.path.exists(vf) else 0
        try:
            import subprocess as _sp
            probe = _sp.run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', vf], capture_output=True, text=True, timeout=10)
            info = json.loads(probe.stdout)
            dur = float(info.get('format', {}).get('duration', 0))
            vs = [s for s in info.get('streams', []) if s['codec_type'] == 'video']
            res = f"{vs[0].get('width')}x{vs[0].get('height')}" if vs else '?'
            subs = [s for s in info.get('streams', []) if s['codec_type'] == 'subtitle']
            sub_tag = ' subs' if subs else ''
            video_meta.append(f"  • {vf_name[:38]} | {dur:.0f}s | {res} | {vf_size}KB{sub_tag}")
        except Exception:
            video_meta.append(f"  • {vf_name[:38]} | {vf_size}KB")

    # Build message — short and scannable
    lines = [
        f"🎬 <b>ViralDNA — Video Ready</b>",
        f"",
        f"⏰ <b>Reply:</b>",
        f"  ✅ <code>/approve {topic_id}</code>",
        f"  ❌ <code>/reject {topic_id}</code>",
        f"",
        f"📌 <b>Topic:</b> {topic_title}",
        f"⭐ <b>Score:</b> {topic_score}  |  🆔 <b>ID:</b> <code>{topic_id}</code>",
    ]

    # Add video metadata
    if video_meta:
        lines.append("")
        lines.append(f"📹 <b>Videos ({len(video_meta)}):</b>")
        lines.extend(video_meta)

    # Add source URL
    if topic_url:
        lines.append("")
        lines.append(f"🔗 <b>Source:</b> {topic_url}")
    elif topic_source:
        lines.append("")
        lines.append(f"📰 <b>Feed:</b> {topic_source}")

    # Add publish schedule info if available (v85.1)
    if publish_decision:
        slot = publish_decision.get("slot", "")
        main_time = publish_decision.get("main_publish_time_ist", "")
        shorts_time = publish_decision.get("shorts_publish_time_ist", "")
        if slot:
            lines.append(f"")
            lines.append(f"📅 <b>Schedule:</b> {slot.upper()}")
            if main_time:
                lines.append(f"  🎥 Main: {main_time} IST")
            if shorts_time:
                lines.append(f"  📱 Shorts: {shorts_time} IST")

    message = "\n".join(lines)

    # Build inline keyboard with Approve/Reject buttons
    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"approve:{topic_id}"},
                {"text": "❌ Reject", "callback_data": f"reject:{topic_id}"},
            ]
        ]
    }

    # Send thumbnail + message (caption max 1024 chars for photo)
    # Commands are at the top, so they survive truncation
    import sys
    print(f"  [ApprovalGate] Photo check: thumbnail_files={thumbnail_files}, exists={os.path.exists(thumbnail_files[0]) if thumbnail_files else 'N/A'}", file=sys.stderr, flush=True)
    sent_photo = False
    if thumbnail_files and os.path.exists(thumbnail_files[0]):
        try:
            result = send_telegram_photo(thumbnail_files[0], caption=message[:1024], reply_markup=inline_keyboard)
            sent_photo = result.get("ok", False)
            print(f"  [ApprovalGate] Photo sent: {sent_photo}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"  [ApprovalGate] Photo FAILED: {e}", file=sys.stderr, flush=True)
            # Fallback: send text only (Telegram text limit = 4096)
            send_telegram(message[:4000], reply_markup=inline_keyboard)
    else:
        print(f"  [ApprovalGate] No thumbnail, sending text only", file=sys.stderr, flush=True)
        send_telegram(message[:4000], reply_markup=inline_keyboard)

    # Send all scene visuals (viz_*.jpg) as individual photos
    _scene_visuals = [v for v in (scene_visuals or []) if os.path.exists(v)]
    if _scene_visuals:
        print(f"  [ApprovalGate] Sending {len(_scene_visuals)} scene visual(s)...", file=sys.stderr, flush=True)
        for _i, _viz in enumerate(_scene_visuals):
            try:
                _viz_name = os.path.basename(_viz)
                send_telegram_photo(_viz, caption=f"📸 Scene {_i + 1}/{len(_scene_visuals)}: {_viz_name}")
                print(f"  [ApprovalGate] Scene visual {_i + 1} sent: {_viz_name}", file=sys.stderr, flush=True)
            except Exception as _viz_err:
                print(f"  [ApprovalGate] Scene visual {_i + 1} FAILED: {_viz_err}", file=sys.stderr, flush=True)

    # Save to queue — cleanup stale entries first, then add with validated videos
    queue = _load_queue()
    queue = _cleanup_stale_queue_entries(queue)
    queue["pending"][topic_id] = {
        "token": token,
        "topic_id": topic_id,
        "topic_title": topic_title,
        "topic_source": topic_source,
        "topic_url": topic_url,
        "topic_score": topic_score,
        "video_files": valid_videos,
        "thumbnail_files": thumbnail_files,
        "scene_visuals": _scene_visuals,
        "publish_decision": publish_decision,
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

        # Trigger upload via upload_approved.py (pass topic_id only — it reads from approved queue)
        import subprocess
        try:
            result = subprocess.run(
                ["/home/jay/venv/bin/python3", "/home/jay/ViralDNA/upload_approved.py", topic_id],
                capture_output=True, text=True, timeout=600
            )
            _log_approval(topic_id, "upload_triggered", f"exit={result.returncode} stdout={result.stdout[-200:]}")
        except Exception as e:
            _log_approval(topic_id, "upload_failed", str(e))

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


def poll_callback_queries(timeout: int = 30) -> list:
    """
    Poll Telegram for callback queries from inline keyboard buttons.
    Returns list of handled callbacks.
    Requires TELEGRAM_BOT_TOKEN to be set in environment.
    """
    import urllib.request as _ur
    import json as _json
    import os as _os
    import time as _time

    token = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return []

    base = f"https://api.telegram.org/bot{token}"
    handled = []
    offset = None

    # Get updates with short polling — listen for both callback queries AND text commands
    url = f"{base}/getUpdates?timeout={timeout}&allowed_updates=[\"callback_query\",\"message\"]"
    if offset:
        url += f"&offset={offset}"

    resp_data = None
    for attempt in range(10):
        try:
            resp = _ur.urlopen(url, timeout=timeout + 5)
            resp_data = resp.read()
            break
        except Exception as e:
            if "409" in str(e):
                _time.sleep(0.5)
                continue
            else:
                print(f"  [ApprovalGate] Callback poll error: {e}")
                return []

    if resp_data is None:
        print("  [ApprovalGate] Callback poll error: Persistent HTTP 409 Conflict")
        return []

    try:
        data = _json.loads(resp_data)
    except Exception as e:
        print(f"  [ApprovalGate] JSON parse error: {e}")
        return []

    for update in data.get("result", []):
        update_id = update.get("update_id")

        # Handle inline keyboard button clicks (callback_query)
        cq = update.get("callback_query", {})
        if cq:
            callback_id = cq.get("id")
            callback_data = cq.get("data", "")
            chat_id = cq.get("message", {}).get("chat", {}).get("id")

            if ":" in callback_data:
                action, topic_id = callback_data.split(":", 1)
                result = process_approval_command(action, topic_id)

                if result["status"] == "approved":
                    msg = f"✅ <b>{topic_id}</b> APPROVED — uploading to YouTube..."
                elif result["status"] == "rejected":
                    msg = f"❌ <b>{topic_id}</b> REJECTED"
                elif result["status"] == "already_approved":
                    msg = f"⚠️ <b>{topic_id}</b> already approved"
                elif result["status"] == "already_rejected":
                    msg = f"⚠️ <b>{topic_id}</b> already rejected"
                else:
                    msg = f"⚠️ <b>{topic_id}</b> {result['status']}"

                try:
                    payload = _json.dumps({
                        "chat_id": chat_id,
                        "text": msg,
                        "parse_mode": "HTML",
                    }).encode()
                    req = _ur.Request(f"{base}/sendMessage", data=payload,
                                     headers={"Content-Type": "application/json"})
                    _ur.urlopen(req, timeout=10)
                except Exception:
                    pass

                # Answer the callback query (removes loading state from button)
                try:
                    payload = _json.dumps({"callback_query_id": callback_id}).encode()
                    req = _ur.Request(f"{base}/answerCallbackQuery", data=payload,
                                     headers={"Content-Type": "application/json"})
                    _ur.urlopen(req, timeout=10)
                except Exception:
                    pass

                handled.append({"type": "callback", "action": action, "topic_id": topic_id, "result": result["status"]})
                continue

        # Handle text commands: /approve VDNA219 or /reject VDNA219
        msg_obj = update.get("message", {})
        text = msg_obj.get("text", "").strip()
        chat_id = msg_obj.get("chat", {}).get("id")

        if text.startswith("/approve ") or text.startswith("/reject "):
            parts = text.split(maxsplit=1)
            if len(parts) == 2:
                action = parts[0][1:]  # strip leading "/"
                topic_id = parts[1].strip()
                result = process_approval_command(action, topic_id)

                if result["status"] == "approved":
                    reply = f"✅ <b>{topic_id}</b> APPROVED — uploading to YouTube..."
                elif result["status"] == "rejected":
                    reply = f"❌ <b>{topic_id}</b> REJECTED"
                elif result["status"] == "already_approved":
                    reply = f"⚠️ <b>{topic_id}</b> already approved"
                elif result["status"] == "already_rejected":
                    reply = f"⚠️ <b>{topic_id}</b> already rejected"
                elif result["status"] == "not_found":
                    reply = f"⚠️ <b>{topic_id}</b> not found in pending queue"
                else:
                    reply = f"⚠️ <b>{topic_id}</b> {result['status']}"

                try:
                    payload = _json.dumps({
                        "chat_id": chat_id,
                        "text": reply,
                        "parse_mode": "HTML",
                    }).encode()
                    req = _ur.Request(f"{base}/sendMessage", data=payload,
                                     headers={"Content-Type": "application/json"})
                    _ur.urlopen(req, timeout=10)
                except Exception:
                    pass
                handled.append({"type": "command", "action": action, "topic_id": topic_id, "result": result["status"]})

    return handled


if __name__ == "__main__":
    # Test: show pending approvals
    pending = get_pending_approvals()
    print(f"Pending approvals: {len(pending)}")
    for p in pending:
        print(f"  {p['topic_id']}: {p['topic_title'][:60]}")
