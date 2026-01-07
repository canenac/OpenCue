"""
OpenCue - Sync Session Manager

Manages sync sessions for connected browser extensions.
Each session can operate in:
1. Real-time mode: Detect profanity from live subtitles
2. Cue-file mode: Use pre-analyzed .opencue files with audio sync
"""

import asyncio
import threading
from typing import Optional, Dict, Callable, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import time

from websockets.server import WebSocketServerProtocol

from cue_manager import get_cue_manager

# Try to import audio fingerprinting (optional)
try:
    from audio.capture import create_audio_capture
    from audio.fingerprint import Fingerprinter, CHROMAPRINT_AVAILABLE
    AUDIO_FINGERPRINTING_AVAILABLE = CHROMAPRINT_AVAILABLE
except ImportError as e:
    AUDIO_FINGERPRINTING_AVAILABLE = False
    print(f"[OpenCue] Audio fingerprinting not available: {e}")


class SessionMode(Enum):
    REALTIME = "realtime"      # Live subtitle detection
    CUE_FILE = "cue_file"      # Pre-analyzed cue file
    HYBRID = "hybrid"          # Cue file with realtime fallback
    RECORDING = "recording"    # Record detections to create .opencue file


@dataclass
class SyncSession:
    """A sync session for a connected client"""
    websocket: WebSocketServerProtocol
    session_id: str
    mode: SessionMode = SessionMode.REALTIME
    content_id: Optional[str] = None
    cue_file_id: Optional[str] = None

    # Sync state
    synced: bool = False
    sync_offset_ms: int = 0
    last_position_ms: int = 0

    # Cue tracking
    triggered_cues: set = field(default_factory=set)
    active_cues: Dict[str, dict] = field(default_factory=dict)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    # Audio sync engine (if using cue file mode)
    sync_engine: Any = None

    # Recording mode state
    recording: bool = False
    recording_start_time: Optional[datetime] = None
    recording_start_position_ms: int = 0
    recorded_cues: list = field(default_factory=list)
    recording_title: str = ""

    # Audio fingerprint capture during recording
    recording_audio_capture: Any = None
    recording_fingerprinter: Any = None
    recorded_fingerprints: list = field(default_factory=list)
    fingerprint_capture_task: Any = None
    fingerprint_interval_ms: int = 5000  # Capture fingerprint every 5 seconds


class SessionManager:
    """Manages all active sync sessions"""

    def __init__(self):
        self.sessions: Dict[str, SyncSession] = {}
        self._session_counter = 0
        self._cue_data_cache: Dict[str, dict] = {}

    def create_session(self, websocket: WebSocketServerProtocol) -> SyncSession:
        """Create a new session for a websocket connection"""
        self._session_counter += 1
        session_id = f"session_{self._session_counter}"

        session = SyncSession(
            websocket=websocket,
            session_id=session_id
        )

        self.sessions[session_id] = session
        print(f"[OpenCue] Session created: {session_id}")
        return session

    def get_session_by_websocket(self, websocket: WebSocketServerProtocol) -> Optional[SyncSession]:
        """Find session by websocket"""
        for session in self.sessions.values():
            if session.websocket == websocket:
                return session
        return None

    def remove_session(self, session: SyncSession):
        """Remove a session"""
        if session.session_id in self.sessions:
            # Stop sync engine if running
            if session.sync_engine:
                asyncio.create_task(self._stop_sync_engine(session))

            del self.sessions[session.session_id]
            print(f"[OpenCue] Session removed: {session.session_id}")

    async def _stop_sync_engine(self, session: SyncSession):
        """Stop sync engine for session"""
        if session.sync_engine:
            try:
                await session.sync_engine.stop()
            except:
                pass
            session.sync_engine = None

    async def set_mode(self, session: SyncSession, mode: str, cue_file_id: Optional[str] = None) -> dict:
        """Set session mode"""
        try:
            session.mode = SessionMode(mode)
        except ValueError:
            return {"success": False, "error": f"Invalid mode: {mode}"}

        session.cue_file_id = cue_file_id

        # Load cue file if specified
        if cue_file_id and session.mode in [SessionMode.CUE_FILE, SessionMode.HYBRID]:
            cue_data = self._load_cue_file(cue_file_id)
            if not cue_data:
                return {"success": False, "error": f"Cue file not found: {cue_file_id}"}

            session.triggered_cues.clear()
            session.active_cues.clear()

            # Try to start audio sync engine
            await self._start_sync_engine(session, cue_data)

        print(f"[OpenCue] Session {session.session_id} mode: {session.mode.value}, cue: {cue_file_id}")
        return {"success": True, "mode": session.mode.value}

    def _load_cue_file(self, cue_file_id: str) -> Optional[dict]:
        """Load cue file data"""
        if cue_file_id in self._cue_data_cache:
            return self._cue_data_cache[cue_file_id]

        manager = get_cue_manager()
        data = manager.load(cue_file_id)

        if data:
            self._cue_data_cache[cue_file_id] = data

        return data

    async def _start_sync_engine(self, session: SyncSession, cue_data: dict):
        """Start audio sync engine for session"""
        try:
            # Import here to avoid circular imports
            from audio.sync_engine import OpenCueFile, SyncEngine

            cue_file = OpenCueFile(cue_data)

            # Create cue callback
            async def on_cue(cue, event_type):
                await self._handle_cue_event(session, cue, event_type)

            def on_cue_sync(cue, event_type):
                asyncio.create_task(on_cue(cue, event_type))

            # Create state callback
            def on_state_change(state, info):
                session.synced = state.value == "synced"
                asyncio.create_task(self._send_sync_state(session, state.value, info))

            session.sync_engine = SyncEngine(
                cue_file=cue_file,
                capture_mode="auto",
                on_cue=on_cue_sync,
                on_state_change=on_state_change
            )

            await session.sync_engine.start()
            print(f"[OpenCue] Sync engine started for session {session.session_id}")

        except ImportError as e:
            print(f"[OpenCue] Audio sync not available: {e}")
            print("[OpenCue] Using timestamp-only mode")
        except Exception as e:
            print(f"[OpenCue] Failed to start sync engine: {e}")

    async def _handle_cue_event(self, session: SyncSession, cue, event_type: str):
        """Handle cue start/end events"""
        try:
            message = {
                "type": "cue",
                "payload": {
                    "event": event_type,
                    "cue_id": cue.id,
                    "action": cue.action,
                    "category": cue.category,
                    "start_ms": cue.start_ms,
                    "end_ms": cue.end_ms
                }
            }

            if cue.word:
                message["payload"]["word"] = cue.word
            if cue.region:
                message["payload"]["region"] = cue.region

            await session.websocket.send(json.dumps(message))

        except Exception as e:
            print(f"[OpenCue] Error sending cue event: {e}")

    async def _send_sync_state(self, session: SyncSession, state: str, info: dict):
        """Send sync state update to client"""
        try:
            import json
            message = {
                "type": "syncState",
                "payload": {
                    "state": state,
                    **info
                }
            }
            await session.websocket.send(json.dumps(message))
        except Exception as e:
            print(f"[OpenCue] Error sending sync state: {e}")

    def update_position(self, session: SyncSession, position_ms: int):
        """Update playback position (for timestamp-only mode)"""
        session.last_position_ms = position_ms
        session.last_activity = datetime.now()

        # Check cues if in cue file mode without audio sync
        if session.mode in [SessionMode.CUE_FILE, SessionMode.HYBRID]:
            if not session.sync_engine or not session.sync_engine.is_synced:
                asyncio.create_task(self._check_cues_by_position(session, position_ms))

    async def _check_cues_by_position(self, session: SyncSession, position_ms: int):
        """Check and trigger cues based on reported position"""
        if not session.cue_file_id:
            return

        cue_data = self._load_cue_file(session.cue_file_id)
        if not cue_data:
            return

        cues = cue_data.get("cues", [])
        lookahead_ms = 200  # Trigger slightly early

        for cue in cues:
            cue_id = cue["id"]
            start_ms = cue["start_ms"]
            end_ms = cue["end_ms"]

            # Check if cue should start
            if (cue_id not in session.triggered_cues and
                start_ms <= position_ms + lookahead_ms and
                position_ms < end_ms):

                session.triggered_cues.add(cue_id)
                session.active_cues[cue_id] = cue

                await self._send_cue_command(session, cue, "start")

            # Check if cue should end
            elif cue_id in session.active_cues and position_ms >= end_ms:
                del session.active_cues[cue_id]
                await self._send_cue_command(session, cue, "end")

    async def _send_cue_command(self, session: SyncSession, cue: dict, event: str):
        """Send cue command to client"""
        try:
            import json

            # Map to overlay command format for compatibility
            if event == "start":
                message = {
                    "type": "overlay",
                    "payload": {
                        "cue_id": cue["id"],
                        "action": cue["action"],
                        "start_ms": cue["start_ms"],
                        "end_ms": cue["end_ms"],
                        "category": cue.get("category", ""),
                        "matched": cue.get("word", ""),
                        "replacement": self._get_replacement(cue.get("word", "")),
                        "source": "cue_file"
                    },
                    "timestamp": int(time.time() * 1000)
                }
            else:
                message = {
                    "type": "cueEnd",
                    "payload": {
                        "cue_id": cue["id"]
                    }
                }

            await session.websocket.send(json.dumps(message))
            print(f"[OpenCue] Cue {event}: {cue.get('word', cue['action'])} ({cue['start_ms']}-{cue['end_ms']}ms)")

        except Exception as e:
            print(f"[OpenCue] Error sending cue command: {e}")

    def _get_replacement(self, word: str) -> str:
        """Get silly replacement for a word"""
        if not word:
            return "****"

        try:
            from profanity.detector import get_replacement
            return get_replacement(word)
        except:
            return word[0] + "*" * (len(word) - 1) if len(word) > 1 else "****"

    def handle_seek(self, session: SyncSession, position_ms: int):
        """Handle seek - reset cue states"""
        # Reset cues that are after seek position
        cues_to_reset = [
            cue_id for cue_id in session.triggered_cues
            if self._get_cue_start(session, cue_id) > position_ms
        ]

        for cue_id in cues_to_reset:
            session.triggered_cues.discard(cue_id)

        # End active cues that are no longer valid
        for cue_id in list(session.active_cues.keys()):
            cue = session.active_cues[cue_id]
            if cue["end_ms"] <= position_ms or cue["start_ms"] > position_ms:
                del session.active_cues[cue_id]

        # Notify sync engine
        if session.sync_engine:
            session.sync_engine.seek(position_ms)

        session.last_position_ms = position_ms

    def _get_cue_start(self, session: SyncSession, cue_id: str) -> int:
        """Get start time for a cue"""
        if not session.cue_file_id:
            return 0

        cue_data = self._load_cue_file(session.cue_file_id)
        if cue_data:
            for cue in cue_data.get("cues", []):
                if cue["id"] == cue_id:
                    return cue["start_ms"]
        return 0

    def get_stats(self) -> dict:
        """Get session statistics"""
        return {
            "total_sessions": len(self.sessions),
            "sessions": [
                {
                    "id": s.session_id,
                    "mode": s.mode.value,
                    "synced": s.synced,
                    "content_id": s.content_id,
                    "cue_file": s.cue_file_id,
                    "active_cues": len(s.active_cues),
                    "recording": s.recording,
                    "recorded_cues": len(s.recorded_cues) if s.recording else 0
                }
                for s in self.sessions.values()
            ]
        }

    def start_recording(self, session: SyncSession, title: str, content_id: str) -> dict:
        """Start recording mode for a session"""
        session.mode = SessionMode.RECORDING
        session.recording = True
        session.recording_start_time = datetime.now()
        session.recording_start_position_ms = session.last_position_ms
        session.recorded_cues = []
        session.recorded_fingerprints = []
        session.recording_title = title or f"Recording {session.session_id}"
        session.content_id = content_id

        # Start audio fingerprint capture if available
        fingerprinting_started = False
        if AUDIO_FINGERPRINTING_AVAILABLE:
            try:
                session.recording_audio_capture = create_audio_capture("auto")
                if session.recording_audio_capture.start():
                    from audio.fingerprint import Fingerprinter
                    session.recording_fingerprinter = Fingerprinter(sample_rate=22050)
                    # Start fingerprint capture task
                    session.fingerprint_capture_task = asyncio.create_task(
                        self._fingerprint_capture_loop(session)
                    )
                    fingerprinting_started = True
                    print(f"[OpenCue] Audio fingerprinting started for recording")
                else:
                    print(f"[OpenCue] Audio capture not available - recording without fingerprints")
            except Exception as e:
                print(f"[OpenCue] Could not start audio fingerprinting: {e}")
                session.recording_audio_capture = None
                session.recording_fingerprinter = None

        print(f"[OpenCue] Recording started for session {session.session_id}: {session.recording_title}")
        return {
            "success": True,
            "recording": True,
            "title": session.recording_title,
            "start_position_ms": session.recording_start_position_ms,
            "fingerprinting": fingerprinting_started
        }

    async def _fingerprint_capture_loop(self, session: SyncSession):
        """Background task to capture audio fingerprints during recording"""
        import numpy as np
        from audio.fingerprint import FingerprintMarker

        SAMPLE_RATE = 22050
        FINGERPRINT_DURATION_SEC = 5  # 5 seconds of audio per fingerprint
        CAPTURE_INTERVAL_SEC = 5  # Capture every 5 seconds

        audio_buffer = []
        buffer_duration_ms = 0
        last_fingerprint_time_ms = 0

        print(f"[OpenCue] Fingerprint capture loop started")

        try:
            while session.recording and session.recording_audio_capture:
                # Get audio chunk
                chunk = session.recording_audio_capture.get_audio_chunk(timeout=0.5)
                if chunk is not None:
                    audio_buffer.append(chunk)
                    chunk_duration_ms = int(len(chunk) / SAMPLE_RATE * 1000)
                    buffer_duration_ms += chunk_duration_ms

                    # Check if we have enough audio for a fingerprint
                    if buffer_duration_ms >= FINGERPRINT_DURATION_SEC * 1000:
                        # Combine buffer
                        combined = np.concatenate(audio_buffer)

                        # Calculate content timestamp for this fingerprint
                        content_time_ms = session.last_position_ms

                        # Only capture if enough time has passed since last fingerprint
                        if content_time_ms - last_fingerprint_time_ms >= CAPTURE_INTERVAL_SEC * 1000:
                            # Generate fingerprint
                            fp = session.recording_fingerprinter.fingerprint(combined)
                            if fp:
                                marker = FingerprintMarker(
                                    time_ms=content_time_ms,
                                    fingerprint=fp
                                )
                                session.recorded_fingerprints.append(marker)
                                last_fingerprint_time_ms = content_time_ms
                                print(f"[OpenCue] Captured fingerprint at {content_time_ms}ms "
                                      f"(total: {len(session.recorded_fingerprints)})")

                        # Clear buffer (keep some overlap for continuity)
                        keep_chunks = len(audio_buffer) // 4
                        audio_buffer = audio_buffer[-keep_chunks:] if keep_chunks > 0 else []
                        buffer_duration_ms = sum(int(len(c) / SAMPLE_RATE * 1000) for c in audio_buffer)

                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            print(f"[OpenCue] Fingerprint capture loop cancelled")
        except Exception as e:
            print(f"[OpenCue] Fingerprint capture error: {e}")

        print(f"[OpenCue] Fingerprint capture loop ended - {len(session.recorded_fingerprints)} markers captured")

    def _stop_fingerprint_capture(self, session: SyncSession):
        """Stop audio capture and fingerprinting for a session"""
        # Cancel capture task
        if session.fingerprint_capture_task:
            session.fingerprint_capture_task.cancel()
            session.fingerprint_capture_task = None

        # Stop audio capture
        if session.recording_audio_capture:
            session.recording_audio_capture.stop()
            session.recording_audio_capture = None

        session.recording_fingerprinter = None

    def stop_recording(self, session: SyncSession) -> dict:
        """Stop recording and return the recorded cues"""
        if not session.recording:
            return {"success": False, "error": "Not recording"}

        session.recording = False
        duration_ms = session.last_position_ms - session.recording_start_position_ms

        # Stop fingerprint capture
        self._stop_fingerprint_capture(session)

        # Convert fingerprint markers to dict format
        fingerprint_markers = []
        for marker in session.recorded_fingerprints:
            fingerprint_markers.append(marker.to_dict())

        # Build .opencue file data
        cue_data = {
            "version": "2.0",
            "content": {
                "title": session.recording_title,
                "duration_ms": duration_ms if duration_ms > 0 else session.last_position_ms,
                "content_id": session.content_id,
                "recorded_at": session.recording_start_time.isoformat() if session.recording_start_time else None
            },
            "fingerprints": {
                "algorithm": "chromaprint",
                "sample_rate": 22050,
                "markers": fingerprint_markers
            },
            "cues": session.recorded_cues,
            "metadata": {
                "created": datetime.now().isoformat(),
                "tool_version": "1.0.0",
                "source": "recording_mode",
                "fingerprint_count": len(fingerprint_markers)
            }
        }

        cue_count = len(session.recorded_cues)
        fingerprint_count = len(fingerprint_markers)
        print(f"[OpenCue] Recording stopped for session {session.session_id}: "
              f"{cue_count} cues, {fingerprint_count} fingerprints captured")

        # Reset recording state but keep cue_data for export
        session.mode = SessionMode.REALTIME
        session.recorded_fingerprints = []

        return {
            "success": True,
            "recording": False,
            "cue_count": cue_count,
            "fingerprint_count": fingerprint_count,
            "duration_ms": duration_ms,
            "cue_data": cue_data
        }

    def abort_recording(self, session: SyncSession) -> dict:
        """Abort recording and discard all captured cues"""
        if not session.recording:
            return {"success": False, "error": "Not recording"}

        cue_count = len(session.recorded_cues)
        fingerprint_count = len(session.recorded_fingerprints)
        print(f"[OpenCue] Recording ABORTED for session {session.session_id}: "
              f"{cue_count} cues, {fingerprint_count} fingerprints discarded")

        # Stop fingerprint capture
        self._stop_fingerprint_capture(session)

        # Reset all recording state
        session.recording = False
        session.mode = SessionMode.REALTIME
        session.recorded_cues = []
        session.recorded_fingerprints = []
        session.recording_title = ""
        session.recording_start_time = None

        return {
            "success": True,
            "aborted": True,
            "discarded_cues": cue_count,
            "discarded_fingerprints": fingerprint_count
        }

    def pause_recording(self, session: SyncSession) -> dict:
        """Pause recording (keep cues, can resume later)"""
        if not session.recording:
            return {"success": False, "error": "Not recording"}

        elapsed_ms = 0
        if session.recording_start_time:
            elapsed_ms = int((datetime.now() - session.recording_start_time).total_seconds() * 1000)

        cue_count = len(session.recorded_cues)
        fingerprint_count = len(session.recorded_fingerprints)
        position_ms = session.last_position_ms

        # Stop fingerprint capture (but keep captured fingerprints)
        if session.fingerprint_capture_task:
            session.fingerprint_capture_task.cancel()
            session.fingerprint_capture_task = None
        if session.recording_audio_capture:
            session.recording_audio_capture.stop()
            session.recording_audio_capture = None
        session.recording_fingerprinter = None

        print(f"[OpenCue] Recording PAUSED for session {session.session_id}: "
              f"{cue_count} cues, {fingerprint_count} fingerprints at {position_ms}ms")

        # Keep recording state but mark as paused
        session.recording = False  # Stop accepting new cues

        return {
            "success": True,
            "paused": True,
            "state": {
                "cue_count": cue_count,
                "fingerprint_count": fingerprint_count,
                "position_ms": position_ms,
                "elapsed_ms": elapsed_ms,
                "title": session.recording_title
            }
        }

    def resume_recording(self, session: SyncSession, position_ms: int = 0) -> dict:
        """Resume recording from a paused state"""
        # Check if we have existing cues (from pause)
        has_previous = len(session.recorded_cues) > 0

        session.recording = True
        session.mode = SessionMode.RECORDING

        if not has_previous:
            # Fresh start
            session.recording_start_time = datetime.now()
            session.recording_start_position_ms = position_ms
        # else keep existing start time and cues

        # Restart fingerprint capture if available
        fingerprinting_started = False
        if AUDIO_FINGERPRINTING_AVAILABLE:
            try:
                session.recording_audio_capture = create_audio_capture("auto")
                if session.recording_audio_capture.start():
                    from audio.fingerprint import Fingerprinter
                    session.recording_fingerprinter = Fingerprinter(sample_rate=22050)
                    session.fingerprint_capture_task = asyncio.create_task(
                        self._fingerprint_capture_loop(session)
                    )
                    fingerprinting_started = True
                    print(f"[OpenCue] Audio fingerprinting resumed")
            except Exception as e:
                print(f"[OpenCue] Could not restart audio fingerprinting: {e}")

        print(f"[OpenCue] Recording RESUMED for session {session.session_id} at {position_ms}ms "
              f"(existing cues: {len(session.recorded_cues)}, fingerprints: {len(session.recorded_fingerprints)})")

        return {
            "success": True,
            "resumed": True,
            "existing_cues": len(session.recorded_cues),
            "existing_fingerprints": len(session.recorded_fingerprints),
            "position_ms": position_ms,
            "fingerprinting": fingerprinting_started
        }

    def add_recorded_cue(self, session: SyncSession, cue: dict) -> bool:
        """Add a detected cue to the recording (with minimal deduplication)"""
        if not session.recording:
            return False

        word = cue.get("matched", cue.get("word", "")).lower()
        start_ms = cue.get("start_ms", 0)

        # Only skip if EXACT same word at EXACT same timestamp (within 100ms)
        # This handles Netflix sending same subtitle multiple times
        # but preserves intentional repetition like "Fuck you. Fuck you. Fuck you."
        DEDUP_WINDOW_MS = 100  # Very tight window - only catches true duplicates
        for existing in session.recorded_cues:
            if existing["word"].lower() == word:
                time_diff = abs(existing["start_ms"] - start_ms)
                if time_diff < DEDUP_WINDOW_MS:
                    # Skip duplicate
                    return False

        # Generate unique cue ID
        cue_id = f"cue_{len(session.recorded_cues) + 1:04d}"

        recorded_cue = {
            "id": cue_id,
            "start_ms": start_ms,
            "end_ms": cue.get("end_ms", 0),
            "action": cue.get("action", "mute"),
            "category": cue.get("category", "language.profanity"),
            "word": cue.get("matched", cue.get("word", "")),
            "confidence": cue.get("confidence", 0.9)
        }

        session.recorded_cues.append(recorded_cue)
        print(f"[OpenCue] Recorded cue {cue_id}: {recorded_cue['word']} at {recorded_cue['start_ms']}ms")
        return True

    def get_recording_status(self, session: SyncSession) -> dict:
        """Get current recording status"""
        if not session.recording:
            return {
                "recording": False,
                "cue_count": 0,
                "fingerprint_count": 0
            }

        elapsed_ms = session.last_position_ms - session.recording_start_position_ms
        return {
            "recording": True,
            "title": session.recording_title,
            "cue_count": len(session.recorded_cues),
            "fingerprint_count": len(session.recorded_fingerprints),
            "elapsed_ms": elapsed_ms,
            "start_position_ms": session.recording_start_position_ms,
            "current_position_ms": session.last_position_ms
        }


# Import json at module level
import json

# Global instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get the global session manager"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
