import sys, os
import torch
import numpy as np

# Override torch.load
orig_load = torch.load
def safe_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return orig_load(*args, **kwargs)
torch.load = safe_load

sys.path.append('/home/jay/modules')
from rvc_python.infer import RVCInference

rvc = RVCInference(device='cuda:0')
# Default is_half is True for CUDA:0

# Load model
rvc.load_model('/home/jay/rvc_core/assets/weights/jay_voice_prod.pth')

# Let's intercept Pipeline.pipeline to inspect features
from rvc_python.modules.vc.pipeline import Pipeline
orig_pipeline = Pipeline.pipeline

def patched_pipeline(self, model, net_g, *args, **kwargs):
    print("--- IN PATCHED PIPELINE (FP16) ---")
    res = orig_pipeline(self, model, net_g, *args, **kwargs)
    return res

Pipeline.pipeline = patched_pipeline

# Also patch net_g.infer to inspect its input and output tensors!
orig_infer = rvc.vc.net_g.infer
def patched_infer(*args, **kwargs):
    print("--- IN PATCHED NET_G.INFER (FP16) ---")
    out = orig_infer(*args, **kwargs)
    if isinstance(out, tuple):
        for i, o in enumerate(out):
            if torch.is_tensor(o):
                o_np = o.detach().cpu().numpy()
                print(f"out tuple {i} shape: {o_np.shape}, min: {np.min(o_np)}, max: {np.max(o_np)}, NaN: {np.any(np.isnan(o_np))}")
    return out

rvc.vc.net_g.infer = patched_infer

f_in = '/home/jay/ViralDNA/output/runtime/work_test_investigation/chunk_000.mp3'
f_out = '/home/jay/ViralDNA/output/runtime/work_test_investigation/chunk_000_fp16_test.wav'

rvc.set_params(
    f0method="rmvpe",
    f0up_key=0,
    index_rate=0.0,
    filter_radius=3,
    resample_sr=0,
    rms_mix_rate=0.25,
    protect=0.5
)

print("Running inference...")
rvc.infer_file(f_in, f_out)
print("Done.")

# Analyze pitch
import librosa
y, sr = librosa.load(f_out, sr=None)
print('First 20 samples of y (FP16):', y[:20])
print('Any negative values in y (FP16)?', np.any(y < 0))
f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'), sr=sr)
voiced_f0 = f0[voiced_flag]
if len(voiced_f0) > 0:
    print('Total voiced frames (FP16):', len(voiced_f0))
    print('Mean Pitch (FP16):', np.mean(voiced_f0))
    print('Std of Pitch (FP16):', np.std(voiced_f0))
else:
    print('No voiced frames detected in the output!')
