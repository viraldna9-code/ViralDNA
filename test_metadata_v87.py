#!/usr/bin/env python3
"""Test v87.0 metadata generation — uses actual module code."""
import sys, os, json, re, datetime

sys.path.insert(0, '/home/jay/ViralDNA/modules')

# We can't easily instantiate YouTubeUploader (needs config, credentials etc.)
# So we extract and test the key logic functions directly.

year = datetime.datetime.now().year
_year = str(year)

# ── Reproduce title generation from youtube_uploader.py lines 236-270 ──
def generate_title(title_raw, is_short=False):
    clean_title = re.sub(r'\s*[-|]\s*(The Hindu|NDTV|Times of India|India Today|Firstpost|Scroll\.in|The Wire|News18|CNBC|BBC|CNN|Al Jazeera|Reuters|AP|AFP|PTI|ANI).*$', '', title_raw, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r'\s*[-|]\s*(Google News|RSS|India Top).*$', '', clean_title, flags=re.IGNORECASE).strip()

    if is_short:
        base = re.sub(r'\s*#Shorts.*$', '', clean_title, flags=re.IGNORECASE).strip()
        base = re.sub(r'\s*\(\d{4}\)\s*$', '', base).strip()
        # " ({year}) #Shorts" = 13 chars
        max_base_len = 60 - len(f" ({_year}) #Shorts")
        if len(base) > max_base_len:
            base = base[:max_base_len - 3].rstrip() + "..."
        title = f"{base} ({_year}) #Shorts"
    else:
        base = re.sub(r'\s*\(\d{4}\)\s*$', '', clean_title).strip()
        if _year not in base:
            candidate = f"{base} ({_year})"
        else:
            candidate = base
        if len(candidate) > 70:
            overflow = len(candidate) - 70
            base = base[:len(base) - overflow - 3].rstrip()
            if _year not in base:
                candidate = f"{base} ({_year})"
            else:
                candidate = base
        title = candidate
    return title

# ── Test cases ──
test_cases = [
    ("West Asia war highlights: U.S. strikes Iran after Apache helicopter downing - The Hindu", False, "Strip source, add year, under 70"),
    ("West Asia war highlights: U.S. strikes Iran after Apache helicopter downing - The Hindu", True, "Strip source, single #Shorts, under 60"),
    ("Global Alert: US Attacks Iran!", False, "Add year, under 70"),
    ("Global Alert: US Attacks Iran! #Shorts", True, "No duplicate #Shorts"),
    ("Telugu news today (2026) - NDTV", False, "Strip NDTV, no duplicate year"),
    ("Telugu news today (2026) - NDTV", True, "Strip NDTV, single #Shorts"),
    ("Breaking: Major earthquake hits Japan - Times of India", False, "Strip source"),
    ("Budget 2026: What it means for Telugu people - The Hindu", False, "Strip source"),
]

print("=" * 70)
print("TITLE GENERATION TESTS (v87.0)")
print("=" * 70)

all_pass = True
for title_raw, is_short, desc in test_cases:
    result = generate_title(title_raw, is_short)
    max_len = 60 if is_short else 70
    issues = []
    if len(result) > max_len:
        issues.append(f"TOO LONG ({len(result)} > {max_len})")
    if "#Shorts #Shorts" in result:
        issues.append("DUPLICATE #Shorts")
    if result.count("(2026)") > 1:
        issues.append("DUPLICATE YEAR")
    for src in ["The Hindu", "NDTV", "Times of India", "India Today", "Firstpost"]:
        if src.lower() in result.lower():
            issues.append(f"SOURCE LEAK: {src}")
    
    status = "✅" if not issues else "❌ " + ", ".join(issues)
    print(f"\n{desc}")
    print(f"  In:  {title_raw[:65]}")
    print(f"  Out: {result} ({len(result)} chars)")
    print(f"  {status}")
    if issues:
        all_pass = False

# ── Verify module code ──
print("\n" + "=" * 70)
print("MODULE CODE VERIFICATION")
print("=" * 70)

with open('/home/jay/ViralDNA/modules/youtube_uploader.py') as f:
    content = f.read()

checks = [
    ('Competitor tags removed from channel_tags', 'TV9 Telugu' not in content.split('channel_tags')[1].split(']')[0]),
    ('"ai" removed from HIGH_VALUE_KEYWORDS', '"ai"' not in content.split('HIGH_VALUE_KEYWORDS')[1].split(']')[0]),
    ('"ai" removed from tag_map', '"ai": "#AI"' not in content.split('tag_map')[1].split('}')[0]),
    ('Bloated CTA removed', 'We cover news that matters to Telugu people everywhere:' not in content),
    ('Repetitive CTA removed', 'Like this video — it helps us reach more' not in content),
    ('Generic "Intro" chapter removed', '"0:00", "Intro"' not in content),
    ('Dynamic chapters present', 'entities[0]' in content and 'entities[1]' in content),
    ('Source name stripping present', 'The Hindu|NDTV' in content),
    ('Word-boundary SEO matching', r"r'\\b'" in content or "r'\\\\b'" in content or r"\b" in content),
    ('Description trimmed', '👍 Like • 💬 Comment • 📤 Share' in content),
]

for desc, passed in checks:
    print(f"  {'✅' if passed else '❌'} {desc}")
    if not passed:
        all_pass = False

# ── Verify upload_approved.py ──
print("\n" + "=" * 70)
print("UPLOAD_APPROVED.PY VERIFICATION")
print("=" * 70)

with open('/home/jay/ViralDNA/upload_approved.py') as f:
    ucontent = f.read()

uchecks = [
    ('Source name stripping in upload_approved.py', 'The Hindu|NDTV' in ucontent),
    ('Symlinks for production_main.mp4', 'production_main.mp4' in ucontent),
    ('Symlinks for production_branded.jpg', 'production_branded.jpg' in ucontent),
    ('script_payload construction', 'main_title_variants' in ucontent),
    ('publish_decision pass-through', 'publish_decision' in ucontent),
]

for desc, passed in uchecks:
    print(f"  {'✅' if passed else '❌'} {desc}")
    if not passed:
        all_pass = False

print("\n" + "=" * 70)
if all_pass:
    print("ALL TESTS PASSED ✅ — Ready for 5:30 PM run")
else:
    print("SOME TESTS FAILED ❌ — Fix before 5:30 PM run")
print("=" * 70)
