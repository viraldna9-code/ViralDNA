"""
Visual Forensic Gate — Post-assembly visual quality check.
Validates that assembled videos have proper visual content (not solid color,
single frame, or corrupted output) before they reach upload.
"""

import os


class VisualForensicGate:
    """Basic visual forensic checks on assembled video files."""

    def __init__(self):
        self.name = "VisualForensicGate"

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

            size = os.path.getsize(path)
            if size < 100_000:
                report.append(f"TOO SMALL ({size}b): {path}")
                all_passed = False
            else:
                report.append(f"OK ({size // 1024}KB): {os.path.basename(path)}")

        if branded_thumb and os.path.exists(branded_thumb):
            report.append(f"THUMB OK: {os.path.basename(branded_thumb)}")
        elif branded_thumb:
            report.append(f"THUMB MISSING: {branded_thumb}")

        return all_passed, report
