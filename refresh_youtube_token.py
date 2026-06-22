#!/usr/bin/env python3
"""YouTube OAuth token refresh for ViralDNA.
Run: cd /home/jay/ViralDNA && python3 refresh_youtube_token.py
"""
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

print('YouTube OAuth Re-authorization')
print('=' * 50)
print('Started:', now_ist())

if not os.path.exists(SECRETS_PATH):
    print('ERROR: client_secrets.json not found')
    sys.exit(1)

if os.path.exists(TOKEN_PATH):
    backup = TOKEN_PATH + '.bak'
    with open(TOKEN_PATH) as f:
        old = json.load(f)
    with open(backup, 'w') as f:
        json.dump(old, f, indent=2)
    print('Old token backed up.')

print('Requested scopes:')
for s in SCOPES:
    print(' ', s)

flow = InstalledAppFlow.from_client_secrets_file(SECRETS_PATH, SCOPES)
flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

print()
print('=' * 50)
print('STEP 1: Open this URL in your Windows browser:')
print('=' * 50)
print()
print(auth_url)
print()
print('=' * 50)
print('STEP 2: Sign in, grant permissions.')
print('Google will show you an authorization code.')
print('Copy that code and paste it below.')
print('=' * 50)
print()

code = input('Paste authorization code: ').strip()

try:
    flow.fetch_token(code=code)
    creds = flow.credentials
    with open(TOKEN_PATH, 'w') as f:
        f.write(creds.to_json())
    print()
    print('=' * 50)
    print('SUCCESS! Token saved.')
    print('=' * 50)
    print('Completed:', now_ist())
    expiry_ist = creds.expiry.astimezone(IST) if creds.expiry else None
    print('Token expiry (IST):', expiry_ist.strftime("%Y-%m-%d %H:%M:%S IST") if expiry_ist else 'Unknown')
    if expiry_ist:
        remaining = expiry_ist - datetime.now(IST)
        print('Valid for:', str(remaining).split('.')[0])
except Exception as e:
    print('ERROR at', now_ist(), ':', e)
    sys.exit(1)
