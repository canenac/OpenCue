"""
OpenCue - Whisper Transcription Module

Uses faster-whisper for word-level timestamps from audio.
Provides precise timing for profanity detection.
"""

import os
import tempfile
import wave
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple
from pathlib import Path


@dataclass
class WordTiming:
    """A single word with precise timing"""
    word: str
    start_ms: int
    end_ms: int
    confidence: float

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass
class TranscriptionResult:
    """Full transcription with word-level timing"""
    text: str
    words: List[WordTiming]
    language: str
    duration_ms: int


# Check for faster-whisper
try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("[OpenCue] faster-whisper not installed. Run: pip install faster-whisper")


class WhisperTranscriber:
    """Transcribe audio with word-level timestamps"""

    def __init__(self, model_size: str = "base", device: str = "auto"):
        """
        Initialize Whisper model.

        Args:
            model_size: "tiny", "base", "small", "medium", "large-v2"
                       Larger = more accurate but slower
            device: "auto", "cpu", or "cuda"
        """
        self.model_size = model_size
        self.device = device
        self._model: Optional[WhisperModel] = None

    def _ensure_model(self):
        """Lazy-load the model"""
        if self._model is None:
            if not WHISPER_AVAILABLE:
                raise RuntimeError("faster-whisper not installed")

            print(f"[OpenCue] Loading Whisper model: {self.model_size}...")

            # Determine compute type based on device
            if self.device == "auto":
                try:
                    import torch
                    if torch.cuda.is_available():
                        self.device = "cuda"
                        compute_type = "float16"
                    else:
                        self.device = "cpu"
                        compute_type = "int8"
                except ImportError:
                    self.device = "cpu"
                    compute_type = "int8"
            elif self.device == "cuda":
                compute_type = "float16"
            else:
                compute_type = "int8"

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=compute_type
            )
            print(f"[OpenCue] Whisper model loaded ({self.device}, {compute_type})")

    def transcribe_file(
        self,
        audio_path: str,
        language: str = "en",
        playback_speed: float = 1.0
    ) -> TranscriptionResult:
        """
        Transcribe an audio file with word-level timestamps.

        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)
            language: Language code (e.g., "en" for English)
            playback_speed: If audio was recorded at 2x, set to 2.0 to adjust timestamps

        Returns:
            TranscriptionResult with word timings
        """
        self._ensure_model()

        print(f"[OpenCue] Transcribing: {audio_path}")

        segments, info = self._model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=True,  # Filter out silence
        )

        words = []
        full_text_parts = []

        for segment in segments:
            full_text_parts.append(segment.text)

            if segment.words:
                for word_info in segment.words:
                    # Adjust for playback speed
                    start_ms = int(word_info.start * 1000 * playback_speed)
                    end_ms = int(word_info.end * 1000 * playback_speed)

                    words.append(WordTiming(
                        word=word_info.word.strip(),
                        start_ms=start_ms,
                        end_ms=end_ms,
                        confidence=word_info.probability
                    ))

        full_text = " ".join(full_text_parts)
        duration_ms = int(info.duration * 1000 * playback_speed)

        print(f"[OpenCue] Transcribed {len(words)} words in {duration_ms}ms")

        return TranscriptionResult(
            text=full_text,
            words=words,
            language=info.language,
            duration_ms=duration_ms
        )

    def transcribe_audio_data(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        language: str = "en",
        playback_speed: float = 1.0
    ) -> TranscriptionResult:
        """
        Transcribe raw audio data.

        Args:
            audio_data: NumPy array of audio samples (float32, mono)
            sample_rate: Sample rate of the audio
            language: Language code
            playback_speed: Playback speed multiplier for timestamp adjustment

        Returns:
            TranscriptionResult with word timings
        """
        # Save to temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            # Ensure audio is in correct format
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # Normalize if needed
            max_val = np.abs(audio_data).max()
            if max_val > 1.0:
                audio_data = audio_data / max_val

            # Convert to int16 for WAV
            audio_int16 = (audio_data * 32767).astype(np.int16)

            # Write WAV file
            with wave.open(temp_path, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)  # 16-bit
                wav.setframerate(sample_rate)
                wav.writeframes(audio_int16.tobytes())

            # Transcribe
            return self.transcribe_file(temp_path, language, playback_speed)

        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except Exception:
                pass


def find_profanity_timestamps(
    transcription: TranscriptionResult,
    profanity_list: List[str]
) -> List[WordTiming]:
    """
    Find profanity words in transcription with their exact timestamps.

    Args:
        transcription: Whisper transcription result
        profanity_list: List of profanity words to detect

    Returns:
        List of WordTiming for detected profanity
    """
    profanity_set = set(w.lower() for w in profanity_list)
    detected = []

    for word in transcription.words:
        # Clean word (remove punctuation)
        clean_word = ''.join(c for c in word.word.lower() if c.isalnum())

        if clean_word in profanity_set:
            detected.append(word)
            print(f"[OpenCue] Found '{word.word}' at {word.start_ms}-{word.end_ms}ms")

    return detected


# Singleton instance
_transcriber: Optional[WhisperTranscriber] = None


def get_transcriber(model_size: str = "base") -> WhisperTranscriber:
    """Get or create the Whisper transcriber"""
    global _transcriber
    if _transcriber is None or _transcriber.model_size != model_size:
        _transcriber = WhisperTranscriber(model_size=model_size)
    return _transcriber


def check_whisper_available() -> dict:
    """Check if Whisper is available and return status"""
    return {
        "available": WHISPER_AVAILABLE,
        "install_command": "pip install faster-whisper" if not WHISPER_AVAILABLE else None,
        "models": ["tiny", "base", "small", "medium", "large-v2"] if WHISPER_AVAILABLE else []
    }
