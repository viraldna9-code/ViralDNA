#!/usr/bin/env python3
"""
ffmpeg_filter_precheck.py — FFmpeg Filter Pre-Flight Checker for ViralDNA
=========================================================================
Tests that required FFmpeg filters are available AND that known-problematic
filter expressions actually work before any pipeline run.

Usage:
  python3 ffmpeg_filter_precheck.py          # Run all checks
  python3 ffmpeg_filter_precheck.py --json   # Machine-readable output
  python3 ffmpeg_filter_precheck.py --fix    # Auto-fix known issues

Exit codes:
  0 = All checks passed
  1 = One or more checks failed (see output)
  2 = FFmpeg not found or not executable
"""

import subprocess
import sys
import os
import json
import tempfile

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# ═══════════════════════════════════════════════════════════════
# KNOWN PROBLEMATIC FILTER PATTERNS
# These have bitten the ViralDNA pipeline before.
# ═══════════════════════════════════════════════════════════════

KNOWN_ISSUES = {
    "drawbox_w_h_variables": {
        "description": "FFmpeg drawbox filter does NOT support 'w' and 'h' "
                       "expressions (unlike drawtext). Must use explicit pixel values.",
        "broken":   "[0]drawbox=x=0:y=0:w=w:h=6:color=red@0.9:t=fill",
        "working":  "[0]drawbox=x=0:y=0:w=320:h=6:color=red@0.9:t=fill",
        "fix_hint": "Replace 'w=w' with 'w=<width>' and 'y=h-6' with 'y=<height-6>' "
                    "using explicit integer values in your Python code.",
    },
    "drawtext_w_h_ok": {
        "description": "FFmpeg drawtext DOES support w/h variables (confirming build).",
        "broken":   None,
        "working":  "[0]drawtext=text='Test':fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2:fontcolor=white",
        "fix_hint": None,
    },
    "zoompan_iw_ih": {
        "description": "zoompan uses iw/ih for input dimensions (not w/h).",
        "broken":   "[0]zoompan=z='zoom+0.001':x='w/2-(w/zoom/2)':y='h/2-(h/zoom/2)':d=30:s=320x240:fps=30",
        "working":  "[0]zoompan=z='zoom+0.001':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=30:s=320x240:fps=30",
        "fix_hint": "In zoompan, always use iw/ih for input dimensions, not w/h.",
    },
}

# ═══════════════════════════════════════════════════════════════
# REQUIRED FILTERS FOR VIRALDNA PIPELINE
# ═══════════════════════════════════════════════════════════════

REQUIRED_FILTERS = [
    "drawbox",
    "drawtext",
    "zoompan",
    "overlay",
    "color",
    "concat",
    "scale",
    "format",
    "geq",
    "amix",
    "aresample",
    "volume",
    "volumedetect",
]

# ═══════════════════════════════════════════════════════════════
# REQUIRED FONTS
# ═══════════════════════════════════════════════════════════════

REQUIRED_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

# ═══════════════════════════════════════════════════════════════
# CHECK FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def check_ffmpeg_available():
    """Verify ffmpeg and ffprobe are on PATH and executable."""
    results = {}
    for binary in ["ffmpeg", "ffprobe"]:
        try:
            r = subprocess.run(
                [binary, "-version"],
                capture_output=True, text=True, timeout=10
            )
            version_line = r.stdout.split("\n")[0] if r.stdout else "unknown"
            results[binary] = {"ok": True, "version": version_line}
        except FileNotFoundError:
            results[binary] = {"ok": False, "error": f"{binary} not found on PATH"}
        except Exception as e:
            results[binary] = {"ok": False, "error": str(e)}
    return results


def check_filter_available(filter_name):
    """Check if a specific filter is compiled into this FFmpeg build."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-filters"],
            capture_output=True, text=True, timeout=15
        )
        # Filter lines: " T.C drawbox  V->V  Draw a colored box..."
        # Format: <space><flag><dot><flag><space><filter_name><space>
        # e.g. "T.C drawbox  V->V  Draw..."
        for line in r.stdout.split("\n"):
            # Split by whitespace and check if filter_name appears as a token
            tokens = line.split()
            # Format: " T.C drawbox  V->V  Draw..."
            # tokens[0] = "T.C" (flags), tokens[1] = filter_name, tokens[2] = "V->V"
            if len(tokens) >= 2 and tokens[1] == filter_name:
                return True
        return False
    except Exception:
        return False


def test_filter_expression(filter_str, test_input="color=c=black:s=320x240:d=1:r=30"):
    """
    Test a filter expression by running it through FFmpeg.
    Returns (ok: bool, error_msg: str or None).
    """
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", test_input,
            "-filter_complex", filter_str + "[v]",
            "-map", "[v]",
            "-t", "1",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "30",
            "-pix_fmt", "yuv420p",
            "-an",
            tmp.name,
        ]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            if r.returncode == 0:
                # Also verify output file is non-trivial (> 1KB)
                size = os.path.getsize(tmp.name)
                if size > 1000:
                    return True, None
                else:
                    return False, f"Output file too small ({size} bytes) — filter may have produced blank frames"
            else:
                # Extract the most relevant error line
                err_lines = [
                    l for l in r.stderr.split("\n")
                    if "Error" in l or "error" in l or "Invalid" in l
                ]
                err_msg = err_lines[0] if err_lines else r.stderr[:300]
                return False, err_msg
        except subprocess.TimeoutExpired:
            return False, "FFmpeg timed out (30s) — filter expression may be hanging"
        except Exception as e:
            return False, str(e)


def check_fonts():
    """Verify required font files exist on disk."""
    results = {}
    for font_path in REQUIRED_FONTS:
        exists = os.path.exists(font_path)
        results[font_path] = {
            "ok": exists,
            "error": None if exists else f"Font not found: {font_path}"
        }
    return results


def check_drawtext_font_rendering():
    """
    Verify drawtext actually renders text (not just parses).
    Some FFmpeg builds have drawtext but lack libfreetype.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=640x480:d=1",
            "-filter_complex",
            "drawtext=text='ViralDNA':fontsize=72:x=(w-text_w)/2:y=(h-text_h)/2:fontcolor=white",
            "-frames:v", "1",
            tmp.name,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 5000:
                return True, None
            else:
                return False, "drawtext parsed but output is suspicious — libfreetype may be missing"
        except Exception as e:
            return False, str(e)


# ═══════════════════════════════════════════════════════════════
# MAIN RUNNER
# ═══════════════════════════════════════════════════════════════

def run_all_checks(json_output=False):
    all_passed = True
    report = {}

    # 1. FFmpeg availability
    ffmpeg_checks = check_ffmpeg_available()
    report["ffmpeg"] = ffmpeg_checks
    for binary, info in ffmpeg_checks.items():
        if not info["ok"]:
            all_passed = False

    # 2. Required filters
    filter_results = {}
    for f in REQUIRED_FILTERS:
        available = check_filter_available(f)
        filter_results[f] = {"ok": available}
        if not available:
            all_passed = False
            filter_results[f]["error"] = f"Filter '{f}' not available in this FFmpeg build"
    report["filters"] = filter_results

    # 3. Known problematic patterns
    known_results = {}
    for issue_id, issue in KNOWN_ISSUES.items():
        entry = {"description": issue["description"]}

        # Test the broken pattern (if it exists)
        if issue["broken"]:
            ok, err = test_filter_expression(issue["broken"])
            entry["broken_pattern_works"] = ok
            if ok:
                # The broken pattern actually works — issue may be fixed in this FFmpeg version
                entry["status"] = "ok (broken pattern works on this FFmpeg version)"
            else:
                entry["status"] = "expected_failure"
                entry["broken_error"] = err
        else:
            entry["broken_pattern_works"] = None

        # Test the working pattern
        if issue["working"]:
            ok, err = test_filter_expression(issue["working"])
            entry["working_pattern_works"] = ok
            if not ok:
                all_passed = False
                entry["status"] = "CRITICAL: working pattern also fails"
                entry["working_error"] = err
            elif entry.get("broken_pattern_works") is False:
                entry["status"] = "confirmed_issue"
                entry["fix_hint"] = issue.get("fix_hint")

        known_results[issue_id] = entry
    report["known_issues"] = known_results

    # 4. Font files
    font_results = check_fonts()
    report["fonts"] = font_results
    for font_path, info in font_results.items():
        if not info["ok"]:
            all_passed = False

    # 5. Drawtext rendering
    dt_ok, dt_err = check_drawtext_font_rendering()
    report["drawtext_rendering"] = {"ok": dt_ok, "error": dt_err}
    if not dt_ok:
        all_passed = False

    # 6. Scene directory writable
    scene_dir = os.path.join(PROJECT_DIR, "runtime", "trailer", "trailer_scenes")
    os.makedirs(scene_dir, exist_ok=True)
    writable = os.access(scene_dir, os.W_OK)
    report["scene_dir_writable"] = {
        "ok": writable,
        "path": scene_dir,
        "error": None if writable else f"Cannot write to {scene_dir}"
    }
    if not writable:
        all_passed = False

    report["overall"] = "PASS" if all_passed else "FAIL"

    if json_output:
        print(json.dumps(report, indent=2))
    else:
        print("=" * 60)
        print("FFmpeg Filter Pre-Flight Check — ViralDNA Pipeline")
        print("=" * 60)

        print("\n[1] FFmpeg Binaries:")
        for binary, info in ffmpeg_checks.items():
            status = "OK" if info["ok"] else "FAIL"
            print(f"    {status}  {binary}: {info.get('version', info.get('error', ''))}")

        print("\n[2] Required Filters:")
        for f, info in filter_results.items():
            status = "OK" if info["ok"] else "MISSING"
            print(f"    {status}  {f}")

        print("\n[3] Known Problematic Patterns:")
        for issue_id, entry in known_results.items():
            status = entry.get("status", "unknown")
            icon = "OK" if "ok" in status or status == "expected_failure" else "FAIL"
            print(f"    {icon}  {issue_id}: {status}")
            if entry.get("fix_hint"):
                print(f"        FIX: {entry['fix_hint']}")

        print("\n[4] Font Files:")
        for font_path, info in font_results.items():
            status = "OK" if info["ok"] else "MISSING"
            basename = os.path.basename(font_path)
            print(f"    {status}  {basename}")

        print(f"\n[5] Drawtext Rendering: {'OK' if dt_ok else 'FAIL'}")
        if dt_err:
            print(f"        Error: {dt_err}")

        print(f"\n[6] Scene Directory Writable: {'OK' if writable else 'FAIL'}")
        print(f"        Path: {scene_dir}")

        print("\n" + "=" * 60)
        print(f"OVERALL: {'ALL CHECKS PASSED' if all_passed else 'SOME CHECKS FAILED — FIX BEFORE RUNNING PIPELINE'}")
        print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    json_mode = "--json" in sys.argv
    exit_code = run_all_checks(json_output=json_mode)
    sys.exit(exit_code)
