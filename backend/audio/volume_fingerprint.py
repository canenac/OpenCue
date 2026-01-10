"""
Volume Envelope Fingerprinting for OpenCue

This module captures audio volume levels (peak meters) without recording
actual audio. The volume envelope can be used for sync verification
during playback.

Key insight: Windows exposes per-application audio meters via WASAPI.
We can read Firefox's meter to track volume over time, creating a
"loudness fingerprint" that matches the content being played.
"""
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from pycaw.utils import AudioUtilities
from pycaw.api.endpointvolume import IAudioMeterInformation


@dataclass
class VolumeEnvelope:
    """Stores a volume envelope (loudness over time)"""
    samples: List[float] = field(default_factory=list)
    timestamps_ms: List[int] = field(default_factory=list)
    sample_rate_hz: float = 20.0  # Default: 20 samples per second
    start_time_ms: int = 0

    def add_sample(self, peak: float, timestamp_ms: int):
        """Add a peak sample at the given timestamp"""
        self.samples.append(peak)
        self.timestamps_ms.append(timestamp_ms)

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage"""
        return {
            "samples": self.samples,
            "timestamps_ms": self.timestamps_ms,
            "sample_rate_hz": self.sample_rate_hz,
            "start_time_ms": self.start_time_ms
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VolumeEnvelope":
        """Deserialize from dictionary"""
        envelope = cls(
            samples=data.get("samples", []),
            timestamps_ms=data.get("timestamps_ms", []),
            sample_rate_hz=data.get("sample_rate_hz", 20.0),
            start_time_ms=data.get("start_time_ms", 0)
        )
        return envelope


class VolumeEnvelopeRecorder:
    """Records volume envelope from a specific application"""

    def __init__(self, target_process: str = "firefox.exe", sample_rate_hz: float = 20.0):
        self.target_process = target_process.lower()
        self.sample_rate_hz = sample_rate_hz
        self.sample_interval = 1.0 / sample_rate_hz
        self.meter: Optional[IAudioMeterInformation] = None
        self.envelope: Optional[VolumeEnvelope] = None
        self._recording = False

    def find_session_meter(self) -> bool:
        """Find and cache the audio meter for the target process"""
        sessions = AudioUtilities.GetAllSessions()

        for session in sessions:
            process = session.Process
            if process:
                name = process.name().lower()
                if self.target_process in name:
                    try:
                        self.meter = session._ctl.QueryInterface(IAudioMeterInformation)
                        print(f"[VolumeRecorder] Found meter for {name}")
                        return True
                    except Exception as e:
                        print(f"[VolumeRecorder] Error getting meter for {name}: {e}")

        print(f"[VolumeRecorder] Could not find audio session for {self.target_process}")
        return False

    def get_peak(self) -> float:
        """Get current peak value (0.0 to 1.0)"""
        if self.meter is None:
            if not self.find_session_meter():
                return 0.0

        try:
            return self.meter.GetPeakValue()
        except Exception as e:
            print(f"[VolumeRecorder] Error reading peak: {e}")
            self.meter = None  # Will retry finding meter
            return 0.0

    def start_recording(self, start_time_ms: int = 0) -> bool:
        """Start recording volume envelope"""
        if not self.find_session_meter():
            return False

        self.envelope = VolumeEnvelope(
            sample_rate_hz=self.sample_rate_hz,
            start_time_ms=start_time_ms
        )
        self._recording = True
        print(f"[VolumeRecorder] Started recording at {self.sample_rate_hz}Hz")
        return True

    def record_sample(self, current_time_ms: int):
        """Record a single sample at the current time"""
        if not self._recording or self.envelope is None:
            return

        peak = self.get_peak()
        self.envelope.add_sample(peak, current_time_ms)

    def stop_recording(self) -> Optional[VolumeEnvelope]:
        """Stop recording and return the envelope"""
        self._recording = False
        envelope = self.envelope
        self.envelope = None
        if envelope:
            print(f"[VolumeRecorder] Stopped. Captured {len(envelope.samples)} samples")
        return envelope


class VolumeEnvelopeMatcher:
    """Matches live volume against a stored envelope for sync"""

    def __init__(self, reference_envelope: VolumeEnvelope, window_size: int = 100):
        self.reference = reference_envelope
        self.window_size = window_size  # Number of samples to compare
        self.ref_array = np.array(reference_envelope.samples)

    def find_position(self, live_samples: List[float]) -> Tuple[int, float]:
        """
        Find the position in the reference that best matches the live samples.

        Returns:
            (position_ms, confidence) - The estimated position and match confidence
        """
        if len(live_samples) < 10:
            return (0, 0.0)

        live_array = np.array(live_samples)

        # Normalize both arrays
        if np.std(live_array) > 0.001:
            live_norm = (live_array - np.mean(live_array)) / np.std(live_array)
        else:
            return (0, 0.0)  # No meaningful signal

        if np.std(self.ref_array) > 0.001:
            ref_norm = (self.ref_array - np.mean(self.ref_array)) / np.std(self.ref_array)
        else:
            return (0, 0.0)

        # Cross-correlation to find best alignment
        correlation = np.correlate(ref_norm, live_norm, mode='valid')

        if len(correlation) == 0:
            return (0, 0.0)

        # Find peak correlation
        best_idx = np.argmax(correlation)
        best_corr = correlation[best_idx]

        # Normalize correlation to 0-1 range (confidence)
        max_possible = len(live_norm) * 1.0  # Perfect correlation
        confidence = min(1.0, max(0.0, best_corr / max_possible))

        # Convert index to timestamp
        if len(self.reference.timestamps_ms) > best_idx:
            position_ms = self.reference.timestamps_ms[best_idx]
        else:
            # Estimate from sample rate
            position_ms = int(best_idx * (1000.0 / self.reference.sample_rate_hz))

        return (position_ms, confidence)


def test_volume_recording():
    """Test volume envelope recording"""
    print("=== Volume Envelope Recording Test ===\n")

    recorder = VolumeEnvelopeRecorder(target_process="firefox.exe", sample_rate_hz=20)

    if not recorder.start_recording(start_time_ms=0):
        print("Failed to start recording. Is Firefox playing audio?")
        return

    print("Recording for 10 seconds... Play audio in Firefox!\n")

    start_time = time.time()
    while time.time() - start_time < 10:
        elapsed_ms = int((time.time() - start_time) * 1000)
        recorder.record_sample(elapsed_ms)

        # Visual feedback
        peak = recorder.envelope.samples[-1] if recorder.envelope.samples else 0
        bar = "#" * int(peak * 50)
        print(f"\r  {elapsed_ms:5d}ms | {peak:.4f} | {bar:50s}", end="", flush=True)

        time.sleep(1.0 / 20)  # 20 Hz

    print("\n")
    envelope = recorder.stop_recording()

    if envelope:
        print(f"\nRecorded {len(envelope.samples)} samples")
        print(f"Time range: {envelope.timestamps_ms[0]}ms - {envelope.timestamps_ms[-1]}ms")

        # Show statistics
        samples = np.array(envelope.samples)
        print(f"Peak range: {samples.min():.4f} - {samples.max():.4f}")
        print(f"Mean: {samples.mean():.4f}, Std: {samples.std():.4f}")

        # Test serialization
        data = envelope.to_dict()
        restored = VolumeEnvelope.from_dict(data)
        print(f"Serialization test: {len(restored.samples)} samples restored")


if __name__ == "__main__":
    test_volume_recording()
