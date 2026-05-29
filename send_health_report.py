#!/usr/bin/env python3
"""
ViralDNA Channel Health — Action Taker
Reads feedback.md, sends structured Telegram summary:
what Hermes fixed, what needs Jay's manual action, what's pending.
"""

import json, os, re, sys, urllib.request
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
FEEDBACK_FILE = os.path.join(PROJECT_ROOT, "analytics", "feedback.md")
ACTION_LOG = os.path.join(PROJECT_ROOT, "analytics", "actions_taken.json")


def load_action_log():
    if os.path.exists(ACTION_LOG):
        with open(ACTION_LOG) as f:
            return json.load(f)
    return {"fixed": [], "manual_needed": [], "pending": []}


def save_action_log(log):
    os.makedirs(os.path.join(PROJECT_ROOT, "analytics"), exist_ok=True)
    with open(ACTION_LOG, "w") as f:
        json.dump(log, f, indent=2)


def parse_feedback():
    """Parse feedback.md into structured sections."""
    if not os.path.exists(FEEDBACK_FILE):
        return None

    with open(FEEDBACK_FILE) as f:
        content = f.read()

    result = {
        "header": "",
        "channel_line": "",
        "monetization_line": "",
        "critical": [],
        "high": [],
        "medium": [],
        "low": [],
        "info": [],
    }

    current_section = None
    for line in content.split("\n"):
        line = line.rstrip()
        if line.startswith("# ViralDNA"):
            result["header"] = line
        elif "Views:" in line and "Subscribers:" in line:
            result["channel_line"] = line.strip("- ")
        elif "Monetization:" in line:
            result["monetization_line"] = line.strip("- ")
        elif "🔴 CRITICAL" in line:
            current_section = "critical"
        elif "🟠 HIGH" in line:
            current_section = "high"
        elif "🟡 MEDIUM" in line:
            current_section = "medium"
        elif "🔵 LOW" in line:
            current_section = "low"
        elif "ℹ️ INFO" in line:
            current_section = "info"
        elif line.startswith("- **[") and current_section:
            # Parse: - **[CATEGORY]** message \n   → action
            m = re.match(r"- \*\*\[(\w+)\]\*\* (.+)", line)
            if m:
                cat, msg = m.group(1), m.group(2).strip()
                # Look for action on next line
                result[current_section].append({"category": cat, "issue": msg, "action": ""})

    # Second pass: extract actions (lines starting with → or indented action)
    current_section = None
    item_idx = {}
    for line in content.split("\n"):
        line = line.rstrip()
        if "🔴 CRITICAL" in line:
            current_section = "critical"; item_idx[current_section] = 0
        elif "🟠 HIGH" in line:
            current_section = "high"; item_idx[current_section] = 0
        elif "🟡 MEDIUM" in line:
            current_section = "medium"; item_idx[current_section] = 0
        elif "🔵 LOW" in line:
            current_section = "low"; item_idx[current_section] = 0
        elif "ℹ️ INFO" in line:
            current_section = "info"; item_idx[current_section]  = 0
        elif line.strip().startswith("→ ") and current_section:
            idx = item_idx.get(current_section, 0)
            if idx < len(result[current_section]):
                result[current_section][idx]["action"] = line.strip().lstrip("→ ").strip()
            item_idx[current_section] = idx + 1

    return result


def format_telegram_message(fb, action_log):
    """Format a clear, actionable Telegram message."""
    now = datetime.now(IST)

    msg = f"The ViralDNA — Channel Health Check\n"
    msg += f"{now.strftime('%A, %d %b %Y — %H:%M IST')}\n\n"

    # Channel stats
    if fb["channel_line"]:
        msg += f"{fb['channel_line']}\n"
    if fb["monetization_line"]:
        msg += f"{fb['monetization_line']}\n"

    msg += "\n"

    # ── AUTO-FIXED CHANNEL HEALTH ────────────────────────────────
    if action_log.get("fixed"):
        msg += "AUTO-FIXED THIS SESSION:\n"
        for item in action_log["fixed"]:
            msg += f"  FIXED: {item}\n"
        msg += "\n"

    # ── CRITICAL / HIGH — NEED ACTION ─────────────────────────────
    urgent = fb.get("critical", []) + fb.get("high", [])
    if urgent:
        msg += "NEED YOUR ACTION:\n"
        for i, item in enumerate(urgent, 1):
            sev = "CRITICAL" if item in fb.get("critical", []) else "HIGH"
            msg += f"  {i}. [{item['category'].upper()}] {item['issue']}\n"
            if item.get("action"):
                msg += f"     DO THIS: {item['action']}\n"

    # ── MEDIUM — THIS WEEK ──────────────────────────────────────
    if fb.get("medium"):
        msg += "\nTHIS WEEK:\n"
        for i, item in enumerate(fb["medium"], 1):
            msg += f"  {i}. [{item['category'].upper()}] {item['issue']}\n"
            if item.get("action"):
                msg += f"     FIX: {item['action']}\n"

    # ── GOOD NEWS / INFO ─────────────────────────────────────────
    if fb.get("info"):
        msg += "\nSTATUS:\n"
        for item in fb["info"][:3]:  # Top 3 info items
            msg += f"  • [{item['category'].upper()}] {item['issue']}\n"

    # Manual items from log
    if action_log.get("manual_needed"):
        msg += "\nMANUAL ACTION NEEDED (cant fix via API):\n"
        for item in action_log["manual_needed"]:
            msg += f"  TODO: {item}\n"

    msg += "\nReply 'fixed' after doing manual items so I update the list."

    return msg


def send_telegram(message):
    env = {}
    try:
        with open(os.path.expanduser("~/.env")) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass

    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("Telegram creds missing")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({
        "chat_id": chat_id, "text": message,
        "parse_mode": "HTML", "disable_web_page_preview": True
    }).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}),
            timeout=15
        )
        return True
    except Exception as e:
        print(f"Telegram send error: {e}")
        return False


def main():
    fb = parse_feedback()
    if not fb:
        print("No feedback.md found")
        return

    action_log = load_action_log()
    msg = format_telegram_message(fb, action_log)

    print(f"Message ({len(msg)} chars):")
    print(msg)
    print()

    sent = send_telegram(msg)
    if sent:
        print("Telegram sent!")
    else:
        print("Telegram send FAILED")


if __name__ == "__main__":
    main()
