"""
OpenCue - Audio Fingerprint Module

Uses Chromaprint for audio fingerprinting and matching.
Supports two backends:
1. chromaprint library (faster, in-memory)
2. fpcalc executable (slower, uses temp files)
"""

import numpy as np
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
import base64
import struct
import subprocess
import tempfile
import wave
import os
import shutil

# Try to import chromaprint library
try:
    import chromaprint
    CHROMAPRINT_LIB_AVAILABLE = True
except ImportError:
    CHROMAPRINT_LIB_AVAILABLE = False

# Check for fpcalc executable
FPCALC_PATH = shutil.which('fpcalc') or shutil.which('fpcalc.exe')
if not FPCALC_PATH:
    # Check common locations (relative to project and user paths)
    _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _project_dir = os.path.dirname(_backend_dir)
    for path in [
        os.path.join(_project_dir, 'venv311', 'Scripts', 'fpcalc.exe'),
        os.path.join(_project_dir, 'venv', 'Scripts', 'fpcalc.exe'),
        os.path.expanduser('~/bin/fpcalc.exe'),
        os.path.expanduser('~/bin/fpcalc'),
    ]:
        if os.path.exists(path):
            FPCALC_PATH = path
            break

FPCALC_AVAILABLE = FPCALC_PATH is not None

# Overall availability
CHROMAPRINT_AVAILABLE = CHROMAPRINT_LIB_AVAILABLE or FPCALC_AVAILABLE

if not CHROMAPRINT_AVAILABLE:
    print("[OpenCue] chromaprint not available - install chromaprint library or fpcalc")
elif CHROMAPRINT_LIB_AVAILABLE:
    print("[OpenCue] Using chromaprint library for fingerprinting")
elif FPCALC_AVAILABLE:
    print(f"[OpenCue] Using fpcalc for fingerprinting: {FPCALC_PATH}")


@dataclass
class FingerprintMarker:
    """A fingerprint marker at a specific time"""
    time_ms: int
    fingerprint: bytes

    def to_dict(self) -> dict:
        return {
            "time_ms": self.time_ms,
            "hash": base64.b64encode(self.fingerprint).decode('ascii')
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'FingerprintMarker':
        return cls(
            time_ms=data["time_ms"],
            fingerprint=base64.b64decode(data["hash"])
        )


class Fingerprinter:
    """Generate audio fingerprints using Chromaprint (library or fpcalc)"""

    def __init__(self, sample_rate: int = 22050):
        self.sample_rate = sample_rate
        self.use_fpcalc = not CHROMAPRINT_LIB_AVAILABLE and FPCALC_AVAILABLE

        if not CHROMAPRINT_AVAILABLE:
            raise RuntimeError("Chromaprint not available (no library or fpcalc)")

    def fingerprint(self, audio_data: np.ndarray, duration_ms: int = 5000) -> Optional[bytes]:
        """
        Generate fingerprint from audio data.

        Args:
            audio_data: Mono audio samples as float32 numpy array
            duration_ms: Target duration for fingerprint (affects granularity)

        Returns:
            Raw fingerprint bytes or None on failure
        """
        if self.use_fpcalc:
            return self._fingerprint_fpcalc(audio_data)
        else:
            return self._fingerprint_library(audio_data)

    def _fingerprint_library(self, audio_data: np.ndarray) -> Optional[bytes]:
        """Generate fingerprint using chromaprint library"""
        try:
            # Convert to int16 for chromaprint
            audio_int16 = (audio_data * 32767).astype(np.int16)

            # Generate fingerprint
            fp = chromaprint.fingerprint(
                audio_int16.tobytes(),
                self.sample_rate,
                1,  # mono
                len(audio_int16)
            )

            # Return raw fingerprint (not the encoded string)
            return chromaprint.decode_fingerprint(fp)[0] if fp else None

        except Exception as e:
            print(f"[OpenCue] Fingerprint error: {e}")
            return None

    def _fingerprint_fpcalc(self, audio_data: np.ndarray) -> Optional[bytes]:
        """Generate fingerprint using fpcalc executable"""
        try:
            # Convert to int16
            audio_int16 = (audio_data * 32767).astype(np.int16)

            # Write to temp WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name

            try:
                with wave.open(temp_path, 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)  # 16-bit
                    wav.setframerate(self.sample_rate)
                    wav.writeframes(audio_int16.tobytes())

                # Run fpcalc
                result = subprocess.run(
                    [FPCALC_PATH, '-raw', '-json', temp_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    print(f"[OpenCue] fpcalc error: {result.stderr}")
                    return None

                # Parse JSON output
                import json
                data = json.loads(result.stdout)

                # Convert fingerprint array to bytes
                fp_array = data.get('fingerprint', [])
                if not fp_array:
                    return None

                # Pack as uint32 array
                return struct.pack(f'{len(fp_array)}I', *fp_array)

            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

        except Exception as e:
            print(f"[OpenCue] fpcalc fingerprint error: {e}")
            return None

    def fingerprint_encoded(self, audio_data: np.ndarray) -> Optional[str]:
        """Generate base64-encoded fingerprint string"""
        fp = self.fingerprint(audio_data)
        if fp:
            return base64.b64encode(fp).decode('ascii')
        return None


class FingerprintMatcher:
    """Match live audio against known fingerprint markers"""

    def __init__(self, markers: List[FingerprintMarker], sample_rate: int = 22050):
        self.markers = sorted(markers, key=lambda m: m.time_ms)
        self.sample_rate = sample_rate
        self.fingerprinter = Fingerprinter(sample_rate) if CHROMAPRINT_AVAILABLE else None

        # Build lookup structure for fast matching
        self._marker_fps = [(m.time_ms, m.fingerprint) for m in markers]

    def match(self, audio_data: np.ndarray, threshold: float = 0.5) -> Optional[Tuple[int, float]]:
        """
        Match audio against markers.

        Args:
            audio_data: Mono audio samples
            threshold: Minimum similarity score (0-1)

        Returns:
            Tuple of (matched_time_ms, confidence) or None if no match
        """
        if not self.fingerprinter:
            return None

        # Generate fingerprint of live audio
        live_fp = self.fingerprinter.fingerprint(audio_data)
        if not live_fp:
            return None

        # Find best match
        best_match = None
        best_score = threshold

        for time_ms, marker_fp in self._marker_fps:
            score = self._compare_fingerprints(live_fp, marker_fp)
            if score > best_score:
                best_score = score
                best_match = time_ms

        if best_match is not None:
            return (best_match, best_score)
        return None

    def _compare_fingerprints(self, fp1: bytes, fp2: bytes) -> float:
        """
        Compare two fingerprints using bit similarity.

        Returns similarity score between 0 and 1.
        """
        if not fp1 or not fp2:
            return 0.0

        # Convert to integers for comparison
        try:
            # Unpack as array of uint32
            arr1 = np.frombuffer(fp1, dtype=np.uint32)
            arr2 = np.frombuffer(fp2, dtype=np.uint32)

            # Compare overlapping portion
            min_len = min(len(arr1), len(arr2))
            if min_len == 0:
                return 0.0

            arr1 = arr1[:min_len]
            arr2 = arr2[:min_len]

            # Count matching bits using XOR and popcount
            xor = arr1 ^ arr2
            # Count set bits (differences)
            diff_bits = sum(bin(x).count('1') for x in xor)
            total_bits = min_len * 32

            # Similarity is inverse of difference ratio
            similarity = 1.0 - (diff_bits / total_bits)
            return similarity

        except Exception as e:
            print(f"[OpenCue] Fingerprint comparison error: {e}")
            return 0.0


class ContentMatcher:
    """High-level content matching with sync tracking"""

    def __init__(self, markers: List[FingerprintMarker], sample_rate: int = 22050):
        self.matcher = FingerprintMatcher(markers, sample_rate)
        self.sample_rate = sample_rate

        # Sync state
        self._synced = False
        self._offset_ms: Optional[int] = None  # Difference between wall clock and content time
        self._last_match_time: Optional[float] = None
        self._confidence_history: List[float] = []

        # Buffer for accumulating audio
        self._audio_buffer: List[np.ndarray] = []
        self._buffer_duration_ms = 0
        self._target_duration_ms = 5000  # 5 seconds for matching

    def add_audio(self, audio_chunk: np.ndarray, wall_time_ms: int) -> Optional[Dict]:
        """
        Add audio chunk and attempt to match/sync.

        Args:
            audio_chunk: Audio samples
            wall_time_ms: Current wall clock time in milliseconds

        Returns:
            Sync result dict or None if not enough data
        """
        # Add to buffer
        self._audio_buffer.append(audio_chunk)
        chunk_duration_ms = int(len(audio_chunk) / self.sample_rate * 1000)
        self._buffer_duration_ms += chunk_duration_ms

        # Check if we have enough audio
        if self._buffer_duration_ms < self._target_duration_ms:
            return None

        # Combine buffer
        combined = np.concatenate(self._audio_buffer)

        # Clear buffer (keep some overlap)
        overlap_chunks = len(self._audio_buffer) // 2
        self._audio_buffer = self._audio_buffer[overlap_chunks:]
        self._buffer_duration_ms = sum(
            int(len(c) / self.sample_rate * 1000) for c in self._audio_buffer
        )

        # Try to match
        match_result = self.matcher.match(combined)

        if match_result:
            matched_time_ms, confidence = match_result

            # Calculate offset
            new_offset = wall_time_ms - matched_time_ms

            if self._offset_ms is None:
                self._offset_ms = new_offset
            else:
                # Smooth offset updates
                self._offset_ms = int(0.7 * self._offset_ms + 0.3 * new_offset)

            self._synced = True
            self._last_match_time = wall_time_ms
            self._confidence_history.append(confidence)
            if len(self._confidence_history) > 10:
                self._confidence_history.pop(0)

            return {
                "synced": True,
                "content_time_ms": matched_time_ms,
                "offset_ms": self._offset_ms,
                "confidence": confidence,
                "avg_confidence": sum(self._confidence_history) / len(self._confidence_history)
            }

        # No match - check if we've lost sync
        if self._synced and self._last_match_time:
            time_since_match = wall_time_ms - self._last_match_time
            if time_since_match > 30000:  # 30 seconds without match
                self._synced = False
                return {
                    "synced": False,
                    "status": "lost",
                    "time_since_match_ms": time_since_match
                }

        return {
            "synced": self._synced,
            "status": "searching" if not self._synced else "ok"
        }

    def get_content_time(self, wall_time_ms: int) -> Optional[int]:
        """Get estimated content time from wall clock time"""
        if self._offset_ms is not None:
            return wall_time_ms - self._offset_ms
        return None

    def reset(self):
        """Reset sync state"""
        self._synced = False
        self._offset_ms = None
        self._last_match_time = None
        self._confidence_history = []
        self._audio_buffer = []
        self._buffer_duration_ms = 0

    @property
    def is_synced(self) -> bool:
        return self._synced

    @property
    def offset_ms(self) -> Optional[int]:
        return self._offset_ms
