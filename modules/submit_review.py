# VERSION: 1.0
# MODULE: submit_review.py
# PURPOSE: CLI Utility to log user reviews after seeing videos, thumbnails, or scripts

import sys
from growth_observer import GrowthObserver

def main():
    if len(sys.argv) < 5:
        print("\n" + "="*50)
        print("📝 VIRALDNA USER REVIEW REGISTRY")
        print("="*50)
        print("Usage: python3 submit_review.py <category> <version> <score> <feedback_text>")
        print("\nCategories: 'scripts' | 'thumbnails' | 'videos'")
        print("Example: python3 submit_review.py thumbnails v1.0 9 \"Yellow text is highly readable, excellent watermark placement.\"")
        print("="*50 + "\n")
        sys.exit(1)

    category = sys.argv[1].lower().strip()
    version = sys.argv[2].strip()
    
    try:
        score = int(sys.argv[3])
        if not (1 <= score <= 10):
            raise ValueError
    except ValueError:
        print("❌ Error: Score must be an integer between 1 and 10.")
        sys.exit(1)

    feedback_text = sys.argv[4].strip()

    observer = GrowthObserver()
    success = observer.log_user_review(category, feedback_text, score, version)
    
    if success:
        print(f"✅ Successfully recorded your {category} {version} feedback in the growth ledger!")
    else:
        print("❌ Failed to commit review to ledger.")

if __name__ == "__main__":
    main()
