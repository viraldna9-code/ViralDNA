#!/usr/bin/env python3
"""
data_guard.py — Analytics Data-Average Guard
=============================================
Prevents the pipeline from answering questions with fabricated statistics.

Problem: When asked questions like "what % of views come from Search vs Browse?",
the LLM invents plausible-sounding numbers (97.2% Shorts, 70.5% Google Search,
11.2% likes/view) because the data isn't in our CSV exports, and LLMs are trained
to be "helpful" (i.e., always produce an answer).

Solution: This module defines exactly what data we HAVE and what we DON'T HAVE.
Any analytics answer MUST go through guard.check(question_type) first. If the
required data is missing, the guard returns a "not available" response with
instructions on what to download — NEVER a fabricated number.

VERSION: 1.0
"""

import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")

PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ANALYTICS_DIR = os.path.join(PROJECT_ROOT, "analytics")
DIAGNOSTICS_DIR = os.path.join(PROJECT_ROOT, "diagnostics")


# ─── DATA INVENTORY ──────────────────────────────────────────────────────────────
# Each entry says: we have this data, from how many samples, last updated.
# Everything NOT in this inventory is assumed unavailable.

def get_data_inventory() -> dict:
    """Scan analytics files and return what data is actually available."""
    inventory = {}

    # CTR performance log (from Studio CSV import)
    ctr_log_path = os.path.join(ANALYTICS_DIR, "ctr_performance_log.json")
    if os.path.exists(ctr_log_path):
        try:
            with open(ctr_log_path) as f:
                ctr = json.load(f)
            videos = ctr.get("videos", [])
            meaningful = [v for v in videos if v.get("impressions", 0) >= 50]
            inventory["ctr_performance"] = {
                "available": True,
                "source": "YouTube Studio CSV export (Table data.csv)",
                "videos_total": len(videos),
                "videos_meaningful": len(meaningful),
                "metrics": ["impressions", "ctr_percent", "views", "title"],
                "has_traffic_sources": False,
                "has_subscriber_data": False,
                "has_engagement_data": False,
                "last_updated": ctr.get("stats", {}).get("last_import", "unknown"),
            }
        except (json.JSONDecodeError, KeyError):
            inventory["ctr_performance"] = {"available": False, "reason": "corrupt file"}

    # Channel stats cache (from YouTube Data API)
    stats_path = os.path.join(ANALYTICS_DIR, "channel_stats_cache.json")
    if os.path.exists(stats_path):
        try:
            with open(stats_path) as f:
                stats = json.load(f)
            inventory["channel_stats"] = {
                "available": True,
                "source": "YouTube Data API (channels.list)",
                "metrics": ["subscriberCount", "viewCount", "videoCount"],
                "last_updated": stats.get("timestamp", "unknown"),
                "has_traffic_sources": False,
                "has_engagement_data": False,
                "has_subscriber_history": False,
            }
        except (json.JSONDecodeError, KeyError):
            inventory["channel_stats"] = {"available": False, "reason": "corrupt file"}

    # Metrics history (from periodic channel snapshots)
    metrics_path = os.path.join(ANALYTICS_DIR, "metrics_history.json")
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path) as f:
                mh = json.load(f)
            snapshots = mh.get("snapshots", [])
            inventory["metrics_history"] = {
                "available": True,
                "source": "Periodic channel snapshots",
                "snapshot_count": len(snapshots),
                "metrics": ["total_views", "subscribers", "video_count", "total_likes", "total_comments"],
                "has_subscriber_history": len(snapshots) >= 2,
                "has_traffic_sources": False,
            }
        except (json.JSONDecodeError, KeyError):
            inventory["metrics_history"] = {"available": False, "reason": "corrupt file"}

    # Growth ledger (from rag_feedback.py post-pipeline runs)
    ledger_path = os.path.join(DIAGNOSTICS_DIR, "growth_ledger.json")
    if os.path.exists(ledger_path):
        try:
            with open(ledger_path) as f:
                ledger = json.load(f)
            pm = ledger.get("performance_metrics", [])
            inventory["growth_ledger"] = {
                "available": True,
                "source": "YouTube Analytics API (rag_feedback.py)",
                "video_count": len(pm),
                "metrics": [
                    "views", "estimatedMinutesWatched", "averageViewDuration",
                    "averageViewPercentage", "subscribersGained", "likes",
                    "impressions", "impressionClickRate"
                ],
                "has_engagement_data": True,
                "has_retention_data": True,
                "has_subscriber_gains": True,
                "has_traffic_sources": False,  # API doesn't give this without trafficType dimension
            }
        except (json.JSONDecodeError, KeyError):
            inventory["growth_ledger"] = {"available": False, "reason": "corrupt file"}

    return inventory


# ─── QUESTION TYPES AND THEIR DATA REQUIREMENTS ─────────────────────────────────
# Maps question categories → required data sources.
# If the required data isn't in the inventory, the guard BLOCKS the answer.

QUESTION_REQUIREMENTS = {
    "traffic_sources": {
        "description": "Views by source (Browse/Suggested/Search/Shorts/External)",
        "required_metrics": ["traffic_source_type", "views_by_source"],
        "required_file": "traffic_sources_export.csv",
        "studio_path": "YouTube Studio → Analytics → Reach → Traffic Source Types → Export",
        "available": False,  # We don't have this in any current data source
    },
    "subscriber_conversion": {
        "description": "Subscriber conversion rate (subs / views)",
        "required_metrics": ["subscribersGained", "views"],
        "required_file": "growth_ledger.json OR channel_stats_cache.json",
        "studio_path": "Growth ledger (auto) or Studio → Analytics → Audience → Subscribers",
        "available": True,  # We have subscribersGained from API
    },
    "ctr_per_video": {
        "description": "CTR (click-through rate) per video",
        "required_metrics": ["impressions", "ctr_percent"],
        "required_file": "ctr_performance_log.json",
        "studio_path": "Studio → Analytics → Reach → Impressions click-through rate → Export",
        "available": True,
    },
    "engagement_ratios": {
        "description": "Likes per view, comments per view (engagement ratios)",
        "required_metrics": ["likes", "comments", "views"],
        "required_file": "growth_ledger.json or metrics_history.json",
        "studio_path": "Studio → Analytics → Engagement → Likes & Comments → Export",
        "available": True,  # Partial — likes available, comments may be limited
    },
    "avg_view_duration": {
        "description": "Average view duration ( Shorts vs long-form)",
        "required_metrics": ["averageViewDuration", "video_duration"],
        "required_file": "growth_ledger.json",
        "studio_path": "Auto from YouTube Analytics API (rag_feedback.py)",
        "available": True,
    },
    "browse_feature_growth": {
        "description": "Browse Features traffic growth over time",
        "required_metrics": ["traffic_source_type", "views_over_time"],
        "required_file": "traffic_sources_timeseries.csv",
        "studio_path": "Studio → Analytics → Reach → Traffic Source Types → Compare to previous period",
        "available": False,
    },
    "search_terms": {
        "description": "Top search terms driving traffic to channel",
        "required_metrics": ["search_keyword", "views_from_search"],
        "required_file": "search_terms_export.csv",
        "studio_path": "Studio → Analytics → Reach → Traffic Source → YouTube Search → See search terms",
        "available": False,  # YouTube hides this for small channels
    },
    "audience_demographics": {
        "description": "Audience age, gender, geography",
        "required_metrics": ["age_group", "gender", "country"],
        "required_file": "audience_demographics.csv",
        "studio_path": "Studio → Analytics → Audience → Demographics",
        "available": False,
    },
    "best_posting_time": {
        "description": "When your audience is online (heat map)",
        "required_metrics": ["viewer_hours", "day_of_week"],
        "required_file": "audience_activity.csv",
        "studio_path": "Studio → Analytics → Audience → When your viewers are on YouTube",
        "available": False,
    },
    "shorts_sweet_spot": {
        "description": "Optimal Shorts length for maximum reach",
        "required_metrics": ["video_duration_seconds", "views", "traffic_source"],
        "required_file": "ctr_performance_log.json + video duration data",
        "studio_path": "Requires joining Studio export with video metadata (duration)",
        "available": False,  # We have impressions/CTR but not duration per video in the CTR log
    },
    "growth_forecast": {
        "description": "Projected subscribers/views N days out",
        "required_metrics": ["subscriber_timeseries", "view_timeseries"],
        "required_file": "metrics_history.json (needs ≥4 weekly snapshots)",
        "studio_path": "Auto from periodic snapshots (needs more data)",
        "available": True,  # Can be estimated from existing snapshots but must be labeled as estimate
        "caveat": "Must be labeled as ROUGH ESTIMATE with confidence interval",
    },
}


# ─── GUARD FUNCTION ──────────────────────────────────────────────────────────────

def guard_check(question_type: str) -> dict:
    """
    Check if we have the data to answer a given type of question.

    Returns:
        {
            "can_answer": bool,
            "data_sources": [...],
            "missing_data": [...],
            "response": str,  # Either the "go ahead" signal or the BLOCKED message
        }
    """
    inventory = get_data_inventory()
    req = QUESTION_REQUIREMENTS.get(question_type)

    if req is None:
        return {
            "can_answer": False,
            "data_sources": [],
            "missing_data": ["unknown_question_type"],
            "response": (
                f"UNKNOWN QUESTION TYPE: '{question_type}'\n"
                f"This question type is not in the data guard registry.\n"
                f"Do NOT answer with fabricated numbers.\n"
                f"Available types: {', '.join(QUESTION_REQUIREMENTS.keys())}"
            ),
        }

    if not req["available"]:
        return {
            "can_answer": False,
            "data_sources": [],
            "missing_data": req["required_metrics"],
            "response": (
                f"DATA NOT AVAILABLE: Cannot answer '{question_type}' ({req['description']}).\n"
                f"Missing data: {', '.join(req['required_metrics'])}\n"
                f"\n"
                f"To get this data:\n"
                f"  {req['studio_path']}\n"
                f"\n"
                f"Then run: python3 scripts/ingest_studio_csv.py <downloaded_file>\n"
                f"\n"
                f"DO NOT fabricate numbers for this metric. Say: 'I don't have that data yet.'"
            ),
        }

    # Data is available — but check if the actual files have enough samples
    sources = []
    if question_type == "ctr_performance":
        if "ctr_performance" in inventory and inventory["ctr_performance"]["available"]:
            sources.append("ctr_performance_log.json")
    elif question_type == "engagement_ratios":
        if "growth_ledger" in inventory and inventory["growth_ledger"]["available"]:
            sources.append("growth_ledger.json")
        if "metrics_history" in inventory and inventory["metrics_history"]["available"]:
            sources.append("metrics_history.json")
    elif question_type == "subscriber_conversion":
        if "growth_ledger" in inventory and inventory["growth_ledger"]["available"]:
            sources.append("growth_ledger.json")

    warning = ""
    if question_type == "growth_forecast":
        warning = (
            "\n⚠️  CAVEAT: This is a ROUGH ESTIMATE based on limited historical data.\n"
            "ALWAYS label projections as estimates and include a confidence range.\n"
            "NEVER present projections as exact numbers (e.g., '~10-12 subs' NOT '11 subs')."
        )

    return {
        "can_answer": True,
        "data_sources": sources,
        "missing_data": [],
        "response": f"DATA AVAILABLE from: {', '.join(sources)}{warning}",
    }


# ─── FORMATTED "I DON'T HAVE THIS DATA" RESPONSE ─────────────────────────────────

def format_missing_data_response(topic: str, question_type: str) -> str:
    """Generate a consistent 'data not available' response for the LLM to use."""
    guard = guard_check(question_type)
    return f"""
╔══════════════════════════════════════════════════════════════╗
║  ⚠️  DATA NOT AVAILABLE — DO NOT FABRICATE                 ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Question: "{topic}"                                        ║
║  Category: {question_type}                                   ║
║                                                              ║
║  {guard['response']}
║                                                              ║
║  RULE: If you don't have the data, say so clearly.           ║
║  DO NOT invent specific numbers (%, counts, ratios).         ║
║  DO NOT present estimates as facts.                          ║
║  DO say: "I need you to download X from YouTube Studio."     ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


# ─── CLI ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 data_guard.py <question_type>")
        print(f"Types: {', '.join(QUESTION_REQUIREMENTS.keys())}")
        print("\nOr: python3 data_guard.py --inventory  (show what data we have)")
        sys.exit(1)

    if sys.argv[1] == "--inventory":
        inv = get_data_inventory()
        print(json.dumps(inv, indent=2, default=str))
        sys.exit(0)

    qtype = sys.argv[1]
    result = guard_check(qtype)
    print(result["response"])
    print(f"\nCan answer: {result['can_answer']}")
    print(f"Sources: {result['data_sources']}")
    print(f"Missing: {result['missing_data']}")
