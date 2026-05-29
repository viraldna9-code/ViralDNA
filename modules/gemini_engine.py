# VERSION: 63.0
# MODULE: gemini_engine.py
# PURPOSE: Hybrid Unified Interface — Direct Google AI Studio (Pay-as-you-go)
#          priority, OpenRouter as fallback, local heuristic as last resort.

import requests
import json
import re
import os
from dotenv import load_dotenv
import config

# Load variables from user's standard .env
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path)

class GeminiEngine:
    def __init__(self):
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY") or config.API_KEYS.get("GEMINI_API_KEY")

        # Primary models for routing
        self.openrouter_models = ["google/gemini-2.5-flash", "google/gemini-2.5-pro", "meta-llama/llama-3-8b-instruct"]
        self.gemini_models = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"]

    def _generate_local_fallback(self, prompt: str) -> dict:
        """Dynamic Local Heuristic Fallback: Generates a detailed script locally."""
        print("    ⚠️ Network/API Failed. Generating high-quality local fallback script...")

        match = re.search(r'Topic: (.*?)\n', prompt)
        topic_title = match.group(1) if match else "breaking regional updates"

        main_script = (
            f"Good evening. This is ViralDNA, keeping our global Telugu family connected to our beloved homeland. "
            f"Today, we bring you an important development regarding {topic_title}. "
            f"Our reporters on the ground indicate that this situation is developing rapidly and impacting local communities. "
            f"As we watch from the United States, the United Kingdom, Canada, and Australia, we understand your deep-seated concern "
            f"for your loved ones and the land you call home. This development is creating significant discussions among local "
            f"businesses, traders, and everyday commuters. Proponents argue that these recent changes are necessary to ensure "
            f"equitable access, transparency, and progress across the region. However, critics point out potential logistical "
            f"challenges that could disrupt daily operations. We will continue to monitor the ground reality and bring you "
            f"the most authentic, broadcast-grade news directly from our homeland. Stay connected to your roots with ViralDNA."
        )

        return {
            "main": main_script,
            "short_1": f"=== SHORT 1 ===\nBreaking update: {topic_title} is creating major discussions across Andhra and Telangana today. Stay informed with ViralDNA.",
            "short_2": f"=== SHORT 2 ===\nDevelopments regarding {topic_title} are moving fast. We bring you direct real-time updates. Follow ViralDNA.",
            "short_3": f"=== SHORT 3 ===\nAre you watching our homeland's policy shifts from abroad? Follow ViralDNA to keep your family informed.",
        }

    def ask(self, prompt: str) -> str:
        """Raw Text Engine: Direct Gemini first, then OpenRouter, then local fallback."""
        # 1. Try direct Google Generative API FIRST (Pay-as-you-go preferred)
        if self.gemini_key:
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            for model in self.gemini_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_key}"
                try:
                    print(f"    GeminiEngine: Routing raw ask to direct {model}...")
                    response = requests.post(url, json=payload, timeout=8).json()
                    if "candidates" in response:
                        print(f"    ✅ GeminiEngine Success: {model} responded directly.")
                        return response["candidates"][0]["content"]["parts"][0]["text"]
                    elif "error" in response:
                        print(f"    ⚠️ Direct model {model} error: {response['error'].get('message', '')[:100]}")
                except Exception as e:
                    print(f"    ⚠️ Direct model {model} exception: {e}")

        # 2. Try OpenRouter as fallback
        if self.openrouter_key:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self.openrouter_key}", "Content-Type": "application/json"}
            for model in self.openrouter_models:
                payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1500}
                try:
                    print(f"    GeminiEngine: Fallback routing raw ask to {model} via OpenRouter...")
                    r = requests.post(url, json=payload, headers=headers, timeout=25)
                    if r.status_code == 200:
                        content = r.json()["choices"][0]["message"]["content"]
                        print(f"    ✅ GeminiEngine Success: {model} responded via OpenRouter.")
                        return content
                    else:
                        print(f"    ⚠️ OpenRouter model {model} failed with status {r.status_code}: {r.text[:100]}")
                except Exception as e:
                    print(f"    ⚠️ OpenRouter model {model} exception: {e}")

        # 3. Final fallback — local heuristic
        print("    ⚠️ All API providers failed. Generating local fallback script...")
        fallback = self._generate_local_fallback(prompt)
        return f"=== MAIN ===\n{fallback['main']}\n{fallback['short_1']}\n{fallback['short_2']}\n{fallback['short_3']}"

    def ask_structured(self, prompt: str) -> dict:
        """Structured Engine: Direct Gemini first, then OpenRouter, then local fallback."""
        # 1. Try direct Google Generative API FIRST (Pay-as-you-go preferred)
        if self.gemini_key:
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 4096,
                    "responseSchema": {
                        "type": "OBJECT",
                        "properties": {
                            "main": {"type": "OBJECT", "properties": {"script": {"type": "STRING"}, "title_variants": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"title": {"type": "STRING"}, "description": {"type": "STRING"}}, "required": ["title", "description"]}, "minItems": 3, "maxItems": 3}}, "required": ["script", "title_variants"]},
                            "short_1": {"type": "OBJECT", "properties": {"script": {"type": "STRING"}, "title_variants": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"title": {"type": "STRING"}, "description": {"type": "STRING"}}, "required": ["title", "description"]}, "minItems": 3, "maxItems": 3}}, "required": ["script", "title_variants"]},
                            "short_2": {"type": "OBJECT", "properties": {"script": {"type": "STRING"}, "title_variants": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"title": {"type": "STRING"}, "description": {"type": "STRING"}}, "required": ["title", "description"]}, "minItems": 3, "maxItems": 3}}, "required": ["script", "title_variants"]},
                            "short_3": {"type": "OBJECT", "properties": {"script": {"type": "STRING"}, "title_variants": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"title": {"type": "STRING"}, "description": {"type": "STRING"}}, "required": ["title", "description"]}, "minItems": 3, "maxItems": 3}}, "required": ["script", "title_variants"]},
                        },
                        "required": ["main", "short_1", "short_2", "short_3"]
                    }
                }
            }
            for model in self.gemini_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_key}"
                try:
                    print(f"    GeminiEngine: Routing structured to direct {model}...")
                    response = requests.post(url, json=payload, timeout=12).json()
                    if "candidates" in response:
                        raw_text = response["candidates"][0]["content"]["parts"][0]["text"]
                        print(f"    ✅ GeminiEngine Success: direct {model} responded.")
                        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
                        match = re.search(r'\{.*\}', clean_text, re.DOTALL)
                        if match:
                            return json.loads(match.group(0))
                    elif "error" in response:
                        print(f"    ⚠️ Direct model {model} error: {response['error'].get('message', '')[:100]}")
                except Exception as e:
                    print(f"    ⚠️ Direct model {model} exception: {e}")

        # 2. Try OpenRouter as fallback
        if self.openrouter_key:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self.openrouter_key}", "Content-Type": "application/json"}
            system_msg = (
                "You are an expert news producer. Return JSON with keys: main, short_1, short_2, short_3. "
                "main = 5-min deep-dive script (3000+ chars). shorts = 60-sec highlights (500+ chars each)."
            )
            for model in self.openrouter_models:
                payload = {
                    "model": model,
                    "messages": [{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "max_tokens": 4000
                }
                try:
                    print(f"    GeminiEngine: Fallback routing structured to {model} via OpenRouter...")
                    r = requests.post(url, json=payload, headers=headers, timeout=30)
                    if r.status_code == 200:
                        content = r.json()["choices"][0]["message"]["content"]
                        print(f"    ✅ GeminiEngine Success: {model} responded via OpenRouter.")
                        return json.loads(content)
                    else:
                        print(f"    ⚠️ OpenRouter model {model} failed: {r.text[:100]}")
                except Exception as e:
                    print(f"    ⚠️ OpenRouter model {model} exception: {e}")

        # 3. Final fallback — local heuristic
        print("    ⚠️ All API providers failed. Generating local fallback script...")
        return self._generate_local_fallback(prompt)
