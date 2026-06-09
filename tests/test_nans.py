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
rvc.config.is_half = False # Use FP32

# Load model
rvc.load_model('/home/jay/rvc_core/assets/weights/jay_voice_prod.pth')

# Let's intercept Pipeline.pipeline to inspect features
from rvc_python.modules.vc.pipeline import Pipeline
orig_pipeline = Pipeline.pipeline

def patched_pipeline(self, model, net_g, *args, **kwargs):
    print("--- IN PATCHED PIPELINE ---")
    print("model class:", model.__class__.__name__)
    print("net_g class:", net_g.__class__.__name__)
    
    # Let's see what parameters are passed to net_g
    # We will call the original pipeline and print what happens
    res = orig_pipeline(self, model, net_g, *args, **kwargs)
    return res

Pipeline.pipeline = patched_pipeline

# Also patch net_g.infer to inspect its input and output tensors!
# We can do this by overriding net_g's infer method dynamically
orig_infer = rvc.vc.net_g.infer
def patched_infer(*args, **kwargs):
    print("--- IN PATCHED NET_G.INFER ---")
    for i, arg in enumerate(args):
        if torch.is_tensor(arg):
            arg_np = arg.detach().cpu().numpy()
            print(f"arg {i} shape: {arg_np.shape}, min: {np.min(arg_np)}, max: {np.max(arg_np)}, NaN: {np.any(np.isnan(arg_np))}")
        else:
            print(f"arg {i}: {arg}")
    for k, v in kwargs.items():
        if torch.is_tensor(v):
            v_np = v.detach().cpu().numpy()
            print(f"kwarg {k} shape: {v_np.shape}, min: {np.min(v_np)}, max: {np.max(v_np)}, NaN: {np.any(np.isnan(v_np))}")
        else:
            print(f"kwarg {k}: {v}")
            
    out = orig_infer(*args, **kwargs)
    print("--- OUT OF NET_G.INFER ---")
    if isinstance(out, tuple):
        for i, o in enumerate(out):
            if torch.is_tensor(o):
                o_np = o.detach().cpu().numpy()
                print(f"out tuple {i} shape: {o_np.shape}, min: {np.min(o_np)}, max: {np.max(o_np)}, NaN: {np.any(np.isnan(o_np))}")
    elif torch.is_tensor(out):
        out_np = out.detach().cpu().numpy()
        print(f"out tensor shape: {out_np.shape}, min: {np.min(out_np)}, max: {np.max(out_np)}, NaN: {np.any(np.isnan(out_np))}")
    return out

rvc.vc.net_g.infer = patched_infer

f_in = '/home/jay/ViralDNA/output/runtime/work_test_investigation/chunk_000.mp3'
f_out = '/home/jay/ViralDNA/output/runtime/work_test_investigation/chunk_000_trace_test.wav'

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
