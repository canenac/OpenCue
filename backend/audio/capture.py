"""
OpenCue - Audio Capture Module

Hybrid audio capture supporting:
1. System audio (loopback) - preferred
2. Microphone fallback - when system audio unavailable
"""

# CRITICAL: Fix for soundcard + NumPy 2.x compatibility
# numpy.fromstring was removed in NumPy 2.0, soundcard uses it internally
# This MUST happen before any other imports that might load soundcard
import numpy
if not hasattr(numpy, 'fromstring'):
    numpy.fromstring = numpy.frombuffer

import asyncio
import numpy as np
from typing import Optional, Callable, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import threading
import queue
from scipy import signal

# Audio capture backends
try:
    import soundcard as sc
    SOUNDCARD_AVAILABLE = True
except ImportError:
    SOUNDCARD_AVAILABLE = False
    print("[OpenCue] soundcard not available - system audio capture disabled")

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    print("[OpenCue] sounddevice not available - microphone capture disabled")


class CaptureMode(Enum):
    SYSTEM = "system"      # System audio loopback
    MICROPHONE = "mic"     # Microphone input
    AUTO = "auto"          # Try system first, fall back to mic


@dataclass
class AudioConfig:
    sample_rate: int = 22050      # Chromaprint default
    channels: int = 1             # Mono for fingerprinting
    chunk_duration: float = 0.5   # Seconds per chunk
    mode: CaptureMode = CaptureMode.AUTO


class AudioCapture:
    """Hybrid audio capture with system audio and microphone support"""

    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig()
        self.running = False
        self.audio_queue: queue.Queue = queue.Queue(maxsize=100)
        self._capture_thread: Optional[threading.Thread] = None
        self._active_mode: Optional[CaptureMode] = None

    def get_available_modes(self) -> list[CaptureMode]:
        """Get list of available capture modes"""
        modes = []
        if SOUNDCARD_AVAILABLE:
            try:
                # Check if loopback device exists
                loopback = sc.default_speaker()
                if loopback:
                    modes.append(CaptureMode.SYSTEM)
            except Exception:
                pass
        if SOUNDDEVICE_AVAILABLE:
            try:
                # Check if microphone exists
                devices = sd.query_devices()
                if any(d['max_input_channels'] > 0 for d in devices):
                    modes.append(CaptureMode.MICROPHONE)
            except Exception:
                pass
        return modes

    def start(self) -> bool:
        """Start audio capture"""
        if self.running:
            return True

        available = self.get_available_modes()
        if not available:
            print("[OpenCue] No audio capture methods available")
            return False

        # Determine mode
        if self.config.mode == CaptureMode.AUTO:
            # Prefer system audio, fall back to mic
            if CaptureMode.SYSTEM in available:
                self._active_mode = CaptureMode.SYSTEM
            elif CaptureMode.MICROPHONE in available:
                self._active_mode = CaptureMode.MICROPHONE
            else:
                return False
        else:
            if self.config.mode in available:
                self._active_mode = self.config.mode
            else:
                print(f"[OpenCue] Requested mode {self.config.mode} not available")
                return False

        self.running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        print(f"[OpenCue] Audio capture started: {self._active_mode.value}")
        return True

    def stop(self):
        """Stop audio capture"""
        self.running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None
        self._active_mode = None

        # Clear queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        print("[OpenCue] Audio capture stopped")

    def _capture_loop(self):
        """Main capture loop - runs in separate thread"""
        if self._active_mode == CaptureMode.SYSTEM:
            self._capture_system_audio()
        elif self._active_mode == CaptureMode.MICROPHONE:
            self._capture_microphone()

    def _capture_system_audio(self):
        """Capture from system audio loopback"""
        # First, try VB-Cable with sounddevice (works better than soundcard)
        if SOUNDDEVICE_AVAILABLE:
            cable_idx = None
            for i, d in enumerate(sd.query_devices()):
                if 'cable output' in d['name'].lower() and 'vb-audio virtual' in d['name'].lower():
                    cable_idx = i
                    print(f"[OpenCue] Found VB-Cable Output: {d['name']}")
                    break

            if cable_idx is not None:
                try:
                    # Use sounddevice for VB-Cable (soundcard has issues with it)
                    native_rate = 44100  # VB-Cable configured at 44100Hz
                    chunk_samples = int(native_rate * self.config.chunk_duration)

                    print(f"[OpenCue] Recording from VB-Cable (silent mode) at {native_rate}Hz")
                    print(f"[OpenCue] Using sounddevice library for reliable capture")

                    while self.running:
                        try:
                            data = sd.rec(chunk_samples, samplerate=native_rate,
                                         channels=1, device=cable_idx, dtype='float32')
                            sd.wait()

                            data = data.flatten()
                            self.audio_queue.put(data, timeout=0.1)
                        except queue.Full:
                            try:
                                self.audio_queue.get_nowait()
                                self.audio_queue.put(data, timeout=0.1)
                            except Exception:
                                pass
                        except Exception as e:
                            print(f"[OpenCue] VB-Cable capture error: {e}")
                            break
                    return
                except Exception as e:
                    print(f"[OpenCue] VB-Cable sounddevice error: {e}")

        # Fallback to soundcard for Realtek loopback
        if not SOUNDCARD_AVAILABLE:
            return

        try:
            speaker = None
            for s in sc.all_speakers():
                if 'realtek' in s.name.lower():
                    speaker = s
                    print(f"[OpenCue] Found Realtek: {s.name}")
                    break

            if not speaker:
                speaker = sc.default_speaker()
                print(f"[OpenCue] Realtek not found, using default: {speaker.name}")

            mic = sc.get_microphone(speaker.id, include_loopback=True)
            print(f"[OpenCue] Using loopback capture from: {speaker.name}")

            native_rate = 48000
            native_chunk_samples = int(native_rate * self.config.chunk_duration)

            with mic.recorder(samplerate=native_rate, channels=self.config.channels) as recorder:
                print(f"[OpenCue] Audio capture active: {mic.name}")
                print(f"[OpenCue] Capturing at {native_rate}Hz (will resample complete audio later)")

                while self.running:
                    try:
                        data = recorder.record(numframes=native_chunk_samples)

                        if len(data.shape) > 1 and data.shape[1] > 1:
                            data = np.mean(data, axis=1)

                        data = data.astype(np.float32).flatten()
                        self.audio_queue.put(data, timeout=0.1)
                    except queue.Full:
                        try:
                            self.audio_queue.get_nowait()
                            self.audio_queue.put(data, timeout=0.1)
                        except Exception:
                            pass
                    except Exception as e:
                        print(f"[OpenCue] System audio error: {e}")
                        break

        except Exception as e:
            print(f"[OpenCue] Failed to start system audio: {e}")
            if CaptureMode.MICROPHONE in self.get_available_modes():
                print("[OpenCue] Falling back to microphone...")
                self._active_mode = CaptureMode.MICROPHONE
                self._capture_microphone()

    def _capture_microphone(self):
        """Capture from microphone"""
        if not SOUNDDEVICE_AVAILABLE:
            return

        try:
            chunk_samples = int(self.config.sample_rate * self.config.chunk_duration)

            def callback(indata, frames, time, status):
                if status:
                    print(f"[OpenCue] Mic status: {status}")
                if self.running:
                    try:
                        # Convert to mono if stereo
                        data = indata[:, 0] if len(indata.shape) > 1 else indata.flatten()
                        self.audio_queue.put(data.astype(np.float32), block=False)
                    except queue.Full:
                        pass

            with sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                blocksize=chunk_samples,
                callback=callback
            ):
                print("[OpenCue] Microphone capture active")
                while self.running:
                    asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.1))

        except Exception as e:
            print(f"[OpenCue] Microphone capture error: {e}")

    def get_audio_chunk(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """Get next audio chunk from queue"""
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    async def get_audio_stream(self) -> AsyncGenerator[np.ndarray, None]:
        """Async generator for audio chunks"""
        while self.running:
            chunk = self.get_audio_chunk(timeout=0.5)
            if chunk is not None:
                yield chunk
            else:
                await asyncio.sleep(0.1)

    @property
    def active_mode(self) -> Optional[CaptureMode]:
        return self._active_mode

    @property
    def is_running(self) -> bool:
        return self.running


# Convenience function
def create_audio_capture(mode: str = "auto") -> AudioCapture:
    """Create audio capture with specified mode"""
    mode_map = {
        "auto": CaptureMode.AUTO,
        "system": CaptureMode.SYSTEM,
        "mic": CaptureMode.MICROPHONE,
        "microphone": CaptureMode.MICROPHONE
    }
    config = AudioConfig(mode=mode_map.get(mode.lower(), CaptureMode.AUTO))
    return AudioCapture(config)
