#!/bin/bash
# One-liner YouTube OAuth token refresh for ViralDNA
# Run this directly in your WSL terminal (not through the agent)

cd /home/jay/ViralDNA

echo ""
echo "=========================================="
echo "YouTube OAuth Token Refresh for ViralDNA"
echo "=========================================="
echo ""

/home/jay/venv/bin/python3 -c "
from google_auth_oauthlib.flow import InstalledAppFlow
from urllib.parse import urlparse, parse_qs
import json, sys

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
]

flow = InstalledAppFlow.from_client_secrets_file(
    'credentials/client_secrets.json',
    scopes=SCOPES,
)
flow.redirect_uri = 'http://localhost'

auth_url, state = flow.authorization_url(prompt='consent', access_type='offline')

print('STEP 1: Open this URL in your browser:')
print('----------------------------------------')
print(auth_url)
print()
print('STEP 2: Approve all permissions')
print()
print('STEP 3: Browser will show connection error on localhost')
print('        Copy the FULL URL from the address bar')
print('        It looks like: http://localhost/?code=4/0A...&state=...')
print()

redirect_url = input('STEP 4: Paste the full redirect URL here: ').strip()

parsed = urlparse(redirect_url)
params = parse_qs(parsed.query)
code = params.get('code', [None])[0]

if not code:
    print('ERROR: No code found in URL')
    sys.exit(1)

print(f'Code extracted: {code[:15]}...')

try:
    flow.fetch_token(code=code)
    creds = flow.credentials
    token_data = json.loads(creds.to_json())
    with open('credentials/youtube_token.json', 'w') as f:
        json.dump(token_data, f, indent=2)
    print()
    print('========================================')
    print('SUCCESS! Token saved.')
    print(f'Access:  {token_data[\"token\"][:20]}...')
    print(f'Refresh: {token_data.get(\"refresh_token\", \"N/A\")[:20]}...')
    print(f'Expiry:  {token_data.get(\"expiry\", \"unknown\")}')
    print('========================================')
except Exception as e:
    print(f'FAILED: {e}')
    sys.exit(1)
"
