"""
OpenCue - Audio Microsignatures

Lightweight audio signatures for precise sync verification.
Unlike global fingerprints, microsignatures only need to be unique
within a small time window (±10 seconds).

Key features extracted:
1. Onsets - When sounds start (consonants, impacts, etc.)
2. Energy peaks - Volume spikes
3. Spectral flux - Tonal changes
4. Zero-crossing patterns - Voice/silence transitions

These are fast to compute and provide sub-100ms precision.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum


class SignatureType(Enum):
    ONSET = "onset"           # Sound start (high precision)
    ENERGY_PEAK = "peak"      # Volume spike
    SPECTRAL_FLUX = "flux"    # Tonal change
    SILENCE_START = "silence" # Transition to quiet
    SILENCE_END = "voice"     # Transition from quiet


@dataclass
class Microsignature:
    """A single audio microsignature event"""
    time_ms: int              # Precise timestamp
    sig_type: SignatureType   # Type of event
    strength: float           # How prominent (0-1)

    def to_dict(self) -> dict:
        return {
            "time_ms": self.time_ms,
            "type": self.sig_type.value,
            "strength": round(self.strength, 3)
        }

    @staticmethod
    def from_dict(d: dict) -> 'Microsignature':
        return Microsignature(
            time_ms=d["time_ms"],
            sig_type=SignatureType(d["type"]),
            strength=d.get("strength", 1.0)
        )


@dataclass
class MicrosignatureSequence:
    """A sequence of microsignatures over a time range"""
    start_ms: int
    end_ms: int
    signatures: List[Microsignature] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "signatures": [s.to_dict() for s in self.signatures]
        }

    @staticmethod
    def from_dict(d: dict) -> 'MicrosignatureSequence':
        return MicrosignatureSequence(
            start_ms=d["start_ms"],
            end_ms=d["end_ms"],
            signatures=[Microsignature.from_dict(s) for s in d.get("signatures", [])]
        )


class MicrosignatureExtractor:
    """
    Extracts audio microsignatures for precise sync.

    Designed for speed and precision within small windows,
    not global uniqueness like Chromaprint.
    """

    def __init__(self, sample_rate: int = 22050):
        self.sample_rate = sample_rate

        # Analysis parameters
        self.frame_size = 512          # ~23ms at 22050Hz
        self.hop_size = 256            # ~12ms hop for precision
        self.onset_threshold = 0.15    # Sensitivity for onset detection
        self.peak_threshold = 0.3      # Minimum prominence for peaks
        self.silence_threshold = 0.02  # Below this = silence

    def extract(self, audio: np.ndarray, base_time_ms: int = 0) -> MicrosignatureSequence:
        """
        Extract microsignatures from audio chunk.

        Args:
            audio: Audio samples (mono, float32, -1 to 1)
            base_time_ms: Timestamp of audio start

        Returns:
            MicrosignatureSequence with detected events
        """
        if len(audio) < self.frame_size:
            return MicrosignatureSequence(base_time_ms, base_time_ms, [])

        # Ensure mono
        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)

        # Normalize
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val

        signatures = []
        duration_ms = int(len(audio) / self.sample_rate * 1000)

        # Extract different signature types
        signatures.extend(self._detect_onsets(audio, base_time_ms))
        signatures.extend(self._detect_energy_peaks(audio, base_time_ms))
        signatures.extend(self._detect_silence_transitions(audio, base_time_ms))
        signatures.extend(self._detect_spectral_flux(audio, base_time_ms))

        # Sort by time
        signatures.sort(key=lambda s: s.time_ms)

        return MicrosignatureSequence(
            start_ms=base_time_ms,
            end_ms=base_time_ms + duration_ms,
            signatures=signatures
        )

    def _detect_onsets(self, audio: np.ndarray, base_time_ms: int) -> List[Microsignature]:
        """
        Detect sound onsets using spectral flux.

        Onsets are very precise markers - when a consonant starts,
        when a drum hits, etc.
        """
        signatures = []

        # Compute short-time energy difference
        n_frames = (len(audio) - self.frame_size) // self.hop_size + 1
        if n_frames < 2:
            return signatures

        energies = []
        for i in range(n_frames):
            start = i * self.hop_size
            frame = audio[start:start + self.frame_size]
            energy = np.sqrt(np.mean(frame ** 2))
            energies.append(energy)

        energies = np.array(energies)

        # Onset = rapid energy increase
        for i in range(1, len(energies)):
            diff = energies[i] - energies[i-1]
            if diff > self.onset_threshold and energies[i] > self.silence_threshold:
                time_ms = base_time_ms + int(i * self.hop_size / self.sample_rate * 1000)
                strength = min(1.0, diff / 0.5)  # Normalize strength
                signatures.append(Microsignature(
                    time_ms=time_ms,
                    sig_type=SignatureType.ONSET,
                    strength=strength
                ))

        return signatures

    def _detect_energy_peaks(self, audio: np.ndarray, base_time_ms: int) -> List[Microsignature]:
        """
        Detect local energy peaks (volume spikes).
        """
        signatures = []

        # Compute energy envelope
        n_frames = (len(audio) - self.frame_size) // self.hop_size + 1
        if n_frames < 3:
            return signatures

        energies = []
        for i in range(n_frames):
            start = i * self.hop_size
            frame = audio[start:start + self.frame_size]
            energy = np.sqrt(np.mean(frame ** 2))
            energies.append(energy)

        energies = np.array(energies)

        # Find local maxima
        for i in range(1, len(energies) - 1):
            if (energies[i] > energies[i-1] and
                energies[i] > energies[i+1] and
                energies[i] > self.peak_threshold):

                # Check prominence (how much higher than neighbors)
                prominence = energies[i] - max(energies[max(0,i-3):i].min() if i > 0 else 0,
                                               energies[i+1:min(len(energies),i+4)].min() if i < len(energies)-1 else 0)

                if prominence > 0.1:
                    time_ms = base_time_ms + int(i * self.hop_size / self.sample_rate * 1000)
                    strength = min(1.0, energies[i])
                    signatures.append(Microsignature(
                        time_ms=time_ms,
                        sig_type=SignatureType.ENERGY_PEAK,
                        strength=strength
                    ))

        return signatures

    def _detect_silence_transitions(self, audio: np.ndarray, base_time_ms: int) -> List[Microsignature]:
        """
        Detect transitions between silence and sound.

        Very useful for dialogue - marks when speaking starts/stops.
        """
        signatures = []

        n_frames = (len(audio) - self.frame_size) // self.hop_size + 1
        if n_frames < 2:
            return signatures

        energies = []
        for i in range(n_frames):
            start = i * self.hop_size
            frame = audio[start:start + self.frame_size]
            energy = np.sqrt(np.mean(frame ** 2))
            energies.append(energy)

        # Track silence state
        in_silence = energies[0] < self.silence_threshold

        for i in range(1, len(energies)):
            now_silent = energies[i] < self.silence_threshold

            if in_silence and not now_silent:
                # Silence -> Sound
                time_ms = base_time_ms + int(i * self.hop_size / self.sample_rate * 1000)
                signatures.append(Microsignature(
                    time_ms=time_ms,
                    sig_type=SignatureType.SILENCE_END,
                    strength=min(1.0, energies[i] / 0.3)
                ))
            elif not in_silence and now_silent:
                # Sound -> Silence
                time_ms = base_time_ms + int(i * self.hop_size / self.sample_rate * 1000)
                signatures.append(Microsignature(
                    time_ms=time_ms,
                    sig_type=SignatureType.SILENCE_START,
                    strength=1.0
                ))

            in_silence = now_silent

        return signatures

    def _detect_spectral_flux(self, audio: np.ndarray, base_time_ms: int) -> List[Microsignature]:
        """
        Detect spectral flux events (sudden tonal changes).

        Useful for music, sound effects, scene changes.
        """
        signatures = []

        n_frames = (len(audio) - self.frame_size) // self.hop_size + 1
        if n_frames < 2:
            return signatures

        # Compute simple spectral features per frame
        prev_spectrum = None

        for i in range(n_frames):
            start = i * self.hop_size
            frame = audio[start:start + self.frame_size]

            # Simple FFT magnitude
            spectrum = np.abs(np.fft.rfft(frame * np.hanning(len(frame))))

            if prev_spectrum is not None and len(spectrum) == len(prev_spectrum):
                # Spectral flux = sum of positive differences
                diff = spectrum - prev_spectrum
                flux = np.sum(np.maximum(0, diff))

                # Normalize by spectrum size
                flux = flux / len(spectrum)

                if flux > 0.1:  # Threshold for significant change
                    time_ms = base_time_ms + int(i * self.hop_size / self.sample_rate * 1000)
                    strength = min(1.0, flux / 0.3)
                    signatures.append(Microsignature(
                        time_ms=time_ms,
                        sig_type=SignatureType.SPECTRAL_FLUX,
                        strength=strength
                    ))

            prev_spectrum = spectrum

        return signatures


class MicrosignatureMatcher:
    """
    Matches microsignature sequences for sync verification.

    Given a reference sequence and a live sequence, finds the
    best alignment within a search window.
    """

    def __init__(self):
        self.match_window_ms = 100    # Max time difference for matching events
        self.min_matches = 3          # Minimum matches required
        self.type_weights = {
            SignatureType.ONSET: 2.0,        # Onsets are most precise
            SignatureType.SILENCE_END: 1.5,  # Silence transitions are good
            SignatureType.SILENCE_START: 1.5,
            SignatureType.ENERGY_PEAK: 1.0,
            SignatureType.SPECTRAL_FLUX: 0.8
        }

    def find_offset(self,
                    reference: MicrosignatureSequence,
                    live: MicrosignatureSequence,
                    search_range_ms: int = 5000) -> Optional[Tuple[int, float]]:
        """
        Find the best time offset between reference and live sequences.

        Args:
            reference: Microsignatures from cue file
            live: Microsignatures from current playback
            search_range_ms: How far to search (±ms)

        Returns:
            (offset_ms, confidence) or None if no good match
            offset_ms: Add to live time to get reference time
        """
        if not reference.signatures or not live.signatures:
            return None

        # Try different offsets and score each
        best_offset = 0
        best_score = 0.0

        # Use onset events to seed candidate offsets
        ref_onsets = [s for s in reference.signatures if s.sig_type == SignatureType.ONSET]
        live_onsets = [s for s in live.signatures if s.sig_type == SignatureType.ONSET]

        candidate_offsets = set([0])

        # Generate candidate offsets from onset pairs
        for ref_sig in ref_onsets[:10]:  # Limit for speed
            for live_sig in live_onsets[:10]:
                offset = ref_sig.time_ms - live_sig.time_ms
                if abs(offset) <= search_range_ms:
                    candidate_offsets.add(offset)

        # Also try offsets from silence transitions
        ref_silence = [s for s in reference.signatures if s.sig_type in [SignatureType.SILENCE_START, SignatureType.SILENCE_END]]
        live_silence = [s for s in live.signatures if s.sig_type in [SignatureType.SILENCE_START, SignatureType.SILENCE_END]]

        for ref_sig in ref_silence[:10]:
            for live_sig in live_silence[:10]:
                if ref_sig.sig_type == live_sig.sig_type:
                    offset = ref_sig.time_ms - live_sig.time_ms
                    if abs(offset) <= search_range_ms:
                        candidate_offsets.add(offset)

        # Score each candidate offset
        for offset in candidate_offsets:
            score = self._score_alignment(reference, live, offset)
            if score > best_score:
                best_score = score
                best_offset = offset

        # Check if we have enough confidence
        if best_score < self.min_matches:
            return None

        # Confidence based on score relative to signature count
        max_possible = min(len(reference.signatures), len(live.signatures))
        confidence = min(1.0, best_score / max(max_possible * 0.5, 1))

        return (best_offset, confidence)

    def _score_alignment(self,
                         reference: MicrosignatureSequence,
                         live: MicrosignatureSequence,
                         offset_ms: int) -> float:
        """
        Score how well two sequences align at a given offset.
        """
        score = 0.0
        matched_live = set()

        for ref_sig in reference.signatures:
            adjusted_time = ref_sig.time_ms - offset_ms

            # Find matching signature in live
            for i, live_sig in enumerate(live.signatures):
                if i in matched_live:
                    continue

                # Must be same type
                if live_sig.sig_type != ref_sig.sig_type:
                    continue

                # Must be within match window
                time_diff = abs(live_sig.time_ms - adjusted_time)
                if time_diff <= self.match_window_ms:
                    # Score based on type weight and time precision
                    weight = self.type_weights.get(ref_sig.sig_type, 1.0)
                    precision = 1.0 - (time_diff / self.match_window_ms)
                    strength = (ref_sig.strength + live_sig.strength) / 2

                    score += weight * precision * strength
                    matched_live.add(i)
                    break

        return score

    def verify_sync(self,
                    reference: MicrosignatureSequence,
                    live: MicrosignatureSequence,
                    expected_offset_ms: int,
                    tolerance_ms: int = 200) -> Tuple[bool, float]:
        """
        Verify that sync is still accurate.

        Args:
            reference: Reference signatures
            live: Live signatures
            expected_offset_ms: Current sync offset
            tolerance_ms: How much drift is acceptable

        Returns:
            (is_valid, actual_offset) - whether sync is still good
        """
        result = self.find_offset(reference, live, search_range_ms=tolerance_ms * 2)

        if result is None:
            return (True, expected_offset_ms)  # No data, assume still valid

        actual_offset, confidence = result
        drift = abs(actual_offset - expected_offset_ms)

        if drift <= tolerance_ms and confidence > 0.5:
            return (True, actual_offset)
        elif confidence < 0.3:
            return (True, expected_offset_ms)  # Low confidence, keep current
        else:
            return (False, actual_offset)


# Convenience functions
def create_extractor(sample_rate: int = 22050) -> MicrosignatureExtractor:
    """Create a microsignature extractor"""
    return MicrosignatureExtractor(sample_rate)


def create_matcher() -> MicrosignatureMatcher:
    """Create a microsignature matcher"""
    return MicrosignatureMatcher()
