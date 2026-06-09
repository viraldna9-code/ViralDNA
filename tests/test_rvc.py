import torch
import os
import numpy as np

# Monkeypatch torch.load BEFORE importing fairseq or rvc_python to resolve PyTorch 2.6 weights_only=True default
orig_load = torch.load
def safe_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return orig_load(*args, **kwargs)
torch.load = safe_load

import sys
sys.path.append('/home/jay/venv/lib/python3.12/site-packages/rvc_python')
from rvc_python.infer import RVCInference
import scipy.io.wavfile as wavfile

def test():
    print("Initializing RVC...")
    rvc = RVCInference(device="cuda:0")
    print("Loading model...")
    rvc.load_model("/home/jay/rvc_core/assets/weights/jay_voice_prod.pth")
    
    input_path = "/home/jay/ViralDNA/output/runtime/production_main_raw.mp3"
    output_path = "/home/jay/ViralDNA/audio/debug_test_out.wav"
    
    print(f"Converting {input_path} to {output_path}...")
    model_info = rvc.models[rvc.current_model]
    file_index = model_info.get("index", "")
    
    wav_opt = rvc.vc.vc_single(
        sid=0,
        input_audio_path=input_path,
        f0_up_key=rvc.f0up_key,
        f0_method=rvc.f0method,
        file_index=file_index,
        index_rate=rvc.index_rate,
        filter_radius=rvc.filter_radius,
        resample_sr=rvc.resample_sr,
        rms_mix_rate=rvc.rms_mix_rate,
        protect=rvc.protect,
        f0_file="",
        file_index2=""
    )
    
    print("Type of wav_opt:", type(wav_opt))
    if isinstance(wav_opt, np.ndarray):
        print("Array shape:", wav_opt.shape)
        print("Min/Max:", np.min(wav_opt), np.max(wav_opt))
        print("Mean:", np.mean(wav_opt))
        print("Std dev:", np.std(wav_opt))
        
        # Write WAV
        wavfile.write(output_path, rvc.vc.tgt_sr, wav_opt)
        print(f"WAV written successfully to {output_path}")
    else:
        print("Error: wav_opt is not ndarray, it is:", wav_opt)

if __name__ == "__main__":
    test()
