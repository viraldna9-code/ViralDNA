# VERSION: 1.0
# MODULE: rag_feedback.py
# PURPOSE: RAG Feedback Loop — Pull YouTube Analytics, store performance metrics,
#          and generate actionable insights that feed back into discovery + scripting.
#
# After each pipeline run, this module:
#   1. Pulls YouTube Analytics (views, CTR, avg duration, impressions, likes)
#   2. Stores metrics in the growth ledger (linked to topic + upload ID)
#   3. Generates performance insights (what topics/formats work best)
#   4. Creates a "producer brief" — a text summary injected into the next run's
#      script prompt so Gemini learns from past performance

import os
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")


class RagFeedbackLoop:
    def __init__(self, ledger_path: str = None):
        drive_base = os.getenv("DRIVE_BASE", "/home/jay/ViralDNA")
        if ledger_path is None:
            ledger_path = os.path.join(drive_base, "diagnostics", "growth_ledger.json")
        self.ledger_path = ledger_path
        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)

    # ─── Load / Save Ledger ───────────────────────────────────────────
    def _load_ledger(self) -> dict:
        if os.path.exists(self.ledger_path):
            try:
                with open(self.ledger_path, "r") as f:
                    ledger = json.load(f)
                # Migrate: ensure new keys exist from older ledger formats
                ledger.setdefault("performance_metrics", [])
                ledger.setdefault("producer_briefs", [])
                if "user_reviews" not in ledger:
                    ledger["user_reviews"] = {"scripts": [], "thumbnails": [], "videos": []}
                if "growth_recommendations" not in ledger:
                    ledger["growth_recommendations"] = []
                if "known_errors_log" not in ledger:
                    ledger["known_errors_log"] = []
                if "execution_history" not in ledger:
                    ledger["execution_history"] = []
                return ledger
            except Exception:
                pass
        return self._blank_ledger()

    def _save_ledger(self, ledger: dict):
        try:
            with open(self.ledger_path, "w") as f:
                json.dump(ledger, f, indent=2)
        except Exception as e:
            print(f"  ⚠️ RAG: Failed to save ledger: {e}")

    def _blank_ledger(self) -> dict:
        now = datetime.now(_IST).isoformat()
        return {
            "system_version": "57.0",
            "created_at": now,
            "execution_history": [],
            "user_reviews": {"scripts": [], "thumbnails": [], "videos": []},
            "growth_recommendations": [],
            "known_errors_log": [],
            "performance_metrics": [],   # NEW: per-video analytics snapshots
            "producer_briefs": []         # NEW: historical producer briefs
        }

    # ─── Step 1: Pull YouTube Analytics ───────────────────────────────
    def pull_youtube_analytics(self, youtube_service, video_ids: list) -> dict:
        """
        Pull YouTube Analytics v2 data for a list of video IDs.
        Returns dict keyed by video_id with metrics.
        Uses the YouTube Analytics Reporting API (free, needs youtube.readonly scope).
        """
        results = {}
        if not youtube_service or not video_ids:
            return results

        # Filter to only valid-looking IDs
        valid_ids = [v for v in video_ids if v and len(v) >= 8]
        if not valid_ids:
            return results

        try:
            # YouTube Analytics API v2 — query last 30 days
            end_date = datetime.now(_IST).strftime("%Y-%m-%d")
            start_date = (datetime.now(_IST) - timedelta(days=30)).strftime("%Y-%m-%d")

            for vid in valid_ids:
                try:
                    resp = youtube_service.reports().query(
                        ids="channel==MINE",
                        startDate=start_date,
                        endDate=end_date,
                        metrics="views,estimatedMinutesWatched,averageViewDuration,"
                                "averageViewPercentage,subscribersGained,likes,impressions,impressionClickRate",
                        dimensions="video",
                        filters=f"video=={vid}",
                        maxResults=1
                    ).execute()

                    rows = resp.get("rows", [])
                    if rows:
                        row = rows[0]
                        results[vid] = {
                            "views":              int(row[0]) if row[0] else 0,
                            "estimatedMinutesWatched": float(row[1]) if row[1] else 0.0,
                            "averageViewDuration": float(row[2]) if row[2] else 0.0,
                            "averageViewPercentage": float(row[3]) if row[3] else 0.0,
                            "subscribersGained":  int(row[4]) if row[4] else 0,
                            "likes":              int(row[5]) if row[5] else 0,
                            "impressions":        int(row[6]) if row[6] else 0,
                            "impressionClickRate": float(row[7]) if row[7] else 0.0,
                        }
                    else:
                        results[vid] = {"views": 0, "note": "no data yet (new video)"}
                except Exception as e:
                    error_str = str(e)
                    if "403" in error_str or "insufficient" in error_str.lower():
                        # Channel may not have Analytics API access yet
                        results[vid] = {"views": None, "note": f"API limit: {error_str[:80]}"}
                    else:
                        results[vid] = {"views": None, "note": error_str[:100]}
        except Exception as e:
            print(f"  ⚠️ YouTube Analytics pull failed: {e}")

        return results

    # ─── Step 2: Store Metrics in Ledger ──────────────────────────────
    def store_metrics(self, metrics_by_id: dict, topic_title: str):
        """Store a performance snapshot in the growth ledger."""
        ledger = self._load_ledger()

        snapshot = {
            "timestamp": datetime.now(_IST).isoformat(),
            "topic": topic_title,
            "videos": {}
        }

        for vid, m in metrics_by_id.items():
            snapshot["videos"][vid] = m

            # Also update the execution_history entry for this video
            for entry in reversed(ledger.get("execution_history", [])):
                upload = entry.get("upload_results", {})
                main_id = upload.get("main_id", "")
                shorts = upload.get("standalone_shorts_uploads", [])
                all_ids = [main_id] + [s.get("youtube_id", "") for s in shorts]
                if vid in all_ids:
                    entry.setdefault("performance", {})[vid] = m
                    break

        ledger["performance_metrics"].append(snapshot)
        self._save_ledger(ledger)
        print(f"  📊 RAG: Stored performance snapshot for topic: '{topic_title}'")
        return snapshot

    # ─── Step 3: Generate Producer Brief ──────────────────────────────
    def generate_producer_brief(self) -> str:
        """
        Analyze all historical performance data and generate a text brief
        that will be injected into the next prompt.
        
        The brief covers:
        - Top-performing topics (by views / CTR)
        - Lowest-performing topics
        - Format insights (main vs shorts performance)
        - Content angle recommendations
        """
        ledger = self._load_ledger()
        metrics = ledger.get("performance_metrics", [])
        history = ledger.get("execution_history", [])

        if not metrics and not history:
            return "No performance data available yet. This is the first run."

        # Collect all video-perf pairs with topic labels
        video_data = []  # [(topic, views, ctr, avg_pct, likes, is_short)]
        for snap in metrics:
            topic = snap.get("topic", "Unknown")
            for vid, m in snap.get("videos", {}).items():
                views = m.get("views") or 0
                ctr = m.get("impressionClickRate") or 0.0
                avg_pct = m.get("averageViewPercentage") or 0.0
                likes = m.get("likes") or 0
                is_short = views > 0 and m.get("averageViewDuration", 0) < 90
                video_data.append({
                    "topic": topic, "views": views, "ctr": ctr,
                    "avg_pct": avg_pct, "likes": likes, "is_short": is_short
                })

        if not video_data:
            # Fall back to execution_history for basic info
            brief_lines = ["=== PRODUCER BRIEF (RAG Feedback) ===\n"]
            brief_lines.append(f"Total pipeline runs: {len(history)}")
            topics = [e.get("topic_used", "?") for e in history[-5:]]
            brief_lines.append(f"Recent topics: {', '.join(topics)}")
            brief_lines.append("\n⚠️ No YouTube Analytics data available.")
            brief_lines.append("Enable YouTube Analytics API access for performance feedback.")
            brief_lines.append("=" * 45)
            return "\n".join(brief_lines)

        # Sort by views descending
        video_data.sort(key=lambda x: x["views"], reverse=True)

        brief_lines = ["=== PRODUCER BRIEF (RAG Feedback) ===\n"]
        brief_lines.append(f"Total videos tracked: {len(video_data)}")
        total_views = sum(v["views"] for v in video_data if v["views"] > 0)
        brief_lines.append(f"Total views: {total_views:,}\n")

        # Top performers
        top = [v for v in video_data if v["views"] > 0][:5]
        if top:
            brief_lines.append("🏆 TOP PERFORMING TOPICS (by views):")
            for i, v in enumerate(top, 1):
                ctr_str = f"{v['ctr']:.1%}" if v['ctr'] > 0 else "N/A"
                brief_lines.append(
                    f"  {i}. \"{v['topic'][:60]}\" — "
                    f"{v['views']} views | CTR: {ctr_str} | "
                    f"Avg watch: {v['avg_pct']:.0%} | 👍 {v['likes']}"
                )
            brief_lines.append("")

        # Bottom performers
        bottom = [v for v in video_data if v["views"] > 0][-3:]
        if bottom and len(bottom) < len(video_data):
            brief_lines.append("📉 LOWEST PERFORMING TOPICS:")
            for v in bottom:
                brief_lines.append(f"  - \"{v['topic'][:60]}\" — {v['views']} views")
            brief_lines.append("")

        # Main vs Shorts comparison
        mains = [v for v in video_data if not v["is_short"] and v["views"] > 0]
        shorts = [v for v in video_data if v["is_short"] and v["views"] > 0]
        if mains and shorts:
            avg_main = sum(v["views"] for v in mains) / len(mains)
            avg_short = sum(v["views"] for v in shorts) / len(shorts)
            brief_lines.append(f"📊 FORMAT INSIGHTS:")
            brief_lines.append(f"  Main videos avg: {avg_main:.0f} views")
            brief_lines.append(f"  Shorts avg: {avg_short:.0f} views")
            if avg_short > avg_main:
                brief_lines.append(f"  → Shorts perform {avg_short/avg_main:.1f}x better than long-form")
            brief_lines.append("")

        # Content angle recommendations based on topic keywords in top performers
        top_topics = " ".join(v["topic"].lower() for v in top[:5])
        strong_angles = []
        angle_keywords = {
            "visa": "Visa/immigration topics drive strong engagement",
            "h1b": "H-1B visa updates are high-interest",
            "green card": "Green card / residency topics perform well",
            "immigration": "Immigration policy angles resonate with the audience",
            "andhra": "Andhra Pradesh local news gets good reach",
            "telugu": "Telugu cultural connecting content works",
            "trump": "Political angles (whoever is driving policy) attract views",
            "policy": "Policy change angles get above-average CTR",
            "crisis": "Crisis/dramatic framing gets initial clicks (monitor retention)",
            "announcement": "Announcement/breaking framing works well",
        }
        for keyword, insight in angle_keywords.items():
            if keyword in top_topics:
                strong_angles.append(insight)

        if strong_angles:
            brief_lines.append("🎯 CONTENT ANGLE INSIGHTS:")
            for a in strong_angles:
                brief_lines.append(f"  → {a}")
            brief_lines.append("")

        brief_lines.append("💡 RECOMMENDATION FOR NEXT TOPIC SEEKER:")
        brief_lines.append("  When choosing between candidate topics, prefer:")
        if strong_angles:
            for a in strong_angles[:3]:
                brief_lines.append(f"    - {a.split(' → ') if ' → ' in a else a}")
        else:
            brief_lines.append("    - Topics about visa, immigration, or Andhra Pradesh policy")
        brief_lines.append("=" * 45)

        return "\n".join(brief_lines)

    # ─── Step 4: Get Feed-Ready Brief ─────────────────────────────────
    def get_injection_text(self, max_chars: int = 1500) -> str:
        """
        Text injected into the script generation prompt.
        Kept concise to avoid exceeding context limits.
        """
        brief = self.generate_producer_brief()
        if len(brief) > max_chars:
            # Trimit — keep only the actionable parts
            lines = brief.split("\n")
            trimmed = []
            section = None
            for line in lines:
                if "TOP PERFORMING" in line or "CONTENT ANGLE" in line or "RECOMMENDATION" in line:
                    section = "keep"
                elif line.startswith("==="):
                    section = "keep"
                elif section == "keep" or line.startswith("  "):
                    trimmed.append(line)
                if len("\n".join(trimmed)) > max_chars:
                    break
            brief = "\n".join(trimmed) + "\n..."
        return brief

    # ─── Full Pipeline: Run after upload ─────────────────────────────
    def run_feedback_cycle(self, youtube_service, video_ids: list, topic_title: str) -> str:
        """
        Full feedback cycle:
        1. Pull analytics for uploaded videos
        2. Store in ledger
        3. Generate producer brief for next run
        Returns the injection text to add to the next run's script prompt.
        """
        print("\n🧠 [RAG Feedback Loop] Starting post-pipeline analysis...")

        # Step 1: Pull metrics
        print("  [Step 1] Pulling YouTube Analytics...")
        metrics = self.pull_youtube_analytics(youtube_service, video_ids)
        for vid, m in metrics.items():
            views = m.get("views", "?")
            print(f"    Video {vid}: {views} views")

        # Step 2: Store
        print("  [Step 2] Storing metrics in growth ledger...")
        self.store_metrics(metrics, topic_title)

        # Step 3: Generate brief
        print("  [Step 3] Generating producer brief...")
        brief = self.generate_producer_brief()
        print(brief)

        # Step 4: Return injection text
        injection = self.get_injection_text()
        print(f"  [Step 4] Injection text ready ({len(injection)} chars)")

        # Save brief to ledger
        ledger = self._load_ledger()
        ledger.setdefault("producer_briefs", []).append({
            "timestamp": datetime.now(_IST).isoformat(),
            "topic": topic_title,
            "brief": brief
        })
        self._save_ledger(ledger)

        return injection
