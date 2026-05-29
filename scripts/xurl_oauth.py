#!/usr/bin/env python3
"""
Manual X OAuth2 flow for WSL - handles the browser auth that xurl can't do natively.
Saves the resulting token to ~/.xurl in the correct format.
"""
import base64 as b64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

CLIENT_ID = "aEdIajdPZ3dOeXE5bWtLLUw5N3I6MTpjaQ"
CLIENT_SECRET = "ShcD7RZ8qeJSdxSUD7Ju_vvweuRTDL5TT8MDBLFCUSaQYuKcam"
REDIRECT_URI = "http://localhost:8080/callback"
PORT = 8080
USERNAME = "TheViralDNA"

AUTH_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"

SCOPES = "tweet.read tweet.write users.read offline.access"

authorization_code = None
auth_error = None
code_verifier_global = None


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global authorization_code, auth_error
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            authorization_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authorization successful!</h1>"
                b"<p>You can close this window and return to the terminal.</p></body></html>"
            )
        elif "error" in params:
            auth_error = params.get("error_description", [params.get("error", ["unknown"])])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h1>Authorization failed</h1><p>{auth_error}</p></body></html>".encode()
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    global authorization_code, auth_error, code_verifier_global

    # Generate PKCE
    code_verifier = secrets.token_urlsafe(64)[:128]
    code_verifier_global = code_verifier
    code_challenge = b64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    # Start callback server
    server = http.server.HTTPServer(("127.0.0.1", PORT), CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    print(f"  Callback server listening on port {PORT}...")

    # Build auth URL
    state = secrets.token_urlsafe(16)
    auth_params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_request_url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

    print(f"\n  Opening browser for X authorization...")
    print(f"  If browser doesn't open, manually visit this URL:\n")
    print(f"  {auth_request_url}\n")

    # Try to open browser via Windows
    browser_opened = False

    # Method 1: Write an HTML redirect file and open it
    html_path = "/tmp/xurl_oauth_redirect.html"
    with open(html_path, "w") as f:
        f.write(f'<html><head><meta http-equiv="refresh" content="0;url={auth_request_url}"></head>'
                f'<body><p>Redirecting to X authorization...</p>'
                f'<p>If not redirected, <a href="{auth_request_url}">click here</a>.</p></body></html>')

    browser_paths = [
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        "/mnt/c/Windows/System32/cmd.exe",
    ]
    for bp in browser_paths:
        if os.path.exists(bp):
            try:
                if "cmd.exe" in bp:
                    # Use start with the HTML redirect file (avoids & escaping issues)
                    os.system(f'cmd.exe /c start "" "file://{html_path}"')
                elif "chrome" in bp.lower():
                    os.system(f'"{bp}" "file://{html_path}"')
                else:
                    os.system(f'"{bp}" "file://{html_path}"')
                browser_opened = True
                print(f"  Browser opened via {bp}")
                break
            except Exception:
                continue

    if not browser_opened:
        print("  Could not auto-open browser. Please open the URL above manually.")

    # Wait for callback
    timeout = 180
    elapsed = 0
    print("  Waiting for authorization (timeout: 180s)...")
    while authorization_code is None and auth_error is None and elapsed < timeout:
        time.sleep(1)
        elapsed += 1
        if elapsed % 15 == 0:
            print(f"  ... still waiting ({elapsed}s)")

    server.shutdown()

    if auth_error:
        print(f"\n  Authorization ERROR: {auth_error}")
        sys.exit(1)

    if authorization_code is None:
        print("\n  Authorization timed out.")
        sys.exit(1)

    print(f"  Authorization code received! Exchanging for token...")

    # Exchange code for token
    token_data = urllib.parse.urlencode({
        "code": authorization_code,
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier_global,
    }).encode()

    credentials = b64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

    req = urllib.request.Request(
        TOKEN_URL,
        data=token_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            token_response = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"  Token exchange FAILED: {e.code} {error_body}")
        sys.exit(1)

    if "access_token" not in token_response:
        print(f"  Unexpected response: {json.dumps(token_response, indent=2)}")
        sys.exit(1)

    print(f"  Token exchange successful!")

    # Configure ~/.xurl
    xurl_path = os.path.expanduser("~/.xurl")
    xurl_config = {"apps": {}, "default_app": "viraldna"}

    if os.path.exists(xurl_path):
        try:
            with open(xurl_path, "r") as f:
                xurl_config = yaml.safe_load(f) or xurl_config
        except Exception:
            pass

    xurl_config.setdefault("apps", {})
    xurl_config["apps"]["viraldna"] = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "oauth2": {
            "access_token": token_response["access_token"],
            "refresh_token": token_response.get("refresh_token", ""),
            "expires_in": token_response.get("expires_in", 7200),
            "scope": token_response.get("scope", SCOPES),
            "username": USERNAME,
        },
    }
    xurl_config["default_app"] = "viraldna"

    with open(xurl_path, "w") as f:
        yaml.dump(xurl_config, f, default_flow_style=False)

    # Set restrictive permissions
    os.chmod(xurl_path, 0o600)

    print(f"  Token saved to {xurl_path}")
    print(f"  App 'viraldna' set as default")
    print(f"\n  xurl is now configured for @{USERNAME}!")


if __name__ == "__main__":
    main()
