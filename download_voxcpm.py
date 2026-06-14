#!/usr/bin/env python3
"""Download VoxCPM2-ONNX models from HuggingFace."""
import os
from huggingface_hub import snapshot_download

dest = "/home/jay/ViralDNA/models/voxcpm2-onnx"
os.makedirs(dest, exist_ok=True)

print("Downloading VoxCPM2-ONNX models (~16GB total)...")
snapshot_download(
    "ai4all8/VoxCPM2-ONNX",
    local_dir=dest,
    ignore_patterns=["*.md", "*.txt"]
)
print(f"Downloaded to {dest}")

# Also download the PyTorch model for preprocessing
print("\nDownloading VoxCPM2 PyTorch weights for preprocessing...")
from voxcpm import VoxCPM
VoxCPM.from_pretrained("openbmb/VoxCPM2")
print("Done.")
