# VERSION: 30.0
# MODULE: rvc_infer.py
# PURPOSE: Correct class import from rvc_python (Uses RVCInference) with PyTorch 2.6 safe globals, proactive CPU routing for long files (>60s) to prevent OOM, resilient CPU fallback with safe cache-clear, padding normalization, and dynamic MP3 transcoding. Supports batch directory processing.

import argparse
import sys
import os

# Monkeypatch torch.load to bypass PyTorch 2.6 weights_only=True default before importing any other packages
import torch
orig_load = torch.load
def safe_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return orig_load(*args, **kwargs)
torch.load = safe_load

import shutil
import scipy.io.wavfile as wavfile
import librosa
import numpy as np
import subprocess

try:
    from fairseq.data.dictionary import Dictionary
    torch.serialization.add_safe_globals([Dictionary])
except Exception as e:
    print(f"  ⚠️ Warning setting up fairseq Dictionary safe globals: {e}")

from rvc_python.infer import RVCInference

def _execute_rvc(input_path, output_path, model_path, device):
    print(f"  ℹ️ Executing RVC conversion on: {device}")
    
    if os.path.isdir(input_path):
        # Batch directory mode
        print(f"  ℹ️ Batch Directory Mode Active: {input_path}")
        rvc = RVCInference(device=device)
        rvc.load_model(model_path)
        
        files = sorted([f for f in os.listdir(input_path) if f.startswith("chunk_") and f.endswith(".mp3")])
        print(f"  ℹ️ Found {len(files)} chunks to process.")
        
        for f in files:
            f_in = os.path.join(input_path, f)
            f_out_name = "rvc_" + f
            f_out = os.path.join(output_path, f_out_name)
            
            print(f"  ℹ️ Converting chunk: {f} -> {f_out_name}")
            
            duration = librosa.get_duration(path=f_in)
            x_pad = min(0.3, duration / 3.0)
            x_pad = max(0.02, x_pad)
            
            if hasattr(rvc, "vc") and hasattr(rvc.vc, "pipeline"):
                rvc.config.x_pad = x_pad
                rvc.vc.pipeline.x_pad = x_pad
                rvc.vc.pipeline.t_pad_tgt = int(rvc.vc.tgt_sr * x_pad)
                rvc.vc.pipeline.t_pad = int(16000 * x_pad)
                rvc.vc.pipeline.t_pad2 = int(16000 * x_pad * 2)
                rvc.vc.pipeline.t_max = 10000000
                
            model_info = rvc.models[rvc.current_model]
            file_index = model_info.get("index", "")
            
            wav_opt = rvc.vc.vc_single(
                sid=0,
                input_audio_path=f_in,
                f0_up_key=0,
                f0_method="rmvpe",
                file_index=file_index,
                index_rate=0.0,
                filter_radius=3,
                resample_sr=0,
                rms_mix_rate=1.0,
                protect=0.33,
                f0_file="",
                file_index2=""
            )
            
            if isinstance(wav_opt, tuple) or isinstance(wav_opt, str):
                raise ValueError(f"RVC internal voice conversion failed for {f}: {wav_opt}")
                
            target_sr = rvc.vc.tgt_sr
            
            # DC Centering & Peak Normalization
            y = wav_opt.astype(np.float32)
            y = y - np.mean(y)
            peak = np.max(np.abs(y))
            if peak > 0:
                y = y * (0.95 / peak)
            wav_opt_processed = (y * 32767.0).astype(np.int16)
            
            temp_wav_path = f_out + ".temp.wav"
            wavfile.write(temp_wav_path, target_sr, wav_opt_processed)
            
            transcode_cmd = [
                "ffmpeg", "-y", 
                "-i", temp_wav_path, 
                "-codec:a", "libmp3lame", 
                "-b:a", "192k", 
                f_out
            ]
            res = subprocess.run(transcode_cmd, capture_output=True, text=True)
            
            if os.path.exists(temp_wav_path):
                os.remove(temp_wav_path)
                
            if res.returncode != 0:
                print(f"  ❌ FFmpeg Transcoding Error for {f}: {res.stderr}")
                raise RuntimeError(f"FFmpeg Transcoding failed: {res.stderr}")
                
        print("  ✅ All chunks processed successfully in batch mode.")
        
    else:
        # Single file mode
        rvc = RVCInference(device=device)
        rvc.load_model(model_path)
        
        if hasattr(rvc, "vc") and hasattr(rvc.vc, "pipeline"):
            duration = librosa.get_duration(path=input_path)
            x_pad = min(0.3, duration / 3.0)
            x_pad = max(0.02, x_pad)
            
            rvc.config.x_pad = x_pad
            rvc.vc.pipeline.x_pad = x_pad
            rvc.vc.pipeline.t_pad_tgt = int(rvc.vc.tgt_sr * x_pad)
            rvc.vc.pipeline.t_pad = int(16000 * x_pad)
            rvc.vc.pipeline.t_pad2 = int(16000 * x_pad * 2)
            rvc.vc.pipeline.t_max = 10000000
            print(f"  ℹ️ Dynamic Safe Padding Configured: duration={duration:.2f}s | x_pad={x_pad:.3f}s | t_pad_tgt={rvc.vc.pipeline.t_pad_tgt}")
        
        model_info = rvc.models[rvc.current_model]
        file_index = model_info.get("index", "")
        
        print("  ℹ️ Running voice conversion...")
        wav_opt = rvc.vc.vc_single(
            sid=0,
            input_audio_path=input_path,
            f0_up_key=0,
            f0_method="rmvpe",
            file_index=file_index,
            index_rate=0.0,
            filter_radius=3,
            resample_sr=0,
            rms_mix_rate=1.0,
            protect=0.33,
            f0_file="",
            file_index2=""
        )
        
        if isinstance(wav_opt, tuple) or isinstance(wav_opt, str):
            raise ValueError(f"RVC internal voice conversion failed: {wav_opt}")
            
        target_sr = rvc.vc.tgt_sr
        print(f"  ℹ️ RVC Raw Output Length: {len(wav_opt)} samples at {target_sr} Hz.")
        
        print("  ℹ️ Performing Forensic Audio Enhancement: DC Centering & Peak Normalization...")
        y = wav_opt.astype(np.float32)
        y = y - np.mean(y)
        peak = np.max(np.abs(y))
        if peak > 0:
            y = y * (0.95 / peak)
        wav_opt_processed = (y * 32767.0).astype(np.int16)
        
        temp_wav_path = output_path + ".temp.wav"
        print(f"  ℹ️ Writing enhanced, normalized WAV data to: {temp_wav_path}")
        wavfile.write(temp_wav_path, target_sr, wav_opt_processed)
        
        print(f"  ℹ️ Transcoding temporary WAV to target MP3 path: {output_path}")
        transcode_cmd = [
            "ffmpeg", "-y", 
            "-i", temp_wav_path, 
            "-codec:a", "libmp3lame", 
            "-b:a", "192k", 
            output_path
        ]
        res = subprocess.run(transcode_cmd, capture_output=True, text=True)
        
        if os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)
            
        if res.returncode != 0:
            print(f"  ❌ FFmpeg Transcoding Error: {res.stderr}")
            raise RuntimeError(f"FFmpeg Transcoding failed: {res.stderr}")
            
        print("  ✅ RVC Inference & MP3 Transcoding: Success.")


def run_rvc(input_path, output_path, model_path):
    print(f"  ✅ RVC Inference (v30.0): Converting {input_path} using {model_path}...")
    
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # Check if directory mode or single file mode
    if os.path.isdir(input_path):
        duration = 0.0
        # Sum durations of all chunk files to check OOM
        for f in os.listdir(input_path):
            if f.startswith("chunk_") and f.endswith(".mp3"):
                try:
                    duration += librosa.get_duration(path=os.path.join(input_path, f))
                except Exception:
                    pass
    else:
        try:
            duration = librosa.get_duration(path=input_path)
            print(f"  ℹ️ Input audio duration: {duration:.2f} seconds.")
        except Exception as e:
            print(f"  ⚠️ Warning getting audio duration: {e}. Defaulting to CPU safe-mode.")
            duration = 999.0
        
    # Route to CPU if total duration is long (>60s) to proactively prevent OOM on RTX 3050 (6GB VRAM)
    if duration > 60.0:
        print("  ℹ️ Proactive OOM routing: Audio > 60s. Routing directly to CPU safe-mode.")
        device = "cpu"
    else:
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        
    print(f"  ℹ️ Initialized RVC on target device: {device}")
    
    try:
        _execute_rvc(input_path, output_path, model_path, device)
    except Exception as e:
        err_msg = str(e).lower()
        is_cuda_error = (
            "out of memory" in err_msg or 
            "cuda error" in err_msg or 
            "acceleratorerror" in err_msg or
            "allocation" in err_msg
        )
        if device.startswith("cuda") and is_cuda_error:
            print(f"  ⚠️ CUDA OOM or CUDA execution error: {e}")
            print("  🔄 Initiating resilient CPU Fallback mode...")
            
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception as cache_e:
                print(f"  ⚠️ Note: Could not empty CUDA cache: {cache_e}")
                
            if not os.path.isdir(input_path):
                temp_wav_path = output_path + ".temp.wav"
                if os.path.exists(temp_wav_path):
                    try:
                        os.remove(temp_wav_path)
                    except Exception:
                        pass
            
            try:
                _execute_rvc(input_path, output_path, model_path, "cpu")
            except Exception as cpu_e:
                print(f"  ❌ RVC Inference CPU Fallback Error: {cpu_e}")
                sys.exit(1)
        else:
            print(f"  ❌ RVC Inference Error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input")
    parser.add_argument("-o", "--output")
    parser.add_argument("-m", "--model")
    args = parser.parse_args()
    run_rvc(args.input, args.output, args.model)
