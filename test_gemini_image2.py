#!/usr/bin/env python3
"""Test Gemini image generation specifically."""
import os, sys

api_key = os.environ.get("GEMINI_IMAGE_API_KEY", "")
if not api_key:
    print("ERROR: Set GEMINI_IMAGE_API_KEY env var")
    sys.exit(1)

from google import genai
from google.genai import types

client = genai.Client(api_key=api_key)

# Test 1: Try different image generation models
image_models = [
    'gemini-2.0-flash-exp-image-generation',
    'gemini-2.0-flash-preview-image-generation',
    'imagen-3.0-generate-002',
    'imagen-3.0-generate-001',
]

for model_name in image_models:
    print(f"\n=== Testing: {model_name} ===")
    try:
        resp = client.models.generate_content(
            model=model_name,
            contents=(
                'A cinematic wide shot of a futuristic Telugu news studio with holographic displays, '
                'dark moody lighting, professional broadcast aesthetic, photorealistic'
            ),
            config=types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE']
            )
        )
        for part in resp.parts:
            if part.inline_data and part.inline_data.data:
                img_data = part.inline_data.data
                out_path = f"/home/jay/ViralDNA/output/test_{model_name.replace('/', '_')}.png"
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, 'wb') as f:
                    f.write(img_data)
                print(f"  IMAGE SAVED: {out_path} ({len(img_data)} bytes)")
                break
            if part.text:
                print(f"  Text: {part.text[:100]}")
    except Exception as e:
        print(f"  Error: {e}")

# Test 2: List all available models
print("\n=== All Available Models ===")
try:
    for m in client.models.list():
        name = m.name
        methods = m.supported_methods if hasattr(m, 'supported_methods') else []
        if 'image' in name.lower() or 'imagen' in name.lower() or 'flash' in name.lower():
            print(f"  {name} | methods: {methods}")
except Exception as e:
    print(f"  List error: {e}")

print("\n=== DONE ===")
