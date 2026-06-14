#!/usr/bin/env python3
"""Check current live metadata for VDNA218 videos on YouTube."""
import json, requests

with open('/home/jay/ViralDNA/credentials/youtube_token.json') as f:
    t = json.load(f)

headers = {
    'Authorization': f'Bearer {t["token"]}',
    'Accept': 'application/json',
}

for vid, label in [("9vxPRDcl0RA", "MAIN"), ("_00tPsz4AXI", "SHORT")]:
    resp = requests.get(
        f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={vid}",
        headers=headers, timeout=15
    )
    data = resp.json()
    if data.get('items'):
        s = data['items'][0]['snippet']
        print(f"=== {label} ({vid}) ===")
        print(f"Title: {s['title']}")
        print(f"Desc: {s['description'][:300]}...")
        print(f"Tags ({len(s.get('tags', []))}): {s.get('tags', [])[:10]}...")
        print(f"Category: {s.get('categoryId')}")
        print()
    else:
        print(f"=== {label} ({vid}) === NOT FOUND")
        print(resp.text[:200])
