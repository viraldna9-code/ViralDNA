#!/usr/bin/env python3
"""Download VoxCPM2-ONNX models - direct file by file."""
import os, sys
from huggingface_hub import hf_hub_download

dest = "/home/jay/ViralDNA/models/voxcpm2-onnx"
os.makedirs(dest, exist_ok=True)

# Only download missing .data files
files = [
    "voxcpm2_prefill.onnx.data",    # ~7.8GB
    "voxcpm2_decode_step.onnx.data", # ~8.1GB
]

repo = "ai4all8/VoxCPM2-ONNX"

for fname in files:
    fpath = os.path.join(dest, fname)
    if os.path.exists(fpath) and os.path.getsize(fpath) > 100*1024*1024:
        print(f"  [SKIP] {fname} ({os.path.getsize(fpath)/1024/1024/1024:.1f} GB)")
        continue
    print(f"  [DOWNLOAD] {fname}...")
    try:
        hf_hub_download(repo_id=repo, filename=fname, local_dir=dest, local_dir_use_symlinks=False)
        size = os.path.getsize(fpath)
        print(f"  [OK] {fname} ({size/1024/1024/1024:.1f} GB)")
    except Exception as e:
        print(f"  [ERROR] {fname}: {e}")

# Also download PyTorch model for preprocessing (needed by infer.py)
print("\nDownloading VoxCPM2 PyTorch weights for preprocessing...")
try:
    from voxcpm import VoxCPM
    VoxCPM.from_pretrained("openbmb/VoxCPM2")
    print("  [OK] PyTorch weights downloaded")
except Exception as e:
    print(f"  [ERROR] PyTorch weights: {e}")

print("\nAll done.")
print("Files:")
for f in sorted(os.listdir(dest)):
    fp = os.path.join(dest, f)
    if os.path.isfile(fp):
        print(f"  {f}: {os.path.getsize(fp)/1024/1024:.0f} MB")
