#!/usr/bin/env python3
"""
ViralDNA Pipeline Trigger via Telegram Reply
==============================================
When the user replies YES to a topic alert, the Hermes gateway
receives the message and starts a new agent session.
This module handles the reply and starts the production pipeline.

Flow:
  1. Monitor sends alert: "Produce this topic: [TITLE]. Reply YES to start."
  2. User replies YES on Telegram (any device)
  3. Hermes gateway receives the message -> agent session starts
  4. Agent reads last_topic.json -> starts production pipeline
  5. Pipeline produces 1 main + 2 shorts -> uploads to YouTube
"""
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IST = ZoneInfo("Asia/Kolkata")
LAST_TOPIC_FILE = os.path.join(PROJECT_ROOT, "logs", "last_topic.json")
PIPELINE_STATUS_FILE = os.path.join(PROJECT_ROOT, "logs", "pipeline_status.json")

def save_last_topic(topic: dict):
    """Save the topic from the latest monitor alert, so the reply handler can find it."""
    os.makedirs(os.path.dirname(LAST_TOPIC_FILE), exist_ok=True)
    data = {
        "title": topic["title"],
        "editorial_score": topic["editorial_score"],
        "source": topic["source"],
        "link": topic.get("link", ""),
        "reasons": topic.get("editorial_reasons", []),
        "timestamp": datetime.now(IST).isoformat(),
    }
    with open(LAST_TOPIC_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[trigger] Last topic saved: {topic['title'][:60]}")

def load_last_topic() -> dict | None:
    """Load the last alerted topic (to be produced)."""
    if not os.path.exists(LAST_TOPIC_FILE):
        return None
    with open(LAST_TOPIC_FILE) as f:
        return json.load(f)

def is_topic_fresh(max_age_hours=12) -> bool:
    """Check if the last topic is recent enough to produce."""
    topic = load_last_topic()
    if not topic:
        return False
    ts = datetime.fromisoformat(topic["timestamp"])
    return (datetime.now(IST) - ts).total_seconds() < max_age_hours * 3600

def save_pipeline_status(status: str, details: str):
    """Save pipeline execution status."""
    os.makedirs(os.path.dirname(PIPELINE_STATUS_FILE), exist_ok=True)
    with open(PIPELINE_STATUS_FILE, "w") as f:
        json.dump({
            "status": status,
            "details": details,
            "timestamp": datetime.now(IST).isoformat(),
        }, f, indent=2)

def load_pipeline_status() -> dict | None:
    if not os.path.exists(PIPELINE_STATUS_FILE):
        return None
    with open(PIPELINE_STATUS_FILE) as f:
        return json.load(f)
