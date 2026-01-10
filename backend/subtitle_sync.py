"""
OpenCue - Subtitle-Based Sync Engine

Simple 3-step sync approach:
1. Timestamp gives rough position (±30 seconds)
2. Subtitle text matching narrows to exact position
3. Continuous verification maintains sync

No complex audio fingerprinting - just text matching.
"""

from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime
import re


@dataclass
class SyncResult:
    """Result of a sync attempt"""
    synced: bool
    offset_ms: int = 0  # Add this to video time to get cue file time
    confidence: float = 0.0
    matched_subtitle: str = ""
    method: str = ""  # "subtitle", "timestamp", "verified"


class SubtitleSyncEngine:
    """
    Syncs playback to cue file using subtitle text matching.

    The key insight: subtitle text is the same across all streaming platforms,
    even if timing differs. Match the text to find exact position.
    """

    def __init__(self, cue_data: dict):
        self.cue_data = cue_data
        self.cues = cue_data.get("cues", [])
        self.subtitles = cue_data.get("subtitles", [])  # For sync

        # Sync state
        self.synced = False
        self.offset_ms = 0
        self.confidence = 0.0
        self.last_match_time = None
        self.match_history: List[int] = []  # Recent offset values

        # Settings
        self.search_window_ms = 120000  # ±120 seconds search window (wider for different start points)
        self.min_subtitle_length = 8  # Reduced to catch more subtitles
        self.required_matches = 1  # Reduced to 1 for faster initial sync (verify with subsequent matches)

        print(f"[SubtitleSync] Initialized with {len(self.cues)} cues, {len(self.subtitles)} subtitle markers")

    def process_subtitle(self, text: str, video_time_ms: int) -> SyncResult:
        """
        Process incoming subtitle and attempt to sync.

        Args:
            text: Current subtitle text on screen
            video_time_ms: Current video playback position

        Returns:
            SyncResult with sync status and offset
        """
        if not text or len(text) < self.min_subtitle_length:
            return SyncResult(synced=self.synced, offset_ms=self.offset_ms,
                            confidence=self.confidence, method="skipped")

        # Normalize text for matching
        normalized = self._normalize_text(text)

        # Search for this subtitle in cue file
        match = self._find_subtitle_match(normalized, video_time_ms)

        if match:
            cue_time_ms, matched_text, score = match
            new_offset = cue_time_ms - video_time_ms

            # Add to match history
            self.match_history.append(new_offset)
            if len(self.match_history) > 10:
                self.match_history.pop(0)

            # Check if offset is consistent
            if self._is_offset_consistent(new_offset):
                self.synced = True
                self.offset_ms = self._calculate_stable_offset()
                self.confidence = min(0.95, 0.5 + (len(self.match_history) * 0.1))
                self.last_match_time = datetime.now()

                return SyncResult(
                    synced=True,
                    offset_ms=self.offset_ms,
                    confidence=self.confidence,
                    matched_subtitle=matched_text[:50],
                    method="subtitle_match"
                )
            else:
                # Single match, not yet confirmed
                return SyncResult(
                    synced=False,
                    offset_ms=new_offset,
                    confidence=0.3,
                    matched_subtitle=matched_text[:50],
                    method="pending_confirmation"
                )

        # No match found
        if self.synced and self.last_match_time:
            # Check if we've lost sync (no match for too long)
            time_since_match = (datetime.now() - self.last_match_time).total_seconds()
            if time_since_match > 30:
                self.confidence = max(0.3, self.confidence - 0.1)

        return SyncResult(
            synced=self.synced,
            offset_ms=self.offset_ms,
            confidence=self.confidence,
            method="no_match"
        )

    def _normalize_text(self, text: str) -> str:
        """Normalize subtitle text for matching"""
        # Lowercase
        text = text.lower()
        # Remove punctuation except apostrophes
        text = re.sub(r"[^\w\s']", "", text)
        # Normalize whitespace
        text = " ".join(text.split())
        return text

    def _find_subtitle_match(self, normalized_text: str, video_time_ms: int) -> Optional[Tuple[int, str, float]]:
        """
        Find matching subtitle in cue file within search window.

        Returns: (cue_time_ms, matched_text, similarity_score) or None
        """
        best_match = None
        best_score = 0.0

        # Calculate search window based on current estimate
        if self.synced:
            # If already synced, narrow the window
            estimated_cue_time = video_time_ms + self.offset_ms
            window_start = estimated_cue_time - 10000  # ±10 seconds
            window_end = estimated_cue_time + 10000
        else:
            # Not synced - use wide window
            window_start = max(0, video_time_ms - self.search_window_ms)
            window_end = video_time_ms + self.search_window_ms

        # Search in subtitle markers (if available)
        for sub in self.subtitles:
            sub_time = sub.get("time_ms", 0)
            if window_start <= sub_time <= window_end:
                sub_text = self._normalize_text(sub.get("text", ""))
                score = self._text_similarity(normalized_text, sub_text)
                if score > best_score and score > 0.6:  # 60% similarity threshold
                    best_score = score
                    best_match = (sub_time, sub.get("text", ""), score)

        # Also search in cue words (less reliable but backup)
        if not best_match:
            for cue in self.cues:
                cue_time = cue.get("start_ms", 0)
                if window_start <= cue_time <= window_end:
                    cue_word = cue.get("word", "").lower()
                    if cue_word and cue_word in normalized_text:
                        # Found the profanity word in current subtitle
                        score = 0.7  # Good but not perfect match
                        if not best_match or score > best_score:
                            best_score = score
                            best_match = (cue_time, cue_word, score)

        return best_match

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts (0-1)"""
        if not text1 or not text2:
            return 0.0

        # Simple word overlap similarity
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)

    def _is_offset_consistent(self, new_offset: int) -> bool:
        """Check if new offset is consistent with recent history"""
        if len(self.match_history) < self.required_matches:
            return False

        # Check if recent offsets are within 2 seconds of each other
        recent = self.match_history[-self.required_matches:]
        avg = sum(recent) / len(recent)

        for offset in recent:
            if abs(offset - avg) > 2000:  # 2 second tolerance
                return False

        return True

    def _calculate_stable_offset(self) -> int:
        """Calculate stable offset from recent matches"""
        if not self.match_history:
            return 0

        # Use median of recent matches for stability
        sorted_offsets = sorted(self.match_history[-5:])
        mid = len(sorted_offsets) // 2
        return sorted_offsets[mid]

    def get_cue_time(self, video_time_ms: int) -> int:
        """Convert video time to cue file time"""
        return video_time_ms + self.offset_ms

    def get_video_time(self, cue_time_ms: int) -> int:
        """Convert cue file time to video time"""
        return cue_time_ms - self.offset_ms

    def get_upcoming_cues(self, video_time_ms: int, lookahead_ms: int = 5000) -> List[dict]:
        """Get cues that should trigger soon"""
        if not self.synced:
            return []

        cue_time = self.get_cue_time(video_time_ms)
        upcoming = []

        for cue in self.cues:
            cue_start = cue.get("start_ms", 0)
            if cue_time <= cue_start <= cue_time + lookahead_ms:
                # Adjust times back to video time
                adjusted_cue = cue.copy()
                adjusted_cue["video_start_ms"] = self.get_video_time(cue_start)
                adjusted_cue["video_end_ms"] = self.get_video_time(cue.get("end_ms", cue_start + 3000))
                upcoming.append(adjusted_cue)

        return upcoming

    def reset(self):
        """Reset sync state"""
        self.synced = False
        self.offset_ms = 0
        self.confidence = 0.0
        self.last_match_time = None
        self.match_history.clear()


# Convenience function
def create_subtitle_sync(cue_data: dict) -> SubtitleSyncEngine:
    """Create a subtitle sync engine for the given cue data"""
    return SubtitleSyncEngine(cue_data)
