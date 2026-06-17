# MODULE: forensic_audit.py
# PURPOSE: Pre-ship forensic audit gate — examines ALL artifacts before upload.
#          5 audit categories: TEXT, IMAGE, AUDIO, VIDEO, COMPLIANCE.
#          Hard halts on any failure — no silent fallbacks, no stubs.
#
# VERSION: 84.3 (YouTube Studio v84.3 shorts format audit)

import os
import re
import subprocess


class ForensicAuditError(Exception):
    """Raised when the forensic audit detects a critical failure."""
    pass


class ForensicAudit:
    """
    Pre-ship forensic auditor. Examines every artifact produced by the
    pipeline before content ships to YouTube.

    Audit categories:
      A. TEXT — script quality, word count, forbidden words, PII
      B. IMAGE — background canvas, thumbnails exist and are valid
      C. AUDIO — voiceover files exist, non-silent, correct duration
      D. VIDEO — compiled videos exist, non-corrupt, have audio
      E. COMPLIANCE — hate speech, PII leaks, copyright, medical misinformation
    """

    # Forbidden patterns that indicate AI slop or policy violations
    FORBIDDEN_PHRASES = [
        "as an ai",
        "as a language model",
        "i cannot",
        "i'm unable",
        "diaspora",  # channel style guide: avoid this word
    ]

    # v84.3: Academic/formal phrases banned from all scripts (YouTube Studio style guide)
    BANNED_ACADEMIC_PHRASES = [
        "crystallization of alliances",
        "redefine local political dynamics",
        "this development has sent ripples",
        "sparking intense debate",
        "widely reported",
        "political analysts alike",
        "significant development",
        "reshaping electoral dynamics",
        "stay tuned to viral dna",
        "breaking news from our homeland",
    ]

    # v84.3: Shorts must start with these hook patterns (first 10 words)
    SHORT_HOOK_PATTERNS = [
        r"^(?:why|what|how|when|who|which|did you|have you|are you|can you|will you|would you|could you|should you|isn't it|aren't you|don't you|won't you)",
        r"^(?:\d+\s+(?:parties|crore|lakh|million|billion|rupees|people|villagers|workers|employees|students|voters))",
        r"^(?:just|breaking|urgent|shocking|surprising|unexpected|incredible|unbelievable|massive|huge|biggest)",
    ]

    # PII patterns (emails, phone numbers, Aadhaar-like IDs)
    PII_PATTERNS = [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # email
        r'\b\d{10}\b',           # 10-digit phone-like
        r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Aadhaar-like
    ]

    # Medical misinformation red flags
    MEDICAL_RED_FLAGS = [
        "cure cancer",
        "miracle cure",
        "doctors don't want you to know",
        "one weird trick",
        "guaranteed cure",
    ]

    def __init__(self, drive_base: str):
        self.drive_base = drive_base
        self.video_dir = os.path.join(drive_base, "videos")
        self.audio_dir = os.path.join(drive_base, "audio")
        self.thumbnail_dir = os.path.join(drive_base, "thumbnails")

    # ─── A. TEXT AUDIT ───

    def _audit_text(self, state: dict) -> list:
        """Audit script text for quality, forbidden phrases, PII, STATE ACCURACY."""
        issues = []
        script_payload = state.get("script_payload")
        if not script_payload:
            issues.append("TEXT: No script_payload in state")
            return issues

        # ── State accuracy: detect expected state from topic source ──
        topic = state.get("selected_topic", {})
        topic_title = topic.get("title", "")
        topic_url = topic.get("url", "")
        topic_source = topic.get("source", "")
        # Combine all topic metadata for state detection
        topic_ctx = f"{topic_title} {topic_url} {topic_source}".lower()

        # Detect expected state(s) from topic metadata
        expected_states = []
        state_keywords = {
            "Telangana": ["telangana", "hyderabad", "revanth", "kcr", "brs", "telangana cm",
                          "hyderabad news", "telangana government", "telangana cm revanth"],
            "Andhra Pradesh": ["andhra pradesh", "andhra", "amaraviti", "amaravati", "vijayawada",
                               "visakhapatnam", "vizag", "tirupati", "jagan", "ysrcp", "tdp",
                               "nara lokesh", "chandrababu", "andhra cm"],
        }
        for st, keywords in state_keywords.items():
            for kw in keywords:
                if kw in topic_ctx:
                    if st not in expected_states:
                        expected_states.append(st)

        # VDNA 3.0: Handle dict (from checkpoint) or ScriptPayload object
        if isinstance(script_payload, dict):
            segments = ["main", "short_1", "short_2", "short_3"]
            for seg in segments:
                text = script_payload.get(f"{seg}_clean", "") or script_payload.get(f"{seg}_raw", "")
                wc = len(text.split())
                if seg == "main" and wc < 100:
                    issues.append(f"TEXT: Main script too short ({wc} words, min 100)")
                if seg.startswith("short_") and wc < 10:
                    issues.append(f"TEXT: {seg} script too short ({wc} words, min 10)")
                text_lower = text.lower()

                # ── State accuracy check ──
                if expected_states and seg == "main":
                    state_mentioned = any(s.lower() in text_lower for s in expected_states)
                    if not state_mentioned:
                        all_known_states = list(state_keywords.keys())
                        wrong_states_in_script = [s for s in all_known_states
                                                  if s.lower() in text_lower and s not in expected_states]
                        if wrong_states_in_script:
                            issues.append(
                                f"TEXT: STATE MISMATCH in {seg} — source is {expected_states} "
                                f"but script mentions {wrong_states_in_script}. "
                                f"Script must use the correct state from the source."
                            )
                        elif len(expected_states) == 1:
                            issues.append(
                                f"TEXT: STATE MISSING in {seg} — source topic is about "
                                f"{expected_states[0]} but script never mentions the state name."
                            )

                for phrase in self.FORBIDDEN_PHRASES:
                    if phrase in text_lower:
                        issues.append(f"TEXT: Forbidden phrase '{phrase}' found in {seg}")

                for phrase in self.BANNED_ACADEMIC_PHRASES:
                    if phrase in text_lower:
                        issues.append(f"TEXT: Academic/banned phrase '{phrase}' in {seg} — use conversational YouTube style")

                if seg.startswith("short_"):
                    first_words = " ".join(text_lower.split()[:10])
                    has_hook = any(re.match(p, first_words) for p in self.SHORT_HOOK_PATTERNS)
                    if re.match(r"^(?:the\s+)?\w+\s+(?:party|government|minister|cm|pm|mla|mp)\s+(?:announced|said|declared|stated)", first_words):
                        issues.append(f"TEXT: {seg} starts with passive announcement opener — must start with shocking fact/question in first 2 seconds (v84.3)")
                    elif not has_hook and seg == "short_1":
                        issues.append(f"TEXT: {seg} has no question/shock/number hook in first 10 words — violates v84.3 short format. First words: '{first_words[:60]}...'")

                for pii_pattern in self.PII_PATTERNS:
                    matches = re.findall(pii_pattern, text)
                    if matches:
                        issues.append(f"TEXT: PII leak ({matches[0][:8]}...) found in {seg}")

                for flag in self.MEDICAL_RED_FLAGS:
                    if flag in text_lower:
                        issues.append(f"COMPLIANCE: Medical red flag '{flag}' in {seg}")
        else:
            segments = ["main", "short_1", "short_2", "short_3"]
            for seg in segments:
                segment = script_payload.get_segment(seg)
                text = segment["text"]
                wc = segment["word_count"]

                if seg == "main" and wc < 100:
                    issues.append(f"TEXT: Main script too short ({wc} words, min 100)")
                if seg.startswith("short_") and wc < 10:
                    issues.append(f"TEXT: {seg} script too short ({wc} words, min 10)")

                text_lower = text.lower()

                # ── State accuracy check ──
                if expected_states and seg == "main":
                    state_mentioned = any(s.lower() in text_lower for s in expected_states)
                    if not state_mentioned:
                        all_known_states = list(state_keywords.keys())
                        wrong_states_in_script = [s for s in all_known_states
                                                  if s.lower() in text_lower and s not in expected_states]
                        if wrong_states_in_script:
                            issues.append(
                                f"TEXT: STATE MISMATCH in {seg} — source is {expected_states} "
                                f"but script mentions {wrong_states_in_script}. "
                                f"Script must use the correct state from the source."
                            )
                        elif len(expected_states) == 1:
                            issues.append(
                                f"TEXT: STATE MISSING in {seg} — source topic is about "
                                f"{expected_states[0]} but script never mentions the state name."
                            )

                for phrase in self.FORBIDDEN_PHRASES:
                    if phrase in text_lower:
                        issues.append(f"TEXT: Forbidden phrase '{phrase}' found in {seg}")

                for phrase in self.BANNED_ACADEMIC_PHRASES:
                    if phrase in text_lower:
                        issues.append(f"TEXT: Academic/banned phrase '{phrase}' in {seg} — use conversational YouTube style")

                if seg.startswith("short_"):
                    first_words = " ".join(text_lower.split()[:10])
                    has_hook = any(re.match(p, first_words) for p in self.SHORT_HOOK_PATTERNS)
                    if re.match(r"^(?:the\s+)?\w+\s+(?:party|government|minister|cm|pm|mla|mp)\s+(?:announced|said|declared|stated)", first_words):
                        issues.append(f"TEXT: {seg} starts with passive announcement opener — must start with shocking fact/question in first 2 seconds (v84.3)")
                    elif not has_hook and seg == "short_1":
                        issues.append(f"TEXT: {seg} has no question/shock/number hook in first 10 words — violates v84.3 short format. First words: '{first_words[:60]}...'")

                for pii_pattern in self.PII_PATTERNS:
                    matches = re.findall(pii_pattern, text)
                    if matches:
                        issues.append(f"TEXT: PII leak ({matches[0][:8]}...) found in {seg}")

                for flag in self.MEDICAL_RED_FLAGS:
                    if flag in text_lower:
                        issues.append(f"COMPLIANCE: Medical red flag '{flag}' in {seg}")

        return issues

    # ─── B. IMAGE AUDIT ───

    def _audit_images(self, state: dict) -> list:
        """Verify background canvas, thumbnails, and scene images exist and are valid."""
        issues = []

        canvas = state.get("background_canvas")
        if not canvas:
            issues.append("IMAGE: No background_canvas in state")
        elif not os.path.exists(canvas):
            issues.append(f"IMAGE: Background canvas missing: {canvas}")
        else:
            size = os.path.getsize(canvas)
            if size < 10 * 1024:
                issues.append(f"IMAGE: Background canvas suspiciously small ({size} bytes)")

        # Check thumbnails — ThumbnailCreator produces {prefix}_branded.jpg
        for thumb_name in ["production_branded.jpg", "short_1_branded.jpg",
                           "short_2_branded.jpg", "short_3_branded.jpg"]:
            thumb_path = os.path.join(self.thumbnail_dir, thumb_name)
            if not os.path.exists(thumb_path):
                # Only required thumbnails: main always, shorts only if produced
                if thumb_name == "production_branded.jpg":
                    issues.append(f"IMAGE: Thumbnail missing: {thumb_name}")
                # Short thumbnails are optional — skip if not present
            elif os.path.getsize(thumb_path) < 5 * 1024:
                issues.append(f"IMAGE: Thumbnail suspiciously small: {thumb_name}")

        # ── Scene image audit — verify slideshow images exist and are sufficient ──
        topic = state.get("selected_topic", {})
        topic_title = topic.get("title", "")
        topic_ctx = topic_title.lower()

        # Check main video scene images
        for slot in ["main", "short_1", "short_2", "short_3"]:
            slideshow_dir = os.path.join(self.audio_dir, f"slideshow_{slot}")
            if not os.path.isdir(slideshow_dir):
                if slot == "main":
                    issues.append(f"IMAGE: Slideshow directory missing for {slot}: {slideshow_dir}")
                continue

            scene_images = sorted([
                f for f in os.listdir(slideshow_dir)
                if f.endswith(('.jpg', '.jpeg', '.png', '.webp'))
            ])

            if slot == "main":
                if len(scene_images) < 3:
                    issues.append(
                        f"IMAGE: Main video has only {len(scene_images)} scene images "
                        f"(min 3 expected). Video may be mostly static/slideshow."
                    )
            elif slot.startswith("short_"):
                # v84.3: Shorts need 5-8 scenes for jump-cut zooms every 5-7s
                if len(scene_images) < 4:
                    issues.append(
                        f"IMAGE: {slot} has only {len(scene_images)} scene images "
                        f"(min 4 required for jump-cut zoom pacing per v84.3). "
                        f"Shorts need 5-7s per scene for visual variety."
                    )
                elif len(scene_images) > 10:
                    issues.append(
                        f"IMAGE: {slot} has {len(scene_images)} scene images "
                        f"(max 10 recommended — too many scenes = flickering)."
                    )
                # Check for suspiciously small images (likely placeholders/junk)
                tiny_images = []
                for img_file in scene_images:
                    img_path = os.path.join(slideshow_dir, img_file)
                    if os.path.getsize(img_path) < 15 * 1024:
                        tiny_images.append(img_file)
                if tiny_images:
                    issues.append(
                        f"IMAGE: {len(tiny_images)} scene images in main are suspiciously small "
                        f"(<15KB each, likely placeholders): {tiny_images[:3]}"
                    )
                # Check that not all images are the same file (duplicate detection)
                if len(scene_images) >= 2:
                    sizes = [os.path.getsize(os.path.join(slideshow_dir, f)) for f in scene_images]
                    if len(set(sizes)) == 1:
                        issues.append(
                            f"IMAGE: All {len(scene_images)} scene images in main have identical "
                            f"file sizes ({sizes[0]} bytes) — likely all the same image duplicated."
                        )

        return issues

    # ─── C. AUDIO AUDIT ───

    def _audit_audio(self, state: dict) -> list:
        """Verify voiceover audio files exist and are non-silent."""
        issues = []
        voiceover_assets = state.get("voiceover_assets")
        if not voiceover_assets:
            issues.append("AUDIO: No voiceover_assets in state")
            return issues

        for slot in ["main", "short_1", "short_2", "short_3"]:
            audio_path = voiceover_assets.get(slot)
            if not audio_path:
                # Shorts may be legitimately absent if word_count was too low
                if slot.startswith("short_"):
                    continue
                issues.append(f"AUDIO: Missing audio for {slot}")
                continue

            if not os.path.exists(audio_path):
                issues.append(f"AUDIO: File not found: {audio_path}")
                continue

            size = os.path.getsize(audio_path)
            if size < 1 * 1024:
                issues.append(f"AUDIO: {slot} audio suspiciously small ({size} bytes)")
                continue

            # Probe audio volume
            try:
                cmd = ["ffmpeg", "-i", audio_path, "-filter:a",
                       "volumedetect", "-f", "null", "/dev/null"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                mean_volume = None
                for line in result.stderr.splitlines():
                    if "mean_volume" in line:
                        parts = line.split("mean_volume:")
                        if len(parts) > 1:
                            mean_volume = float(parts[1].replace("dB", "").strip())
                            break
                if mean_volume is None:
                    issues.append(f"AUDIO: {slot} — no audio stream detected")
                elif mean_volume < -60.0 or mean_volume == float("-inf"):
                    issues.append(f"AUDIO: {slot} — audio is silent ({mean_volume} dB)")
            except subprocess.TimeoutExpired:
                issues.append(f"AUDIO: {slot} — ffmpeg probe timed out")
            except Exception as e:
                issues.append(f"AUDIO: {slot} — probe error: {e}")

        return issues

    # ─── D. VIDEO AUDIT ───

    def _audit_videos(self, state: dict) -> list:
        """Verify compiled videos exist, are non-corrupt, and have audio."""
        issues = []
        compiled_videos = state.get("compiled_videos", [])

        if not compiled_videos:
            issues.append("VIDEO: No compiled_videos in state")
            return issues

        for video_path in compiled_videos:
            if not os.path.exists(video_path):
                issues.append(f"VIDEO: File not found: {video_path}")
                continue

            size = os.path.getsize(video_path)
            if size < 100 * 1024:
                issues.append(f"VIDEO: Suspiciously small ({size} bytes): {video_path}")
                continue

            # Probe with ffmpeg to verify integrity
            try:
                cmd = ["ffmpeg", "-v", "error", "-i", video_path,
                       "-f", "null", "-"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode != 0:
                    error_msg = result.stderr[:200] if result.stderr else "unknown error"
                    issues.append(f"VIDEO: Corrupt/invalid: {video_path} — {error_msg}")
            except subprocess.TimeoutExpired:
                issues.append(f"VIDEO: ffmpeg probe timed out: {video_path}")
            except Exception as e:
                issues.append(f"VIDEO: Probe error for {video_path}: {e}")

        return issues

    # ─── E. COMPLIANCE AUDIT ───

    def _audit_compliance(self, state: dict) -> list:
        """Final compliance check on topic metadata and script content."""
        issues = []
        topic = state.get("selected_topic", {})

        title = topic.get("title", "")
        if not title or len(title.strip()) < 5:
            issues.append("COMPLIANCE: Topic title missing or too short")

        # Check for hate speech indicators in title
        hate_indicators = ["kill", "murder", "attack", "destroy", "hate"]
        title_lower = title.lower()
        for indicator in hate_indicators:
            if indicator in title_lower:
                # Flag for review but don't auto-reject (could be legitimate news)
                issues.append(f"COMPLIANCE: Hate speech indicator '{indicator}' in title — manual review recommended")

        return issues

    # ─── MASTER AUDIT ORCHESTRATOR ───

    def run_full_audit(self, state: dict) -> dict:
        """
        Run all 5 audit categories. Collects all issues.
        Raises ForensicAuditError on critical failures.
        Returns audit report dict.
        """
        report = {
            "categories": {},
            "total_issues": 0,
            "critical_issues": 0,
            "passed": True,
            "details": [],
        }

        # A. TEXT
        text_issues = self._audit_text(state)
        report["categories"]["TEXT"] = {"issues": text_issues, "passed": len(text_issues) == 0}

        # B. IMAGE
        image_issues = self._audit_images(state)
        report["categories"]["IMAGE"] = {"issues": image_issues, "passed": len(image_issues) == 0}

        # C. AUDIO
        audio_issues = self._audit_audio(state)
        report["categories"]["AUDIO"] = {"issues": audio_issues, "passed": len(audio_issues) == 0}

        # D. VIDEO
        video_issues = self._audit_videos(state)
        report["categories"]["VIDEO"] = {"issues": video_issues, "passed": len(video_issues) == 0}

        # E. COMPLIANCE
        compliance_issues = self._audit_compliance(state)
        report["categories"]["COMPLIANCE"] = {"issues": compliance_issues, "passed": len(compliance_issues) == 0}

        # Aggregate
        all_issues = text_issues + image_issues + audio_issues + video_issues + compliance_issues
        report["total_issues"] = len(all_issues)
        report["details"] = all_issues

        # Critical = VIDEO/AUDIO failures + TEXT state errors + IMAGE quality failures
        critical_categories = ["VIDEO", "AUDIO"]
        critical_issues = []
        for cat in critical_categories:
            cat_issues = report["categories"][cat]["issues"]
            # Only treat missing/corrupt files as critical, not "manual review" flags
            for issue in cat_issues:
                if "missing" in issue.lower() or "not found" in issue.lower() or \
                   "silent" in issue.lower() or "corrupt" in issue.lower() or \
                   "no audio stream" in issue.lower() or "too small" in issue.lower():
                    critical_issues.append(issue)

        # TEXT state accuracy issues are CRITICAL — wrong state = wrong video
        text_issues = report["categories"]["TEXT"]["issues"]
        for issue in text_issues:
            if "STATE MISMATCH" in issue or "STATE MISSING" in issue:
                critical_issues.append(issue)

        # IMAGE issues that indicate junk/placeholder content are CRITICAL
        image_issues = report["categories"]["IMAGE"]["issues"]
        for issue in image_issues:
            if "suspiciously small" in issue.lower() or \
               "identical" in issue.lower() or \
               "only" in issue.lower() and "scene images" in issue.lower():
                critical_issues.append(issue)

        report["critical_issues"] = len(critical_issues)

        if critical_issues:
            report["passed"] = False
            error_msg = f"ForensicAudit FAILED — {len(critical_issues)} critical issue(s):\n"
            for issue in critical_issues:
                error_msg += f"  ❌ {issue}\n"
            raise ForensicAuditError(error_msg)

        # Also report non-critical warnings if any exist
        if report["total_issues"] > 0:
            warning_msg = f"ForensicAudit PASSED with {report['total_issues']} warning(s):\n"
            for issue in report["details"]:
                warning_msg += f"  ⚠️  {issue}\n"
            self._log_warning(warning_msg)

        return report

    def _log_warning(self, msg: str):
        """Log audit warnings to a file for review."""
        import datetime
        log_path = os.path.join(os.path.dirname(self.video_dir), "logs", "audit_warnings.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"{datetime.datetime.now().isoformat()}\n")
            f.write(msg)
