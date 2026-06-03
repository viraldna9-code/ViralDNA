# VERSION: 80.0
# MODULE: image_validator.py
# PURPOSE: Shared image validation — used by BOTH VisualFetcher AND VideoAssembler.
#          This is the SINGLE source of truth for watermark/copyright/person checks.
#          Created during forensic audit to fix the dual-pipeline architecture flaw.
#
#          Checks:
#          1. Watermark/copyright domain rejection (stock photo sites)
#          2. EXIF copyright/Artist tag rejection
#          3. Metadata text rejection (source/title contains copyright strings)
#          4. Person-name verification (image title must contain topic person name)

import re

# Known stock photo / watermark domains that cause copyright strikes
REJECT_DOMAINS = {
    "gettyimages", "shutterstock", "dreamstime", "alamy", "istockphoto",
    "stock.adobe", "bigstock", "depositphotos", "123rf", "pond5",
    "canstockphoto", "fotolia", "featurepics", "photodune",
}

# Copyright strings that indicate watermarked/stock photos when found in
# EXIF tags or image metadata (title, source field)
REJECT_COPYRIGHT = {
    "hindustan times", "getty images", "shutterstock", "dreamstime",
    "alamy", "istock", "adobe stock", "bigstock", "depositphotos",
    "reuters", "afp", "ani",  # news agency watermarks cause strikes
}

# Words extracted from topic titles/scripts that are NOT person names.
# Includes: grammar words, geography, politics, common English words that
# appear capitalized in sentences (This, What, Did, Home, Union, etc.)
PERSON_SKIP_WORDS = {
    # Grammar / common English
    "and", "the", "with", "for", "from", "new", "old", "big", "small",
    "meets", "visit", "talks", "meeting", "after", "over", "under",
    "then", "now", "today", "yesterday", "tomorrow", "first", "last", "next",
    "more", "most", "some", "all", "any", "each", "every", "both",
    "this", "that", "these", "those", "what", "when", "where", "which",
    "who", "how", "why", "not", "but", "its", "his", "her", "our",
    "did", "does", "done", "had", "has", "was", "were", "been", "being",
    "will", "would", "could", "should", "can", "may", "might", "shall",
    "get", "got", "getting", "make", "made", "making", "take", "took",
    "come", "came", "coming", "go", "went", "going", "gone",
    "say", "said", "saying", "tell", "told", "telling",
    "see", "saw", "seen", "seeing", "look", "looked", "looking",
    "give", "gave", "given", "giving", "find", "found", "finding",
    "use", "used", "using", "put", "puts", "putting",
    "try", "tried", "trying", "keep", "kept", "keeping",
    "let", "lets", "letting", "begin", "began", "beginning",
    "show", "showed", "shown", "showing", "hear", "heard", "hearing",
    "play", "played", "playing", "run", "ran", "running",
    "move", "moved", "moving", "live", "lived", "living",
    "believe", "change", "happen", "include", "increase", "continue",
    "set", "learn", "lead", "understand", "watch", "follow", "stop",
    "create", "speak", "read", "spend", "grow", "open", "walk", "win",
    "teach", "offer", "remember", "love", "consider", "appear", "buy",
    "wait", "serve", "die", "send", "expect", "build", "stay", "fall",
    "cut", "reach", "kill", "remain", "suggest", "raise", "pass", "sell",
    "require", "report", "decide", "pull", "develop",
    # Geography / politics
    "india", "indian", "delhi", "news", "minister", "chief", "leader",
    "president", "bjp", "congress", "tdp", "ysrcp", "mla", "mp",
    "pm", "cm", "govt", "government", "state", "central", "party",
    "telangana", "andhra", "tamil", "nadu", "telugu", "karnataka",
    "rally", "rallies", "event", "events", "press", "media",
    "chennai", "hyderabad", "bangalore", "mumbai", "kolkata", "tirupati",
    "visakhapatnam", "vijayawada", "guntur", "nellore", "kurnool",
    "warangal", "karimnagar", "nizamabad", "khammam", "rajahmundry",
    # Common nouns that appear capitalized
    "home", "union", "national", "international", "global", "local",
    "south", "north", "east", "west", "political", "social", "economic",
    "public", "private", "official", "final", "main", "major", "minor",
    "high", "low", "long", "short", "large", "late", "early",
    "good", "bad", "great", "little", "right", "wrong", "real", "free",
    "times", "time", "year", "years", "day", "days", "week", "month",
    "people", "man", "men", "woman", "women", "group", "side",
    # Weather / disasters
    "heavy", "rain", "rains", "flood", "flooding", "storm", "cyclone",
}


def _extract_person_names(topic_title: str) -> list[str]:
    """Extract likely person names (capitalized proper nouns) from a topic title.
    Strips news source suffixes like ' - The Hindu', ' - Times of India' etc.
    Uses two strategies:
    1. Consecutive capitalized word pairs (First Last) — almost always names
    2. Single capitalized words after initials (K. Annamalai) or before/after
       known name markers (meets, with, and, vs, etc.)
    """
    import re as _re
    # Strip common news source suffixes: " - Source Name"
    cleaned = _re.sub(
        r'\s*[-–—]\s*(The\s+)?'
        r'(Hindu|Times|Express|Tribune|Guardian|Independent|Post|Herald|BBC|CNN|NDTV|News|India|Deccan|Sakshi|Eenadu|Andhra|Telangana).*$',
        '', topic_title, flags=_re.IGNORECASE
    )

    names = []
    words = _re.findall(r'\b[A-Z][a-z]{2,}\b', cleaned)

    # Strategy 1: Consecutive capitalized pairs (First Last)
    for i in range(len(words) - 1):
        w1, w2 = words[i].lower(), words[i + 1].lower()
        if w1 not in PERSON_SKIP_WORDS and w2 not in PERSON_SKIP_WORDS:
            names.append(w2)  # Last name is the key identifier
            names.append(w1)  # First name too

    # Strategy 2: Single words near name markers or after initials
    name_markers = {'meets', 'with', 'and', 'vs', 'visit', 'talks', 'meeting'}
    for i, word in enumerate(words):
        w = word.lower()
        if w in PERSON_SKIP_WORDS or w in names:
            continue
        # After initial (K. Annamalai)
        if i > 0 and len(words[i - 1]) <= 2 and words[i - 1].endswith('.'):
            names.append(w)
            continue
        # Before/after name markers
        if i > 0 and words[i - 1].lower() in name_markers:
            names.append(w)
            continue
        if i < len(words) - 1 and words[i + 1].lower() in name_markers:
            names.append(w)
            continue

    return list(set(names))


def is_watermarked_stock(img_path: str, img_url: str = "",
                          img_title: str = "", img_source: str = "") -> tuple[bool, str]:
    """
    Reject stock photos with watermarks/copyright that cause channel strikes.
    Returns (is_rejected, reason_string).
    """
    # Check URL domain against known stock photo sites
    if img_url:
        from urllib.parse import urlparse
        domain = urlparse(img_url).netloc.lower()
        for rd in REJECT_DOMAINS:
            if rd in domain:
                return True, f"stock domain: {rd}"

    # Check EXIF copyright/Artist tags
    try:
        from PIL import Image as PILImage
        from PIL.ExifTags import TAGS as EXIF_TAGS
        im = PILImage.open(img_path)
        exif = im.getexif()
        if exif:
            for tid, val in exif.items():
                tag = EXIF_TAGS.get(tid, tid)
                if tag in ("Copyright", "Artist", "ImageDescription"):
                    val_lower = str(val).lower()
                    for rc in REJECT_COPYRIGHT:
                        if rc in val_lower:
                            return True, f"EXIF {tag}: {rc}"
    except Exception:
        pass

    # Check title/source text metadata
    meta_text = (img_title + " " + img_source).lower()
    for rc in REJECT_COPYRIGHT:
        if rc in meta_text:
            return True, f"meta: {rc}"

    return False, ""


def check_person_name_in_title(topic_title: str, img_title: str) -> tuple[bool, list[str]]:
    """
    If the topic mentions a specific person (capitalized proper noun),
    the image title MUST contain at least one of those names.
    Returns (passed, list_of_expected_names).
    """
    person_names = _extract_person_names(topic_title)
    if not person_names:
        return True, []  # No person names found, skip check
    img_lower = img_title.lower()
    for name in person_names:
        if name in img_lower:
            return True, person_names
    return False, person_names  # None of the person names found in image title
