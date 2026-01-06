"""
OpenCue - Overlay Engine

Analyzes subtitle text and generates overlay commands.
"""

import re
import uuid
from datetime import datetime
from typing import List, Dict, Any
from collections import deque

from profanity.detector import detect_profanity

# Configuration
MUTE_PADDING_MS = 300  # Padding before/after detected word

# Recent events buffer (for dashboard)
recent_events: deque = deque(maxlen=100)


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

    # Detect profanity in text
    detections = detect_profanity(text)

    for detection in detections:
        # Generate unique cue ID
        cue_id = f"cue_{uuid.uuid4().hex[:8]}"

        # Calculate overlay timing with padding
        overlay_start = max(0, start_ms - MUTE_PADDING_MS)
        overlay_end = end_ms + MUTE_PADDING_MS

        command = {
            "cue_id": cue_id,
            "action": "mute",
            "start_ms": overlay_start,
            "end_ms": overlay_end,
            "category": detection["category"],
            "confidence": detection["confidence"],
            "detected": detection["display"],
            "content_id": content_id
        }

        overlay_commands.append(command)
        print(f"[OpenCue] Detected: {detection['display']} -> mute {overlay_start}-{overlay_end}ms")

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
