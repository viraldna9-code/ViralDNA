#!/usr/bin/env python3
"""Test Gemini image generation — read key from file."""
import os, sys, json

# Read key from file
key_file = os.path.join(os.path.dirname(__file__), ".gemini_image_key")
if os.path.exists(key_file):
    api_key = open(key_file).read().strip()
else:
    # Try env
    api_key = os.environ.get("GEMINI_IMAGE_API_KEY", "").strip()

if not api_key:
    print("ERROR: No API key. Put it in .gemini_image_key or set GEMINI_IMAGE_API_KEY")
    sys.exit(1)

print(f"KeyPrefix: {api_key[:10]}...")
print(f"KeyLen: {len(api_key)}")

from google import genai
from google.genai import types

client = genai.Client(api_key=api_key)

# Test text first
print("\n=== Text Generation Test ===")
try:
    resp = client.models.generate_content(
        model='gemini-2.0-flash',
        contents='Reply with: OK'
    )
    print(f"  TEXT OK: {resp.text.strip()}")
except Exception as e:
    print(f"  TEXT ERROR: {e}")

# Test image generation
print("\n=== Image Generation Test ===")
try:
    resp = client.models.generate_content(
        model='gemini-2.0-flash-exp-image-generation',
        contents=(
            'A cinematic photorealistic wide shot of a futuristic Telugu news studio, '
            'holographic displays showing Telugu text, dark moody cinematic lighting, '
            'professional broadcast aesthetic, volumetric light rays, shallow depth of field'
        ),
        config=types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE']
        )
    )
    img_saved = False
    for part in resp.parts:
        if part.inline_data and part.inline_data.data:
            img_data = part.inline_data.data
            out_path = "/home/jay/ViralDNA/output/test_gemini_image.png"
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'wb') as f:
                f.write(img_data)
            print(f"  IMAGE SAVED: {out_path} ({len(img_data)} bytes)")
            img_saved = True
            break
        if part.text:
            print(f"  Text: {part.text[:200]}")
    if not img_saved:
        print("  No image in response")
except Exception as e:
    print(f"  IMAGE ERROR: {e}")

print("\n=== DONE ===")
