# Diagnostic script for RVC chunks
import os
import subprocess
import asyncio
import sys
import numpy as np
import scipy.io.wavfile as wavfile
import librosa

sys.path.append("/home/jay/modules")
from voiceover import VoiceoverGenerator

vg = VoiceoverGenerator()
script_obj = {
    "full_script": "This is a test of our brand new batch RVC pipeline. తెలుగు లో కూడా ఎలా వస్తుందో చూద్దాం! It should be completely smooth without any robotic glitch sounds."
}

# 1. Segment script dynamically
segments = vg._segment_script(script_obj["full_script"])
print(f"Segments: {segments}")

# Create workspace dir manually
workspace_dir = "/home/jay/ViralDNA/output/runtime/work_test_investigation"
if os.path.exists(workspace_dir):
    import shutil
    shutil.rmtree(workspace_dir)
os.makedirs(workspace_dir, exist_ok=True)

# 2. Synthesize segments
segment_paths = []
for idx, s in enumerate(segments):
    chunk_name = f"chunk_{idx:03d}.mp3"
    chunk_path = os.path.join(workspace_dir, chunk_name)
    success = asyncio.run(vg._synthesize_segment_async(s["text"], s["lang"], chunk_path))
    print(f"Segment {idx} ({s['lang']}): '{s['text']}' -> Synthesized: {success}, Size: {os.path.getsize(chunk_path) if success else 0} bytes")
    segment_paths.append(chunk_path)

# Let's inspect the synthesized chunks to see if they have actual voice
print("\n=== INVESTIGATING PRE-RVC CHUNKS ===")
for p in segment_paths:
    y, sr = librosa.load(p, sr=None)
    duration = librosa.get_duration(y=y, sr=sr)
    rms = np.sqrt(np.mean(y**2))
    peak = np.max(np.abs(y))
    print(f"File: {os.path.basename(p)} | Duration: {duration:.2f}s | SR: {sr} | RMS: {rms:.6f} | Peak: {peak:.6f}")

# 3. Run RVC Batch Command and capture all output
print("\n=== RUNNING RVC BATCH COMMAND ===")
rvc_cmd = [
    "/home/jay/venv/bin/python3",
    "/home/jay/modules/rvc_infer.py",
    "-i", workspace_dir,
    "-o", workspace_dir,
    "-m", vg.rvc_model
]
result = subprocess.run(rvc_cmd, capture_output=True, text=True)
print(f"RVC Return Code: {result.returncode}")
print("--- RVC STDOUT ---")
print(result.stdout)
print("--- RVC STDERR ---")
print(result.stderr)

# 4. Let's inspect the post-RVC chunks
print("\n=== INVESTIGATING POST-RVC CHUNKS ===")
rvc_files = sorted([f for f in os.listdir(workspace_dir) if f.startswith("rvc_chunk_")])
for f in rvc_files:
    p = os.path.join(workspace_dir, f)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        y, sr = librosa.load(p, sr=None)
        duration = librosa.get_duration(y=y, sr=sr)
        rms = np.sqrt(np.mean(y**2))
        peak = np.max(np.abs(y))
        print(f"File: {f} | Duration: {duration:.2f}s | SR: {sr} | RMS: {rms:.6f} | Peak: {peak:.6f}")
    else:
        print(f"File: {f} -> DOES NOT EXIST OR IS EMPTY (Size: {os.path.getsize(p) if os.path.exists(p) else 'N/A'})")
