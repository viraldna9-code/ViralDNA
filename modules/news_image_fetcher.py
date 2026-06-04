# VERSION: 81.0
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
    """Count matching keywords (>=4 chars) between topic and article title."""
    stop = {"this", "that", "with", "from", "have", "been", "were", "will",
            "would", "could", "should", "about", "their", "there", "these",
            "those", "which", "while", "after", "before", "under", "over"}
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
                RARE_NOUNS = {"trinamool", "mamata", "banerjee", "pawan", "kalyan",
                              "jana sena", "revanth", "reddy", "chandrababu", "naidu",
                              "kcr", "ktr", "modi", "kejriwal", "yogi", "adityanath",
                              "rahul", "gandhi", "amaravati", "telangana", "andhra",
                              "hyderabad", "vijayawada", "vizag", "kolkata", "bengal",
                              "sharad", "pawar", "uddhav", "thackeray", "nitish", "kumar",
                              "lalu", "prasad", "mamata", "tmc", "bjp", "dmk", "aiadmk"}
                overlap_lower = {w.lower() for w in overlap}
                has_rare = bool(overlap_lower & RARE_NOUNS)
                if len(overlap) < 2 and not has_rare:
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

                score = len(overlap) + bonus
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
