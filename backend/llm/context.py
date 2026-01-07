"""
OpenCue - LLM Context Analysis

Uses Ollama for contextual analysis of subtitle text to reduce false positives
and improve detection accuracy.
"""

import json
import asyncio
from typing import Optional, Dict, Any, List
from collections import deque
from datetime import datetime

# Try to import httpx for async HTTP requests to Ollama
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    print("[OpenCue] Warning: httpx not installed, LLM features disabled")

# Configuration
OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"  # Fast, good for context analysis
CONTEXT_TIMEOUT = 5.0  # Max seconds to wait for LLM response

# Subtitle context window (stores recent subtitles for context)
subtitle_window: deque = deque(maxlen=10)  # Last 10 subtitles


class SubtitleContext:
    """Stores subtitle with timestamp for context windowing"""
    def __init__(self, text: str, start_ms: int, end_ms: int, content_id: str):
        self.text = text
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.content_id = content_id
        self.timestamp = datetime.now()


def add_subtitle_to_window(text: str, start_ms: int, end_ms: int, content_id: str):
    """Add subtitle to the context window"""
    subtitle_window.append(SubtitleContext(text, start_ms, end_ms, content_id))


def get_context_text(current_content_id: str, window_seconds: float = 5.0) -> str:
    """Get recent subtitle text for context (within time window)"""
    context_parts = []
    now = datetime.now()

    for sub in subtitle_window:
        # Only include subtitles from the same content
        if sub.content_id != current_content_id:
            continue

        # Only include recent subtitles (within window)
        age = (now - sub.timestamp).total_seconds()
        if age <= window_seconds:
            context_parts.append(sub.text)

    return " ".join(context_parts)


def clear_window():
    """Clear the subtitle window"""
    subtitle_window.clear()


async def check_ollama_available() -> bool:
    """Check if Ollama is running and accessible"""
    if not HTTPX_AVAILABLE:
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{OLLAMA_BASE_URL}/api/tags",
                timeout=2.0
            )
            return response.status_code == 200
    except Exception:
        return False


async def get_available_models() -> List[str]:
    """Get list of available Ollama models"""
    if not HTTPX_AVAILABLE:
        return []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{OLLAMA_BASE_URL}/api/tags",
                timeout=5.0
            )
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass

    return []


async def analyze_context(
    text: str,
    detected_word: str,
    category: str,
    context_text: str = "",
    model: str = DEFAULT_MODEL
) -> Dict[str, Any]:
    """
    Use LLM to analyze if detected word should be filtered based on context.

    Returns:
        {
            "should_filter": bool,
            "confidence": float (0-1),
            "reason": str,
            "context_type": str (e.g., "exclamation", "religious", "literal")
        }
    """
    if not HTTPX_AVAILABLE:
        return {
            "should_filter": True,
            "confidence": 0.5,
            "reason": "LLM not available, defaulting to filter",
            "context_type": "unknown"
        }

    # Build the prompt
    prompt = f"""You are a family content filter. Decide if this word should be MUTED (audio silenced) for family viewing.

WORD DETECTED: "{detected_word}"
CATEGORY: {category}
FULL SENTENCE: "{text}"
CONTEXT: "{context_text}"

MUTE RULES (should_filter = true):
- Profanity/swearing/cursing = MUTE (true)
- Religious words as exclamations ("Oh my God!", "Jesus Christ!") = MUTE (true)

DO NOT MUTE RULES (should_filter = false):
- Religious words in prayer/worship/scripture = DO NOT MUTE (false)
- Proper nouns or character names = DO NOT MUTE (false)
- Medical/educational context = DO NOT MUTE (false)

Output ONLY valid JSON:
{{"should_filter": true, "confidence": 0.95, "reason": "profanity as curse word", "context_type": "profanity"}}

or

{{"should_filter": false, "confidence": 0.9, "reason": "religious/reverent context", "context_type": "religious"}}"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # Low temperature for consistent results
                        "num_predict": 150   # Limit response length
                    }
                },
                timeout=CONTEXT_TIMEOUT
            )

            if response.status_code == 200:
                data = response.json()
                response_text = data.get("response", "")

                # Parse JSON from response
                try:
                    # Find JSON in response
                    start = response_text.find("{")
                    end = response_text.rfind("}") + 1
                    if start >= 0 and end > start:
                        result = json.loads(response_text[start:end])
                        return {
                            "should_filter": result.get("should_filter", True),
                            "confidence": float(result.get("confidence", 0.75)),
                            "reason": result.get("reason", "LLM analysis"),
                            "context_type": result.get("context_type", "unknown")
                        }
                except json.JSONDecodeError:
                    pass

                # Fallback: check for keywords in response
                response_lower = response_text.lower()
                should_filter = "should_filter\": true" in response_lower or "mute" in response_lower

                return {
                    "should_filter": should_filter,
                    "confidence": 0.6,
                    "reason": "Parsed from LLM response",
                    "context_type": "unknown"
                }

    except asyncio.TimeoutError:
        print(f"[OpenCue] LLM timeout for: {detected_word}")
    except Exception as e:
        print(f"[OpenCue] LLM error: {e}")

    # Default to filtering if LLM fails
    return {
        "should_filter": True,
        "confidence": 0.5,
        "reason": "LLM unavailable, defaulting to filter",
        "context_type": "unknown"
    }


async def should_filter_with_context(
    text: str,
    detected_word: str,
    category: str,
    content_id: str,
    use_llm: bool = True,
    model: str = DEFAULT_MODEL
) -> Dict[str, Any]:
    """
    Main entry point for context-aware filtering.

    Combines rule-based checks with optional LLM analysis.
    """
    # Add current subtitle to context window
    # (timestamp not critical here, we use it for context building)

    # Get surrounding context
    context_text = get_context_text(content_id)

    # Quick rule-based checks first (fast path)

    # 1. Check for proper nouns / titles
    # If the word appears with capital in middle of sentence, might be name

    # 2. Check for clear exclamatory patterns
    exclamatory_patterns = [
        "oh god", "my god", "oh my god", "omg",
        "jesus christ", "jesus!", "christ!",
        "god damn", "goddamn", "god damn it"
    ]
    text_lower = text.lower()
    is_exclamation = any(p in text_lower for p in exclamatory_patterns)

    # For context_required words (like "god", "jesus"), use LLM if not clear exclamation
    if "blasphemy" in category and not is_exclamation and use_llm:
        # Check if Ollama is available
        if await check_ollama_available():
            result = await analyze_context(
                text=text,
                detected_word=detected_word,
                category=category,
                context_text=context_text,
                model=model
            )
            return result

    # For clear profanity, always filter
    if "profanity.severe" in category:
        return {
            "should_filter": True,
            "confidence": 0.95,
            "reason": "Severe profanity detected",
            "context_type": "profanity"
        }

    # For moderate profanity, filter with high confidence
    if "profanity.moderate" in category:
        return {
            "should_filter": True,
            "confidence": 0.90,
            "reason": "Moderate profanity detected",
            "context_type": "profanity"
        }

    # For exclamatory blasphemy, filter
    if is_exclamation:
        return {
            "should_filter": True,
            "confidence": 0.85,
            "reason": "Exclamatory use detected",
            "context_type": "exclamation"
        }

    # Default for other categories
    return {
        "should_filter": True,
        "confidence": 0.75,
        "reason": "Default filter policy",
        "context_type": "unknown"
    }
