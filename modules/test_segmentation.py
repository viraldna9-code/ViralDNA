import re

def segment_bilingual_text(text: str):
    # Let's find all contiguous Telugu segments
    # Telugu unicode block is U+0C00 to U+0C7F
    pattern = re.compile(r'([\u0c00-\u0c7f]+(?:[\s,\.\-\"\'](?:[\u0c00-\u0c7f]+))*)')
    
    segments = []
    last_idx = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        # Anything before the match is English (if non-empty)
        if start > last_idx:
            eng_text = text[last_idx:start]
            if eng_text.strip():
                segments.append({"lang": "en", "text": eng_text})
        # The matched part is Telugu
        te_text = match.group(0)
        if te_text.strip():
            segments.append({"lang": "te", "text": te_text})
        last_idx = end
        
    # Any remaining text at the end is English
    if last_idx < len(text):
        eng_text = text[last_idx:]
        if eng_text.strip():
            segments.append({"lang": "en", "text": eng_text})
            
    return segments

if __name__ == "__main__":
    test_texts = [
        "Today, the Chief Minister of ఆంధ్ర ప్రదేశ్ announced a new welfare scheme.",
        "Breaking News from తెలంగాణ: Hyderabad is preparing for elections.",
        "ఆంధ్ర ప్రదేశ్ is a state in southern India. నమస్కారం to all our viewers."
    ]
    for idx, text in enumerate(test_texts):
        print(f"\n--- Test {idx+1} ---")
        print("Original:", text)
        segs = segment_bilingual_text(text)
        for s in segs:
            print(f"  [{s['lang'].upper()}]: {repr(s['text'])}")
