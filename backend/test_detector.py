"""Quick test of profanity detector"""
from profanity.detector import detect_profanity

test_phrases = [
    "What the fuck is going on?",
    "This is bullshit",
    "Holy shit that's amazing",
    "You're such an asshole",
    "Clean sentence here"
]

print("Testing profanity detector...")
print("=" * 50)

for phrase in test_phrases:
    result = detect_profanity(phrase)
    print(f"\nInput: {phrase}")
    print(f"Detections: {len(result)}")
    for r in result:
        print(f"  - {r}")
