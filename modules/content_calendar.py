#!/usr/bin/env python3
"""
Content Calendar for ViralDNA
Manages content scheduling, topic pipeline, and category rotation.
Integrates with blogwatcher for topic discovery.
"""
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

CALENDAR_PATH = os.path.expanduser("~/.hermes/viral_dna/content_calendar.json")
TOPICS_PATH = os.path.expanduser("~/.hermes/viral_dna/content_topics.json")

# Category rotation weights (higher = more frequent)
CATEGORY_WEIGHTS = {
    "POLITICS": 3,
    "POLICY": 2,
    "ECONOMICS": 2,
    "DISASTER": 2,
    "CRIME": 2,
    "HEALTH": 1,
    "TECHNOLOGY": 1,
    "ENTERTAINMENT": 1,
    "SPORTS": 1,
}

# Minimum days between same category
CATEGORY_COOLDOWN_DAYS = {
    "POLITICS": 1,
    "POLICY": 1,
    "ECONOMICS": 1,
    "DISASTER": 0,  # Breaking news — no cooldown
    "CRIME": 1,
    "HEALTH": 2,
    "TECHNOLOGY": 2,
    "ENTERTAINMENT": 2,
    "SPORTS": 2,
}


def _ensure_dirs():
    os.makedirs(os.path.dirname(CALENDAR_PATH), exist_ok=True)


def _load_calendar():
    _ensure_dirs()
    if os.path.exists(CALENDAR_PATH):
        with open(CALENDAR_PATH) as f:
            return json.load(f)
    return {"published": [], "scheduled": [], "stats": {}}


def _save_calendar(calendar):
    _ensure_dirs()
    with open(CALENDAR_PATH, "w") as f:
        json.dump(calendar, f, indent=2, default=str)


def _load_topics():
    _ensure_dirs()
    if os.path.exists(TOPICS_PATH):
        with open(TOPICS_PATH) as f:
            return json.load(f)
    return {"pending": [], "used": []}


def _save_topics(topics):
    _ensure_dirs()
    with open(TOPICS_PATH, "w") as f:
        json.dump(topics, f, indent=2, default=str)


def get_next_category():
    """Pick the next content category based on weights and cooldowns."""
    calendar = _load_calendar()
    published = calendar.get("published", [])

    # Get last publish date per category
    last_published = {}
    for entry in published:
        cat = entry.get("category", "UNKNOWN")
        pub_date = entry.get("date", "")
        if pub_date:
            if cat not in last_published or pub_date > last_published[cat]:
                last_published[cat] = pub_date

    now = datetime.now()
    available = []
    for cat, weight in CATEGORY_WEIGHTS.items():
        cooldown = CATEGORY_COOLDOWN_DAYS.get(cat, 1)
        if cat in last_published:
            last_date = datetime.fromisoformat(last_published[cat])
            days_since = (now - last_date).days
            if days_since < cooldown:
                continue
        available.append((cat, weight))

    if not available:
        # All on cooldown — pick the one with most days since last publish
        oldest_cat = min(last_published.keys(),
                         key=lambda c: datetime.fromisoformat(last_published[c]))
        return oldest_cat

    # Weighted random selection
    import random
    total_weight = sum(w for _, w in available)
    r = random.uniform(0, total_weight)
    cumulative = 0
    for cat, weight in available:
        cumulative += weight
        if r <= cumulative:
            return cat

    return available[-1][0]


def add_topic(title, category, source="manual", url="", priority=5):
    """Add a topic to the pending queue."""
    topics = _load_topics()
    topic = {
        "id": f"topic_{int(datetime.now().timestamp())}",
        "title": title,
        "category": category,
        "source": source,
        "url": url,
        "priority": priority,  # 1-10, higher = more important
        "added": datetime.now().isoformat(),
        "status": "pending",
    }
    topics["pending"].append(topic)
    # Sort by priority (descending)
    topics["pending"].sort(key=lambda t: t.get("priority", 5), reverse=True)
    _save_topics(topics)
    return topic


def get_next_topic():
    """Get the highest priority pending topic."""
    topics = _load_topics()
    if not topics["pending"]:
        return None
    return topics["pending"][0]


def mark_topic_used(topic_id, video_id=""):
    """Mark a topic as used after publishing."""
    topics = _load_topics()
    for i, t in enumerate(topics["pending"]):
        if t["id"] == topic_id:
            topic = topics["pending"].pop(i)
            topic["status"] = "used"
            topic["used_date"] = datetime.now().isoformat()
            topic["video_id"] = video_id
            topics["used"].append(topic)
            break
    _save_topics(topics)


def schedule_content(topic_id, scheduled_date, category):
    """Schedule content for a specific date."""
    calendar = _load_calendar()
    entry = {
        "topic_id": topic_id,
        "scheduled_date": scheduled_date.isoformat() if isinstance(scheduled_date, datetime) else scheduled_date,
        "category": category,
        "status": "scheduled",
        "created": datetime.now().isoformat(),
    }
    calendar["scheduled"].append(entry)
    _save_calendar(calendar)
    return entry


def mark_published(topic_id, video_id, title, category):
    """Mark content as published."""
    calendar = _load_calendar()
    entry = {
        "topic_id": topic_id,
        "video_id": video_id,
        "title": title,
        "category": category,
        "date": datetime.now().isoformat(),
        "status": "published",
    }
    calendar["published"].append(entry)

    # Remove from scheduled
    calendar["scheduled"] = [
        s for s in calendar["scheduled"]
        if s.get("topic_id") != topic_id
    ]

    # Update stats
    stats = calendar.get("stats", {})
    cat_count = stats.get("category_counts", {})
    cat_count[category] = cat_count.get(category, 0) + 1
    stats["category_counts"] = cat_count
    stats["total_published"] = stats.get("total_published", 0) + 1
    stats["last_published"] = datetime.now().isoformat()
    calendar["stats"] = stats

    _save_calendar(calendar)
    mark_topic_used(topic_id, video_id)


def get_stats():
    """Get content calendar statistics."""
    calendar = _load_calendar()
    topics = _load_topics()
    stats = calendar.get("stats", {})
    return {
        "total_published": stats.get("total_published", 0),
        "pending_topics": len(topics.get("pending", [])),
        "used_topics": len(topics.get("used", [])),
        "scheduled": len(calendar.get("scheduled", [])),
        "category_counts": stats.get("category_counts", {}),
        "last_published": stats.get("last_published", "never"),
    }


def get_upcoming(days=7):
    """Get content scheduled for the next N days."""
    calendar = _load_calendar()
    now = datetime.now()
    cutoff = now + timedelta(days=days)
    upcoming = []
    for entry in calendar.get("scheduled", []):
        try:
            sched_date = datetime.fromisoformat(entry["scheduled_date"])
            if now <= sched_date <= cutoff:
                upcoming.append(entry)
        except (ValueError, TypeError):
            continue
    return upcoming


def list_pending(limit=20):
    """List pending topics."""
    topics = _load_topics()
    return topics.get("pending", [])[:limit]


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "stats":
            print(json.dumps(get_stats(), indent=2))
        elif cmd == "next-cat":
            print(get_next_category())
        elif cmd == "next-topic":
            t = get_next_topic()
            print(json.dumps(t, indent=2) if t else "No pending topics")
        elif cmd == "list":
            for t in list_pending():
                print(f"  [{t['priority']}] {t['title']} ({t['category']}) - {t['source']}")
        elif cmd == "add" and len(sys.argv) >= 4:
            topic = add_topic(
                title=sys.argv[2],
                category=sys.argv[3],
                priority=int(sys.argv[4]) if len(sys.argv) > 4 else 5,
            )
            print(f"Added: {topic['title']}")
        else:
            print("Usage: content_calendar.py [stats|next-cat|next-topic|list|add TITLE CATEGORY [PRIORITY]]")
    else:
        # Default: show stats
        stats = get_stats()
        print("=== ViralDNA Content Calendar ===")
        print(f"Total published: {stats['total_published']}")
        print(f"Pending topics: {stats['pending_topics']}")
        print(f"Scheduled: {stats['scheduled']}")
        print(f"Last published: {stats['last_published']}")
        print(f"\nCategory distribution: {json.dumps(stats['category_counts'], indent=2)}")


class ContentCalendar:
    """Wrapper class for content_calendar module functions."""

    def get_weekly_schedule(self):
        """Return weekly content schedule."""
        stats = get_stats()
        return {
            "shorts_per_week": 7,
            "mains_per_week": 3,
            "pending_topics": stats.get("pending_topics", 0),
            "scheduled": stats.get("scheduled", 0),
            "category_counts": stats.get("category_counts", {}),
        }

    def get_next_topic(self):
        """Get next pending topic."""
        topics = list_pending()
        if topics:
            return topics[0]
        return None

    def mark_topic_used(self, topic_id):
        """Mark a topic as used."""
        pass
