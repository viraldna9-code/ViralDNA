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

# Countries, regions, cities that appear capitalized in news headlines.
# These are NOT person names — used to filter out false positives from
# the person-name extraction in _extract_person_names().
GEO_AND_COUNTRY_WORDS = {
    "afghanistan", "africa", "african", "algeria", "america", "american",
    "angola", "antarctica", "argentina", "armenia", "asia", "asian",
    "australia", "austrian", "azerbaijan", "bahrain", "bangladesh",
    "belarus", "belgium", "bhutan", "bolivia", "bosnia", "botswana",
    "brazil", "british", "bulgaria", "burkina", "burundi", "cambodia",
    "cameroon", "canada", "caribbean", "central", "chad", "chile",
    "china", "chinese", "colombia", "comoros", "congo", "costa",
    "croatia", "cuba", "cyprus", "czech", "denmark", "djibouti",
    "dominica", "east", "ecuador", "egypt", "egyptian", "eritrea",
    "estonia", "eswatini", "ethiopia", "europe", "european", "fiji",
    "finland", "france", "gabon", "gambia", "georgia", "germany",
    "ghana", "global", "greece", "grenada", "guatemala", "guinea",
    "guyana", "haiti", "honduras", "hungary", "iceland", "india",
    "indian", "indonesia", "iran", "iraqi", "iraq", "ireland", "israel",
    "israeli", "italy", "ivory", "jamaica", "japan", "japanese",
    "jordan", "kazakhstan", "kenya", "kuwait", "kyrgyzstan", "laos",
    "latvia", "lebanon", "lesotho", "liberia", "libya", "liechtenstein",
    "lithuania", "luxembourg", "madagascar", "malawi", "malaysia",
    "maldives", "mali", "malta", "mauritania", "mauritius", "mexico",
    "middle", "moldova", "monaco", "mongolia", "montenegro", "morocco",
    "mozambique", "myanmar", "namibia", "nepal", "netherlands", "new",
    "nicaragua", "niger", "nigeria", "north", "norway", "oman",
    "pakistan", "pakistani", "palestine", "palestinian", "panama",
    "papua", "paraguay", "peru", "philippines", "poland", "portugal",
    "qatar", "romania", "russia", "russian", "rwanda", "saudi",
    "senegal", "serbia", "seychelles", "sierra", "singapore",
    "slovakia", "slovenia", "somalia", "south", "spain", "sri",
    "sudan", "suriname", "sweden", "switzerland", "syria", "syrian",
    "taiwan", "tajikistan", "tanzania", "thailand", "timor", "togo",
    "trinidad", "tunisia", "turkey", "turkish", "turkmenistan",
    "uganda", "ukraine", "uruguay", "uzbekistan", "vanuatu", "vatican",
    "venezuela", "vietnam", "west", "yemen", "zambia", "zimbabwe",
    # Regions and directional terms
    "kashmir", "korea", "kurdistan", "balkans", "gaza", "sahara",
    "sinai", "himalayas", "arabian", "mediterranean", "pacific",
    "atlantic",
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
    "anyone", "everyone", "someone", "nobody", "anybody", "everybody",
    "somebody", "nothing", "everything", "something", "anything",
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
    "president", "bjp", "congress", "tdp", "ysrcp", "mla", "mp", "aap", "shiv", "sena",
 "trinamool", "tmc", "dmk", "aiadmk", "ncp", "rjd", "jd", "bsp", "sp",
 "cpi", "cpim", "ncp", "aitc", "npp", "mns", "ncp",
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
    # Months / seasons
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "spring", "summer", "autumn", "winter", "monsoon",
    # Organizations / infrastructure
    "railways", "airports", "schools", "colleges", "universities",
    "hospitals", "courts", "police", "army", "navy", "airforce",
    "supreme", "high", "district", "civil", "criminal",
    "rajya", "sabha", "lok", "vidhan", "sansad", "parliament",
    "municipal", "corporation", "panchayat", "zilla", "mandal",
    # Technology / products
    "google", "apple", "microsoft", "amazon", "facebook", "meta",
    "twitter", "youtube", "instagram", "whatsapp", "telegram",
    # Finance / budget / governance
    "budget", "finance", "economic", "fiscal", "monetary", "gst", "tax",
    "reserve", "bank", "rbi", "sebi", "stock", "market", "sensex", "nifty",
    "inflation", "gdp", "trade", "export", "import", "rupee", "dollar",
    # Education / health
    "education", "health", "medical", "doctor", "patient", "hospital",
    "school", "college", "university", "student", "teacher", "exam",
    # Sports
    "cricket", "football", "hockey", "tennis", "olympics", "ipl",
    "match", "tournament", "championship", "league", "score", "wicket",
}

# Merge geo words into skip words for the extraction function
_ALL_SKIP_WORDS = PERSON_SKIP_WORDS | GEO_AND_COUNTRY_WORDS


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
        if w1 not in _ALL_SKIP_WORDS and w2 not in _ALL_SKIP_WORDS:
            names.append(w2)  # Last name is the key identifier
            names.append(w1)  # First name too

    # Strategy 2: Single words near name markers or after initials
    name_markers = {'meets', 'with', 'and', 'vs', 'visit', 'talks', 'meeting'}
    for i, word in enumerate(words):
        w = word.lower()
        if w in _ALL_SKIP_WORDS or w in names:
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

    # Post-filter: remove names that are common English words (not proper nouns)
    # This catches false positives like "Quote", "Anyone", "Today" etc.
    _common_english = {
        "about", "above", "after", "again", "also", "another", "around",
        "away", "back", "because", "before", "being", "below", "between",
        "both", "came", "come", "could", "days", "does", "down", "each",
        "even", "ever", "every", "from", "gets", "give", "going", "gone",
        "good", "gott", "great", "hand", "have", "head", "here", "high",
        "home", "into", "just", "keep", "kind", "knew", "know", "last",
        "left", "life", "like", "live", "long", "look", "made", "make",
        "many", "mean", "more", "most", "much", "must", "name", "near",
        "need", "next", "only", "other", "over", "part", "place", "point",
        "right", "said", "same", "seem", "show", "side", "some", "such",
        "take", "tell", "than", "that", "them", "then", "there", "these",
        "they", "thing", "think", "this", "those", "though", "through",
        "time", "today", "together", "told", "took", "turn", "under",
        "until", "upon", "very", "want", "well", "went", "were", "what",
        "when", "where", "which", "while", "white", "whole", "will",
        "with", "work", "world", "would", "year", "years", "young",
        "your", "quote", "quotes", "daily", "breaking", "exclusive",
        "special", "latest", "update", "updates", "news", "report",
        "story", "stories", "watch", "video", "photo", "photos",
        "image", "images", "picture", "pictures", "click", "read",
        "share", "comment", "like", "follow", "subscribe", "join",
        "sign", "log", "get", "got", "win", "won", "lose", "lost",
        "end", "ends", "start", "starts", "stop", "stops", "run", "runs",
        "play", "plays", "hit", "hits", "set", "sets", "put", "puts",
        "cut", "cuts", "add", "adds", "pay", "pays", "buy", "buys",
        "sell", "sells", "send", "sends", "call", "calls", "ask", "asks",
        "try", "tries", "use", "uses", "find", "finds", "help", "helps",
        "hold", "holds", "open", "opens", "close", "closes", "turn", "turns",
        "move", "moves", "live", "lives", "die", "dies", "kill", "kills",
        "fall", "falls", "rise", "rises", "grow", "grows", "lead", "leads",
        "meet", "meets", "talk", "talks", "speak", "speaks", "say", "says",
        "tell", "tells", "show", "shows", "hear", "hears", "read", "reads",
        "write", "writes", "learn", "learns", "teach", "teaches", "study",
        "change", "changes", "happen", "happens", "include", "includes",
        "continue", "continues", "increase", "increases", "decrease",
        "develop", "develops", "create", "creates", "build", "builds",
        "break", "breaks", "destroy", "destroys", "damage", "damages",
        "attack", "attacks", "defend", "defends", "fight", "fights",
        "war", "wars", "peace", "deal", "deals", "plan", "plans",
        "decision", "decisions", "result", "results", "effect", "effects",
        "cause", "causes", "reason", "reasons", "problem", "problems",
        "solution", "solutions", "question", "questions", "answer", "answers",
        "issue", "issues", "matter", "matters", "case", "cases",
        "example", "examples", "fact", "facts", "idea", "ideas",
        "thought", "thoughts", "view", "views", "opinion", "opinions",
        "belief", "beliefs", "feeling", "feelings", "emotion", "emotions",
        "love", "hate", "fear", "hope", "wish", "dream", "goal",
        "success", "failure", "win", "loss", "victory", "defeat",
        "power", "force", "strength", "weakness", "advantage", "disadvantage",
        "benefit", "cost", "price", "value", "worth", "quality", "quantity",
        "amount", "number", "level", "rate", "speed", "size", "shape",
        "color", "form", "type", "sort", "kind", "class", "group",
        "team", "crew", "staff", "force", "army", "navy", "police",
        "court", "judge", "lawyer", "doctor", "nurse", "patient",
        "student", "teacher", "professor", "principal", "director",
        "manager", "boss", "worker", "employee", "employer", "owner",
        "member", "leader", "chief", "head", "chairman", "president",
        "minister", "secretary", "officer", "official", "agent",
        "expert", "specialist", "professional", "amateur", "beginner",
        "anyone", "everyone", "someone", "nobody", "anybody", "everybody",
        "somebody", "nothing", "everything", "something", "anything",
        # Nationality adjectives (not person names)
        "iranian", "american", "indian", "british", "chinese", "russian",
        "pakistani", "israeli", "palestinian", "ukrainian", "afghan",
        "african", "european", "asian", "australian", "canadian",
        "mexican", "brazilian", "japanese", "korean", "vietnamese",
        "turkish", "egyptian", "syrian", "iraqi", "saudi", "yemeni",
        "filipino", "indonesian", "malaysian", "thai", "nepali",
        "bangladeshi", "sri", "lankan", "israel", "lebanese", "jordanian",
        "english", "french", "german", "spanish", "italian", "portuguese",
        "dutch", "polish", "swedish", "norwegian", "danish", "finnish",
    }
    names = [n for n in names if n not in _common_english]

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


def check_person_name_in_title(topic_title: str, img_title: str, is_hero: bool = False) -> tuple[bool, list[str]]:
    """
    If the topic mentions a specific person (capitalized proper noun),
    the image title MUST contain at least one of those names.
    Only enforced for hero (first) images — fallback images skip this check
    because stock photo sites rarely have images with specific person names.
    Returns (passed, list_of_expected_names).
    """
    # Only check person names for hero images
    if not is_hero:
        return True, []
    person_names = _extract_person_names(topic_title)
    if not person_names:
        return True, []  # No person names found, skip check
    img_lower = img_title.lower()
    for name in person_names:
        if name in img_lower:
            return True, person_names
    return False, person_names  # None of the person names found in image title
