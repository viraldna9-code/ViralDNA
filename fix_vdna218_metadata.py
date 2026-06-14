#!/usr/bin/env python3
"""Update VDNA218 metadata on YouTube using direct API calls (bypass httplib2 DNS issues)."""
import json
import requests
import datetime

# Load token
with open('/home/jay/ViralDNA/credentials/youtube_token.json') as f:
    token_data = json.load(f)

ACCESS_TOKEN = token_data['token']
HEADERS = {
    'Authorization': f'Bearer {ACCESS_TOKEN}',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}

year = datetime.datetime.now().year
today_str = datetime.datetime.now().strftime("%B %d, %Y")

# ── MAIN VIDEO METADATA ──
MAIN_VIDEO_ID = "9vxPRDcl0RA"

main_title = "US Attacks Iran After Apache Helicopter Shot Down — What Happens Next?"

main_description = f"""{year} update: The US launches proportional strikes on Iran after an Apache helicopter is shot down. Here's what this means for West Asia and India.

🔔 SUBSCRIBE & hit the bell → https://www.youtube.com/@TheViralDNA
West Asia war highlights: U.S. strikes Iran after Apache helicopter downing ({today_str})

The US has launched strikes on Iran after an Apache helicopter was shot down in the region. Tensions are escalating rapidly across West Asia. Here's what you need to know.

⏱️ CHAPTERS:
  0:00 US Strikes Iran — Breaking
  0:15 Apache Helicopter Shot Down
  1:30 US Retaliation Details
  3:00 Iran's Response
  4:30 Impact on India & West Asia
  5:30 Key Takeaway

SOURCE: The Hindu via Google News RSS

🔑 TOPICS: West Asia War, US Strikes Iran, Apache Helicopter Downing, Iran US Conflict, Geopolitical Crisis

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 TheViralDNA — Real News. Real Voices. Built with AI.

We cover news that matters to Telugu people everywhere:
📍 Andhra Pradesh | Telangana | Telugu States
🇮🇳 National India — politics, economy, policy
🌍 Telugu people worldwide

🕘 New videos daily at 9:00 AM and 7:00 PM IST

👍 Like this video — it helps us reach more Telugu people
💬 Comment your thoughts — we read every comment
📤 Share with family & friends — spread the news

📧 Business/Collab: viraldna9@gmail.com
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📎 RELATED:
  • Subscribe to ViralDNA: https://youtube.com/@ViralDNA?sub_confirmation=1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#WestAsiaWar #USstrikesIran #IranUSconflict #BreakingNews #TeluguNews #AndhraPradesh #Telangana #IndiaNews #ViralDNA #NRI #TeluguDiaspora #GeopoliticalNews #MilitaryEscalation

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

# ── SHORT VIDEO METADATA ──
SHORT_VIDEO_ID = "_00tPsz4AXI"

short_title = "US Strikes Iran — Apache Helicopter Downing #Shorts"

short_description = f"""{year} update: US launches strikes on Iran after Apache helicopter shot down. Tensions escalate across West Asia.

🔔 SUBSCRIBE & hit the bell → https://www.youtube.com/@TheViralDNA
US Strikes Iran — Apache Helicopter Downing #Shorts ({today_str})

West Asia war highlights: U.S. strikes Iran after Apache helicopter downing

SOURCE: The Hindu via Google News RSS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 TheViralDNA — Real News. Real Voices. Built with AI.

🕘 New videos daily at 9:00 AM and 7:00 PM IST

👍 Like • 💬 Comment • 📤 Share

📧 Business/Collab: viraldna9@gmail.com
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📎 RELATED:
  • Subscribe: https://youtube.com/@ViralDNA?sub_confirmation=1

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
    """Update video metadata via YouTube Data API v3."""
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
    
    resp = requests.put(url, headers=HEADERS, json=body, timeout=30)
    
    if resp.status_code == 200:
        result = resp.json()
        print(f"✅ Updated: {video_id}")
        print(f"   Title: {result['snippet']['title'][:80]}")
        print(f"   Tags: {len(result['snippet'].get('tags', []))}")
        return True
    else:
        print(f"❌ Failed ({resp.status_code}): {video_id}")
        print(f"   {resp.text[:200]}")
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
print("Done. Check YouTube Studio for updated metadata.")
