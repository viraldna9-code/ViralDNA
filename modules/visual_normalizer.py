# VERSION: 25.0
# MODULE: visual_normalizer.py
# PURPOSE: Force-converts all visual assets to FFmpeg-compatible RGB JPEG

from PIL import Image
import os

def normalize_visual(input_path, output_path):
    try:
        # Force conversion to RGB JPEG to avoid RGBA/WebP FFmpeg crashes
        with Image.open(input_path) as img:
            rgb_img = img.convert('RGB')
            rgb_img.save(output_path, "JPEG")
        return True
    except Exception as e:
        print(f"  ❌ Normalization Error: {e}")
        return False
