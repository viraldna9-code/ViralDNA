#!/usr/bin/env python3
"""One-shot YouTube OAuth token refresh. Run with code as argument."""
import os, sys, json
from datetime import datetime, timezone, timedelta
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

IST = timezone(timedelta(hours=5, minutes=30))
def now_ist():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

CREDENTIALS_DIR = '/home/jay/ViralDNA/credentials'
TOKEN_PATH = CREDENTIALS_DIR + '/youtube_token.json'
SECRETS_PATH = CREDENTIALS_DIR + '/client_secrets.json'

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
]

if len(sys.argv) < 2:
    print('Usage: python3 refresh_youtube_token_oneshot.py <auth_code>')
    sys.exit(1)

code = sys.argv[1].strip()

print('YouTube OAuth Re-authorization (one-shot)')
print('=' * 50)
print('Started:', now_ist())

if os.path.exists(TOKEN_PATH):
    backup = TOKEN_PATH + '.bak'
    with open(TOKEN_PATH) as f:
        old = json.load(f)
    with open(backup, 'w') as f:
        json.dump(old, f, indent=2)
    print('Old token backed up.')

flow = InstalledAppFlow.from_client_secrets_file(SECRETS_PATH, SCOPES)
flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'

try:
    flow.fetch_token(code=code)
    creds = flow.credentials
    with open(TOKEN_PATH, 'w') as f:
        f.write(creds.to_json())
    print('✅ Token refreshed and saved to', TOKEN_PATH)
    print('Expires:', creds.expiry)
except Exception as e:
    print('ERROR:', e)
    sys.exit(1)
