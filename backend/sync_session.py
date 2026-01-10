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
from subtitle_sync import SubtitleSyncEngine

# NOTE: The old fingerprinting/microsignature recording code has been deprecated.
# Precision recording (audio/precision_recorder.py) now handles all recording with Whisper.
# These imports are kept for backwards compatibility with cue file playback sync.
try:
    from audio.capture import create_audio_capture
    AUDIO_CAPTURE_AVAILABLE = True
except ImportError:
    AUDIO_CAPTURE_AVAILABLE = False

# Microsignatures may still be used for cue file playback sync
try:
    from audio.microsignatures import MicrosignatureSequence, create_matcher
    MICROSIGNATURES_AVAILABLE = True
except ImportError:
    MICROSIGNATURES_AVAILABLE = False


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

    # Subtitle sync engine (3-step sync approach)
    subtitle_sync_engine: Any = None

    # Microsignature matcher for cue file playback verification
    microsig_matcher: Any = None
    microsig_reference: Any = None

    # Recording mode state (DEPRECATED - use precision recording instead)
    recording: bool = False
    recording_start_time: Optional[datetime] = None
    recording_start_position_ms: int = 0
    recorded_cues: list = field(default_factory=list)
    recording_title: str = ""
    recorded_subtitles: list = field(default_factory=list)


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
            except Exception:
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
        """Start sync engine for session (3-step approach)"""
        # Check what sync data is available
        fingerprints = cue_data.get("fingerprints", {})
        markers = fingerprints.get("markers", [])
        subtitles = cue_data.get("subtitles", [])
        microsigs = cue_data.get("microsignatures", {})
        microsig_sequences = microsigs.get("sequences", [])

        # Load microsignatures for verification if available
        if microsig_sequences and MICROSIGNATURES_AVAILABLE:
            try:
                session.microsig_matcher = create_matcher()
                # Convert dict sequences back to MicrosignatureSequence objects
                session.microsig_reference = [
                    MicrosignatureSequence.from_dict(seq) for seq in microsig_sequences
                ]
                print(f"[OpenCue] Loaded {len(session.microsig_reference)} microsignature sequences for verification")
            except Exception as e:
                print(f"[OpenCue] Could not load microsignatures: {e}")
                session.microsig_matcher = None
                session.microsig_reference = None

        # 3-step sync: try subtitle sync first (most reliable)
        if subtitles:
            print(f"[OpenCue] Cue file has {len(subtitles)} subtitle markers - using subtitle sync")
            session.subtitle_sync_engine = SubtitleSyncEngine(cue_data)
            session.sync_engine = None
            # Start in pending state - will sync once subtitles are received
            has_microsigs = session.microsig_reference is not None
            await self._send_sync_state(session, "syncing", {
                "mode": "subtitle",
                "reason": "waiting_for_subtitles",
                "has_microsignatures": has_microsigs
            })
            return

        if not markers:
            # No fingerprints and no subtitles - use timestamp-only mode
            print(f"[OpenCue] No fingerprints or subtitles in cue file - using timestamp mode")
            session.synced = True
            session.sync_engine = None
            session.subtitle_sync_engine = None
            await self._send_sync_state(session, "synced", {"mode": "timestamp", "reason": "no_sync_data"})
            return

        # Has fingerprints - try audio sync
        try:
            from audio.sync_engine import OpenCueFile, SyncEngine

            cue_file = OpenCueFile(cue_data)

            async def on_cue(cue, event_type):
                await self._handle_cue_event(session, cue, event_type)

            def on_cue_sync(cue, event_type):
                asyncio.create_task(on_cue(cue, event_type))

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
            session.synced = True
            session.sync_engine = None
            await self._send_sync_state(session, "synced", {"mode": "timestamp", "reason": "import_error"})
        except Exception as e:
            print(f"[OpenCue] Failed to start sync engine: {e}")
            session.synced = True
            session.sync_engine = None
            await self._send_sync_state(session, "synced", {"mode": "timestamp", "reason": str(e)})

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

    async def process_subtitle_for_sync(self, session: SyncSession, text: str, position_ms: int):
        """Process incoming subtitle for sync (3-step approach)"""
        if not session.subtitle_sync_engine:
            return

        # Process subtitle through sync engine
        result = session.subtitle_sync_engine.process_subtitle(text, position_ms)

        # Update session state based on result
        if result.synced and not session.synced:
            session.synced = True
            session.sync_offset_ms = result.offset_ms
            print(f"[OpenCue] Synced via subtitle! Offset: {result.offset_ms}ms (confidence: {result.confidence:.2f})")
            await self._send_sync_state(session, "synced", {
                "mode": "subtitle",
                "offset_ms": result.offset_ms,
                "confidence": result.confidence,
                "matched": result.matched_subtitle
            })
        elif result.method == "pending_confirmation":
            print(f"[OpenCue] Subtitle match pending confirmation (offset: {result.offset_ms}ms)")

    def update_position(self, session: SyncSession, position_ms: int):
        """Update playback position (for timestamp-only mode)"""
        session.last_position_ms = position_ms
        session.last_activity = datetime.now()

        # Check cues if in cue file mode
        if session.mode in [SessionMode.CUE_FILE, SessionMode.HYBRID]:
            # Debug: Log position updates periodically
            if position_ms % 5000 < 600:  # Log every ~5 seconds
                print(f"[OpenCue] Position update: {position_ms}ms, synced={session.synced}, cue_file={session.cue_file_id}")

            # Use subtitle sync offset if synced, otherwise timestamp-only
            if session.subtitle_sync_engine and session.synced:
                # Adjust position based on subtitle sync offset
                adjusted_position = position_ms + session.subtitle_sync_engine.offset_ms
                asyncio.create_task(self._check_cues_by_position(session, adjusted_position))
            else:
                # ALWAYS check cues with raw position while waiting for sync
                # This ensures timestamp-only mode works as fallback
                asyncio.create_task(self._check_cues_by_position(session, position_ms))

    async def _check_cues_by_position(self, session: SyncSession, position_ms: int):
        """Check and trigger cues based on reported position"""
        if not session.cue_file_id:
            # Only log occasionally to avoid spam
            if position_ms % 10000 < 600:
                print(f"[OpenCue] No cue file loaded for session")
            return

        cue_data = self._load_cue_file(session.cue_file_id)
        if not cue_data:
            print(f"[OpenCue] Could not load cue file: {session.cue_file_id}")
            return

        cues = cue_data.get("cues", [])
        lookahead_ms = 500  # Trigger slightly early (increased from 200)

        # Debug: show cue check range periodically
        if position_ms % 5000 < 600:
            print(f"[OpenCue] Checking {len(cues)} cues at position {position_ms}ms (triggered: {len(session.triggered_cues)})")

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
                print(f"[OpenCue] TRIGGERING CUE: {cue_id} at position {position_ms}ms (cue: {start_ms}-{end_ms}ms)")

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
        except Exception:
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
        """Start recording mode for a session.

        DEPRECATED: This is the old subtitle-based recording mode.
        Use precision recording (startPrecisionRecording) instead for accurate word-level timing.
        """
        print("[OpenCue] WARNING: Using deprecated subtitle-based recording.")
        print("[OpenCue] Consider using precision recording for better accuracy.")

        session.mode = SessionMode.RECORDING
        session.recording = True
        session.recording_start_time = datetime.now()
        session.recording_start_position_ms = session.last_position_ms
        session.recorded_cues = []
        session.recorded_subtitles = []
        session.recording_title = title or f"Recording {session.session_id}"
        session.content_id = content_id

        print(f"[OpenCue] Recording started for session {session.session_id}: {session.recording_title}")
        return {
            "success": True,
            "recording": True,
            "title": session.recording_title,
            "start_position_ms": session.recording_start_position_ms,
            "deprecated": True,
            "message": "Using deprecated subtitle-based recording. Consider precision recording."
        }

    # NOTE: _fingerprint_capture_loop removed - precision recording handles audio capture now

    def _stop_fingerprint_capture(self, session: SyncSession):
        """Stop audio capture for a session (deprecated)"""
        # Cancel capture task if any
        if hasattr(session, 'fingerprint_capture_task') and session.fingerprint_capture_task:
            session.fingerprint_capture_task.cancel()
            session.fingerprint_capture_task = None

        # Stop audio capture if any
        if hasattr(session, 'recording_audio_capture') and session.recording_audio_capture:
            session.recording_audio_capture.stop()
            session.recording_audio_capture = None

    def stop_recording(self, session: SyncSession) -> dict:
        """Stop recording and return the recorded cues.

        DEPRECATED: This is the old subtitle-based recording mode.
        Use precision recording (stopPrecisionRecording) instead.
        """
        if not session.recording:
            return {"success": False, "error": "Not recording"}

        try:
            session.recording = False
            duration_ms = session.last_position_ms - session.recording_start_position_ms

            # Stop any audio capture
            self._stop_fingerprint_capture(session)

            # Build .opencue file data (simplified - no fingerprints)
            cue_data = {
                "version": "2.0",
                "content": {
                    "title": session.recording_title,
                    "duration_ms": duration_ms if duration_ms > 0 else session.last_position_ms,
                    "content_id": session.content_id,
                    "recorded_at": session.recording_start_time.isoformat() if session.recording_start_time else None
                },
                "subtitles": session.recorded_subtitles,
                "cues": session.recorded_cues,
                "metadata": {
                    "created": datetime.now().isoformat(),
                    "tool_version": "1.0.0",
                    "source": "subtitle_recording_deprecated",
                    "subtitle_count": len(session.recorded_subtitles)
                }
            }

            cue_count = len(session.recorded_cues)
            subtitle_count = len(session.recorded_subtitles)
            print(f"[OpenCue] Recording stopped for session {session.session_id}: "
                  f"{cue_count} cues, {subtitle_count} subtitles")

            # Clean up incremental save temp file
            self._cleanup_temp_file(session)

            # Reset recording state
            session.mode = SessionMode.REALTIME
            session.recorded_subtitles = []

            return {
                "success": True,
                "recording": False,
                "cue_count": cue_count,
                "subtitle_count": subtitle_count,
                "duration_ms": duration_ms,
                "cue_data": cue_data,
                "deprecated": True
            }

        except Exception as e:
            print(f"[OpenCue] ERROR stopping recording: {e}")
            import traceback
            traceback.print_exc()
            session.recording = False
            session.mode = SessionMode.REALTIME
            return {
                "success": False,
                "error": str(e),
                "cue_count": len(session.recorded_cues)
            }

    def abort_recording(self, session: SyncSession) -> dict:
        """Abort recording and discard all captured cues (deprecated)"""
        if not session.recording:
            return {"success": False, "error": "Not recording"}

        cue_count = len(session.recorded_cues)
        subtitle_count = len(session.recorded_subtitles)
        print(f"[OpenCue] Recording ABORTED for session {session.session_id}: "
              f"{cue_count} cues, {subtitle_count} subtitles discarded")

        # Stop any audio capture
        self._stop_fingerprint_capture(session)

        # Reset all recording state
        session.recording = False
        session.mode = SessionMode.REALTIME
        session.recorded_cues = []
        session.recorded_subtitles = []
        session.recording_title = ""
        session.recording_start_time = None

        return {
            "success": True,
            "aborted": True,
            "discarded_cues": cue_count,
            "discarded_subtitles": subtitle_count
        }

    def pause_recording(self, session: SyncSession) -> dict:
        """Pause recording (deprecated - precision recording has no pause)"""
        if not session.recording:
            return {"success": False, "error": "Not recording"}

        cue_count = len(session.recorded_cues)
        position_ms = session.last_position_ms

        print(f"[OpenCue] Recording PAUSED for session {session.session_id}: "
              f"{cue_count} cues at {position_ms}ms")

        session.recording = False

        return {
            "success": True,
            "paused": True,
            "state": {
                "cue_count": cue_count,
                "position_ms": position_ms,
                "title": session.recording_title
            }
        }

    def resume_recording(self, session: SyncSession, position_ms: int = 0) -> dict:
        """Resume recording from paused state (deprecated)"""
        has_previous = len(session.recorded_cues) > 0

        session.recording = True
        session.mode = SessionMode.RECORDING

        if not has_previous:
            session.recording_start_time = datetime.now()
            session.recording_start_position_ms = position_ms

        print(f"[OpenCue] Recording RESUMED for session {session.session_id} at {position_ms}ms "
              f"(existing cues: {len(session.recorded_cues)})")

        return {
            "success": True,
            "resumed": True,
            "existing_cues": len(session.recorded_cues),
            "position_ms": position_ms
        }

    def add_recorded_cue(self, session: SyncSession, cue: dict) -> bool:
        """Add a detected cue to the recording (deprecated subtitle-based recording)"""
        if not session.recording:
            return False

        # Generate unique cue ID
        cue_id = f"cue_{len(session.recorded_cues) + 1:04d}"

        recorded_cue = {
            "id": cue_id,
            "start_ms": cue.get("start_ms", 0),
            "end_ms": cue.get("end_ms", 0),
            "action": cue.get("action", "mute"),
            "category": cue.get("category", "language.profanity"),
            "word": cue.get("matched", cue.get("word", "")),
            "confidence": cue.get("confidence", 0.9)
        }

        session.recorded_cues.append(recorded_cue)
        print(f"[OpenCue] Recorded cue {cue_id}: {recorded_cue['word']} at {recorded_cue['start_ms']}ms (total: {len(session.recorded_cues)})")

        # Auto-save incrementally to prevent data loss
        self._incremental_save(session)

        return True

    def _incremental_save(self, session: SyncSession):
        """Save recording progress incrementally to prevent data loss"""
        try:
            from pathlib import Path
            import json

            # Create temp file with recording progress
            cues_dir = Path(__file__).parent / "cues"
            cues_dir.mkdir(exist_ok=True)

            # Use session ID for temp filename
            safe_title = "".join(c for c in session.recording_title if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_title = safe_title[:50] if safe_title else "recording"
            temp_file = cues_dir / f".{safe_title}_recording.tmp"

            # Build partial cue data
            partial_data = {
                "version": "2.0",
                "content": {
                    "title": session.recording_title,
                    "content_id": session.content_id,
                    "recording_in_progress": True,
                    "recorded_at": session.recording_start_time.isoformat() if session.recording_start_time else None
                },
                "cues": session.recorded_cues,
                "subtitles": session.recorded_subtitles[-50:],  # Last 50 subtitles
                "metadata": {
                    "cue_count": len(session.recorded_cues),
                    "subtitle_count": len(session.recorded_subtitles),
                    "last_update": datetime.now().isoformat()
                }
            }

            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(partial_data, f, indent=2)

        except Exception as e:
            print(f"[OpenCue] Warning: Incremental save failed: {e}")

    def _cleanup_temp_file(self, session: SyncSession):
        """Remove incremental save temp file after successful save"""
        try:
            from pathlib import Path
            cues_dir = Path(__file__).parent / "cues"
            safe_title = "".join(c for c in session.recording_title if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_title = safe_title[:50] if safe_title else "recording"
            temp_file = cues_dir / f".{safe_title}_recording.tmp"
            if temp_file.exists():
                temp_file.unlink()
                print(f"[OpenCue] Cleaned up temp file: {temp_file.name}")
        except Exception as e:
            print(f"[OpenCue] Warning: Could not clean up temp file: {e}")

    def add_recorded_subtitle(self, session: SyncSession, text: str, time_ms: int) -> bool:
        """Add a subtitle snapshot during recording (for 3-step sync)"""
        if not session.recording:
            return False

        # Only record meaningful subtitles (10+ chars, not duplicate)
        if len(text.strip()) < 10:
            return False

        # Skip if duplicate of recent subtitle (within 1 second)
        for existing in session.recorded_subtitles[-5:]:  # Check last 5
            if existing["text"] == text and abs(existing["time_ms"] - time_ms) < 1000:
                return False

        subtitle_entry = {
            "time_ms": time_ms,
            "text": text
        }
        session.recorded_subtitles.append(subtitle_entry)
        return True

    def get_recording_status(self, session: SyncSession) -> dict:
        """Get current recording status (deprecated subtitle-based recording)"""
        if not session.recording:
            return {
                "recording": False,
                "cue_count": 0
            }

        elapsed_ms = session.last_position_ms - session.recording_start_position_ms
        return {
            "recording": True,
            "title": session.recording_title,
            "cue_count": len(session.recorded_cues),
            "elapsed_ms": elapsed_ms,
            "start_position_ms": session.recording_start_position_ms,
            "current_position_ms": session.last_position_ms,
            "deprecated": True
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
