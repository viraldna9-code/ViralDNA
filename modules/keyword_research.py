# VERSION: 1.0
# MODULE: keyword_research.py
# PURPOSE: Dynamic keyword research for VDNA 3.0 script generation.
#          Replaces static HIGH_SEARCH_KEYWORDS with real-time data from:
#            1. Google Trends RSS (India) – trending topics + traffic scores
#            2. YouTube/Google Autocomplete – what people actually type
#            3. Keyword overlap scoring – match topic entity to search phrases
#          Called by ScriptGenerator._inject_search_keywords()

import json
import os
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# Cache file for trending keywords (refreshed every 6 hours)
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "vdna")
CACHE_FILE = os.path.join(CACHE_DIR, "keyword_cache.json")
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _load_cache():
    """Load cached keywords from disk. Returns dict or None if stale/missing."""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
        cached_time = data.get("_timestamp", 0)
        if (time.time() - cached_time) > CACHE_TTL_SECONDS:
            return None
        return data.get("keywords", {})
    except Exception:
        return None


def _save_cache(keywords: dict):
    """Save keywords to disk cache."""
    _ensure_cache_dir()
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"_timestamp": time.time(), "keywords": keywords}, f, indent=2)
    except Exception:
        pass


def fetch_google_trends_keywords() -> dict:
    """
    Fetch real-time trending searches from Google Trends India RSS.
    Returns dict: {search_phrase: traffic_score_approx}
    """
    trends = {}
    try:
        url = "https://trends.google.com/trending/rss?geo=IN"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.read())
            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                traffic_elem = item.find("{https://trends.google.com/trending/rss}approx_traffic")
                traffic_str = traffic_elem.text if traffic_elem is not None else ""
                if title and traffic_str:
                    try:
                        traffic = int(traffic_str.replace("+", "").replace(",", ""))
                    except ValueError:
                        traffic = 100
                    trends[title.lower()] = traffic
    except Exception:
        pass
    return trends


def fetch_youtube_autocomplete(query: str) -> list:
    """
    Fetch Google/YouTube autocomplete suggestions for a query.
    Returns list of suggested search phrases (raw strings).
    """
    suggestions = []
    try:
        url = (
            "https://suggestqueries.google.com/complete/search"
            f"?client=youtube&ds=yt&q={urllib.parse.quote(query)}"
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            # Response is wrapped: window.google.ac.h([...])
            # Extract the JSON array portion
            start = raw.index("(") + 1
            end = raw.rindex(")")
            data = json.loads(raw[start:end])
            suggestions = data[1] if len(data) > 1 else []
            # Suggestions are strings or [string, ...] tuples — extract just the phrase strings
            clean = []
            for s in suggestions:
                if isinstance(s, str):
                    clean.append(s)
                elif isinstance(s, list) and len(s) > 0 and isinstance(s[0], str):
                    clean.append(s[0])
            suggestions = clean
    except Exception:
        pass
    return suggestions


def _extract_keywords_from_title(title: str) -> list:
    """Extract meaningful search keywords from an article title."""
    stop_words = {
        "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
        "her", "was", "one", "our", "out", "new", "now", "how", "its", "may",
        "get", "has", "him", "his", "who", "did", "own", "say", "she", "too",
        "use", "with", "this", "will", "your", "from", "they", "been", "have",
        "what", "when", "them", "then", "come", "could", "each", "make", "than",
        "breaking", "urgent", "news", "update", "latest", "today", "just",
        "in", "on", "at", "to", "of", "by", "as", "is", "it", "be", "or", "an",
        "if", "so", "no", "up", "go", "do", "he", "we",
        "explain", "analysis", "report", "says", "said",
        "over", "after", "before", "about", "into", "also", "more",
    }
    words = re.findall(r'[a-zA-Z0-9]+', title.lower())
    return [w for w in words if len(w) > 2 and w not in stop_words and not w.isdigit()]


def _compute_relevance_score(candidate: str, topic_keywords: list, traffic: int) -> float:
    """
    Compute relevance score for a candidate search phrase against the topic's keywords.
    Higher = better match + more traffic.
    """
    score = 0.0
    cand_lower = candidate.lower()

    # Traffic component (log scale so 1000+ doesn't dominate entirely)
    if traffic > 0:
        score += min(1.0, 0.3 * (traffic / 10000.0))

    # Keyword overlap: how many topic keywords appear in this candidate phrase
    if topic_keywords:
        overlap = sum(1 for kw in topic_keywords if kw in cand_lower)
        score += overlap * 0.3  # Each matching keyword = +0.3

    # Bonus: exact phrase match (highest relevance)
    if any(kw == cand_lower for kw in topic_keywords):
        score += 0.5

    # Bonus: candidate starts with a topic entity (highly searchable)
    if topic_keywords and cand_lower.startswith(topic_keywords[0]):
        score += 0.2

    return score


def research_keywords_for_topic(title: str, description: str = "") -> dict:
    """
    Main entry point: research keywords for a breaking news topic.
    Called by ScriptGenerator._inject_search_keywords.

    Returns dict: {
        "best_keyword": str,       # highest-scoring keyword phrase
        "alternatives": list[str], # other good options (max 3)
        "source": str,             # "live" or "cache" or "fallback"
    }
    """
    # Extract topic keywords for relevance matching
    title_kws = _extract_keywords_from_title(title)
    desc_kws = _extract_keywords_from_title(description) if description else []
    all_topic_kws = list(dict.fromkeys(title_kws + desc_kws))  # dedup, preserve order

    # ── Step 1: Try cache ──
    cached = _load_cache()
    if cached:
        # Find best match from cached Google Trends data
        scored = []
        for phrase, traffic in cached.items():
            s = _compute_relevance_score(phrase, all_topic_kws, traffic)
            # Apply same strict filter: must have keyword overlap
            has_overlap = any(kw in phrase for kw in all_topic_kws) if all_topic_kws else False
            if has_overlap:
                scored.append((phrase, s, traffic))
        scored.sort(key=lambda x: x[1], reverse=True)
        if scored and scored[0][1] > 0:
            # Filter out suggestions too similar to title
            filtered = []
            title_words = set(title.lower().split())
            for s in scored:
                kw_words = set(s[0].lower().split())
                if title_words and kw_words:
                    overlap_ratio = len(kw_words & title_words) / len(kw_words)
                    if overlap_ratio < 0.8:
                        filtered.append(s)
                else:
                    filtered.append(s)
            if filtered:
                alternatives = [s[0] for s in filtered[1:4] if s[1] > 0]
                return {
                    "best_keyword": filtered[0][0].title(),
                    "alternatives": [a.title() for a in alternatives],
                    "source": "cache",
                }

    # ── Step 2: Fetch live Google Trends ──
    live_trends = fetch_google_trends_keywords()

    # ── Step 3: Fetch YouTube autocomplete for topic ──
    autocomplete_phrases = []
    if all_topic_kws:
        # Strategy 1: Full title as query (most specific, catches exact match trends)
        title_query = title[:60]  # truncate to avoid URL issues
        autocomplete_phrases.extend(fetch_youtube_autocomplete(title_query))

        # Strategy 2: Compound queries (top 2-3 keywords)
        if len(all_topic_kws) >= 2:
            compound = " ".join(all_topic_kws[:3])
            autocomplete_phrases.extend(fetch_youtube_autocomplete(compound))

        # Strategy 3: Single most-specific keyword (longest, usually a named entity)
        top_kw = max(all_topic_kws, key=len)
        if len(top_kw) > 4:  # skip short generic words
            autocomplete_phrases.extend(fetch_youtube_autocomplete(top_kw))

    # Deduplicate while preserving order
    seen = set()
    unique_sugs = []
    for s in autocomplete_phrases:
        sl = s.lower().strip()
        if sl and sl not in seen:
            seen.add(sl)
            unique_sugs.append(s)
    autocomplete_phrases = unique_sugs

    # Assign traffic scores to autocomplete phrases (unknown, but assume base)
    for phrase in autocomplete_phrases:
        pl = phrase.lower().strip()
        if pl and pl not in live_trends:
            live_trends[pl] = 200  # base score for suggestions

    # ── Step 4: Cache only autocomplete + matching trends (skip random trends) ──
    cache_data = {}
    for phrase, traffic in live_trends.items():
        is_autocomplete = phrase.lower().strip() in [p.lower().strip() for p in autocomplete_phrases]
        has_overlap = any(kw in phrase for kw in all_topic_kws) if all_topic_kws else False
        if is_autocomplete or has_overlap:
            cache_data[phrase] = traffic
    if cache_data:
        _save_cache(cache_data)

    # ── Step 5: Score and rank ──
    scored = []
    for phrase, traffic in live_trends.items():
        s = _compute_relevance_score(phrase, all_topic_kws, traffic)
        # Strict filter: must be EITHER an autocomplete match OR have keyword overlap
        is_autocomplete = phrase.lower().strip() in [p.lower().strip() for p in autocomplete_phrases]
        has_overlap = any(kw in phrase.lower() for kw in all_topic_kws) if all_topic_kws else False
        if is_autocomplete or has_overlap:
            scored.append((phrase, s, traffic))
    scored.sort(key=lambda x: x[1], reverse=True)

    if scored and scored[0][1] > 0:
        # Filter out suggestions that are too similar to the original title (>80% overlap)
        filtered = []
        title_words = set(title.lower().split())
        for s in scored:
            kw_words = set(s[0].lower().split())
            if title_words and kw_words:
                overlap_ratio = len(kw_words & title_words) / len(kw_words)
                if overlap_ratio < 0.8:  # skip if >80% of keyword words are already in title
                    filtered.append(s)
            else:
                filtered.append(s)
        if not filtered:
            return {"best_keyword": "", "alternatives": [], "source": "none"}
        alternatives = [s[0] for s in filtered[1:4] if s[1] > 0]
        return {
            "best_keyword": filtered[0][0].title(),
            "alternatives": [a.title() for a in alternatives],
            "source": "live",
        }

    # ── Step 6: Google Trends had no matches — use top autocomplete as keyword ──
    if autocomplete_phrases:
        return {
            "best_keyword": autocomplete_phrases[0].title(),
            "alternatives": [s.title() for s in autocomplete_phrases[1:4]],
            "source": "live",
        }

    # ── Step 7: Fallback — topic entity as keyword ──
    if all_topic_kws:
        fallback = " ".join(all_topic_kws[:3]).title()
        return {
            "best_keyword": fallback,
            "alternatives": [],
            "source": "fallback",
        }

    return {"best_keyword": "", "alternatives": [], "source": "none"}


def get_search_volume(keyword: str) -> dict:
    """
    Get search volume estimate for a keyword from Google Trends RSS.
    This is the 'per_search' anchor — called by competitor_intelligence.py
    to assess demand per keyword for saturation scoring.

    Returns dict: {keyword, traffic_score (0-100000+), source}
    """
    if not keyword or not keyword.strip():
        return {"keyword": keyword, "traffic_score": 0, "source": "none"}

    try:
        trends = fetch_google_trends_keywords()
        kw_lower = keyword.lower().strip()

        # Exact match
        if kw_lower in trends:
            return {"keyword": keyword, "traffic_score": trends[kw_lower], "source": "live"}

        # Partial match (keyword contained in trending phrase)
        for phrase, traffic in trends.items():
            if kw_lower in phrase or phrase in kw_lower:
                return {"keyword": keyword, "traffic_score": traffic, "source": "live"}

        # No match in trends
        return {"keyword": keyword, "traffic_score": 0, "source": "live"}
    except Exception:
        return {"keyword": keyword, "traffic_score": 0, "source": "error"}


if __name__ == "__main__":
    # Quick test
    result = research_keywords_for_topic(
        "Ketan Agarwal murder case new twist stadium footage",
        "A viral cricket stadium video has reopened the Ketan Agarwal murder investigation"
    )
    print(f"Best keyword: {result['best_keyword']} (source: {result['source']})")
    print(f"Alternatives: {result['alternatives']}")
