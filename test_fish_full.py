#!/usr/bin/env python3
"""
Fish Speech v1.4 — Full 3-Step Voice Cloning Pipeline (CPU-ONLY)
Fixed: trimmed reference audio to 60s to stay within 4096 token limit.
"""
import os, sys, subprocess, shutil, time

os.environ["CUDA_VISIBLE_DEVICES"] = ""

FISH_DIR = "/home/jay/fish-speech-v1.5"
CKPT_DIR = os.path.join(FISH_DIR, "checkpoints/fish-speech-1.4")
REF_AUDIO = "/home/jay/voice_sample.wav"
TEST_TEXT = "This is a test of Fish Speech voice cloning for the ViralDNA pipeline. Breaking news from India today."
OUTPUT_WAV = "/home/jay/ViralDNA/output/runtime/test_fish_output.wav"
TRIMMED_AUDIO = "/home/jay/ViralDNA/output/runtime/voice_trimmed.wav"
os.makedirs(os.path.dirname(OUTPUT_WAV), exist_ok=True)

gen_ckpt = os.path.join(CKPT_DIR, "firefly-gan-vq-fsq-8x1024-21hz-generator.pth")

# Trim reference audio to 60s (Fish Speech uses 21.53 features/sec, 60s = ~1290 features, well under 4096)
print("Trimming reference audio to 60s...")
import torchaudio
audio, sr = torchaudio.load(REF_AUDIO)
max_samples = 60 * sr
if audio.shape[1] > max_samples:
    audio = audio[:, :max_samples]
torchaudio.save(TRIMMED_AUDIO, audio, sr)
print(f"  Trimmed: {audio.shape[1]/sr:.1f}s, {sr}Hz")

wrapper_prefix = """
import os, sys, torch
os.environ["CUDA_VISIBLE_DEVICES"] = ""
sys.path.insert(0, "{FISH_DIR}")
_orig = torch.load
def _p(f, *a, **k):
    k.setdefault('map_location', 'cpu')
    k.setdefault('weights_only', False)
    return _orig(f, *a, **k)
torch.load = _p
""".format(FISH_DIR=FISH_DIR)

# ============ STEP 1: VQ-GAN Encode ============
print("\n" + "=" * 60)
print("STEP 1: VQ-GAN Encode (trimmed audio -> indices)")
print("=" * 60)
step1 = wrapper_prefix + """
from tools.vqgan.inference import main as vqgan_main
sys.argv = ["inference.py", "-i", "{audio}", "--checkpoint-path", "{ckpt}", "--device", "cpu"]
vqgan_main()
""".format(audio=TRIMMED_AUDIO, ckpt=gen_ckpt)

t0 = time.time()
r = subprocess.run([sys.executable, "-c", step1], capture_output=True, text=True, cwd=FISH_DIR, timeout=300)
t1 = time.time()
print(f"  Exit: {r.returncode}, Time: {t1-t0:.1f}s")
if r.returncode != 0: print(f"  stderr: {r.stderr[-300:]}")

npy_file = os.path.join(FISH_DIR, "fake.npy")
if not os.path.exists(npy_file):
    print("  [ERROR] Step 1 failed"); sys.exit(1)
import numpy as np
indices = np.load(npy_file)
print(f"  [OK] fake.npy: {indices.shape} ({os.path.getsize(npy_file)} bytes)")

# ============ STEP 2: LLaMA Generate ============
print("\n" + "=" * 60)
print("STEP 2: LLaMA Generate (text + indices -> semantic tokens)")
print("  943MB model on CPU, may take 3-8 min")
print("=" * 60)
step2 = wrapper_prefix + """
from tools.llama.generate import main as llama_main
sys.argv = [
    "generate.py",
    "--text", "{text}",
    "--prompt-text", "This is a news broadcast test in Indian English.",
    "--prompt-tokens", "{npy}",
    "--checkpoint-path", "{ckpt}",
    "--num-samples", "1",
    "--device", "cpu",
    "--half"
]
llama_main()
""".format(text=TEST_TEXT, npy=npy_file, ckpt=str(CKPT_DIR))

t0 = time.time()
r = subprocess.run([sys.executable, "-c", step2], capture_output=True, text=True, cwd=FISH_DIR, timeout=600)
t1 = time.time()
print(f"  Exit: {r.returncode}, Time: {t1-t0:.1f}s")
if r.stdout: print(f"  stdout: {r.stdout[-300:]}")
if r.returncode != 0: print(f"  stderr: {r.stderr[-500:]}")

codes_file = None
for f in os.listdir(FISH_DIR):
    if f.startswith("codes_") and f.endswith(".npy"):
        codes_file = os.path.join(FISH_DIR, f)
        break
if not codes_file:
    print("  [ERROR] Step 2 failed"); sys.exit(1)
print(f"  [OK] {os.path.basename(codes_file)}: {os.path.getsize(codes_file)} bytes")

# ============ STEP 3: VQ-GAN Decode ============
print("\n" + "=" * 60)
print("STEP 3: VQ-GAN Decode (semantic tokens -> speech)")
print("=" * 60)
step3 = wrapper_prefix + """
from tools.vqgan.inference import main as vqgan_main
sys.argv = ["inference.py", "-i", "{codes}", "--checkpoint-path", "{ckpt}", "--device", "cpu"]
vqgan_main()
""".format(codes=codes_file, ckpt=gen_ckpt)

t0 = time.time()
r = subprocess.run([sys.executable, "-c", step3], capture_output=True, text=True, cwd=FISH_DIR, timeout=300)
t1 = time.time()
print(f"  Exit: {r.returncode}, Time: {t1-t0:.1f}s")
if r.returncode != 0: print(f"  stderr: {r.stderr[-300:]}")

output_wav = os.path.join(FISH_DIR, "fake.wav")
if not os.path.exists(output_wav):
    print("  [ERROR] Step 3 failed"); sys.exit(1)

shutil.copy2(output_wav, OUTPUT_WAV)
print(f"  [OK] Output: {OUTPUT_WAV} ({os.path.getsize(OUTPUT_WAV)/1024:.0f} KB)")

# Cleanup
for f in ["fake.npy", "fake.wav", "codes_0.npy"]:
    fp = os.path.join(FISH_DIR, f)
    if os.path.exists(fp): os.remove(fp)

print("\n" + "=" * 60)
print("FISH SPEECH VOICE CLONING TEST COMPLETE")
print("=" * 60)
print(f"Output: {OUTPUT_WAV}")
print("Listen to verify voice quality.")
