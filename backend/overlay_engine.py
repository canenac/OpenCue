"""
OpenCue - Overlay Engine

Analyzes subtitle text and generates overlay commands.
Supports both rule-based and LLM-based contextual analysis.
"""

import uuid
from datetime import datetime
from typing import List, Dict, Any
from collections import deque

from profanity.detector import detect_profanity

# Try to import LLM context module
try:
    from llm.context import (
        should_filter_with_context,
        add_subtitle_to_window,
        check_ollama_available
    )
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("[OpenCue] LLM context module not available")

# Configuration
MUTE_PADDING_BEFORE_MS = 400  # Padding BEFORE word (accounts for processing latency + subtitle timing)
MUTE_PADDING_AFTER_MS = 150   # Padding AFTER word
MIN_MUTE_DURATION_MS = 400    # Minimum mute duration to avoid pops
USE_LLM_CONTEXT = True  # Enable LLM for context-aware filtering
LLM_MODEL = "llama3.2:3b"  # Model to use for context analysis

# Recent events buffer (for dashboard)
recent_events: deque = deque(maxlen=100)

# Track Ollama availability
_ollama_checked = False
_ollama_available = False


async def check_llm_status() -> bool:
    """Check if LLM is available for context analysis"""
    global _ollama_checked, _ollama_available

    if not LLM_AVAILABLE:
        return False

    if not _ollama_checked:
        _ollama_available = await check_ollama_available()
        _ollama_checked = True
        if _ollama_available:
            print("[OpenCue] Ollama LLM available for context analysis")
        else:
            print("[OpenCue] Ollama not available, using rule-based filtering only")

    return _ollama_available


async def process_subtitle(
    text: str,
    start_ms: int,
    end_ms: int,
    content_id: str
) -> List[Dict[str, Any]]:
    """
    Process subtitle text and return overlay commands if needed.

    Args:
        text: Subtitle text content
        start_ms: Start timestamp in milliseconds
        end_ms: End timestamp in milliseconds
        content_id: Content identifier

    Returns:
        List of overlay command dictionaries
    """
    overlay_commands = []

    if not text or not text.strip():
        return overlay_commands

    # Add to subtitle context window for LLM analysis
    if LLM_AVAILABLE:
        add_subtitle_to_window(text, start_ms, end_ms, content_id)

    # Detect profanity in text
    detections = detect_profanity(text)

    # Check LLM availability once
    llm_available = await check_llm_status() if USE_LLM_CONTEXT else False

    for detection in detections:
        should_filter = True
        confidence = detection["confidence"]
        context_info = None

        # For context-required words, use LLM analysis if available
        if LLM_AVAILABLE and USE_LLM_CONTEXT and "context_required" in str(detection):
            context_result = await should_filter_with_context(
                text=text,
                detected_word=detection["word"],
                category=detection["category"],
                content_id=content_id,
                use_llm=llm_available,
                model=LLM_MODEL
            )
            should_filter = context_result["should_filter"]
            confidence = context_result["confidence"]
            context_info = context_result.get("context_type")

            if not should_filter:
                print(f"[OpenCue] Skipped: {detection['display']} "
                      f"(context: {context_info}, confidence: {confidence:.2f})")
                continue

        # For blasphemy category, always check context
        if "blasphemy" in detection["category"] and LLM_AVAILABLE and USE_LLM_CONTEXT:
            context_result = await should_filter_with_context(
                text=text,
                detected_word=detection["word"],
                category=detection["category"],
                content_id=content_id,
                use_llm=llm_available,
                model=LLM_MODEL
            )
            should_filter = context_result["should_filter"]
            confidence = context_result["confidence"]
            context_info = context_result.get("context_type")

            if not should_filter:
                print(f"[OpenCue] Skipped: {detection['display']} "
                      f"(religious context, confidence: {confidence:.2f})")
                continue

        if not should_filter:
            continue

        # Generate unique cue ID
        cue_id = f"cue_{uuid.uuid4().hex[:8]}"

        # Calculate word-specific timing based on position within subtitle
        subtitle_duration = end_ms - start_ms
        position_start = detection.get("position_start", 0.0)
        position_end = detection.get("position_end", 1.0)

        # Estimate when the word is spoken based on its position in text
        # Add padding before and after for safety
        word_start = start_ms + int(subtitle_duration * position_start)
        word_end = start_ms + int(subtitle_duration * position_end)

        # Apply padding (more before to account for processing latency)
        overlay_start = max(0, word_start - MUTE_PADDING_BEFORE_MS)
        overlay_end = word_end + MUTE_PADDING_AFTER_MS

        # Ensure minimum duration to avoid audio pops
        if overlay_end - overlay_start < MIN_MUTE_DURATION_MS:
            # Center the minimum duration around the word
            center = (word_start + word_end) // 2
            overlay_start = max(0, center - MIN_MUTE_DURATION_MS // 2)
            overlay_end = center + MIN_MUTE_DURATION_MS // 2

        command = {
            "cue_id": cue_id,
            "action": "mute",
            "start_ms": overlay_start,
            "end_ms": overlay_end,
            "category": detection["category"],
            "confidence": confidence,
            "detected": detection["display"],
            "matched": detection.get("matched", detection["word"]),
            "replacement": detection.get("replacement", "****"),
            "content_id": content_id,
            "word_position": f"{position_start:.2f}-{position_end:.2f}",  # Debug info
            "subtitle_text": text  # Full subtitle for smart deduplication
        }

        if context_info:
            command["context_type"] = context_info

        overlay_commands.append(command)
        print(f"[OpenCue] Detected: {detection['display']} -> mute {overlay_start}-{overlay_end}ms "
              f"(word at {position_start:.0%}-{position_end:.0%} of subtitle, "
              f"matched='{command['matched']}', replacement='{command['replacement']}')")

    return overlay_commands


def record_event(command: Dict[str, Any]):
    """Record an overlay event for dashboard display"""
    event = {
        **command,
        "timestamp": datetime.now().isoformat()
    }
    recent_events.append(event)


def get_recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent overlay events"""
    events = list(recent_events)
    events.reverse()  # Most recent first
    return events[:limit]


def clear_events():
    """Clear event history"""
    recent_events.clear()


def set_llm_enabled(enabled: bool):
    """Enable or disable LLM context analysis"""
    global USE_LLM_CONTEXT
    USE_LLM_CONTEXT = enabled
    print(f"[OpenCue] LLM context analysis: {'enabled' if enabled else 'disabled'}")


def set_llm_model(model: str):
    """Set the LLM model to use"""
    global LLM_MODEL
    LLM_MODEL = model
    print(f"[OpenCue] LLM model set to: {model}")
