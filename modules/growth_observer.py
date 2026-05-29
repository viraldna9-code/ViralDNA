# VERSION: 1.0
# MODULE: growth_observer.py
# PURPOSE: Continuous Intelligence, Feedback Loop, and Channel Growth Auditing System

import os
import json
from datetime import datetime

class GrowthObserver:
    def __init__(self, ledger_path: str = None):
        if ledger_path is None:
            drive_base = os.getenv("DRIVE_BASE", "/home/jay/ViralDNA")
            ledger_path = os.path.join(drive_base, "diagnostics", "growth_ledger.json")
        self.ledger_path = ledger_path
        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
        self.growth_metrics = {
            "target_niche": "Telugu Diaspora (NRI, H1B, Visas)",
            "monetization_goal": "Maximize CPM via high-retention news topics",
            "active_version": "55.0",
            "historical_cvi_weight": 0.85
        }
        print("  🧠 GrowthObserver (v1.0): Intelligence & Audit Layer Active.")

    def load_ledger(self) -> dict:
        """Loads the historical intelligence and feedback ledger."""
        if os.path.exists(self.ledger_path):
            try:
                with open(self.ledger_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"  ⚠️ Error loading ledger: {e}. Resetting ledger.")
        
        return {
            "system_version": "55.0",
            "created_at": datetime.now().isoformat(),
            "execution_history": [],
            "user_reviews": {
                "scripts": [],
                "thumbnails": [],
                "videos": []
            },
            "growth_recommendations": [
                {
                    "priority": "HIGH",
                    "category": "Metadata",
                    "suggestion": "Always prepend 'H-1B Visa Update' or 'US Visa News' in Telugu titles to capture diaspora search index.",
                    "status": "active"
                },
                {
                    "priority": "MEDIUM",
                    "category": "Pacing",
                    "suggestion": "Keep introductory hooks under 10 seconds. In long-form, state the immigration impact within the first 15 seconds.",
                    "status": "active"
                }
            ],
            "known_errors_log": []
        }

    def save_ledger(self, ledger_data: dict):
        """Saves updated ledger data to disk."""
        try:
            with open(self.ledger_path, "w") as f:
                json.dump(ledger_data, f, indent=4)
        except Exception as e:
            print(f"  ❌ Failed to save intelligence ledger: {e}")

    def log_execution(self, topic: dict, duration_map: dict, thumbnail_status: bool, upload_results: dict) -> dict:
        """Records a successful pipeline execution cycle with key diagnostic metrics."""
        ledger = self.load_ledger()
        
        execution_entry = {
            "timestamp": datetime.now().isoformat(),
            "topic_used": topic.get("title", "Unknown"),
            "cvi_score": topic.get("cvi_score", 0),
            "durations": duration_map,
            "thumbnail_generated": thumbnail_status,
            "upload_results": {
                "status": upload_results.get("overall_status", "unknown"),
                "main_id": upload_results.get("main_upload", {}).get("youtube_id", "none"),
                "shorts_count": len(upload_results.get("standalone_shorts_uploads", []))
            }
        }
        
        ledger["execution_history"].append(execution_entry)
        self.save_ledger(ledger)
        print(f"  🟢 Recorded execution entry in the intelligence ledger for topic: '{execution_entry['topic_used']}'.")
        return execution_entry

    def record_user_feedback(self, category: str, feedback_text: str, rating: int, asset_version: str) -> dict:
        """
        Accepts and records human-editor feedback on specific production outputs.
        Categories: 'scripts', 'thumbnails', 'videos'
        """
        if category not in ["scripts", "thumbnails", "videos"]:
            print(f"  ❌ Invalid feedback category: {category}")
            return {"status": "failed", "error": "Invalid category"}

        ledger = self.load_ledger()
        feedback_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_rating": rating, # Scale 1-10
            "feedback": feedback_text,
            "asset_version": asset_version
        }
        
        ledger["user_reviews"][category].append(feedback_entry)
        
        # Core Intelligence: Generate an immediate growth suggestion based on low feedback score
        if rating < 7:
            suggestion = f"Fix required for {category} (v{asset_version}) based on user feedback: '{feedback_text[:60]}...'. Ensure higher quality tolerances next cycle."
            ledger["growth_recommendations"].insert(0, {
                "priority": "CRITICAL",
                "category": category.capitalize(),
                "suggestion": suggestion,
                "status": "pending"
            })
            print(f"  ⚠️ Critical Growth Suggestion registered for {category} due to rating: {rating}/10.")

        self.save_ledger(ledger)
        print(f"  🟢 Registered {category} user feedback in intelligence ledger. Rating: {rating}/10.")
        return feedback_entry

    def log_error(self, phase: str, error_message: str):
        """Captures phase-specific operational failures to suggest future resilience overrides."""
        ledger = self.load_ledger()
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "phase": phase,
            "error": error_message
        }
        ledger["known_errors_log"].append(error_entry)
        
        # Register automatic troubleshooting suggestion
        troubleshoot_suggestion = f"Address recurrent {phase} crash: '{error_message[:50]}...'. Review local fallback configurations."
        ledger["growth_recommendations"].insert(0, {
            "priority": "HIGH",
            "category": f"Error-Fix ({phase})",
            "suggestion": troubleshoot_suggestion,
            "status": "pending"
        })
        
        self.save_ledger(ledger)
        print(f"  🔴 Registered error in intelligence ledger for Phase '{phase}'. Actionable fix compiled.")
