"""
OpenCue - Profanity Detector

Regex-based profanity detection using configurable word lists.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any

# Load word list
WORDLIST_PATH = Path(__file__).parent / "wordlist.json"
_wordlist = None
_patterns = None


def load_wordlist() -> Dict[str, Any]:
    """Load the profanity word list from JSON file"""
    global _wordlist
    if _wordlist is None:
        if WORDLIST_PATH.exists():
            with open(WORDLIST_PATH, 'r', encoding='utf-8') as f:
                _wordlist = json.load(f)
        else:
            print(f"[OpenCue] Warning: Word list not found at {WORDLIST_PATH}")
            _wordlist = {"version": "1.0", "categories": {}}
    return _wordlist


def compile_patterns() -> List[Dict[str, Any]]:
    """Compile regex patterns from word list"""
    global _patterns
    if _patterns is not None:
        return _patterns

    wordlist = load_wordlist()
    _patterns = []

    for category_name, category_data in wordlist.get("categories", {}).items():
        for severity, words in category_data.items():
            if not isinstance(words, list):
                continue

            for word_entry in words:
                if isinstance(word_entry, dict):
                    word = word_entry.get("word", "")
                    display = word_entry.get("display", word[:2] + "*" * (len(word) - 2))
                    variants = word_entry.get("variants", [])
                    context_required = word_entry.get("context_required", False)
                else:
                    word = str(word_entry)
                    display = word[:2] + "*" * (len(word) - 2) if len(word) > 2 else word
                    variants = []
                    context_required = False

                # Build pattern for word and variants
                all_words = [word] + variants
                for w in all_words:
                    if not w:
                        continue

                    # Create word boundary pattern
                    # Allows for common obfuscations like f*ck, sh!t
                    pattern_str = r'\b' + re.escape(w).replace(r'\*', r'[*@#$!]?') + r'\b'

                    try:
                        pattern = re.compile(pattern_str, re.IGNORECASE)
                        _patterns.append({
                            "pattern": pattern,
                            "word": word,
                            "display": display,
                            "category": f"language.{category_name}.{severity}",
                            "severity": severity,
                            "context_required": context_required
                        })
                    except re.error as e:
                        print(f"[OpenCue] Invalid regex for '{w}': {e}")

    print(f"[OpenCue] Compiled {len(_patterns)} profanity patterns")
    return _patterns


def detect_profanity(text: str) -> List[Dict[str, Any]]:
    """
    Detect profanity in text.

    Args:
        text: Text to analyze

    Returns:
        List of detection results
    """
    patterns = compile_patterns()
    detections = []
    seen_words = set()  # Avoid duplicate detections

    for pattern_info in patterns:
        pattern = pattern_info["pattern"]
        matches = pattern.findall(text)

        for match in matches:
            word_key = pattern_info["word"].lower()
            if word_key in seen_words:
                continue

            # TODO: Add context analysis for context_required words
            # For now, detect all matches
            if pattern_info["context_required"]:
                # Simple heuristic: only flag if used as exclamation
                exclamation_patterns = [
                    r'\b(oh\s+)?' + re.escape(match) + r'[!]?\b',
                    r'\b' + re.escape(match) + r'\s+(damn|dammit)',
                ]
                is_exclamation = any(
                    re.search(p, text, re.IGNORECASE)
                    for p in exclamation_patterns
                )
                if not is_exclamation:
                    continue

            seen_words.add(word_key)
            detections.append({
                "word": pattern_info["word"],
                "display": pattern_info["display"],
                "category": pattern_info["category"],
                "severity": pattern_info["severity"],
                "confidence": 0.95 if not pattern_info["context_required"] else 0.75
            })

    return detections


def reload_wordlist():
    """Reload word list (for dynamic updates)"""
    global _wordlist, _patterns
    _wordlist = None
    _patterns = None
    load_wordlist()
    compile_patterns()
