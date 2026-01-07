# .opencue File Format Specification v2.0

## Overview

The `.opencue` format defines content-aware overlay cues synchronized via audio fingerprinting.
This enables accurate filtering regardless of streaming platform, ads, or subtitle settings.

## File Structure

```json
{
  "version": "2.0",
  "content": {
    "title": "Movie Title",
    "year": 2024,
    "duration_ms": 7200000,
    "imdb_id": "tt1234567",
    "content_hash": "sha256:abc123..."
  },
  "fingerprints": {
    "algorithm": "chromaprint",
    "interval_ms": 5000,
    "markers": [
      {"time_ms": 0, "hash": "AQAA..."},
      {"time_ms": 5000, "hash": "AQAB..."},
      {"time_ms": 10000, "hash": "AQAC..."}
    ]
  },
  "cues": [
    {
      "id": "cue_001",
      "start_ms": 45230,
      "end_ms": 45890,
      "action": "mute",
      "category": "language.profanity.severe",
      "word": "f**k",
      "confidence": 1.0
    },
    {
      "id": "cue_002",
      "start_ms": 123400,
      "end_ms": 124100,
      "action": "mute",
      "category": "language.profanity.moderate",
      "word": "sh*t",
      "confidence": 1.0
    },
    {
      "id": "cue_003",
      "start_ms": 234500,
      "end_ms": 237800,
      "action": "blur",
      "category": "visual.nudity",
      "region": {"x": 0.2, "y": 0.3, "w": 0.4, "h": 0.5},
      "confidence": 0.95
    }
  ],
  "metadata": {
    "created": "2024-01-15T10:30:00Z",
    "creator": "opencue-generator v1.0",
    "source": "manual",
    "verified": true
  }
}
```

## Fingerprint Section

### Algorithm
- `chromaprint` - Industry standard, used by MusicBrainz/AcoustID
- Compact representation (~100 bytes per fingerprint)
- Robust to compression, minor audio variations

### Interval
- Default: 5000ms (every 5 seconds)
- Trade-off: More frequent = faster sync, larger file
- Recommended range: 3000-10000ms

### Markers
- `time_ms`: Position in content timeline (milliseconds)
- `hash`: Base64-encoded Chromaprint fingerprint

## Cue Section

### Actions
| Action | Description |
|--------|-------------|
| `mute` | Silence audio for duration |
| `blur` | Apply visual blur to region |
| `skip` | Skip segment entirely |
| `warn` | Display content warning |

### Categories
```
language.profanity.severe    - F-word, etc.
language.profanity.moderate  - S-word, etc.
language.profanity.mild      - Damn, hell, etc.
language.blasphemy           - Religious exclamations
language.slurs               - Slurs and hate speech
visual.nudity                - Nudity
visual.violence.gore         - Graphic violence
visual.violence.mild         - Fighting, etc.
substances.drugs             - Drug use
substances.alcohol           - Alcohol use
themes.disturbing            - Disturbing content
```

## Sync Process

```
1. Load .opencue file for content
2. Start audio capture (system audio or mic)
3. Compute fingerprint of captured audio
4. Match against markers to find position
5. Calculate offset: actual_position = matched_time + drift
6. Apply cues at (cue_time - offset)
7. Continuously refine offset with new matches
8. Handle sync loss (ads): pause cues, wait for re-match
```

## Sync States

```
SYNCING     - Looking for initial match
SYNCED      - Position locked, applying cues
DRIFTING    - Minor drift detected, adjusting
LOST        - No match (ads, different content), waiting
```

## File Naming Convention

```
{imdb_id}_{title_slug}.opencue

Examples:
tt0111161_the_shawshank_redemption.opencue
tt0468569_the_dark_knight.opencue
```

## Distribution

Cue files can be:
1. Bundled with the extension
2. Downloaded from community repositories
3. Generated locally with the cue generator tool
4. Shared peer-to-peer

## Legal Notes

- Cue files contain NO copyrighted content
- Audio fingerprints are mathematical hashes only
- Timestamps and metadata are factual information
- Distribution is legal under fair use principles
