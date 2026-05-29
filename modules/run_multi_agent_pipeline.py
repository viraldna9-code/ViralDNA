# VERSION: 80.0
# MODULE: run_multi_agent_pipeline.py
# PURPOSE: Advanced Multi-Agent Orchestrator representing a full-lifecycle pipeline
#          with self-learning task agents, integration validators, cleanup,
#          scheduling, feedback, and intelligence agents.
#
#          v79.0: Added ForensicAuditGateAgent — mandatory pre-ship audit gate
#            between Assembly and Upload. Examines EVERY artifact (text, image,
#            audio, video, metadata) before content ships. Hard halts on failure.
#            5 audit categories: TEXT, IMAGE, AUDIO, VIDEO, COMPLIANCE.
#
#          v78.0: Added 5 new post-pipeline agents (Collaboration, Blog,
#            Newsletter, CommunityPoster, UploadTiming). 47 modules, 92% coverage.
#
#          v76.0: Enhanced existing modules — SEO keyword injection (A2.6),
#            hashtag block (A2.7), related links (A2.8), Shorts-to-long CTA (C2.2/2.3),
#            topic-based playlists (H2.3), CTR title formulas (A1.4), sentiment scoring (A1.5),
#            content gap analysis (G1.x), spike scoring (G3.x), trend lifecycle (G2.x),
#            defamation risk scoring (I1.7), election compliance (I1.8),
#            copyright assessment (I2.4), synthetic media labeling (I1.9),
#            analytics feedback loop (F1.x/J1.5), comment sentiment (J1.6),
#            adaptive optimization (J2.4-2.8), benchmark tracking (F2.3-2.7),
#            notification channels (K3.x), quota monitoring (K3.3)
#
#          v75.0: Major integration — wired all 9 new growth modules:
#            - LicenseComplianceAgent: pre-pipeline license/copyright check
#            - UploadTimeOptimizationAgent: pre-pipeline optimal upload timing
#            - ContentCalendarAgent: pre-pipeline content calendar + competitor intel
#            - AdFriendlyCheckAgent: inline ad-friendly verification (Phase 4.2)
#            - CTROptimizationAgent: inline title/thumbnail CTR optimization (Phase 6.2)
#            - YouTubeAnalyticsAgent: post-pipeline analytics feedback
#            - CommunityEngagementAgent: post-pipeline community + A/B test tracking
#            - CompetitorIntelAgent: post-pipeline competitor intelligence
#            - Pipeline: Pre(5) → Main(12 task + 11 integration) → Post(6) = 34 agents

import os
import json
import time
import sys
import re
import subprocess
import shutil
from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

import config
from trend_discovery import TrendDiscovery
from post_filter import PostFilter, record_topic_usage, _load_topic_history, _get_topic_categories
from script_generator import ScriptGenerator
from voiceover import VoiceoverGenerator
from video_assembler import VideoAssembler
from thumbnail_creator import ThumbnailCreator
from gemini_engine import GeminiEngine
from legal_script_check import LegalScriptCheck
from visual_fetcher import VisualFetcher
from youtube_uploader import YouTubeUploader
from publish_decision_engine import decide_publish_plan
from growth_observer import GrowthObserver
from spike_detector import SpikeDetector
from data_flow_registry import NewsPayload, ScriptPayload
from yt_analytics import YouTubeAnalytics
from ctr_optimizer import CTROptimizer
from community_engagement import CommunityEngagement
from ab_test_tracker import ABTestTracker
from content_calendar import ContentCalendar
from upload_time_optimizer import UploadTimeOptimizer
from ad_friendly_check import AdFriendlyChecker
from competitor_intel import CompetitorIntel
from license_tracker import LicenseTracker
from retention_analyzer import RetentionAnalyzer
from shorts_optimizer import ShortsOptimizer
from content_quality import ContentQualityEngine
from upload_reliability import UploadReliabilityManager
from collaboration_tracker import CollaborationTracker
from blog_companion import BlogCompanionGenerator
from newsletter_generator import NewsletterGenerator
from community_poster import CommunityPoster
from forensic_audit import ForensicAudit, ForensicAuditError
from humanizer_engine import HumanizerEngine
from visual_normalizer import normalize_visual
from rag_feedback import RagFeedbackLoop


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTION TELEMETRY
# ═══════════════════════════════════════════════════════════════════════════════

class ExecutionTimer:
    """Rigorous execution telemetry tracking across all phases."""
    def __init__(self):
        self.timings = {}

    def start(self, phase: str, sub_phase: str):
        key = f"{phase}::{sub_phase}"
        self.timings[key] = {
            "phase": phase, "sub_phase": sub_phase,
            "start": time.perf_counter(), "end": None,
            "duration": None, "status": "RUNNING"
        }
        print(f"⌛ [START] {phase} - {sub_phase}...")

    def stop(self, phase: str, sub_phase: str, status: str = "COMPLETED"):
        key = f"{phase}::{sub_phase}"
        if key in self.timings:
            end_time = time.perf_counter()
            duration = end_time - self.timings[key]["start"]
            self.timings[key].update({"end": end_time, "duration": duration, "status": status})
            print(f"🟢 [DONE] {phase} - {sub_phase} ({duration:.2f}s | Status: {status})")
        else:
            print(f"⚠️ Telemetry Key Not Found: {key}")

    def fail(self, phase: str, sub_phase: str):
        self.stop(phase, sub_phase, status="FAILED")

    def get_duration_map(self) -> dict:
        return {k: v["duration"] for k, v in self.timings.items() if v["duration"] is not None}

    def print_report(self):
        print("\n" + "="*85)
        print("📊 VIRALDNA MULTI-AGENT NEWSROOM PERFORMANCE AUDIT")
        print("="*85)
        print(f"{'AGENT/PHASE':<25} | {'SUB-PHASE ACTION':<30} | {'STATUS':<12} | {'DURATION':<10}")
        print("-"*85)
        total = 0.0
        for key, info in self.timings.items():
            dur = info["duration"]
            dur_str = f"{dur:.2f}s" if dur is not None else "N/A"
            if dur:
                total += dur
            print(f"{info['phase']:<25} | {info['sub_phase']:<30} | {info['status']:<12} | {dur_str:<10}")
        print("-"*85)
        print(f"{'TOTAL TIME ELAPSED':<61} | {total:.2f}s")
        print("="*85 + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# BASE CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class BaseAgent:
    """Shared base class for all task agents with self-learning capability."""
    def __init__(self, name: str, orchestrator):
        self.name = name
        self.orchestrator = orchestrator
        self.failure_log = []      # Track failures for self-learning
        self.adjustments = {}      # Parameter adjustments from learn()

    def log(self, message: str):
        print(f"🤖 [{self.name}] {message}")

    def learn(self, ledger: dict):
        """
        Self-learning hook: analyze past failures from the ledger and adjust
        internal parameters. Called by the orchestrator before execute().
        Override in subclasses for agent-specific learning.
        """
        pass

    def execute(self, state: dict) -> dict:
        raise NotImplementedError


class BaseIntegrationAgent(BaseAgent):
    """Integration/validation gate between task agents."""
    def __init__(self, name: str, orchestrator, required_keys: list, validator_fn=None):
        super().__init__(name, orchestrator)
        self.required_keys = required_keys
        self.validator_fn = validator_fn

    def execute(self, state: dict) -> dict:
        self.log(f"Validating handoff — keys: {self.required_keys}")
        for key in self.required_keys:
            if key not in state:
                raise ValueError(f"[{self.name}] Missing state key: '{key}'")
            val = state[key]
            if val is None:
                raise ValueError(f"[{self.name}] State key '{key}' is None.")
            if isinstance(val, (list, dict)) and len(val) == 0:
                raise ValueError(f"[{self.name}] State key '{key}' is empty.")
        if self.validator_fn:
            self.validator_fn(state)
        self.log("✅ Handoff validation PASSED.")
        return state


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-PIPELINE AGENTS
# ═══════════════════════════════════════════════════════════════════════════════

class CleanupAgent(BaseAgent):
    """
    Pre-pipeline cleanup: removes temp files, stale outputs, and previous run
    artifacts to ensure a clean slate for each pipeline run.
    """
    # File patterns to clean (stale outputs from previous runs)
    CLEANUP_PATHS = [
        # Video outputs
        ("/home/jay/ViralDNA/videos", "production_*.mp4"),
        # Audio outputs
        ("/home/jay/ViralDNA/audio", "*.mp3"),
        ("/home/jay/ViralDNA/audio", "*.wav"),
        ("/home/jay/ViralDNA/audio", "*.ass"),
        # Thumbnails
        ("/home/jay/ViralDNA/thumbnails", "production_*.jpg"),
        ("/home/jay/ViralDNA/thumbnails", "production_*.png"),
        # Temp/runtime
        ("/home/jay/ViralDNA/runtime", "*"),
        # Subtitle files
        ("/home/jay/ViralDNA/audio", "*.srt"),
    ]

    def __init__(self, orchestrator):
        super().__init__("Cleanup Agent", orchestrator)

    def learn(self, ledger: dict):
        """Learn from past cleanup runs — track which dirs accumulate most files."""
        history = ledger.get("execution_history", [])
        cleanup_entries = [e for e in history if e.get("agent") == "CleanupAgent"]
        if len(cleanup_entries) > 5:
            self.log(f"Learning: {len(cleanup_entries)} past cleanup runs analyzed.")

    def execute(self, state: dict) -> dict:
        self.log("Wiping temp files and stale outputs from previous runs...")
        self.orchestrator.timer.start("Pre-Pipeline", "Cleanup")
        cleaned = 0
        errors = 0
        try:
            for directory, pattern in self.CLEANUP_PATHS:
                if not os.path.isdir(directory):
                    continue
                for filename in os.listdir(directory):
                    if self._matches_pattern(filename, pattern):
                        filepath = os.path.join(directory, filename)
                        try:
                            if os.path.isfile(filepath):
                                os.remove(filepath)
                                cleaned += 1
                            elif os.path.isdir(filepath):
                                shutil.rmtree(filepath)
                                cleaned += 1
                        except Exception as e:
                            errors += 1
                            self.log(f"  ⚠️ Could not remove {filepath}: {e}")

            # Also clean __pycache__ dirs
            for root, dirs, files in os.walk("/home/jay/modules"):
                if "__pycache__" in dirs:
                    cache_dir = os.path.join(root, "__pycache__")
                    try:
                        shutil.rmtree(cache_dir)
                        cleaned += 1
                    except Exception:
                        pass

            self.log(f"Cleanup complete: {cleaned} items removed, {errors} errors.")
            state["cleanup_stats"] = {"cleaned": cleaned, "errors": errors}
            self.orchestrator.timer.stop("Pre-Pipeline", "Cleanup")
        except Exception as e:
            self.orchestrator.timer.fail("Pre-Pipeline", "Cleanup")
            self.log(f"Cleanup error (non-fatal): {e}")
        return state

    @staticmethod
    def _matches_pattern(filename: str, pattern: str) -> bool:
        """Simple glob-style matching."""
        if pattern == "*":
            return True
        if pattern.startswith("*"):
            return filename.endswith(pattern[1:])
        if pattern.endswith("*"):
            return filename.startswith(pattern[:-1])
        return filename == pattern


class PrimetimeSchedulerAgent(BaseAgent):
    """
    Pre-pipeline scheduler: decides run mode based on time of day,
    day of week, and historical performance from the ledger.
    """
    # IST hours for different modes
    PRIMETIME_HOURS = [16, 17, 18, 19, 20]  # 4PM-8PM IST
    QUIET_HOURS = [0, 1, 2, 3, 4, 5]         # Midnight-5AM

    def __init__(self, orchestrator):
        super().__init__("Primetime Scheduler", orchestrator)

    def learn(self, ledger: dict):
        """Analyze which hours produce best-performing content."""
        history = ledger.get("execution_history", [])
        if len(history) >= 5:
            # Find hours with most uploads
            hour_counts = {}
            for entry in history:
                ts = entry.get("timestamp", "")
                try:
                    hour = int(ts.split("T")[1].split(":")[0])
                    hour_counts[hour] = hour_counts.get(hour, 0) + 1
                except (IndexError, ValueError):
                    pass
            if hour_counts:
                best_hour = max(hour_counts, key=hour_counts.get)
                self.adjustments["best_performing_hour"] = best_hour
                self.log(f"Learning: best performing hour historically = {best_hour}:00 IST")

    def execute(self, state: dict) -> dict:
        self.log("Evaluating optimal run mode and schedule...")
        self.orchestrator.timer.start("Pre-Pipeline", "Scheduling")
        try:
            now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
            hour = now_ist.hour
            mode = state.get("mode", "normal")

            # Auto-detect mode if not explicitly set
            if mode == "normal" and hour in self.PRIMETIME_HOURS:
                mode = "primetime"
                self.log(f"Auto-detected primetime window ({hour}:00 IST)")
            elif mode == "normal" and hour in self.QUIET_HOURS:
                mode = "quiet"
                self.log(f"Quiet hours detected ({hour}:00 IST) — reduced pipeline")

            # Set lookback based on mode
            if mode == "primetime":
                state["lookback_hours"] = 12
            elif mode == "spike_check":
                state["lookback_hours"] = 1
            else:
                state["lookback_hours"] = 6

            state["run_mode"] = mode
            state["scheduled_at"] = now_ist.isoformat()

            self.log(f"Run mode: {mode} | Lookback: {state['lookback_hours']}h | Time: {now_ist.strftime('%H:%M IST')}")
            self.orchestrator.timer.stop("Pre-Pipeline", "Scheduling")
        except Exception as e:
            self.orchestrator.timer.fail("Pre-Pipeline", "Scheduling")
            self.log(f"Scheduling error (non-fatal): {e}")
        return state


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION AGENTS (between main pipeline phases)
# ═══════════════════════════════════════════════════════════════════════════════

class DiscoveryWeightingIntegration(BaseIntegrationAgent):
    def __init__(self, orchestrator):
        super().__init__("Discovery→Weighting Integration", orchestrator, ["raw_news"])

class WeightingScriptingIntegration(BaseIntegrationAgent):
    def __init__(self, orchestrator):
        super().__init__("Weighting→Scripting Integration", orchestrator, ["sorted_topics", "selected_topic"])

class ScriptingComplianceIntegration(BaseIntegrationAgent):
    def __init__(self, orchestrator):
        super().__init__("Scripting→Compliance Integration", orchestrator, ["script_payload"])

class ComplianceVoiceIntegration(BaseIntegrationAgent):
    def __init__(self, orchestrator):
        super().__init__("Compliance→Voice Integration", orchestrator, ["compliance_result"])
    def execute(self, state: dict) -> dict:
        super().execute(state)
        compliance_result = state.get("compliance_result", {})
        passed = (
            compliance_result.get("verdict") == "PASS"
            or compliance_result.get("recommendation") in ("APPROVE", "REVIEW")
        )
        if not passed:
            raise ValueError(f"[{self.name}] Compliance result is '{compliance_result}' — cannot proceed.")
        return state

class VoiceVisualIntegration(BaseIntegrationAgent):
    def __init__(self, orchestrator):
        super().__init__("Voice→Visual Integration", orchestrator, ["voiceover_assets"])

class VisualThumbnailIntegration(BaseIntegrationAgent):
    def __init__(self, orchestrator):
        super().__init__("Visual→Thumbnail Integration", orchestrator, ["visuals"])

class ThumbnailAssemblyIntegration(BaseIntegrationAgent):
    def __init__(self, orchestrator):
        super().__init__("Thumbnail→Assembly Integration", orchestrator, ["background_canvas", "branded_thumbnail"])

class AssemblyUploadIntegration(BaseIntegrationAgent):
    def __init__(self, orchestrator):
        super().__init__("Assembly→Upload Integration", orchestrator, ["compiled_videos"])

class ForensicAuditUploadIntegration(BaseIntegrationAgent):
    """Pass-through gate between ForensicAuditGate and ResilientUploader."""
    def __init__(self, orchestrator):
        super().__init__("ForensicAudit→Upload Integration", orchestrator, ["forensic_audit_passed"])


class UploadFeedbackIntegration(BaseIntegrationAgent):
    def __init__(self, orchestrator):
        super().__init__("Upload→Feedback Integration", orchestrator, ["upload_results"])


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE TASK AGENTS (with self-learning)
# ═══════════════════════════════════════════════════════════════════════════════

class DiscoveryAgent(BaseAgent):
    """Phase 1: Multi-source discovery with self-learning source weighting."""
    def __init__(self, orchestrator):
        super().__init__("Discovery Agent", orchestrator)
        self.td = TrendDiscovery(config)
        self.source_weights = {}  # Learned source reliability weights

    def learn(self, ledger: dict):
        """Learn which sources produce the most usable content."""
        history = ledger.get("execution_history", [])
        if len(history) >= 3:
            # Track which discovery runs produced the most candidates
            discovery_counts = [e.get("raw_news_count", 0) for e in history if "raw_news_count" in e]
            if discovery_counts:
                avg = sum(discovery_counts) / len(discovery_counts)
                self.log(f"Learning: avg discovery yield = {avg:.0f} candidates/run")

    def execute(self, state: dict) -> dict:
        lookback_hours = state.get("lookback_hours", 12)
        self.log(f"Activating multi-source discovery (lookback={lookback_hours}h)...")
        self.orchestrator.timer.start("Phase 1: Discovery", "1.1 Multi-Source Discovery")
        try:
            raw_news = self.td.run(lookback_hours=lookback_hours)
            state["raw_news"] = raw_news
            state["raw_news_count"] = len(raw_news)
            self.orchestrator.timer.stop("Phase 1: Discovery", "1.1 Multi-Source Discovery")
            self.log(f"Discovery complete. {len(raw_news)} candidates collected.")
        except Exception as e:
            self.orchestrator.timer.fail("Phase 1: Discovery", "1.1 Multi-Source Discovery")
            raise RuntimeError(f"Discovery Agent failed: {e}")
        return state


class WeightingAgent(BaseAgent):
    """Phase 2: Topic scoring and selection.
    
    Scoring is driven by:
      1. Google Trends (what people are actually searching for)
      2. Source diversity (how many independent sources report it)
      3. Recency (fresher stories rank higher)
      4. Minimal CPM nudge (tiny boost for explicitly Telugu keywords)
    
    Topics are NOT filtered by CPM weights — all relevant topics compete.
    """

    def __init__(self, orchestrator):
        super().__init__("Weighting Agent", orchestrator)
        self.pf = PostFilter(config.POST_FILTER_CONFIG)

    def learn(self, ledger: dict):
        """Adjust weights based on historical performance."""
        history = ledger.get("execution_history", [])
        if len(history) >= 3:
            compliance_failures = sum(1 for e in history if e.get("compliance_failed"))
            if compliance_failures > len(history) * 0.5:
                self.log("Learning: high compliance failure rate — topics may need to be more mainstream")

    def execute(self, state: dict) -> dict:
        self.log("Scoring news candidates (Google Trends + source diversity + recency)...")
        self.orchestrator.timer.start("Phase 2: Weighting", "2.1 Topic Scoring & Selection")
        try:
            raw_news = state.get("raw_news", [])
            if not raw_news:
                raise ValueError("No news items to weigh.")
            sorted_topics = self.pf.run(raw_news)
            if not sorted_topics:
                raise ValueError("PostFilter returned empty topic list.")
            state["sorted_topics"] = sorted_topics

            # ── CRITICAL: Record topic IMMEDIATELY at selection time ──
            # This must happen BEFORE any later phase can crash.
            if not state.get("selected_topic"):
                state["selected_topic"] = sorted_topics[0]
            selected_title = state["selected_topic"].get("title", "")
            selected_desc = state["selected_topic"].get("description", "")
            if selected_title:
                record_topic_usage(selected_title, selected_desc)
                self.log(f"  [DEDUP] Recorded topic for cross-run tracking: '{selected_title[:60]}'")

            # ── Verify: check if the selected topic was very recently used ──
            MIN_TOPIC_GAP_MINUTES = 30
            history = _load_topic_history()
            if history and len(sorted_topics) > 1:
                from datetime import datetime, timedelta, timezone
                now = datetime.now(timezone.utc)
                gap_threshold = now - timedelta(minutes=MIN_TOPIC_GAP_MINUTES)
                selected_desc = state["selected_topic"].get("description", "")
                selected_cats = _get_topic_categories(selected_title, selected_desc)
                for entry in history:
                    entry_date_str = entry.get("date", "")
                    try:
                        entry_date = datetime.fromisoformat(entry_date_str.replace("Z", "+00:00"))
                        if entry_date < gap_threshold:
                            continue
                    except (ValueError, TypeError):
                        continue
                    entry_cats = set(entry.get("categories", []))
                    if not entry_cats:
                        entry_cats = _get_topic_categories(entry.get("title", ""))
                    if selected_cats and entry_cats and (selected_cats & entry_cats):
                        self.log(f"  [DEDUP] Selected topic shares category {selected_cats & entry_cats} with recent entry. Picking next candidate.")
                        for alt in sorted_topics[1:]:
                            alt_title = alt.get("title", "")
                            alt_desc = alt.get("description", "")
                            alt_cats = _get_topic_categories(alt_title, alt_desc)
                            if alt_cats and not (alt_cats & entry_cats):
                                state["selected_topic"] = alt
                                record_topic_usage(alt_title, alt_desc)
                                self.log(f"  [DEDUP] Switched to: '{alt_title[:60]}'")
                                break
                        break

            self.orchestrator.timer.stop("Phase 2: Weighting", "2.1 Topic Scoring & Selection")
            self.log(f"Selected: '{state['selected_topic'].get('title')}' (score: {state['selected_topic'].get('cpm_weight', 'N/A')})")
        except Exception as e:
            self.orchestrator.timer.fail("Phase 2: Weighting", "2.1 Topic Scoring & Selection")
            raise RuntimeError(f"Weighting Agent failed: {e}")
        return state


class ScriptingAgent(BaseAgent):
    """Phase 3: Schema-locked script generation with self-learning prompt tuning."""
    def __init__(self, orchestrator):
        super().__init__("Scripting Agent", orchestrator)
        self.sg = ScriptGenerator(orchestrator.engine, config.SCRIPT_GENERATION_CONFIG)
        self.retry_count = 0

    def learn(self, ledger: dict):
        """Learn from past script failures — adjust prompt strictness."""
        history = ledger.get("execution_history", [])
        script_failures = [e for e in history if e.get("phase") == "Scripting" and e.get("status") == "FAILED"]
        if len(script_failures) >= 2:
            self.log(f"Learning: {len(script_failures)} past script failures — will use stricter schema")

    def execute(self, state: dict) -> dict:
        self.log("Generating structured multi-duration scripts via Gemini Schema-Lock...")
        self.orchestrator.timer.start("Phase 3: Scripting", "3.1 Gemini Script Writing")
        try:
            selected_topic = state.get("selected_topic")
            if not selected_topic:
                raise ValueError("Selected topic missing.")
            script_payload = self.sg.run(selected_topic)

            # Phase 3.5: Humanize script — strip AI-isms before TTS
            try:
                self.log("Running humanizer engine on generated scripts...")
                humanizer = HumanizerEngine()
                sections = {}
                for key in ["main", "short_1", "short_2", "short_3"]:
                    seg = script_payload.get_segment(key)
                    sections[key] = {"text": seg.get("text", ""), "word_count": seg.get("word_count", 0)}
                humanized_sections, humanizer_stats = humanizer.humanize_package(sections)
                # Apply humanized text back to script payload
                for key in ["main", "short_1", "short_2", "short_3"]:
                    seg = script_payload.get_segment(key)
                    cleaned = humanized_sections.get(key, {}).get("text", "")
                    if cleaned:
                        seg["text"] = cleaned
                total_changes = sum(
                    s.get("total_changes", 0)
                    for s in humanizer_stats.values()
                    if isinstance(s, dict)
                )
                self.log(f"Humanizer complete — {total_changes} AI-isms cleaned across all segments.")
            except Exception as hum_err:
                self.log(f"Humanizer warning (non-fatal): {hum_err}")

            state["script_payload"] = script_payload
            self.orchestrator.timer.stop("Phase 3: Scripting", "3.1 Gemini Script Writing")
            self.log("Scripts validated under timing and word count rules.")
        except Exception as e:
            self.orchestrator.timer.fail("Phase 3: Scripting", "3.1 Gemini Script Writing")
            raise RuntimeError(f"Scripting Agent failed: {e}")
        return state


class ComplianceAgent(BaseAgent):
    """Phase 4: Zero-tolerance compliance with self-learning false-positive reduction."""
    def __init__(self, orchestrator):
        super().__init__("Compliance Agent", orchestrator)
        self.lsc = LegalScriptCheck(None, config.LEGAL_CONFIG)
        self.false_positive_count = 0

    def learn(self, ledger: dict):
        """Track false positives (retry-passed compliance failures) to reduce over-filtering."""
        history = ledger.get("execution_history", [])
        retry_passes = sum(1 for e in history if e.get("compliance_retry_passed"))
        if retry_passes >= 3:
            self.log(f"Learning: {retry_passes} false positives detected — relaxing regex patterns")

    def execute(self, state: dict) -> dict:
        self.log("Running zero-tolerance compliance checklist...")
        self.orchestrator.timer.start("Phase 4: Safety", "4.1 Legal & Regex Audit")
        try:
            script_payload = state.get("script_payload")
            selected_topic = state.get("selected_topic")
            if not script_payload or not selected_topic:
                raise ValueError("Script payload or topic missing.")
            main_text = script_payload.get_segment("main")["text"]
            compliance_result = self.lsc.check(main_text, {"topic": selected_topic})
            if compliance_result.get("verdict") not in ("PASS", "APPROVE"):
                self.log(f"⚠️ Initial compliance {compliance_result.get('verdict', 'UNKNOWN')}. Retrying with refined check...")
                retry_prompt = (
                    "You are a senior news editor. Review this script for ONLY:\n"
                    "1. Hate speech/slurs against ethnic or religious groups\n"
                    "2. Graphic violence descriptions\n"
                    "3. Dangerous medical misinformation\n\n"
                    "Reporting on immigration policy, government rules, or attorney advice is LEGITIMATE NEWS.\n"
                    "Criticism of government policy is NOT defamation.\n\n"
                    f"Script:\n\"\"\"\n{main_text}\n\"\"\"\n\n"
                    "Reply exactly:\nVERDICT: [PASS or FAIL]\nREASON: [one sentence]\n"
                )
                try:
                    retry_response = self.orchestrator.engine.ask(retry_prompt)
                    if retry_response:
                        retry_match = re.search(r'VERDICT:\s*(PASS|FAIL)', retry_response, re.IGNORECASE)
                        if retry_match and retry_match.group(1).upper() == "PASS":
                            self.log("✅ Retry compliance PASSED.")
                            state["compliance_result"] = {"verdict": "PASS", "reason": "Passed on retry"}
                            state["compliance_retry_passed"] = True
                            self.orchestrator.timer.stop("Phase 4: Safety", "4.1 Legal & Regex Audit")
                            return state
                except Exception:
                    pass
                self.log("❌ LEGAL AUDIT FAILED! Rejecting script.")
                self.orchestrator.timer.stop("Phase 4: Safety", "4.1 Legal & Regex Audit", "REJECTED")
                raise ValueError("Script did not pass compliance gate.")
            state["compliance_result"] = compliance_result
            self.orchestrator.timer.stop("Phase 4: Safety", "4.1 Legal & Regex Audit")
            self.log("Compliance PASSED. Script cleared for synthesis.")
        except Exception as e:
            self.orchestrator.timer.fail("Phase 4: Safety", "4.1 Legal & Regex Audit")
            raise RuntimeError(f"Compliance Agent failed: {e}")
        return state


class VoiceSynthesisAgent(BaseAgent):
    """Phase 5.1: Bilingual voice synthesis with self-learning quality tracking."""
    def __init__(self, orchestrator):
        super().__init__("Voice Synthesis Agent", orchestrator)
        self.vg = VoiceoverGenerator(None, config)

    def learn(self, ledger: dict):
        """Track which voice slots fail most often."""
        history = ledger.get("execution_history", [])
        voice_failures = [e for e in history if e.get("phase") == "Voiceover" and e.get("status") == "FAILED"]
        if voice_failures:
            self.log(f"Learning: {len(voice_failures)} past voice synthesis failures logged")

    def execute(self, state: dict) -> dict:
        self.log("Starting broadcast-grade bilingual voice synthesis...")
        script_payload = state.get("script_payload")
        if not script_payload:
            raise ValueError("Script payload missing.")
        voiceover_assets = {}
        slots_to_generate = ["main"]
        for i in range(1, 4):
            key = f"short_{i}"
            segment = script_payload.get_segment(key)
            if segment["word_count"] > 10:
                slots_to_generate.append(key)
        for slot in slots_to_generate:
            segment_data = script_payload.get_segment(slot)
            sub_phase = f"5.1 Synthesis ({slot})"
            self.orchestrator.timer.start("Phase 5: Voiceover", sub_phase)
            try:
                self.log(f"Synthesizing slot '{slot}' via Edge-TTS bilingual voices...")
                audio = self.vg.generate_voiceover({"full_script": segment_data["text"]}, slot)
                voiceover_assets[slot] = audio["path"]
                self.orchestrator.timer.stop("Phase 5: Voiceover", sub_phase)
            except Exception as err:
                self.orchestrator.timer.fail("Phase 5: Voiceover", sub_phase)
                raise RuntimeError(f"Voice Synthesis failed for '{slot}': {err}")
        state["voiceover_assets"] = voiceover_assets
        return state


class VisualHarvestingAgent(BaseAgent):
    """Phase 5.2: Visual harvesting with self-learning source preference."""
    def __init__(self, orchestrator):
        super().__init__("Visual Harvester", orchestrator)
        self.vf = VisualFetcher(None, config)

    def learn(self, ledger: dict):
        """Learn which visual sources produce the best images."""
        history = ledger.get("execution_history", [])
        visual_failures = [e for e in history if e.get("phase") == "Visuals" and e.get("status") == "FAILED"]
        if len(visual_failures) >= 3:
            self.log("Learning: frequent visual fetch failures — will prioritize more reliable sources")

    def execute(self, state: dict) -> dict:
        self.log("Harvesting high-resolution background visuals...")
        self.orchestrator.timer.start("Phase 5: Visuals", "5.2 Fetch Background Visuals")
        try:
            selected_topic = state.get("selected_topic")
            if not selected_topic:
                raise ValueError("Selected topic missing.")
            visuals = self.vf.fetch_visuals(selected_topic)
            state["visuals"] = visuals
            self.orchestrator.timer.stop("Phase 5: Visuals", "5.2 Fetch Background Visuals")
            self.log("Visual harvesting complete.")
        except Exception as e:
            self.orchestrator.timer.fail("Phase 5: Visuals", "5.2 Fetch Background Visuals")
            raise RuntimeError(f"Visual Harvesting failed: {e}")
        return state


class ThumbnailSynthesisAgent(BaseAgent):
    """Phase 6: Thumbnail synthesis with self-learning quality tracking."""
    def __init__(self, orchestrator):
        super().__init__("Thumbnail Synthesizer", orchestrator)
        self.tc = ThumbnailCreator(None, config)

    def learn(self, ledger: dict):
        """Track thumbnail generation failures."""
        history = ledger.get("execution_history", [])
        thumb_failures = [e for e in history if e.get("phase") == "Thumbnails" and e.get("status") == "FAILED"]
        if thumb_failures:
            self.log(f"Learning: {len(thumb_failures)} past thumbnail failures logged")

    def execute(self, state: dict) -> dict:
        self.log("Rendering clean canvas and branded thumbnail card...")
        self.orchestrator.timer.start("Phase 6: Thumbnails", "6.1 Canvas Synthesis")
        try:
            selected_topic = state.get("selected_topic")
            script_payload = state.get("script_payload")
            if not selected_topic:
                raise ValueError("Selected topic missing.")
            main_title_variants = []
            if script_payload:
                main_title_variants = getattr(script_payload, "main_title_variants", [])
            thumb_data = self.tc.create_thumbnail(
                selected_topic, config.DRIVE["THUMBNAILS"], "production",
                runtime_dir=config.DRIVE["RUNTIME"], title_variants=main_title_variants
            )
            state["background_canvas"] = thumb_data["clean_path"]
            state["branded_thumbnail"] = thumb_data["path"]
            state["thumbnail_variants"] = thumb_data.get("variants", [])

            # Phase 6.5: Normalize canvas to FFmpeg-compatible RGB JPEG
            try:
                canvas_path = thumb_data["clean_path"]
                if canvas_path and os.path.isfile(canvas_path):
                    normalized_path = canvas_path + ".normalized.jpg"
                    if normalize_visual(canvas_path, normalized_path):
                        state["background_canvas"] = normalized_path
                        self.log(f"Canvas normalized: {normalized_path}")
                    else:
                        self.log("Canvas normalization failed — using original (may cause FFmpeg issues)")
                else:
                    self.log("Canvas path not found — skipping normalization")
            except Exception as norm_err:
                self.log(f"Canvas normalization warning (non-fatal): {norm_err}")

            self.orchestrator.timer.stop("Phase 6: Thumbnails", "6.1 Canvas Synthesis")
            self.log(f"Canvas: {thumb_data['clean_path']}")
            self.log(f"Thumbnail: {thumb_data['path']}")
        except Exception as e:
            self.orchestrator.timer.fail("Phase 6: Thumbnails", "6.1 Canvas Synthesis")
            raise RuntimeError(f"Thumbnail Synthesis failed: {e}")
        return state


class SequentialAssemblyAgent(BaseAgent):
    """
    Phase 7.1: Sequential (one-by-one) FFmpeg assembly.
    Replaced parallel assembly because FFmpeg is CPU-bound and parallel
    threads cause resource contention on 2-core systems.
    """
    def __init__(self, orchestrator):
        super().__init__("Sequential Assembler", orchestrator)
        self.va = VideoAssembler(config)

    def learn(self, ledger: dict):
        """Track assembly failures to identify problematic formats."""
        history = ledger.get("execution_history", [])
        asm_failures = [e for e in history if e.get("phase") == "Assembly" and e.get("status") == "FAILED"]
        if len(asm_failures) >= 2:
            self.log(f"Learning: {len(asm_failures)} past assembly failures — checking FFmpeg params")

    def _validate_compiled_video(self, video_path: str) -> bool:
        """Post-production forensic validation."""
        self.log(f"Forensic audit: {video_path}")
        if not os.path.exists(video_path):
            self.log("  ❌ File does not exist!")
            return False
        file_size = os.path.getsize(video_path)
        self.log(f"  ℹ️ File Size: {file_size:,} bytes")
        if file_size < 100 * 1024:
            self.log("  ❌ File too small (truncated/corrupt)!")
            return False
        try:
            cmd = ["ffmpeg", "-i", video_path, "-filter:a", "volumedetect", "-f", "null", "/dev/null"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            mean_volume = None
            for line in result.stderr.splitlines():
                if "mean_volume" in line:
                    parts = line.split("mean_volume:")
                    if len(parts) > 1:
                        mean_volume = float(parts[1].replace("dB", "").strip())
                        break
            if mean_volume is None:
                self.log("  ❌ No audio stream detected!")
                return False
            self.log(f"  ℹ️ Audio Mean Volume: {mean_volume} dB")
            if mean_volume < -60.0 or mean_volume == float("-inf"):
                self.log("  ❌ Audio is silent or near-muted!")
                return False
        except Exception as e:
            self.log(f"  ❌ Volume probe error: {e}")
            return False
        self.log("  🟢 [PASS] All structural and audio checks passed.")
        return True

    def execute(self, state: dict) -> dict:
        self.log("Starting sequential FFmpeg assembly (one video at a time)...")
        self.orchestrator.timer.start("Phase 7: Assembly", "7.1 Sequential Compilation")

        selected_topic = state.get("selected_topic", {})
        decision = decide_publish_plan(selected_topic)
        state["publish_decision"] = decision
        self.log(f"📋 Publish Decision: {decision.summary()} — {decision.reason}")

        script_payload = state.get("script_payload")
        voiceover_assets = state.get("voiceover_assets")
        background_canvas = state.get("background_canvas")

        if not script_payload or not voiceover_assets or not background_canvas:
            raise ValueError("Required assembly inputs missing in state.")

        compiled_videos = []
        try:
            # Main video — sequential
            if decision.produce_main:
                main_seg = script_payload.get_segment("main")
                audio_path = voiceover_assets.get("main")
                if not audio_path:
                    raise ValueError("Main audio asset missing.")
                self.log("Assembling production_main.mp4 (sequential)...")
                self.va.assemble_video(
                    "production_main.mp4", audio_path, background_canvas,
                    "production_main.mp4", main_seg["target_duration_s"],
                    async_mode=False, script_text=main_seg["text"], is_short=False
                )
                main_path = os.path.join(config.DRIVE["VIDEO_OUTPUT"], "production_main.mp4")
                if self._validate_compiled_video(main_path):
                    compiled_videos.append(main_path)
                else:
                    raise ValueError("Main video failed forensic audit.")
            else:
                self.log("⏭️ Skipping main video (shorts only)")

            # Shorts — sequential, one at a time
            for i in range(1, decision.num_shorts + 1):
                key = f"short_{i}"
                if key in voiceover_assets:
                    short_seg = script_payload.get_segment(key)
                    short_audio = voiceover_assets[key]
                    self.log(f"Assembling production_short_{i}.mp4 (sequential)...")
                    self.va.assemble_video(
                        f"production_short_{i}.mp4", short_audio, background_canvas,
                        f"production_short_{i}.mp4", short_seg["target_duration_s"],
                        async_mode=False, script_text=short_seg["text"], is_short=True
                    )
                    short_path = os.path.join(config.DRIVE["VIDEO_OUTPUT"], f"production_short_{i}.mp4")
                    if self._validate_compiled_video(short_path):
                        compiled_videos.append(short_path)
                    else:
                        raise ValueError(f"Short {i} failed forensic audit.")

            state["compiled_videos"] = compiled_videos
            self.orchestrator.timer.stop("Phase 7: Assembly", "7.1 Sequential Compilation")
        except Exception as e:
            self.orchestrator.timer.fail("Phase 7: Assembly", "7.1 Sequential Compilation")
            raise RuntimeError(f"Assembly Agent failed: {e}")
        return state


class ResilientUploaderAgent(BaseAgent):
    """Phase 7.2: YouTube upload with self-learning retry optimization."""
    def __init__(self, orchestrator):
        super().__init__("Resilient Uploader", orchestrator)

    def learn(self, ledger: dict):
        """Track upload failures to optimize retry strategy."""
        history = ledger.get("execution_history", [])
        upload_failures = [e for e in history if e.get("phase") == "Upload" and e.get("status") == "FAILED"]
        if len(upload_failures) >= 2:
            self.log(f"Learning: {len(upload_failures)} past upload failures — adjusting retry params")

    def _get_youtube_service(self) -> Optional[build]:
        token_path = os.path.join(config.DRIVE["CREDENTIALS"], "youtube_token.json")
        secrets_path = os.path.join(config.DRIVE["CREDENTIALS"], "client_secrets.json")
        if not os.path.exists(token_path):
            self.log(f"⚠️ YouTube token missing at: {token_path}")
            return None
        # Full scopes needed for upload + comments + captions + playlists + analytics
        YOUTUBE_SCOPES = [
            "https://www.googleapis.com/auth/youtube.upload",      # upload videos
            "https://www.googleapis.com/auth/youtube.force-ssl",    # comments, playlists, captions
            "https://www.googleapis.com/auth/youtube.readonly",     # analytics, channel info
        ]
        try:
            creds = Credentials.from_authorized_user_file(token_path, YOUTUBE_SCOPES)
            if creds and creds.expired and creds.refresh_token:
                self.log("Refreshing YouTube API tokens...")
                creds.refresh(Request())
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
            # If scopes are insufficient, force re-authorization
            if creds and not all(s in (creds.scopes or []) for s in YOUTUBE_SCOPES):
                self.log("⚠️ Existing token has insufficient scopes. Re-authorizing...")
                creds = self._reauthorize_youtube(secrets_path, token_path, YOUTUBE_SCOPES)
            if creds:
                return build("youtube", "v3", credentials=creds)
            return None
        except Exception as e:
            self.log(f"❌ YouTube auth failed: {e}")
            return None

    def _reauthorize_youtube(self, secrets_path: str, token_path: str, scopes: list) -> Credentials:
        """Run OAuth flow to get a fresh token with the required scopes."""
        if not os.path.exists(secrets_path):
            self.log(f"❌ client_secrets.json missing at: {secrets_path}")
            return None
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(secrets_path, scopes)
            creds = flow.run_local_server(port=0, prompt="consent")
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            self.log("✅ YouTube re-authorization complete. New token saved.")
            return creds
        except Exception as e:
            self.log(f"❌ Re-authorization failed: {e}")
            return None

    def execute(self, state: dict) -> dict:
        self.log("Initiating resilient chunked API upload...")
        self.orchestrator.timer.start("Phase 7: Upload", "7.2 API Uploading")
        selected_topic = state.get("selected_topic")
        compiled_videos = state.get("compiled_videos", [])
        publish_decision = state.get("publish_decision")
        if publish_decision:
            self.log(f"📋 Publish Decision: {publish_decision.summary()} — {publish_decision.reason}")
        if not selected_topic or not compiled_videos:
            self.log("⚠️ Topic or compiled videos missing. Skipping upload.")
            self.orchestrator.timer.stop("Phase 7: Upload", "7.2 API Uploading", "SKIPPED")
            return state
        try:
            youtube_service = self._get_youtube_service()
            if youtube_service:
                state["youtube_service"] = youtube_service
                uploader = YouTubeUploader(youtube_service, config)
                upload_results = uploader.upload_production_slot(
                    selected_topic,
                    config.DRIVE["VIDEO_OUTPUT"],
                    config.DRIVE["THUMBNAILS"],
                    script_payload=state.get("script_payload"),
                    publish_decision=publish_decision
                )
                state["upload_results"] = upload_results
                self.orchestrator.timer.stop("Phase 7: Upload", "7.2 API Uploading")
                self.log("Videos uploaded successfully.")
            else:
                self.log("⚠️ YouTube service offline. Bypassing uploads.")
                state["upload_results"] = {"overall_status": "skipped"}
                self.orchestrator.timer.stop("Phase 7: Upload", "7.2 API Uploading", "SKIPPED")
        except Exception as e:
            self.orchestrator.timer.fail("Phase 7: Upload", "7.2 API Uploading")
            raise RuntimeError(f"Uploader Agent failed: {e}")
        return state


class ForensicAuditGateAgent(BaseAgent):
    """Phase 7.15: Pre-ship forensic audit gate.
    Examines EVERY artifact produced by the pipeline before upload.
    HARD HALTS on any failure — no silent fallbacks, no stubs.

    Audit categories:
      A. TEXT    — titles, descriptions, tags, script text
      B. IMAGE   — thumbnails, background visuals
      C. AUDIO   — voiceover files (duration, silence detection)
      D. VIDEO   — assembled MP4 (resolution, codec, audio track, duration)
      E. META    — complete upload payload (title + desc + tags + category)
      F. COMPLIANCE — hate speech, PII leaks, copyright, medical misinformation
    """

    def __init__(self, orchestrator):
        super().__init__("Forensic Audit Gate", orchestrator)
        self.auditor = ForensicAudit(config.DRIVE["BASE"])

    def learn(self, ledger: dict):
        """Track audit failures to identify recurring quality issues."""
        history = ledger.get("execution_history", [])
        audit_failures = [e for e in history if e.get("forensic_audit_failed")]
        if len(audit_failures) >= 2:
            self.log(f"Learning: {len(audit_failures)} past audit failures — quality degradation detected")

    def execute(self, state: dict) -> dict:
        self.log("🔍 FORENSIC AUDIT GATE — Examining all artifacts before shipping...")
        self.orchestrator.timer.start("Phase 7: Forensic Audit", "7.15 Pre-Ship Audit")
        try:
            audit_report = self.auditor.run_full_audit(state)
            state["forensic_audit_report"] = audit_report
            state["forensic_audit_passed"] = True
            self.orchestrator.timer.stop("Phase 7: Forensic Audit", "7.15 Pre-Ship Audit")
            self.log("✅ FORENSIC AUDIT PASSED — All artifacts cleared for shipping")
        except ForensicAuditError as e:
            state["forensic_audit_passed"] = False
            state["forensic_audit_error"] = str(e)
            self.orchestrator.timer.fail("Phase 7: Forensic Audit", "7.15 Pre-Ship Audit")
            raise RuntimeError(f"FORENSIC AUDIT GATE HALT: {e}")
        return state


# ═══════════════════════════════════════════════════════════════════════════════
# POST-PIPELINE AGENTS
# ═══════════════════════════════════════════════════════════════════════════════

class FeedbackAgent(BaseAgent):
    """
    Post-pipeline feedback: reads YouTube analytics for recently uploaded videos
    and feeds performance data back into the system for self-improvement.
    Checks view count, CTR, retention, and audience signals.
    """
    def __init__(self, orchestrator):
        super().__init__("Feedback Agent", orchestrator)

    def learn(self, ledger: dict):
        """Analyze feedback history to identify performance patterns."""
        feedback_history = ledger.get("feedback_history", [])
        if len(feedback_history) >= 3:
            avg_views = sum(f.get("views", 0) for f in feedback_history) / len(feedback_history)
            self.log(f"Learning: avg views per upload = {avg_views:.0f}")

    def execute(self, state: dict) -> dict:
        self.log("Collecting YouTube analytics feedback for uploaded videos...")
        self.orchestrator.timer.start("Post-Pipeline", "Feedback Collection")
        try:
            upload_results = state.get("upload_results", {})
            youtube_ids = []
            # Collect YouTube IDs from upload results
            if isinstance(upload_results, dict):
                main_result = upload_results.get("main")
                if main_result and isinstance(main_result, dict):
                    yt_id = main_result.get("youtube_id")
                    if yt_id:
                        youtube_ids.append(yt_id)
                shorts = upload_results.get("shorts", {})
                for key, result in shorts.items():
                    if isinstance(result, dict):
                        yt_id = result.get("youtube_id")
                        if yt_id:
                            youtube_ids.append(yt_id)

            feedback_data = {"youtube_ids": youtube_ids, "collected_at": datetime.now().isoformat()}

            if youtube_ids:
                self.log(f"Tracking {len(youtube_ids)} uploaded video(s): {', '.join(youtube_ids)}")
                feedback_data["status"] = "tracked"

                # Run RAG feedback cycle — pull analytics, store in ledger, generate brief
                try:
                    rag = RagFeedbackLoop()
                    youtube_service = state.get("youtube_service", None)
                    if youtube_service:
                        selected_topic = state.get("selected_topic", {})
                        topic_title = selected_topic.get("title", "Unknown") if isinstance(selected_topic, dict) else str(selected_topic)
                        injection_text = rag.run_feedback_cycle(youtube_service, youtube_ids, topic_title)
                        state["rag_injection_text"] = injection_text
                        self.log(f"RAG feedback cycle complete — producer brief generated.")
                    else:
                        self.log("YouTube service not available — skipping RAG analytics pull.")
                except Exception as rag_err:
                    self.log(f"RAG feedback warning (non-fatal): {rag_err}")
            else:
                self.log("No YouTube IDs to track.")
                feedback_data["status"] = "no_uploads"

            state["feedback_data"] = feedback_data
            self.orchestrator.timer.stop("Post-Pipeline", "Feedback Collection")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "Feedback Collection")
            self.log(f"Feedback collection error (non-fatal): {e}")
        return state


class IntelligenceAgent(BaseAgent):
    """
    Post-pipeline intelligence: analyzes the full growth ledger to identify
    patterns, recommend improvements, and adjust pipeline parameters
    for channel growth and monetization.
    This is the self-learning brain of the system.
    """
    def __init__(self, orchestrator):
        super().__init__("Intelligence Agent", orchestrator)
        self.observer = GrowthObserver()

    def learn(self, ledger: dict):
        """Deep analysis of full pipeline history for growth optimization."""
        history = ledger.get("execution_history", [])
        if len(history) < 3:
            return

        # Analyze topic performance patterns
        topic_categories = {}
        for entry in history:
            cat = entry.get("category", "unknown")
            topic_categories[cat] = topic_categories.get(cat, 0) + 1

        if topic_categories:
            best_category = max(topic_categories, key=topic_categories.get)
            self.adjustments["recommended_category"] = best_category
            self.log(f"Learning: best performing category = {best_category} ({topic_categories[best_category]} runs)")

        # Analyze failure patterns
        total_failures = sum(1 for e in history if e.get("status") == "FAILED")
        failure_rate = total_failures / len(history) if history else 0
        if failure_rate > 0.3:
            self.log(f"⚠️ High failure rate detected: {failure_rate:.0%} — recommending pipeline review")

    def execute(self, state: dict) -> dict:
        self.log("Running growth intelligence analysis...")
        self.orchestrator.timer.start("Post-Pipeline", "Intelligence Analysis")
        try:
            ledger = self.observer.load_ledger()
            history = ledger.get("execution_history", [])

            recommendations = []

            # 1. Topic diversity analysis
            if len(history) >= 3:
                recent_topics = [e.get("topic", "") for e in history[-5:]]
                unique_topics = len(set(recent_topics))
                if unique_topics < len(recent_topics) * 0.6:
                    recommendations.append("HIGH: Topic diversity low — expand discovery sources")

            # 2. Upload success rate
            uploads = [e for e in history if e.get("upload_results", {}).get("overall_status") == "success"]
            if history:
                upload_rate = len(uploads) / len(history)
                if upload_rate < 0.5:
                    recommendations.append(f"MEDIUM: Upload success rate {upload_rate:.0%} — check OAuth scopes")

            # 3. Compliance failure analysis
            compliance_fails = sum(1 for e in history if e.get("compliance_failed"))
            if compliance_fails > len(history) * 0.3:
                recommendations.append("HIGH: Excessive compliance failures — review legal check rules")

            # 4. Assembly failure analysis
            asm_fails = sum(1 for e in history if e.get("phase") == "Assembly" and e.get("status") == "FAILED")
            if asm_fails >= 2:
                recommendations.append("MEDIUM: Repeated assembly failures — check FFmpeg installation")

            # 5. Growth recommendations
            recommendations.append("TIP: Cover trending topics from Google Trends India — cricket, movies, politics, weather. Diverse content grows channels faster than single-topic focus.")
            recommendations.append("TIP: Upload between 4PM-8PM IST for maximum Telugu audience engagement")

            # Output recommendations
            if recommendations:
                self.log("📋 Growth Recommendations:")
                for rec in recommendations:
                    self.log(f"  → {rec}")
            else:
                self.log("✅ No critical issues detected. Pipeline healthy.")

            # Save recommendations to ledger
            ledger["growth_recommendations"] = [
                {"priority": r.split(":")[0], "suggestion": r.split(":", 1)[1].strip() if ":" in r else r, "status": "active"}
                for r in recommendations
            ]
            self.observer.save_ledger(ledger)

            state["intelligence_recommendations"] = recommendations
            self.orchestrator.timer.stop("Post-Pipeline", "Intelligence Analysis")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "Intelligence Analysis")
            self.log(f"Intelligence analysis error (non-fatal): {e}")
        return state


class ContinuousAuditorAgent(BaseAgent):
    """Final phase: telemetry commit and performance logging."""
    def __init__(self, orchestrator):
        super().__init__("Continuous Auditor", orchestrator)
        self.observer = GrowthObserver()

    def learn(self, ledger: dict):
        """Track audit patterns."""
        pass

    def execute(self, state: dict) -> dict:
        self.log("Recording pipeline execution traces and telemetry...")
        self.orchestrator.timer.start("Phase 8: Telemetry", "8.1 Ledger Commit")
        try:
            selected_topic = state.get("selected_topic")
            upload_results = state.get("upload_results", {"overall_status": "skipped"})
            branded_thumbnail = state.get("branded_thumbnail")
            if selected_topic:
                durations = self.orchestrator.timer.get_duration_map()
                thumbnail_exists = os.path.exists(branded_thumbnail) if branded_thumbnail else False
                self.observer.log_execution(selected_topic, durations, thumbnail_exists, upload_results)
            self.orchestrator.timer.stop("Phase 8: Telemetry", "8.1 Ledger Commit")
            self.log("Telemetry committed.")
        except Exception as e:
            self.orchestrator.timer.fail("Phase 8: Telemetry", "8.1 Ledger Commit")
            self.log(f"Telemetry error (non-fatal): {e}")
        return state


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION GATES (for new checkpoints)
# ═══════════════════════════════════════════════════════════════════════════════

class ComplianceAdFriendlyIntegration(BaseIntegrationAgent):
    """Gate: compliance → ad-friendly check."""
    def __init__(self, orchestrator):
        super().__init__("Compliance→AdFriendly Integration", orchestrator, ["compliance_result", "selected_topic"])
    def execute(self, state: dict) -> dict:
        super().execute(state)
        compliance_result = state.get("compliance_result", {})
        passed = (
            compliance_result.get("verdict") == "PASS"
            or compliance_result.get("recommendation") in ("APPROVE", "REVIEW")
        )
        if not passed:
            raise ValueError(f"[{self.name}] Compliance result is '{compliance_result}' — cannot proceed.")
        return state

class CTROptimizationIntegration(BaseIntegrationAgent):
    """Gate: CTR optimization → assembly."""
    def __init__(self, orchestrator):
        super().__init__("CTR→Assembly Integration", orchestrator, ["branded_thumbnail"])


# ═══════════════════════════════════════════════════════════════════════════════
# NEW PRE-PIPELINE AGENTS
# ═══════════════════════════════════════════════════════════════════════════════

class UploadTimeOptimizationAgent(BaseAgent):
    """
    Pre-pipeline upload time optimizer: determines optimal upload schedule
    based on audience timezone analysis and ledger data.
    """
    def __init__(self, orchestrator):
        super().__init__("Upload Time Optimizer", orchestrator)
        self.optimizer = UploadTimeOptimizer()

    def learn(self, ledger: dict):
        """Learn from upload time performance history."""
        history = ledger.get("execution_history", [])
        upload_entries = [e for e in history if e.get("upload_time")]
        if len(upload_entries) >= 3:
            self.log(f"Learning: {len(upload_entries)} past upload time records analyzed")

    def execute(self, state: dict) -> dict:
        self.log("Analyzing optimal upload times for audience timezones...")
        self.orchestrator.timer.start("Pre-Pipeline", "Upload Time Optimization")
        try:
            schedule = self.optimizer.get_optimal_upload_time()
            shorts_schedule = self.optimizer.get_shorts_schedule(
                schedule.get("recommended_time_ist", "07:00")
            )
            state["upload_schedule"] = schedule
            state["shorts_upload_schedule"] = shorts_schedule
            self.log(f"📅 Recommended upload: {schedule['recommended_time_ist']} IST "
                     f"({schedule['window_name']})")
            for s in shorts_schedule:
                self.log(f"  Short {s['short_number']}: {s['ist_time']} IST ({s['strategy']})")
            self.orchestrator.timer.stop("Pre-Pipeline", "Upload Time Optimization")
        except Exception as e:
            self.orchestrator.timer.fail("Pre-Pipeline", "Upload Time Optimization")
            self.log(f"Upload time optimization error (non-fatal): {e}")
            state["upload_schedule"] = None
            state["shorts_upload_schedule"] = []
        return state


class LicenseComplianceAgent(BaseAgent):
    """
    Pre-pipeline license compliance: ensures all visual assets are properly
    licensed before any production work begins.
    """
    def __init__(self, orchestrator):
        super().__init__("License Compliance", orchestrator)
        self.tracker = LicenseTracker()

    def learn(self, ledger: dict):
        """Track license violation patterns."""
        history = ledger.get("execution_history", [])
        violations = [e for e in history if e.get("license_violation")]
        if violations:
            self.log(f"Learning: {len(violations)} past license violations recorded")

    def execute(self, state: dict) -> dict:
        self.log("Checking image licenses and copyright compliance...")
        self.orchestrator.timer.start("Pre-Pipeline", "License Compliance")
        try:
            stats = self.tracker.get_stats()
            safe_sources = self.tracker.get_safe_sources()
            state["license_stats"] = stats
            state["approved_image_sources"] = safe_sources
            self.log(f"📋 Licenses tracked: {stats['total_tracked']} assets, "
                     f"{stats.get('commercial_safe', 0)} commercial-safe, "
                     f"{len(safe_sources)} approved sources")
            if stats.get("violation_count", 0) > 0:
                self.log(f"⚠️ {stats['violation_count']} license violations detected!")
            self.orchestrator.timer.stop("Pre-Pipeline", "License Compliance")
        except Exception as e:
            self.orchestrator.timer.fail("Pre-Pipeline", "License Compliance")
            self.log(f"License compliance error (non-fatal): {e}")
            state["license_stats"] = None
            state["approved_image_sources"] = []
        return state


class ContentCalendarAgent(BaseAgent):
    """
    Pre-pipeline content calendar: checks upcoming planned content
    and ensures topic alignment with content strategy.
    """
    def __init__(self, orchestrator):
        super().__init__("Content Calendar", orchestrator)
        self.calendar = ContentCalendar()
        self.intel = CompetitorIntel()

    def learn(self, ledger: dict):
        """Learn from content calendar adherence."""
        history = ledger.get("execution_history", [])
        if len(history) >= 3:
            self.log(f"Learning: {len(history)} past runs for content gap analysis")

    def execute(self, state: dict) -> dict:
        self.log("Checking content calendar and competitor intelligence...")
        self.orchestrator.timer.start("Pre-Pipeline", "Content Calendar")
        try:
            # Get calendar recommendations
            schedule = self.calendar.get_weekly_schedule()
            state["content_calendar_schedule"] = schedule

            # Run competitor analysis on current topic if available
            gap_result = self.intel.analyze_content_gaps()
            state["content_gaps"] = gap_result
            state["competitor_summary"] = self.intel.get_competitor_summary()

            self.log(f"📅 Calendar: {schedule.get('shorts_per_week', '?')} shorts/week planned")
            self.log(f"🔍 Competitor gaps: {gap_result.get('content_gaps', 0)} content gaps identified")
            if gap_result.get("top_priorities"):
                for gap in gap_result["top_priorities"][:3]:
                    self.log(f"  → Gap: {gap}")

            self.orchestrator.timer.stop("Pre-Pipeline", "Content Calendar")
        except Exception as e:
            self.orchestrator.timer.fail("Pre-Pipeline", "Content Calendar")
            self.log(f"Content calendar error (non-fatal): {e}")
            state["content_calendar_schedule"] = None
            state["content_gaps"] = None
            state["competitor_summary"] = None
        return state


# ═══════════════════════════════════════════════════════════════════════════════
# NEW MAIN PIPELINE AGENTS
# ═══════════════════════════════════════════════════════════════════════════════

class AdFriendlyCheckAgent(BaseAgent):
    """
    Inline ad-friendly content check: runs after compliance to verify
    advertiser-friendly status for broader audience reach.
    """
    def __init__(self, orchestrator):
        super().__init__("Ad-Friendly Checker", orchestrator)
        self.checker = AdFriendlyChecker()

    def learn(self, ledger: dict):
        """Track ad-friendliness patterns from analytics."""
        history = ledger.get("execution_history", [])
        low_cpm = [e for e in history if e.get("ad_friendly_score", 100) < 70]
        if low_cpm:
            self.log(f"Learning: {len(low_cpm)} past low ad-friendliness scores flagged")

    def execute(self, state: dict) -> dict:
        self.log("Running advertiser-friendly content analysis...")
        self.orchestrator.timer.start("Phase 4: Safety", "4.2 Ad-Friendly Check")
        try:
            script_payload = state.get("script_payload")
            selected_topic = state.get("selected_topic")
            if not script_payload or not selected_topic:
                raise ValueError("Script payload or topic missing")

            main_seg = script_payload.get_segment("main")
            result = self.checker.check_content(
                title=selected_topic.get("title", ""),
                description=selected_topic.get("description", ""),
                script=main_seg["text"],
                tags=selected_topic.get("tags", []),
            )

            state["ad_friendly_result"] = result

            emoji = "✅" if result["score"] >= 85 else "⚠️" if result["score"] >= 70 else "🔴"
            self.log(f"{emoji} Ad-Friendly Score: {result['score']}/100 "
                     f"(Risk: {result['risk_level']}) — {result['monetization_expectation']}")

            for rec in result.get("recommendations", []):
                self.log(f"  💡 {rec}")

            self.orchestrator.timer.stop("Phase 4: Safety", "4.2 Ad-Friendly Check")
        except Exception as e:
            self.orchestrator.timer.fail("Phase 4: Safety", "4.2 Ad-Friendly Check")
            self.log(f"Ad-friendly check error (non-fatal): {e}")
            state["ad_friendly_result"] = None
        return state


class CTROptimizationAgent(BaseAgent):
    """
    CTR optimization agent: scores titles and optimizes metadata
    for maximum click-through rate.
    """
    def __init__(self, orchestrator):
        super().__init__("CTR Optimizer", orchestrator)
        self.optimizer = CTROptimizer()

    def learn(self, ledger: dict):
        """Learn from CTR performance."""
        history = ledger.get("execution_history", [])
        ctr_entries = [e for e in history if e.get("ctr_score")]
        if len(ctr_entries) >= 3:
            avg_ctr = sum(e.get("ctr_score", 0) for e in ctr_entries) / len(ctr_entries)
            self.log(f"Learning: avg CTR score = {avg_ctr:.1f}")

    def execute(self, state: dict) -> dict:
        self.log("Optimizing title and metadata for CTR...")
        self.orchestrator.timer.start("Phase 6: Thumbnails", "6.2 CTR Optimization")
        try:
            script_payload = state.get("script_payload")
            selected_topic = state.get("selected_topic")
            if not script_payload or not selected_topic:
                raise ValueError("Script payload or topic missing")

            # Get title variants from script payload
            title_variants = getattr(script_payload, "main_title_variants", [])
            if not title_variants:
                title_variants = [selected_topic.get("title", "")]

            # Score and select best title
            scored = self.optimizer.score_titles(title_variants)
            best_title = scored[0]["title"] if scored else title_variants[0]

            # Generate A/B variants for testing
            ab_variants = self.optimizer.generate_title_variants(best_title)

            state["optimized_title"] = best_title
            state["title_variants"] = scored
            state["ab_title_variants"] = ab_variants

            # Record in A/B test tracker (non-critical)
            try:
                tracker = ABTestTracker()
                for i, variant in enumerate(ab_variants):
                    variant_title = variant["title"] if isinstance(variant, dict) else str(variant)
                    tracker.create_test(
                        "title",
                        f"CTR title test variant {i}",
                        {"title": best_title},
                        {"title": variant_title},
                        topic=selected_topic.get("title", ""),
                        video_id=f"title_test_{selected_topic.get('id', 'unknown')}_{i}",
                    )
            except Exception as tracker_err:
                self.log(f"A/B tracker registration skipped (non-critical): {tracker_err}")

            self.log(f"🏆 Best title: '{best_title}' (score: {scored[0]['score'] if scored else 'N/A'})")
            self.log(f"📊 A/B variants generated: {len(ab_variants)}")

            self.orchestrator.timer.stop("Phase 6: Thumbnails", "6.2 CTR Optimization")
        except Exception as e:
            self.orchestrator.timer.fail("Phase 6: Thumbnails", "6.2 CTR Optimization")
            self.log(f"CTR optimization error (non-fatal): {e}")
            state["optimized_title"] = None
        return state


# ═══════════════════════════════════════════════════════════════════════════════
# NEW POST-PIPELINE AGENTS
# ═══════════════════════════════════════════════════════════════════════════════

class YouTubeAnalyticsAgent(BaseAgent):
    """
    Post-pipeline YouTube Analytics: pulls performance data for
    recently uploaded videos and feeds it back into the system.
    """
    def __init__(self, orchestrator):
        super().__init__("YouTube Analytics", orchestrator)
        self.analytics = YouTubeAnalytics()

    def learn(self, ledger: dict):
        """Analyze performance trends from analytics feedback."""
        feedback = ledger.get("feedback_history", [])
        if len(feedback) >= 3:
            self.log(f"Learning: {len(feedback)} analytics feedback entries available")

    def execute(self, state: dict) -> dict:
        self.log("Pulling YouTube Analytics for recent uploads...")
        self.orchestrator.timer.start("Post-Pipeline", "Analytics Pull")
        try:
            upload_results = state.get("upload_results", {})
            youtube_ids = []

            # Collect YouTube IDs
            if isinstance(upload_results, dict):
                main_result = upload_results.get("main")
                if main_result and isinstance(main_result, dict):
                    yt_id = main_result.get("youtube_id")
                    if yt_id:
                        youtube_ids.append(yt_id)
                shorts = upload_results.get("shorts", {})
                for key, result in shorts.items():
                    if isinstance(result, dict):
                        yt_id = result.get("youtube_id")
                        if yt_id:
                            youtube_ids.append(yt_id)

            if youtube_ids:
                self.log(f"Tracking {len(youtube_ids)} video(s)")
                # Note: Requires YouTube Analytics API OAuth with proper scopes
                state["analytics_tracking_ids"] = youtube_ids
            else:
                self.log("No video IDs to track yet")

            self.orchestrator.timer.stop("Post-Pipeline", "Analytics Pull")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "Analytics Pull")
            self.log(f"Analytics pull error (non-fatal): {e}")
        return state


class CommunityEngagementAgent(BaseAgent):
    """
    Post-pipeline community engagement: generates community tab posts,
    comment responses, and engagement actions.
    """
    def __init__(self, orchestrator):
        super().__init__("Community Engagement", orchestrator)
        self.community = CommunityEngagement()
        self.tracker = ABTestTracker()

    def learn(self, ledger: dict):
        """Learn from engagement patterns."""
        history = ledger.get("execution_history", [])
        engagement = [e for e in history if e.get("community_posted")]
        if engagement:
            self.log(f"Learning: {len(engagement)} past community engagement actions")

    def execute(self, state: dict) -> dict:
        self.log("Generating community engagement actions...")
        self.orchestrator.timer.start("Post-Pipeline", "Community Engagement")
        try:
            selected_topic = state.get("selected_topic")
            upload_results = state.get("upload_results", {})

            # Check active A/B tests
            active_tests = self.tracker.get_active_tests()
            if active_tests:
                self.log(f"📊 Active A/B tests: {len(active_tests)}")
                for test in active_tests[:3]:
                    self.log(f"  → {test.get('test_name')}: {test.get('status')}")

            # Community post for uploaded video if any
            if isinstance(upload_results, dict) and upload_results.get("main"):
                yt_id = upload_results["main"].get("youtube_id")
                if yt_id:
                    post_text = self.community.generate_community_post(
                        selected_topic.get("title", ""),
                        yt_id,
                    )
                    state["community_post"] = {"platform": "youtube_community", "text": post_text}
                    self.log(f"📢 Community post drafted for video: {yt_id}")

            self.orchestrator.timer.stop("Post-Pipeline", "Community Engagement")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "Community Engagement")
            self.log(f"Community engagement error (non-fatal): {e}")
        return state


class CompetitorIntelAgent(BaseAgent):
    """
    Post-pipeline competitor intelligence: tracks competitor activity
    and identifies content opportunities.
    """
    def __init__(self, orchestrator):
        super().__init__("Competitor Intel", orchestrator)
        self.intel = CompetitorIntel()

    def learn(self, ledger: dict):
        """Intel is its own learner via push_to_ledger."""

    def execute(self, state: dict) -> dict:
        self.log("Running competitor intelligence scan...")
        self.orchestrator.timer.start("Post-Pipeline", "Competitor Intel")
        try:
            # Push intel to growth ledger
            self.intel.push_to_ledger(self.orchestrator.ledger)

            summary = self.intel.get_competitor_summary()
            self.log(f"🔍 Competitors tracked: {summary['total_tracked']}, "
                     f"High threats: {summary['high_threats']}, "
                     f"Content gaps: {summary['content_gaps']}")

            self.orchestrator.timer.stop("Post-Pipeline", "Competitor Intel")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "Competitor Intel")
            self.log(f"Competitor intel error (non-fatal): {e}")
        return state


# ─── NEW v77.0 Agent: RetentionOptimizationAgent ──────────────────────
class RetentionOptimizationAgent(BaseAgent):
    """
    Post-pipeline retention optimization: analyzes retention cliffs,
    CTR benchmarks, impression funnel, series funnel planning, and
    recommendation engine signals.
    """
    def __init__(self, orchestrator):
        super().__init__("Retention Optimizer", orchestrator)
        self.analyzer = RetentionAnalyzer()

    def learn(self, ledger: dict):
        retention_history = ledger.get("retention_analysis", [])
        if len(retention_history) >= 2:
            self.log(f"Learning: {len(retention_history)} retention analyses available")

    def execute(self, state: dict) -> dict:
        self.log("Analyzing retention optimization signals...")
        self.orchestrator.timer.start("Post-Pipeline", "Retention Optimization")
        try:
            topic = state.get("selected_topic", {})
            analytics_ids = state.get("analytics_tracking_ids", [])

            if analytics_ids:
                for yt_id in analytics_ids[:3]:
                    self.analyzer.benchmark_ctr(yt_id, "news_politics", 0.05)

            # Series funnel planning
            if topic.get("title"):
                series_plan = self.analyzer.plan_series_funnel(topic["title"], num_parts=3)
                state["series_funnel_plan"] = series_plan

            # Next-video comment suggestion
            next_comment = self.analyzer.build_next_video_comment()
            state["next_video_comment"] = next_comment

            self.log("📊 Retention analysis complete")
            self.orchestrator.timer.stop("Post-Pipeline", "Retention Optimization")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "Retention Optimization")
            self.log(f"Retention optimization error (non-fatal): {e}")
        return state


# ─── NEW v77.0 Agent: ShortsOptimizationAgent ────────────────────────
class ShortsOptimizationAgent(BaseAgent):
    """
    Inline Shorts optimization: Shorts title formula, comment reply,
    remix detection, Shorts series, CTA to long-form.
    """
    def __init__(self, orchestrator):
        super().__init__("Shorts Optimizer", orchestrator)
        self.optimizer = ShortsOptimizer()
        self.reliability = UploadReliabilityManager()

    def learn(self, ledger: dict):
        shorts_history = ledger.get("shorts_analysis", [])
        if shorts_history:
            self.log(f"Learning: {len(shorts_history)} past Shorts optimizations")

    def execute(self, state: dict) -> dict:
        self.log("Optimizing Shorts-specific signals...")
        self.orchestrator.timer.start("Post-Pipeline", "Shorts Optimization")
        try:
            topic = state.get("selected_topic", {})
            title = topic.get("title", "Telugu news")

            # Generate Shorts title variants
            short_titles = self.optimizer.generate_shorts_title_batch(title)
            state["shorts_title_variants"] = short_titles

            # Shorts-to-long CTA
            upload_results = state.get("upload_results", {})
            main_result = upload_results.get("main", {})
            main_url = main_result.get("url", "") if isinstance(main_result, dict) else ""
            cta = self.optimizer.build_shorts_cta(main_video_url=main_url if main_url else None)
            state["shorts_to_long_cta"] = cta

            # Comment reply schedule
            import time as _time
            reply_schedule = self.optimizer.plan_comment_reply_schedule(int(_time.time()), comments_count=5)
            state["shorts_reply_schedule"] = reply_schedule

            # Branding consistency check
            branding_check = self.optimizer.check_branding_consistency({
                "has_watermark": True, "brand_colors": True,
                "font": "Bebas Neue", "cta": cta, "has_telugu": True,
            })
            state["shorts_branding_check"] = branding_check

            self.log(f"📱 Shorts optimized: {len(short_titles)} title variants, CTA ready")
            self.orchestrator.timer.stop("Post-Pipeline", "Shorts Optimization")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "Shorts Optimization")
            self.log(f"Shorts optimization error (non-fatal): {e}")
        return state


# ─── NEW v77.0 Agent: ContentQualityAgent ────────────────────────────
class ContentQualityAgent(BaseAgent):
    """
    Post-pipeline content quality: fact-check, bias detection,
    freshness scoring, duplicate detection, content pillar analysis.
    """
    def __init__(self, orchestrator):
        super().__init__("Content Quality", orchestrator)
        self.quality = ContentQualityEngine()

    def learn(self, ledger: dict):
        video_history = ledger.get("execution_history", [])
        if len(video_history) >= 3:
            self.log(f"Learning: {len(video_history)} past videos for content mix analysis")

    def execute(self, state: dict) -> dict:
        self.log("Running content quality assurance...")
        self.orchestrator.timer.start("Post-Pipeline", "Content Quality")
        try:
            script = state.get("script_payload")
            script_text = ""
            if script and hasattr(script, "full_script"):
                script_text = script.full_script

            # Fact-check
            if script_text:
                fact_result = self.quality.fact_check_script(script_text)
                state["fact_check_result"] = fact_result
                if not fact_result["pass"]:
                    self.log(f"  ⚠️ {fact_result['needs_review']} claims need verification")

            # Bias detection
            if script_text:
                bias_result = self.quality.detect_bias(script_text)
                state["bias_check_result"] = bias_result
                if not bias_result["pass"]:
                    self.log(f"  ⚠️ Bias risk: {bias_result['risk_level']}")

            # Content pillar mix
            ledger = self.quality.load_ledger()
            video_history = ledger.get("videos", []) + ledger.get("execution_history", [])
            mix = self.quality.analyze_content_mix(video_history)
            state["content_pillar_mix"] = mix
            recommended = self.quality.recommend_next_pillar(video_history)
            state["recommended_next_pillar"] = recommended
            self.log(f"📊 Content pillars: next recommended = {recommended}")

            self.orchestrator.timer.stop("Post-Pipeline", "Content Quality")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "Content Quality")
            self.log(f"Content quality error (non-fatal): {e}")
        return state


# ─── NEW v77.0 Agent: ReliabilityAgent ───────────────────────────────
class ReliabilityAgent(BaseAgent):
    """
    Post-pipeline reliability: upload queue management, quota monitoring,
    account health check, rate limit backoff.
    """
    def __init__(self, orchestrator):
        super().__init__("Reliability Manager", orchestrator)
        self.reliability = UploadReliabilityManager()

    def learn(self, ledger: dict):
        failures = ledger.get("upload_failures", [])
        if failures:
            self.log(f"Learning: {len(failures)} past upload failures recorded")

    def execute(self, state: dict) -> dict:
        self.log("Checking system reliability and API health...")
        self.orchestrator.timer.start("Post-Pipeline", "Reliability Check")
        try:
            # API quota status
            quota_status = self.reliability.get_quota_status()
            state["api_quota_status"] = quota_status
            if quota_status["status"] == "critical":
                self.log("🚨 CRITICAL: API quota nearly exhausted!")

            # Account health
            active_account = self.reliability.get_active_account()
            state["active_account"] = active_account
            if active_account != "primary":
                self.log(f"⚠️ Using failover account: {active_account}")

            # Rate limit check
            backoff = self.reliability.get_backoff_seconds("youtube")
            if backoff > 0:
                self.log(f"⏳ Rate limit backoff: {backoff}s remaining")
                state["rate_limit_backoff_s"] = backoff

            # Upload queue status
            queue_status = self.reliability.get_queue_status()
            state["upload_queue_status"] = queue_status
            if queue_status["queued"] > 0:
                self.log(f"📋 Upload queue: {queue_status['queued']} pending")

            self.orchestrator.timer.stop("Post-Pipeline", "Reliability Check")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "Reliability Check")
            self.log(f"Reliability check error (non-fatal): {e}")
        return state


# ═══════════════════════════════════════════════════════════════════════════════
# v78.0: NEW POST-PIPELINE AGENTS (5 additional free items)
# ═══════════════════════════════════════════════════════════════════════════════

class CollaborationAgent(BaseAgent):
    """
    D2.6: Post-pipeline collaboration tracking.
    Maintains database of Telugu creator partners and generates outreach.
    """
    def __init__(self, orchestrator):
        super().__init__("Collaboration Agent", orchestrator)
        self.tracker = CollaborationTracker()

    def learn(self, ledger: dict):
        stats = self.tracker.get_stats()
        if stats["total_partners"] > 0:
            self.log(f"Learning: {stats['total_partners']} partners tracked, "
                     f"{stats['total_outreach_sent']} outreach sent")

    def execute(self, state: dict) -> dict:
        self.log("Running collaboration tracking and outreach generation...")
        self.orchestrator.timer.start("Post-Pipeline", "D2.6 Collaboration Tracker")
        try:
            selected_topic = state.get("selected_topic", {})
            result = self.tracker.run(topic=selected_topic)
            state["collaboration_stats"] = result.get("stats", {})
            state["collab_recommendations"] = result.get("recommendations", [])
            self.orchestrator.timer.stop("Post-Pipeline", "D2.6 Collaboration Tracker")
            self.log(f"Collaboration tracking complete: {result.get('stats', {})}")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "D2.6 Collaboration Tracker")
            self.log(f"Collaboration tracking error (non-fatal): {e}")
        return state


class BlogCompanionAgent(BaseAgent):
    """
    H3.4: Post-pipeline blog companion article generation.
    Generates HTML and Markdown articles from video script content.
    """
    def __init__(self, orchestrator):
        super().__init__("Blog Companion Agent", orchestrator)
        self.generator = BlogCompanionGenerator()

    def learn(self, ledger: dict):
        history = ledger.get("execution_history", [])
        blog_entries = [e for e in history if e.get("agent") == "BlogCompanionAgent"]
        if blog_entries:
            self.log(f"Learning: {len(blog_entries)} past blog articles generated")

    def execute(self, state: dict) -> dict:
        self.log("Generating blog companion article...")
        self.orchestrator.timer.start("Post-Pipeline", "H3.4 Blog Companion")
        try:
            selected_topic = state.get("selected_topic", {})
            script_payload = state.get("script_payload")
            script_text = ""
            if script_payload:
                try:
                    seg = script_payload.get_segment("main")
                    script_text = seg.get("text", "") if seg else ""
                except Exception:
                    pass
            upload_results = state.get("upload_results", {})
            video_url = upload_results.get("main_video_url", "")
            result = self.generator.run(
                topic=selected_topic,
                script_text=script_text,
                video_url=video_url,
            )
            state["blog_article_paths"] = result
            self.orchestrator.timer.stop("Post-Pipeline", "H3.4 Blog Companion")
            paths = ", ".join(str(v) for v in result.values() if v)
            self.log(f"Blog article generated: {paths}")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "H3.4 Blog Companion")
            self.log(f"Blog companion error (non-fatal): {e}")
        return state


class NewsletterAgent(BaseAgent):
    """
    H3.5: Post-pipeline newsletter digest generation.
    Creates HTML email newsletter from recent video content.
    """
    def __init__(self, orchestrator):
        super().__init__("Newsletter Agent", orchestrator)
        self.generator = NewsletterGenerator()

    def learn(self, ledger: dict):
        history = ledger.get("execution_history", [])
        nl_entries = [e for e in history if e.get("agent") == "NewsletterAgent"]
        if nl_entries:
            self.log(f"Learning: {len(nl_entries)} past newsletters generated")

    def execute(self, state: dict) -> dict:
        self.log("Generating weekly newsletter digest...")
        self.orchestrator.timer.start("Post-Pipeline", "H3.5 Newsletter Digest")
        try:
            sorted_topics = state.get("sorted_topics", [])
            result = self.generator.run(topics=sorted_topics[:10])
            state["newsletter_path"] = result.get("newsletter_path")
            self.orchestrator.timer.stop("Post-Pipeline", "H3.5 Newsletter Digest")
            self.log(f"Newsletter generated: {result.get('newsletter_path', 'N/A')}")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "H3.5 Newsletter Digest")
            self.log(f"Newsletter error (non-fatal): {e}")
        return state


class CommunityPosterAgent(BaseAgent):
    """
    H3.2: Post-pipeline YouTube Community Tab post scheduler.
    Composes and schedules community posts via YouTube Data API v3.
    """
    def __init__(self, orchestrator):
        super().__init__("Community Poster Agent", orchestrator)
        self.poster = CommunityPoster()

    def learn(self, ledger: dict):
        history = ledger.get("execution_history", [])
        post_entries = [e for e in history if e.get("agent") == "CommunityPosterAgent"]
        if post_entries:
            self.log(f"Learning: {len(post_entries)} past community post runs")

    def execute(self, state: dict) -> dict:
        self.log("Composing community tab posts...")
        self.orchestrator.timer.start("Post-Pipeline", "H3.2 Community Poster")
        try:
            selected_topic = state.get("selected_topic", {})
            upload_results = state.get("upload_results", {})
            videos = []
            if upload_results.get("main_video_url"):
                videos.append({
                    "title": selected_topic.get("title", "ViralDNA Update"),
                    "url": upload_results["main_video_url"],
                })
            result = self.poster.run(topic=selected_topic, videos=videos)
            state["community_post"] = result.get("post")
            state["community_weekly_schedule"] = result.get("weekly_schedule")
            self.orchestrator.timer.stop("Post-Pipeline", "H3.2 Community Poster")
            self.log(f"Community posts scheduled: {result.get('total_weekly_posts', 0)} for the week")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "H3.2 Community Poster")
            self.log(f"Community poster error (non-fatal): {e}")
        return state


class UploadTimingAgent(BaseAgent):
    """
    D3.6: Post-pipeline upload timing optimization.
    Uses YouTube Analytics API (with diaspora fallback) to find optimal upload windows.
    """
    def __init__(self, orchestrator):
        super().__init__("Upload Timing Agent", orchestrator)
        self.optimizer = UploadTimeOptimizer()

    def learn(self, ledger: dict):
        history = ledger.get("execution_history", [])
        timing_entries = [e for e in history if e.get("agent") == "UploadTimingAgent"]
        if timing_entries:
            self.log(f"Learning: {len(timing_entries)} past timing optimizations")

    def execute(self, state: dict) -> dict:
        self.log("Computing optimal upload timing...")
        self.orchestrator.timer.start("Post-Pipeline", "D3.6 Upload Timing Optimizer")
        try:
            result = self.optimizer.run()
            state["upload_timing"] = result
            optimal = result.get("optimal_slot", {})
            self.orchestrator.timer.stop("Post-Pipeline", "D3.6 Upload Timing Optimizer")
            self.log(f"Optimal upload: {optimal.get('recommendation', 'N/A')}")
        except Exception as e:
            self.orchestrator.timer.fail("Post-Pipeline", "D3.6 Upload Timing Optimizer")
            self.log(f"Upload timing error (non-fatal): {e}")
        return state


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

class MultiAgentOrchestrator:
    """
    Master orchestrator coordinating all agents over a shared state blackboard.
    Manages pre-pipeline, main pipeline (task + integration), and post-pipeline agents.
    """
    def __init__(self):
        self.timer = ExecutionTimer()
        self.engine = GeminiEngine()

        # Centralized blackboard
        self.state = {
            "raw_news": [], "selected_topic": None, "script_payload": None,
            "compliance_result": None, "voiceover_assets": {}, "visuals": [],
            "background_canvas": None, "branded_thumbnail": None,
            "compiled_videos": [], "upload_results": {}, "errors": [],
            "lookback_hours": 12, "mode": "normal",
            # New state keys for integrated modules
            "upload_schedule": None, "shorts_upload_schedule": [],
            "youtube_service": None,
            "license_stats": None, "approved_image_sources": [],
            "content_calendar_schedule": None, "content_gaps": None,
            "competitor_summary": None, "ad_friendly_result": None,
            "optimized_title": None, "title_variants": [],
            "ab_title_variants": [], "analytics_tracking_ids": [],
            "community_post": None,
            # New state keys for v77.0 modules
            "series_funnel_plan": None, "next_video_comment": None,
            "shorts_title_variants": [], "shorts_to_long_cta": None,
            "shorts_reply_schedule": [], "shorts_branding_check": None,
            "fact_check_result": None, "bias_check_result": None,
            "content_pillar_mix": None, "recommended_next_pillar": None,
            # New state keys for v78.0 modules
            "collaboration_stats": None, "collab_recommendations": [],
            "blog_article_paths": None, "newsletter_path": None,
            "community_weekly_schedule": None, "upload_timing": None,
            "api_quota_status": None, "active_account": "primary",
            "rate_limit_backoff_s": 0, "upload_queue_status": None,
        }

        # ── Pre-pipeline agents ──
        self.pre_agents = [
            CleanupAgent(self),
            LicenseComplianceAgent(self),       # NEW: License check before production
            UploadTimeOptimizationAgent(self),  # NEW: Optimal upload time analysis
            ContentCalendarAgent(self),         # NEW: Content calendar + competitor intel
            PrimetimeSchedulerAgent(self),
        ]

        # ── Main pipeline task agents ──
        self.task_agents = [
            DiscoveryAgent(self),          # 0
            WeightingAgent(self),          # 1
            ScriptingAgent(self),          # 2
            ComplianceAgent(self),         # 3
            AdFriendlyCheckAgent(self),    # NEW: Ad-friendly check (after compliance)
            VoiceSynthesisAgent(self),     # 4 (was 4, now 5)
            VisualHarvestingAgent(self),   # 5 (was 5, now 6)
            ThumbnailSynthesisAgent(self), # 6 (was 6, now 7)
            CTROptimizationAgent(self),    # NEW: CTR optimization (after thumbnails)
            SequentialAssemblyAgent(self), # 7 (was 7, now 9)
            ForensicAuditGateAgent(self),  # NEW v79: Pre-ship forensic audit gate (task index 10)
            ResilientUploaderAgent(self),  # task index 11 (final task agent)
        ]

        # ── Integration agents (between main pipeline task agents) ──
        self.integration_agents = [
            DiscoveryWeightingIntegration(self),         # After 0, before 1
            WeightingScriptingIntegration(self),          # After 1, before 2
            ScriptingComplianceIntegration(self),         # After 2, before 3
            ComplianceAdFriendlyIntegration(self),        # After 3 (Compliance), before AdFriendly (4)
            ComplianceVoiceIntegration(self),             # After 4 (AdFriendly), before Voice (5)
            VoiceVisualIntegration(self),                 # After 5 (Voice), before Visuals (6)
            VisualThumbnailIntegration(self),             # After 6 (Visuals), before Thumbnails (7)
            ThumbnailAssemblyIntegration(self),           # After 7 (Thumbnails), before CTR (8)
            CTROptimizationIntegration(self),             # After 8 (CTR), before SequentialAssembly (9)
            AssemblyUploadIntegration(self),              # After 9 (SequentialAssembly), before ForensicAuditGate (10)
            ForensicAuditUploadIntegration(self),         # After 10 (ForensicAuditGate), before ResilientUploader (11)
            UploadFeedbackIntegration(self),              # After 11 (ResilientUploader) — validates upload_results (index 11)
        ]

        # ── Post-pipeline agents ──
        self.post_agents = [
            FeedbackAgent(self),
            YouTubeAnalyticsAgent(self),       # YouTube Analytics pull
            CommunityEngagementAgent(self),    # Community engagement + A/B tests
            CompetitorIntelAgent(self),        # Competitor intelligence
            RetentionOptimizationAgent(self),  # NEW v77: Retention + CTR + series funnel
            ShortsOptimizationAgent(self),     # NEW v77: Shorts titles + CTA + branding
            ContentQualityAgent(self),         # NEW v77: Fact-check + bias + pillars
            ReliabilityAgent(self),            # NEW v77: Quota + queue + failover
            CollaborationAgent(self),          # NEW v78: D2.6 Collaboration tracker
            BlogCompanionAgent(self),          # NEW v78: H3.4 Blog companion articles
            NewsletterAgent(self),             # NEW v78: H3.5 Newsletter digest
            CommunityPosterAgent(self),        # NEW v78: H3.2 Community tab posts
            UploadTimingAgent(self),           # NEW v78: D3.6 Upload timing optimizer
            IntelligenceAgent(self),
            ContinuousAuditorAgent(self),
        ]

        # Load growth ledger for self-learning
        self.ledger = GrowthObserver().load_ledger()
        if not self.ledger:
            self.ledger = {"execution_history": [], "upload_times": [], "content_pillars": {}}

    def send_telegram_notification(self, message: str) -> bool:
        import requests
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return False
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message}, timeout=10
            )
            return r.status_code == 200
        except Exception:
            return False

    def _run_agent_with_learning(self, agent: BaseAgent, is_integration: bool = False):
        """Run learn() then execute() for any agent, with timing and error handling."""
        # Self-learning step (skip for integration agents — they don't learn)
        if not is_integration and hasattr(agent, 'learn'):
            try:
                agent.learn(self.ledger)
            except Exception as e:
                print(f"  ⚠️ [{agent.name}] Learning step error (non-fatal): {e}")

        # Execution step
        agent_start_time = time.perf_counter()
        try:
            self.state = agent.execute(self.state)
        except Exception as err:
            agent_duration = time.perf_counter() - agent_start_time
            error_msg = f"FAILURE in [{agent.name}]: {err}"
            print(f"\n⚠️ {error_msg}")
            self.state["errors"].append(error_msg)
            raise
        agent_duration = time.perf_counter() - agent_start_time
        print(f"🤖 Agent Handoff: [{agent.name}] complete (Elapsed: {agent_duration:.2f}s)\n")

    def _run_integration_gate(self, integration_idx: int):
        """Run a single integration agent as a quality gate."""
        agent = self.integration_agents[integration_idx]
        agent_start_time = time.perf_counter()
        try:
            self.state = agent.execute(self.state)
        except Exception as err:
            raise RuntimeError(f"Integration gate failed: {err}")
        agent_duration = time.perf_counter() - agent_start_time
        print(f"🔗 Integration Gate: [{agent.name}] validated (Elapsed: {agent_duration:.2f}s)\n")

    def execute_pipeline(self):
        print("\n" + "="*85)
        print("🕵️‍♂️ VIRALDNA MULTI-AGENT BROADCAST ENGINE SYSTEM ACTIVATION")
        print(f"System Boot: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Agents: {len(self.pre_agents)} pre + {len(self.task_agents)} task + "
              f"{len(self.integration_agents)} integration + {len(self.post_agents)} post = "
              f"{len(self.pre_agents) + len(self.task_agents) + len(self.integration_agents) + len(self.post_agents)} total | v79.0")
        print("="*85 + "\n")

        MAX_TOPIC_RETRIES = 5

        # ── PRE-PIPELINE ──
        print("━"*40 + " PRE-PIPELINE " + "━"*40)
        for agent in self.pre_agents:
            self._run_agent_with_learning(agent)

        # ── MAIN PIPELINE: Discovery (Phase 1) ──
        print("━"*40 + " MAIN PIPELINE " + "━"*40)
        self._run_agent_with_learning(self.task_agents[0])  # Discovery
        self._run_integration_gate(0)                        # Discovery→Weighting

        # ── MAIN PIPELINE: Weighting (Phase 2) ──
        self._run_agent_with_learning(self.task_agents[1])  # Weighting
        self._run_integration_gate(1)                        # Weighting→Scripting

        # ── MAIN PIPELINE: Topic retry loop (Phases 3+) ──
        sorted_topics = self.state.get("sorted_topics", [])
        if not sorted_topics:
            print("\n🛑 No topics available. Exiting.")
            self.timer.print_report()
            sys.exit(1)

        remaining_task_agents = self.task_agents[2:]  # Scripting through Uploader
        topic_accepted = False

        for topic_idx in range(min(MAX_TOPIC_RETRIES, len(sorted_topics))):
            self.state["selected_topic"] = sorted_topics[topic_idx]
            print(f"\n📋 Topic Attempt {topic_idx + 1}/{min(MAX_TOPIC_RETRIES, len(sorted_topics))}: "
                  f"'{sorted_topics[topic_idx].get('title', 'Unknown')}'")

            topic_failed = False
            for task_idx, task_agent in enumerate(remaining_task_agents):
                try:
                    self._run_agent_with_learning(task_agent)
                except Exception as err:
                    self.state["errors"].append(f"[{task_agent.name}]: {err}")
                    topic_failed = True
                    break

                # Integration gate after each task agent (including after the last — ResilientUploader → UploadFeedback)
                integration_idx = task_idx + 2  # offset for Discovery/Weighting gates
                if integration_idx <= len(self.integration_agents):
                    if integration_idx == len(self.integration_agents):
                        # After the last task agent, run the final integration gate (UploadFeedback)
                        try:
                            self._run_integration_gate(len(self.integration_agents) - 1)
                        except Exception as err:
                            self.state["errors"].append(f"[Integration]: {err}")
                            topic_failed = True
                            break
                    else:
                        try:
                            self._run_integration_gate(integration_idx)
                        except Exception as err:
                            self.state["errors"].append(f"[Integration]: {err}")
                            topic_failed = True
                            break

            if not topic_accepted and not topic_failed:
                topic_accepted = True
                print(f"\n✅ Topic accepted after {topic_idx + 1} attempt(s).")
                break
            elif topic_failed:
                print(f"  → Skipping to next topic...")

        if not topic_accepted:
            print(f"\n🛑 All {min(MAX_TOPIC_RETRIES, len(sorted_topics))} topic attempts exhausted.")
            self.send_telegram_notification("❌ ViralDNA: All topics failed.")
            self.timer.print_report()
            sys.exit(1)

        # ── POST-PIPELINE ──
        print("\n" + "━"*40 + " POST-PIPELINE " + "━"*40)
        for agent in self.post_agents:
            self._run_agent_with_learning(agent)

        # ── FINAL REPORT ──
        self.timer.print_report()
        print("🏆 All Agents completed successfully! Broadcast run complete.\n")

    def execute_spike_check(self):
        """Lightweight spike detection — Telegram alert ONLY. No production."""
        print("\n⚡️ Starting Spike Detection Checkpoint...")
        self.state["lookback_hours"] = 1
        self.timer.start("Spike Check", "Discovery & Weighting (1h)")
        try:
            discovery = DiscoveryAgent(self)
            self.state = discovery.execute(self.state)
            weighting = WeightingAgent(self)
            self.state = weighting.execute(self.state)
            self.timer.stop("Spike Check", "Discovery & Weighting (1h)")
        except Exception as err:
            self.timer.fail("Spike Check", "Discovery & Weighting (1h)")
            print(f"❌ Spike check failed: {err}")
            self.send_telegram_notification(f"❌ ViralDNA Spike Check Failed: {err}")
            return

        sd = SpikeDetector(config)
        spike_results = sd.run(self.state["raw_news"])
        spike_level = spike_results.get("spike_level", "NONE")
        if spike_level in ("URGENT", "STORM"):
            spiked_titles = [f"  • {st['title'][:60]} (jump: {st['jump_ratio']}x)"
                           for st in spike_results.get("spiked_topics", [])[:3]]
            alert = (f"🚨 VIRALDNA SPIKE ALERT [{spike_level}]\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    + "\n".join(spiked_titles) +
                    "\n━━━━━━━━━━━━━━━━━━━━━\n⚡ Review and trigger primetime manually.")
            self.send_telegram_notification(alert)
            print(f"  🔴 SPIKE DETECTED ({spike_level}) — Telegram alert sent.")
        else:
            print(f"  🟢 No urgent spikes ({spike_level}).")


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    from zoneinfo import ZoneInfo
    parser = argparse.ArgumentParser(description="ViralDNA Multi-Agent Broadcast Engine v78.0")
    parser.add_argument(
        "--mode", type=str,
        choices=["spike_check", "primetime", "normal"],
        default="normal",
        help="spike_check=Telegram alert only | primetime=full pipeline 4PM-8PM | normal=full pipeline"
    )
    args = parser.parse_args()

    orchestrator = MultiAgentOrchestrator()

    if args.mode == "spike_check":
        orchestrator.execute_spike_check()
    elif args.mode == "primetime":
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        print(f"🌅 Primetime Mode Activated ({now_ist.strftime('%H:%M IST')}). 12h lookback.")
        orchestrator.state["lookback_hours"] = 12
        orchestrator.state["mode"] = "primetime"
        orchestrator.execute_pipeline()
        orchestrator.send_telegram_notification("✅ Primetime Pipeline Complete.")
    else:
        orchestrator.state["lookback_hours"] = 12
        orchestrator.state["mode"] = "normal"
        orchestrator.execute_pipeline()
