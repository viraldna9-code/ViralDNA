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

f_in = '/home/jay/ViralDNA/output/runtime/work_test_investigation/chunk_000.mp3'
f_out = '/home/jay/ViralDNA/output/runtime/work_test_investigation/chunk_000_good_cp.wav'

if os.path.exists(f_out):
    os.remove(f_out)

print("Instantiating RVCInference...")
rvc = RVCInference(device='cuda:0')

print("Loading jay_voice_prod_e200_s2400.pth...")
rvc.load_model('/home/jay/rvc_core/assets/weights/jay_voice_prod_e200_s2400.pth')

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

# Pitch analysis
import librosa
y, sr = librosa.load(f_out, sr=None)
print('First 20 samples of y (good CP):', y[:20])
print('Any negative values in y? (good CP):', np.any(y < 0))
f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'), sr=sr)
voiced_f0 = f0[voiced_flag]
if len(voiced_f0) > 0:
    print('Total voiced frames (good CP):', len(voiced_f0))
    print('Mean Pitch (good CP):', np.mean(voiced_f0))
    print('Std of Pitch (good CP):', np.std(voiced_f0))
    print('Min Pitch (good CP):', np.min(voiced_f0))
    print('Max Pitch (good CP):', np.max(voiced_f0))
else:
    print('No voiced frames detected in the output!')
