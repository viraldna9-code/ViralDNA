#!/usr/bin/env python3
"""Download VoxCPM2-ONNX models - direct file download."""
import os
from huggingface_hub import hf_hub_download, HfFileSystem

dest = "/home/jay/ViralDNA/models/voxcpm2-onnx"
os.makedirs(dest, exist_ok=True)

files = [
    "audio_vae_encoder.onnx",
    "audio_vae_encoder.onnx.data",
    "audio_vae_decoder.onnx",
    "audio_vae_decoder.onnx.data",
    "voxcpm2_prefill.onnx",
    "voxcpm2_prefill.onnx.data",
    "voxcpm2_decode_step.onnx",
    "voxcpm2_decode_step.onnx.data",
]

fs = HfFileSystem()
repo = "ai4all8/VoxCPM2-ONNX"

# List all files in repo
print("Listing repo files...")
all_files = fs.ls(repo, detail=False)
for f in all_files:
    print(f"  {f}")

print("\nDownloading missing files...")
for fname in files:
    fpath = os.path.join(dest, fname)
    if os.path.exists(fpath):
        size = os.path.getsize(fpath)
        if size > 1000:  # skip small files that are probably complete
            print(f"  [SKIP] {fname} ({size/1024/1024:.0f} MB)")
            continue
    print(f"  [DOWNLOAD] {fname}...")
    try:
        hf_hub_download(repo_id=repo, filename=fname, local_dir=dest, local_dir_use_symlinks=False)
        print(f"  [OK] {fname}")
    except Exception as e:
        print(f"  [ERROR] {fname}: {e}")

print("\nDone. Files:")
for f in sorted(os.listdir(dest)):
    fp = os.path.join(dest, f)
    if os.path.isfile(fp):
        print(f"  {f}: {os.path.getsize(fp)/1024/1024:.0f} MB")
