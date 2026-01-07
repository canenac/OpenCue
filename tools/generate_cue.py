#!/usr/bin/env python3
"""
OpenCue - Cue File Generator

Generates .opencue files from video content by:
1. Extracting audio and generating fingerprint markers
2. Extracting subtitles and detecting profanity
3. Allowing manual cue additions

Requirements:
- ffmpeg (for audio extraction)
- chromaprint/fpcalc (for fingerprinting)

Usage:
    python generate_cue.py video.mp4 -o output.opencue
    python generate_cue.py video.mp4 --subtitles subs.srt -o output.opencue
"""

import argparse
import json
import subprocess
import tempfile
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import re

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    from profanity.detector import detect_profanity
    PROFANITY_DETECTOR_AVAILABLE = True
except ImportError:
    PROFANITY_DETECTOR_AVAILABLE = False
    print("Warning: Profanity detector not available")


def run_command(cmd: List[str], capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return result"""
    return subprocess.run(cmd, capture_output=capture_output, text=True)


def check_dependencies() -> Dict[str, bool]:
    """Check for required dependencies"""
    deps = {}

    # Check ffmpeg
    result = run_command(["ffmpeg", "-version"])
    deps["ffmpeg"] = result.returncode == 0

    # Check fpcalc (chromaprint)
    result = run_command(["fpcalc", "-version"])
    deps["fpcalc"] = result.returncode == 0

    return deps


def extract_audio(video_path: str, output_path: str, sample_rate: int = 22050) -> bool:
    """Extract audio from video using ffmpeg"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",                          # No video
        "-acodec", "pcm_s16le",        # PCM format
        "-ar", str(sample_rate),        # Sample rate
        "-ac", "1",                      # Mono
        output_path
    ]

    result = run_command(cmd)
    return result.returncode == 0


def get_video_duration(video_path: str) -> Optional[int]:
    """Get video duration in milliseconds"""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        video_path
    ]

    result = run_command(cmd)
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            duration_sec = float(data["format"]["duration"])
            return int(duration_sec * 1000)
        except:
            pass
    return None


def generate_fingerprints(audio_path: str, interval_ms: int = 5000) -> List[Dict]:
    """Generate fingerprint markers at regular intervals"""
    markers = []

    # Get audio duration
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "json", audio_path]
    result = run_command(cmd)

    try:
        duration_sec = float(json.loads(result.stdout)["format"]["duration"])
    except:
        print("Error: Could not determine audio duration")
        return markers

    duration_ms = int(duration_sec * 1000)
    interval_sec = interval_ms / 1000

    print(f"Generating fingerprints every {interval_sec}s for {duration_sec:.1f}s of audio...")

    time_ms = 0
    while time_ms < duration_ms:
        # Use fpcalc to generate fingerprint for segment
        start_sec = time_ms / 1000

        cmd = [
            "fpcalc",
            "-raw",                          # Raw fingerprint output
            "-ts", str(start_sec),           # Start time
            "-length", str(interval_sec),    # Duration
            audio_path
        ]

        result = run_command(cmd)

        if result.returncode == 0:
            # Parse fpcalc output
            for line in result.stdout.strip().split('\n'):
                if line.startswith('FINGERPRINT='):
                    fp_data = line.split('=', 1)[1]
                    markers.append({
                        "time_ms": time_ms,
                        "hash": fp_data
                    })
                    break

        time_ms += interval_ms

        # Progress
        progress = (time_ms / duration_ms) * 100
        print(f"\r  Progress: {progress:.1f}%", end="", flush=True)

    print()  # Newline after progress
    return markers


def parse_srt(srt_path: str) -> List[Dict]:
    """Parse SRT subtitle file"""
    subtitles = []

    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split into subtitle blocks
    blocks = re.split(r'\n\n+', content.strip())

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            # Parse timestamp line
            time_line = lines[1]
            match = re.match(
                r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})',
                time_line
            )

            if match:
                # Start time
                start_ms = (
                    int(match.group(1)) * 3600000 +
                    int(match.group(2)) * 60000 +
                    int(match.group(3)) * 1000 +
                    int(match.group(4))
                )

                # End time
                end_ms = (
                    int(match.group(5)) * 3600000 +
                    int(match.group(6)) * 60000 +
                    int(match.group(7)) * 1000 +
                    int(match.group(8))
                )

                # Text (remaining lines)
                text = ' '.join(lines[2:])
                # Remove HTML tags
                text = re.sub(r'<[^>]+>', '', text)

                subtitles.append({
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": text
                })

    return subtitles


def detect_profanity_in_subtitles(subtitles: List[Dict]) -> List[Dict]:
    """Detect profanity in subtitles and generate cues"""
    cues = []
    cue_id = 1

    if not PROFANITY_DETECTOR_AVAILABLE:
        print("Warning: Profanity detector not available, skipping auto-detection")
        return cues

    for sub in subtitles:
        detections = detect_profanity(sub["text"])

        for detection in detections:
            cues.append({
                "id": f"cue_{cue_id:04d}",
                "start_ms": sub["start_ms"] - 100,  # Small padding
                "end_ms": sub["end_ms"] + 100,
                "action": "mute",
                "category": detection["category"],
                "word": detection["display"],
                "confidence": detection["confidence"]
            })
            cue_id += 1

    return cues


def generate_cue_file(
    video_path: str,
    output_path: str,
    subtitle_path: Optional[str] = None,
    title: Optional[str] = None,
    fingerprint_interval: int = 5000,
    skip_fingerprints: bool = False
) -> bool:
    """Generate a complete .opencue file"""

    video_path = os.path.abspath(video_path)

    if not os.path.exists(video_path):
        print(f"Error: Video file not found: {video_path}")
        return False

    # Check dependencies
    deps = check_dependencies()
    if not deps["ffmpeg"]:
        print("Error: ffmpeg not found. Please install ffmpeg.")
        return False
    if not deps["fpcalc"] and not skip_fingerprints:
        print("Warning: fpcalc not found. Install chromaprint for fingerprinting.")
        print("Continuing without fingerprints...")
        skip_fingerprints = True

    # Get video info
    duration_ms = get_video_duration(video_path)
    if not duration_ms:
        print("Error: Could not determine video duration")
        return False

    print(f"Video duration: {duration_ms / 1000:.1f}s")

    # Extract title from filename if not provided
    if not title:
        title = Path(video_path).stem

    # Initialize cue file structure
    cue_data = {
        "version": "2.0",
        "content": {
            "title": title,
            "duration_ms": duration_ms,
            "source_file": Path(video_path).name
        },
        "fingerprints": {
            "algorithm": "chromaprint",
            "interval_ms": fingerprint_interval,
            "markers": []
        },
        "cues": [],
        "metadata": {
            "created": datetime.now().isoformat(),
            "creator": "opencue-generator v1.0",
            "source": "auto"
        }
    }

    # Generate fingerprints
    if not skip_fingerprints:
        print("\nExtracting audio...")
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_audio = tmp.name

        try:
            if extract_audio(video_path, tmp_audio):
                print("Generating fingerprints...")
                markers = generate_fingerprints(tmp_audio, fingerprint_interval)
                cue_data["fingerprints"]["markers"] = markers
                print(f"Generated {len(markers)} fingerprint markers")
            else:
                print("Warning: Audio extraction failed")
        finally:
            if os.path.exists(tmp_audio):
                os.remove(tmp_audio)

    # Process subtitles for profanity detection
    if subtitle_path:
        if not os.path.exists(subtitle_path):
            print(f"Warning: Subtitle file not found: {subtitle_path}")
        else:
            print("\nProcessing subtitles for profanity...")
            subtitles = parse_srt(subtitle_path)
            print(f"Found {len(subtitles)} subtitle entries")

            cues = detect_profanity_in_subtitles(subtitles)
            cue_data["cues"] = cues
            print(f"Detected {len(cues)} profanity instances")

    # Save cue file
    output_path = os.path.abspath(output_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cue_data, f, indent=2)

    print(f"\nCue file saved: {output_path}")
    print(f"  Fingerprints: {len(cue_data['fingerprints']['markers'])}")
    print(f"  Cues: {len(cue_data['cues'])}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate .opencue files from video content"
    )
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("-o", "--output", help="Output .opencue file path")
    parser.add_argument("-s", "--subtitles", help="Path to SRT subtitle file")
    parser.add_argument("-t", "--title", help="Content title")
    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=5000,
        help="Fingerprint interval in ms (default: 5000)"
    )
    parser.add_argument(
        "--skip-fingerprints",
        action="store_true",
        help="Skip fingerprint generation"
    )

    args = parser.parse_args()

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = Path(args.video).stem + ".opencue"

    success = generate_cue_file(
        video_path=args.video,
        output_path=output_path,
        subtitle_path=args.subtitles,
        title=args.title,
        fingerprint_interval=args.interval,
        skip_fingerprints=args.skip_fingerprints
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
