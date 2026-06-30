# VDNA 4.0 — Changelog & Release Notes
**Date:** 2026-06-30

## What is VDNA 4.0?

VDNA 4.0 is a ground-up rewrite and hardening of the ViralDNA pipeline. It fixes critical bugs from VDNA 3.0 and introduces strict execution mode where no phase can be silently skipped or fail without raising an error.

## Critical Bugs Fixed (from VDNA 3.0 → 4.0)

### 1. Duplicate Skills Dict Keys (CRITICAL)
- **Bug:** The `self.skills = {...}` dict had 29 duplicate keys. Python's dict behavior means the last value silently overwrote all prior entries.
- **Impact:** `engagement_loop`, `subscribe_cta`, `retention_curve`, and 6+ other modules were mapped to the WRONG class instance (the second definition always won).
- **Fix:** Completely rebuilt `_build_skills_dict()` — each skill key is set EXACTLY ONCE with proper try/except import handling.

### 2. Duplicate Imports
- **VDNA 3.0 had:** `from rag_feedback import RagFeedbackLoop` imported twice (lines 261, 1627), `from yt_analytics import YouTubeAnalytics` twice (lines 260, 1628), plus 6 other duplicate import statements.
- **Fix:** All imports consolidated at module top — no duplicates.

### 3. Class Name Mismatch
- **VDNA 3.0:** Class named `VDNA2Director` despite being "VDNA 3.0" with prints saying "IRALDNA 2.0" and "VDNA 3.0" mixed throughout.
- **VDNA 4.0:** Clean rename to `VDNA4Director`, all prints consistently say "VDNA 4.0".

### 4. Silent Phase Skipping
- **VDNA 3.0:** Missing skills set to `None` → phases would silently no-op. Try/except wrappers caught ALL exceptions and just printed "⚠️".
- **VDNA 4.0:** Strict mode ON by default. Missing critical skills → `RuntimeError`.

## New Architecture (4.0)

### Phases (all execute unless valid checkpoint exists)
| Phase | Name | Sub-phases | Description |
|-------|------|------------|-------------|
| 0 | Genesis | — | Growth bus load, data guard inventory, disk check |
| 1 | Discovery | 1.1 Validation | Trend discovery + topic selection |
| 2 | Weighting | — | Score and rank candidates |
| 2.5 | Quality Gate | — | Fact-check + compliance |
| 3 | Scripting | 3.5 Review | Script generation + NER verification |
| 4 | Voice | 4.5 Verify | RVC → gTTS fallback chain |
| 5 | Thumbnail | 5.5 Validate | CTR-optimized branded thumbnails |
| 6 | Assembly | 6.5 Verify | FFmpeg assembly with typewriter fallback |
| 7 | Forensic Audit | — | Pre-ship quality gate |
| 8 | Upload | 8.5 Verify | YouTube upload + publish decision |
| 9 | Post-Pipeline | — | Analytics, growth agents, blog, Telegram |

### Sub-phases (validation checkpoints)
- **Phase 1.1 (Discovery Validation):** Ensures topic selected or falls back to growth bus top performer
- **Phase 3.5 (Script Review):** Length + entity count verification
- **Phase 4.5 (Voice Verify):** Audio file exists + non-silent check
- **Phase 5.5 (Thumb Validate):** Image dimensions + file size check
- **Phase 6.5 (Assembly Verify):** ffprobe duration check
- **Phase 8.5 (Upload Verify):** YouTube ID confirmation

### Strict Mode Rules
1. Every phase MUST complete or explicitly skip via valid checkpoint
2. If a phase fails without a fallback → `RuntimeError` → pipeline halts
3. Upload disabled is NOT a failure — it's a valid configuration state
4. Fallback chain: RVC → gTTS (voice), PIL solid color (thumbnail), inline (audit)

## File Changes

| File | Action | Status |
|------|--------|--------|
| modules/vdna4_director.py | NEW — VDNA4Director | Created |
| run_vdna4.py | NEW — VDNA 4.0 entry point | Created |
| modules/vdna2_director.py | KEPT — VDNA 3.0 director (reference) | Unchanged |
| run_vdna3.py | KEPT — VDNA 3.0 entry point | Unchanged |

## Migration Guide

**To run VDNA 4.0:**
```bash
python3 run_vdna4.py                          # Full pipeline
python3 run_vdna4.py --topic "Some News"      # Inject topic
python3 run_vdna4.py --no-strict              # Soft mode (NOT recommended)
```

**To run VDNA 3.0 (legacy):**
```bash
python3 run_vdna3.py
```

## Verification Status
- [x] Compile check: PASSED
- [x] Import test: PASSED
- [x] Singleton skills dict: VALIDATED (no duplicate keys)
- [x] Strict mode enforcement: VALIDATED
- [x] Data guard integration: WIRED
- [x] Growth feedback bus: WIRED (load/inject/persist)
- [x] Checkpoint/resume: WIRED (FactoryWorker.is_complete check)
- [x] Runtime error propagation: VALIDATED
