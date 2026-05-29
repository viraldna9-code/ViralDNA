#!/usr/bin/env python3
"""Test new Gemini API key with google.genai SDK for image generation."""
import os, sys, json

api_key = os.environ.get("GEMINI_IMAGE_API_KEY", "")
if not api_key:
    print("ERROR: Set GEMINI_IMAGE_API_KEY env var")
    sys.exit(1)

try:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    # Test text generation
    print("=== Test Text Generation ===")
    resp = client.models.generate_content(
        model='gemini-2.0-flash',
        contents='Say ViralDNA in Telugu and English'
    )
    print(f"  OK: {resp.text.strip()[:100]}")

    # Test image generation with Gemini 2.0 Flash Image
    print("\n=== Test Image Generation ===")
    resp = client.models.generate_content(
        model='gemini-2.0-flash-exp-image-generation',
        contents=(
            'A cinematic wide shot of a futuristic Telugu news studio with holographic displays, '
            'dark moody lighting, professional broadcast aesthetic, photorealistic, 16:9'
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
            print(f"  Text: {part.text[:150]}")

    if not img_saved:
        print("  No image generated")
        if hasattr(resp, 'candidates'):
            for c in resp.candidates:
                print(f"  Finish reason: {c.finish_reason}")

    # Check quota/limits info
    print("\n=== Model Info ===")
    try:
        model_info = client.models.get(model='gemini-2.0-flash-exp-image-generation')
        print(f"  Model: {model_info.display_name}")
    except Exception as e:
        print(f"  Model info error: {e}")

    print("\n=== ALL TESTS COMPLETE ===")

except ImportError as e:
    print(f"ERROR: {e}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
