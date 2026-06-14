#!/usr/bin/env python3
"""Fix VDNA218 metadata on YouTube — v87.0 clean version (v2)."""
import json, requests, datetime

with open('/home/jay/ViralDNA/credentials/youtube_token.json') as f:
    t = json.load(f)

headers = {
    'Authorization': f'Bearer {t["token"]}',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}

year = datetime.datetime.now().year

# ── MAIN VIDEO ──
MAIN_VIDEO_ID = "9vxPRDcl0RA"

main_title = "US Attacks Iran After Apache Helicopter Shot Down — What Happens Next?"

main_description = f"""{year} update: The US launches proportional strikes on Iran after an Apache helicopter is shot down. Here's what this means for West Asia and India.

🔔 SUBSCRIBE & hit the bell → https://www.youtube.com/@TheViralDNA

The US has launched strikes on Iran after an Apache helicopter was shot down in the region. Tensions are escalating rapidly across West Asia. Here's what you need to know.

⏱️ CHAPTERS:
  0:00 Breaking
  0:15 US Strikes Iran
  1:30 Apache Helicopter Downing
  3:00 What Happens Next
  4:30 Impact on India
  5:30 Key Takeaway

SOURCE: The Hindu

🔑 TOPICS: West Asia War, US Strikes Iran, Apache Helicopter Downing, Iran US Conflict, Geopolitical Crisis

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 TheViralDNA — Real News. Real Voices. Built with AI.
🕘 New videos daily at 9:00 AM & 7:00 PM IST
👍 Like • 💬 Comment • 📤 Share
📧 viraldna9@gmail.com
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤖 ALTERED CONTENT DISCLOSURE:
This video was produced using AI-assisted tools: AI script generation, AI voice synthesis, algorithmic video assembly. Visuals may include AI-generated imagery. Labeled per YouTube synthetic media policies.
©️ Produced by TheViralDNA."""

main_tags = [
    "West Asia War", "US strikes Iran", "Apache helicopter downing",
    "Iran US conflict", "Breaking news", "Geopolitical crisis",
    "Military escalation", "Middle East tensions", "International relations",
    "Telugu news", "Andhra Pradesh", "Telangana", "India news",
    "Telugu varthalu", "Andhra varthalu", "Telangana varthalu",
    "NRI news", "Telugu diaspora", "TheViralDNA",
    f"trending India {year}", "news today"
]

# ── SHORT VIDEO ──
SHORT_VIDEO_ID = "_00tPsz4AXI"

short_title = "US Strikes Iran — Apache Helicopter Downing #Shorts"

short_description = f"""{year} update: US launches strikes on Iran after Apache helicopter shot down. Tensions escalate across West Asia.

🔔 SUBSCRIBE & hit the bell → https://www.youtube.com/@TheViralDNA

SOURCE: The Hindu

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 TheViralDNA — Real News. Real Voices. Built with AI.
🕘 New videos daily at 9:00 AM & 7:00 PM IST
👍 Like • 💬 Comment • 📤 Share
📧 viraldna9@gmail.com
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#Shorts #WestAsiaWar #USstrikesIran #IranUSconflict #BreakingNews #TeluguNews #AndhraPradesh #Telangana #IndiaNews #ViralDNA #YouTubeShorts #TeluguShorts #GeopoliticalNews #MilitaryEscalation

🤖 ALTERED CONTENT DISCLOSURE:
This video was produced using AI-assisted tools: AI script generation, AI voice synthesis, algorithmic video assembly. Visuals may include AI-generated imagery. Labeled per YouTube synthetic media policies.
©️ Produced by TheViralDNA."""

short_tags = [
    "Shorts", "YouTube Shorts", "Telugu Shorts", "Shorts News",
    "West Asia War", "US strikes Iran", "Apache helicopter downing",
    "Iran US conflict", "Breaking news", "Geopolitical crisis",
    "Military escalation", "Middle East tensions",
    "Telugu news", "Andhra Pradesh", "Telangana", "India news",
    "Telugu varthalu", "Andhra varthalu", "Telangana varthalu",
    "TheViralDNA", f"trending India {year}"
]

def update_video(video_id, title, description, tags):
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet"
    body = {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "25",
            "defaultLanguage": "en-IN",
            "defaultAudioLanguage": "en-IN"
        }
    }
    resp = requests.put(url, headers=headers, json=body, timeout=30)
    if resp.status_code == 200:
        result = resp.json()
        print(f"✅ {video_id}")
        print(f"   Title: {result['snippet']['title']}")
        print(f"   Tags: {len(result['snippet'].get('tags', []))}")
        return True
    else:
        print(f"❌ {video_id} ({resp.status_code})")
        print(f"   {resp.text[:300]}")
        return False

print("=" * 60)
print("UPDATING VDNA218 MAIN VIDEO")
print("=" * 60)
update_video(MAIN_VIDEO_ID, main_title, main_description, main_tags)

print()
print("=" * 60)
print("UPDATING VDNA218 SHORT VIDEO")
print("=" * 60)
update_video(SHORT_VIDEO_ID, short_title, short_description, short_tags)

print()
print("Done.")
