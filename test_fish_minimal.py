import os, sys, torch, time

os.environ["CUDA_VISIBLE_DEVICES"] = ""

CKPT_DIR = "/home/jay/fish-speech-v1.5/checkpoints/fish-speech-1.4"
FISH_DIR = "/home/jay/fish-speech-v1.5"
sys.path.insert(0, FISH_DIR)

# Patch torch.load BEFORE any fish speech imports
_orig_load = torch.load
def _patched(f, *args, **kwargs):
    kwargs.setdefault('map_location', 'cpu')
    kwargs.setdefault('weights_only', False)
    return _orig_load(f, *args, **kwargs)
torch.load = _patched

print("torch.load patched for CPU")

# Now import and run vqgan inference
from tools.vqgan.inference import main as vqgan_main

sys.argv = [
    "inference.py",
    "-i", "/home/jay/voice_sample.wav",
    "--checkpoint-path", os.path.join(CKPT_DIR, "firefly-gan-vq-fsq-8x1024-21hz-generator.pth"),
    "--device", "cpu"
]

print("Running VQ-GAN encoding on CPU...")
t0 = time.time()
vqgan_main()
t1 = time.time()
print(f"Completed in {t1-t0:.1f}s")
