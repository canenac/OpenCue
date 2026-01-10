"""
OpenCue - Precision Recording Manager

Coordinates:
1. Audio device switching (to VB-Cable for silent recording)
2. Audio capture during movie playback
3. Whisper transcription for word-level timestamps
4. Profanity detection with precise timing
5. Cue file generation
6. Volume envelope fingerprinting for sync verification
"""

import asyncio
import json
import wave
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
import threading
import time

from .device_manager import get_device_manager, check_virtual_cable_installed
from .capture import AudioCapture, AudioConfig, CaptureMode
from .whisper_transcribe import (
    get_transcriber, check_whisper_available,
    TranscriptionResult, WordTiming, find_profanity_timestamps
)
# Volume fingerprinting is optional - pycaw has COM threading issues with async
try:
    from .volume_fingerprint import VolumeEnvelopeRecorder, VolumeEnvelope
    VOLUME_FINGERPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    print(f"[OpenCue] Volume fingerprinting disabled: {e}")
    VolumeEnvelopeRecorder = None
    VolumeEnvelope = None
    VOLUME_FINGERPRINT_AVAILABLE = False


@dataclass
class RecordingConfig:
    """Configuration for precision recording"""
    use_virtual_cable: bool = True    # Switch to VB-Cable for silent recording
    whisper_model: str = "base"       # tiny/base/small/medium/large-v2
    playback_speed: float = 1.0       # Adjust if playing at 1.5x or 2x
    sample_rate: int = 16000          # 16kHz for Whisper
    save_audio: bool = True           # Save captured audio to file
    auto_restore_audio: bool = True   # Restore original audio device when done
    video_start_position_ms: int = 0  # Video position when recording started (for timestamp offset)
    capture_volume_envelope: bool = True  # Capture volume envelope for sync verification


@dataclass
class RecordingState:
    """Current state of a precision recording"""
    recording_id: str
    title: str
    content_id: str
    start_time: datetime
    config: RecordingConfig
    audio_chunks: List[np.ndarray] = field(default_factory=list)
    volume_envelope: Optional[VolumeEnvelope] = None
    duration_ms: int = 0
    status: str = "recording"  # recording, processing, complete, failed
    error: Optional[str] = None
    output_path: Optional[str] = None


class PrecisionRecorder:
    """
    Manages high-precision recording with Whisper transcription.

    Usage:
        recorder = PrecisionRecorder()

        # Check requirements
        status = recorder.check_requirements()

        # Start recording
        recording_id = await recorder.start_recording("Movie Title", "netflix:12345")

        # ... movie plays ...

        # Stop and process
        result = await recorder.stop_recording(recording_id)
        # result contains the precise cue file
    """

    def __init__(self):
        self._recordings: Dict[str, RecordingState] = {}
        self._active_recording: Optional[str] = None
        self._capture: Optional[AudioCapture] = None
        self._capture_thread: Optional[threading.Thread] = None
        self._volume_recorder: Optional[VolumeEnvelopeRecorder] = None
        self._volume_thread: Optional[threading.Thread] = None
        self._device_manager = get_device_manager()

    def check_requirements(self) -> Dict[str, Any]:
        """Check if all requirements are met for precision recording"""
        vb_status = check_virtual_cable_installed()
        whisper_status = check_whisper_available()

        return {
            "ready": vb_status["installed"] and whisper_status["available"],
            "virtual_cable": vb_status,
            "whisper": whisper_status,
            "instructions": self._get_setup_instructions(vb_status, whisper_status)
        }

    def _get_setup_instructions(self, vb_status: dict, whisper_status: dict) -> List[str]:
        """Get setup instructions for missing requirements"""
        instructions = []

        if not vb_status["installed"]:
            instructions.append(
                f"Install VB-Cable for silent recording: {vb_status['install_url']}"
            )

        if not whisper_status["available"]:
            instructions.append(
                f"Install Whisper for transcription: {whisper_status['install_command']}"
            )

        return instructions

    async def start_recording(
        self,
        title: str,
        content_id: str,
        config: Optional[RecordingConfig] = None
    ) -> Dict[str, Any]:
        """
        Start a precision recording session.

        Args:
            title: Content title
            content_id: Content identifier
            config: Recording configuration

        Returns:
            Dict with recording_id and status
        """
        if self._active_recording:
            return {
                "success": False,
                "error": "Recording already in progress",
                "recording_id": self._active_recording
            }

        config = config or RecordingConfig()

        # Generate recording ID
        recording_id = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # NOTE: VB-Cable disabled due to routing issues (produces buzzing)
        # Using Realtek loopback instead - recording will be audible
        silent_mode_active = False
        print("[OpenCue] Using audible recording mode (Realtek loopback)")
        print("[OpenCue] You will hear the audio during recording")

        # Create recording state
        state = RecordingState(
            recording_id=recording_id,
            title=title,
            content_id=content_id,
            start_time=datetime.now(),
            config=config
        )
        self._recordings[recording_id] = state
        self._active_recording = recording_id

        # Start audio capture
        audio_config = AudioConfig(
            sample_rate=config.sample_rate,
            channels=1,
            chunk_duration=0.5,
            mode=CaptureMode.SYSTEM
        )
        self._capture = AudioCapture(audio_config)

        if not self._capture.start():
            state.status = "failed"
            state.error = "Failed to start audio capture"
            self._active_recording = None
            return {
                "success": False,
                "error": state.error,
                "recording_id": recording_id
            }

        # Start capture collection thread
        self._capture_thread = threading.Thread(
            target=self._collect_audio,
            args=(state,),
            daemon=True
        )
        self._capture_thread.start()

        # Start volume envelope recording (for sync verification)
        if config.capture_volume_envelope:
            self._start_volume_recording(state)

        print(f"[OpenCue] Precision recording started: {recording_id}")
        print(f"[OpenCue] Title: {title}")
        print(f"[OpenCue] Playback speed: {config.playback_speed}x")

        return {
            "success": True,
            "recording_id": recording_id,
            "title": title,
            "silent_mode": silent_mode_active,
            "whisper_model": config.whisper_model
        }

    def _collect_audio(self, state: RecordingState):
        """Collect audio chunks in background thread"""
        chunk_duration_ms = 500  # 0.5 seconds per chunk
        while self._capture and self._capture.is_running:
            chunk = self._capture.get_audio_chunk(timeout=1.0)
            if chunk is not None:
                state.audio_chunks.append(chunk)
                # Update duration estimate (chunks * ms per chunk)
                state.duration_ms = len(state.audio_chunks) * chunk_duration_ms

    def _start_volume_recording(self, state: RecordingState):
        """Start volume envelope recording in background thread"""
        if not VOLUME_FINGERPRINT_AVAILABLE:
            print("[OpenCue] Volume envelope recording skipped (pycaw not available)")
            return
        try:
            self._volume_recorder = VolumeEnvelopeRecorder(
                target_process="firefox.exe",
                sample_rate_hz=50  # 50 samples per second for detailed fingerprint
            )

            if self._volume_recorder.start_recording(
                start_time_ms=state.config.video_start_position_ms
            ):
                self._volume_thread = threading.Thread(
                    target=self._collect_volume_samples,
                    args=(state,),
                    daemon=True
                )
                self._volume_thread.start()
                print("[OpenCue] Volume envelope recording started (50Hz)")
            else:
                print("[OpenCue] Warning: Could not start volume envelope recording")
                self._volume_recorder = None
        except Exception as e:
            print(f"[OpenCue] Warning: Volume envelope recording failed: {e}")
            self._volume_recorder = None

    def _collect_volume_samples(self, state: RecordingState):
        """Collect volume envelope samples in background thread"""
        sample_interval = 1.0 / 50  # 50 Hz for detailed fingerprint
        start_time = time.time()

        while self._volume_recorder and self._capture and self._capture.is_running:
            elapsed_ms = int((time.time() - start_time) * 1000)
            current_time_ms = state.config.video_start_position_ms + elapsed_ms
            self._volume_recorder.record_sample(current_time_ms)
            time.sleep(sample_interval)

    async def stop_recording(self, recording_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Stop recording and process with Whisper.

        Args:
            recording_id: Recording to stop (defaults to active recording)

        Returns:
            Dict with cue file data and status
        """
        recording_id = recording_id or self._active_recording

        if not recording_id or recording_id not in self._recordings:
            return {
                "success": False,
                "error": "No active recording found"
            }

        state = self._recordings[recording_id]

        # Stop volume envelope recording
        if self._volume_recorder:
            state.volume_envelope = self._volume_recorder.stop_recording()
            self._volume_recorder = None

        if self._volume_thread:
            self._volume_thread.join(timeout=1.0)
            self._volume_thread = None

        # Stop audio capture
        if self._capture:
            self._capture.stop()
            self._capture = None

        # Wait for capture thread
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None

        # Restore original audio device
        if state.config.auto_restore_audio:
            self._device_manager.restore_original()

        self._active_recording = None
        state.status = "processing"

        print(f"[OpenCue] Recording stopped. Processing {len(state.audio_chunks)} audio chunks...")

        # Log volume envelope stats
        if state.volume_envelope:
            samples = state.volume_envelope.samples
            print(f"[OpenCue] Volume envelope: {len(samples)} samples captured")
            if samples:
                import numpy as np
                arr = np.array(samples)
                print(f"[OpenCue] Volume range: {arr.min():.4f} - {arr.max():.4f}, mean: {arr.mean():.4f}")

        # Combine audio chunks
        if not state.audio_chunks:
            state.status = "failed"
            state.error = "No audio captured"
            return {
                "success": False,
                "error": state.error,
                "recording_id": recording_id
            }

        audio_data = np.concatenate(state.audio_chunks)

        # Audio was captured at 44100Hz (VB-Cable) - resample to 16kHz for Whisper
        native_rate = 44100
        target_rate = state.config.sample_rate  # 16000

        if native_rate != target_rate:
            from scipy import signal
            original_samples = len(audio_data)
            target_samples = int(original_samples * target_rate / native_rate)
            print(f"[OpenCue] Resampling complete audio: {native_rate}Hz -> {target_rate}Hz ({original_samples} -> {target_samples} samples)")
            audio_data = signal.resample(audio_data, target_samples)

        duration_ms = int(len(audio_data) / target_rate * 1000)
        state.duration_ms = int(duration_ms * state.config.playback_speed)

        print(f"[OpenCue] Audio duration: {state.duration_ms}ms ({state.duration_ms/1000/60:.1f} minutes)")

        # Normalize audio for better Whisper recognition
        audio_data = self._normalize_audio(audio_data)
        print(f"[OpenCue] Audio normalized, max amplitude: {np.max(np.abs(audio_data)):.3f}")

        # Save audio file if configured
        audio_path = None
        if state.config.save_audio:
            audio_path = await self._save_audio(state, audio_data)

        # Transcribe with Whisper
        try:
            result = await self._transcribe_audio(state, audio_data)
        except Exception as e:
            state.status = "failed"
            state.error = f"Transcription failed: {str(e)}"
            return {
                "success": False,
                "error": state.error,
                "recording_id": recording_id,
                "audio_path": audio_path
            }

        # Generate cue file
        cue_data = await self._generate_cue_file(state, result)

        # Save cue file
        cue_path = await self._save_cue_file(state, cue_data)
        state.output_path = cue_path
        state.status = "complete"

        return {
            "success": True,
            "recording_id": recording_id,
            "cue_file": cue_path,
            "cue_data": cue_data,
            "audio_path": audio_path,
            "duration_ms": state.duration_ms,
            "word_count": len(result.words),
            "cue_count": len(cue_data.get("cues", []))
        }

    async def _save_audio(self, state: RecordingState, audio_data: np.ndarray) -> str:
        """Save captured audio to WAV file"""
        cues_dir = Path(__file__).parent.parent / "cues"
        cues_dir.mkdir(exist_ok=True)

        safe_title = "".join(c for c in state.title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title[:50] if safe_title else "recording"
        audio_path = cues_dir / f"{safe_title}.wav"

        # Convert to int16
        audio_int16 = (audio_data * 32767).astype(np.int16)

        with wave.open(str(audio_path), 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(state.config.sample_rate)
            wav.writeframes(audio_int16.tobytes())

        print(f"[OpenCue] Audio saved: {audio_path}")
        return str(audio_path)

    async def _transcribe_audio(
        self,
        state: RecordingState,
        audio_data: np.ndarray
    ) -> TranscriptionResult:
        """Transcribe audio with Whisper"""
        print(f"[OpenCue] Starting Whisper transcription (model: {state.config.whisper_model})...")

        transcriber = get_transcriber(state.config.whisper_model)

        # Run in thread to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: transcriber.transcribe_audio_data(
                audio_data,
                sample_rate=state.config.sample_rate,
                language="en",
                playback_speed=state.config.playback_speed
            )
        )

        print(f"[OpenCue] Transcription complete: {len(result.words)} words")
        return result

    async def _generate_cue_file(
        self,
        state: RecordingState,
        transcription: TranscriptionResult
    ) -> Dict[str, Any]:
        """Generate cue file from transcription"""
        from profanity.detector import get_all_profanity_words

        # Get profanity word list
        profanity_words = get_all_profanity_words()

        # Find profanity in transcription
        detected = find_profanity_timestamps(transcription, profanity_words)

        # Get video start offset (timestamps are relative to recording start, need to add video position)
        video_offset_ms = state.config.video_start_position_ms
        print(f"[OpenCue] Applying video offset: {video_offset_ms}ms to all cue timestamps")

        # Build cues with precise timing
        cues = []
        for i, word in enumerate(detected):
            # Add small padding for safety
            PADDING_MS = 50

            # Add video offset to convert recording-relative timestamps to video-absolute timestamps
            cues.append({
                "id": f"cue_{i+1:04d}",
                "type": "mute",
                "start_ms": max(0, word.start_ms - PADDING_MS + video_offset_ms),
                "end_ms": word.end_ms + PADDING_MS + video_offset_ms,
                "detected_word": word.word,
                "confidence": word.confidence,
                "source": "whisper"
            })

        # Build cue file
        cue_data = {
            "version": "2.0",
            "content": {
                "title": state.title,
                "content_id": state.content_id,
                "duration_ms": state.duration_ms
            },
            "cues": cues,
            "metadata": {
                "created": datetime.now().isoformat(),
                "creator": "OpenCue Precision Recorder",
                "whisper_model": state.config.whisper_model,
                "playback_speed": state.config.playback_speed,
                "word_count": len(transcription.words),
                "source": "whisper_transcription",
                "video_start_position_ms": state.config.video_start_position_ms
            },
            "transcription": {
                "full_text": transcription.text[:1000] + "..." if len(transcription.text) > 1000 else transcription.text,
                "language": transcription.language
            }
        }

        # Add volume envelope for sync verification if captured
        if state.volume_envelope and state.volume_envelope.samples:
            cue_data["volume_envelope"] = state.volume_envelope.to_dict()
            print(f"[OpenCue] Volume envelope added to cue file ({len(state.volume_envelope.samples)} samples)")

        print(f"[OpenCue] Generated {len(cues)} cues from transcription")
        return cue_data

    async def _save_cue_file(self, state: RecordingState, cue_data: Dict) -> str:
        """Save cue file to disk"""
        cues_dir = Path(__file__).parent.parent / "cues"
        cues_dir.mkdir(exist_ok=True)

        safe_title = "".join(c for c in state.title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title[:50] if safe_title else "recording"
        cue_path = cues_dir / f"{safe_title}.opencue"

        with open(cue_path, 'w', encoding='utf-8') as f:
            json.dump(cue_data, f, indent=2)

        print(f"[OpenCue] Cue file saved: {cue_path}")
        return str(cue_path)

    def _normalize_audio(self, audio_data: np.ndarray, target_level: float = 0.9) -> np.ndarray:
        """
        Normalize audio to target level for better Whisper recognition.

        Args:
            audio_data: Audio samples (float32, -1 to 1 range expected by Whisper)
            target_level: Target peak level (0-1)

        Returns:
            Normalized audio data
        """
        # Get current max amplitude
        max_amplitude = np.max(np.abs(audio_data))

        if max_amplitude == 0:
            print("[OpenCue] Warning: Audio is completely silent")
            return audio_data

        # Calculate normalization factor
        normalization_factor = target_level / max_amplitude

        # Don't amplify too much (could amplify noise)
        max_gain = 10.0  # Maximum 10x amplification
        if normalization_factor > max_gain:
            print(f"[OpenCue] Warning: Audio very quiet, limiting gain to {max_gain}x")
            normalization_factor = max_gain

        # Apply normalization
        normalized = audio_data * normalization_factor

        print(f"[OpenCue] Audio normalized: {max_amplitude:.4f} -> {np.max(np.abs(normalized)):.4f} (gain: {normalization_factor:.1f}x)")

        return normalized

    def get_recording_status(self, recording_id: Optional[str] = None) -> Dict[str, Any]:
        """Get status of a recording"""
        recording_id = recording_id or self._active_recording

        if not recording_id or recording_id not in self._recordings:
            return {
                "active": False,
                "recording_id": None
            }

        state = self._recordings[recording_id]

        return {
            "active": state.status == "recording",
            "recording_id": recording_id,
            "title": state.title,
            "status": state.status,
            "duration_ms": state.duration_ms,
            "chunks_captured": len(state.audio_chunks),
            "error": state.error,
            "output_path": state.output_path
        }

    def abort_recording(self, recording_id: Optional[str] = None) -> Dict[str, Any]:
        """Abort an active recording without processing"""
        recording_id = recording_id or self._active_recording

        if not recording_id or recording_id not in self._recordings:
            return {"success": False, "error": "No recording found"}

        state = self._recordings[recording_id]

        # Stop volume recording
        if self._volume_recorder:
            self._volume_recorder.stop_recording()
            self._volume_recorder = None

        # Stop capture
        if self._capture:
            self._capture.stop()
            self._capture = None

        # Restore audio
        if state.config.auto_restore_audio:
            self._device_manager.restore_original()

        state.status = "aborted"
        self._active_recording = None

        return {"success": True, "recording_id": recording_id}


# Singleton instance
_recorder: Optional[PrecisionRecorder] = None


def get_precision_recorder() -> PrecisionRecorder:
    """Get the precision recorder singleton"""
    global _recorder
    if _recorder is None:
        _recorder = PrecisionRecorder()
    return _recorder
