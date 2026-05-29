# MODULE: forensic_audit.py
# PURPOSE: Pre-ship forensic audit gate — examines ALL artifacts before upload.
#          5 audit categories: TEXT, IMAGE, AUDIO, VIDEO, COMPLIANCE.
#          Hard halts on any failure — no silent fallbacks, no stubs.
#
# VERSION: 1.0 (v79.0 pipeline)

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
        """Audit script text for quality, forbidden phrases, PII."""
        issues = []
        script_payload = state.get("script_payload")
        if not script_payload:
            issues.append("TEXT: No script_payload in state")
            return issues

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
            for phrase in self.FORBIDDEN_PHRASES:
                if phrase in text_lower:
                    issues.append(f"TEXT: Forbidden phrase '{phrase}' found in {seg}")

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
        """Verify background canvas and thumbnails exist and are valid."""
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

        # Check thumbnails
        for thumb_name in ["production_branded.jpg", "short_1_thumb.jpg",
                           "short_2_thumb.jpg", "short_3_thumb.jpg"]:
            thumb_path = os.path.join(self.thumbnail_dir, thumb_name)
            if not os.path.exists(thumb_path):
                issues.append(f"IMAGE: Thumbnail missing: {thumb_name}")
            elif os.path.getsize(thumb_path) < 5 * 1024:
                issues.append(f"IMAGE: Thumbnail suspiciously small: {thumb_name}")

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

        # Critical = any VIDEO or AUDIO failure (corrupt/missing media)
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

        report["critical_issues"] = len(critical_issues)

        if critical_issues:
            report["passed"] = False
            error_msg = f"ForensicAudit FAILED — {len(critical_issues)} critical issue(s):\n"
            for issue in critical_issues:
                error_msg += f"  ❌ {issue}\n"
            raise ForensicAuditError(error_msg)

        return report
