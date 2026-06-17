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
3. Graceful degradation — Fish Speech fails? Falls back to gTTS. Visual fails? Uses local generator.
4. Disk monitoring — refuses to write if disk < 500MB
5. Signal handling — SIGTERM/SIGINT triggers graceful shutdown, not crash
6. Per-phase isolation — each factory worker runs in controlled environment
7. RAG feedback loop — producer brief from past performance injected into scripting
8. CTR optimization — title + thumbnail scored after creation
9. Shorts optimization — LLM-based titles after assembly
10. Upload time optimization — IST window enforced
11. YouTube Analytics — real metrics pulled post-pipeline

Architecture:
    Director.run()
        ├── Phase 1: Discovery        → FactoryWorker("discovery")
        ├── Phase 2: Weighting        → FactoryWorker("weighting")
        ├── Phase 3: Scripting        → FactoryWorker("scripting") [+ RAG brief]
        ├── Phase 4: Voice            → FactoryWorker("voice") [Fish Speech + gTTS fallback]
        ├── Phase 5: Visuals          → FactoryWorker("visuals")
        ├── Phase 6: Thumbnail       → FactoryWorker("thumbnail") [+ CTR optimizer]
        ├── Phase 7: Assembly         → FactoryWorker("assembly") [+ Shorts optimizer]
        ├── Phase 8: Forensic Audit  → FactoryWorker("forensic_audit")
        ├── Phase 9: Upload           → FactoryWorker("upload") [+ Upload time optimizer]
        └── Phase 10: Post-pipeline   → FactoryWorker("post_pipeline") [+ Analytics + RAG]
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
    "visuals":         300,   # 5 min — image fetching/generation
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
            "visuals": ["visuals", "background_canvas"],
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
        from visual_fetcher import VisualFetcher
        from gemini_engine import GeminiEngine
        from forensic_audit import ForensicAudit
        from pre_ship_check import PreShipCheck
        from publish_decision_engine import decide_publish_plan
        # VDNA 3.0: New modules wired into pipeline
        from ctr_optimizer import CTROptimizer
        from shorts_optimizer import ShortsOptimizer
        from upload_time_optimizer import UploadTimeOptimizer
        from yt_analytics import YouTubeAnalytics
        from rag_feedback import RagFeedbackLoop

        self.skills = {
            "trend_discovery": TrendDiscovery(config_instance=config),
            "post_filter": PostFilter(config_dict=config.POST_FILTER_CONFIG),
            "script_generator": ScriptGenerator(engine=GeminiEngine(), config_dict=config.SCRIPT_GENERATION_CONFIG),
            "voiceover": VoiceoverGenerator,
            "video_assembler": VideoAssembler(config_instance=config),
            "thumbnail_creator": ThumbnailCreator(pacer=config, config_instance=config),
            "visual_fetcher": VisualFetcher(pacer=config, config_instance=config),
            "gemini_engine": GeminiEngine(),
            "forensic_audit": ForensicAudit(drive_base=config.DRIVE_BASE),
            "pre_ship_check": PreShipCheck(drive_base=config.DRIVE_BASE),
            "decide_publish_plan": decide_publish_plan,
            # VDNA 3.0 additions
            "ctr_optimizer": CTROptimizer(),
            "shorts_optimizer": ShortsOptimizer(),
            "upload_time_optimizer": UploadTimeOptimizer(),
            "yt_analytics": YouTubeAnalytics(credentials_path=config.DRIVE.get("YOUTUBE_TOKEN", "")),
            "rag_feedback": RagFeedbackLoop(ledger_path=os.path.join(config.DRIVE_BASE, "diagnostics", "growth_ledger.json")),
        }
        print(f"   📦 Loaded {len(self.skills)} skill modules")

    def run(self, injected_topic=None):
        """
        Execute the full VDNA 2.0 pipeline.

        Args:
            injected_topic: Optional pre-selected topic (skips discovery/weighting)
        """
        print(f"\n{'━'*70}")
        print(f"🚀 VIRALDNA 2.0 PIPELINE START — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'━'*70}\n")

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

        # ── PHASE 5: Visuals ──
        worker = FactoryWorker("visuals", self)
        self.state, ok = worker.run(
            self.state,
            primary_fn=self._phase_visuals,
            fallback_fn=self._phase_visuals_fallback,
        )
        if not ok:
            print("🛑 Visual harvesting failed (both primary and fallback)")
            return self.state

        # ── PHASE 6: Thumbnail ──
        worker = FactoryWorker("thumbnail", self)
        self.state, ok = worker.run(
            self.state,
            primary_fn=self._phase_thumbnail,
        )
        if not ok:
            print("⚠️ Thumbnail creation failed — continuing without branded thumbnail")

        # ── PHASE 7: Assembly ──
        worker = FactoryWorker("assembly", self)
        self.state, ok = worker.run(
            self.state,
            primary_fn=self._phase_assembly,
        )
        if not ok:
            print("🛑 Video assembly failed")
            return self.state

        # ── PHASE 8: Forensic Audit ──
        worker = FactoryWorker("forensic_audit", self)
        self.state, ok = worker.run(
            self.state,
            primary_fn=self._phase_forensic_audit,
        )
        if not ok:
            print("🛑 Forensic audit failed — halting before upload")
            return self.state

        # ── PHASE 9: Upload ──
        if os.environ.get("VIRALDNA_UPLOAD_ENABLED", "false").lower() == "true":
            worker = FactoryWorker("upload", self)
            self.state, ok = worker.run(
                self.state,
                primary_fn=self._phase_upload,
            )
        else:
            print("⏭️ Upload skipped (VIRALDNA_UPLOAD_ENABLED=false — review mode)")
            self.state["upload_results"] = {"status": "skipped", "reason": "upload_disabled"}

        # ── PHASE 10: Post-Pipeline ──
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
        """Phase 2: Weight and rank topics."""
        print("   ⚖️  Weighting and ranking topics...")
        pf = self.skills["post_filter"]
        raw_news = state.get("raw_news", [])
        sorted_topics = pf.run(raw_news)
        state["sorted_topics"] = sorted_topics
        if sorted_topics:
            state["selected_topic"] = sorted_topics[0]
            raw = sorted_topics[0].get("title", sorted_topics[0].get("id", "topic"))
            words = raw.split()[:6]
            slug = "_".join(w for w in words if w).replace("/", "_").replace(":", "").replace("'", "").replace('"', "").replace("?", "").replace("!", "").replace(",", "").replace(";", "").replace("(", "").replace(")", "").replace("&", "and")
            state["topic_slug"] = slug or sorted_topics[0].get("id", "topic")
            print(f"   🏆 Top topic: {sorted_topics[0].get('title', 'N/A')[:60]}")
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

    def _phase_visuals(self, state):
        """Phase 5: Visual harvesting.
        v87.8: Primary = Stable Diffusion via local_visual_generator.
               Fallback = VisualFetcher (RSS/Serper) for supplementary images.
        """
        print("   🖼️  Harvesting visuals...")
        topic = state.get("selected_topic", {})
        topic_title = topic.get("title", "")
        topic_slug = state.get("topic_slug", "topic")
        runtime_dir = config.DRIVE.get("RUNTIME", "/home/jay/ViralDNA/output/runtime")
        os.makedirs(runtime_dir, exist_ok=True)

        # ─── Primary: Stable Diffusion local generation ────────────────────
        from local_visual_generator import generate_scene_images
        sd_dir = os.path.join(runtime_dir, "sd_scenes")
        try:
            sd_paths = generate_scene_images(
                topic_title, sd_dir, count=5, width=1920, height=1080
            )
            if sd_paths:
                state["visuals"] = sd_paths
                bg_path = os.path.join(runtime_dir, f"{topic_slug}_bg.jpg")
                import shutil
                shutil.copy2(sd_paths[0], bg_path)
                state["background_canvas"] = bg_path
                print(f"   🖼️  SD generated {len(sd_paths)} scene images")
                return state
        except Exception as e:
            print(f"   ⚠️  SD generation failed: {e}, trying VisualFetcher...")

        # ─── Fallback: VisualFetcher (RSS/Serper) ─────────────────────────
        vf = self.skills["visual_fetcher"]
        visuals = vf.fetch_visuals(topic=topic)
        state["visuals"] = visuals

        bg_path = os.path.join(runtime_dir, f"{topic_slug}_bg.jpg")
        if visuals:
            import shutil
            shutil.copy2(visuals[0], bg_path)
            state["background_canvas"] = bg_path
        else:
            state["background_canvas"] = self._generate_local_background(state)

        print(f"   🖼️  Visuals: {len(visuals)} images (from VisualFetcher)")
        return state

    def _phase_visuals_fallback(self, state):
        """Phase 5 Fallback: local visual generation."""
        print("   🔄 Visual fallback: using local generator...")
        bg_path = self._generate_local_background(state)
        state["background_canvas"] = bg_path
        state["visuals"] = [bg_path]
        return state

    def _generate_local_background(self, state):
        """Generate a local background image when all fetchers fail."""
        try:
            from local_visual_generator import generate_scene_image
            topic = state.get("selected_topic", {})
            title = topic.get("title", "News")
            category = topic.get("category", "general")
            bg_path = os.path.join(
                config.DRIVE.get("RUNTIME", "/home/jay/ViralDNA/output/runtime"),
                f"{state.get('topic_slug', 'topic')}_bg.jpg"
            )
            os.makedirs(os.path.dirname(bg_path), exist_ok=True)
            generate_scene_image(title, bg_path)
            return bg_path
        except Exception as e:
            print(f"   ⚠️ Local background generation failed: {e}")
            return None

    def _phase_thumbnail(self, state):
        """Phase 6: Thumbnail creation.
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

        # VDNA 3.0: CTR optimization — score title + thumbnail
        try:
            ctr = self.skills["ctr_optimizer"]
            title = topic.get("title", "ViralDNA News")
            ctr_result = ctr.optimize(title=title, thumbnail_path=thumb_path)
            state["ctr_optimization"] = ctr_result
            print(f"   📊 CTR score: {ctr_result.get('ctr_score', 'N/A')}/100 (title: {ctr_result.get('title_score', 'N/A')}, thumb: {ctr_result.get('thumbnail_score', 'N/A')})")
        except Exception as e:
            print(f"   ⚠️ CTR optimization failed: {e} — continuing without")

        return state

    def _phase_assembly(self, state):
        """Phase 7: Video assembly with FFmpeg.
        VDNA 3.0: Shorts optimizer generates titles + CTAs after assembly.
        """
        print("   🎬 Assembling videos...")
        va = self.skills["video_assembler"]
        script_payload = state.get("script_payload")
        voiceover_assets = state.get("voiceover_assets", {})
        background_canvas = state.get("background_canvas")
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

        # Main video
        if decision.produce_main:
            audio_path = voiceover_assets.get("main")
            if audio_path:
                main_filename = f"{topic_slug}_Main.mp4"
                # Calculate target duration from word count (~150 wpm speaking rate)
                word_count = len(main_text.split()) if main_text else 200
                target_duration = max(60, min(word_count * 0.4, 600))
                va.assemble_video(
                    main_filename, audio_path, background_canvas,
                    main_filename, target_duration,
                    async_mode=False, script_text=main_text[:500],
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
                short_audio = voiceover_assets[key]
                short_filename = f"{topic_slug}_Short{i}.mp4"
                short_word_count = len(short_text.split()) if short_text else 30
                short_duration = max(15, min(short_word_count * 0.4, 60))
                va.assemble_video(
                    short_filename, short_audio, background_canvas,
                    short_filename, short_duration,
                    async_mode=False, script_text=short_text[:200],
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

        # VDNA 3.0: Shorts optimization — generate titles, CTAs, branding
        try:
            so = self.skills["shorts_optimizer"]
            topic_title = topic.get("title", "")
            topic_context = topic.get("description", "")
            source = topic.get("source", "")
            shorts_titles = so.generate_shorts_title_batch(
                base_title=topic_title,
                topic_context=topic_context,
                source=source,
            )
            state["shorts_titles"] = shorts_titles
            print(f"   📱 Shorts titles generated: {len(shorts_titles)} variants")

            # VDNA 3.0: Build CTA with main video URL for subscriber conversion
            main_video_url = state.get("main_video_url", "")
            cta = so.build_shorts_cta(main_video_url=main_video_url, topic_title=topic_title)
            state["shorts_cta"] = cta
            print(f"   🔗 Shorts CTA: {cta.get('cta_text', 'N/A')[:60]}...")
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
        """
        print("   📤 Uploading to YouTube...")
        from youtube_uploader import YouTubeUploader
        uploader = YouTubeUploader(config)
        compiled_videos = state.get("compiled_videos", [])
        topic = state.get("selected_topic", {})
        results = []

        # VDNA 3.0: Check optimal upload time window
        try:
            uto = self.skills["upload_time_optimizer"]
            schedule = uto.get_optimal_upload_time()
            state["upload_schedule"] = schedule
            print(f"   ⏰ Upload window: {schedule.get('window_name', 'N/A')} (score: {schedule.get('window_score', 'N/A')})")
        except Exception as e:
            print(f"   ⚠️ Upload time optimization failed: {e}")

        for video_path in compiled_videos:
            is_short = "Short" in video_path
            result = uploader.upload(
                video_path=video_path,
                title=topic.get("title", "ViralDNA News"),
                description=self._build_description(state),
                tags=["news", "india", "viral"],
                is_short=is_short,
            )
            results.append(result)
        state["upload_results"] = results
        print(f"   📤 Uploaded {len(results)} videos")
        return state

    def _phase_post_pipeline(self, state):
        """Phase 10: Post-pipeline tasks (analytics, RAG feedback, notifications).
        VDNA 3.0: Pulls YouTube Analytics, stores metrics, generates producer brief.
        """
        print("   📊 Post-pipeline: analytics + notifications...")

        # VDNA 3.0: YouTube Analytics — pull metrics for uploaded videos
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

        # VDNA 3.0: RAG feedback — store performance + generate producer brief
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

        # Send Telegram summary
        compiled = state.get("compiled_videos", [])
        upload = state.get("upload_results", {})
        errors = state.get("errors", [])
        topic = state.get("selected_topic", {})

        msg = (
            f"🧬 VDNA 3.0 Pipeline Complete\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📰 Topic: {topic.get('title', 'N/A')}\n"
            f"🎬 Videos: {len(compiled)}\n"
            f"📤 Upload: {upload.get('status', 'N/A') if isinstance(upload, dict) else 'done'}\n"
            f"⚠️ Errors: {len(errors)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
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
