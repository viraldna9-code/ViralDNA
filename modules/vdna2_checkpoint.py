"""
VDNA 2.0 — Checkpoint/Resume System
=====================================
Disk-based state persistence so any worker can crash and resume
without losing progress or restarting the whole pipeline.

Each worker phase writes a JSON checkpoint file:
  /home/jay/ViralDNA/.vdna2/checkpoints/{run_id}/{phase}.json

On resume, the Director reads the latest checkpoint and skips
already-completed phases.

Crash prevention:
- Atomic writes (write to .tmp, then rename)
- Timeout enforcement per phase
- Disk space monitoring before writes
- Graceful SIGTERM handling
"""

import os
import json
import time
import shutil
import signal
import tempfile
from datetime import datetime
from pathlib import Path

CHECKPOINT_DIR = "/home/jay/ViralDNA/.vdna2/checkpoints"
MAX_CHECKPOINT_AGE_HOURS = 48  # Auto-cleanup old runs
MIN_DISK_SPACE_MB = 500        # Refuse to write if disk < 500MB


class CheckpointError(Exception):
    """Raised when checkpoint operations fail critically."""
    pass


class DiskSpaceError(CheckpointError):
    """Raised when disk space is critically low."""
    pass


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _atomic_write_json(data, filepath):
    """Write JSON atomically — write to .tmp then rename. Prevents corruption on crash."""
    _ensure_dir(os.path.dirname(filepath))
    dir_name = os.path.dirname(filepath) or "."
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, filepath)
    except Exception as e:
        # Clean up temp file on failure
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise CheckpointError(f"Atomic write failed for {filepath}: {e}")


def _check_disk_space(path=CHECKPOINT_DIR):
    """Check available disk space. Raises DiskSpaceError if critically low."""
    try:
        stat = shutil.disk_usage(path if os.path.exists(path) else "/home/jay")
        free_mb = stat.free / (1024 * 1024)
        if free_mb < MIN_DISK_SPACE_MB:
            raise DiskSpaceError(
                f"Disk space critically low: {free_mb:.0f}MB free "
                f"(minimum {MIN_DISK_SPACE_MB}MB required)"
            )
        return free_mb
    except DiskSpaceError:
        raise
    except Exception:
        return None  # If we can't check, proceed with caution


class CheckpointManager:
    """
    Manages checkpoint lifecycle for a single pipeline run.

    Usage:
        mgr = CheckpointManager(run_id="20260613_1000")
        mgr.save("discovery", {"topics": [...], "count": 5})
        state = mgr.load("discovery")  # None if not found
        completed = mgr.get_completed_phases()  # ["discovery", "weighting"]
        mgr.cleanup()  # Remove old checkpoints
    """

    def __init__(self, run_id=None):
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M")
        self.run_dir = os.path.join(CHECKPOINT_DIR, self.run_id)
        _ensure_dir(self.run_dir)

    def save(self, phase, data):
        """
        Save checkpoint for a phase. Atomic write prevents corruption.
        Adds timestamp and phase metadata.
        """
        _check_disk_space(self.run_dir)
        checkpoint = {
            "phase": phase,
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "epoch": time.time(),
            "data": data,
        }
        filepath = os.path.join(self.run_dir, f"{phase}.json")
        _atomic_write_json(checkpoint, filepath)
        return filepath

    def load(self, phase):
        """Load checkpoint data for a phase. Returns None if not found."""
        filepath = os.path.join(self.run_dir, f"{phase}.json")
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r") as f:
                checkpoint = json.load(f)
            return checkpoint.get("data", checkpoint)
        except (json.JSONDecodeError, IOError) as e:
            # Corrupted checkpoint — remove it so we don't loop on bad data
            try:
                os.remove(filepath)
            except OSError:
                pass
            return None

    def is_phase_complete(self, phase):
        """Check if a phase has a valid checkpoint."""
        filepath = os.path.join(self.run_dir, f"{phase}.json")
        return os.path.exists(filepath) and os.path.getsize(filepath) > 0

    def get_completed_phases(self):
        """Return list of completed phase names, sorted alphabetically."""
        if not os.path.exists(self.run_dir):
            return []
        phases = []
        for f in os.listdir(self.run_dir):
            if f.endswith(".json"):
                phase_name = f[:-5]  # Remove .json
                filepath = os.path.join(self.run_dir, f)
                if os.path.getsize(filepath) > 0:
                    phases.append(phase_name)
        return sorted(phases)

    def get_run_metadata(self):
        """Return metadata about this run."""
        phases = self.get_completed_phases()
        total_size = 0
        for f in os.listdir(self.run_dir):
            fp = os.path.join(self.run_dir, f)
            if os.path.isfile(fp):
                total_size += os.path.getsize(fp)
        return {
            "run_id": self.run_id,
            "phases_completed": phases,
            "total_phases": len(phases),
            "total_size_kb": round(total_size / 1024, 1),
            "run_dir": self.run_dir,
        }

    def cleanup(self, max_age_hours=MAX_CHECKPOINT_AGE_HOURS):
        """Remove checkpoint runs older than max_age_hours."""
        if not os.path.exists(CHECKPOINT_DIR):
            return 0
        removed = 0
        cutoff = time.time() - (max_age_hours * 3600)
        for run_dir_name in os.listdir(CHECKPOINT_DIR):
            run_path = os.path.join(CHECKPOINT_DIR, run_dir_name)
            if not os.path.isdir(run_path):
                continue
            try:
                dir_mtime = os.path.getmtime(run_path)
                if dir_mtime < cutoff:
                    shutil.rmtree(run_path)
                    removed += 1
            except OSError:
                pass
        return removed

    @staticmethod
    def list_runs():
        """List all checkpoint runs with metadata."""
        if not os.path.exists(CHECKPOINT_DIR):
            return []
        runs = []
        for run_dir_name in sorted(os.listdir(CHECKPOINT_DIR), reverse=True):
            run_path = os.path.join(CHECKPOINT_DIR, run_dir_name)
            if not os.path.isdir(run_path):
                continue
            mgr = CheckpointManager(run_id=run_dir_name)
            runs.append(mgr.get_run_metadata())
        return runs


class PhaseTimer:
    """
    Context manager for timing phases with timeout enforcement.

    Usage:
        with PhaseTimer("discovery", timeout=300) as timer:
            # ... do work ...
            timer.checkpoint("halfway", {"progress": 50})
        # Automatically logs elapsed time

    Raises TimeoutError if elapsed exceeds timeout seconds.
    """

    def __init__(self, phase_name, timeout=600):
        self.phase_name = phase_name
        self.timeout = timeout
        self.start_time = None
        self.elapsed = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.perf_counter() - self.start_time
        status = "FAIL" if exc_type else "OK"
        print(f"   ⏱️  [{self.phase_name}] {status} in {self.elapsed:.1f}s (timeout: {self.timeout}s)")
        if self.elapsed > self.timeout and exc_type is None:
            print(f"   ⚠️  [{self.phase_name}] Exceeded timeout ({self.timeout}s) — consider increasing limit")
        return False  # Don't suppress exceptions

    def check_remaining(self):
        """Check remaining time. Raises TimeoutError if exceeded."""
        elapsed = time.perf_counter() - self.start_time
        if elapsed > self.timeout:
            raise TimeoutError(
                f"Phase '{self.phase_name}' exceeded {self.timeout}s timeout "
                f"(elapsed: {elapsed:.1f}s)"
            )
        return self.timeout - elapsed


def setup_signal_handlers():
    """
    Set up graceful SIGTERM/SIGINT handlers.
    Instead of crashing, set a flag that workers can check.
    """
    _shutdown_requested = False

    def _handle_signal(signum, frame):
        nonlocal _shutdown_requested
        _shutdown_requested = True
        sig_name = signal.Signals(signum).name
        print(f"\n   ⚠️  Received {sig_name} — graceful shutdown requested (finish current segment)")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    return lambda: _shutdown_requested


# ── Module-level convenience ──

def get_checkpoint_manager(run_id=None):
    """Get a CheckpointManager instance."""
    return CheckpointManager(run_id=run_id)


def cleanup_old_checkpoints(max_age_hours=MAX_CHECKPOINT_AGE_HOURS):
    """Clean up old checkpoint runs. Returns count removed."""
    mgr = CheckpointManager(run_id="_cleanup")
    return mgr.cleanup(max_age_hours=max_age_hours)


if __name__ == "__main__":
    # Quick self-test
    print("=== Checkpoint System Self-Test ===\n")

    # Test 1: Save and load
    mgr = CheckpointManager(run_id="test_001")
    mgr.save("discovery", {"topics": ["A", "B", "C"], "count": 3})
    data = mgr.load("discovery")
    assert data["count"] == 3, f"Expected 3, got {data['count']}"
    print("✅ Test 1: Save/Load — OK")

    # Test 2: Phase completion check
    assert mgr.is_phase_complete("discovery") is True
    assert mgr.is_phase_complete("scripting") is False
    print("✅ Test 2: Phase completion — OK")

    # Test 3: Completed phases list
    mgr.save("scripting", {"script": "Hello world"})
    phases = mgr.get_completed_phases()
    assert "discovery" in phases and "scripting" in phases
    print("✅ Test 3: Completed phases list — OK")

    # Test 4: Metadata
    meta = mgr.get_run_metadata()
    assert meta["run_id"] == "test_001"
    assert meta["total_phases"] == 2
    print("✅ Test 4: Metadata — OK")

    # Test 5: PhaseTimer
    with PhaseTimer("test_phase", timeout=10) as timer:
        time.sleep(0.1)
    assert timer.elapsed < 1.0
    print("✅ Test 5: PhaseTimer — OK")

    # Test 6: Disk space check
    free = _check_disk_space()
    if free:
        print(f"✅ Test 6: Disk space check — {free:.0f}MB free")
    else:
        print("⚠️  Test 6: Disk space check unavailable (non-fatal)")

    # Cleanup test data
    shutil.rmtree(mgr.run_dir, ignore_errors=True)
    print("\n✅ All tests passed. Checkpoint system ready.")
