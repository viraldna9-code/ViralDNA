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

    # ─── Retention Curve Storage ───────────────────────────────────────
    def store_retention_curve(self, video_id: str, retention_data: dict):
        """
        Store a retention curve snapshot in the growth ledger.
        Called after pull_retention_curve() succeeds.

        retention_data format (from yt_analytics.pull_retention_curve):
          {
            "video_id": str, "days": int,
            "curve": [{"ratio": float, "relative_retention": float, "audience_watch_ratio": float}, ...],
            "peak_drop_ratio": float, "avg_relative_retention": float,
            "has_data": bool, "error": str (if not has_data)
          }
        """
        ledger = self._load_ledger()
        ledger.setdefault("retention_curves", {})

        entry = {
            "timestamp": datetime.now(_IST).isoformat(),
            "days": retention_data.get("days", 30),
            "has_data": retention_data.get("has_data", False),
        }

        if retention_data.get("has_data"):
            entry["curve"] = retention_data.get("curve", [])
            entry["peak_drop_ratio"] = retention_data.get("peak_drop_ratio", 0.0)
            entry["avg_relative_retention"] = retention_data.get("avg_relative_retention", 0.0)
        else:
            entry["error"] = retention_data.get("error", "unknown")

        ledger["retention_curves"][video_id] = entry
        self._save_ledger(ledger)
        status = "stored" if entry["has_data"] else f"no data ({entry.get('error', '?')})"
        print(f"  📉 RAG: Retention curve for {video_id}: {status}")
        return entry

    def get_retention_summary(self, video_id: str) -> dict:
        """
        Retrieve the latest stored retention curve for a video.
        Returns dict with has_data flag and curve info, or has_data=False
        if no curve has been stored yet.
        """
        ledger = self._load_ledger()
        curves = ledger.get("retention_curves", {})

        if video_id not in curves:
            return {"video_id": video_id, "has_data": False, "error": "no retention data stored for this video"}

        entry = curves[video_id]
        if not entry.get("has_data"):
            return {"video_id": video_id, "has_data": False, "error": entry.get("error", "no data")}

        curve = entry.get("curve", [])

        # Extract key milestone points (closest to 30s, 60s, end — approximated from ratios)
        # Note: ratio is fraction of video duration, not absolute seconds.
        # We return the raw ratios so the caller can map to actual video length.
        milestones = {}
        target_ratios = [0.1, 0.25, 0.5, 0.75, 1.0]
        for target in target_ratios:
            closest = min(curve, key=lambda p: abs(p["ratio"] - target), default=None)
            if closest:
                milestones[f"ratio_{target:.2f}"] = {
                    "ratio": closest["ratio"],
                    "audience_watch_pct": round(closest["audience_watch_ratio"] * 100, 1),
                    "relative_retention": closest["relative_retention"],
                }

        return {
            "video_id": video_id,
            "has_data": True,
            "timestamp": entry.get("timestamp"),
            "days": entry.get("days"),
            "curve_sample_count": len(curve),
            "peak_drop_ratio": entry.get("peak_drop_ratio", 0.0),
            "avg_relative_retention": entry.get("avg_relative_retention", 0.0),
            "milestones": milestones,
        }

    def has_retention_data(self, video_id: str) -> bool:
        """Quick check: does this video have real retention data stored?"""
        ledger = self._load_ledger()
        curves = ledger.get("retention_curves", {})
        entry = curves.get(video_id, {})
        return entry.get("has_data", False)

    # ─── Q&A Guard: Prevents Fabricated Retention Answers ──────────────
    def qa_retention_check(self, video_id: str, question: str) -> dict:
        """
        Q&A guard for retention-related questions.
        Returns a dict with:
          - can_answer (bool): True only if real data exists
          - answer (str): The real answer if can_answer, or a refusal if not
          - source (str): Where the data came from

        CRITICAL: This function MUST be called before answering any retention
        question. If can_answer=False, the caller MUST refuse to give numeric
        retention percentages — it must return the refusal text instead.
        """
        summary = self.get_retention_summary(video_id)

        if not summary.get("has_data"):
            return {
                "can_answer": False,
                "answer": (
                    "I cannot answer that retention question — no real retention "
                    "data is available for this video.\n\n"
                    "This happens when:\n"
                    "  • The video is less than 24-48 hours old (YouTube hasn't processed it yet)\n"
                    "  • The YouTube Analytics API scope (yt-analytics.readonly) is not authorized\n"
                    "  • The video has too few views to generate a retention curve\n\n"
                    "Retention data will appear automatically once YouTube processes the video. "
                    "Check back in 24-48 hours."
                ),
                "source": "none",
            }

        # We have real data — generate answer from actual curve
        milestones = summary.get("milestones", {})
        avg_rel = summary.get("avg_relative_retention", 0.0)
        peak_drop = summary.get("peak_drop_ratio", 0.0)

        # Build a factual answer
        parts = [f"Based on YouTube Analytics API data (last {summary.get('days', 30)} days):"]

        if milestones:
            parts.append("\nKey retention points (relative to all videos of similar length on your channel):")
            for key, m in sorted(milestones.items()):
                parts.append(
                    f"  • At {m['ratio']:.0%} through the video: "
                    f"{m['audience_watch_pct']:.1%} of initial viewers still watching "
                    f"(relative retention: {m['relative_retention']:.2f}x)"
                )

        parts.append(f"\nOverall average relative retention: {avg_rel:.2f}x YouTube baseline")
        parts.append(f"Biggest drop-off point: at {peak_drop:.0%} of video duration")

        if avg_rel >= 1.1:
            parts.append("Verdict: ABOVE average — this format is working well for you.")
        elif avg_rel >= 0.9:
            parts.append("Verdict: AVERAGE — there's room for improvement in pacing/hooks.")
        else:
            parts.append("Verdict: BELOW average — consider improving the hook or shortening the intro.")

        return {
            "can_answer": True,
            "answer": "\n".join(parts),
            "source": "youtube_analytics_api",
        }

    # ─── Step 2 (alias): Store Run Performance ─────────────────────────
    def store_run_performance(self, topic_title: str, video_ids: list[str] = None,
                              analytics: dict = None):
        """
        Store a performance snapshot from a pipeline run.
        Called by vdna2_director.py post-pipeline phase.
        Delegates to store_metrics after building the metrics dict.
        """
        metrics_by_id = {}
        if video_ids:
            for vid in video_ids:
                if analytics and vid in analytics:
                    metrics_by_id[vid] = analytics[vid]
                else:
                    # No analytics data yet (upload skipped) — store placeholder
                    metrics_by_id[vid] = {
                        "views": None,
                        "likes": None,
                        "note": "Analytics pending — will be pulled on next run"
                    }
        return self.store_metrics(metrics_by_id, topic_title)

    # ─── Step 2 (original): Store Metrics in Ledger ────────────────────
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

    # ─── Step 5: Pull + Store Retention Curves ────────────────────────
    def pull_and_store_retention(self, youtube_service, video_ids: list, days: int = 30) -> dict:
        """
        Pull retention curves for multiple videos and store in ledger.
        Requires the YouTube Analytics service object (youtubeAnalytics v2).
        Returns {video_id: retention_data_dict}.
        """
        results = {}
        if not youtube_service or not video_ids:
            return results

        for vid in video_ids:
            if not vid or len(vid) < 8:
                continue
            try:
                resp = youtube_service.reports().query(
                    ids="channel==MINE",
                    startDate=(datetime.now(_IST) - timedelta(days=days)).strftime("%Y-%m-%d"),
                    endDate=datetime.now(_IST).strftime("%Y-%m-%d"),
                    metrics="relativeRetentionPerformance,audienceWatchRatio",
                    dimensions="elapsedVideoTimeRatio",
                    filters=f"video=={vid}",
                    sort="elapsedVideoTimeRatio",
                ).execute()

                rows = resp.get("rows", [])
                if not rows:
                    retention = {"video_id": vid, "has_data": False, "error": "no data"}
                else:
                    curve = []
                    for row in rows:
                        ratio = float(row[0]) if row[0] is not None else 0.0
                        rel_ret = float(row[1]) if row[1] is not None else 0.0
                        watch_ratio = float(row[2]) if row[2] is not None else 0.0
                        curve.append({
                            "ratio": round(ratio, 4),
                            "relative_retention": round(rel_ret, 4),
                            "audience_watch_ratio": round(watch_ratio, 4),
                        })

                    peak_drop_ratio = 0.0
                    max_drop = 0.0
                    for i in range(1, len(curve)):
                        drop = curve[i - 1]["audience_watch_ratio"] - curve[i]["audience_watch_ratio"]
                        if drop > max_drop:
                            max_drop = drop
                            peak_drop_ratio = curve[i]["ratio"]

                    avg_rel = sum(p["relative_retention"] for p in curve) / len(curve) if curve else 0.0
                    retention = {
                        "video_id": vid, "days": days, "curve": curve,
                        "peak_drop_ratio": round(peak_drop_ratio, 4),
                        "avg_relative_retention": round(avg_rel, 4),
                        "has_data": True,
                    }

                self.store_retention_curve(vid, retention)
                results[vid] = retention

            except Exception as e:
                err_data = {"video_id": vid, "has_data": False, "error": str(e)[:120]}
                self.store_retention_curve(vid, err_data)
                results[vid] = err_data

        return results

    # ─── Step 6: Generate Human-Readable Retention Report ──────────────
    def generate_retention_report(self, video_id: str, video_title: str = "",
                                  video_duration_seconds: int = 0) -> str:
        """
        Generate a human-readable retention report for a video.
        Uses REAL data from the growth ledger.
        Returns a text summary suitable for Q&A answers.
        If no data exists, returns a clear "no data" message (NOT fabricated numbers).
        """
        summary = self.get_retention_summary(video_id)

        if not summary.get("has_data"):
            return (
                f"No retention data available for \"{video_title or video_id}\".\n"
                f"This usually means the video is too new (needs 24-48h for YouTube to process)\n"
                f"or the YouTube Analytics API scope is not authorized.\n"
                f"Retention data will appear automatically once the video accumulates views."
            )

        milestones = summary.get("milestones", {})
        peak_drop = summary.get("peak_drop_ratio", 0.0)
        avg_rel = summary.get("avg_relative_retention", 0.0)

        lines = [f"📉 Audience Retention Report: \"{video_title or video_id}\""]

        if video_duration_seconds > 0:
            lines.append(f"Duration: {video_duration_seconds}s ({video_duration_seconds // 60}:{video_duration_seconds % 60:02d})")
            # Map ratio milestones to actual timestamps
            for key, m in sorted(milestones.items()):
                ratio = m["ratio"]
                seconds_at_point = int(ratio * video_duration_seconds)
                mins, secs = divmod(seconds_at_point, 60)
                lines.append(
                    f"  At {mins}:{secs:02d} ({ratio:.0%} through): "
                    f"~{m['audience_watch_pct']:.0%} of initial audience still watching | "
                    f"relative: {m['relative_retention']:.2f}x"
                )
            peak_sec = int(peak_drop * video_duration_seconds)
            pm, ps = divmod(peak_sec, 60)
            lines.append(f"\n  ⚠️ Biggest drop-off point: {pm}:{ps:02d} ({peak_drop:.0%} through)")
        else:
            # No duration info — show ratio-only
            for key, m in sorted(milestones.items()):
                lines.append(
                    f"  At {m['ratio']:.0%} through video: "
                    f"~{m['audience_watch_pct']:.0%} of initial audience | "
                    f"relative: {m['relative_retention']:.2f}x"
                )
            lines.append(f"\n  ⚠️ Biggest drop-off: {peak_drop:.0%} through video")

        # Interpret avg relative retention
        if avg_rel >= 1.1:
            lines.append(f"\n  ✅ Overall: ABOVE average retention ({avg_rel:.2f}x YouTube baseline)")
        elif avg_rel >= 0.9:
            lines.append(f"\n  📊 Overall: AVERAGE retention ({avg_rel:.2f}x YouTube baseline)")
        else:
            lines.append(f"\n  ⚠️ Overall: BELOW average retention ({avg_rel:.2f}x YouTube baseline) — consider improving hooks")

        lines.append(f"\n  Data source: YouTube Analytics API (last {summary.get('days', 30)} days)")
        lines.append(f"  Samples: {summary.get('curve_sample_count', 0)} data points")
        return "\n".join(lines)

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
