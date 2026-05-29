# VERSION: 52.0
# MODULE: post_filter.py
# PURPOSE: Topic scoring driven by Google Trends (what people actually search)
#          + source diversity + recency. Minimal CPM nudge only.
#          Cross-run category-based deduplication to prevent topic repetition.

import json
import os
from datetime import datetime, timedelta, timezone

# ── Cross-Run Topic History ──────────────────────────────────────────────────
TOPIC_HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "runtime", "topic_history.json")
TOPIC_DEDUP_LOOKBACK_DAYS = 3  # Don't repeat topics used in last 3 days
TOPIC_MIN_KEYWORD_OVERLAP = 0.5  # Min fraction of topic keywords that must match


# Topic category tags for deduplication — broader than keywords
# If two titles share a category tag within the lookback window, they're the same topic
TOPIC_CATEGORIES = {
    "visa_immigration": [
        "visa", "h1b", "h-1b", "b1", "b2", "f1", "o1", "o-1", "l1", "l-1",
        "greencard", "green card", "permanent resident", "pr ", "pr:", "citizenship",
        "immigration", "deport", "asylum", "refugee", "border", "customs", "cbp",
        "uscis", "embassy", "consulate", "passport"
    ],
    "nri_diaspora": [
        "nri", "non-resident", "nris", "diaspora", "expat", "expatriate",
        "telugu abroad", "indian abroad", "overseas indian", "pravasi",
        "nri marriage", "nri wedding", "nri match", "nri matrimony",
        "telugu nri", "indian nri"
    ],
    "marriage_family": [
        "marriage", "wedding", "matrimony", "bride", "groom", "match", "partner",
        "spouse", "husband", "wife", "divorce", "family planning", "dowry",
        "arranged marriage", "love marriage", "engagement"
    ],
    "politics_government": [
        "trump", "biden", "congress", "senate", "house of representatives",
        "supreme court", "ruling", "executive order", "policy", "regulation",
        "election", "campaign", "vote", "ballot", "democrat", "republican",
        "government", "minister", "prime minister", "president"
    ],
    "jobs_career": [
        "job", "hiring", "layoff", "unemployment", "career", "salary", "offer",
        "interview", "resume", "recruitment", "work permit", "labor cert",
        "h1b worker", "foreign worker", "employment"
    ],
    "weather_disaster": [
        "cyclone", "hurricane", "typhoon", "earthquake", "flood", "tsunami",
        "landslide", "drought", "wildfire", "storm", "monsoon", "heat wave",
        "cold wave", "tornado", "volcano", "disaster", "evacuation"
    ],
    "technology": [
        "tech", "software", "ai", "artificial intelligence", "machine learning",
        "startup", "app", "cyber", "hack", "data breach", "cloud", "saas",
        "google", "apple", "microsoft", "meta", "amazon"
    ],
    "entertainment": [
        "movie", "film", "cinema", "actor", "actress", "director", "box office",
        "bollywood", "tollywood", "sandalwood", "kollywood", "release", "trailer",
        "review", "hero", "heroine", "music", "song", "album", "concert",
        "mahesh babu", "prabhas", "allu arjun", "jr ntr", "ram charan",
        "ss rajamouli", "keerthy suresh", "samantha", "rashmika"
    ],
    "sports": [
        "cricket", "ipl", "world cup", "t20", "odi", "test match", "football",
        "soccer", "hockey", "tennis", "badminton", "olympics", "score",
        "virat", "dhoni", "rohit", "sachin", "kohli"
    ],
    "health_medical": [
        "health", "medical", "hospital", "doctor", "vaccine", "disease",
        "covid", "corona", "pandemic", "medicine", "treatment", "drug",
        "fda", "clinical", "symptom"
    ],
    "finance_economy": [
        "economy", "inflation", "recession", "gdp", "stock", "market", "sensex",
        "nifty", "mutual fund", "investment", "real estate", "housing", "mortgage",
        "bank", "loan", "emi", "fd", "nre", "nro", "remittance",
        "amaravati", "investment", "budget", "tax", "gst", "income tax"
    ],
    "travel_transport": [
        "travel", "flight", "airline", "airport", "booking", "cancellation",
        "delay", "layover", "transit", "ticket", "fare", "luggage", "baggage",
        "highway", "road", "train", "railway", "metro"
    ],
    "education": [
        "education", "university", "college", "school", "student", "exam",
        "score", "admission", "scholarship", "loan", "gmat", "gre", "toefl",
        "ielts", "grade", "degree", "phd", "master", "bachelor"
    ],
    "crime_law": [
        "crime", "police", "arrest", "murder", "theft", "fraud", "scam",
        "lawsuit", "court", "judge", "verdict", "sentence", "jail", "prison",
        "investigation", "cybercrime", "harassment"
    ]
}


def _get_topic_categories(title: str, description: str = "") -> set:
    """Map a title+description to a set of broad topic categories.
    This is FAR more reliable for deduplication than keyword overlap,
    because 'H1B visa rules' and 'Trump visa restrictions' both map to
    {'visa_immigration'} — clearly the same topic."""
    import re
    text = (title + " " + description).lower()
    categories = set()
    for cat_name, keywords in TOPIC_CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                categories.add(cat_name)
                break  # One match is enough to assign the category
    return categories


def _load_topic_history() -> list:
    """Load topic history from JSON file. Returns list of {title, date} dicts."""
    if not os.path.exists(TOPIC_HISTORY_PATH):
        return []
    try:
        with open(TOPIC_HISTORY_PATH, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, IOError):
        pass
    return []


def _save_topic_history(history: list):
    """Save topic history to JSON file, pruning entries older than 30 days."""
    os.makedirs(os.path.dirname(TOPIC_HISTORY_PATH), exist_ok=True)
    # Prune entries older than 30 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    pruned = [e for e in history if e.get("date", "") >= cutoff]
    try:
        with open(TOPIC_HISTORY_PATH, "w") as f:
            json.dump(pruned, f, indent=2)
    except IOError:
        pass


def _tokenize_title(title: str) -> set:
    """Tokenize a title into a set of lowercase words (3+ chars)."""
    import re
    stop = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
            "to", "for", "of", "and", "or", "but", "with", "from", "by",
            "about", "new", "latest", "update", "breaking", "just"}
    return set(w.lower() for w in re.findall(r'[a-zA-Z]{3,}', title) if w.lower() not in stop)


def _title_similarity(title1: str, title2: str) -> float:
    """Jaccard similarity between two titles. Returns 0.0-1.0."""
    t1 = _tokenize_title(title1)
    t2 = _tokenize_title(title2)
    if not t1 or not t2:
        return 0.0
    intersection = len(t1 & t2)
    union = len(t1 | t2)
    return intersection / union if union > 0 else 0.0


def _is_topic_used_recently(title: str, history: list, lookback_days: int = TOPIC_DEDUP_LOOKBACK_DAYS, description: str = "") -> bool:
    """Check if a topic with overlapping categories was used in the last N days.
    Uses broad topic categories (visa_immigration, weather_disaster, etc.)
    instead of keyword overlap — far more reliable for detecting same-topic stories."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    new_cats = _get_topic_categories(title, description)
    if not new_cats:
        return False
    for entry in history:
        entry_date_str = entry.get("date", "")
        try:
            entry_date = datetime.fromisoformat(entry_date_str.replace("Z", "+00:00"))
            if entry_date < cutoff:
                continue
        except (ValueError, TypeError):
            continue
        entry_title = entry.get("title", "")
        entry_cats = _get_topic_categories(entry_title)
        if not entry_cats:
            continue
        # If ANY category overlaps, it's the same topic
        if new_cats & entry_cats:
            return True
    return False


def record_topic_usage(title: str, description: str = ""):
    """Record that a topic was used in the current run. Also stores categories for reliable dedup."""
    history = _load_topic_history()
    now = datetime.now(timezone.utc).isoformat()
    categories = _get_topic_categories(title, description)
    history.append({
        "title": title,
        "date": now,
        "categories": list(categories)
    })
    _save_topic_history(history)


class PostFilter:
    def __init__(self, config_dict: dict):
        self.config = dict(config_dict) if config_dict else {}
        # Minimal CPM boost — only a tiny nudge, never the deciding factor.
        # The scoring is driven by what people are ACTUALLY searching (Google Trends)
        # and how many sources confirm it (source diversity).
        self.cpm_boost_keywords = {
            "telugu": 3, "andhra": 3, "telangana": 3,
            "tollywood": 3, "hyderabad": 2, "vizag": 2,
        }

    def run(self, topics: list) -> list:
        print("▶ Phase 1.2: Topic Scoring (Google Trends primary + source diversity + recency)...")
        weighted_topics = []
        
        for t in topics:
            title_lower = t.get("title", "").lower()
            desc_lower = t.get("description", "").lower()
            
            # ── PRIMARY: Google Trends score (0-50) ──
            # If people are actively searching for this, it MATTERS.
            trending_score = 0
            source_name = t.get("source", "").lower()
            if "google trends (india daily)" in source_name:
                trending_score = 50  # India daily trends = what Telugu people are searching NOW
            elif "google trends (related" in source_name:
                trending_score = 35  # Related topics to AP/Telugu keywords
            elif "google trends (us" in source_name:
                trending_score = 25  # US trends relevant to NRIs
            elif "youtube trending" in source_name:
                trending_score = 20  # YouTube trending = viral content
            elif "reddit" in source_name:
                trending_score = 15  # Reddit = community discussion
            elif "inshorts" in source_name:
                trending_score = 12  # Inshorts = curated news
            elif "rss" in source_name or "feed" in source_name:
                trending_score = 10  # RSS = editorial news
            
            # ── SECONDARY: Source diversity (0-30) ──
            # Story confirmed by multiple independent sources = more credible/important
            num_sources = t.get("num_sources", 1)
            source_score = min(num_sources * 10, 30)
            
            # ── TERTIARY: Recency decay (0-15) ──
            # Fresher stories get a small boost
            recency_score = 0
            pub_date_str = t.get("published", t.get("date", ""))
            if pub_date_str:
                try:
                    from datetime import datetime, timedelta, timezone
                    if isinstance(pub_date_str, str):
                        pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                    else:
                        pub_date = pub_date_str
                    now = datetime.now(timezone.utc)
                    age_hours = (now - pub_date).total_seconds() / 3600
                    if age_hours < 2:
                        recency_score = 15  # Breaking: less than 2 hours old
                    elif age_hours < 6:
                        recency_score = 10  # Very fresh: under 6 hours
                    elif age_hours < 12:
                        recency_score = 5   # Same day: under 12 hours
                except Exception:
                    recency_score = 5  # Can't parse date = give benefit of doubt
            else:
                recency_score = 5  # No date = treat as recent
            
            # ── MINIMAL: CPM niche nudge (0-5 max) ──
            # Tiny boost for explicitly Telugu-relevant keywords.
            # This should NEVER override a trending topic from Google Trends.
            cpm_boost = 0
            import re
            for kw, score in self.cpm_boost_keywords.items():
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, title_lower) or re.search(pattern, desc_lower):
                    cpm_boost += score
            cpm_boost = min(cpm_boost, 5)  # Hard cap at 5 points
            
            # ── FINAL WEIGHT: Trends + sources + recency + tiny CPM nudge ──
            weight = 5 + trending_score + source_score + recency_score + cpm_boost
            t["cpm_weight"] = weight
            t["_trending_score"] = trending_score
            t["_source_score"] = source_score
            t["_recency_score"] = recency_score
            t["_cpm_boost"] = cpm_boost
            weighted_topics.append(t)
            
        # Sort topics descending by weight
        weighted_topics.sort(key=lambda x: x["cpm_weight"], reverse=True)

        # ── Cross-Run Deduplication: filter out recently used topics ──
        history = _load_topic_history()
        if history:
            deduped = []
            skipped = []
            for t in weighted_topics:
                if _is_topic_used_recently(t.get("title", ""), history, description=t.get("description", "")):
                    skipped.append(t.get("title", "")[:60])
                else:
                    deduped.append(t)
            if skipped:
                print(f"  [DEDUP] Skipped {len(skipped)} recently-used topic(s): {', '.join(skipped)}")
            if deduped:
                weighted_topics = deduped
            else:
                print("  [DEDUP] All topics filtered — history too recent, allowing top topic through")
                weighted_topics = [weighted_topics[0]]

        for t in weighted_topics[:3]:
            print(f"    Scored: {t['title'][:40]}... | Total: {t['cpm_weight']} (trend={t['_trending_score']}, src={t['_source_score']}, fresh={t['_recency_score']}, cpm={t['_cpm_boost']})")

        return weighted_topics
