"""
Cleanup Agent v3.0 — VDNA 3.0 Port
Pre-pipeline cleanup: removes temp files, stale outputs, disk space check.
Ported from old pipeline's CleanupAgent.
"""
import os, shutil, glob


class CleanupAgent:
    """
    Pre-pipeline cleanup: removes temp files and stale outputs from previous runs.
    Non-fatal: cleanup errors don't block the pipeline.
    """

    CLEANUP_PATHS = [
        ("/home/jay/ViralDNA/audio", "*.mp3"),
        ("/home/jay/ViralDNA/audio", "*.wav"),
        ("/home/jay/ViralDNA/audio", "*.ass"),
        ("/home/jay/ViralDNA/audio", "*.srt"),
        ("/home/jay/ViralDNA/audio", "slideshow_*"),
        ("/home/jay/ViralDNA/output/runtime", "viz_*"),
        ("/home/jay/ViralDNA/output/runtime", "work_*"),
        ("/home/jay/ViralDNA/output/runtime", "phase*_debug.json"),
        ("/home/jay/ViralDNA/output/runtime", "dry_run_*.log"),
        ("/home/jay/ViralDNA/output/runtime", "*.log"),
        ("/home/jay/ViralDNA/output/runtime", "silence_*.mp3"),
        ("/home/jay/ViralDNA/runtime", "*"),
    ]

    def __init__(self, *args, **kwargs):
        pass

    def cleanup(self) -> dict:
        """Run cleanup. Returns stats dict."""
        cleaned = 0
        errors = 0
        freed_bytes = 0

        for directory, pattern in self.CLEANUP_PATHS:
            if not os.path.isdir(directory):
                continue
            try:
                for filename in os.listdir(directory):
                    if self._matches_pattern(filename, pattern):
                        filepath = os.path.join(directory, filename)
                        try:
                            if os.path.isfile(filepath):
                                freed_bytes += os.path.getsize(filepath)
                                os.remove(filepath)
                                cleaned += 1
                            elif os.path.isdir(filepath):
                                freed_bytes += self._dir_size(filepath)
                                shutil.rmtree(filepath)
                                cleaned += 1
                        except Exception:
                            errors += 1
            except Exception:
                pass

        # Clean __pycache__
        modules_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules")
        for root, dirs, files in os.walk(modules_dir):
            if "__pycache__" in dirs:
                cache_dir = os.path.join(root, "__pycache__")
                try:
                    shutil.rmtree(cache_dir)
                    cleaned += 1
                except Exception:
                    pass

        freed_mb = round(freed_bytes / (1024 * 1024), 2)
        return {
            "cleaned": cleaned,
            "errors": errors,
            "freed_mb": freed_mb,
        }

    def check_disk_space(self, min_free_gb: float = 5.0) -> dict:
        """Check available disk space."""
        try:
            stat = os.statvfs("/home/jay")
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
            return {
                "free_gb": round(free_gb, 2),
                "sufficient": free_gb >= min_free_gb,
                "min_required_gb": min_free_gb,
            }
        except Exception:
            return {"free_gb": -1, "sufficient": True, "min_required_gb": min_free_gb}

    @staticmethod
    def _matches_pattern(filename: str, pattern: str) -> bool:
        if pattern == "*":
            return True
        if pattern.startswith("*"):
            return filename.endswith(pattern[1:])
        if pattern.endswith("*"):
            return filename.startswith(pattern[:-1])
        return filename == pattern

    @staticmethod
    def _dir_size(path: str) -> int:
        total = 0
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
        return total

    def execute(self, state):
        return state
