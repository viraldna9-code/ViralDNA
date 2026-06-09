import torch
import sys
import os
import numpy as np
import librosa

# Monkeypatch torch.load to bypass weights_only=True default
orig_load = torch.load
def safe_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return orig_load(*args, **kwargs)
torch.load = safe_load

sys.path.append("/home/jay/venv/lib/python3.12/site-packages/rvc_python")
from rvc_python.infer import RVCInference

# Test input
input_audio = "/home/jay/modules/test_edge.mp3"

# List all models
weights_dir = "/home/jay/rvc_core/assets/weights"
checkpoints = [
    os.path.join(weights_dir, f) for f in os.listdir(weights_dir)
    if f.endswith(".pth") and "prod" in f
]

print(f"Found {len(checkpoints)} checkpoints.")

# We will test a few of them
for cp in sorted(checkpoints)[:3]:
    print(f"\n--- Testing Checkpoint: {os.path.basename(cp)} ---")
    try:
        rvc = RVCInference(device="cuda:0")
        rvc.load_model(cp)
        
        # Test configurations
        for sid in [0, 1]:
            for f0_method in ["rmvpe", "pm"]:
                print(f"Testing SID={sid}, Method={f0_method}...")
                wav_opt = rvc.vc.vc_single(
                    sid=sid,
                    input_audio_path=input_audio,
                    f0_up_key=0,
                    f0_method=f0_method,
                    file_index="",
                    index_rate=0.75,
                    filter_radius=3,
                    resample_sr=0,
                    rms_mix_rate=0.25,
                    protect=0.33,
                    f0_file="",
                    file_index2=""
                )
                
                # Analyze array
                if isinstance(wav_opt, tuple):
                    print(f"  ❌ Failed with tuple: {wav_opt}")
                else:
                    # Normalized stats
                    # wav_opt is int16, let's normalize to float32
                    y = wav_opt.astype(np.float32) / 32768.0
                    mean = np.mean(y)
                    std = np.std(y)
                    min_v = np.min(y)
                    max_v = np.max(y)
                    print(f"  🟢 Success! Shape: {wav_opt.shape}, Mean: {mean:.4f}, Std: {std:.4f}, Min/Max: {min_v:.4f}/{max_v:.4f}")
    except Exception as e:
        print(f"  ❌ Error with checkpoint {os.path.basename(cp)}: {e}")
