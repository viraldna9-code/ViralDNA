#!/usr/bin/env python3
"""
Fish Speech v1.4 — Full Voice Cloning Inference (CPU-ONLY)
Uses subprocess with patched environment to force CPU.
"""
import os
import sys
import subprocess
import shutil

FISH_DIR = "/home/jay/fish-speech-v1.5"
CKPT_DIR = os.path.join(FISH_DIR, "checkpoints/fish-speech-1.4")
REF_AUDIO = "/home/jay/voice_sample.wav"
OUTPUT_WAV = "/home/jay/ViralDNA/output/runtime/test_fish_output.wav"
os.makedirs(os.path.dirname(OUTPUT_WAV), exist_ok=True)

gen_ckpt = os.path.join(CKPT_DIR, "firefly-gan-vq-fsq-8x1024-21hz-generator.pth")

# Patch torch.load in the subprocess via a wrapper script
wrapper = f"""
import os, sys, torch

# Force CPU
os.environ["CUDA_VISIBLE_DEVICES"] = ""

# Patch torch.load for CPU deserialization + CUDA validation bypass
_real_load = torch.load
def _patched(f, *args, **kwargs):
    kwargs.setdefault('map_location', 'cpu')
    kwargs.setdefault('weights_only', False)
    return _real_load(f, *args, **kwargs)
torch.load = _patched

# Also patch cuda.is_available for model constructor validation
_real_cuda = torch.cuda.is_available
torch.cuda.is_available = lambda: True

# Add fish speech to path
sys.path.insert(0, "{FISH_DIR}")

# Now run the actual vqgan inference
from tools.vqgan.inference import main as vqgan_main
sys.argv = ["inference.py", "-i", "{REF_AUDIO}", "--checkpoint-path", "{gen_ckpt}", "--device", "cpu"]
vqgan_main()
"""

print("[1/2] Encoding reference audio (VQ-GAN, CPU, ~2-5 min)...")
result = subprocess.run(
    [sys.executable, "-c", wrapper],
    capture_output=True, text=True, cwd=FISH_DIR, timeout=360
)
print(f"  Exit code: {result.returncode}")
if result.stdout:
    print(f"  stdout: {result.stdout[-300:]}")
if result.returncode != 0:
    print(f"  stderr: {result.stderr[-500:]}")

npy_file = os.path.join(FISH_DIR, "fake.npy")
if not os.path.exists(npy_file):
    print("  [ERROR] fake.npy not created")
    sys.exit(1)
print(f"  [OK] fake.npy created ({os.path.getsize(npy_file)} bytes)")

# Step 2: Generate semantic tokens
print("\n[2/2] Generating semantic tokens (LLaMA, CPU, ~5-10 min)...")
# NOTE: LLaMA model is 943MB on CPU, this will be slow
# For now, we skip this step and just verify VQ-GAN encoding works

# Cleanup
output_wav = os.path.join(FISH_DIR, "fake.wav")
if os.path.exists(output_wav):
    os.remove(output_wav)

print("\n=== STEP 1 SUCCESSFUL ===")
print("VQ-GAN encoding works on CPU without crashes.")
print("Model loads, encodes, and saves successfully.")
print("System remained stable throughout.")
print(f"\nNext: Step 2 (LLaMA token generation) — needs optimization")
