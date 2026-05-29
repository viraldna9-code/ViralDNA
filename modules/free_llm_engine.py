# VERSION: 1.0
# MODULE: free_llm_engine.py
# PURPOSE: 100% Free Hugging Face Serverless Inference Client (No billing required)

import requests, json, os

class FreeLlmEngine:
    def __init__(self):
        # Users can get a free token from huggingface.co (Settings -> Access Tokens)
        # Drop it into your environment variables as HF_TOKEN or HF_API_KEY
        self.api_key = os.getenv("HF_TOKEN", os.getenv("HF_API_KEY", ""))
        self.model = "meta-llama/Meta-Llama-3-8B-Instruct"
        self.url = f"https://api-inference.huggingface.co/models/{self.model}"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
            "Content-Type": "application/json"
        }
        print(f"  ✅ FreeLlmEngine (v1.0): Hugging Face Serverless Active ({self.model})")

    def ask(self, prompt: str) -> dict:
        if not self.api_key:
            print("  ⚠️ FreeLlmEngine Warning: No HF_TOKEN found in environment. Call limit is restricted.")
            
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 1500,
                "temperature": 0.7,
                "return_full_text": False
            }
        }
        
        try:
            r = requests.post(self.url, json=payload, headers=self.headers)
            if r.status_code == 200:
                text = r.json()[0].get("generated_text", "")
                # Extract JSON block
                import re
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
            else:
                print(f"❌ FreeLlmEngine Error {r.status_code}: {r.text}")
        except Exception as e:
            print(f"❌ FreeLlmEngine Exception: {e}")
            
        return {"main": "Breaking news report."}
