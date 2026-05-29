# Placeholder diagnostic for Phase 1 (RSS ingestion)
import json, os
from . import config

def run():
    # Simulate RSS fetch by reading a sample file if it exists
    sample_path = os.path.join(config.DRIVE["BASE"], "sample_rss.json")
    if os.path.exists(sample_path):
        with open(sample_path) as f:
            data = json.load(f)
    else:
        data = {"items": []}
    # Basic sanity checks
    raw_count = len(data.get("items", []))
    filtered = [i for i in data.get("items", []) if i.get("title")]
    filtered_count = len(filtered)
    print("Phase 1 Diagnostic:")
    print(f"Raw items: {raw_count}, Filtered items: {filtered_count}")
    # Write a minimal runtime JSON for downstream phases
    out_path = os.path.join(config.DRIVE["RUNTIME"], "phase1_debug.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as out:
        json.dump({"raw": raw_count, "filtered": filtered_count, "items": filtered}, out, indent=2)
    print(f"Runtime file written to {out_path}")

if __name__ == "__main__":
    run()
