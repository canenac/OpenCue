"""
OpenCue - Profanity Detector

Regex-based profanity detection using configurable word lists.
Uses syllable-matched replacements for natural flow.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any

# Import syllable-matched replacement library
from profanity.replacements import (
    get_replacement as get_syllable_replacement,
    get_all_replacements,
    get_replacement_display,
    count_syllables
)


def get_replacement(word: str, match_syllables: bool = True) -> str:
    """
    Get a syllable-matched replacement for a profane word.

    Uses the pre-computed replacement library for consistent,
    syllable-matched replacements that flow naturally.
    """
    word_lower = word.lower().strip()
    replacement = get_syllable_replacement(word_lower, match_syllables=match_syllables)

    # Match original capitalization
    if word.isupper():
        return replacement.upper()
    elif word and word[0].isupper():
        return replacement.capitalize()
    return replacement

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
                    # Also handles variations like fuckin', motherfuckin'
                    escaped = re.escape(w).replace(r'\*', r'[*@#$!]?')

                    # Only add optional suffixes if word doesn't already end with them
                    w_lower = w.lower()
                    if w_lower.endswith(('ing', 'in', 'er', 'ers', 'ed')):
                        # Word already has suffix, just allow optional apostrophe
                        pattern_str = r'\b' + escaped + r"'?\b"
                    else:
                        # Allow optional apostrophe variations and suffixes
                        pattern_str = r'\b' + escaped + r"(?:'|in'?|er|ers|ed|ing)?\b"

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
        List of detection results with position info for precise timing
    """
    patterns = compile_patterns()
    detections = []
    seen_matches = set()  # Avoid duplicate detections of same exact match

    # Calculate text length for position estimation
    text_len = len(text)

    for pattern_info in patterns:
        pattern = pattern_info["pattern"]

        # Use finditer to get match positions
        for match_obj in pattern.finditer(text):
            match = match_obj.group()
            # Use the actual matched text as key (case-insensitive)
            # This allows "fuck" and "fucker" in same subtitle
            match_key = match.lower()
            if match_key in seen_matches:
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

            seen_matches.add(match_key)

            # Calculate position within text (0.0 to 1.0)
            match_start = match_obj.start()
            match_end = match_obj.end()
            position_start = match_start / text_len if text_len > 0 else 0.0
            position_end = match_end / text_len if text_len > 0 else 1.0

            detections.append({
                "word": pattern_info["word"],
                "matched": match,  # The actual text that was matched
                "display": pattern_info["display"],
                "replacement": get_replacement(match),  # Silly replacement
                "category": pattern_info["category"],
                "severity": pattern_info["severity"],
                "confidence": 0.95 if not pattern_info["context_required"] else 0.75,
                "position_start": position_start,  # 0.0 to 1.0 within subtitle
                "position_end": position_end,      # 0.0 to 1.0 within subtitle
                "char_start": match_start,         # Character position
                "char_end": match_end
            })

    return detections


def reload_wordlist():
    """Reload word list (for dynamic updates)"""
    global _wordlist, _patterns
    _wordlist = None
    _patterns = None


def get_all_profanity_words() -> list:
    """
    Get a flat list of all profanity words for Whisper matching.
    Returns the base words and common variations.
    """
    wordlist = load_wordlist()
    words = set()

    for word_entry in wordlist.get("words", []):
        base_word = word_entry.get("word", "").lower()
        if base_word:
            words.add(base_word)

        # Add variations
        for variant in word_entry.get("variations", []):
            words.add(variant.lower())

    # Add common phonetic variations not in wordlist
    extra_variations = [
        # F-word variations
        "fuck", "fucking", "fuckin", "fucked", "fucker", "fucks",
        "motherfuck", "motherfucker", "motherfucking", "motherfuckin",
        # S-word variations
        "shit", "shitting", "shittin", "shitty", "bullshit",
        # B-word variations
        "bitch", "bitches", "bitching", "bitchin",
        # A-word variations
        "ass", "asshole", "asses", "dumbass", "badass", "jackass",
        # D-word variations
        "damn", "damned", "dammit", "goddamn", "goddammit",
        # H-word variations
        "hell", "hellhole",
        # C-word variations
        "crap", "crappy",
        # Other common profanity
        "piss", "pissed", "cunt", "dick", "cock", "bastard",
        "whore", "slut", "douche", "douchebag"
    ]

    for word in extra_variations:
        words.add(word)

    return list(words)
