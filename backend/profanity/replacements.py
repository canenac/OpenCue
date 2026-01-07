"""
OpenCue - Syllable-Matched Replacement Library

Pre-computed replacements that match syllable counts for natural flow.
No AI needed - all replacements are deterministic.
"""

# Syllable count for common profanity words and their replacements
# Format: word -> (syllables, [replacement options with same syllable count])

SYLLABLE_REPLACEMENTS = {
    # 1-syllable words
    "ass": (1, ["butt", "rear", "tush", "rump"]),
    "damn": (1, ["dang", "darn", "shoot", "rats"]),
    "hell": (1, ["heck", "flip"]),
    "shit": (1, ["crap", "crud", "shoot", "drat"]),
    "fuck": (1, ["fudge", "flip", "frick", "frig"]),
    "dick": (1, ["jerk", "dork", "fool"]),
    "cock": (1, ["jerk", "fool", "dork"]),
    "cunt": (1, ["jerk", "fool", "meanie"]),  # 2-syllable backup
    "slut": (1, ["jerk", "fool"]),
    "whore": (1, ["jerk", "fool"]),
    "bitch": (1, ["witch", "jerk"]),
    "piss": (1, ["ticked", "mad"]),
    "crap": (1, ["crud", "stuff", "junk"]),
    "tit": (1, ["chest"]),
    "tits": (1, ["chest"]),
    "balls": (1, ["guts", "nerves"]),
    "arse": (1, ["rear", "butt"]),
    "prick": (1, ["jerk", "fool"]),
    "twat": (1, ["fool", "jerk"]),
    "wank": (1, ["fool"]),

    # 2-syllable words
    "asshole": (2, ["jerkwad", "meanie", "butthead"]),
    "bastard": (2, ["meanie", "rascal", "scoundrel"]),  # scoundrel is 2
    "bullshit": (2, ["nonsense", "baloney", "hogwash", "rubbish"]),
    "dammit": (2, ["dang it", "darn it", "shoot it"]),
    "damnit": (2, ["dang it", "darn it"]),
    "goddamn": (2, ["gosh darn", "dog gone"]),
    "shitty": (2, ["crummy", "lousy", "crappy"]),
    "shittin": (2, ["fibbin", "messin"]),
    "shitting": (2, ["fibbing", "messing"]),
    "fucking": (2, ["freaking", "flipping", "fricking"]),
    "fuckin": (2, ["freakin", "flippin", "frickin"]),
    "fucker": (2, ["meanie", "stinker", "jerkwad"]),
    "fuckers": (2, ["meanies", "stinkers", "jerkwads"]),
    "fucked": (1, ["messed", "ruined"]),
    "bitchy": (2, ["grumpy", "cranky", "snippy"]),
    "bitchin": (2, ["awesome", "wicked"]),
    "idiot": (3, ["silly goose", "goofball"]),
    "idiots": (3, ["goofballs", "silly folks"]),
    "stupid": (2, ["silly", "goofy"]),
    "moron": (2, ["goofball", "silly"]),
    "screwed": (1, ["messed"]),
    "pissed": (1, ["ticked", "miffed"]),
    "horny": (2, ["frisky"]),
    "boobs": (1, ["chest"]),
    "booze": (1, ["drinks"]),
    "badass": (2, ["awesome", "cool cat"]),
    "jackass": (2, ["dummy", "foolish"]),
    "dumbass": (2, ["dummy", "silly"]),
    "dipshit": (2, ["dummy", "dimwit"]),
    "dickhead": (2, ["jerkwad", "meanie"]),
    "shithead": (2, ["numbskull", "dummy"]),

    # 3-syllable words
    "motherfucker": (4, ["son of a gun", "goodness gracious"]),  # 4 syllables
    "motherfucking": (4, ["flippin' heckin'", "gosh darn awful"]),  # 4 syllables
    "motherfuckin": (4, ["flippin' heckin'", "gosh darn"]),  # 3-4 syllables
    "goddammit": (3, ["gosh darn it", "oh my gosh"]),
    "sonofabitch": (4, ["son of a gun", "scoundrel there"]),
    "bullshitting": (3, ["fibbing here", "stretching it"]),
    "fucking hell": (3, ["oh my gosh", "goodness me"]),

    # Phrases and compounds
    "holy shit": (3, ["holy cow", "oh my gosh", "goodness me"]),
    "holy fuck": (3, ["holy cow", "oh my gosh"]),
    "what the fuck": (3, ["what the heck", "what on earth"]),
    "what the hell": (3, ["what the heck", "what on earth"]),
    "oh my god": (3, ["oh my gosh", "goodness me"]),
    "jesus christ": (4, ["goodness gracious", "oh my goodness"]),
    "for fucks sake": (3, ["for goodness sake", "for pity's sake"]),
    "go to hell": (3, ["go away now", "leave me be"]),
    "shut the fuck up": (4, ["be quiet please", "hush up now"]),
    "fuck off": (2, ["go away", "buzz off", "shove off"]),
    "piss off": (2, ["buzz off", "go away"]),
    "screw you": (2, ["forget you"]),
    "fuck you": (2, ["forget you", "screw this"]),

    # Religious/blasphemy (context-sensitive but have replacements ready)
    "god": (1, ["gosh"]),
    "jesus": (2, ["gee whiz", "goodness"]),
    "christ": (1, ["gosh", "geez"]),
}

# Additional silly/fun replacements by category
SILLY_REPLACEMENTS = {
    "hell": ["H-E-double-hockey-sticks", "heck", "the bad place"],
    "damn": ["dagnabbit", "gosh darn", "heckin"],
    "shit": ["shucks", "sugar", "shoot", "shinola"],
    "fuck": ["fudge", "frick", "frick-frack", "fluffernutter"],
    "ass": ["behind", "posterior", "bootie", "keister"],
    "bitch": ["witch", "beach", "mean person"],
    "bastard": ["scoundrel", "rascal", "rapscallion"],
    "crap": ["crud", "crumbs", "criminy"],
}

# Severity-based default replacements (fallback)
SEVERITY_DEFAULTS = {
    "mild": "darn",
    "moderate": "shoot",
    "strong": "fudge",
    "severe": "frick",
}


def count_syllables(word: str) -> int:
    """
    Estimate syllable count for a word.
    Uses a simple heuristic based on vowel groups.
    """
    word = word.lower().strip()
    if not word:
        return 0

    vowels = "aeiouy"
    count = 0
    prev_was_vowel = False

    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_was_vowel:
            count += 1
        prev_was_vowel = is_vowel

    # Adjust for silent e
    if word.endswith('e') and count > 1:
        count -= 1

    # Adjust for -le endings (like "bottle")
    if word.endswith('le') and len(word) > 2 and word[-3] not in vowels:
        count += 1

    return max(1, count)


def get_replacement(word: str, category: str = "", match_syllables: bool = True) -> str:
    """
    Get a replacement for a profanity word.

    Args:
        word: The profanity word to replace
        category: Category hint for severity
        match_syllables: If True (default), prioritize syllable-matched replacements

    Returns:
        A replacement word/phrase, syllable-matched when possible
    """
    word_lower = word.lower().strip()

    # Check direct match in syllable replacements (prioritized when match_syllables=True)
    if word_lower in SYLLABLE_REPLACEMENTS:
        syllables, replacements = SYLLABLE_REPLACEMENTS[word_lower]
        if match_syllables:
            return replacements[0]  # Return syllable-matched replacement
        elif word_lower in SILLY_REPLACEMENTS:
            return SILLY_REPLACEMENTS[word_lower][0]
        return replacements[0]

    # Fall back to silly replacements
    if word_lower in SILLY_REPLACEMENTS:
        return SILLY_REPLACEMENTS[word_lower][0]

    # Fallback: generate based on syllable count
    target_syllables = count_syllables(word)

    # Map syllable count to generic replacements
    syllable_fallbacks = {
        1: ["darn", "shoot", "crud", "drat"],
        2: ["dang it", "oh no", "criminy", "goodness"],
        3: ["oh my gosh", "goodness me", "dear me"],
        4: ["goodness gracious", "oh my goodness"],
    }

    fallback_list = syllable_fallbacks.get(target_syllables, syllable_fallbacks[2])
    return fallback_list[0]


def get_all_replacements(word: str) -> list:
    """Get all available replacements for a word."""
    word_lower = word.lower().strip()

    replacements = set()

    if word_lower in SYLLABLE_REPLACEMENTS:
        replacements.update(SYLLABLE_REPLACEMENTS[word_lower][1])

    if word_lower in SILLY_REPLACEMENTS:
        replacements.update(SILLY_REPLACEMENTS[word_lower])

    return list(replacements) if replacements else [get_replacement(word)]


def get_replacement_display(word: str) -> str:
    """Get a censored display version of the word (e.g., sh*t)."""
    if len(word) <= 2:
        return "*" * len(word)
    return word[0] + "*" * (len(word) - 2) + word[-1]
