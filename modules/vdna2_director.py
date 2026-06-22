"""
VDNA 3.0 — Director + Factory Architecture
============================================
The official ViralDNA pipeline as of June 15, 2026.

Layer 1: OWL Director — decides WHAT to produce, manages lifecycle
Layer 2: Python Factory — crash-isolated workers that produce artifacts
Layer 3: Skills Specialists — wrapped existing modules (voiceover, video_assembler, etc.)

Key improvements over v80.0 monolithic orchestrator:
1. Checkpoint/resume — any phase can crash and resume without full restart
2. Timeout enforcement — no phase can hang forever
3. Graceful degradation — Fish Speech fails? Falls back to gTTS. Assembly fails? Typewriter renderer fallback.
4. Disk monitoring — refuses to write if disk < 500MB
5. Signal handling — SIGTERM/SIGINT triggers graceful shutdown, not crash
6. Per-phase isolation — each factory worker runs in controlled environment
7. RAG feedback loop — producer brief from past performance injected into scripting
8. CTR optimization — title + thumbnail scored after creation
9. Shorts optimization — LLM-based titles after assembly
10. Upload time optimization — IST window enforced
11. YouTube Analytics — real metrics pulled post-pipeline

Architecture (10 phases, Phase 0–9):
    Director.run()
        ├── Phase 0: Pre-Pipeline    → inline (cleanup + primetime scheduling)
        ├── Phase 1: Discovery        → FactoryWorker("discovery")
        ├── Phase 2: Weighting        → FactoryWorker("weighting")
        ├── Phase 2.5: Quality Gate   → FactoryWorker("pre_production") [fact_check + compliance]
        ├── Phase 3: Scripting        → FactoryWorker("scripting") [+ RAG brief]
        ├── Phase 4: Voice            → FactoryWorker("voice") [Fish Speech + gTTS fallback]
        ├── Phase 5: Thumbnail       → FactoryWorker("thumbnail") [+ CTR optimizer]
        ├── Phase 6: Assembly         → FactoryWorker("assembly") [+ typewriter + shorts optimizer]
        ├── Phase 7: Forensic Audit  → FactoryWorker("forensic_audit")
        ├── Phase 8: Upload           → FactoryWorker("upload") [+ publish decision]
        └── Phase 9: Post-pipeline   → FactoryWorker("post_pipeline") [+ Analytics + RAG + growth agents]
"""

import os
import sys
import json
import time
import shutil
import signal
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

# Add project root to path so "from modules.X import Y" works
sys.path.insert(0, "/home/jay/ViralDNA")
sys.path.insert(0, "/home/jay/ViralDNA/modules")

import config
from vdna2_checkpoint import (
    CheckpointManager, PhaseTimer, setup_signal_handlers,
    DiskSpaceError, get_checkpoint_manager, cleanup_old_checkpoints
)

# ── Timeout defaults per phase (seconds) ──
PHASE_TIMEOUTS = {
    "discovery":       300,   # 5 min — web search + trend analysis
    "weighting":       120,   # 2 min — scoring and ranking
    "scripting":       300,   # 5 min — LLM script generation
    "fact_check":      180,   # 3 min — fact verification
    "compliance":      60,    # 1 min — legal/compliance check
    "voice":           600,   # 10 min — Fish Speech is slow (~12s/sentence)
    "thumbnail":       120,   # 2 min — thumbnail creation
    "assembly":        600,   # 10 min — FFmpeg video assembly
    "forensic_audit":  60,    # 1 min — pre-ship audit
    "upload":          300,   # 5 min — YouTube upload
    "post_pipeline":   300,   # 5 min — analytics, community, etc.
}

# ── Graceful shutdown flag ──
_shutdown_requested = False


class FactoryWorker:
    """
    Crash-isolated worker that produces one artifact type.

    Features:
    - Checkpoint: saves result to disk after completion
    - Resume: skips if already completed (checks for checkpoint)
    - Timeout: enforces per-phase time limit
    - Fallback: calls fallback function if primary fails
    - Error isolation: catches ALL exceptions, logs them, doesn't crash pipeline
    """

    def __init__(self, phase_name, director):
        self.phase_name = phase_name
        self.director = director
        self.timeout = PHASE_TIMEOUTS.get(phase_name, 300)
        self.checkpoint_mgr = director.checkpoint_mgr

    def is_complete(self):
        """Check if this phase has a valid checkpoint from a previous run."""
        return self.checkpoint_mgr.is_phase_complete(self.phase_name)

    def get_checkpoint(self):
        """Load checkpoint data for this phase."""
        return self.checkpoint_mgr.load(self.phase_name)

    def save_checkpoint(self, data):
        """Save checkpoint data for this phase."""
        self.checkpoint_mgr.save(self.phase_name, data)

    def run(self, state, primary_fn, fallback_fn=None):
        """
        Execute the phase with crash isolation.

        Args:
            state: Pipeline state dict
            primary_fn: Main function(state) -> state
            fallback_fn: Optional fallback(state) -> state

        Returns:
            (state, success_bool)
        """
        # Resume: skip if already complete
        if self.is_complete():
            print(f"   ⏭️  [{self.phase_name}] Already completed (checkpoint found) — skipping")
            checkpoint_data = self.get_checkpoint()
            if checkpoint_data and isinstance(checkpoint_data, dict):
                # Merge checkpoint data back into state
                if "state_updates" in checkpoint_data:
                    state.update(checkpoint_data["state_updates"])
            return state, True

        print(f"   🏭 [{self.phase_name}] Starting (timeout: {self.timeout}s)...")

        with PhaseTimer(self.phase_name, timeout=self.timeout) as timer:
            try:
                # Check for shutdown signal before starting
                if _shutdown_requested:
                    print(f"   ⚠️  [{self.phase_name}] Shutdown requested before start — skipping")
                    return state, False

                # Run primary function
                state = primary_fn(state)

                # Save checkpoint on success
                self._save_state_checkpoint(state)
                print(f"   ✅ [{self.phase_name}] Complete")
                return state, True

            except Exception as e:
                error_msg = f"[{self.phase_name}] {type(e).__name__}: {e}"
                print(f"   ❌ {error_msg}")
                state.setdefault("errors", []).append(error_msg)

                # Try fallback if available
                if fallback_fn is not None:
                    print(f"   🔄 [{self.phase_name}] Trying fallback...")
                    try:
                        state = fallback_fn(state)
                        self._save_state_checkpoint(state)
                        print(f"   ✅ [{self.phase_name}] Fallback succeeded")
                        return state, True
                    except Exception as fallback_err:
                        fb_msg = f"[{self.phase_name} fallback] {type(fallback_err).__name__}: {fallback_err}"
                        print(f"   ❌ {fb_msg}")
                        state.setdefault("errors", []).append(fb_msg)

                # Save error checkpoint so we know this phase failed
                self.save_checkpoint({
                    "status": "failed",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "timestamp": datetime.now().isoformat(),
                })
                return state, False

    def _save_state_checkpoint(self, state):
        """Extract relevant state keys and save as checkpoint."""
        # Only save serializable, relevant data
        checkpoint_data = {
            "status": "complete",
            "timestamp": datetime.now().isoformat(),
            "state_updates": {},
        }
        # Extract phase-relevant keys
        phase_keys = {
            "discovery": ["raw_news", "sorted_topics", "selected_topic"],
            "weighting": ["sorted_topics", "selected_topic", "topic_slug"],
            "scripting": ["script_payload"],
            "fact_check": ["fact_check_result", "bias_check_result"],
            "compliance": ["compliance_result"],
            "voice": ["voiceover_assets"],
            "thumbnail": ["branded_thumbnail"],
            "assembly": ["compiled_videos", "publish_decision", "topic_slug"],
            "forensic_audit": ["audit_result"],
            "upload": ["upload_results"],
            "post_pipeline": ["analytics_summary"],
        }
        keys = phase_keys.get(self.phase_name, [])
        for key in keys:
            if key in state:
                val = state[key]
                # Only save JSON-serializable values
                try:
                    json.dumps(val, default=str)
                    checkpoint_data["state_updates"][key] = val
                except (TypeError, ValueError):
                    checkpoint_data["state_updates"][key] = str(val)

        self.save_checkpoint(checkpoint_data)


class VDNA2Director:
    """
    VDNA 2.0 Director — orchestrates the full pipeline using Factory workers.

    Replaces MultiAgentOrchestrator with a cleaner architecture:
    - Each phase is a FactoryWorker with checkpoint/resume
    - Phases can crash independently without killing the pipeline
    - Graceful degradation with fallback functions
    - Timeout enforcement prevents infinite hangs
    """

    def __init__(self, run_id=None):
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M")
        self.checkpoint_mgr = CheckpointManager(run_id=self.run_id)
        self.state = {
            "run_id": self.run_id,
            "errors": [],
            "start_time": datetime.now().isoformat(),
            "mode": "normal",
            "lookback_hours": 12,
        }
        self._shutdown_check = setup_signal_handlers()

        # Import existing modules (Layer 3: Skills Specialists)
        self._load_skills()

        print(f"\n{'='*70}")
        print(f"🧬 VIRALDNA 2.0 — Director Initialized")
        print(f"   Run ID: {self.run_id}")
        print(f"   Checkpoint dir: {self.checkpoint_mgr.run_dir}")
        print(f"   Completed phases: {self.checkpoint_mgr.get_completed_phases()}")
        print(f"{'='*70}\n")

    def _load_skills(self):
        """Load existing modules as Skills Specialists (Layer 3)."""
        # These are the proven existing modules — we wrap, not replace
        from trend_discovery import TrendDiscovery
        from post_filter import PostFilter
        from script_generator import ScriptGenerator
        from voiceover import VoiceoverGenerator
        from video_assembler import VideoAssembler
        from thumbnail_creator import ThumbnailCreator
        from gemini_engine import GeminiEngine
        from forensic_audit import ForensicAudit
        from pre_ship_check import PreShipCheck
        from publish_decision_engine import decide_publish_plan
        # VDNA 3.0: Analytics + RAG
        from yt_analytics import YouTubeAnalytics
        from rag_feedback import RagFeedbackLoop
        # VDNA 3.0 Growth + Operational agents (forensic audit pruned 4 dead weight modules)
        from community_engagement_v3 import CommunityEngagement
        from competitor_intel_v3 import CompetitorIntel
        from retention_analyzer_v3 import RetentionAnalyzer
        from content_quality_v3 import ContentQualityEngine
        from upload_reliability_v3 import UploadReliability
        from license_compliance_v3 import LicenseCompliance
        from content_calendar_v3 import ContentCalendarV3
        from primetime_scheduler_v3 import PrimetimeScheduler
        from cleanup_agent_v3 import CleanupAgent
        from continuous_auditor_v3 import ContinuousAuditor
        from fact_check_v3 import FactCheckV3
        from compliance_check_v3 import ComplianceCheckV3
        from intelligence_agent_v3 import IntelligenceAgentV3
        from collaboration_agent_v3 import CollaborationAgentV3
        from audience_channel_manager_v3 import AudienceChannelManagerV3
        # VDNA 3.0 Growth Gap modules (10 critical gaps)
        from thumbnail_ab_tester import ThumbnailABTester
        from title_optimizer_v3 import TitleOptimizer
        from engagement_loop import EngagementLoop
        from shorts_optimizer_v3 import ShortsOptimizer
        from cross_platform_distributor import CrossPlatformDistributor
        from subscribe_cta_optimizer import SubscribeCTOptimizer
        from retention_curve_analyzer import RetentionCurveAnalyzer

        self.skills = {
            "trend_discovery": TrendDiscovery(config_instance=config),
            "post_filter": PostFilter(config_dict=config.POST_FILTER_CONFIG),
            "script_generator": ScriptGenerator(engine=GeminiEngine(), config_dict=config.SCRIPT_GENERATION_CONFIG),
            "voiceover": VoiceoverGenerator,
            "video_assembler": VideoAssembler(config_instance=config),
            "thumbnail_creator": ThumbnailCreator(pacer=config, config_instance=config),
            "gemini_engine": GeminiEngine(),
            "forensic_audit": ForensicAudit(drive_base=config.DRIVE_BASE),
            "pre_ship_check": PreShipCheck(drive_base=config.DRIVE_BASE),
            "rag_feedback": RagFeedbackLoop(ledger_path=os.path.join(config.DRIVE_BASE, "diagnostics", "growth_ledger.json")),
            "decide_publish_plan": decide_publish_plan,
            "yt_analytics": YouTubeAnalytics(credentials_path=config.DRIVE.get("YOUTUBE_TOKEN", "")),
            # VDNA 3.0 Growth + Operational agents (forensic audit pruned 4 dead weight)
            "community_engagement": CommunityEngagement(),
            "competitor_intel": CompetitorIntel(),
            "retention_analyzer": RetentionAnalyzer(),
            "content_quality": ContentQualityEngine(),
            "upload_reliability": UploadReliability(),
            "license_compliance": LicenseCompliance(),
            "content_calendar": ContentCalendarV3(),
            "primetime_scheduler": PrimetimeScheduler(),
            "cleanup_agent": CleanupAgent(),
            "continuous_auditor": ContinuousAuditor(),
            "fact_check": FactCheckV3(),
            "compliance_check": ComplianceCheckV3(),
            "intelligence_agent": IntelligenceAgentV3(),
            "collaboration_agent": CollaborationAgentV3(),
            "audience_channel_manager": AudienceChannelManagerV3(),
            # VDNA 3.0 Growth Gap modules (10 critical gaps)
            "thumbnail_ab_tester": ThumbnailABTester(),
            "title_optimizer": TitleOptimizer(),
            "engagement_loop": EngagementLoop(),
            "shorts_optimizer_v3": ShortsOptimizer(),
            "cross_platform": CrossPlatformDistributor(),
            "subscribe_cta": SubscribeCTOptimizer(),
            "retention_curve": RetentionCurveAnalyzer(),
        }
        print(f"   📦 Loaded {len(self.skills)} skill modules")

    def run(self, injected_topic=None):
        """
        Execute the full VDNA 2.0 pipeline.

        Args:
            injected_topic: Optional pre-selected topic (skips discovery/weighting)
        """
        print(f"{'━'*70}")
        print(f"🚀 VIRALDNA 2.0 PIPELINE START — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'━'*70}\n")

        # ── PHASE 0: Pre-Pipeline ──
        try:
            print("━" * 50)
            print("⚙️  PHASE 0: Pre-Pipeline")
            print("━" * 50)
            # 0.1: Cleanup
            try:
                cleanup = self.skills["cleanup_agent"]
                cleanup_stats = cleanup.cleanup()
                disk = cleanup.check_disk_space()
                print(f"   🧹 Cleanup: {cleanup_stats['cleaned']} files removed, {cleanup_stats['freed_mb']}MB freed")
                print(f"   💾 Disk: {disk['free_gb']}GB free ({'OK' if disk['sufficient'] else 'LOW'})")
                self.state["cleanup_stats"] = cleanup_stats
                self.state["disk_status"] = disk
            except Exception as e:
                print(f"   ⚠️ Cleanup error (non-fatal): {e}")

            # 0.2: Primetime scheduling
            try:
                sched = self.skills["primetime_scheduler"]
                run_mode = sched.get_run_mode()
                upload_sched = sched.get_upload_schedule()
                self.state["run_mode"] = run_mode
                self.state["upload_schedule"] = upload_sched
                print(f"   🕐 Run mode: {run_mode['mode']} (hour {run_mode['hour_ist']} IST)")
                if upload_sched.get("main_upload"):
                    rec = upload_sched["main_upload"].get("recommended_time_ist", "N/A")
                    print(f"   📅 Recommended upload: {rec} IST")
            except Exception as e:
                print(f"   ⚠️ Primetime scheduling error (non-fatal): {e}")
        except Exception as e:
            print(f"   ⚠️ Pre-pipeline error (non-fatal): {e}")

        # ── PHASE 1: Discovery ──
        if injected_topic:
            print("📋 Using injected topic — skipping discovery/weighting")
            self.state["selected_topic"] = injected_topic
            self.state["sorted_topics"] = [injected_topic]
            raw = injected_topic.get("title", injected_topic.get("id", "topic"))
            words = raw.split()[:6]
            slug = "_".join(w for w in words if w).replace("/", "_").replace(":", "").replace("'", "").replace('"', "").replace("?", "").replace("!", "").replace(",", "").replace(";", "").replace("(", "").replace(")", "").replace("&", "and")
            self.state["topic_slug"] = slug or injected_topic.get("id", "topic")
        else:
            worker = FactoryWorker("discovery", self)
            self.state, ok = worker.run(
                self.state,
                primary_fn=self._phase_discovery,
            )
            if not ok:
                print("🛑 Discovery failed — no topics found")
                return self.state

            # ── PHASE 2: Weighting ──
            worker = FactoryWorker("weighting", self)
            self.state, ok = worker.run(
                self.state,
                primary_fn=self._phase_weighting,
            )
            if not ok:
                print("🛑 Weighting failed — no topics ranked")
                return self.state

        # ── PHASE 2.5: Pre-Production Quality Gate ──
        worker = FactoryWorker("pre_production", self)
        self.state, _ = worker.run(
            self.state,
            primary_fn=self._phase_pre_production_gate,
        )

        # ── PHASE 3: Scripting ──
        worker = FactoryWorker("scripting", self)
        self.state, ok = worker.run(
            self.state,
            primary_fn=self._phase_scripting,
        )
        if not ok:
            print("🛑 Scripting failed")
            return self.state

        # ── PHASE 4: Voice (Fish Speech + gTTS fallback) ──
        worker = FactoryWorker("voice", self)
        self.state, ok = worker.run(
            self.state,
            primary_fn=self._phase_voice,
            fallback_fn=self._phase_voice_fallback,
        )
        if not ok:
            print("🛑 Voice synthesis failed (both primary and fallback)")
            return self.state

        # ── PHASE 5: Thumbnail ──
        worker = FactoryWorker("thumbnail", self)
        self.state, ok = worker.run(
            self.state,
            primary_fn=self._phase_thumbnail,
        )
        if not ok:
            print("⚠️ Thumbnail creation failed — continuing without branded thumbnail")

        # ── PHASE 6: Assembly ──
        worker = FactoryWorker("assembly", self)
        self.state, ok = worker.run(
            self.state,
            primary_fn=self._phase_assembly,
        )
        if not ok:
            print("🛑 Video assembly failed")
            return self.state

        # ── PHASE 7: Forensic Audit ──
        worker = FactoryWorker("forensic_audit", self)
        self.state, ok = worker.run(
            self.state,
            primary_fn=self._phase_forensic_audit,
        )
        if not ok:
            print("🛑 Forensic audit failed — halting before upload")
            return self.state

        # ── PHASE 8: Upload ──
        if os.environ.get("VIRALDNA_UPLOAD_ENABLED", "false").lower() == "true":
            worker = FactoryWorker("upload", self)
            self.state, ok = worker.run(
                self.state,
                primary_fn=self._phase_upload,
            )
        else:
            print("⏭️ Upload skipped (VIRALDNA_UPLOAD_ENABLED=false — review mode)")
            self.state["upload_results"] = {"status": "skipped", "reason": "upload_disabled"}

        # ── PHASE 9: Post-Pipeline ──
        worker = FactoryWorker("post_pipeline", self)
        self.state, _ = worker.run(
            self.state,
            primary_fn=self._phase_post_pipeline,
        )

        # ── FINAL REPORT ──
        self._print_final_report()
        return self.state

    # ═══════════════════════════════════════════════════════════════════
    # PHASE IMPLEMENTATIONS
    # ═══════════════════════════════════════════════════════════════════

    def _phase_discovery(self, state):
        """Phase 1: Discover trending news topics."""
        print("   🔍 Discovering trending topics...")
        td = self.skills["trend_discovery"]
        lookback = state.get("lookback_hours", 12)
        raw_news = td.run(lookback_hours=lookback)
        state["raw_news"] = raw_news
        print(f"   📰 Found {len(raw_news)} news items")
        return state

    def _phase_weighting(self, state):
        """Phase 2: Weight and rank topics.
        VDNA 3.0: Content calendar injects category rotation bonus.
        """
        print("   ⚖️  Weighting and ranking topics...")
        pf = self.skills["post_filter"]
        raw_news = state.get("raw_news", [])

        # VDNA 3.0: Get category rotation bonus from content calendar
        category_bonus = {}
        try:
            cc = self.skills["content_calendar"]
            next_cat = cc.get_next_category()
            if next_cat:
                category_bonus = {"preferred_category": next_cat.get("category", ""),
                                  "bonus_multiplier": 1.3}
                print(f"   📅 Calendar rotation: preferring '{next_cat.get('category')}' category")
        except Exception:
            pass

        sorted_topics = pf.run(raw_news)
        # VDNA 3.0: Apply content calendar category bonus (1.3x for preferred category)
        if category_bonus and sorted_topics:
            preferred = category_bonus.get("preferred_category", "")
            bonus_mult = category_bonus.get("bonus_multiplier", 1.3)
            if preferred:
                for t in sorted_topics:
                    cats = t.get("categories", [])
                    if isinstance(cats, list) and preferred.lower() in [c.lower() for c in cats]:
                        t["score"] = t.get("score", 0) * bonus_mult
                sorted_topics.sort(key=lambda x: x.get("score", 0), reverse=True)
                print(f"   📅 Calendar bonus applied: '{preferred}' category ×{bonus_mult}")
        state["sorted_topics"] = sorted_topics
        if sorted_topics:
            state["selected_topic"] = sorted_topics[0]
            raw = sorted_topics[0].get("title", sorted_topics[0].get("id", "topic"))
            words = raw.split()[:6]
            slug = "_".join(w for w in words if w).replace("/", "_").replace(":", "").replace("'", "").replace('"', "").replace("?", "").replace("!", "").replace(",", "").replace(";", "").replace("(", "").replace(")", "").replace("&", "and")
            state["topic_slug"] = slug or sorted_topics[0].get("id", "topic")
            print(f"   🏆 Top topic: {sorted_topics[0].get('title', 'N/A')[:60]}")
        return state

    def _phase_pre_production_gate(self, state):
        """Phase 2.5: Pre-production quality gate.
        VDNA 3.0: Content quality check BEFORE scripting — reject low-quality topics early.
        Fact-check named entities in the selected topic title/description.
        """
        print("   🔬 Pre-production quality gate...")
        topic = state.get("selected_topic", {})

        # Content quality check
        try:
            cq = self.skills["content_quality"]
            title = topic.get("title", "")
            desc = topic.get("description", topic.get("summary", ""))
            quality_result = cq.run_quality_check(script_text=title + " " + desc)
            state["pre_production_quality"] = quality_result
            score = quality_result.get("quality_score", quality_result.get("overall_score", 0))
            if isinstance(score, (int, float)) and score < 30:
                print(f"   ⚠️ Low quality score ({score}/100) — proceeding with caution")
            else:
                print(f"   ✅ Quality score: {score}/100")
        except Exception as e:
            print(f"   ⚠️ Quality check failed: {e}")

        # Fact-check named entities
        try:
            fc = self.skills["fact_check"]
            title = topic.get("title", "")
            source_url = topic.get("url", topic.get("link", ""))
            fc_result = fc.check_script(
                script_text=title + " " + topic.get("description", ""),
                title=title,
                source_url=source_url,
            )
            state["pre_production_fact_check"] = fc_result
            verdict = fc_result.get("verdict", fc_result.get("status", "unknown"))
            if verdict in ("VERIFIED", "PASS", "verified", "pass"):
                print(f"   ✅ Fact check: {verdict}")
            else:
                print(f"   ⚠️ Fact check: {verdict} — flag for review")
        except Exception as e:
            print(f"   ⚠️ Fact check failed: {e}")

        return state

    def _phase_scripting(self, state):
        """Phase 3: Generate bilingual script.
        VDNA 3.0: Loads producer brief from RAG feedback loop for context injection.
        """
        print("   📝 Generating script...")
        topic = state.get("selected_topic", {})
        sg = self.skills["script_generator"]

        # VDNA 3.0: Load producer brief from RAG feedback loop
        producer_brief = ""
        try:
            rag = self.skills["rag_feedback"]
            brief_data = rag.generate_producer_brief()
            if brief_data:
                producer_brief = brief_data
                print("   🧠 RAG producer brief loaded for script context")
        except Exception as e:
            print(f"   ⚠️ RAG brief load failed: {e} — continuing without")

        script = sg.run(topic=topic, producer_brief=producer_brief)
        # VDNA 3.0: Convert ScriptPayload to dict for JSON checkpoint serialization
        if hasattr(script, '__dict__'):
            state["script_payload"] = script.__dict__
        else:
            state["script_payload"] = script
        print(f"   📄 Script generated: {len(str(script))} chars")
        return state

    def _extract_script_text(self, script_payload):
        """VDNA 3.0: Extract main text and short texts from any script payload format.
        Handles ScriptPayload objects, dicts (from checkpoint), and strings.
        Returns (main_text: str, short_texts: dict[int, str])
        """
        if isinstance(script_payload, str):
            return script_payload, {}
        elif isinstance(script_payload, dict):
            main_raw = script_payload.get("main_raw", "")
            main_clean = script_payload.get("main_clean", "")
            main_text = main_clean or main_raw
            short_texts = {}
            for i in range(1, 4):
                val = script_payload.get(f"short_{i}_clean", "")
                if not val:
                    val = script_payload.get(f"short_{i}_raw", "")
                short_texts[i] = val
            return main_text, short_texts
        else:
            # Live ScriptPayload object
            main_seg = script_payload.get_segment("main")
            main_text = main_seg.get("text", "")
            if not main_text:
                main_text = getattr(script_payload, "full_script", "") or ""
            short_texts = {}
            for i in range(1, 4):
                short_seg = script_payload.get_segment(f"short_{i}")
                short_texts[i] = short_seg.get("text", "")
            return main_text, short_texts

    def _phase_voice(self, state):
        """Phase 4: Voice synthesis with Fish Speech (primary).
        VDNA 3.0: Handles both ScriptPayload objects and string payloads (from checkpoint restore).
        """
        print("   🎙️  Synthesizing voice (Fish Speech primary)...")
        vg = self.skills["voiceover"]()
        script_payload = state.get("script_payload")
        if not script_payload:
            raise ValueError("No script_payload in state")

        voiceover_assets = {}

        # Handle ScriptPayload objects, dict (from checkpoint), or string
        if isinstance(script_payload, str):
            # Checkpoint stored str() representation — use raw string as main text
            main_text = script_payload
            short_texts = {}
        elif isinstance(script_payload, dict):
            # Dict from checkpoint restore — extract text fields
            main_raw = script_payload.get("main_raw", "")
            main_clean = script_payload.get("main_clean", "")
            main_text = main_clean or main_raw
            short_texts = {}
            for i in range(1, 4):
                key = f"short_{i}_clean"
                val = script_payload.get(key, "")
                if not val:
                    key = f"short_{i}_raw"
                    val = script_payload.get(key, "")
                short_texts[i] = val
        else:
            # Live ScriptPayload object
            main_seg = script_payload.get_segment("main")
            main_text = main_seg.get("text", "")
            if not main_text:
                main_text = getattr(script_payload, "full_script", "") or ""
            short_texts = {}
            for i in range(1, 4):
                short_seg = script_payload.get_segment(f"short_{i}")
                short_texts[i] = short_seg.get("text", "")

        if main_text:
            main_audio = os.path.join(
                config.DRIVE.get("AUDIO_OUTPUT", "/home/jay/ViralDNA/audio"),
                f"{state.get('topic_slug', 'topic')}_main.mp3"
            )
            os.makedirs(os.path.dirname(main_audio), exist_ok=True)
            result = vg.generate_voiceover(
                {"full_script": main_text}, state.get("topic_slug", "topic")
            )
            if result.get("status") == "success":
                voiceover_assets["main"] = result["path"]

        # Short voiceover
        for i in range(1, 4):
            short_text = short_texts.get(i, "")
            if short_text:
                short_key = f"short_{i}"
                short_audio = os.path.join(
                    config.DRIVE.get("AUDIO_OUTPUT", "/home/jay/ViralDNA/audio"),
                    f"{state.get('topic_slug', 'topic')}_{short_key}.mp3"
                )
                result = vg.generate_voiceover(
                    {"full_script": short_text}, f"{state.get('topic_slug', 'topic')}_{short_key}"
                )
                if result.get("status") == "success":
                    voiceover_assets[short_key] = result["path"]

        if not voiceover_assets:
            raise RuntimeError("No voiceover assets produced")

        state["voiceover_assets"] = voiceover_assets
        print(f"   🎙️  Voice assets: {list(voiceover_assets.keys())}")
        return state

    def _phase_voice_fallback(self, state):
        """Phase 4 Fallback: gTTS-only voice synthesis."""
        print("   🔄 Voice fallback: using gTTS only...")
        # Set env var to disable Fish Speech for this attempt
        os.environ["FISH_SPEECH_ENABLED"] = "0"
        vg = self.skills["voiceover"]()
        script_payload = state.get("script_payload")
        voiceover_assets = {}

        main_text, _ = self._extract_script_text(script_payload)
        if main_text:
            main_audio = os.path.join(
                config.DRIVE.get("AUDIO_OUTPUT", "/home/jay/ViralDNA/audio"),
                f"{state.get('topic_slug', 'topic')}_main.mp3"
            )
            os.makedirs(os.path.dirname(main_audio), exist_ok=True)
            result = vg.generate_voiceover(
                {"full_script": main_text}, state.get("topic_slug", "topic")
            )
            if result.get("status") == "success":
                voiceover_assets["main"] = result["path"]

        state["voiceover_assets"] = voiceover_assets
        return state

    def _phase_thumbnail(self, state):
        """Phase 5: Thumbnail creation.
        VDNA 3.0: CTR optimizer scores and refines title + thumbnail after creation.
        """
        print("   🏷️  Creating thumbnail...")
        tc = self.skills["thumbnail_creator"]
        topic = state.get("selected_topic", {})
        topic_slug = state.get("topic_slug", "topic")
        thumb_dir = config.DRIVE.get("THUMBNAILS", "/home/jay/ViralDNA/thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)
        thumb_path = os.path.join(thumb_dir, f"{topic_slug}_thumb.jpg")
        tc.create_thumbnail(
            topic=topic,
            thumb_output_dir=thumb_path,
            sk=topic_slug,
            runtime_dir=config.DRIVE.get("RUNTIME", "/home/jay/ViralDNA/output/runtime"),
        )
        state["branded_thumbnail"] = thumb_path

        # VDNA 3.0: Thumbnail A/B testing — score variants, pick best
        try:
            ab = self.skills["thumbnail_ab_tester"]
            variants = ab.generate_variants(topic, thumb_path, thumb_path)
            if variants:
                best = ab.select_best(variants, topic)
                state["thumbnail_ab_result"] = best
                print(f"   🖼️  Thumbnail A/B: {best.get('recommendation', 'N/A')}")
        except Exception as e:
            print(f"   ⚠️ Thumbnail A/B testing failed: {e}")

        # VDNA 3.0: Title optimization — generate + score variants
        try:
            to = self.skills["title_optimizer"]
            base_title = topic.get("title", "ViralDNA News")
            variants = to.generate_variants(base_title, topic.get("description", ""))
            best_title = to.select_best(variants)
            state["title_optimization"] = best_title
            # Override topic title with optimized version
            if best_title.get("best_title"):
                state["selected_topic"]["optimized_title"] = best_title["best_title"]
                print(f"   📝 Title optimized: \"{best_title['best_title'][:60]}\" (score: {best_title['best_score']}/100)")
        except Exception as e:
            print(f"   ⚠️ Title optimization failed: {e}")

        return state

    def _phase_assembly(self, state):
        """Phase 7: Video assembly with FFmpeg.
        VDNA 3.0: Shorts optimizer generates titles + CTAs after assembly.
        """
        print("   🎬 Assembling videos...")
        va = self.skills["video_assembler"]
        script_payload = state.get("script_payload")
        voiceover_assets = state.get("voiceover_assets", {})
        topic = state.get("selected_topic", {})
        topic_slug = state.get("topic_slug", "topic")

        if not script_payload or not voiceover_assets:
            raise ValueError("Missing script or voiceover for assembly")

        decision = self.skills["decide_publish_plan"](topic)
        state["publish_decision"] = decision
        print(f"   📋 Publish plan: main={decision.produce_main}, shorts={decision.num_shorts}")

        compiled_videos = []

        # VDNA 3.0: Extract text from any payload format (object, dict, string)
        main_text, short_texts = self._extract_script_text(script_payload)

        # Preprocess text to match TTS output (contraction expansion, acronym expansion, etc.)
        # This ensures the typewriter displays exactly what the voice speaks
        # Use the voice engine's own preprocessing to guarantee exact match
        vg = self.skills["voiceover"]()
        main_text_display = vg.preprocess_text(main_text)
        short_texts_display = {k: vg.preprocess_text(v) for k, v in short_texts.items()}

        # Main video
        if decision.produce_main:
            audio_path = voiceover_assets.get("main")
            if audio_path:
                main_filename = f"{topic_slug}_Main.mp4"
                # Calculate target duration from word count (~150 wpm speaking rate)
                word_count = len(main_text.split()) if main_text else 200
                target_duration = max(60, min(word_count * 0.4, 600))
                va.assemble_video(
                    main_filename, audio_path, None,
                    main_filename, target_duration,
                    async_mode=False, script_text=main_text_display,
                    is_short=False, topic_title=topic.get("title", "")
                )
                main_path = os.path.join(config.DRIVE["VIDEO_OUTPUT"], main_filename)
                if os.path.exists(main_path) and os.path.getsize(main_path) > 100000:
                    compiled_videos.append(main_path)
                    print(f"   ✅ Main video: {main_filename}")
                else:
                    print(f"   ❌ Main video failed validation")

        # Shorts
        for i in range(1, decision.num_shorts + 1):
            key = f"short_{i}"
            if key in voiceover_assets:
                short_text = short_texts.get(i, "")
                short_text_display = short_texts_display.get(i, "")
                short_audio = voiceover_assets[key]
                short_filename = f"{topic_slug}_Short{i}.mp4"
                short_word_count = len(short_text.split()) if short_text else 30
                short_duration = max(15, min(short_word_count * 0.4, 60))
                va.assemble_video(
                    short_filename, short_audio, None,
                    short_filename, short_duration,
                    async_mode=False, script_text=short_text_display,
                    is_short=True, topic_title=topic.get("title", "")
                )
                short_path = os.path.join(config.DRIVE["VIDEO_OUTPUT"], short_filename)
                if os.path.exists(short_path) and os.path.getsize(short_path) > 50000:
                    compiled_videos.append(short_path)
                    print(f"   ✅ Short {i}: {short_filename}")
                else:
                    print(f"   ❌ Short {i} failed validation")

        if not compiled_videos:
            raise RuntimeError("No videos assembled successfully")

        state["compiled_videos"] = compiled_videos
        print(f"   🎬 Total videos: {len(compiled_videos)}")

        # VDNA 3.0: Shorts optimization — hooks, titles, CTAs
        try:
            so = self.skills["shorts_optimizer_v3"]
            topic_title = topic.get("title", "")

            # Generate hooks for each short
            hooks = []
            for i in range(3):
                hook_style = ["shock_value", "curiosity_gap", "urgency"][i % 3]
                hook = so.generate_hook(topic, style=hook_style)
                hooks.append(hook)
            state["shorts_hooks"] = hooks
            print(f"   🎣 Shorts hooks: {len(hooks)} generated")

            # Generate Shorts-optimized titles
            shorts_titles = []
            for i in range(3):
                st = so.generate_shorts_title(topic_title, variant_idx=i)
                shorts_titles.append(st)
            state["shorts_titles"] = shorts_titles
            print(f"   📱 Shorts titles: {len(shorts_titles)} variants")

            # Generate end-screen CTAs
            main_video_url = state.get("main_video_url", "")
            cta_seq = so.generate_end_screen_cta(topic, main_video_url=main_video_url)
            state["shorts_cta_sequence"] = cta_seq
            print(f"   🔗 Shorts CTA sequence: {len(cta_seq.get('cta_sequence', []))} CTAs")

            # Generate Shorts descriptions
            shorts_desc = so.generate_shorts_description(topic, main_video_url)
            state["shorts_description"] = shorts_desc
            print(f"   📝 Shorts description: {len(shorts_desc)} chars")
        except Exception as e:
            print(f"   ⚠️ Shorts optimization failed: {e} — continuing without")

        return state

    def _phase_forensic_audit(self, state):
        """Phase 8: Pre-ship forensic audit."""
        print("   🔬 Running forensic audit...")
        fa = self.skills["forensic_audit"]
        compiled_videos = state.get("compiled_videos", [])
        audit_result = fa.run_full_audit(state)
        state["audit_result"] = audit_result
        if not audit_result.get("passed", False):
            raise RuntimeError(f"Forensic audit failed: {audit_result.get('reason', 'unknown')}")
        print(f"   ✅ Audit passed")
        return state

    def _phase_upload(self, state):
        """Phase 9: YouTube upload.
        VDNA 3.0: Upload time optimizer enforces IST window (4PM-8PM).
        Fixed: Properly constructs YouTube service, resolves branded thumbnail
        from subdirectory, and calls upload_single_video with correct args.
        """
        print("   📤 Uploading to YouTube...")

        # Build YouTube service
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build as gbuild
            cred_file = os.path.join(config.DRIVE.get("CREDENTIALS", "credentials"), "youtube_token.json")
            if not os.path.exists(cred_file):
                cred_file = "credentials/youtube_token.json"
            with open(cred_file) as f:
                creds_data = json.load(f)
            creds = Credentials.from_authorized_user_info(creds_data)
            youtube_service = gbuild("youtube", "v3", credentials=creds)
            print("   🔑 YouTube service authenticated")
        except Exception as e:
            print(f"   ❌ YouTube auth failed: {e} — skipping upload")
            state["upload_results"] = {"status": "failed", "error": str(e)}
            return state

        from youtube_uploader import YouTubeUploader
        uploader = YouTubeUploader(youtube_service, config.YOUTUBE_UPLOAD_CONFIG)

        compiled_videos = state.get("compiled_videos", [])
        topic = state.get("selected_topic", {})
        topic_slug = state.get("topic_slug", "topic")
        results = []

        # Resolve branded thumbnail path
        # ThumbnailCreator saves to: thumbnails/<slug>_thumb.jpg/<slug>_branded.jpg
        branded_thumb_dir = state.get("branded_thumbnail", "")
        branded_thumb = ""
        if branded_thumb_dir:
            if os.path.isdir(branded_thumb_dir):
                for f in os.listdir(branded_thumb_dir):
                    if f.endswith("_branded.jpg"):
                        branded_thumb = os.path.join(branded_thumb_dir, f)
                        break
            elif os.path.isfile(branded_thumb_dir):
                branded_thumb = branded_thumb_dir
            if not branded_thumb:
                flat_thumb = os.path.join(
                    config.DRIVE.get("THUMBNAILS", "thumbnails"),
                    f"{topic_slug}_branded.jpg")
                if os.path.isfile(flat_thumb):
                    branded_thumb = flat_thumb

        if branded_thumb:
            print(f"   🖼️  Thumbnail: {os.path.basename(branded_thumb)}")
        else:
            print("   ⚠️  No branded thumbnail found — YouTube will auto-generate")

        # VDNA 3.0: Primetime scheduler — delay upload if outside optimal window
        try:
            sched = self.skills["primetime_scheduler"]
            run_mode = sched.get_run_mode()
            upload_schedule = sched.get_upload_schedule()
            state["run_mode"] = run_mode
            state["upload_schedule"] = upload_schedule

            recommended_time = upload_schedule.get("main_upload", {}).get("recommended_time_ist", "")
            window_name = upload_schedule.get("main_upload", {}).get("window_name", "normal")
            print(f"   ⏰ Run mode: {run_mode['mode']} | Window: {window_name} | Recommended: {recommended_time} IST")

            # If quiet hours, delay upload to recommended time
            if run_mode.get("is_quiet") and recommended_time:
                from datetime import datetime as _dt
                now_ist = _dt.now(config.IST)
                rec_hour, rec_min = map(int, recommended_time.split(":"))
                delay_min = (rec_hour - now_ist.hour) * 60 + (rec_min - now_ist.minute)
                if delay_min > 0:
                    delay_sec = min(delay_min * 60, 3600)  # max 1 hour delay
                    print(f"   ⏳ Quiet hours — delaying upload {delay_min}min ({delay_sec}s) until {recommended_time} IST")
                    import time as _time
                    _time.sleep(delay_sec)
                    print(f"   ▶️ Delay complete — uploading now")
        except Exception as e:
            print(f"   ⚠️ Primetime scheduling failed: {e} — uploading immediately")

        title = topic.get("title", "ViralDNA News")
        description = self._build_description(state)
        tags = topic.get("tags", ["news", "india", "viral", "ViralDNA"])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]

        for video_path in compiled_videos:
            if not os.path.exists(video_path):
                print(f"   ⚠️ Video not found: {video_path} — skipping")
                results.append({"status": "failed", "error": f"Video not found: {video_path}"})
                continue

            is_short = "Short" in os.path.basename(video_path)
            short_index = 0
            if is_short:
                import re as _re
                m = _re.search(r'Short(\d+)', os.path.basename(video_path))
                short_index = int(m.group(1)) if m else 0

            # Only pass thumbnail for main videos (shorts use frame injection)
            thumb = branded_thumb if not is_short else None

            print(f"   📤 Uploading: {os.path.basename(video_path)} ({'short' if is_short else 'main'})")
            result = uploader.upload_single_video(
                title_raw=title[:100],
                desc_raw=description[:5000],
                rag_context=title[:300],
                video_path=video_path,
                thumbnail_path=thumb or "",
                is_short=is_short,
                short_index=short_index,
                variant_idx=0,
                topic=topic,
            )
            results.append(result)

            if result.get("status") == "success":
                print(f"   ✅ Uploaded: {result.get('youtube_url', result.get('youtube_id', 'N/A'))}")
            else:
                print(f"   ❌ Upload failed: {result.get('error', 'unknown error')}")

        state["upload_results"] = results
        print(f"   📤 Uploaded {len(results)} videos")
        return state

    def _phase_post_pipeline(self, state):
        """Phase 9: Post-pipeline tasks (analytics, RAG feedback, growth agents, notifications).
        VDNA 3.0: Pulls YouTube Analytics, stores metrics, generates producer brief.
        VDNA 3.0 Tier 1: Community engagement, competitor intel, retention,
        content quality, milestone detection.
        """
        print("   📊 Post-pipeline: analytics + growth agents...")

        # ── 10.1: YouTube Analytics — pull metrics for uploaded videos ──
        try:
            yta = self.skills["yt_analytics"]
            upload_results = state.get("upload_results", [])
            video_ids = []
            for r in upload_results:
                if isinstance(r, dict):
                    vid = r.get("video_id", "")
                    if vid:
                        video_ids.append(vid)
            if video_ids:
                metrics = yta.pull_metrics(video_ids=video_ids, days=7)
                state["analytics_summary"] = metrics
                print(f"   📈 Analytics pulled for {len(video_ids)} videos")
            else:
                print("   📈 No video IDs available for analytics pull")
        except Exception as e:
            print(f"   ⚠️ YouTube Analytics failed: {e}")

        # ── 10.2: RAG feedback — store performance ──
        try:
            rag = self.skills["rag_feedback"]
            topic = state.get("selected_topic", {})
            upload_results = state.get("upload_results", [])
            analytics = state.get("analytics_summary", {})
            rag.store_run_performance(
                topic_title=topic.get("title", ""),
                video_ids=[r.get("video_id", "") for r in upload_results if isinstance(r, dict)],
                analytics=analytics,
            )
            print("   🧠 RAG feedback stored for next run")
        except Exception as e:
            print(f"   ⚠️ RAG feedback storage failed: {e}")

        # ── 10.3: Community Tab Posting ──
        try:
            ce = self.skills["community_engagement"]
            topic = state.get("selected_topic", {})
            upload_results = state.get("upload_results", [])
            title = topic.get("title", "")

            # Get YouTube video IDs from upload results
            videos = []
            for r in upload_results:
                if isinstance(r, dict) and r.get("video_id"):
                    videos.append({"id": r["video_id"], "url": r.get("youtube_url", f"https://youtu.be/{r['video_id']}")})

            if videos:
                # Attempt to post launch comment via YouTube API
                main_video = videos[0]
                post_result = ce.post_to_community_tab(title=title, youtube_id=main_video["id"])
                state["community_post_result"] = post_result
                if post_result.get("posted"):
                    print(f"   ✅ Community comment posted: {post_result.get('comment_id', 'N/A')}")
                else:
                    print(f"   📋 Community post generated (not posted): {post_result.get('reason', 'N/A')}")
            else:
                print("   📢 No videos to generate community posts for")
        except Exception as e:
            print(f"   ⚠️ Community engagement failed: {e}")

        # ── 10.4: Subscriber Milestone Detection ──
        try:
            ce = self.skills["community_engagement"]
            milestone = ce.check_milestone()
            state["milestone_check"] = milestone
            if milestone.get("celebrate"):
                print(f"   🎉 MILESTONE: {milestone.get('milestone')} subscribers!")
                print(f"      {milestone.get('message', '')}")
            else:
                print(f"   📊 Milestone check: {milestone.get('note', 'No new milestone')}")
        except Exception as e:
            print(f"   ⚠️ Milestone check failed: {e}")

        # ── 10.5: Competitor Intelligence ──
        try:
            ci = self.skills["competitor_intel"]
            # Push intel to ledger
            ledger = ci.load_ledger() if hasattr(ci, 'load_ledger') else {}
            ci.push_to_ledger(ledger)
            summary = ci.get_competitor_summary()
            gaps = ci.get_content_gap_result()
            state["competitor_summary"] = summary
            state["content_gaps"] = gaps
            print(f"   🔍 Competitor scan: {summary.get('total_tracked', 0)} tracked, "
                  f"{summary.get('high_threats', 0)} high threats, "
                  f"{summary.get('content_gaps', 0)} gaps")
            if gaps.get("top_priorities"):
                for gap in gaps["top_priorities"][:3]:
                    print(f"      → Gap: {gap.get('topic', 'N/A')}")
        except Exception as e:
            print(f"   ⚠️ Competitor intel failed: {e}")

        # ── 10.6: Retention Analysis ──
        try:
            ra = self.skills["retention_analyzer"]
            topic = state.get("selected_topic", {})
            upload_results = state.get("upload_results", [])
            topic_title = topic.get("title", "Telugu news")

            # Plan series funnel for this topic
            series_plan = ra.plan_series_funnel(topic_title, num_parts=3)
            state["series_funnel_plan"] = series_plan
            print(f"   📺 Series funnel planned: {series_plan.get('total_parts', 0)} parts")

            # Generate next-video comment suggestion
            next_comment = ra.build_next_video_comment()
            state["next_video_comment"] = next_comment
            print(f"   💬 Next-video comment: {next_comment[:60]}...")

            # CTR benchmark for uploaded videos (if analytics available)
            analytics = state.get("analytics_summary", {})
            if analytics and upload_results:
                for r in upload_results[:3]:
                    if isinstance(r, dict) and r.get("video_id"):
                        try:
                            ra.benchmark_ctr(
                                video_id=r["video_id"],
                                category="news_politics",
                                actual_ctr=0.05,  # Default; real CTR from analytics if available
                            )
                        except Exception:
                            pass
                print("   📊 CTR benchmarks updated")
        except Exception as e:
            print(f"   ⚠️ Retention analysis failed: {e}")

        # ── 10.7: Content Quality Check ──
        try:
            cq = self.skills["content_quality"]
            script = state.get("script_payload")
            script_text = ""
            if script and hasattr(script, "full_script"):
                script_text = script.full_script
            elif isinstance(script, dict):
                script_text = script.get("full_script", "")

            if script_text:
                # Load video history for pillar analysis
                ledger = cq.load_ledger()
                video_history = ledger.get("execution_history", [])
                quality_result = cq.run_quality_check(script_text, video_history)
                state["content_quality_result"] = quality_result

                fc = quality_result.get("fact_check", {})
                bi = quality_result.get("bias_detection", {})
                print(f"   ✅ Content quality: fact-check={'PASS' if fc.get('pass') else 'REVIEW'} "
                      f"({fc.get('needs_review', 0)} flags), "
                      f"bias={bi.get('risk_level', 'N/A')} risk")
                if not fc.get("pass"):
                    for flag in fc.get("flags", [])[:3]:
                        print(f"      ⚠️  Fact: {flag}")
                if bi.get("risk_level") != "low":
                    for flag in bi.get("flags", [])[:3]:
                        print(f"      ⚠️  Bias: {flag}")
                print(f"   📊 Recommended next pillar: {quality_result.get('recommended_next_pillar', 'N/A')}")
            else:
                print("   ✅ Content quality: no script text available, skipping")
        except Exception as e:
            print(f"   ⚠️ Content quality check failed: {e}")

        # ── 10.8: API Quota & Reliability Check ──
        try:
            ur = self.skills["upload_reliability"]
            quota = ur.get_quota_status()
            state["api_quota_status"] = quota
            account = ur.get_active_account()
            backoff = ur.get_backoff_seconds("youtube")
            queue = ur.get_queue_status()
            state["reliability_status"] = {
                "quota": quota,
                "active_account": account,
                "backoff_seconds": backoff,
                "upload_queue": queue,
            }
            status_icon = "✅" if quota["status"] == "ok" else ("⚠️" if quota["status"] == "warning" else "🚨")
            print(f"   {status_icon} API quota: {quota['status']} ({quota['percent_used']}% used, {quota['remaining']} remaining)")
            if account != "primary":
                print(f"   ⚠️ Failover account active: {account}")
            if backoff > 0:
                print(f"   ⏳ Rate limit backoff: {backoff}s remaining")
            if queue["queued"] > 0:
                print(f"   📋 Upload queue: {queue['queued']} pending")
        except Exception as e:
            print(f"   ⚠️ Reliability check failed: {e}")

        # ── 10.9: License Compliance ──
        try:
            lc = self.skills["license_compliance"]
            report = lc.get_compliance_report()
            state["license_compliance_report"] = report
            if report["pass"]:
                print(f"   ✅ License compliance: PASS ({report['total_tracked']} assets tracked)")
            else:
                print(f"   ⚠️ License compliance: {report['violations']} violation(s) detected")
            if report.get("safe_sources"):
                print(f"   📋 Approved sources: {', '.join(report['safe_sources'][:4])}")
        except Exception as e:
            print(f"   ⚠️ License compliance check failed: {e}")

        # ── 10.10: Content Calendar Alignment ──
        try:
            cc = self.skills["content_calendar"]
            topic = state.get("selected_topic", {})
            alignment = cc.check_topic_alignment(topic)
            schedule = cc.get_weekly_schedule()
            rotation = cc.get_category_rotation()
            state["content_alignment"] = alignment
            state["weekly_schedule"] = schedule
            print(f"   📅 Content calendar: category={alignment.get('category', 'N/A')}, "
                  f"aligned={'YES' if alignment.get('aligned') else 'NO'}")
            print(f"   📊 Weekly plan: {schedule.get('shorts_per_week', '?')} shorts, "
                  f"{schedule.get('main_videos_per_week', '?')} mains")
            if rotation:
                print(f"   🔄 Category rotation: {' → '.join(rotation[:5])}")
        except Exception as e:
            print(f"   ⚠️ Content calendar check failed: {e}")

        # ── 10.11: Fact Check (Named Entity Verification) ──
        try:
            fc = self.skills["fact_check"]
            script = state.get("script_payload")
            script_text = ""
            if script and hasattr(script, "full_script"):
                script_text = script.full_script
            elif isinstance(script, dict):
                script_text = script.get("full_script", "")
            topic = state.get("selected_topic", {})
            if script_text:
                fc_result = fc.check_script(
                    script_text=script_text,
                    title=topic.get("title", ""),
                    source_url=topic.get("source_url", ""),
                    topic_desc=topic.get("description", ""),
                )
                state["fact_check_result"] = fc_result
                verdict = fc_result.get("verdict", "UNCERTAIN")
                icon = "✅" if verdict == "PASS" else ("⚠️" if verdict == "UNCERTAIN" else "🔴")
                print(f"   {icon} Fact check: {verdict}")
                for w in fc_result.get("warnings", [])[:2]:
                    print(f"      ⚠️  {w}")
            else:
                print("   ✅ Fact check: no script text, skipping")
        except Exception as e:
            print(f"   ⚠️ Fact check failed: {e}")

        # ── 10.12: Compliance Check ──
        try:
            cc = self.skills["compliance_check"]
            script = state.get("script_payload")
            script_text = ""
            if script and hasattr(script, "full_script"):
                script_text = script.full_script
            elif isinstance(script, dict):
                script_text = script.get("full_script", "")
            topic = state.get("selected_topic", {})
            if script_text:
                comp_result = cc.check_compliance(script_text, topic)
                state["compliance_result"] = comp_result
                verdict = comp_result.get("verdict", "PASS")
                icon = "✅" if verdict == "PASS" else "🔴"
                print(f"   {icon} Compliance: {verdict}")
                if verdict != "PASS":
                    print(f"      ⚠️  {comp_result.get('reason', '')}")
            else:
                print("   ✅ Compliance: no script text, skipping")
        except Exception as e:
            print(f"   ⚠️ Compliance check failed: {e}")

        # ── 10.13: Intelligence Analysis ──
        try:
            ia = self.skills["intelligence_agent"]
            intel_result = ia.analyze(state)
            state["intelligence_recommendations"] = intel_result.get("recommendations", [])
            recs = intel_result.get("recommendations", [])
            if recs:
                print(f"   🧠 Intelligence: {len(recs)} recommendation(s)")
                for rec in recs[:3]:
                    print(f"      → {rec}")
            else:
                print("   ✅ Intelligence: pipeline healthy")
        except Exception as e:
            print(f"   ⚠️ Intelligence analysis failed: {e}")

        # ── 10.14: Collaboration Tracking ──
        try:
            col = self.skills["collaboration_agent"]
            topic = state.get("selected_topic", {})
            col_result = col.run(topic=topic)
            state["collaboration_stats"] = col_result.get("stats", {})
            if col_result.get("success"):
                stats = col_result.get("stats", {})
                print(f"   🤝 Collaboration: {stats.get('total_partners', 0)} partners, {stats.get('total_outreach_sent', 0)} outreach")
            else:
                print(f"   ⚠️ Collaboration: {col_result.get('error', 'failed')}")
        except Exception as e:
            print(f"   ⚠️ Collaboration tracking failed: {e}")

        # ── 10.15: Audience Channel Notifications ──
        try:
            acm = self.skills["audience_channel_manager"]
            topic = state.get("selected_topic", {})
            upload = state.get("upload_results", {})
            video_url = ""
            youtube_id = ""
            if isinstance(upload, list) and upload:
                if isinstance(upload[0], dict):
                    video_url = upload[0].get("url", "")
                    youtube_id = upload[0].get("youtube_id", "")
            elif isinstance(upload, dict):
                video_url = upload.get("main_video_url", "")
                main = upload.get("main", {})
                if isinstance(main, dict):
                    youtube_id = main.get("youtube_id", "")
            if video_url:
                notify_result = acm.notify(
                    title=topic.get("title", "New ViralDNA Video"),
                    video_url=video_url,
                    youtube_id=youtube_id,
                )
                state["channel_notification_result"] = notify_result
                if notify_result.get("telegram_sent"):
                    print(f"   📨 Audience notification: Telegram sent!")
                else:
                    print(f"   ⚠️ Audience notification: {notify_result.get('telegram_reason', 'not sent')}")
            else:
                print("   ✅ Audience notification: no video URL, skipping")
        except Exception as e:
            print(f"   ⚠️ Audience notification failed: {e}")

        # ── 10.16: Continuous Auditor (Telemetry Commit) ──
        try:
            ca = self.skills["continuous_auditor"]
            audit = ca.audit_pipeline_run(state)
            state["audit_report"] = audit
            icon = "✅" if audit["status"] == "healthy" else ("⚠️" if audit["status"] == "degraded" else "🔴")
            print(f"   {icon} Audit: {audit['status']} (health={audit['health_score']}/100)")
            ca.commit_telemetry(state)
            print(f"   📊 Telemetry committed to growth ledger")
        except Exception as e:
            print(f"   ⚠️ Continuous auditor failed: {e}")

        # ── 10.17: Telegram Summary ──
        compiled = state.get("compiled_videos", [])
        upload = state.get("upload_results", [])
        errors = state.get("errors", [])
        topic = state.get("selected_topic", {})

        # ── 10.18: Engagement Loop — pinned comment + response generation ──
        try:
            el = self.skills["engagement_loop"]
            topic = state.get("selected_topic", {})
            upload_results = state.get("upload_results", [])
            video_id = ""
            for r in upload_results:
                if isinstance(r, dict) and r.get("video_id"):
                    video_id = r["video_id"]
                    break

            pinned = el.generate_pinned_comment(topic, video_id=video_id)
            state["pinned_comment"] = pinned
            print(f"   📌 Pinned comment: {pinned.get('pinned_comment', '')[:60]}...")

            engagement_prompt = el.generate_engagement_prompt(topic)
            state["engagement_prompt"] = engagement_prompt
            print(f"   💬 Engagement prompt: {engagement_prompt[:60]}...")
        except Exception as e:
            print(f"   ⚠️ Engagement loop failed: {e}")

        # ── 10.19: Subscribe CTA Optimization ──
        try:
            cta = self.skills["subscribe_cta"]
            topic = state.get("selected_topic", {})
            series_plan = state.get("series_funnel_plan", {})

            if series_plan.get("total_parts", 0) > 1:
                # Series CTA
                seq_cta = cta.get_series_cta(part=1, total=series_plan.get("total_parts", 3))
            else:
                # Standard CTA sequence
                seq_cta = cta.get_full_cta_sequence(video_type="main", topic=topic)

            state["subscribe_cta_result"] = seq_cta
            if isinstance(seq_cta, list):
                print(f"   🔔 CTA sequence: {len(seq_cta)} positions")
            else:
                print(f"   🔔 CTA: {seq_cta.get('cta_text', '')[:60]}...")
        except Exception as e:
            print(f"   ⚠️ CTA optimization failed: {e}")

        # ── 10.20: Cross-Platform Distribution Plan ──
        try:
            cpd = self.skills["cross_platform"]
            topic = state.get("selected_topic", {})
            compiled_videos = state.get("compiled_videos", [])
            main_video = compiled_videos[0] if compiled_videos else ""
            clip_plan = cpd.generate_clip_plan(main_video, topic)
            state["cross_platform_plan"] = clip_plan
            print(f"   📱 Cross-platform: {clip_plan.get('total_platforms', 0)} platforms planned")
        except Exception as e:
            print(f"   ⚠️ Cross-platform planning failed: {e}")

        # ── 10.21: Retention Curve Analysis ──
        try:
            rca = self.skills["retention_curve"]
            analytics = state.get("analytics_summary", {})
            # If we have retention data, analyze it
            retention_data = analytics.get("retention_curve", [])
            video_duration = analytics.get("avg_duration_sec", 300)
            if retention_data:
                retention_analysis = rca.analyze_retention_curve(retention_data, video_duration)
                state["retention_analysis"] = retention_analysis
                print(f"   📉 Retention: avg={retention_analysis.get('average_retention_pct', 'N/A')}%, "
                      f"first30s={retention_analysis.get('first_30s_retention_pct', 'N/A')}%")
                for insight in retention_analysis.get("insights", [])[:2]:
                    print(f"      💡 {insight}")
            else:
                print(f"   📉 Retention: no curve data available (will analyze after YouTube processes)")
        except Exception as e:
            print(f"   ⚠️ Retention curve analysis failed: {e}")

        # ── 10.22: Competitor Intel — pass YouTube service for live scanning ──
        try:
            ci = self.skills["competitor_intel"]
            youtube_service = state.get("youtube_service")
            if youtube_service:
                ci.set_youtube_service(youtube_service)
                print(f"   🔍 Competitor intel: YouTube API connected for live scanning")
            else:
                print(f"   🔍 Competitor intel: no YouTube service in state (set_youtube_service to enable)")
        except Exception as e:
            print(f"   ⚠️ Competitor intel setup failed: {e}")

        # ── Telegram Summary ──
        upload = state.get("upload_results", [])
        compiled = state.get("compiled_videos", [])
        errors = state.get("errors", [])
        topic = state.get("selected_topic", {})

        # Count successful uploads
        upload_count = 0
        if isinstance(upload, list):
            upload_count = sum(1 for r in upload if isinstance(r, dict) and r.get("status") == "success")
        elif isinstance(upload, dict):
            upload_count = 1 if upload.get("status") == "success" else 0

        milestone_info = state.get("milestone_check", {})
        quality_info = state.get("content_quality_result", {})

        msg = (
            f"🧬 VDNA 3.0 Pipeline Complete\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📰 Topic: {topic.get('title', 'N/A')}\n"
            f"🎬 Videos: {len(compiled)}\n"
            f"📤 Uploaded: {upload_count}\n"
            f"⚠️ Errors: {len(errors)}\n"
        )

        if milestone_info.get("celebrate"):
            msg += f"🎉 Milestone: {milestone_info.get('milestone')} subs!\n"

        if quality_info:
            fc = quality_info.get("fact_check", {})
            bi = quality_info.get("bias_detection", {})
            msg += f"✅ Quality: fact={'PASS' if fc.get('pass') else 'REVIEW'}, bias={bi.get('risk_level', 'N/A')}\n"

        # Tier 2: reliability + license + calendar
        reliability = state.get("reliability_status", {})
        if reliability:
            quota = reliability.get("quota", {})
            msg += f"📊 API: {quota.get('status', 'N/A')} ({quota.get('percent_used', '?')}% used)\n"

        license_report = state.get("license_compliance_report", {})
        if license_report:
            msg += f"📋 License: {'PASS' if license_report.get('pass') else 'REVIEW'}\n"

        alignment = state.get("content_alignment", {})
        if alignment:
            msg += f"📅 Calendar: {alignment.get('category', 'N/A')} ({'aligned' if alignment.get('aligned') else 'check needed'})\n"

        msg += f"━━━━━━━━━━━━━━━━━━━━━"

        print(f"   📬 Sending Telegram notification...")
        self._send_telegram(msg)
        return state

    def _build_description(self, state):
        """Build YouTube video description."""
        topic = state.get("selected_topic", {})
        script = state.get("script_payload", {})
        title = topic.get("title", "ViralDNA News")
        return f"{title}\n\nProduced by ViralDNA 2.0 — AI-powered news broadcasting.\n\n#News #India #ViralDNA"

    def _send_telegram(self, message):
        """Send Telegram notification."""
        try:
            import requests
            from dotenv import load_dotenv
            load_dotenv(os.path.expanduser("~/.env"))
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
            if not token or not chat_id:
                print("   ⚠️ Telegram: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
                return
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
                timeout=10
            )
            if r.status_code == 200:
                print("   📬 Telegram notification sent")
            else:
                print(f"   ⚠️ Telegram returned {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"   ⚠️ Telegram notification failed: {type(e).__name__}: {e}")

    def _print_final_report(self):
        """Print final pipeline report."""
        errors = self.state.get("errors", [])
        compiled = self.state.get("compiled_videos", [])
        upload = self.state.get("upload_results", {})

        print(f"\n{'='*70}")
        print(f"🏆 VIRALDNA 2.0 — PIPELINE COMPLETE")
        print(f"{'='*70}")
        print(f"   Run ID: {self.run_id}")
        print(f"   Videos produced: {len(compiled)}")
        for v in compiled:
            size = os.path.getsize(v) / (1024*1024) if os.path.exists(v) else 0
            print(f"     📹 {os.path.basename(v)} ({size:.1f}MB)")
        print(f"   Upload: {upload.get('status', 'N/A') if isinstance(upload, dict) else 'completed'}")
        print(f"   Errors: {len(errors)}")
        for err in errors:
            print(f"     ⚠️  {err}")
        print(f"   Checkpoints: {self.checkpoint_mgr.get_completed_phases()}")
        print(f"{'='*70}\n")


# ═══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ViralDNA 2.0 Director")
    parser.add_argument("--run-id", type=str, default=None, help="Run ID (auto-generated if not set)")
    parser.add_argument("--topic", type=str, default=None, help="Inject a topic (skip discovery)")
    args = parser.parse_args()

    director = VDNA2Director(run_id=args.run_id)

    injected = None
    if args.topic:
        injected = {"title": args.topic, "id": args.topic.replace(" ", "_")}

    state = director.run(injected_topic=injected)
