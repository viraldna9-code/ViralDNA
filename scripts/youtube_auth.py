#!/usr/bin/env python3
"""One-time YouTube OAuth2 token generation for WSL."""
import os, sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
]

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT_SECRETS = BASE + "/credentials/client_secrets.json"
TOKEN_OUT = BASE + "/credentials/youtube_token.json"

if not os.path.exists(CLIENT_SECRETS):
    print(f"ERROR: {CLIENT_SECRETS} not found.")
    sys.exit(1)

flow = InstalledAppFlow.from_client_secrets_file(
    CLIENT_SECRETS, SCOPES, redirect_uri="urn:ietf:wg:oauth:2.0:oob"
)
auth_url, _ = flow.authorization_url(prompt="consent")

print()
print("=" * 70)
print("STEP 1: Open this URL in your Windows browser:")
print()
print(auth_url)
print()
print("STEP 2: After authorizing, copy the code from Google consent screen.")
print("STEP 3: Paste the code below and press Enter.")
print("=" * 70)

url_file = BASE + "/credentials/auth_url.txt"
with open(url_file, "w") as f:
    f.write(auth_url)
print(f"(URL also saved to {url_file})")
print()

try:
    code = input("Authorization code: ").strip()
except EOFError:
    print()
    print("ERROR: No input. Run this in an interactive terminal:")
    print("  python3 scripts/youtube_auth.py")
    sys.exit(1)

if not code:
    print("ERROR: No code provided.")
    sys.exit(1)

flow.fetch_token(code=code)
creds = flow.credentials

with open(TOKEN_OUT, "w") as f:
    f.write(creds.to_json())

print()
print(f"SUCCESS! Token saved to {TOKEN_OUT}")
print(f"Scopes: {creds.scopes}")
print(f"Has refresh token: {bool(creds.refresh_token)}")
