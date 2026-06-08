"""
v84.3: Fix published YouTube videos metadata via YouTube Data API.
Strips description prefixes, rebuilds empty descriptions, adds topic-specific tags.
"""
import json, os, sys, time, re

sys.path.insert(0, '/home/jay/ViralDNA/modules')

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

TOKEN_PATH = '/home/jay/ViralDNA/credentials/youtube_token.json'
CHANNEL_ID = 'UCkW7fqkJiaej2PeNcP4PejQ'

with open(TOKEN_PATH) as f:
    creds = Credentials.from_authorized_user_file(TOKEN_PATH)

youtube = build('youtube', 'v3', credentials=creds)

CHANNEL_TAGS = [
    'telugu news', 'andhra pradesh news', 'telangana news',
    'indian politics', 'viral dna', 'telugu breaking news',
    'andhra politics', 'telangana politics', 'telugu news live',
    'india news telugu'
]

def generate_topic_tags(title, existing_tags):
    """Generate topic-specific tags from video title + existing."""
    tags = set(t.lower().strip() for t in existing_tags if t.strip())
    
    title_lower = title.lower()
    
    # Political figures
    for fig in ['pawan kalyan', 'modi', 'revanth', 'kcr', 'lokesh', 'chandrababu',
                'naidu', 'mk stalin', 'jagan', 'shivakumar', 'gandhi', 'annamalai',
                'nainar nagendran', 'ktr', 'thackeray', 'nara lokesh']:
        if fig in title_lower:
            tags.add(fig)
    
    # Parties
    for party in ['jana sena', 'congress', 'bjp', 'tdp', 'trs', 'brs', 'dmk',
                  'aiadmk', 'ysrcp', 'tmc', 'aimim', 'india bloc', 'india janbandhan']:
        if party in title_lower:
            tags.add(party)
    
    # Places
    for place in ['telangana', 'andhra pradesh', 'hyderabad', 'karnataka',
                  'tamil nadu', 'india', 'pakistan', 'russia']:
        if place in title_lower:
            tags.add(place)
    
    # Topics
    for topic in ['nuclear power', 'rosatom', 'terrorism', 'boycott', 'identity row',
                  'political firestorm', 'breaking news', 'election', 'leadership']:
        if topic in title_lower:
            tags.add(topic)
    
    # Add channel-level tags
    for tag in CHANNEL_TAGS:
        tags.add(tag)
    
    # Clean up
    tags.discard('viraldna')
    tags.discard('theviraldna')
    tags.discard('shorts')
    
    return list(tags)[:25]

def build_description(title, existing_desc):
    """Build clean keyword-rich description."""
    desc = existing_desc.strip() if existing_desc else ''
    
    # Strip known prefixes
    desc = re.sub(r'^DESCRIPTION:\s*', '', desc, flags=re.IGNORECASE)
    desc = re.sub(r'^2026 update:\s*', '', desc, flags=re.IGNORECASE)
    desc = desc.strip()
    
    # If too short, rebuild concisely
    if len(desc) < 50:
        desc = f"{title}\n\n"
        desc += "Latest breaking news from Andhra Pradesh, Telangana, and India. "
        desc += "Subscribe: https://www.youtube.com/@TheViralDNA\n\n"
    
    # Add hashtags if not present
    if '#' not in desc:
        desc += "#ViralDNA #TeluguNews #BreakingNews"
    
    return desc[:2000]

def fix_title(title):
    """Return fixed title or None."""
    if len(title) > 70:
        truncated = title[:67].rsplit(' ', 1)[0]
        if len(truncated) > 30:
            return truncated + '...'
    return None

def get_all_videos():
    videos = []
    request = youtube.search().list(
        part="id", channelId=CHANNEL_ID, maxResults=50, order="date", type="video"
    )
    while request:
        resp = request.execute()
        for item in resp.get('items', []):
            vid = item['id'].get('videoId')
            if vid:
                videos.append(vid)
        request = youtube.search().list_next(request, resp)
    return videos

def get_video_details(video_ids):
    all_items = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        resp = youtube.videos().list(
            part="snippet,statistics,contentDetails", id=','.join(batch)
        ).execute()
        all_items.extend(resp.get('items', []))
    return all_items

def update_video(vid, updates, max_retries=3):
    for attempt in range(max_retries):
        try:
            resp = youtube.videos().list(part="snippet", id=vid).execute()
            if not resp.get('items'):
                return False, "not found"
            snippet = resp['items'][0]['snippet']
            snippet.update(updates)
            youtube.videos().update(
                part="snippet",
                body={'id': vid, 'snippet': snippet}
            ).execute()
            return True, "ok"
        except Exception as e:
            err_str = str(e)
            if 'TimeoutError' in type(e).__name__ or 'timed out' in err_str.lower() or '500' in err_str or '503' in err_str:
                wait = (attempt + 1) * 3
                print(f"    [RETRY {attempt+1}/{max_retries}] {type(e).__name__}, waiting {wait}s...")
                time.sleep(wait)
                continue
            return False, err_str
    return False, f"timeout after {max_retries} retries"

# ─── MAIN ───
# Videos already fixed in previous run (skip to avoid re-update)
ALREADY_FIXED = {'PhPKatQc61c', 'dLZZXotpUL4', 'ffAZ7m8XxMY', '8fXr1HmGd2I', 'JDEvBAqd44g'}

print("="*70)
print("v84.3: Fixing published YouTube video metadata")
print("="*70)

video_ids = get_all_videos()
print(f"Found {len(video_ids)} videos")

videos = get_video_details(video_ids)
videos.sort(key=lambda x: int(x['statistics'].get('viewCount', 0)))

success = 0
skip = 0
fail = 0

for v in videos:
    vid = v['id']
    snippet = v['snippet']
    stats = v['statistics']
    views = int(stats.get('viewCount', 0))
    title = snippet['title']
    desc = snippet.get('description', '') or ''
    tags = snippet.get('tags', []) or []
    
    updates = {}
    
    # Fix description
    new_desc = build_description(title, desc)
    if new_desc != desc:
        updates['description'] = new_desc
    
    # Fix tags
    if len(tags) < 10:
        new_tags = generate_topic_tags(title, tags)
        if len(new_tags) > len(tags):
            updates['tags'] = new_tags
    
    # Fix title
    new_title = fix_title(title)
    if new_title:
        updates['title'] = new_title
    
    if not updates:
        print(f"  [SKIP] {vid} ({views}v) - no changes")
        skip += 1
        continue
    
    if vid in ALREADY_FIXED:
        print(f"  [SKIP] {vid} ({views}v) - already fixed in previous run")
        skip += 1
        continue
    
    print(f"\n  [{vid}] {views}v: {title[:55]}")
    if 'title' in updates:
        print(f"    Title: {updates['title'][:55]}")
    if 'description' in updates:
        print(f"    Desc:  {len(updates['description'])} chars (was {len(desc)})")
    if 'tags' in updates:
        print(f"  Tags: {len(updates['tags'])} tags (was {len(tags)})")
    
    ok, msg = update_video(vid, updates)
    if ok:
        print(f"    -> OK")
        success += 1
    else:
        print(f"    -> FAIL: {msg}")
        fail += 1
    
    time.sleep(1.5)

print(f"\n{'='*70}")
print(f"DONE: {success} updated, {skip} unchanged, {fail} failed")
print(f"{'='*70}")
