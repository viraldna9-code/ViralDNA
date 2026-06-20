#!/usr/bin/env python3
"""
Poll Telegram callback queries — WSL network workaround.
Replaces urllib.request.urlopen with a subprocess call to Windows curl,
then calls the original poll_callback_queries().
"""
import sys
import os
import json
import subprocess
import urllib.request

sys.path.insert(0, '/home/jay/ViralDNA')
os.chdir('/home/jay/ViralDNA')

# Load token from ~/.env
TOKEN = None
with open(os.path.expanduser("~/.env")) as f:
    for line in f:
        line = line.strip()
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            TOKEN = line.split("=", 1)[1].strip().strip("'\"")
            break

if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not found in ~/.env")
    sys.exit(1)

# Also set it in env so poll_callback_queries can find it
os.environ["TELEGRAM_BOT_TOKEN"] = TOKEN

WINDOWS_CURL = "/mnt/c/Windows/System32/curl.exe"
BASE = "https://api.telegram.org/bot" + TOKEN

def windows_curl_open(url, timeout=30, data=None):
    """Drop-in replacement for urllib.request.urlopen using Windows curl."""
    if isinstance(url, urllib.request.Request):
        req = url
        url = req.full_url
        if req.data:
            data = req.data

    cmd = [WINDOWS_CURL, "-s", "--connect-timeout", "10", "--max-time", str(timeout)]
    if data:
        cmd += ["-X", "POST", "-H", "Content-Type: application/json", "-d", data if isinstance(data, str) else data.decode()]

    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)

    if result.returncode != 0:
        raise urllib.error.URLError("curl failed (rc={}): {}".format(result.returncode, result.stderr))

    class FakeResponse:
        def __init__(self, body):
            self._body = body.encode() if isinstance(body, str) else body
            self.status = 200
        def read(self):
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    return FakeResponse(result.stdout)

# Monkey-patch urllib.request.urlopen
urllib.request.urlopen = windows_curl_open

# Now import and run the original function
from modules.approval_gate import poll_callback_queries
results = poll_callback_queries(timeout=15)
if results:
    for r in results:
        print("Handled: {} {} -> {}".format(r['action'], r['topic_id'], r['result']))
else:
    print("No callback queries")
