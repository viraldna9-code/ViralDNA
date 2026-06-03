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

# Words extracted from topic titles that are NOT person names (skip words)
PERSON_SKIP_WORDS = {
    "and", "the", "with", "for", "from", "new", "old", "big", "small",
    "meets", "visit", "talks", "meeting", "after", "over", "under",
    "then", "now", "today", "yesterday", "first", "last", "next",
    "more", "most", "some", "all", "any", "each", "every", "both",
    "india", "indian", "delhi", "news", "minister", "chief", "leader",
    "president", "bjp", "congress", "tdp", "ysrcp", "mla", "mp",
    "pm", "cm", "govt", "government", "state", "central", "party",
    "telangana", "andhra", "tamil", "nadu", "telugu", "karnataka",
    "rally", "rallies", "event", "events", "press", "media",
}


def _extract_person_names(topic_title: str) -> list[str]:
    """Extract likely person names (capitalized proper nouns) from a topic title."""
    names = []
    for word in re.findall(r'\b[A-Z][a-z]{2,}\b', topic_title or ""):
        if word.lower() not in PERSON_SKIP_WORDS:
            names.append(word.lower())
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
