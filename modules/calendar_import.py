#!/usr/bin/env python3
"""
Import blogwatcher articles into the ViralDNA content calendar.
Categorizes articles and adds them as pending topics.
"""
import json
import subprocess
import sys
import os
import re

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.content_calendar import add_topic, get_stats

# Category keywords for auto-categorization
CATEGORY_KEYWORDS = {
    "DISASTER": ["flood", "cyclone", "earthquake", "tsunami", "landslide", "drought",
                 "fire", "accident", "collapse", "rain", "storm", "hurricane",
                 "వరదలు", "తుఫాను", "భూకంపం", "అగ్ని", "ప్రమాదం"],
    "CRIME": ["murder", "theft", "robbery", "arrest", "police", "crime", "rape",
              "kidnapping", "fraud", "scam", "bribe", "corruption", "court",
              "హత్య", "దొంగతనం", "అరెస్టు", "పోలీసు", "నేరం"],
    "POLICY": ["policy", "scheme", "welfare", "subsidy", "budget", "allocation",
               "act", "bill", "amendment", "regulation", "reform",
               "పాలసీ", "పథకం", "బడ్జెట్", "చట్టం"],
    "POLITICS": ["election", "vote", "party", "minister", "cm", "mla", "mp",
                 "congress", "bjp", "tdp", "ysrcp", "janasena", "government",
                 "ఎన్నికలు", "పార్టీ", "మంత్రి", "ప్రభుత్వం"],
    "ECONOMICS": ["economy", "gdp", "inflation", "market", "stock", "price",
                  "trade", "export", "import", "investment", "growth",
                  "ఆర్థిక", "మార్కెట్", "ధరలు", "వాణిజ్యం"],
    "HEALTH": ["health", "hospital", "doctor", "disease", "covid", "vaccine",
               "medicine", "medical", "patient", "death", "virus",
               "ఆరోగ్య", "ఆసుపత్రి", "వైద్యుడు", "వ్యాధి"],
    "TECHNOLOGY": ["tech", "ai", "app", "software", "digital", "internet",
                   "cyber", "startup", "phone", "mobile", "computer",
                   "టెక్", "డిజిటల్", "సాఫ్ట్‌వేర్"],
    "ENTERTAINMENT": ["movie", "film", "actor", "actress", "music", "song",
                      "celebrity", "cinema", "tollywood", "bollywood",
                      "సినిమా", "నటుడు", "నటి", "సంగీతం"],
    "SPORTS": ["cricket", "match", "player", "team", "score", "win", "tournament",
               "ipl", "odi", "test", "football", "kabaddi",
               "క్రికెట్", "మ్యాచ్", "ప్లేయర్"],
}


def categorize_article(title):
    """Auto-categorize an article based on its title."""
    title_lower = title.lower()
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw.lower() in title_lower:
                score += 1
        if score > 0:
            scores[category] = score

    if not scores:
        return "POLITICS"  # Default for Telugu news

    return max(scores, key=scores.get)


def get_unread_articles():
    """Fetch unread articles from blogwatcher."""
    try:
        result = subprocess.run(
            ["blogwatcher-cli", "articles", "--json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            # Fallback: parse text output
            result = subprocess.run(
                ["blogwatcher-cli", "articles"],
                capture_output=True, text=True, timeout=30
            )
            return parse_text_articles(result.stdout)
        return json.loads(result.stdout)
    except Exception as e:
        print(f"Error fetching articles: {e}")
        return []


def parse_text_articles(text):
    """Parse blogwatcher text output into article dicts."""
    articles = []
    current = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and "]" in line:
            if current.get("title"):
                articles.append(current)
            current = {"title": line.split("]", 1)[1].strip()}
        elif line.startswith("Blog:"):
            current["blog"] = line.split(":", 1)[1].strip()
        elif line.startswith("URL:"):
            current["url"] = line.split(":", 1)[1].strip()
        elif line.startswith("Published:"):
            current["date"] = line.split(":", 1)[1].strip()
    if current.get("title"):
        articles.append(current)
    return articles


def import_articles(dry_run=False, max_articles=50):
    """Import unread articles into the content calendar."""
    articles = get_unread_articles()
    if not articles:
        print("No unread articles found. Run 'vdna feeds scan' first.")
        return

    print(f"Found {len(articles)} unread articles. Importing up to {max_articles}...")

    added = 0
    skipped = 0
    for article in articles[:max_articles]:
        title = article.get("title", "").strip()
        if not title:
            continue

        # Skip very short or generic titles
        if len(title) < 10:
            skipped += 1
            continue

        category = categorize_article(title)
        blog = article.get("blog", "unknown")
        url = article.get("url", "")

        if dry_run:
            print(f"  [DRY] [{category}] {title[:60]}... (from {blog})")
        else:
            add_topic(
                title=title,
                category=category,
                source=f"blogwatcher:{blog}",
                url=url,
                priority=5,
            )
        added += 1

    print(f"\n{'Would import' if dry_run else 'Imported'} {added} articles, skipped {skipped}.")
    stats = get_stats()
    print(f"Total pending topics: {stats['pending_topics']}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    max_articles = 50
    for arg in sys.argv:
        if arg.startswith("--max="):
            max_articles = int(arg.split("=")[1])

    import_articles(dry_run=dry_run, max_articles=max_articles)
