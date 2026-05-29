#!/usr/bin/env python3
"""Test Gemini 2.5 Flash Image generation."""
import os, sys

key = open(os.path.join(os.path.dirname(__file__), ".gemini_image_key")).read().strip()
print(f"Key: {key[:10]}... ({len(key)} chars)")

from google import genai
from google.genai import types

client = genai.Client(api_key=key)

# Test image generation with gemini-2.5-flash-image
print("\n=== Image Generation: gemini-2.5-flash-image ===")
try:
    resp = client.models.generate_content(
        model='gemini-2.5-flash-image',
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
            out_path = "/home/jay/ViralDNA/output/test_gemini_2.5_image.png"
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
        print(f"  Response: {resp}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== DONE ===")
