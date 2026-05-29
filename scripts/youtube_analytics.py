#!/usr/bin/env python3
"""Check performance of live ViralDNA videos on YouTube."""
import json, sys
sys.path.insert(0, "/home/jay/ViralDNA")

# Load the fresh token
with open("/home/jay/ViralDNA/credentials/youtube_token.json") as f:
    creds_data = json.load(f)

import requests

access_token = creds_data["token"]
headers = {"Authorization": f"Bearer {access_token}"}

# Known video IDs from last production run
videos = [
    {"id": "gErVuH7oZGA", "type": "Main", "title": "Ebola alert declared in Andhra Pradesh"},
    {"id": "KlZbANHfWmE", "type": "Short 1", "title": "Did You Know? Ebola alert..."},
    {"id": "YO4le_9t-XQ", "type": "Short 2", "title": "What Ebola alert declared..."},
]

# YouTube Data API v3 - get video statistics
ids = ",".join(v["id"] for v in videos)
url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet,contentDetails&id={ids}"

resp = requests.get(url, headers=headers)
data = resp.json()

if "error" in data:
    print("ERROR:", data["error"])
    sys.exit(1)

print("=" * 70)
print("VIRALDNA YOUTUBE ANALYTICS")
print("=" * 70)

for item in data.get("items", []):
    vid = item["id"]
    s = item["statistics"]
    sn = item["snippet"]
    cd = item["contentDetails"]
    
    views = int(s.get("viewCount", 0))
    likes = int(s.get("likeCount", 0))
    comments = int(s.get("commentCount", 0))
    duration = cd.get("duration", "N/A")
    title = sn.get("title", "N/A")
    published = sn.get("publishedAt", "N/A")
    
    # Find type
    vtype = "Unknown"
    for v in videos:
        if v["id"] == vid:
            vtype = v["type"]
            break
    
    print(f"\n[{vtype}] {title[:60]}")
    print(f"  Video ID: {vid}")
    print(f"  Published: {published}")
    print(f"  Duration: {duration}")
    print(f"  Views: {views:,}")
    print(f"  Likes: {likes:,}")
    print(f"  Comments: {comments:,}")
    if views > 0:
        like_rate = (likes / views) * 100
        print(f"  Like Rate: {like_rate:.2f}%")
    print(f"  URL: https://youtube.com/watch?v={vid}")

print("\n" + "=" * 70)
