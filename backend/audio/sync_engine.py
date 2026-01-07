"""
OpenCue - Audio Sync Engine

Coordinates audio capture, fingerprint matching, and cue triggering.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass
from enum import Enum

from .capture import AudioCapture, AudioConfig, CaptureMode, create_audio_capture
from .fingerprint import FingerprintMarker, ContentMatcher, CHROMAPRINT_AVAILABLE


class SyncState(Enum):
    IDLE = "idle"
    SYNCING = "syncing"
    SYNCED = "synced"
    LOST = "lost"


@dataclass
class Cue:
    """A content cue (mute, blur, etc.)"""
    id: str
    start_ms: int
    end_ms: int
    action: str
    category: str
    word: Optional[str] = None
    region: Optional[Dict] = None
    confidence: float = 1.0
    triggered: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> 'Cue':
        return cls(
            id=data["id"],
            start_ms=data["start_ms"],
            end_ms=data["end_ms"],
            action=data["action"],
            category=data["category"],
            word=data.get("word"),
            region=data.get("region"),
            confidence=data.get("confidence", 1.0)
        )


class OpenCueFile:
    """Parsed .opencue file"""

    def __init__(self, data: dict):
        self.version = data.get("version", "1.0")
        self.content = data.get("content", {})
        self.title = self.content.get("title", "Unknown")
        self.duration_ms = self.content.get("duration_ms", 0)

        # Parse fingerprint markers
        fp_data = data.get("fingerprints", {})
        self.fp_algorithm = fp_data.get("algorithm", "chromaprint")
        self.fp_interval_ms = fp_data.get("interval_ms", 5000)
        self.markers = [
            FingerprintMarker.from_dict(m) for m in fp_data.get("markers", [])
        ]

        # Parse cues
        self.cues = [Cue.from_dict(c) for c in data.get("cues", [])]

        self.metadata = data.get("metadata", {})

    @classmethod
    def load(cls, path: Path) -> 'OpenCueFile':
        """Load from file"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(data)

    def save(self, path: Path):
        """Save to file"""
        data = {
            "version": self.version,
            "content": self.content,
            "fingerprints": {
                "algorithm": self.fp_algorithm,
                "interval_ms": self.fp_interval_ms,
                "markers": [m.to_dict() for m in self.markers]
            },
            "cues": [
                {
                    "id": c.id,
                    "start_ms": c.start_ms,
                    "end_ms": c.end_ms,
                    "action": c.action,
                    "category": c.category,
                    "word": c.word,
                    "region": c.region,
                    "confidence": c.confidence
                }
                for c in self.cues
            ],
            "metadata": self.metadata
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)


class SyncEngine:
    """
    Main sync engine that coordinates:
    - Audio capture (system or mic)
    - Fingerprint matching
    - Cue triggering
    """

    def __init__(
        self,
        cue_file: OpenCueFile,
        capture_mode: str = "auto",
        on_cue: Optional[Callable[[Cue, str], None]] = None,
        on_state_change: Optional[Callable[[SyncState, Dict], None]] = None
    ):
        self.cue_file = cue_file
        self.on_cue = on_cue
        self.on_state_change = on_state_change

        # Audio capture
        self.capture = create_audio_capture(capture_mode)

        # Content matcher
        self.matcher = ContentMatcher(
            cue_file.markers,
            sample_rate=self.capture.config.sample_rate
        ) if cue_file.markers else None

        # State
        self.state = SyncState.IDLE
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Cue tracking
        self._active_cues: Dict[str, Cue] = {}  # Currently active cues
        self._triggered_cues: set = set()  # Cues already triggered this session

        # Timing
        self._start_time_ms: Optional[int] = None

    async def start(self):
        """Start the sync engine"""
        if self._running:
            return

        if not self.matcher:
            print("[OpenCue] No fingerprint markers - running in timestamp-only mode")

        # Start audio capture
        if self.matcher and not self.capture.start():
            print("[OpenCue] Warning: Audio capture failed, sync unavailable")

        self._running = True
        self._start_time_ms = int(time.time() * 1000)
        self._triggered_cues.clear()

        # Reset all cue triggered states
        for cue in self.cue_file.cues:
            cue.triggered = False

        self._set_state(SyncState.SYNCING)

        # Start main loop
        self._task = asyncio.create_task(self._main_loop())
        print(f"[OpenCue] Sync engine started for: {self.cue_file.title}")

    async def stop(self):
        """Stop the sync engine"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self.capture.stop()
        if self.matcher:
            self.matcher.reset()

        # End any active cues
        for cue_id, cue in list(self._active_cues.items()):
            self._end_cue(cue)

        self._set_state(SyncState.IDLE)
        print("[OpenCue] Sync engine stopped")

    async def _main_loop(self):
        """Main processing loop"""
        while self._running:
            try:
                wall_time_ms = int(time.time() * 1000)

                # Process audio for sync (if available)
                if self.matcher and self.capture.is_running:
                    chunk = self.capture.get_audio_chunk(timeout=0.1)
                    if chunk is not None:
                        result = self.matcher.add_audio(chunk, wall_time_ms)
                        if result:
                            self._handle_sync_result(result)

                # Get current content time
                content_time_ms = self._get_content_time(wall_time_ms)

                if content_time_ms is not None:
                    # Check and trigger cues
                    self._process_cues(content_time_ms)

                await asyncio.sleep(0.05)  # 50ms loop

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[OpenCue] Sync loop error: {e}")
                await asyncio.sleep(0.5)

    def _handle_sync_result(self, result: Dict):
        """Handle sync match result"""
        if result.get("synced"):
            if self.state != SyncState.SYNCED:
                self._set_state(SyncState.SYNCED, {
                    "content_time_ms": result.get("content_time_ms"),
                    "confidence": result.get("confidence")
                })
        elif result.get("status") == "lost":
            if self.state != SyncState.LOST:
                self._set_state(SyncState.LOST)

    def _get_content_time(self, wall_time_ms: int) -> Optional[int]:
        """Get current content time"""
        if self.matcher and self.matcher.is_synced:
            return self.matcher.get_content_time(wall_time_ms)

        # Fallback: assume content started when engine started
        if self._start_time_ms:
            return wall_time_ms - self._start_time_ms

        return None

    def _process_cues(self, content_time_ms: int):
        """Check and trigger cues based on content time"""
        # Look ahead slightly for cue triggering
        lookahead_ms = 100

        for cue in self.cue_file.cues:
            cue_id = cue.id

            # Check if cue should start
            if (not cue.triggered and
                cue.start_ms <= content_time_ms + lookahead_ms and
                content_time_ms < cue.end_ms):

                self._start_cue(cue)

            # Check if cue should end
            elif cue_id in self._active_cues and content_time_ms >= cue.end_ms:
                self._end_cue(cue)

    def _start_cue(self, cue: Cue):
        """Trigger a cue start"""
        cue.triggered = True
        self._active_cues[cue.id] = cue
        self._triggered_cues.add(cue.id)

        print(f"[OpenCue] CUE START: {cue.action} '{cue.word or cue.category}' "
              f"({cue.start_ms}-{cue.end_ms}ms)")

        if self.on_cue:
            self.on_cue(cue, "start")

    def _end_cue(self, cue: Cue):
        """Trigger a cue end"""
        if cue.id in self._active_cues:
            del self._active_cues[cue.id]

            print(f"[OpenCue] CUE END: {cue.action} '{cue.word or cue.category}'")

            if self.on_cue:
                self.on_cue(cue, "end")

    def _set_state(self, new_state: SyncState, info: Optional[Dict] = None):
        """Update sync state"""
        old_state = self.state
        self.state = new_state

        if old_state != new_state:
            print(f"[OpenCue] Sync state: {old_state.value} -> {new_state.value}")
            if self.on_state_change:
                self.on_state_change(new_state, info or {})

    def seek(self, content_time_ms: int):
        """Handle seek - reset cue states appropriately"""
        # Reset cues that are after the seek point
        for cue in self.cue_file.cues:
            if cue.start_ms > content_time_ms:
                cue.triggered = False
                self._triggered_cues.discard(cue.id)

        # End any active cues
        for cue_id, cue in list(self._active_cues.items()):
            if cue.end_ms <= content_time_ms or cue.start_ms > content_time_ms:
                self._end_cue(cue)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_synced(self) -> bool:
        return self.state == SyncState.SYNCED

    @property
    def active_capture_mode(self) -> Optional[str]:
        if self.capture.active_mode:
            return self.capture.active_mode.value
        return None


# Convenience function to load and create engine
def create_sync_engine(
    cue_file_path: str,
    capture_mode: str = "auto",
    on_cue: Optional[Callable] = None,
    on_state_change: Optional[Callable] = None
) -> SyncEngine:
    """Create a sync engine from a cue file path"""
    cue_file = OpenCueFile.load(Path(cue_file_path))
    return SyncEngine(
        cue_file=cue_file,
        capture_mode=capture_mode,
        on_cue=on_cue,
        on_state_change=on_state_change
    )
