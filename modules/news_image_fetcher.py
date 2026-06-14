# VERSION: 87.8
# MODULE: news_image_fetcher.py
# PURPOSE: Fetch REAL news photos from Indian news RSS feeds.
#          This replaces ComfyUI as the primary image source for scene images.
#          Uses direct RSS feeds from The Hindu, NDTV, Indian Express, Deccan Chronicle RSS
#          No API key needed. No redirects. Direct image URLs.
#
#          Priority: RSS feeds (real news) > ComfyUI (last resort)
#
#          v87.8: Fixed Gemini Visual gate was always returning True (ignoring NO).
#                  Raised keyword overlap threshold from >=2 to >=3 to prevent
#                  generic "Andhra Pradesh" matches returning irrelevant images.
# MODULE: news_image_fetcher.py
# PURPOSE: Fetch REAL news photos from Indian news RSS feeds.
#          This replaces ComfyUI as the primary image source for scene images.
#          Uses direct RSS feeds from The Hindu, NDTV, Indian Express,
#          Deccan Chronicle — all provide images via <enclosure> tags.
#          No API key needed. No redirects. Direct image URLs.
#
#          Priority: RSS feeds (real news) > Serper (if credits) > ComfyUI (last resort)

import os
import re
import hashlib
import requests
import urllib.parse
from io import BytesIO
from PIL import Image

# Indian news RSS feeds with direct image enclosure support
RSS_FEEDS = [
    # (name, url, referer)
    ("The Hindu - TN", "https://www.thehindu.com/news/national/tamil-nadu/feeder/default.rss", "https://www.thehindu.com/"),
    ("The Hindu - AP", "https://www.thehindu.com/news/national/andhra-pradesh/feeder/default.rss", "https://www.thehindu.com/"),
    ("The Hindu - TS", "https://www.thehindu.com/news/national/telangana/feeder/default.rss", "https://www.thehindu.com/"),
    ("The Hindu - National", "https://www.thehindu.com/news/national/feeder/default.rss", "https://www.thehindu.com/"),
    ("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories", "https://www.ndtv.com/"),
    ("Indian Express", "https://indianexpress.com/feed/", "https://indianexpress.com/"),
    ("Deccan Chronicle", "https://www.deccanchronicle.com/rss.xml", "https://www.deccanchronicle.com/"),
    ("News18", "https://www.news18.com/rss/india.xml", "https://www.news18.com/"),
    ("Times of India", "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms", "https://timesofindia.indiatimes.com/"),
]

# Domains known to cause copyright strikes — reject even from RSS
BLOCKED_IMAGE_DOMAINS = {
    "gettyimages", "shutterstock", "dreamstime", "alamy", "istockphoto",
    "stock.adobe", "bigstock", "depositphotos", "123rf", "pond5",
}

# Minimum image acceptance criteria
MIN_IMAGE_BYTES = 10 * 1024       # 10 KB — RSS enclosures are real photos
MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB cap
MIN_WIDTH = 400
MIN_HEIGHT = 300


def _strip_cdata(text):
    """Remove CDATA wrapper from RSS titles."""
    return text.replace("<![CDATA[", "").replace("]]>", "").strip()


def _keyword_overlap(topic, title):
    """Count matching keywords (>=4 chars) between topic and article title.
    
    v82.2: Expanded stop list with common 'bridge words' that appear in 
    nearly every news headline (live, updates, crisis, meeting, house, 
    called, backs, resolution, halt, leader, says, etc.). These words 
    create false matches between unrelated topics (e.g. "US House" 
    matching "Mamata Banerjee's House").
    """
    stop = {"this", "that", "with", "from", "have", "been", "were", "will",
            "would", "could", "should", "about", "their", "there", "these",
            "those", "which", "while", "after", "before", "under", "over",
            # v82.2: Bridge words — too common in ALL news headlines to be meaningful
            "live", "updates", "crisis", "meeting", "house", "called",
            "backs", "resolution", "halt", "leader", "says", "said",
            "party", "government", "minister", "chief", "leader",
            "leaders", "announces", "announce", "decision", "move",
            "big", "major", "key", "top", "new", "latest", "today",
            "yesterday", "day", "days", "week", "month", "year",
            "first", "second", "last", "next", "time", "plan",
            "action", "state", "states", "country", "nation",
            "people", "public", "support", "against", "also",
            "still", "even", "back", "down", "over", "turn",
            "set", "put", "take", "make", "give", "come",
            "want", "know", "need", "call", "talk", "hold",
            "news", "report", "reports", "reveal", "reveals"}
    topic_words = set(w.lower() for w in re.findall(r'[a-zA-Z]{4,}', topic)
                      if w.lower() not in stop)
    title_words = set(w.lower() for w in re.findall(r'[a-zA-Z]{4,}', title)
                      if w.lower() not in stop)
    return topic_words & title_words


def _validate_image_bytes(data):
    """Quick validation: size, magic bytes, PIL parse, dimensions."""
    if len(data) < MIN_IMAGE_BYTES:
        return False, f"too small ({len(data)} bytes)"
    if len(data) > MAX_IMAGE_BYTES:
        return False, f"too large ({len(data)} bytes)"

    # Magic bytes
    if data[:3] == b'\xff\xd8\xff':
        pass  # JPEG
    elif data[:4] == b'\x89PNG':
        pass  # PNG
    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        pass  # WebP
    else:
        return False, f"unknown format (hex: {data[:8].hex()})"

    # PIL parse + dimensions
    try:
        img = Image.open(BytesIO(data))
        img.verify()
    except Exception as e:
        return False, f"PIL verify failed: {e}"

    try:
        img = Image.open(BytesIO(data))
        w, h = img.size
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            return False, f"too small: {w}x{h}"
    except Exception as e:
        return False, f"dimension check failed: {e}"

    return True, "OK"


def _text_only_relevance_check(topic_title, article_title):
    """v87.2: Fallback text-only relevance check when Gemini Vision is unavailable.
    
    Requires >=2 non-generic keyword overlap between topic and article title.
    This is the same filter used in the main scoring loop, applied here as a
    safety net so RSS images aren't silently accepted when Gemini is down.
    """
    GENERIC_NEWS_WORDS = {"india", "us", "usa", "news", "live", "update",
                          "breaking", "latest", "top", "watch", "video",
                          "photo", "photos", "gallery", "pictures",
                          "report", "reports", "said", "says", "new",
                          "first", "last", "one", "two", "three",
                          "day", "days", "week", "month", "year",
                          "today", "yesterday", "tomorrow",
                          "gets", "get", "got", "give", "given",
                          "after", "before", "over", "under", "from",
                          "with", "into", "out", "off", "up", "down",
                          "the", "a", "an", "and", "or", "but", "for",
                          "not", "all", "any", "can", "has", "had",
                          "have", "was", "were", "been", "being",
                          "are", "is", "it", "its", "this", "that",
                          "these", "those", "what", "which", "who",
                          "how", "when", "where", "why", "will",
                          "would", "could", "should", "may", "might",
                          "more", "most", "some", "such", "than",
                          "then", "there", "their", "them", "they",
                          "about", "also", "just", "only", "very",
                          "much", "many", "well", "back", "even",
                          "still", "already", "since", "while",
                          "during", "between", "through", "across"}
    overlap = _keyword_overlap(topic_title, article_title)
    filtered = {w for w in overlap if w.lower() not in GENERIC_NEWS_WORDS}
    return len(filtered) >= 2


def _visual_relevance_check(image_data, topic_title, article_title):
    """v82.2: Use Gemini Vision API to verify downloaded image is visually related to topic.
    
    RSS <enclosure> images are often unrelated to the article — stock photos,
    sidebar trending images, or generic placeholders. This gate sends the image
    to Gemini with the topic context and gets a yes/no relevance judgment.
    
    v87.2: Two-tier fallback:
    1. Gemini Vision check (preferred) — fail-closed on explicit NO
    2. If Gemini unavailable (quota/timeout), fall back to text-only check:
       article title must have >=2 non-generic keyword overlap with topic
    """
    try:
        import base64
        
        # Get API key from env or .env
        _key = os.environ.get("GEMINI_API_KEY", "")
        if not _key:
            _env = os.path.expanduser("~/.env")
            if os.path.exists(_env):
                for line in open(_env):
                    if line.startswith("GEMINI_API_KEY="):
                        _key = line.strip().split("=", 1)[1].strip("\"'")
                        break
        if not _key:
            # No API key — fall back to text-only check
            return _text_only_relevance_check(topic_title, article_title)
        
        b64 = base64.b64encode(image_data).decode("utf-8")
        
        prompt_text = (
            "You are an image relevance checker for an Indian news video pipeline.\n"
            f"TOPIC: {topic_title}\n"
            f"ARTICLE: {article_title}\n\n"
            "Does this image show content that is VISUALLY relevant to this topic? "
            "Answer ONLY 'YES' or 'NO'.\n"
            "Say NO if the image shows: buildings/demolition, entertainment/celebrities, "
            "sports, international flags/scenes unrelated to Indian politics, "
            "stock photos, logos, or generic landscapes.\n"
            "Say YES only if the image clearly shows: Indian political figures, "
            "rallies/protests, parliament/assembly, or news footage directly related to the topic."
        )
        
        # v87.2: Tier 1 — text-only keyword overlap (fast, no API call)
        # Require >=2 non-generic overlapping words just to enter visual check
        _text_ok = _text_only_relevance_check(topic_title, article_title)
        if not _text_ok:
            return False  # Not enough keyword overlap — skip
        
        # v87.2: Tier 1.5 — strong text overlap (>=3 words) bypasses Gemini entirely
        # Avoids wasting API calls on obviously relevant articles
        GENERIC_NEWS_WORDS = {"india", "us", "usa", "news", "live", "update",
                              "breaking", "latest", "top", "watch", "video",
                              "photo", "photos", "gallery", "pictures",
                              "report", "reports", "said", "says", "new",
                              "first", "last", "one", "two", "three",
                              "day", "days", "week", "month", "year",
                              "today", "yesterday", "tomorrow",
                              "gets", "get", "got", "give", "given",
                              "after", "before", "over", "under", "from",
                              "with", "into", "out", "off", "up", "down",
                              "the", "a", "an", "and", "or", "but", "for",
                              "not", "all", "any", "can", "has", "had",
                              "have", "was", "were", "been", "being",
                              "are", "is", "it", "its", "this", "that",
                              "these", "those", "what", "which", "who",
                              "how", "when", "where", "why", "will",
                              "would", "could", "should", "may", "might",
                              "more", "most", "some", "such", "than",
                              "then", "there", "their", "them", "they",
                              "about", "also", "just", "only", "very",
                              "much", "many", "well", "back", "even",
                              "still", "already", "since", "while",
                              "during", "between", "through", "across"}
        _overlap = _keyword_overlap(topic_title, article_title)
        _overlap_filtered = {w for w in _overlap if w.lower() not in GENERIC_NEWS_WORDS}
        if len(_overlap_filtered) >= 3:
            return True  # Strong text match — skip Gemini, accept
        
        # v87.2: Tier 2 — Gemini Vision check for borderline cases (2-word overlap)
        # Gemini can reject if image content doesn't match, but can't override strong text match
        
        # Call Gemini Vision REST API directly
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                    {"text": prompt_text},
                ]
            }],
            "generationConfig": {"maxOutputTokens": 10, "temperature": 0.0}
        }
        
        resp = requests.post(url, json=payload, timeout=15,
                           headers={"Content-Type": "application/json"})
        if resp.status_code != 200:
            # Gemini API error — accept based on text overlap (already >=2)
            return True
        
        answer = ""
        for cand in resp.json().get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                answer += part.get("text", "")
        
        # v87.8: Respect Gemini's NO — reject if image is visually irrelevant
        answer_upper = answer.strip().upper()
        if answer_upper.startswith("NO"):
            return False
        return True
        
    except Exception as e:
        # Gemini unavailable — accept based on text overlap (already >=2)
        print(f"  [NewsImg] Visual gate Gemini error: {str(e)[:80]}")
        return True


def fetch_news_images(topic_title, count=5, used_hashes=None):
    """
    Fetch real news photos from Indian RSS feeds matching the topic.

    Args:
        topic_title: The news topic title (e.g. "Tamil Nadu BJP leader Annamalai meets Amit Shah")
        count: Number of images to fetch
        used_hashes: set of MD5 hashes already used (dedup)

    Returns:
        list of dicts: [{"path": str, "url": str, "source": str, "title": str, "article_url": str, "hash": str}]
    """
    if used_hashes is None:
        used_hashes = set()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    # Score all articles across all feeds
    scored_articles = []

    for feed_name, feed_url, referer in RSS_FEEDS:
        try:
            r = requests.get(feed_url, headers=headers, timeout=8)
            if r.status_code != 200:
                continue

            items = re.findall(r'<item>(.*?)</item>', r.text, re.DOTALL)

            for item in items:
                title_m = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
                link_m = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
                enc_m = re.search(r'<enclosure[^>]*url=["\'](.*?)["\']', item, re.IGNORECASE)
                media_m = re.search(r'<media:content[^>]*url=["\'](.*?)["\']', item, re.IGNORECASE)

                if not title_m:
                    continue

                title = _strip_cdata(title_m.group(1))
                link = _strip_cdata(link_m.group(1)) if link_m else ""

                # Get image URL — prefer enclosure (higher quality)
                img_url = None
                if enc_m:
                    img_url = enc_m.group(1)
                elif media_m:
                    img_url = media_m.group(1)

                if not img_url:
                    continue

                # Skip blocked domains
                domain = urllib.parse.urlparse(img_url).netloc.lower()
                if any(bd in domain for bd in BLOCKED_IMAGE_DOMAINS):
                    continue

                # Score relevance
                overlap = _keyword_overlap(topic_title, title)
                if not overlap:
                    continue

                # v82.1: Minimum relevance gate — reject weak single-word matches
                # Common words like "meeting", "house", "congress" match everything.
                # Require >=2 keyword overlap, OR >=1 if it's a rare proper noun.
                # v86.2: Rare noun alone is NOT enough — must also have >=1 other keyword
                # overlap to prevent "Modi" in script text matching every Modi article
                # when the topic is actually about US-Iran war.
                # v87.2: Generic news words don't count as overlap — "India", "US",
                # "news", "live", "update", "breaking" are in every headline.
                GENERIC_NEWS_WORDS = {"india", "us", "usa", "news", "live", "update",
                                      "breaking", "latest", "top", "watch", "video",
                                      "photo", "photos", "gallery", "pictures",
                                      "report", "reports", "said", "says", "new",
                                      "first", "last", "one", "two", "three",
                                      "day", "days", "week", "month", "year",
                                      "today", "yesterday", "tomorrow",
                                      "gets", "get", "got", "give", "given",
                                      "after", "before", "over", "under", "from",
                                      "with", "into", "out", "off", "up", "down",
                                      "the", "a", "an", "and", "or", "but", "for",
                                      "not", "all", "any", "can", "has", "had",
                                      "have", "was", "were", "been", "being",
                                      "are", "is", "it", "its", "this", "that",
                                      "these", "those", "what", "which", "who",
                                      "how", "when", "where", "why", "will",
                                      "would", "could", "should", "may", "might",
                                      "more", "most", "some", "such", "than",
                                      "then", "there", "their", "them", "they",
                                      "about", "also", "just", "only", "very",
                                      "much", "many", "well", "back", "even",
                                      "still", "already", "since", "while",
                                      "during", "between", "through", "across"}
                overlap_filtered = {w for w in overlap if w.lower() not in GENERIC_NEWS_WORDS}
                # v87.8: Raised from >=2 to >=3 — "Andhra Pradesh" alone matches
                # every AP article (forest, ship, etc.) even when topic is about
                # child rights / social media. Require 3+ specific keywords.
                if len(overlap_filtered) < 3:
                    # Not enough meaningful overlap — skip
                    continue

                # v86.3: Person-subject mismatch check
                # Articles like "PM Modi speaks to Amir of Kuwait about West Asia"
                # pass keyword overlap (west, asia) but the IMAGE shows Modi, not the war.
                # If the article title starts with a person reference and the topic
                # is NOT about that person, reject it.
                _PERSON_PREFIXES = [
                    # Only list people who are COMMENTATORS/OBSERVERS, not primary actors.
                    # "Trump" is NOT here because he IS a primary actor in US-Iran war topics.
                    # "Modi" IS here because he's an Indian PM commenting on West Asia, not a war actor.
                    "pm modi", "narendra modi", "pm narendra",
                    "pm rishi", "rishi sunak",
                    "mamata banerjee", "rahul gandhi",
                    "yogi adityanath", "arvind kejriwal",
                    "nirmala sitharaman", "rajnath singh",
                    "amit shah",
                    "sanjiv goenka", "goenka",
                    "shreyas iyer", "iyer",
                ]
                _title_lower = title.lower().strip()
                _topic_lower = topic_title.lower()
                _person_rejected = False
                for _prefix in _PERSON_PREFIXES:
                    if _title_lower.startswith(_prefix):
                        _person_name = _prefix.replace("pm ", "").strip()
                        if _person_name not in _topic_lower and _prefix not in _topic_lower:
                            print(f"  [NewsImg] REJECT person mismatch: '{title[:50]}' (person: {_person_name})")
                            _person_rejected = True
                        break
                if _person_rejected:
                    continue

                # Bonus for PTI/ANI images (professional news agency photos)
                bonus = 0
                if "pti" in img_url.lower() or "ani" in img_url.lower():
                    bonus += 3
                # Bonus for domain match with topic state
                topic_lower = topic_title.lower()
                if "tamil nadu" in topic_lower and ("tamil-nadu" in link or "tamil-nadu" in img_url):
                    bonus += 2
                elif "andhra" in topic_lower and ("andhra-pradesh" in link or "andhra" in img_url):
                    bonus += 2
                elif "telangana" in topic_lower and ("telangana" in link or "telangana" in img_url):
                    bonus += 2

                score = len(overlap_filtered) + bonus
                scored_articles.append({
                    "score": score,
                    "title": title,
                    "img_url": img_url,
                    "article_url": link,
                    "source": feed_name,
                    "referer": referer,
                })

        except Exception as e:
            print(f"  [NewsImg] RSS feed {feed_name} failed: {e}")
            continue

    # Sort by relevance score (highest first)
    scored_articles.sort(key=lambda x: x["score"], reverse=True)

    print(f"  [NewsImg] Found {len(scored_articles)} relevant articles across RSS feeds")

    # Download and validate
    results = []
    for article in scored_articles:
        if len(results) >= count:
            break

        try:
            dl_headers = {
                'User-Agent': headers['User-Agent'],
                'Referer': article["referer"],
            }
            resp = requests.get(article["img_url"], headers=dl_headers, timeout=10)
            if resp.status_code != 200:
                continue

            data = resp.content

            # Skip tiny images (tracking pixels, icons)
            if len(data) < MIN_IMAGE_BYTES:
                continue

            # Dedup check
            data_hash = hashlib.md5(data).hexdigest()
            if data_hash in used_hashes:
                print(f"  [NewsImg] Skip duplicate ({data_hash[:12]}): {article['source']}")
                continue

            # Validate
            valid, reason = _validate_image_bytes(data)
            if not valid:
                print(f"  [NewsImg] Validate fail ({reason}): {article['source']}")
                continue

            # v82.2: Visual relevance gate — verify image content matches topic
            # RSS enclosures sometimes have unrelated stock/sidebar images.
            # Gemini checks: does this image show content related to the topic?
            _vis_ok = _visual_relevance_check(data, topic_title, article["title"])
            if not _vis_ok:
                print(f"  [NewsImg] REJECTED by visual gate: {article['source']} | {article['title'][:50]}")
                continue

            used_hashes.add(data_hash)

            results.append({
                "url": article["img_url"],
                "source": article["source"],
                "title": article["title"],
                "article_url": article["article_url"],
                "hash": data_hash,
                "data": data,
                "size": len(data),
            })
            print(f"  [NewsImg] Accepted: {article['source']} | {article['title'][:60]} | {len(data)//1024}KB")

        except Exception as e:
            print(f"  [NewsImg] Download failed ({article['source']}): {e}")
            continue

    print(f"  [NewsImg] Total fetched: {len(results)} real news photos")
    return results


def save_news_images(topic_title, output_dir, count=5, used_hashes=None):
    """
    Fetch and save news images to disk.
    Returns list of saved file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    articles = fetch_news_images(topic_title, count, used_hashes)
    paths = []
    for i, article in enumerate(articles):
        path = os.path.join(output_dir, f"scene_img_{i}.jpg")
        with open(path, 'wb') as f:
            f.write(article["data"])
        paths.append(path)
    return paths
