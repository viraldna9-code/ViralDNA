#!/usr/bin/env python3
"""Download Fish Speech model using huggingface_hub Python API."""
import os
from huggingface_hub import snapshot_download

checkpoint_dir = "/home/jay/fish-speech-v1.5/checkpoints/fish-speech-1.4"

if os.path.exists(checkpoint_dir) and len(os.listdir(checkpoint_dir)) > 5:
    print("Model already downloaded.")
    exit(0)

print("Downloading fish-speech-1.4 from HuggingFace (~5GB)...")
snapshot_download(
    repo_id="fishaudio/fish-speech-1.4",
    local_dir=checkpoint_dir,
    local_dir_use_symlinks=False
)
print("Download complete.")
for root, dirs, files in os.walk(checkpoint_dir):
    for f in files:
        full = os.path.join(root, f)
        size = os.path.getsize(full) / (1024*1024)
        print(f"  {os.path.relpath(full, checkpoint_dir)} ({size:.1f} MB)")
