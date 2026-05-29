import torch
import sys
import os
import numpy as np
import subprocess

# Monkeypatch torch.load to bypass weights_only=True
orig_load = torch.load
def safe_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return orig_load(*args, **kwargs)
torch.load = safe_load

sys.path.append("/home/jay/venv/lib/python3.12/site-packages/rvc_python")
from rvc_python.infer import RVCInference
import scipy.io.wavfile as wavfile

def test_voices():
    # Target text to synthesize
    text = "Good evening. This is ViralDNA, bringing you critical updates from the heart of our homeland. Today, we cover a major regulatory development directly impacting local communities."
    
    edge_tts_bin = "/home/jay/venv/bin/edge-tts"
    model_path = "/home/jay/rvc_core/assets/weights/jay_voice_prod.pth"
    
    # 1. We will test different base voices
    base_voices = ["en-IN-PrabhatNeural", "en-US-AndrewNeural", "en-US-ChristopherNeural"]
    
    print("Initializing RVCInference...")
    rvc = RVCInference(device="cuda:0")
    rvc.load_model(model_path)
    
    # Override standard padding values for testing
    rvc.config.x_pad = 0.5
    if hasattr(rvc, "vc") and hasattr(rvc.vc, "pipeline"):
        rvc.vc.pipeline.x_pad = 0.5
        rvc.vc.pipeline.t_pad_tgt = rvc.vc.tgt_sr * 1
        rvc.vc.pipeline.t_pad = 16000 * 1
        rvc.vc.pipeline.t_pad2 = 16000 * 1 * 2

    model_info = rvc.models[rvc.current_model]
    file_index = model_info.get("index", "")
    
    for base in base_voices:
        print(f"\n======================================")
        print(f"🎙️ Testing Base Voice: {base}")
        print(f"======================================")
        
        raw_path = f"/tmp/raw_{base}.mp3"
        out_wav = f"/tmp/out_{base}.wav"
        out_mp3 = f"/tmp/out_{base}.mp3"
        
        # Step 1: Synthesize with Edge-TTS
        print(f"  -> Synthesizing raw TTS...")
        subprocess.run([
            edge_tts_bin,
            "--text", text,
            "--voice", base,
            "--write-media", raw_path
        ], check=True)
        
        # Step 2: Convert using RVC with PM and RMVPE methods
        for method in ["pm", "rmvpe"]:
            for pitch in [-2, 0, 2]:
                print(f"  -> Running RVC (Method: {method}, Pitch Shift: {pitch})...")
                try:
                    wav_opt = rvc.vc.vc_single(
                        sid=0,
                        input_audio_path=raw_path,
                        f0_up_key=pitch,
                        f0_method=method,
                        file_index=file_index,
                        index_rate=0.6,
                        filter_radius=3,
                        resample_sr=0,
                        rms_mix_rate=0.25,
                        protect=0.33,
                        f0_file="",
                        file_index2=""
                    )
                    
                    if isinstance(wav_opt, tuple) or isinstance(wav_opt, str):
                        print(f"    ❌ Conversion returned error tuple: {wav_opt}")
                        continue
                        
                    y = wav_opt.astype(np.float32) / 32768.0
                    mean = np.mean(y)
                    std = np.std(y)
                    min_v = np.min(y)
                    max_v = np.max(y)
                    
                    print(f"    🟢 Success! Shape: {wav_opt.shape}")
                    print(f"    🟢 Signal Stats - Mean: {mean:.4f}, Std Dev: {std:.4f}, Min/Max: {min_v:.4f}/{max_v:.4f}")
                    
                    # Let's save a file for comparison if stats are good
                    if std > 0.01:
                        test_wav = f"/home/jay/ViralDNA/audio/test_{base}_{method}_pitch{pitch}.wav"
                        wavfile.write(test_wav, rvc.vc.tgt_sr, wav_opt)
                        # Transcode to mp3
                        test_mp3 = test_wav.replace(".wav", ".mp3")
                        subprocess.run([
                            "ffmpeg", "-y", "-i", test_wav, "-codec:a", "libmp3lame", "-b:a", "192k", test_mp3
                        ], capture_output=True)
                        if os.path.exists(test_wav):
                            os.remove(test_wav)
                        print(f"    💾 Saved comparison file: {os.path.basename(test_mp3)}")
                except Exception as e:
                    print(f"    ❌ Error: {e}")

if __name__ == "__main__":
    test_voices()
