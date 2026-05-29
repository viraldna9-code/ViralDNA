#!/usr/bin/env python3
import os, sys, json
from google_auth_oauthlib.flow import InstalledAppFlow

if len(sys.argv) < 2:
    print("Usage: python3 youtube_auth_step2.py <authorization_code>")
    sys.exit(1)

code = sys.argv[1].strip()

# Load flow state
with open("/tmp/youtube_flow_state.json") as f:
    flow_state = json.load(f)

vdna_home = os.environ.get("VDNA_HOME", "/home/jay/ViralDNA")
secrets = vdna_home + "/credentials/client_secrets.json"
token_out = flow_state["token_out"]

# Recreate flow
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
]
flow = InstalledAppFlow.from_client_secrets_file(
    secrets, SCOPES, redirect_uri="urn:ietf:wg:oauth:2.0:oob"
)
flow.code_verifier = flow_state["code_verifier"]

# Fetch token
flow.fetch_token(code=code)
creds = flow.credentials

with open(token_out, "w") as f:
    f.write(creds.to_json())

print(f"SUCCESS! Token saved to {token_out}")
print(f"Scopes: {creds.scopes}")
print(f"Has refresh token: {bool(creds.refresh_token)}")
