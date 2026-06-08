# VERSION: 71.0
# MODULE: post_filter.py
# PURPOSE: Topic scoring driven by Google News RSS (editorially curated top stories)
#          + Google Trends RSS (supplementary virality signal) + source diversity
#          + recency + Telugu-relevance boost.
#          Cross-run category-based deduplication to prevent topic repetition.
#          v71.0: Redesigned scoring — Telugu relevance boost (up to +20), minimum
#          headline quality gate for trending queries, Trends RSS demoted to supplementary.

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


def _dedup_similar_titles(topics: list, threshold: float = 0.55) -> list:
    """
    Intra-batch deduplication: remove topics with Jaccard similarity >= threshold.
    Keeps the higher-scored topic, drops the lower-scored one.
    This catches near-duplicates like:
      "DMK to boycott June 8 — What Happened" vs "DMK to boycott June 8 — Why It Matters"
    """
    if len(topics) <= 1:
        return topics

    kept = []
    dropped = []
    for t in topics:
        title = t.get("title", "")
        is_dup = False
        for k in kept:
            sim = _title_similarity(title, k.get("title", ""))
            if sim >= threshold:
                is_dup = True
                dropped.append(f"{title[:50]}... (sim={sim:.2f} vs {k.get('title','')[:40]}...)")
                break
        if not is_dup:
            kept.append(t)

    if dropped:
        print(f"  [DEDUP] Dropped {len(dropped)} near-duplicate title(s):")
        for d in dropped:
            print(f"    {d}")
    return kept


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
        # ── Telugu relevance boost keywords (v71.0) ──
        # Topics directly about Telugu states, Tollywood, or Telugu people
        # get a meaningful boost so they rank above generic India news.
        # Max boost: +20 points (previously only +5).
        self.telugu_keywords = {
            # Telugu states and cities — highest priority
            "andhra pradesh": 8, "andhra": 5, "telangana": 6,
            "amaravati": 6, "hyderabad": 5, "visakhapatnam": 5, "vizag": 4,
            "vijayawada": 4, "tirupati": 4, "guntur": 4, "kakinada": 4,
            "nellore": 3, "warangal": 3, "karimnagar": 3, "kurnool": 3,
            "rajahmundry": 3, "ongole": 3, "eluru": 3,
            # Telugu politics — TDP/JSP/YSRCP leaders
            "telugu desam": 8, "tdp": 6, "ysrcp": 6, "jsp": 5,
            "nara lokesh": 8, "chandrababu naidu": 8, "chandrababu": 6,
            "ys jagan": 8, "jagan": 5, "pawan kalyan": 7,
            "naidu": 4, "amaravati": 5,
            # Tollywood / Telugu entertainment
            "tollywood": 6, "mahesh babu": 6, "prabhas": 6, "allu arjun": 6,
            "jr ntr": 6, "ram charan": 6, "nani": 5, "sai pallavi": 5,
            "keerthy suresh": 5, "samantha": 5, "rashmika": 5,
            "ss rajamouli": 7, "anirudh": 4, "sukumar": 4, "koratala siva": 4,
            "teja sajja": 4, "nithya menen": 4, "dulquer": 4, "fahad fasıl": 4,
            "rrr": 5, "bahubali": 5, "pushpa": 5,
            # Telugu identity / diaspora
            "telugu": 5, "telugu people": 6, "telugu nri": 6, "telugu american": 6,
        }

    def run(self, topics: list):
        import re
        print("▶ Phase 1.2: Topic Scoring (Google News RSS + Trends + Telugu relevance + recency)...")
        weighted_topics = []

        for t in topics:
            title_lower = t.get("title", "").lower()
            desc_lower = t.get("description", "").lower()
            source_name = t.get("source", "").lower()

            # ── HEADLINE QUALITY GATE (v71.0) ──
            # Reject Google Trends search queries that are too short/fragmentary
            # to be usable as news headlines.
            if "google trends (india daily)" in source_name:
                title_raw = t.get("title", "")
                word_count = len(title_raw.split())
                alpha_chars = sum(1 for c in title_raw if c.isalpha())
                # Reject if: < 3 words OR < 15 alpha chars
                # e.g. "times of india" (3 words, 13 alpha), "pm svanidhi" (2 words)
                if word_count < 3 or alpha_chars < 15:
                    print(f"  [SKIP] Low-quality trend query rejected: '{title_raw}'")
                    continue

            # ── PRIMARY: Source virality score (0-50) ──
            # Google News RSS (Telugu-relevant) = 50 pts — people reading + Telugu boost
            # Google News RSS (non-Telugu India) = 30 pts — people reading but not Telugu-focused
            # Google Trends RSS = 20 pts — supplementary virality, search queries are lower quality
            # RSS feeds = 10 pts — editorial news, baseline
            trending_score = 0
            if "google news rss" in source_name:
                # v71.0: Telugu-relevant Google News stories get 50, generic India gets 30
                # This ensures Telugu national news (e.g. AP politics in national press) wins
                _title_check = title_lower + " " + desc_lower
                _telugu_in_news = any(
                    re.search(rf"\b{re.escape(kw)}\b", _title_check)
                    for kw in ["andhra", "telangana", "telugu", "hyderabad", "vizag",
                               "visakhapatnam", "tollywood", "tdp", "ysrcp", "amaravati",
                               "chandrababu", "jagan", "lokesh", "pawan kalyan",
                               "mahesh babu", "prabhas", "allu arjun", "jr ntr", "ram charan"]
                )
                if _telugu_in_news:
                    trending_score = 50  # Telugu story in national news = maximum relevance
                else:
                    trending_score = 30  # Generic India trending news
            elif "google trends (india daily)" in source_name:
                trending_score = 20  # Search queries are supplementary, not headlines
            elif "google trends (related" in source_name:
                trending_score = 15
            elif "google trends (us" in source_name:
                trending_score = 10
            elif "youtube trending" in source_name:
                trending_score = 20
            elif "reddit" in source_name:
                trending_score = 15
            elif "inshorts" in source_name:
                trending_score = 12
            elif "rss" in source_name or "feed" in source_name:
                trending_score = 10

            # ── SECONDARY: Source diversity (0-14) ──
            num_sources = t.get("num_sources", 1)
            source_score = min(num_sources * 7, 14)

            # ── TERTIARY: Recency decay (0-15) ──
            recency_score = 0
            pub_date_str = t.get("published", t.get("date", ""))
            if pub_date_str:
                try:
                    if isinstance(pub_date_str, str):
                        pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                    else:
                        pub_date = pub_date_str
                    now_dt = datetime.now(timezone.utc)
                    age_hours = (now_dt - pub_date).total_seconds() / 3600
                    if age_hours < 2:
                        recency_score = 15
                    elif age_hours < 6:
                        recency_score = 10
                    elif age_hours < 12:
                        recency_score = 5
                except Exception:
                    recency_score = 5
            else:
                recency_score = 5

            # ── QUATERNARY: Telugu relevance boost (0-20) ──
            # v71.0: Expanded from max +5 to max +20.
            # Topics about Telugu states, politics, Tollywood, Telugu people
            # get a MAJOR boost so they outrank generic India news.
            telugu_boost = 0
            for kw, score in self.telugu_keywords.items():
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, title_lower) or re.search(pattern, desc_lower):
                    telugu_boost += score
            telugu_boost = min(telugu_boost, 20)  # Hard cap at 20 points

            # ── FINAL WEIGHT ──
            weight = 5 + trending_score + source_score + recency_score + telugu_boost
            t["cpm_weight"] = weight
            t["_trending_score"] = trending_score
            t["_source_score"] = source_score
            t["_recency_score"] = recency_score
            t["_telugu_boost"] = telugu_boost
            weighted_topics.append(t)

        # Sort topics descending by weight
        weighted_topics.sort(key=lambda x: x["cpm_weight"], reverse=True)

        # ── Intra-Batch Deduplication: remove near-duplicate titles ──
        # Catches: "DMK to boycott June 8 — What Happened" vs "DMK to boycott June 8 — Why It Matters"
        before_count = len(weighted_topics)
        weighted_topics = _dedup_similar_titles(weighted_topics, threshold=0.45)
        if len(weighted_topics) < before_count:
            print(f"  [DEDUP] Intra-batch: {before_count} → {len(weighted_topics)} topics (-{before_count - len(weighted_topics)} near-dupes)")

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

        for t in weighted_topics[:5]:
            print(f"    Scored: {t['title'][:45]}... | Total: {t['cpm_weight']} (trend={t['_trending_score']}, src={t['_source_score']}, fresh={t['_recency_score']}, telugu={t['_telugu_boost']})")

        return weighted_topics
