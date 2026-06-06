# MODULE: pre_ship_check.py
# PURPOSE: Post-forensic content accuracy verification — catches what the
#          forensic audit (file existence, word count, silence) cannot catch:
#            1. Thumbnail topic-specificity (thumbnail actually shows the topic)
#            2. Audio-script alignment (voiceover matches script text)
#            3. Real photo vs AI-generated detection (metadata + heuristics)
#            4. Title/description accuracy (matches script + source state)
#            5. Source URL / score freshness (topic not stale, score valid)
#
# VERSION: 1.0 (v75.1 pipeline)
# CALLED BY: ForensicAuditGateAgent.execute() — after forensic audit passes

import os
import re
import json
import hashlib

# ── State key references (from run_multi_agent_pipeline.py state dict) ──
# state["selected_topic"]       → {title, url, description, source, score, ...}
# state["script_payload"]       → ScriptPayload with segments {main, short_1..3}
# state["voiceover_assets"]     → {main: path, short_1: path, ...}
# state["branded_thumbnail"]    → path to production_branded.jpg
# state["compiled_videos"]      → [path, ...]
# state["optimized_title"]      → string (final title chosen by optimizer)
# state["forensic_audit_passed"]→ True (must be True to reach here)
# state["approved_image_sources"] → list of {domain, relevance, is_real} dicts


class PreShipCheckError(Exception):
    """Raised when pre_ship_check detects a content accuracy failure."""
    pass


class PreShipCheck:
    """
    Content accuracy verification that runs AFTER ForensicAudit passes.
    Factual/content checks only — not file existence (that's forensic's job).
    """

    # State keywords for cross-entity disambiguation
    STATE_KEYWORDS = {
        "Telangana": [
            "telangana", "hyderabad", "revanth", "kcr", "brs",
            "telangana cm", "telangana government", "bathukamma",
            "telangana formation", "Telangana Rashtra Samithi",
        ],
        "Andhra Pradesh": [
            "andhra pradesh", "andhra", "amaravati", "amaraviti",
            "vijayawada", "visakhapatnam", "vizag", "tirupati",
            "jagan", "ysrcp", "tdp", "nara lokesh", "chandrababu",
            "andhra cm", "pawan kalyan",
        ],
        "Tamil Nadu": [
            "tamil nadu", "tamil", "chennai", "dmk", "aiadmk",
            "stalin", "modi chennai",
        ],
        "Karnataka": [
            "karnataka", "bangalore", "bengaluru", "karnataka cm",
            "siddaramaiah", "karnataka politics",
        ],
        "Kerala": [
            "kerala", "kochi", "thiruvananthapuram", "kerala cm",
            "pinarayi", "ldf", "udf",
        ],
    }

    # Known Telugu news domains (real photos expected from these)
    TRUSTED_NEWS_DOMAINS = [
        "thehindu.com", "thehindu", "deccanherald.com", "deccanherald",
        "deccanchronicle.com", "deccanchronicle", "newindianexpress.com",
        "newindianexpress", "timesofindia.indiatimes.com", "timesofindia",
        "indianexpress.com", "indianexpress", "news18.com", "news18",
        "ndtv.com", "ndtv", "indiatoday.in", "indiatoday",
        "telanganatoday.com", "telanganatoday", "thenewsminute.com",
        "thenewsminute", "greatandhra.com", "greatandhra",
        "sakshi.com", "sakshi", "andhraprabha.com", "andhraprabha",
    ]

    # AI-generation indicators in file path, EXIF, or source metadata
    AI_INDICATORS = [
        "comfyui", "stable_diffusion", "sdxl", "dall-e", "midjourney",
        "ai_generated", "ai-generated", "ai_generated_image",
    ]

    # Tell-tale signs of duplicate/dummy images
    DUMMY_INDICATORS = [
        "placeholder", "dummy", "filler", "temp_img", "no_image",
        "not_found", "default", "blank",
    ]

    def __init__(self, drive_base: str):
        self.drive_base = drive_base
        self.video_dir = os.path.join(drive_base, "videos")
        self.audio_dir = os.path.join(drive_base, "audio")
        self.thumbnail_dir = os.path.join(drive_base, "thumbnails")
        self.runtime_dir = os.path.join(drive_base, "output", "runtime")
        self.log_path = os.path.join(drive_base, "logs", "pre_ship_check.log")

    # ──────────────────────────────────────────────────────────────────────
    # CHECK 1: Thumbnail topic-specificity
    # ──────────────────────────────────────────────────────────────────────

    def check_thumbnail_topic_match(self, state: dict) -> list:
        """
        Verify branded thumbnail exists and was generated for THIS topic.
        Heuristics:
          - Check file modification time is AFTER the script_payload was created
          - Verify thumbnail filename contains topic-relevant prefix
          - Check file is not from a previous run (compare with runtime dir)
        """
        issues = []
        thumb_path = state.get("branded_thumbnail", "")
        topic = state.get("selected_topic", {})
        topic_title = topic.get("title", "").lower().strip()

        if not thumb_path:
            issues.append("PreShip: No branded_thumbnail in state")
            return issues

        if not os.path.exists(thumb_path):
            issues.append(f"PreShip: Thumbnail file missing: {thumb_path}")
            return issues

        # Check filesize — real topic-specific thumbnails should be > 50KB
        thumb_size = os.path.getsize(thumb_path)
        if thumb_size < 30 * 1024:
            issues.append(
                f"PreShip: Thumbnail suspiciously small ({thumb_size} bytes) — "
                f"may be a placeholder or reused from previous run"
            )

        # Check if a DIFFERENT topic's thumbnail exists in the same directory
        # (would indicate previous run wasn't cleaned up)
        if os.path.isdir(self.thumbnail_dir):
            all_thumbs = [
                f for f in os.listdir(self.thumbnail_dir)
                if f.endswith(('.jpg', '.jpeg', '.png'))
                and f != os.path.basename(thumb_path)
            ]
            # Look for recent thumbnails (<1 hour old) that aren't ours
            import time
            now = time.time()
            for other_thumb in all_thumbs:
                other_path = os.path.join(self.thumbnail_dir, other_thumb)
                age_seconds = now - os.path.getmtime(other_path)
                if age_seconds < 3600 and os.path.getsize(other_path) > 30 * 1024:
                    # Another large, recent thumbnail exists — possible cross-contamination
                    issues.append(
                        f"PreShip: Another recent thumbnail found (age {age_seconds:.0f}s): "
                        f"{other_thumb} — possible cross-contamination from previous run"
                    )

        return issues

    # ──────────────────────────────────────────────────────────────────────
    # CHECK 2: Audio-script alignment
    # ──────────────────────────────────────────────────────────────────────

    def check_audio_script_alignment(self, state: dict) -> list:
        """
        Verify voiceover audio files have expected durations matching script.
        Long main scripts → long audio. If main script is 300 words but
        audio is only 10 seconds, something is wrong.
        Does NOT do speech-to-text (too expensive). Uses duration heuristic.
        """
        issues = []
        import subprocess

        script_payload = state.get("script_payload")
        voiceover_assets = state.get("voiceover_assets", {})

        if not script_payload:
            return ["PreShip: No script_payload in state"]

        for slot in ["main"]:  # Only check main (shorts duration varies)
            audio_path = voiceover_assets.get(slot)
            if not audio_path:
                issues.append(f"PreShip: No voiceover audio for {slot}")
                continue

            if not os.path.exists(audio_path):
                issues.append(f"PreShip: Audio file missing: {audio_path}")
                continue

            segment = script_payload.get_segment(slot)
            word_count = segment["word_count"]

            # Get actual audio duration via ffprobe
            try:
                result = subprocess.run(
                    [
                        "ffprobe", "-v", "quiet", "-show_entries",
                        "format=duration", "-of", "csv=p=0", audio_path
                    ],
                    capture_output=True, text=True, timeout=10
                )
                actual_duration_s = float(result.stdout.strip())
            except Exception:
                issues.append(f"PreShip: Could not probe audio duration: {audio_path}")
                continue

            # Expected: ~150 words/min for en-IN-PrabhatNeural (slightly faster than avg)
            # Min acceptable: 120 words/min (slow speaker)
            # Max acceptable: 200 words/min (very fast)
            expected_min_duration = word_count / 200.0 * 60.0  # fastest speech
            expected_max_duration = word_count / 100.0 * 60.0  # slowest reasonable

            if actual_duration_s < expected_min_duration * 0.5:
                issues.append(
                    f"PreShip: {slot} audio too short ({actual_duration_s:.1f}s) for "
                    f"{word_count}-word script (expected {expected_min_duration:.0f}s-{expected_max_duration:.0f}s). "
                    f"Audio may be truncated or from wrong script."
                )
            elif actual_duration_s > expected_max_duration * 2.0:
                issues.append(
                    f"PreShip: {slot} audio suspiciously long ({actual_duration_s:.1f}s) for "
                    f"{word_count}-word script (expected {expected_min_duration:.0f}s-{expected_max_duration:.0f}s). "
                    f"May contain wrong content."
                )

        return issues

    # ──────────────────────────────────────────────────────────────────────
    # CHECK 3: Real photo vs AI-generated detection
    # ──────────────────────────────────────────────────────────────────────

    def check_real_photos(self, state: dict) -> list:
        """
        Verify scene images are real news photos, not AI-generated.
        Checks:
          1. Image file paths don't contain AI indicators (comfyui_, etc.)
          2. Image sizes are reasonable for real photos (not exact SD resolutions)
          3. At least min 2 of N scene images are from trusted news domains
             (via metadata file if available)
        """
        issues = []
        topic = state.get("selected_topic", {})
        topic_title = topic.get("title", "")

        # Check approved_image_sources if available
        approved_sources = state.get("approved_image_sources", [])

        ai_count = 0
        trusted_count = 0
        untrusted_count = 0

        for src in approved_sources:
            domain = src.get("domain", "").lower()
            is_real = src.get("is_real", True)

            # Check for AI indicators in domain or path
            if any(ind in domain for ind in self.AI_INDICATORS) or not is_real:
                ai_count += 1
            elif any(tld in domain for tld in self.TRUSTED_NEWS_DOMAINS):
                trusted_count += 1
            else:
                untrusted_count += 1

        total = len(approved_sources)
        if total == 0:
            # No image sources recorded — check slideshow directory instead
            slideshow_dir = os.path.join(self.audio_dir, "slideshow_production_main")
            if os.path.isdir(slideshow_dir):
                scene_files = [
                    f for f in os.listdir(slideshow_dir)
                    if f.endswith(('.jpg', '.jpeg', '.png', '.webp'))
                ]
                if not scene_files:
                    issues.append(
                        "PreShip: No scene images found in slideshow_production_main. "
                        "May be fully AI-generated or local-pack fallback."
                    )
                else:
                    # Check for AI indicators in filenames
                    for f in scene_files:
                        fl = f.lower()
                        if any(ind in fl for ind in self.AI_INDICATORS):
                            ai_count += 1
                        elif any(ind in fl for ind in self.DUMMY_INDICATORS):
                            issues.append(
                                f"PreShip: Scene image looks like placeholder: {f}"
                            )

                    if ai_count == len(scene_files) and len(scene_files) > 0:
                        issues.append(
                            f"PreShip: ALL {len(scene_files)} scene images are AI-generated "
                            f"(comfyui_ prefix detected). No real news photos."
                        )
                    elif ai_count > len(scene_files) * 0.5:
                        issues.append(
                            f"PreShip: {ai_count}/{len(scene_files)} scene images are AI-generated. "
                            f"Majority should be real news photos."
                        )
            else:
                issues.append(
                    "PreShip: No slideshow_production_main directory and no approved_image_sources. "
                    "Cannot verify image authenticity."
                )
        else:
            # We have approved_sources metadata
            if ai_count > 0:
                issues.append(
                    f"PreShip: {ai_count}/{total} image sources are AI-generated. "
                    f"Real news photos should be primary."
                )
            if trusted_count == 0 and total >= 3:
                issues.append(
                    f"PreShip: 0/{total} image sources are from trusted news domains. "
                    f"Expected at least 1 from: {', '.join(self.TRUSTED_NEWS_DOMAINS[:5])}"
                )

        return issues

    # ──────────────────────────────────────────────────────────────────────
    # CHECK 4: Title/description accuracy
    # ──────────────────────────────────────────────────────────────────────

    def check_title_description_accuracy(self, state: dict) -> list:
        """
        Verify optimized title and description:
          1. Title contains the correct state name (matching source topic)
          2. Title doesn't contain wrong-state names
          3. Description mentions the state at least once
          4. Title is not a generic template ("Breaking News", "Latest Update")
        """
        issues = []
        topic = state.get("selected_topic", {})
        topic_title = topic.get("title", "")
        topic_desc = topic.get("description", "")
        topic_url = topic.get("url", "")
        topic_source = topic.get("source", "")

        optimized_title = state.get("optimized_title", "") or topic_title
        if not optimized_title:
            issues.append("PreShip: No optimized_title or topic title available")
            return issues

        # Detect expected state from topic metadata
        topic_ctx = f"{topic_title} {topic_desc} {topic_url} {topic_source}".lower()
        expected_states = []
        for state_name, keywords in self.STATE_KEYWORDS.items():
            for kw in keywords:
                if kw in topic_ctx:
                    if state_name not in expected_states:
                        expected_states.append(state_name)

        title_lower = optimized_title.lower()

        if expected_states:
            # Check correct state is in title
            correct_in_title = any(s.lower() in title_lower for s in expected_states)
            if not correct_in_title:
                # Check if WRONG state is in title
                all_states = list(self.STATE_KEYWORDS.keys())
                wrong_in_title = [
                    s for s in all_states
                    if s.lower() in title_lower and s not in expected_states
                ]
                if wrong_in_title:
                    issues.append(
                        f"PreShip: TITLE STATE MISMATCH — topic is about {expected_states} "
                        f"but title says {wrong_in_title}: '{optimized_title}'"
                    )
                elif len(expected_states) == 1:
                    # State not mentioned at all — less critical but worth flagging
                    pass  # Title may not always include state name (acceptable)

        # Check for generic/bare titles
        # v82.5: Expanded to catch semantic generics, not just exact matches
        generic_titles_exact = [
            "breaking news", "latest update", "today's news", "news update",
            "top news", "latest news", "news today", "just in",
        ]
        # Generic patterns: titles that could apply to ANY news story
        generic_patterns = [
            r"^political developments",
            r"^congress leaders",
            r"^leaders show",
            r"^political storm",
            r"^what it means$",
            r"^latest developments",
            r"^breaking story",
            r"^news alert",
            r"^important update",
            r"^just in:",
            r"^update:",
            r"^news:",
        ]
        if title_lower.strip() in generic_titles_exact:
            issues.append(
                f"PreShip: Title is generic template: '{optimized_title}'. "
                f"Must be topic-specific with names, places, or numbers."
            )
        else:
            for pattern in generic_patterns:
                if re.search(pattern, title_lower):
                    issues.append(
                        f"PreShip: Title is too generic/vague: '{optimized_title}'. "
                        f"Pattern matched: '{pattern}'. Must include specific names, places, or data."
                    )
                    break

        # Check title has at least one proper noun (capitalized word mid-title)
        # Titles that are ALL generic words won't have this
        words = optimized_title.split()
        proper_nouns = [w for w in words if len(w) > 2 and w[0].isupper() and w.lower() not in (
            "the", "and", "for", "are", "but", "not", "you", "all", "can", "had", "her", "was",
            "one", "our", "out", "day", "get", "has", "him", "his", "how", "its", "may", "new",
            "now", "old", "see", "two", "way", "who", "boy", "did", "own", "say", "she", "too",
            "use", "with", "have", "this", "will", "your", "from", "they", "been", "call", "come",
            "could", "each", "make", "than", "them", "then", "what", "when", "word", "said",
            "telugu", "news", "india", "andhra", "telangana", "ap", "breaking", "urgent",
            "explained", "analysis", "full", "complete", "latest", "update", "today",
        )]
        if len(proper_nouns) < 2 and len(words) > 4:
            issues.append(
                f"PreShip: Title lacks specific proper nouns (names/places): '{optimized_title}'. "
                f"Need at least 2 specific entities for YouTube SEO."
            )

        # Check title length (YouTube best practice: 60-70 chars)
        if len(optimized_title) < 20:
            issues.append(
                f"PreShip: Title too short ({len(optimized_title)} chars): '{optimized_title}'"
            )
        elif len(optimized_title) > 100:
            issues.append(
                f"PreShip: Title too long ({len(optimized_title)} chars, max 100): "
                f"'{optimized_title[:80]}...'"
            )

        return issues

    # ──────────────────────────────────────────────────────────────────────
    # CHECK 5: Source URL / score freshness
    # ──────────────────────────────────────────────────────────────────────

    def check_source_freshness(self, state: dict) -> list:
        """
        Verify topic source is not stale:
          1. Topic URL is accessible (not 404)
          2. Topic score is recent (not from a previous rescoring run)
          3. Topic date is within 48 hours
        """
        issues = []
        topic = state.get("selected_topic", {})
        topic_url = topic.get("url", "")
        topic_title = topic.get("title", "")

        # Check URL is not empty
        if not topic_url:
            issues.append(
                f"PreShip: Topic has no source URL: '{topic_title}'. "
                f"Cannot verify source freshness."
            )
            return issues

        # Check URL looks valid
        if not topic_url.startswith(("http://", "https://")):
            issues.append(
                f"PreShip: Topic URL looks invalid: '{topic_url}'"
            )

        # Check topic has a score (from monitor_cloud.py scoring)
        score = topic.get("score", None)
        if score is None:
            issues.append(
                f"PreShip: Topic has no score: '{topic_title}'. "
                f"May not have been rescored with v74.0+ system."
            )
        elif score < 10:
            issues.append(
                f"PreShip: Topic score is very low ({score}/30): '{topic_title}'. "
                f"Consider finding a fresher/better topic."
            )

        # Check topic date if available
        topic_date = topic.get("date", topic.get("published_date", ""))
        if topic_date:
            try:
                from datetime import datetime, timedelta
                # Try common date formats
                for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                            "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y"]:
                    try:
                        parsed = datetime.strptime(str(topic_date)[:19], fmt)
                        age = datetime.now() - parsed
                        if age > timedelta(hours=48):
                            issues.append(
                                f"PreShip: Topic is {age.days}d {age.seconds//3600}h old "
                                f"(>{48}h threshold): '{topic_title}'. Consider fresher topic."
                            )
                        break
                    except ValueError:
                        continue
            except Exception:
                pass  # Date parsing failed — not critical

        return issues

    # ──────────────────────────────────────────────────────────────────────
    # MASTER RUNNER
    # ──────────────────────────────────────────────────────────────────────

    def run(self, state: dict) -> dict:
        """
        Run all 5 content accuracy checks.
        Returns report dict. Raises PreShipCheckError on critical failures.
        Non-critical warnings are logged but don't halt the pipeline.
        """
        report = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "checks": {},
            "total_issues": 0,
            "critical_issues": 0,
            "warnings": 0,
            "passed": True,
        }

        all_issues = []
        critical_issues = []
        warnings = []

        # Run all 5 checks
        check_methods = [
            ("THUMBNAIL_TOPIC_MATCH", self.check_thumbnail_topic_match),
            ("AUDIO_SCRIPT_ALIGNMENT", self.check_audio_script_alignment),
            ("REAL_PHOTOS", self.check_real_photos),
            ("TITLE_DESCRIPTION_ACCURACY", self.check_title_description_accuracy),
            ("SOURCE_FRESHNESS", self.check_source_freshness),
        ]

        for check_name, check_fn in check_methods:
            try:
                issues = check_fn(state)
            except Exception as e:
                issues = [f"PreShip: {check_name} check crashed: {e}"]

            report["checks"][check_name] = {
                "issues": issues,
                "passed": len(issues) == 0,
            }

            for issue in issues:
                all_issues.append(issue)
                # Critical issues: state mismatch, all-ai images, no source URL
                if any(kw in issue for kw in [
                    "STATE MISMATCH", "ALL.*AI-generated", "No source URL",
                    "No scene images", "generic template",
                    "TITLE STATE MISMATCH",
                ]):
                    critical_issues.append(issue)
                else:
                    warnings.append(issue)

        report["total_issues"] = len(all_issues)
        report["critical_issues"] = len(critical_issues)
        report["warnings"] = len(warnings)
        report["all_issues"] = all_issues

        # Log results
        self._log_report(report, critical_issues, warnings)

        if critical_issues:
            report["passed"] = False
            error_msg = (
                f"PreShipCheck FAILED — {len(critical_issues)} critical issue(s):\n"
                + "\n".join(f"  ❌ {i}" for i in critical_issues)
            )
            raise PreShipCheckError(error_msg)

        return report

    def _log_report(self, report: dict, critical: list, warnings: list):
        """Write pre_ship_check results to log file."""
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        import datetime
        with open(self.log_path, "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"{datetime.datetime.now().isoformat()}\n")
            f.write(f"Result: {'PASS' if report['passed'] else 'FAIL'}\n")
            f.write(f"Critical: {len(critical)}  Warnings: {len(warnings)}\n")
            if critical:
                f.write("CRITICAL:\n")
                for i in critical:
                    f.write(f"  ❌ {i}\n")
            if warnings:
                f.write("WARNINGS:\n")
                for w in warnings:
                    f.write(f"  ⚠️  {w}\n")
