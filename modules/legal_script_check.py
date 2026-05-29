# VERSION: 50.2
# MODULE: legal_script_check.py
# PURPOSE: Zero-Tolerance Compliance & Legal Audit Gate (Dynamic LLM Check with Local Regex Safety-Net)

import re

class LegalScriptCheck:
    def __init__(self, engine, config_dict: dict):
        self.engine = engine
        self.config = config_dict
        # Local regex sweep for severe offensive terms/slurs (Emergency Fallback)
        self.blacklist_pattern = re.compile(
            r'\b(bastard|scumbag|fraudster|terrorist|criminal scum|illegal immigrant)\b', 
            re.IGNORECASE
        )
        print("  ✅ LegalScriptCheck (v50.1): Zero-Tolerance Compliance Gate Active.")

    def check(self, script: str, context: dict) -> dict:
        topic_title = context.get("topic", "Regional News")
        print(f"    Legal Audit: Auditing script draft for compliance...")
        
        # 1. Try Live LLM Legal Audit
        if self.engine:
            try:
                print("    Legal Audit: Routing compliance audit to Gemini API...")
                prompt = (
                    "You are the Chief Legal Counsel for ViralDNA, a premium broadcast-grade news organization.\n"
                    "Evaluate the following news script draft for ONLY the following severe violations:\n"
                    "1. Hate speech or slurs targeting ethnic/religious groups\n"
                    "2. Graphic violence descriptions\n"
                    "3. Direct, unsubstantiated defamation of a named individual (not policy criticism)\n"
                    "4. Dangerous medical misinformation (e.g., 'drink bleach')\n\n"
                    "IMPORTANT: Reporting on immigration policy, government rules, or attorney commentary\n"
                    "is LEGITIMATE NEWS and must NOT be flagged as misinformation unless it contains\n"
                    "demonstrably false factual claims presented as settled fact.\n\n"
                    f"News Topic Context: {topic_title}\n"
                    f"Script Draft:\n\"\"\"\n{script}\n\"\"\"\n\n"
                    "Does this script contain ANY of the 4 severe violations listed above?\n"
                    "CRITICAL RESPONSE FORMAT:\n"
                    "Reply with exactly two lines:\n"
                    "VERDICT: [PASS or FAIL]\n"
                    "REASON: [A brief, one-sentence justification]\n"
                )
                
                if response:
                    match_verdict = re.search(r'VERDICT:\s*(PASS|FAIL)', response, re.IGNORECASE)
                    match_reason = re.search(r'REASON:\s*(.*)', response, re.IGNORECASE)
                    
                    if match_verdict:
                        verdict = match_verdict.group(1).upper()
                        reason = match_reason.group(1).strip() if match_reason else "Compliance audit completed."
                        print(f"    ✅ Legal Audit Complete. Verdict: {verdict} | Reason: {reason}")
                        return {"verdict": verdict, "reason": reason}
                        
            except Exception as e:
                print(f"    ⚠️ Live Legal Audit failed: {e}. Activating local safety fallback...")
                
        # 2. Local Safe Fallback (Regex Scan + Local Pass)
        print("    Legal Audit: Performing local heuristic regex audit sweep...")
        if self.blacklist_pattern.search(script):
            reason = "Failed local safety sweep: Detected high-risk offensive/defamatory language."
            print(f"    ❌ Legal Audit FAIL. Verdict: FAIL | Reason: {reason}")
            return {"verdict": "FAIL", "reason": reason}
            
        reason = "Passed local safety-net regex sweep (Emergency Fallback)."
        print(f"    ✅ Legal Audit PASS. Verdict: PASS | Reason: {reason}")
        return {"verdict": "PASS", "reason": reason}
