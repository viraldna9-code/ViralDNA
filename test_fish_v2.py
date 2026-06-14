#!/usr/bin/env python3
"""
Fish Speech v1.4 — Step 2 with float32 (no --half flag)
The --half flag uses bfloat16 which may cause numerical issues on CPU.
"""
import os, sys, subprocess, shutil, time

os.environ["CUDA_VISIBLE_DEVICES"] = ""

FISH_DIR = "/home/jay/fish-speech-v1.5"
CKPT_DIR = os.path.join(FISH_DIR, "checkpoints/fish-speech-1.4")
TEST_TEXT = "This is a test of Fish Speech voice cloning for the ViralDNA pipeline. Breaking news from India today."

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

# Step 2 WITHOUT --half (use float32 for CPU stability)
print("STEP 2: LLaMA Generate (float32, CPU)")
print("=" * 60)
step2 = wrapper_prefix + """
from tools.llama.generate import main as llama_main
sys.argv = [
    "generate.py",
    "--text", "{text}",
    "--prompt-text", "This is a news broadcast test in Indian English.",
    "--prompt-tokens", "{FISH_DIR}/fake.npy",
    "--checkpoint-path", "{ckpt}",
    "--num-samples", "1",
    "--device", "cpu"
]
llama_main()
""".format(text=TEST_TEXT, FISH_DIR=FISH_DIR, ckpt=str(CKPT_DIR))

# First create the fake.npy from trimmed audio
print("Creating indices from trimmed audio...")
import torchaudio
audio, sr = torchaudio.load("/home/jay/voice_sample.wav")
max_samples = 60 * sr
if audio.shape[1] > max_samples:
    audio = audio[:, :max_samples]
trimmed = "/home/jay/ViralDNA/output/runtime/voice_trimmed.wav"
os.makedirs(os.path.dirname(trimmed), exist_ok=True)
torchaudio.save(trimmed, audio, sr)

step1 = wrapper_prefix + """
from tools.vqgan.inference import main as vqgan_main
sys.argv = ["inference.py", "-i", "{audio}", "--checkpoint-path", "{ckpt}", "--device", "cpu"]
vqgan_main()
""".format(audio=trimmed, ckpt=os.path.join(CKPT_DIR, "firefly-gan-vq-fsq-8x1024-21hz-generator.pth"))

t0 = time.time()
r = subprocess.run([sys.executable, "-c", step1], capture_output=True, text=True, cwd=FISH_DIR, timeout=300)
t1 = time.time()
print(f"  Step 1: Exit {r.returncode}, {t1-t0:.1f}s")

npy_file = os.path.join(FISH_DIR, "fake.npy")
if not os.path.exists(npy_file):
    print("  [ERROR] Step 1 failed"); sys.exit(1)

# Step 2 with float32
t0 = time.time()
r = subprocess.run([sys.executable, "-c", step2], capture_output=True, text=True, cwd=FISH_DIR, timeout=600)
t1 = time.time()
print(f"  Step 2: Exit {r.returncode}, {t1-t0:.1f}s")
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

# Step 3
print("\nSTEP 3: VQ-GAN Decode")
step3 = wrapper_prefix + """
from tools.vqgan.inference import main as vqgan_main
sys.argv = ["inference.py", "-i", "{codes}", "--checkpoint-path", "{ckpt}", "--device", "cpu"]
vqgan_main()
""".format(codes=codes_file, ckpt=os.path.join(CKPT_DIR, "firefly-gan-vq-fsq-8x1024-21hz-generator.pth"))

t0 = time.time()
r = subprocess.run([sys.executable, "-c", step3], capture_output=True, text=True, cwd=FISH_DIR, timeout=300)
t1 = time.time()
print(f"  Step 3: Exit {r.returncode}, {t1-t0:.1f}s")

output_wav = os.path.join(FISH_DIR, "fake.wav")
if not os.path.exists(output_wav):
    print("  [ERROR] Step 3 failed"); sys.exit(1)

final = "/home/jay/ViralDNA/output/runtime/test_fish_output.wav"
shutil.copy2(output_wav, final)
print(f"  [OK] Output: {final} ({os.path.getsize(final)/1024:.0f} KB)")

# Cleanup
for f in ["fake.npy", "fake.wav", "codes_0.npy"]:
    fp = os.path.join(FISH_DIR, f)
    if os.path.exists(fp): os.remove(fp)

print("\n=== FISH SPEECH TEST COMPLETE ===")
