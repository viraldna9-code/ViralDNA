#!/usr/bin/env python3
"""
Write xurl config file using tokens from X developer portal.
Run this script to configure xurl with your OAuth2 tokens.
"""
import os
import yaml

config = {
    "apps": {
        "default": {
            "client_id": "",
            "client_secret": "",
        },
        "viraldna": {
            "client_id": input("Enter Client ID: ").strip(),
            "client_secret": input("Enter Client Secret: ").strip(),
            "oauth2": {
                "access_token": input("Enter Access Token: ").strip(),
                "refresh_token": input("Enter Refresh Token: ").strip(),
                "scope": "tweet.read tweet.write users.read offline.access",
                "username": "TheViralDNA",
            },
        },
    },
    "default_app": "viraldna",
}

config_path = os.path.expanduser("~/.xurl")
with open(config_path, "w") as f:
    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

print(f"\nConfig written to {config_path}")
print("Run 'xurl whoami' to verify.")
