import sys, os
import torch
orig_load = torch.load
def safe_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return orig_load(*args, **kwargs)
torch.load = safe_load

sys.path.append('/home/jay/modules')
from rvc_python.infer import RVCInference
import librosa
import numpy as np

f_in = '/home/jay/ViralDNA/output/runtime/work_test_investigation/chunk_000.mp3'
f_out = '/home/jay/ViralDNA/output/runtime/work_test_investigation/chunk_000_fp32_cpu.wav'

print("=== Starting RVC CPU FP32 Test ===")
rvc = RVCInference(device='cpu')

# Disable half-precision (FP16)
print("Current is_half:", rvc.config.is_half)
rvc.config.is_half = False
print("Set is_half to:", rvc.config.is_half)

# Load model
rvc.load_model('/home/jay/rvc_core/assets/weights/jay_voice_prod.pth')

# Set generation params
rvc.set_params(
    f0method="rmvpe",
    f0up_key=0,
    index_rate=0.0,
    filter_radius=3,
    resample_sr=0,
    rms_mix_rate=0.25,
    protect=0.5
)

print("Running inference on CPU...")
rvc.infer_file(f_in, f_out)
print("Inference completed. Saved output to:", f_out)

# Analyze pitch
print("\n=== Pitch Analysis ===")
y, sr = librosa.load(f_out, sr=None)
f0, voiced_flag, voiced_probs = librosa.pyin(
    y,
    fmin=librosa.note_to_hz('C2'),
    fmax=librosa.note_to_hz('C7'),
    sr=sr
)

voiced_frames = f0[~np.isnan(f0)]
print("Total voiced frames:", len(voiced_frames))
if len(voiced_frames) > 0:
    print(f"Mean Pitch: {np.mean(voiced_frames):.2f} Hz")
    print(f"Std of Pitch: {np.std(voiced_frames):.2f} Hz")
    print(f"Min Pitch: {np.min(voiced_frames):.2f} Hz")
    print(f"Max Pitch: {np.max(voiced_frames):.2f} Hz")
else:
    print("No voiced frames found!")
