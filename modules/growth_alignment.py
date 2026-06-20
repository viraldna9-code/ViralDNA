# VERSION: 1.0
# MODULE: growth_alignment.py
# PURPOSE: Channel Growth Alignment Scorer — forces the pipeline to justify every
#          topic through the lens of "will this grow MY channel?" before picking it.
#
# Scores each topic on 5 dimensions (0-100 total):
#   1. Audience Fit (0-25) — Does our audience care about this?
#   2. Differentiation (0-25) — Are we unique covering this, or just noise?
#   3. Emotional Hook (0-20) — Will this stop the scroll?
#   4. Viral Coefficient (0-15) — Will people SHARE this?
#   5. Historical Performance (0-15) — Has our channel grown with similar topics?
#
# Output: growth_score (0-100) multiplied into the existing cpm_weight as a modifier.
#         Topics scoring < 40 get a 0.5x penalty (halved weight).
#         Topics scoring >= 70 get a 1.3x bonus.
#         Topics scoring >= 85 get a 1.6x bonus.

import json
import os
import re
from datetime import datetime, timezone

# ── Channel Identity ──────────────────────────────────────────────────────
# This defines who the channel is and who the audience is.
# Update this as the channel evolves — it's the "why" behind every score.

CHANNEL_IDENTITY = {
    "name": "The ViralDNA",
    "audience": "Telugu-speaking Indians (India + diaspora)",
    "niche": "Breaking news with Telugu/India relevance",
    "differentiation": "AI-powered bilingual news with RVC voice (authentic Telugu-English mix)",
    "growth_goal": "Increase Indian/Telugu audience through culturally relevant news",
}

# ── Audience Fit Keywords ─────────────────────────────────────────────────
# Topics matching these score higher because our audience actually cares.

AUDIENCE_FIT_KEYWORDS = {
    # Direct Telugu/India connection (highest fit)
    "telugu": 10, "andhra": 10, "telangana": 10, "hyderabad": 10,
    "vizag": 8, "visakhapatnam": 8, "amaravati": 8, "tirupati": 8,
    "tdp": 8, "ysrcp": 8, "jagan": 8, "chandrababu": 8, "lokesh": 8,
    "pawan kalyan": 8, "tollywood": 7, "mahesh babu": 7, "prabhas": 7,
    "allu arjun": 7, "jr ntr": 7, "ram charan": 7, "ntr": 7,
    # India politics / national (high fit)
    "india": 6, "modi": 6, "bjp": 6, "congress": 6, "rahul": 6,
    "election": 6, "parliament": 6, "lok sabha": 6, "rajya sabha": 6,
    "supreme court": 5, "pm modi": 6, "indian": 5,
    # Indian diaspora (good fit)
    "nri": 6, "diaspora": 6, "indian abroad": 6, "telugu nri": 8,
    "indian american": 5, "indian student": 5, "h1b": 5, "green card": 4,
    # Regional neighbors (moderate fit)
    "tamil nadu": 5, "karnataka": 4, "kerala": 4, "tamil": 4,
    "bangalore": 4, "chennai": 4, "kolkata": 3,
}

# ── Low-Fit Topics (penalty) ─────────────────────────────────────────────
# These topics have zero connection to our audience.
# They might trend globally but won't grow THIS channel.

LOW_FIT_PATTERNS = [
    r"\b(uk|britain|british|london|england)\b.*\b(crash|accident|fire|attack|bomb)\b",
    r"\b(trump|biden|white house|congress|senate)\b",
    r"\b(eu|european|german|french|france|spain|italy)\b",
    r"\b(china|chinese|beijing|xi jinping|hong kong)\b.*\b(military|army|war)\b",
    r"\b(russia|putin|ukraine|war|invasion)\b",
    r"\b(israel|palestine|gaza|hamas|iran)\b",
    r"\b(japan|korean|tokyo|seoul)\b.*\b(earthquake|tsunami|fire)\b",
    r"\b(canada|australia|toronto|sydney)\b",
    r"\b(nfl|nba|mlb|fifa|premier league|la liga)\b",
    r"\b(elon|musk|tesla|apple|google|microsoft)\b",
]

# ── High-Hook Patterns (viral potential) ─────────────────────────────────
# These emotional triggers make people stop scrolling and share.

HIGH_HOOK_PATTERNS = {
    "shocking": [
        r"\b(dead|killed|murdered|massacre|horrific|gruesome|tragic)\b",
        r"\b(bombed|exploded|collapsed|crashed|derailed|sunk)\b",
        r"\b(shot|stabbed|beaten|lynched|tortured)\b",
    ],
    "injustice": [
        r"\b(injustice|discrimination|racism|caste|atrocity|victim)\b",
        r"\b(banned|arrested|jailed|exiled|suppressed|crackdown)\b",
        r"\b(protest|strike|agitation|revolt|uprising)\b",
    ],
    "underdog": [
        r"\b(student|farmer|worker|woman|child|senior|citizen)\b.*\b(fight|win|save|rescue)\b",
        r"\b(hero|brave|saved|rescued|donated|helped)\b",
    ],
    "money": [
        r"\b(crore|lakh|rupee|rs\.?|scam|fraud|corruption|loot)\b",
        r"\b(tax|budget|subsidy|relief|package|benefit)\b",
    ],
    "health_fear": [
        r"\b(cancer|covid|virus|disease|outbreak|hospital|death)\b",
        r"\b(pandemic|epidemic|infection|contaminated)\b",
    ],
}

# ── Category Performance History ─────────────────────────────────────────
# When RAG data exists, we look up how similar topics performed.
# This maps category tags to expected performance tier.

CATEGORY_PERFORMANCE_TIERS = {
    "politics_government": "high",      # Core audience interest
    "visa_immigration": "high",         # Diaspora audience loves this
    "nri_diaspora": "high",             # Direct audience connection
    "jobs_career": "medium-high",       # Broad appeal
    "telugu_culture": "high",           # Niche but engaged
    "india_national": "medium",         # Broad but competitive
    "international_disaster": "low",    # Low audience fit
    "international_politics": "low",    # Not our audience
    "entertainment_bollywood": "medium",
    "sports_cricket": "medium",
    "health_medicine": "medium",
    "technology": "medium-low",
    "unknown": "medium",               # Unknown = neutral
}


def classify_topic_category(title: str, description: str = "") -> str:
    """Classify a topic into a category for performance lookup."""
    text = (title + " " + description).lower()

    # Check from most-specific to least-specific
    category_keywords = {
        "visa_immigration": ["visa", "h1b", "h-1b", "green card", "immigration", "deport", "embuscis", "passport"],
        "nri_diaspora": ["nri", "diaspora", "indian abroad", "telugu nri", "nri marriage", "pravasi"],
        "politics_government": ["modi", "bjp", "congress", "rahul", "election", "parliament", "lok sabha", "minister", "pm ", "chief minister", "cm ", "mla", "mp "],
        "jobs_career": ["job", "hiring", "layoff", "salary", "career", "work permit", "recruitment"],
        "telugu_culture": ["telugu", "tollywood", "tdp", "ysrcp", "andhra", "telangana", "hyderabad", "vizag", "tirupati", "jagan", "chandrababu", "lokesh", "pawan kalyan", "mahesh babu", "prabhas", "allu arjun", "jr ntr", "ram charan"],
        "india_national": ["india", "indian", "supreme court", "cabinet", "rs.", "crore", "lakh"],
        "health_medicine": ["covid", "cancer", "hospital", "virus", "disease", "health", "vaccine", "doctor"],
        "sports_cricket": ["cricket", "ipl", "world cup", "match", "virat", "rohit", "team india"],
        "technology": ["ai ", "chatgpt", "startup", "tech", "app", "cyber", "software"],
        "entertainment_bollywood": ["bollywood", "film", "movie", "actor", "actress", "box office"],
        "international_disaster": ["earthquake", "tsunami", "flood", "hurricane", "tornado", "volcano", "wildfire"],
        "international_politics": ["trump", "biden", "putin", "xi jinping", "nato", "un ", "white house", "downing street", "kremlin"],
    }

    for category, keywords in category_keywords.items():
        for kw in keywords:
            if kw in text:
                return category

    return "unknown"


def score_audience_fit(title: str, description: str = "") -> float:  # type: ignore[assignment]
    """
    Score 0-25: Does our Telugu/India audience actually care about this topic?
    High = direct connection. Low = international event with no India link.
    """
    text = (title + " " + description).lower()
    score = 0

    # Check audience fit keywords
    for keyword, points in AUDIENCE_FIT_KEYWORDS.items():
        if keyword in text:
            score += points

    # Cap at 25
    score = min(score, 25)

    # Penalty for low-fit international topics
    for pattern in LOW_FIT_PATTERNS:
        if re.search(pattern, text):
            score = max(0, score - 15)
            break

    return score


def score_differentiation(title: str, description: str = "", num_sources: int = 1) -> float:
    """
    Score 0-25: Can we offer something unique, or is every news channel covering this?
    Low differentiation = we're just noise in a crowded space.
    """
    text = (title + " " + description).lower()
    score = 12  # Start at neutral

    # If many sources cover it, it's low differentiation (commodity news)
    if num_sources >= 5:
        score -= 8
    elif num_sources >= 3:
        score -= 4
    elif num_sources == 1:
        score += 5  # Only source = unique

    # Telugu/India angle on international story = differentiation
    telugu_keywords = ["telugu", "andhra", "telangana", "indian", "india", "modi", "bjp"]
    has_telugu_angle = any(kw in text for kw in telugu_keywords)

    # International disaster with no India connection = zero differentiation
    # (every channel covers it, we add nothing)
    international_only = any(kw in text for kw in ["london", "uk", "britain", "british"])
    has_india_connection = any(kw in text for kw in ["indian", "india", "telugu", "passenger", "among", "including"])

    if international_only and not has_india_connection:
        score -= 10  # We're just repeating what every channel says
    elif international_only and has_india_connection:
        score += 8   # "Indians affected in London crash" = our angle

    # Niche topics get bonus
    niche_indicators = ["telugu", "andhra", "telangana", "tollywood", "nri", "h1b", "visa"]
    if any(kw in text for kw in niche_indicators):
        score += 5

    return max(0, min(25, score))


def score_emotional_hook(title: str, description: str = "") -> float:
    """
    Score 0-20: Will this stop the scroll? Does it trigger a strong emotion?
    Emotions: shock, anger, fear, hope, pride, curiosity.
    """
    text = (title + " " + description).lower()
    score = 5  # Baseline — news is inherently interesting

    for emotion, patterns in HIGH_HOOK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                if emotion == "shocking":
                    score += 6
                elif emotion == "injustice":
                    score += 5
                elif emotion == "underdog":
                    score += 4
                elif emotion == "money":
                    score += 4
                elif emotion == "health_fear":
                    score += 5

    # Numbers in title create curiosity gap
    if re.search(r"\b(\d+|crore|lakh|thousand|million|billion)\b", title):
        score += 3

    # Question marks create curiosity
    if "?" in title:
        score += 2

    # Exclamation = already trying to hook
    if "!" in title:
        score += 1

    return max(0, min(20, score))


def score_viral_coefficient(title: str, description: str = "") -> float:
    """
    Score 0-15: Will people SHARE this with others?
    Share triggers: outrage, "tag someone", relatable, "this affects us"
    """
    text = (title + " " + description).lower()
    score = 3  # Baseline

    # Outrage sharing
    outrage_keywords = ["shame", "unacceptable", "outrage", "exposed", "scam", "fraud", "loot", "corrupt"]
    if any(kw in text for kw in outrage_keywords):
        score += 6

    # Relatability sharing
    relatable = ["student", "farmer", "common man", "aam aadmi", "middle class", "salary", "job", "visa", "h1b"]
    if any(kw in text for kw in relatable):
        score += 5

    # "Did you know" / curiosity sharing
    curiosity = ["did you know", "didyouknow", "fact", "truth", "revealed", "secret", "hidden"]
    if any(kw in text for kw in curiosity):
        score += 4

    # Pride sharing (India wins)
    pride = ["india wins", "indian wins", "proud", "historic", "first", "record", "achievement"]
    if any(kw in text for kw in pride):
        score += 5

    return max(0, min(15, score))


def score_historical_performance(title: str, ledger_path: str = "") -> float:
    """
    Score 0-15: Has our channel grown with similar topics before?
    Uses RAG growth ledger to look up historical performance on same category.
    """
    score = 7  # Neutral default — no data means we assume medium

    if not ledger_path:
        ledger_path = os.path.join(os.path.dirname(__file__), "..", "diagnostics", "growth_ledger.json")

    if not os.path.exists(ledger_path):
        return score  # No data yet — neutral

    try:
        with open(ledger_path) as f:
            ledger = json.load(f)

        metrics = ledger.get("performance_metrics", [])
        if not metrics:
            return score  # No performance data yet

        # Classify the topic
        category = classify_topic_category(title)

        # Look for historical performance on this category
        category_views = []
        for m in metrics:
            # Check if this metric entry is for a topic in the same category
            m_topic = m.get("topic_title", "")
            if classify_topic_category(m_topic) == category:
                views = m.get("views", 0)
                if views > 0:
                    category_views.append(views)

        if category_views:
            avg_views = sum(category_views) / len(category_views)
            # Score based on how this category performs vs overall average
            all_views = [m.get("views", 0) for m in metrics if m.get("views", 0) > 0]
            if all_views:
                overall_avg = sum(all_views) / len(all_views)
                if overall_avg > 0:
                    ratio = avg_views / overall_avg
                    if ratio >= 2.0:
                        score = 15  # This category performs 2x average
                    elif ratio >= 1.5:
                        score = 13
                    elif ratio >= 1.0:
                        score = 11
                    elif ratio >= 0.5:
                        score = 8
                    else:
                        score = 4  # This category underperforms

    except Exception:
        pass  # Don't break the pipeline if ledger read fails

    return score


def score_topic_growth_alignment(
    topic: dict,
    ledger_path: str = "",
) -> dict:
    """
    Score a single topic on growth alignment. Returns dict with scores.

    Input: topic dict with keys: title, description, source, num_sources, etc.
    Output: topic dict augmented with growth_score and component scores.
    """
    title = topic.get("title", "")
    description = topic.get("description", "")
    num_sources = topic.get("num_sources", 1)

    # Calculate component scores
    audience_fit = score_audience_fit(title, description)
    differentiation = score_differentiation(title, description, num_sources)
    emotional_hook = score_emotional_hook(title, description)
    viral_coefficient = score_viral_coefficient(title, description)
    historical_performance = score_historical_performance(title, ledger_path)

    # Total growth score (0-100)
    growth_score = audience_fit + differentiation + emotional_hook + viral_coefficient + historical_performance

    # Growth modifier for cpm_weight
    if growth_score >= 85:
        growth_modifier = 1.6  # Strong growth topic — boost significantly
    elif growth_score >= 70:
        growth_modifier = 1.3  # Good growth topic — boost
    elif growth_score >= 40:
        growth_modifier = 1.0  # Neutral — no change
    elif growth_score >= 25:
        growth_modifier = 0.7  # Weak — slight penalty
    else:
        growth_modifier = 0.4  # Poor fit — heavy penalty

    # Category for debugging
    category = classify_topic_category(title)

    result = {
        "growth_score": round(growth_score, 1),
        "growth_modifier": growth_modifier,
        "growth_category": category,
        "growth_breakdown": {
            "audience_fit": round(audience_fit, 1),
            "differentiation": round(differentiation, 1),
            "emotional_hook": round(emotional_hook, 1),
            "viral_coefficient": round(viral_coefficient, 1),
            "historical_performance": round(historical_performance, 1),
        },
        "growth_verdict": _growth_verdict(growth_score),
    }

    return result


def _growth_verdict(score: float) -> str:
    """Human-readable verdict for the growth score."""
    if score >= 85:
        return "EXCELLENT — Strong channel fit, high differentiation, viral potential"
    elif score >= 70:
        return "GOOD — Fits audience, decent differentiation"
    elif score >= 55:
        return "MODERATE — Some audience fit but not strongly differentiated"
    elif score >= 40:
        return "WEAK — Low audience fit or commoditized topic"
    elif score >= 25:
        return "POOR — Misaligned with channel identity"
    else:
        return "REJECT — This topic will NOT grow the channel"


def rank_topics_by_growth(
    topics: list,
    ledger_path: str = "",
    verbose: bool = True,
) -> list:
    """
    Score all topics on growth alignment and re-rank.
    Topics are scored, then their cpm_weight is multiplied by the growth modifier.
    Final sort is by the new adjusted weight.

    Returns re-ranked list with growth scores embedded.
    """
    if not topics:
        return topics

    for topic in topics:
        growth_result = score_topic_growth_alignment(topic, ledger_path)
        topic.update(growth_result)

    # Apply growth modifier to cpm_weight
    for topic in topics:
        original_weight = topic.get("cpm_weight", 0)
        modifier = topic.get("growth_modifier", 1.0)
        topic["cpm_weight_original"] = original_weight
        topic["cpm_weight"] = round(original_weight * modifier, 1)

    # Re-sort by adjusted weight
    topics.sort(key=lambda x: x["cpm_weight"], reverse=True)

    if verbose:
        print("\n   📊 GROWTH ALIGNMENT SCORING:")
        print("   " + "─" * 65)
        for i, t in enumerate(topics[:5]):
            score = t.get("growth_score", 0)
            modifier = t.get("growth_modifier", 1.0)
            original = t.get("cpm_weight_original", 0)
            adjusted = t.get("cpm_weight", 0)
            verdict = t.get("growth_verdict", "")
            print(f"   {i+1}. [{score}/100] {t.get('title', '')[:50]}")
            print(f"      Weight: {original} × {modifier} = {adjusted} | {verdict}")
        print("   " + "─" * 65)

    return topics
