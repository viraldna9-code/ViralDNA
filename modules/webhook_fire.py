#!/usr/bin/env python3
"""
ViralDNA Webhook Helper
Fires webhook calls to the Hermes gateway for pipeline events.
 Usage: python3 modules/webhook_fire.py <event_type> [key=value ...]
 Events: pipeline_done, alert, feed_scan
"""
import sys
import os
import json
import hmac
import hashlib
import urllib.request
import urllib.error

WEBHOOKS = {
    "pipeline_done": {
        "url": "http://localhost:8644/webhooks/vdna-pipeline-done",
        "secret": "AKrnRe2CjT4xOHmKeE_R1ytHpPPxi-fi2pFUuwJbIOU",
    },
    "alert": {
        "url": "http://localhost:8644/webhooks/vdna-alert",
        "secret": "lJjbCKTWiAodCdp7w6aUMCzhLzexA_SMSWsYaNshUzc",
    },
    "feed_scan": {
        "url": "http://localhost:8644/webhooks/vdna-feed-scan",
        "secret": "60EuQxjPz3Gs1dfii6CsZwt-_tbNm64jVZDuHTMIfxQ",
    },
}


def fire(event_type: str, payload: dict):
    """Fire a webhook event to the Hermes gateway."""
    if event_type not in WEBHOOKS:
        print(f"Unknown event type: {event_type}")
        print(f"Available: {', '.join(WEBHOOKS.keys())}")
        sys.exit(1)

    hook = WEBHOOKS[event_type]
    url = hook["url"]
    secret = hook["secret"]
    body = json.dumps(payload).encode("utf-8")

    # Compute HMAC-SHA256 signature (generic format: raw hex, no prefix)
    signature = hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": event_type,
        },
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = resp.read().decode("utf-8")
        print(f"Webhook [{event_type}] fired: {result}")
        return True
    except urllib.error.HTTPError as e:
        print(f"Webhook [{event_type}] HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}")
        return False
    except Exception as e:
        print(f"Webhook [{event_type}] error: {e}")
        return False


def parse_kv_args(args):
    """Parse key=value command line arguments into a dict."""
    result = {}
    for arg in args:
        if "=" in arg:
            k, v = arg.split("=", 1)
            result[k] = v
        else:
            result[arg] = True
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 modules/webhook_fire.py <event_type> [key=value ...]")
        print(f"Events: {', '.join(WEBHOOKS.keys())}")
        sys.exit(1)

    event_type = sys.argv[1]
    payload = parse_kv_args(sys.argv[2:])

    if not payload:
        payload = {"source": "cli", "message": f"Manual {event_type} trigger"}

    success = fire(event_type, payload)
    sys.exit(0 if success else 1)
