"""Test if soundcard properly resamples audio"""
import numpy as np
import soundcard as sc
import wave
import tempfile
import os

print("=== Testing soundcard resampling ===")

# Get VB-Cable
vb_cable = None
for spk in sc.all_speakers():
    if 'cable' in spk.name.lower() and 'input' in spk.name.lower():
        vb_cable = spk
        break

if not vb_cable:
    print("VB-Cable not found!")
    exit(1)

print(f"Using VB-Cable: {vb_cable.name}")

# Set as default for test
# (This won't actually change system setting, just use this device for capture)

loopback = sc.get_microphone(vb_cable.id, include_loopback=True)
print(f"Loopback: {loopback.name}")

print()
print("Capturing 3 seconds at different sample rates...")
print("Play some audio/video with clear speech during this time!")
print()

import time
time.sleep(1)  # Give user time to start audio

results = {}

for rate in [48000, 44100, 16000]:
    with loopback.recorder(samplerate=rate, channels=1) as mic:
        data = mic.record(numframes=rate * 3)  # 3 seconds worth

    if len(data.shape) > 1:
        data = data[:, 0]

    results[rate] = {
        'samples': len(data),
        'expected': rate * 3,
        'max_amp': np.max(np.abs(data)),
        'data': data
    }

    print(f"{rate}Hz: {len(data)} samples (expected {rate*3}), max amp: {np.max(np.abs(data)):.4f}")

# The key insight: if soundcard delivers native rate samples regardless of requested rate,
# all three captures would have the SAME max amplitude pattern but different sample counts
# that don't match the expected counts

print()
print("=== Analysis ===")

# Check if sample counts match expected
for rate, r in results.items():
    ratio = r['samples'] / r['expected']
    print(f"{rate}Hz: Got {ratio:.2%} of expected samples")

# If the audio was captured properly at 16kHz, the content should sound correct
# Let's save the 16kHz capture and also save a "fixed" version if needed
data_16k = results[16000]['data']
data_48k = results[48000]['data']

# Save 16kHz version as-is
with wave.open('test_16k_native.wav', 'wb') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    wav.writeframes((data_16k * 32767).astype(np.int16).tobytes())

# If soundcard isn't resampling, the 16kHz request might actually be 48kHz data
# Let's see by comparing zero-crossing rates
zc_16k = np.sum(np.abs(np.diff(np.sign(data_16k)))) / 2 / 3
zc_48k = np.sum(np.abs(np.diff(np.sign(data_48k)))) / 2 / 3

print()
print(f"Zero crossings per second:")
print(f"  16kHz capture: {zc_16k:.0f}/sec")
print(f"  48kHz capture: {zc_48k:.0f}/sec")

if zc_16k > 500 and zc_48k < 300:
    print()
    print("!! ISSUE DETECTED !!")
    print("The 16kHz capture has more zero crossings than 48kHz")
    print("This suggests soundcard is not resampling - it's delivering")
    print("48kHz samples but labeling them as 16kHz, causing 3x speedup!")

    # Save a fixed version by treating 16kHz data as 48kHz
    print()
    print("Creating fixed version by reinterpreting sample rate...")

    # Method 1: Save the 16kHz samples with 48kHz rate header
    # This will play back at correct speed but duration will be 1/3
    with wave.open('test_16k_as_48k.wav', 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)  # Re-interpret as 48kHz
        wav.writeframes((data_16k * 32767).astype(np.int16).tobytes())

    print("Saved test_16k_as_48k.wav - this should sound correct if theory is right")

print()
print("Files saved in current directory. Test with Whisper or audio player.")
