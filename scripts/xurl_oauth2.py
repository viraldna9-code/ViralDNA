#!/usr/bin/env python3
"""
X OAuth2 helper: generates the auth URL and waits for you to complete it manually.
Run this, copy the URL to your browser, authorize, then paste the callback code back.
"""
import urllib.parse
import hashlib
import base64
import secrets
import http.server
import json

CLIENT_ID = "aEdIajdPZ3dOeXE5bWtLLUw5N3A6MTpjaQ"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = "tweet.read tweet.write users.read offline.access"
AUTH_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"

# PKCE
code_verifier = secrets.token_urlsafe(64)[:128]
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b"=").decode()

state = secrets.token_urlsafe(16)

params = {
    "response_type": "code",
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPES,
    "state": state,
    "code_challenge": code_challenge,
    "code_challenge_method": "S256",
}
auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

print("=" * 60)
print("Copy this URL into your browser and authorize:")
print("=" * 60)
print()
print(auth_url)
print()
print("=" * 60)
print("After authorizing, you'll be redirected to localhost:8080.")
print("The callback will be captured automatically.")
print("=" * 60)

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if "code" in query:
            CallbackHandler.auth_code = query["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authorization code received!</h1><p>You can close this tab and return to the terminal.</p>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h1>Error: No code received</h1>")

    def log_message(self, format, *args):
        pass  # Suppress log output

server = http.server.HTTPServer(("127.0.0.1", 8080), CallbackHandler)
print("\nWaiting for callback on port 8080...")

import time
start = time.time()
while CallbackHandler.auth_code is None and time.time() - start < 180:
    server.timeout = 3
    server.handle_request()

if CallbackHandler.auth_code is None:
    print("Timed out waiting for authorization.")
    exit(1)

auth_code = CallbackHandler.auth_code
print(f"\nCode received! Exchanging for tokens...")

# Exchange code for tokens
import urllib.request, urllib.error, ssl

# Read client secret for token exchange
with open("/home/jay/.xurl") as f:
    content = f.read()

# We need the client secret - prompt for it
print("\nTo complete token exchange, I need the Client Secret.")
print("Paste it here and press Enter:")
client_secret = input().strip()

auth_header = base64.b64encode(f"{CLIENT_ID}:{client_secret}".encode()).decode()

data = urllib.parse.urlencode({
    "grant_type": "authorization_code",
    "code": auth_code,
    "redirect_uri": REDIRECT_URI,
    "code_verifier": code_verifier,
}).encode()

ctx = ssl.create_default_context()
req = urllib.request.Request(
    TOKEN_URL,
    data=data,
    headers={
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        result = json.loads(resp.read())
        print("\nToken exchange successful!")
        print(f"Access token: {result['access_token'][:20]}...")
        print(f"Refresh token: {result['refresh_token'][:20]}...")
        print(f"Scope: {result.get('scope', 'N/A')}")
        print(f"Expires in: {result.get('expires_in', 'N/A')}s")

        # Save to ~/.xurl
        import yaml
        config = {
            "apps": {
                "default": {"client_id": "", "client_secret": ""},
                "viraldna": {
                    "client_id": CLIENT_ID,
                    "client_secret": client_secret,
                    "oauth2": {
                        "access_token": result["access_token"],
                        "refresh_token": result["refresh_token"],
                        "scope": result.get("scope", SCOPES),
                        "username": "TheViralDNA",
                    },
                },
            },
            "default_app": "viraldna",
        }
        config_path = "/home/jay/.xurl"
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        print(f"\nConfig saved to {config_path}")
        print("Run 'xurl whoami' to verify.")

except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"\nToken exchange failed: {e.code} {e.reason}")
    print(f"Response: {body}")
except Exception as e:
    print(f"\nError: {e}")
