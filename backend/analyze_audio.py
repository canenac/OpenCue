"""Analyze captured audio file for debugging Whisper issues"""
import wave
import numpy as np
import sys

audio_path = r'D:\opencue\backend\cues\History of Swear WordsFk.wav'

print(f"Analyzing: {audio_path}")
print("=" * 50)

try:
    with wave.open(audio_path, 'rb') as wav:
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        n_frames = wav.getnframes()
        duration = n_frames / sample_rate

        audio_bytes = wav.readframes(n_frames)
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32767

    print(f"Sample rate: {sample_rate} Hz")
    print(f"Channels: {channels}")
    print(f"Sample width: {sample_width} bytes ({sample_width*8} bits)")
    print(f"Duration: {duration:.2f} seconds")
    print(f"Total samples: {len(audio)}")
    print(f"Max amplitude: {np.max(np.abs(audio)):.4f}")

    # Analyze zero crossings
    zero_crossings = np.sum(np.abs(np.diff(np.sign(audio)))) / 2
    zc_per_second = zero_crossings / duration
    print(f"\nZero crossings/sec: {zc_per_second:.0f}")
    print("(Normal speech: 50-200/sec, Music: 1000-3000/sec)")

    # Try direct transcription with resampled audio
    print("\n" + "=" * 50)
    print("Attempting transcription with native rate...")

    from faster_whisper import WhisperModel
    import tempfile
    import os

    # Check if this might be 48kHz audio saved as 16kHz
    # If so, the effective playback would be 3x speed
    if zc_per_second > 500:
        print(f"\nHigh zero-crossing rate detected!")
        print("Possible sample rate mismatch - audio may be 48kHz saved as 16kHz")

        # Try reinterpreting as 48kHz
        print("\nTest 1: Treating audio as 48kHz (3x slower playback)")

        temp_path = tempfile.mktemp(suffix='.wav')
        with wave.open(temp_path, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(48000)  # Re-interpret as 48kHz
            wav.writeframes((audio * 32767).astype(np.int16).tobytes())

        print(f"Saved re-interpreted file as 48kHz: {temp_path}")
        print("New duration would be:", len(audio) / 48000, "seconds")

        model = WhisperModel("base", device="cuda", compute_type="float16")
        segments, info = model.transcribe(temp_path, language="en", word_timestamps=True)

        words = []
        for seg in segments:
            print(f"Segment: {seg.text[:100]}...")
            if seg.words:
                for w in seg.words[:5]:
                    words.append(w.word)

        print(f"\nFound {len(words)} words (first 5: {words[:5]})")
        os.unlink(temp_path)

        if not words:
            # Try 44.1kHz
            print("\nTest 2: Treating audio as 44.1kHz")
            temp_path = tempfile.mktemp(suffix='.wav')
            with wave.open(temp_path, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(44100)
                wav.writeframes((audio * 32767).astype(np.int16).tobytes())

            segments, info = model.transcribe(temp_path, language="en", word_timestamps=True)
            words = []
            for seg in segments:
                print(f"Segment: {seg.text[:100]}...")
                if seg.words:
                    for w in seg.words[:5]:
                        words.append(w.word)
            print(f"\nFound {len(words)} words")
            os.unlink(temp_path)

    else:
        # Try direct transcription
        model = WhisperModel("base", device="cuda", compute_type="float16")
        segments, info = model.transcribe(audio_path, language="en", word_timestamps=True)

        for seg in segments:
            print(f"Segment: {seg.text}")

except FileNotFoundError:
    print(f"ERROR: File not found: {audio_path}")
    print("\nAvailable files in cues directory:")
    import os
    cues_dir = r'D:\opencue\backend\cues'
    if os.path.exists(cues_dir):
        for f in os.listdir(cues_dir):
            print(f"  {f}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
