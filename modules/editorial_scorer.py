#!/usr/bin/env python3
"""
ViralDNA Editorial Scorer
=========================
Scores topics not just for ViralDNA relevance but for CHANNEL GROWTH potential.
Run by the monitor to decide if a topic is worth producing.

Key insight: A topic is worth producing when:
1. It is directly relevant to AP/Telangana/Telugu audience (not just "India")
2. It has cross-source validation (not just one RSS feed)
3. It is GROWTH-oriented (not just "another political statement")
4. It fills the daily upload slot with a topic that adds subscriber value

Score ranges:
  0-9:   Skip — not worth producing
  10-14: Marginal — only if nothing better
  15-19: Good — worth a short, maybe a main
  20-25: Viral + Relevant — DEFINITELY produce, this is the one
"""
import re

# ── GEOGRAPHIC RELEVANCE ──
# Direct AP/Telangana = highest score (our core audience)
# Telugu states related = high score
# South India = moderate (shared culture)
# India national = baseline (everyone covers this)
# International = only if massive India connection

GEO_DIRECT = [
    "andhra pradesh", "telangana", "telugu", "amaravati", "visakhapatnam",
    "vizag", "tirupati", "vijayawada", "guntur", "kakinada", "nellore",
    "ongole", "kurnool", "anantapur", "srikakulam", "east godavari",
    "west godavari", "prakasam", "chittoor", "krishna district",
    "hyderabad", "warangal", "nizamabad", "karimnagar", "adilabad",
    "mahabubnagar", "medak", "rangareddy", "nalgonda",
    "tollywood", "telugu cinema", "telugu film", "telugu movie",
    "mahesh babu", "prabhas", "allu arjun", "jr ntr", "ram charan",
    "chiranjeevi", "nagarjuna", "pawan kalyan", "venkatesh",
    "ss rajamouli", "keerthy suresh", "samantha", "rashmika",
]
GEO_SOUTH = [
    "karnataka", "tamil nadu", "kerala", "chennai", "bangalore",
    "bengaluru", "coimbatore", "mysore", "mangalore",
]
GEO_INDIA = [
    "india", "indian", "delhi", "mumbai", "bjp", "congress", "modi",
    "rahul", "lok sabha", "parliament", "supreme court",
]

# ── TOPIC CATEGORY (what drives Telugu audience engagement) ──
# Crime/Justice + Tollywood + Cricket = highest engagement categories
# Politics/Economy = steady, reliability builders
# Weather/Disaster = urgent, time-sensitive, high CTR
# Social issues = shareable, discussion-driven

CAT_CRIME = [
    "court", "justice", "judge", "bail", "murder", "crime", "death",
    "dowry", "arrest", "police", "rape", "acid", "attack", "fraud",
    "scam", "theft", "kidnap", "accident", "high court", "supreme court",
    "verdict", "sentence", "convicted", "custody", "missing",
]
CAT_POLITICS = [
    "election", "minister", "cm ", "chief minister", "governor",
    "bjp", "congress", "tdp", "ysrcp", "jagan", "naidu", "kcr",
    "chandrababu", "siddaramaiah", "shivakumar", "resign",
    "cabinet", "budget", "assembly", "lok sabha", "rajya sabha",
    "vote", "party", "political", "rally", "campaign",
]
CAT_ECONOMY = [
    "price", "fuel", "petrol", "diesel", "gold", "silver", "sensex",
    "market", "economy", "inflation", "budget", "tax", "gst",
    "interest", "loan", "bank", "rupee", "dollar", "trade",
    "unemployment", "job", "salary", "pension", "subsidy",
]
CAT_WEATHER = [
    "cyclone", "flood", "tsunami", "earthquake", "drought",
    "monsoon", "storm", "landslide", "heat wave", "cold wave",
    "rainfall", "heavy rain", "dam", "reservoir", "river",
    "krishna", "godavari", "warnings", "imd",
]
CAT_TOLLYWOOD = [
    "tollywood", "telugu cinema", "telugu film", "telugu movie",
    "mahesh babu", "prabhas", "allu arjun", "jr ntr", "ram charan",
    "chiranjeevi", "pawan kalyan", "nagarjuna", "venkatesh",
    "ss rajamouli", "keerthy suresh", "samantha", "rashmika",
    "telugu actor", "telugu star", "box office", "movie release",
]
CAT_CRICKET = [
    "cricket", "ipl", "world cup", "t20", "odi", "test match",
    "virat", "rohit", "rahul", "surya", "bumrah", "shami",
    "team india", "bcci", "ipl match", "ipl team",
]
CAT_SOCIAL = [
    "student", "education", "exam", "result", "school", "college",
    "university", "cbse", "neet", "jee", "teacher", "hospital",
    "health", "covid", "vaccine", "doctor", "welfare", "scheme",
    "women", "child", "dalit", "tribal", "minority", "rights",
    "protest", "strike", "bandh", "rally",
]

# ── GROWTH SIGNAL ──
# What makes a topic drive SUBSCRIBERS, not just views?
# - Not already covered by every other channel
# - Has emotional engagement (outrage, joy, shock, pride)
# - Is explainable (not just a political statement)
# - Has a "hook" that works in a thumbnail

GROWTH_EMOTIONAL = [
    "shocking", "outrage", "unbelievable", "historic", "massive",
    "dramatic", "tragic", "heroic", "brave", "incredible",
    "never before", "first time", "record", "breaking",
]
GROWTH_SPECIFIC = [
    "video", "photo", "watch", "listen", "revealed", "exposed",
    "proof", "evidence", "leaked", "caught", "gone wrong",
]

# ── HOOK QUALITY (what makes a viewer CLICK and STAY) ──
# Based on YouTube Studio AI gap analysis for The ViralDNA (Jun 2026):
# Channels in News & Politics with strong hooks get 3-5x higher CTR.
# Hook types: personal stakes, curiosity gap, time urgency, question format, specificity.

HOOK_PERSONAL_STAKES = [
    "you", "your ", "yours", "yourself", "family", "parents", "children",
    "vote", "voter", "your name", "your mobile", "your aadhaar",
    "your bank", "your money", "your property", "your job",
]
HOOK_CURIOUSITY_GAP = [
    "what happened", "what really", "the reason", "the truth",
    "the real", "behind the", "hidden", "secret", "untold",
    "no one", "nobody", "only one", "the one ", "why ",
    "how did ", "how this ", "happened next", "finally",
    "revealed", "exposed", "mystery", "unbelievable",
]
HOOK_TIME_URGENCY = [
    "breaking", "just in", "just hours", "happening now", "alert",
    "urgent", "latest update", "just announced", "minutes ago",
    "today", "this hour", "live", "developing", "update:",
]
HOOK_QUESTION = [
    "will ", "can ", "should ", "what if", "is ",
    "are ", "how ", "why ", "who ", "when ",
]
HOOK_SPECIFICITY = [
    "video", "photo", "watch the", "see how", "proof",
    "footage", "official", "confirmed", "announced", "declared",
]


def _score_hook_quality(title: str) -> tuple:
    """
    Score title for hook quality (0-5 points).
    Returns (score, reasons_list).
    Detects: personal stakes, curiosity gap, time urgency, question format, specificity.
    """
    score = 0
    reasons = []
    title_lower = title.lower()

    if any(kw in title_lower for kw in HOOK_PERSONAL_STAKES):
        score += 2
        reasons.append("Personal stakes language +2")

    if any(kw in title_lower for kw in HOOK_CURIOUSITY_GAP):
        score += 1
        reasons.append("Curiosity gap +1")

    if any(kw in title_lower for kw in HOOK_TIME_URGENCY):
        score += 1
        reasons.append("Time urgency +1")

    # Question format = higher CTR on YouTube
    if any(title_lower.strip().startswith(q) for q in HOOK_QUESTION):
        score += 1
        reasons.append("Question format (CTR hook) +1")
    elif "?" in title:
        score += 1
        reasons.append("Question in title (CTR hook) +1")

    if score > 5:
        score = 5

    return score, reasons


def editorial_score(topic: dict) -> dict:
    """
    Score a topic for ViralDNA editorial worthiness.
    Returns dict with score, reasons, and recommendation.
    """
    title = topic.get("title", "").lower()
    source = topic.get("source", "")
    score = 0
    reasons = []

    # ── 1. GEOGRAPHIC (0-10) ──
    if any(kw in title for kw in GEO_DIRECT):
        score += 10
        reasons.append("DIRECT AP/TELANGANA +10")
    elif any(kw in title for kw in GEO_SOUTH):
        score += 5
        reasons.append("South India +5")
    elif any(kw in title for kw in GEO_INDIA):
        score += 3
        reasons.append("India national +3")
    else:
        score += 1
        reasons.append("Low geo relevance +1")

    # ── 2. CATEGORY (0-7) ──
    cat_scores = []
    if any(kw in title for kw in CAT_CRIME):
        cat_scores.append(("Crime/Justice", 6))
    if any(kw in title for kw in CAT_TOLLYWOOD):
        cat_scores.append(("Tollywood", 7))
    if any(kw in title for kw in CAT_CRICKET):
        cat_scores.append(("Cricket", 6))
    if any(kw in title for kw in CAT_WEATHER):
        cat_scores.append(("Weather/Disaster", 5))
    if any(kw in title for kw in CAT_POLITICS):
        cat_scores.append(("Politics", 5))
    if any(kw in title for kw in CAT_ECONOMY):
        cat_scores.append(("Economy", 5))
    if any(kw in title for kw in CAT_SOCIAL):
        cat_scores.append(("Social", 4))

    if cat_scores:
        best_cat = max(cat_scores, key=lambda x: x[1])
        score += best_cat[1]
        reasons.append(f"{best_cat[0]} +{best_cat[1]}")

    # ── 3. CROSS-SOURCE VALIDATION (0-5) ──
    num_sources = topic.get("num_sources", 1)
    if num_sources >= 3:
        score += 5
        reasons.append("Multi-source (3+) +5")
    elif num_sources >= 2:
        score += 3
        reasons.append("Multi-source (2) +3")

    # ── 4. VIRAL SIGNAL (0-5) ──
    if "google trends" in source.lower():
        score += 5
        reasons.append("Google Trends India +5")
    elif "reddit" in source.lower():
        # Extract upvote count if present
        import re as _re
        m = _re.search(r'\[(\d+)\s*upvotes?\]', source)
        if m:
            ups = int(m.group(1))
            if ups >= 500:
                score += 4
                reasons.append(f"Reddit {ups}+ upvotes +4")
            elif ups >= 100:
                score += 3
                reasons.append(f"Reddit {ups}+ upvotes +3")
        else:
            score += 2
            reasons.append("Reddit (no count) +2")
    elif "google news" in source.lower():
        score += 3
        reasons.append("Google News +3")

    # ── 5. GROWTH POTENTIAL (0-3) ──
    if any(kw in title for kw in GROWTH_EMOTIONAL):
        score += 2
        reasons.append("Emotional hook +2")
    if any(kw in title for kw in GROWTH_SPECIFIC):
        score += 1
        reasons.append("Viral format +1")

    # ── 6. HOOK QUALITY (0-5) [NEW — Studio AI gap fix #1] ──
    hook_score, hook_reasons = _score_hook_quality(title)
    score += hook_score
    reasons.extend(hook_reasons)

    # ── RECOMMENDATION (max now 35 with hook scoring) ──
    if score >= 22:
        recommendation = "� PRODUCE — High viral + relevance + hook"
    elif score >= 17:
        recommendation = "🟡 CONSIDER — Worth a short"
    elif score >= 12:
        recommendation = "🟠 MARGINAL — Only if slot empty"
    else:
        recommendation = "🔴 SKIP — Not worth producing"

    return {
        "score": score,
        "max_possible": 35,
        "reasons": reasons,
        "recommendation": recommendation,
        "hook_score": hook_score,
    }
