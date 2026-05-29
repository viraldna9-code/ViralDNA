#!/usr/bin/env python3
"""
ViralDNA — Send analytics report via Telegram
Usage: python3 send_analytics_report.py --mode daily
       python3 send_analytics_report.py --mode weekly
"""

import os
import sys
import subprocess
import json

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def load_env():
    """Load env vars from ~/.env"""
    env = {}
    try:
        with open(os.path.expanduser("~/.env")) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env

def send_telegram(message, token, chat_id):
    """Send Telegram message via direct API."""
    import urllib.request
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=15)
    result = json.loads(resp.read())
    return result.get("ok", False)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    args = parser.parse_args()

    # Run channel_analytics.py and capture report
    result = subprocess.run(
        [sys.executable, os.path.join(PROJECT_ROOT, "channel_analytics.py"), "--mode", args.mode],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )

    # Extract the report section (from first ━ marker to end)
    output = result.stdout
    if "━" in output:
        idx = output.index("━")
        report = output[idx:].strip()
    else:
        report = output.strip()

    if not report.strip():
        print(f"ERROR: No report generated. stderr: {result.stderr[-500:]}")
        sys.exit(1)

    print(f"Report generated ({len(report)} chars)")

    # Load Telegram creds
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("ERROR: No Telegram credentials in ~/.env")
        print(f"Token: {'present' if token else 'MISSING'}")
        print(f"Chat ID: {chat_id or 'MISSING'}")
        sys.exit(1)

    # Send
    sent = send_telegram(report, token, chat_id)
    print(f"Telegram sent: {sent}")

    if not sent:
        print("ERROR: Failed to send Telegram message")
        sys.exit(1)

    print(f"{args.mode.capitalize()} report delivered.")

if __name__ == "__main__":
    main()
