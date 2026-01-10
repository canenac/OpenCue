"""Check what audio is being captured"""
import numpy as np
import soundcard as sc
import time

print("=== Audio Device Check ===")
print()

# List all speakers
print("All speakers:")
for spk in sc.all_speakers():
    print(f"  - {spk.name} (id: {spk.id[:20]}...)")

print()
print("Default speaker:", sc.default_speaker().name)

# Try to capture a short sample
print()
print("=== Capturing 2 seconds of audio ===")

speaker = sc.default_speaker()
print(f"Using speaker: {speaker.name}")

# Get loopback
loopback = sc.get_microphone(speaker.id, include_loopback=True)
print(f"Loopback device: {loopback.name}")

# Capture
sample_rate = 16000
with loopback.recorder(samplerate=sample_rate, channels=1) as mic:
    print(f"Recording at {sample_rate}Hz...")
    data = mic.record(numframes=sample_rate * 2)  # 2 seconds

print(f"Captured {len(data)} samples")
print(f"Data shape: {data.shape}")
print(f"Data dtype: {data.dtype}")

# Convert to mono if stereo
if len(data.shape) > 1 and data.shape[1] > 1:
    data = np.mean(data, axis=1)
    print("Converted stereo to mono")

# Analyze
max_amp = np.max(np.abs(data))
print(f"Max amplitude: {max_amp:.4f}")

if max_amp < 0.01:
    print("WARNING: Audio is nearly silent!")
    print("Check if audio is playing and routed to VB-Cable")
else:
    zero_crossings = np.sum(np.abs(np.diff(np.sign(data)))) / 2
    zc_per_second = zero_crossings / 2.0
    print(f"Zero crossings/sec: {zc_per_second:.0f}")

# Try to get the actual native sample rate
print()
print("=== Checking native sample rate ===")
try:
    # Capture at 48000 and compare
    with loopback.recorder(samplerate=48000, channels=1) as mic:
        data_48k = mic.record(numframes=48000 * 2)

    print(f"48kHz capture: {len(data_48k)} samples for 2 sec")
    print(f"16kHz capture: {len(data)} samples for 2 sec")

    # If soundcard properly resamples, the content should be similar
    # But timing will be different
    max_amp_48k = np.max(np.abs(data_48k))
    print(f"48kHz max amplitude: {max_amp_48k:.4f}")

except Exception as e:
    print(f"Error with 48kHz capture: {e}")
