#!/usr/bin/env python3
"""
ViralDNA Edge Scorer — Breaks ties with growth intelligence.
=============================================================
When multiple topics share the same base score (e.g., 4 topics at 21),
the edge scorer adds a decimal (0.1–0.9) to each so the BEST one for
channel growth always wins.

Edge factors (each contributes 0.0–0.15, total 0.1–0.9):

  1. Search Demand   — Are people searching this RIGHT NOW? (Google Trends RSS)
  2. Trending Velocity — How fast is it gaining traction? (RSS recurrence)
  3. Channel Fit     — Does this match our best-performing past content?
  4. Competition Gap  — Are other Telugu channels already covering it?
  5. Engagement Potential — Will it get comments/shares? (identity, emotion)
  6. Geographic Breadth — AP + TS dual reach vs single-state
  7. Feedback Analytics — CTR, retention, views from past videos in same category

Design principles:
  - Edge is ALWAYS > 0.1 (every topic gets a baseline)
  - Edge is deterministic (same inputs → same output, no randomness)
  - Top factor: feedback analytics from our OWN channel (what worked before)
  - Tie-breaking: if edge is identical, use title alphabetical (stable sort)
"""

import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from collections import Counter

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYTICS_FILE = os.path.join(PROJECT_ROOT, "analytics", "metrics_history.json")
TOPICS_FILE = os.path.join(PROJECT_ROOT, "logs", "topics_history.json")
LEDGER_FILE = os.path.join(PROJECT_ROOT, "diagnostics", "growth_ledger.json")

# ── CATEGORY KEYWORDS (for matching topics to past video categories) ──

CATEGORY_KEYWORDS = {
    "politics": [
        "election", "minister", "bjp", "congress", "tdp", "ysrcp", "brs",
        "kcr", "revanth", "pawan kalyan", "naidu", "jagan", "modi",
        "cabinet", "assembly", "lok sabha", "rajya sabha", "vote", "party",
    ],
    "crime": [
        "murder", "crime", "arrest", "police", "scam", "fraud", "court",
        "verdict", "convicted", "custody", "rape", "kidnap",
    ],
    "economy": [
        "price", "petrol", "diesel", "gold", "sensex", "market", "budget",
        "tax", "gst", "loan", "bank", "rupee", "unemployment", "job",
    ],
    "weather": [
        "cyclone", "flood", "monsoon", "storm", "heatwave", "rain",
        "dam", "reservoir", "imd", "weather",
    ],
    "tollywood": [
        "tollywood", "telugu cinema", "mahesh babu", "prabhas", "allu arjun",
        "jr ntr", "ram charan", "chiranjeevi", "pawan kalyan", "box office",
        "movie release", "rrr", "baahubali",
    ],
    "cricket": [
        "cricket", "ipl", "world cup", "t20", "odi", "virat", "rohit",
        "bcci", "match",
    ],
    "social": [
        "student", "education", "exam", "neet", "jee", "result", "school",
        "college", "hospital", "health", "protest", "strike", "women",
    ],
    "defence": [
        "army", "navy", "air force", "military", "defence", "border",
        "soldier", "missile", "drdo", "isro",
    ],
}

# ── AP/TELANGANA DUAL-RELEVANCE TERMS ──

AP_TERMS = [
    "andhra", "amaravati", "visakhapatnam", "vizag", "tirupati",
    "vijayawada", "guntur", "kakinada", "nellore", "ongole",
    "kurnool", "anantapur", "srikakulam", "godavari", "prakasam",
    "chittoor", "krishna district", "tdp", "ysrcp", "jagan", "naidu",
    "chandrababu",
]
TE_TERMS = [
    "telangana", "hyderabad", "warangal", "nizamabad", "karimnagar",
    "adilabad", "mahabubnagar", "medak", "rangareddy", "nalgonda",
    "kcr", "ktr", "revanth", "brs",
]

# ── ENGAGEMENT SIGNALS (topics that drive comments/shares) ──

ENGAGEMENT_STRONG = [
    "vs", "clash", "attack", "slams", "hits out", "lashes", "controversy",
    "resigns", "quits", "sacked", "suspended", "banned", "arrested",
    "breaking", "exclusive", "revealed", "exposed", "leaked",
    "first time", "never before", "historic", "unprecedented",
]

ENGAGEMENT_MODERATE = [
    "announces", "launches", "inaugurates", "approves", "rejects",
    "demands", "urges", "warns", "questions", "challenges",
    "probe", "investigation", "review", "audit",
]


def _classify_topic(title: str) -> str:
    """Classify a topic title into a category."""
    t = title.lower()
    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in t)
        if count > 0:
            scores[cat] = count
    if not scores:
        return "general"
    return max(scores, key=lambda k: scores[k])


def _load_channel_analytics() -> dict:
    """Load past video performance data from metrics_history.json."""
    try:
        with open(ANALYTICS_FILE) as f:
            data = json.load(f)
        # Get the latest snapshot
        snapshots = data.get("snapshots", [])
        if not snapshots:
            return {}
        return snapshots[-1]
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_topics_history() -> dict:
    """Load topics history for past production data."""
    try:
        with open(TOPICS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_growth_ledger() -> dict:
    """Load growth ledger for execution history."""
    try:
        with open(LEDGER_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _get_trending_topics() -> set:
    """Fetch current Google Trends India trending topics."""
    trending = set()
    try:
        url = "https://trends.google.com/trending/rss?geo=IN"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=8)
        root = ET.fromstring(resp.read())
        for item in root.findall(".//item")[:20]:
            title = item.findtext("title", "").strip().lower()
            if title:
                trending.add(title)
    except Exception:
        pass
    return trending


# ═══════════════════════════════════════════════════════
#  FACTOR 1: Search Demand (Google Trends match)
# ═══════════════════════════════════════════════════════

def factor_search_demand(title: str, trending_topics: set) -> float:
    """Is this topic trending on Google RIGHT NOW? (0.0–0.15)"""
    if not trending_topics:
        return 0.05  # no data → neutral

    t = title.lower()
    # Check if any trending topic overlaps with our title
    for trend in trending_topics:
        # Match if key words overlap significantly
        trend_words = set(trend.split()) - {"the", "a", "an", "in", "of", "and", "is", "to", "for"}
        title_words = set(t.split()) - {"the", "a", "an", "in", "of", "and", "is", "to", "for"}
        overlap = trend_words & title_words
        if len(overlap) >= 2:  # 2+ shared content words = strong match
            return 0.15
        if len(overlap) >= 1 and len(trend_words) <= 4:  # short trending topic, 1 match is enough
            return 0.12

    # Partial keyword match (any trending term appears in our title)
    for trend in trending_topics:
        for word in trend.split():
            if len(word) > 4 and word in t:
                return 0.08

    return 0.0


# ═══════════════════════════════════════════════════════
#  FACTOR 2: Trending Velocity (RSS recurrence)
# ═══════════════════════════════════════════════════════

def factor_trending_velocity(topic: dict, all_topics: list) -> float:
    """How many RSS sources are carrying this topic? (0.0–0.15)"""
    num_sources = topic.get("num_sources", 1)
    title = topic.get("title", "").lower()

    # Also count how many other topics mention the same entities
    entity_mentions = 0
    key_entities = _extract_entities(title)
    for other in all_topics:
        if other.get("title", "").lower() == title:
            continue
        other_title = other.get("title", "").lower()
        if any(e in other_title for e in key_entities):
            entity_mentions += 1

    if num_sources >= 3 and entity_mentions >= 3:
        return 0.15
    elif num_sources >= 3:
        return 0.12
    elif num_sources >= 2 and entity_mentions >= 2:
        return 0.10
    elif num_sources >= 2:
        return 0.07
    elif entity_mentions >= 3:
        return 0.08
    elif entity_mentions >= 1:
        return 0.04
    return 0.0


def _extract_entities(title: str) -> list:
    """Extract key named entities from title (names, places)."""
    # Simple: words > 4 chars that are capitalized in original, or known names
    words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', title)
    # Also add known entity patterns
    entities = []
    for w in words:
        if len(w) > 3:
            entities.append(w.lower())
    return entities


# ═══════════════════════════════════════════════════════
#  FACTOR 3: Channel Fit (past performance in same category)
# ═══════════════════════════════════════════════════════

def factor_channel_fit(title: str, analytics: dict, ledger: dict) -> float:
    """Does this topic category match our best-performing past content? (0.0–0.15)"""
    category = _classify_topic(title)
    top_videos = analytics.get("videos", {}).get("top_videos", [])

    if not top_videos:
        return 0.05  # no data → neutral

    # Score past videos by category match
    cat_views = 0
    total_views = 0
    for video in top_videos:
        vtitle = video.get("title", "")
        vviews = video.get("views", 0)
        total_views += vviews
        vcat = _classify_topic(vtitle)
        if vcat == category:
            cat_views += vviews

    if total_views == 0:
        return 0.05

    # What fraction of our views come from this category?
    # High fraction = we're good at this → boost
    cat_fraction = cat_views / total_views

    if cat_fraction >= 0.5:
        return 0.15  # This is our bread and butter
    elif cat_fraction >= 0.3:
        return 0.12
    elif cat_fraction >= 0.15:
        return 0.08
    elif cat_fraction >= 0.05:
        return 0.05
    else:
        return 0.02  # Untested category — slight novelty bonus


# ═══════════════════════════════════════════════════════
#  FACTOR 4: Competition Gap (underserved topics)
# ═══════════════════════════════════════════════════════

def factor_competition_gap(title: str, trending_topics: set, all_topics: list) -> float:
    """Are other channels already covering this? (0.0–0.12)
    
    LOW competition = HIGH edge (underserved = opportunity).
    HIGH competition = LOW edge (we're just another voice).
    """
    t = title.lower()
    category = _classify_topic(title)

    # Topics in same category from our monitor = competition signal
    similar_count = 0
    for other in all_topics:
        if other.get("title", "").lower() == t:
            continue
        if _classify_topic(other.get("title", "")) == category:
            similar_count += 1

    # Check if trending (everyone covers trending = saturated)
    is_trending = False
    for trend in trending_topics:
        trend_words = set(trend.split()) - {"the", "a", "an", "in", "of"}
        title_words = set(t.split()) - {"the", "a", "an", "in", "of"}
        if len(trend_words & title_words) >= 2:
            is_trending = True
            break

    if is_trending and similar_count >= 5:
        return 0.02  # Saturated — everyone is covering this
    elif is_trending and similar_count >= 3:
        return 0.04
    elif similar_count >= 5:
        return 0.05  # Lots of similar content
    elif similar_count >= 3:
        return 0.08
    elif similar_count >= 1:
        return 0.10  # Some interest but not crowded
    else:
        return 0.12  # Unique — we'd be first movers


# ═══════════════════════════════════════════════════════
#  FACTOR 5: Engagement Potential
# ═══════════════════════════════════════════════════════

def factor_engagement_potential(title: str) -> float:
    """Will this drive comments/shares? (0.0–0.12)"""
    t = title.lower()

    # Strong engagement signals (controversy, clash, breaking)
    for kw in ENGAGEMENT_STRONG:
        if kw in t:
            return 0.12

    # Moderate engagement signals
    for kw in ENGAGEMENT_MODERATE:
        if kw in t:
            return 0.08

    # Identity politics (Pawan Kalyan, KCR, Revanth = Telugu identity)
    identity_terms = ["pawan kalyan", "kcr", "ktr", "revanth", "jagan", "naidu",
                      "telangana identity", "self-respect", "pride"]
    for term in identity_terms:
        if term in t:
            return 0.10

    return 0.03  # Neutral — no strong hooks


# ═══════════════════════════════════════════════════════
#  FACTOR 6: Geographic Breadth (AP + TS dual reach)
# ═══════════════════════════════════════════════════════

def factor_geographic_breadth(title: str) -> float:
    """Does this reach BOTH AP and TS audiences? (0.0–0.10)"""
    t = title.lower()
    has_ap = any(term in t for term in AP_TERMS)
    has_te = any(term in t for term in TE_TERMS)

    if has_ap and has_te:
        return 0.10  # Dual reach — maximum audience
    elif has_te:
        return 0.07  # TS is our strongest market
    elif has_ap:
        return 0.06  # AP is strong too
    else:
        return 0.02  # National/international — less targeted


# ═══════════════════════════════════════════════════════
#  FACTOR 7: Feedback Analytics (past video performance)
# ═══════════════════════════════════════════════════════

def factor_feedback_analytics(title: str, analytics: dict, ledger: dict) -> float:
    """How did similar past videos perform? (0.0–0.15)
    
    This is the MOST IMPORTANT factor — our own data is the strongest signal.
    If past videos on this category got 1000+ views, this topic should rank higher.
    """
    category = _classify_topic(title)
    top_videos = analytics.get("videos", {}).get("top_videos", [])

    if not top_videos:
        # No analytics data yet — look at ledger
        return _factor_ledger_performance(category, ledger)

    # Calculate average views per video in this category
    cat_views = []
    for video in top_videos:
        vtitle = video.get("title", "")
        vviews = video.get("views", 0)
        vlikes = video.get("likes", 0)
        vcomments = video.get("comments", 0)
        vcat = _classify_topic(vtitle)

        if vcat == category:
            # Engagement rate = (likes + comments) / views (if views > 0)
            engagement_rate = 0
            if vviews > 0:
                engagement_rate = (vlikes + vcomments) / vviews
            cat_views.append({
                "views": vviews,
                "engagement_rate": engagement_rate,
            })

    if not cat_views:
        # No videos in this category → untested, slight exploration bonus
        return 0.06

    avg_views = sum(v["views"] for v in cat_views) / len(cat_views)
    avg_engagement = sum(v["engagement_rate"] for v in cat_views) / len(cat_views)

    # Score based on absolute views + engagement
    # Shorts: 500+ views is good, 1000+ is great
    # Main: 100+ views is good, 500+ is great
    if avg_views >= 1000 or avg_engagement >= 0.05:
        return 0.15  # Proven category — double down
    elif avg_views >= 500 or avg_engagement >= 0.03:
        return 0.12
    elif avg_views >= 100 or avg_engagement >= 0.01:
        return 0.10
    elif avg_views >= 10:
        return 0.07
    else:
        return 0.04  # Low views — maybe try different angle


def _factor_ledger_performance(category: str, ledger: dict) -> float:
    """Fallback: use growth ledger when analytics has no data."""
    executions = ledger.get("execution_history", [])
    if not executions:
        return 0.05

    # Count successful productions by topic category
    cat_count = 0
    total_count = 0
    for ex in executions[-20:]:  # last 20 executions
        topic_title = ex.get("topic_used", "")
        total_count += 1
        if _classify_topic(topic_title) == category:
            cat_count += 1

    if total_count == 0:
        return 0.05

    fraction = cat_count / total_count
    if fraction >= 0.3:
        return 0.10  # Category is well-tested
    elif fraction >= 0.1:
        return 0.07
    else:
        return 0.04  # New territory


# ═══════════════════════════════════════════════════════
#  MAIN: compute_edge_score
# ═══════════════════════════════════════════════════════

def compute_edge_score(topic: dict, all_topics: list = None,
                       trending_topics: set = None) -> tuple:
    """
    Compute the decimal edge score for a topic.
    
    Returns (edge_score, breakdown) where:
      - edge_score: float in range [0.1, 0.9]
      - breakdown: dict of {factor_name: value} for audit/debugging
    
    Args:
      topic: dict with at least 'title' key
      all_topics: list of all topic dicts (for velocity/competition)
      trending_topics: set of trending topic strings (from Google Trends RSS)
    """
    title = topic.get("title", "")
    if not all_topics:
        all_topics = []
    if trending_topics is None:
        trending_topics = set()

    # Load analytics (cache this at call site for batch scoring)
    analytics = _load_channel_analytics()
    ledger = _load_growth_ledger()

    # Compute each factor
    factors = {}

    factors["search_demand"] = factor_search_demand(title, trending_topics)
    factors["trending_velocity"] = factor_trending_velocity(topic, all_topics)
    factors["channel_fit"] = factor_channel_fit(title, analytics, ledger)
    factors["competition_gap"] = factor_competition_gap(title, trending_topics, all_topics)
    factors["engagement_potential"] = factor_engagement_potential(title)
    factors["geographic_breadth"] = factor_geographic_breadth(title)
    factors["feedback_analytics"] = factor_feedback_analytics(title, analytics, ledger)

    # Sum all factors
    raw_edge = sum(factors.values())

    # Clamp to [0.1, 0.9] — every topic gets at least 0.1
    edge = max(0.1, min(0.9, raw_edge))

    # Round to 1 decimal to avoid floating point noise
    edge = round(edge, 1)

    return edge, factors


def batch_score_topics(topics: list) -> list:
    """
    Score a batch of topics. Fetches trending data once, then scores all.
    
    Returns the same list with 'edge_score' and 'edge_breakdown' added to each.
    Also sets 'final_score' = base_score + edge_score.
    """
    # Fetch trending topics once (expensive)
    trending = _get_trending_topics()

    for topic in topics:
        edge, breakdown = compute_edge_score(topic, topics, trending)
        topic["edge_score"] = edge
        topic["edge_breakdown"] = breakdown
        base = topic.get("score", 0)
        # If score is int, preserve it as float with edge
        topic["final_score"] = round(base + edge, 1)

    return topics
