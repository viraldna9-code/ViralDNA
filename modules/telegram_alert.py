#!/usr/bin/env python3
"""
ViralDNA Telegram Alert Module
Stage 1+2: Viral news detection + Telegram notification
Uses direct Telegram API (bypasses Hermes gateway platform layer)
"""
import os
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

# Load credentials from home .env
load_dotenv(os.path.expanduser("~/.env"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def _telegram_request(req, max_retries=3, base_delay=2):
    """Execute a urllib request with retry on transient errors (429, timeout, 5xx)."""
    import time
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            return resp
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # Rate limited — wait with exponential backoff
                retry_after = e.headers.get("Retry-After") if e.headers else None
                delay = int(retry_after) if retry_after else base_delay * (2 ** attempt)
                time.sleep(min(delay, 60))
                last_err = e
                continue
            if e.code >= 500:
                time.sleep(base_delay * (2 ** attempt))
                last_err = e
                continue
            raise  # 4xx errors (except 429) are not retriable
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
                last_err = e
                continue
            raise
    raise last_err


def send_telegram(message: str, parse_mode: str = "HTML") -> dict:
    """Send a message to the configured Telegram chat."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Telegram credentials not configured")
    url = f"{BASE_URL}/sendMessage"
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    resp = _telegram_request(req)
    return json.loads(resp.read())


def send_telegram_photo(photo_path: str, caption: str = "") -> dict:
    """Send a photo to the configured Telegram chat."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Telegram credentials not configured")
    if not os.path.exists(photo_path):
        raise FileNotFoundError(f"Thumbnail not found: {photo_path}")
    url = f"{BASE_URL}/sendPhoto"
    with open(photo_path, "rb") as f:
        photo_data = f.read()
    boundary = b"----ViralDNA"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        + TELEGRAM_CHAT_ID.encode() + b"\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="caption"\r\n\r\n'
        + caption.encode() + b"\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="photo"; filename="thumb.jpg"\r\n'
        b"Content-Type: image/jpeg\r\n\r\n"
        + photo_data + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
    )
    resp = _telegram_request(req)
    return json.loads(resp.read())


if __name__ == "__main__":
    # Test
    result = send_telegram("🔔 ViralDNA alert system — Telegram module test OK")
    print("Telegram test:", result["ok"])
