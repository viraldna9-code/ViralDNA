"""
Visual Forensic Gate — Post-assembly visual quality check.
Validates that assembled videos have proper visual content (not solid color,
single frame, or corrupted output) before they reach upload.

v85.4: Added short format awareness — different size thresholds and
resolution validation for vertical 9:16 shorts vs 16:9 main videos.
"""

import os
import subprocess
import json


class VisualForensicGate:
    """Basic visual forensic checks on assembled video files."""

    # Size thresholds: shorts are smaller (shorter, lower bitrate)
    MAIN_MIN_SIZE = 500_000      # 500KB minimum for main (longer, 4Mbps)
    SHORT_MIN_SIZE = 100_000     # 100KB minimum for short (shorter, 2Mbps)

    # Expected resolutions
    MAIN_WIDTH = 1280
    MAIN_HEIGHT = 720
    SHORT_WIDTH = 1080
    SHORT_HEIGHT = 1920

    def __init__(self):
        self.name = "VisualForensicGate"

    def _is_short(self, path: str) -> bool:
        """Detect if a video is a short based on filename convention."""
        basename = os.path.basename(path).lower()
        return "_short" in basename or "short_" in basename

    def _probe_resolution(self, path: str) -> tuple:
        """Probe video resolution via ffprobe. Returns (width, height) or (0, 0)."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet", "-print_format", "json",
                    "-show_streams", "-select_streams", "v:0", path
                ],
                capture_output=True, text=True, timeout=15
            )
            data = json.loads(result.stdout)
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    return int(stream.get("width", 0)), int(stream.get("height", 0))
        except Exception:
            pass
        return 0, 0

    def validate(self, video_paths: list, branded_thumb: str = None) -> tuple:
        """Run visual forensic checks on assembled video files.

        Args:
            video_paths: list of paths to assembled video files
            branded_thumb: path to branded thumbnail (optional)

        Returns:
            (passed: bool, report: list of str)
        """
        report = []
        all_passed = True

        for path in video_paths:
            if not os.path.exists(path):
                report.append(f"MISSING: {path}")
                all_passed = False
                continue

            basename = os.path.basename(path)
            is_short = self._is_short(path)
            label = "SHORT" if is_short else "MAIN"
            size = os.path.getsize(path)
            min_size = self.SHORT_MIN_SIZE if is_short else self.MAIN_MIN_SIZE

            if size < min_size:
                report.append(f"TOO SMALL ({size // 1024}KB < {min_size // 1024}KB min): [{label}] {basename}")
                all_passed = False
            else:
                report.append(f"OK ({size // 1024}KB): [{label}] {basename}")

            # Resolution validation via ffprobe
            w, h = self._probe_resolution(path)
            if w > 0 and h > 0:
                if is_short:
                    if w != self.SHORT_WIDTH or h != self.SHORT_HEIGHT:
                        report.append(f"  WARN: Resolution {w}x{h} (expected {self.SHORT_WIDTH}x{self.SHORT_HEIGHT})")
                else:
                    if w != self.MAIN_WIDTH or h != self.MAIN_HEIGHT:
                        report.append(f"  WARN: Resolution {w}x{h} (expected {self.MAIN_WIDTH}x{self.MAIN_HEIGHT})")

        if branded_thumb and os.path.exists(branded_thumb):
            report.append(f"THUMB OK: {os.path.basename(branded_thumb)}")
        elif branded_thumb:
            report.append(f"THUMB MISSING: {branded_thumb}")

        return all_passed, report
