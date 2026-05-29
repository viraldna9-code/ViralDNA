#!/usr/bin/env python3
import os, json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
]

vdna_home = "/home/jay/ViralDNA"
secrets = vdna_home + "/credentials/client_secrets.json"
token_out = vdna_home + "/credentials/youtube_token.json"

# Use OOB redirect (no local server needed in WSL)
flow = InstalledAppFlow.from_client_secrets_file(
    secrets, SCOPES, redirect_uri="urn:ietf:wg:oauth:2.0:oob"
)
auth_url, state = flow.authorization_url(
    prompt="consent",
    access_type="offline"  # Force refresh token
)

# Save auth URL
with open(vdna_home + "/credentials/auth_url.txt", "w") as f:
    f.write(auth_url)

# Save state for step2
state_data = {
    "code_verifier": flow.code_verifier,
    "state": state,
    "token_out": token_out,
}
with open("/tmp/youtube_flow_state.json", "w") as f:
    json.dump(state_data, f)

print("AUTH_URL:", auth_url)
print()
print("=== INSTRUCTIONS ===")
print("1. Open the above URL in your Windows browser")
print("2. Sign in with the ViralDNA Google account")
print("3. Click ALLOW for all 3 permissions")
print("4. Copy the authorization code shown")
print("5. Run: cd /home/jay/ViralDNA && python3 scripts/youtube_auth_step2.py <code>")
print("====================")
