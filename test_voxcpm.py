#!/usr/bin/env python3
"""
VoxCPM2-ONNX Voice Cloning Test
Tests voice cloning with Jay's voice sample.
"""
import os
import sys
import subprocess
import shutil

ONNX_DIR = "/home/jay/ViralDNA/models/voxcpm2-onnx"
REPO_DIR = "/home/jay/ViralDNA/VoxCPM2-ONNX"
OUTPUT_DIR = "/home/jay/ViralDNA/output/runtime"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Trim reference audio to 10s for VoxCPM2 (it prefers 3-10s)
REF_WAV = "/home/jay/voice_sample.wav"
TRIMMED_REF = os.path.join(OUTPUT_DIR, "voxcpm_ref.wav")

print("Trimming reference audio to 10s...")
os.system(f'ffmpeg -y -i {REF_WAV} -t 10 -ar 16000 -ac 1 {TRIMMED_REF} 2>/dev/null')
print(f"  Trimmed ref: {os.path.getsize(TRIMMED_REF)/1024:.0f} KB")

# Test text
TEST_TEXT = "This is a voice cloning test using VoxCPM2. Breaking news from India today."
REF_TEXT = "This is a news broadcast test in Indian English."

OUTPUT_WAV = os.path.join(OUTPUT_DIR, "test_voxcpm_output.wav")

# Run inference
cmd = [
    sys.executable,
    os.path.join(REPO_DIR, "infer.py"),
    "--text", TEST_TEXT,
    "--ref_wav", TRIMMED_REF,
    "--ref_text", REF_TEXT,
    "--output", OUTPUT_WAV,
    "--onnx_dir", ONNX_DIR,
    "--timesteps", "10",
    "--max_len", "200",
]

print(f"\nRunning VoxCPM2 inference...")
print(f"  Command: {' '.join(cmd)}")
result = subprocess.run(cmd, capture_output=True, text=True)

print(f"  Exit code: {result.returncode}")
if result.stdout:
    for line in result.stdout.strip().split('\n'):
        print(f"  {line}")
if result.returncode != 0:
    print(f"  stderr: {result.stderr[-500:]}")
    sys.exit(1)

if os.path.exists(OUTPUT_WAV):
    size = os.path.getsize(OUTPUT_WAV)
    print(f"\n  [OK] Output: {OUTPUT_WAV} ({size/1024:.0f} KB)")
else:
    print(f"\n  [ERROR] No output file generated")
    sys.exit(1)

print("\n=== VoxCPM2 TEST COMPLETE ===")
