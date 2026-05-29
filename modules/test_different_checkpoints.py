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

checkpoints = [
    '/home/jay/rvc_core/assets/weights/jay_voice_prod.pth',
    '/home/jay/rvc_core/assets/weights/jay_voice_prod_e200_s2400.pth',
    '/home/jay/rvc_core/assets/weights/jay_voice_prod_e100_s0.pth',
    '/home/jay/rvc_core/assets/weights/jay_voice_prod_e20_s0.pth'
]

# Use a global dictionary to avoid scope binding issues
captured = {}

for cp in checkpoints:
    print(f"\n======================================")
    print(f"Testing checkpoint: {cp}")
    if not os.path.exists(cp):
        print("Checkpoint does not exist!")
        continue
        
    try:
        rvc = RVCInference(device='cuda:0')
        rvc.load_model(cp)
        
        orig_infer = rvc.vc.net_g.infer
        captured['audio'] = None
        
        def patched_infer(*args, **kwargs):
            out = orig_infer(*args, **kwargs)
            if isinstance(out, tuple) and len(out) > 0 and torch.is_tensor(out[0]):
                captured['audio'] = out[0].detach().cpu().numpy()
            return out
            
        rvc.vc.net_g.infer = patched_infer
        
        rvc.set_params(
            f0method="rmvpe",
            f0up_key=0,
            index_rate=0.0,
            filter_radius=3,
            resample_sr=0,
            rms_mix_rate=0.25,
            protect=0.5
        )
        
        temp_out = f"/home/jay/ViralDNA/output/runtime/work_test_investigation/temp_cp_test.wav"
        if os.path.exists(temp_out):
            os.remove(temp_out)
            
        rvc.infer_file(f_in, temp_out)
        
        audio_captured = captured.get('audio')
        if audio_captured is not None:
            audio_flat = audio_captured.flatten()
            print(f"Audio captured shape: {audio_flat.shape}")
            print(f"Min: {np.min(audio_flat)}, Max: {np.max(audio_flat)}, Mean: {np.mean(audio_flat)}")
            print(f"Any negative values? {np.any(audio_flat < 0)}")
            print(f"First 10 values: {audio_flat[:10]}")
        else:
            print("Failed to capture audio during inference!")
            
    except Exception as e:
        print(f"Error testing checkpoint: {e}")
