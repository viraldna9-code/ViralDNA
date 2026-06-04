#!/usr/bin/env python3
"""Build complete YouTube upload metadata for the dry run.

v82.3 fixes: TheViralDNA (one word), no edge-tts exposure, no duplicate
contact sections, #TeluguNews first hashtag, keyword-first titles.
"""
import json, re, os
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
now = datetime.now(IST)

def ass_to_text(path):
    lines = []
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("Dialogue:"):
                    parts = line.split(",", 9)
                    if len(parts) >= 10:
                        text = parts[9].strip()
                        text = re.sub(r'\{[^}]+\}', '', text)
                        if text:
                            lines.append(text)
    except:
        pass
    return " ".join(lines)

main_script = ass_to_text("audio/production_main.mp4.ass")
short1_script = ass_to_text("audio/production_short_1.mp4.ass")
short2_script = ass_to_text("audio/production_short_2.mp4.ass")

print(f"Main script: {len(main_script)} chars")
print(f"Short 1 script: {len(short1_script)} chars")
print(f"Short 2 script: {len(short2_script)} chars")

main_title = "Month-Long Procurement Delay Hits Andhra Farmers Hard | ViralDNA News"
short1_title = "Farmers Waiting, BJP Angry | Andhra Crop Procurement"
short2_title = "Impact on Your Wallet: Farmer Woes Affect Prices"

topic_tags = ["telangana", "farmers", "procurement", "bjp", "politics",
              "andhra pradesh", "crop procurement", "farmer crisis"]
default_tags = [
    "Telugu news today", "Andhra Pradesh news", "Telangana news",
    "AP news today", "Hyderabad news", "Vijayawada news", "Vizag news",
    "Amaravati news", "Guntur news", "TheViralDNA",
    "TV9 Telugu", "Sakshi news", "Eenadu news", "NTV Telugu", "ABN Andhra",
    "telugu varthalu", "andhra varthalu", "telangana varthalu",
    "Telugu breaking news", "Tenglish news", "India news today",
    "NRI Telugu news", "Telugu current affairs", "AP Telangana updates",
    "viral news India", f"trending India {now.year}", "Telugu states news",
]
all_tags = topic_tags + [t for t in default_tags if t.lower() not in [x.lower() for x in topic_tags]]

# MAIN description (v82.3: growth layout, TheViralDNA, no edge-tts, no dupes)
main_desc = "\n".join([
    "🔔 SUBSCRIBE & hit the bell → https://www.youtube.com/@TheViralDNA",
    f"📰 {main_title} ({now.strftime('%B %d, %Y')})",
    "",
    f"SUMMARY: {main_script[:300]}",
    "",
    f"💡 CONTEXT: {main_script[:300]}",
    "",
    "📌 SOURCE: Verified Regional News Feeds",
    "",
    "🔑 TOPICS: Telangana farmers, crop procurement delay, BJP Andhra politics, farmer crisis 2026, minimum support price",
    "",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "📺 TheViralDNA — Real News. Real Voices. Built with AI.",
    "",
    "We cover news that matters to Telugu people everywhere:",
    "📍 Andhra Pradesh | Telangana | Telugu States",
    "🇮🇳 National India — politics, economy, policy",
    "🌍 Telugu people worldwide",
    "",
    "🕘 New videos daily at 9:00 AM and 7:00 PM IST",
    "",
    "👍 Like this video — it helps us reach more Telugu people",
    "💬 Comment your thoughts — we read every comment",
    "📤 Share with family & friends — spread Telugu news",
    "",
    "📧 Business/Collab: viraldna9@gmail.com",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "",
    "📎 RELATED:",
    "  • Source: https://www.thehindu.com/news/national/telangana/farmers-hit-by-month-long-procurement-delay-alleges-bjp/article71049504.ece",
    "",
    "#TeluguNews #AndhraPradesh #TelanganaNews #ViralDNA #FarmersCrisis #BJPElections #CropProcurement #FarmersRights #BreakingNews #IndiaNewsToday",
    "",
    "🤖 ALTERED CONTENT DISCLOSURE:",
    "This video was produced using AI-assisted tools: AI script generation,",
    "AI voice synthesis, algorithmic video assembly. Visuals may",
    "include AI-generated imagery. Labeled per YouTube synthetic media policies.",
    "©️ Produced by TheViralDNA.",
])

# SHORT 1 description
short1_desc = "\n".join([
    f"📰 {short1_title}",
    "",
    f"SUMMARY: {short1_script[:200]}",
    "",
    "📌 SOURCE: Verified Regional News Feeds",
    "",
    "🎥 Watch the full story: https://youtube.com/@TheViralDNA",
    "",
    "#TeluguNews #AndhraPradesh #TelanganaNews #ViralDNA #FarmersCrisis #BJP #FarmersRights #Shorts",
    "",
    "🤖 ALTERED CONTENT DISCLOSURE: This video was produced using AI-assisted tools.",
    "©️ Produced by TheViralDNA.",
])

# SHORT 2 description
short2_desc = "\n".join([
    f"📰 {short2_title}",
    "",
    f"SUMMARY: {short2_script[:200]}",
    "",
    "📌 SOURCE: Verified Regional News Feeds",
    "",
    "🎥 Watch the full story: https://youtube.com/@TheViralDNA",
    "",
    "#TeluguNews #AndhraPradesh #TelanganaNews #ViralDNA #ConsumerPrices #Shorts",
    "",
    "🤖 ALTERED CONTENT DISCLOSURE: This video was produced using AI-assisted tools.",
    "©️ Produced by TheViralDNA.",
])

metadata = {
    "topic_id": "VDNA120",
    "topic_title": "Farmers hit by month-long procurement delay, alleges BJP",
    "score": 18,
    "score_breakdown": [
        "Fresh(Y'DAY) +3", "AP/TS +6", "IndiaRel +4 (farmers)",
        "ChannelGrowth +3", "TitleLen +2"
    ],
    "source": {
        "name": "The Hindu AP/TS",
        "url": "https://www.thehindu.com/news/national/telangana/farmers-hit-by-month-long-procurement-delay-alleges-bjp/article71049504.ece"
    },
    "main_video": {
        "file": "production_main.mp4",
        "title": main_title,
        "description": main_desc,
        "tags": all_tags[:20],
        "category_id": "25",
        "category_name": "News & Politics",
        "privacy_status": "private",
        "language": "en-IN",
        "duration_seconds": 81,
        "file_size_mb": 19.4,
        "is_short": False
    },
    "shorts": [
        {
            "file": "production_short_1.mp4",
            "title": f"{short1_title} #Shorts",
            "description": short1_desc,
            "tags": topic_tags[:10] + ["Shorts"],
            "category_id": "25",
            "privacy_status": "private",
            "language": "en-IN",
            "duration_seconds": 18,
            "file_size_mb": 8.9,
            "is_short": True
        },
        {
            "file": "production_short_2.mp4",
            "title": f"{short2_title} #Shorts",
            "description": short2_desc,
            "tags": topic_tags[:10] + ["Shorts"],
            "category_id": "25",
            "privacy_status": "private",
            "language": "en-IN",
            "duration_seconds": 20,
            "file_size_mb": 9.9,
            "is_short": True
        }
    ],
    "thumbnails": {
        "main": "production_branded.jpg",
        "variants": ["production_branded_v1.jpg", "production_branded_v2.jpg", "production_branded_v3.jpg"]
    },
    "scripts": {
        "main": main_script,
        "short_1": short1_script,
        "short_2": short2_script
    },
    "generated_at": now.strftime("%Y-%m-%d %H:%M IST"),
    "viral_dna_version": "v82.3"
}

os.makedirs("videos", exist_ok=True)
with open("videos/metadata.json", "w") as f:
    json.dump(metadata, f, indent=2, ensure_ascii=False)

print(f"\nMetadata written to videos/metadata.json")
print(f"  Main title: {main_title}")
print(f"  Main desc: {len(main_desc)} chars, {len(main_desc.splitlines())} lines")
print(f"  Tags: {len(all_tags)} tags")
print(f"  Short 1: {short1_title}")
print(f"  Short 2: {short2_title}")
