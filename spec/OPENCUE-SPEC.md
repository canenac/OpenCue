# OpenCue File Format Specification

**Version:** 1.0
**Status:** Draft
**Last Updated:** 2025-01-06

---

## Overview

The `.opencue` file format is an open specification for storing cue-based playback overlay data. It enables users to create lightweight, portable overlays that can mute audio or apply visual overlays during video playback without modifying the underlying media file.

This specification is designed for lawful personal use under the Family Movie Act of 2005.

---

## File Extension

`.opencue`

Files are UTF-8 encoded JSON documents.

---

## Schema

### Root Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `opencue_version` | string | Yes | Specification version (e.g., "1.0") |
| `content` | object | Yes | Content identification |
| `metadata` | object | Yes | File metadata |
| `cues` | array | Yes | Array of cue events |

### Content Object

Identifies the video content this cue file applies to.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | Yes | Human-readable title |
| `source` | string | Yes | Streaming source (e.g., "netflix", "disney", "amazon") |
| `source_id` | string | Yes | Source-specific content identifier |
| `duration_ms` | integer | Yes | Total content duration in milliseconds |
| `fingerprint` | string | No | Content fingerprint for verification (sha256) |
| `season` | integer | No | Season number (for series) |
| `episode` | integer | No | Episode number (for series) |

### Metadata Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `created` | string | Yes | ISO 8601 timestamp of creation |
| `created_by` | string | Yes | Creator identifier ("user", "community", "auto") |
| `tool_version` | string | Yes | OpenCue tool version used to create |
| `description` | string | No | Human-readable description |
| `language` | string | No | Primary language of cue analysis (ISO 639-1) |

### Cue Object

Each cue represents a single overlay event.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique cue identifier (e.g., "cue_001") |
| `start_ms` | integer | Yes | Start time in milliseconds |
| `end_ms` | integer | Yes | End time in milliseconds |
| `action` | string | Yes | Overlay action: "mute", "blur", "skip" |
| `category` | string | Yes | Hierarchical category (e.g., "language.profanity.severe") |
| `confidence` | number | No | Detection confidence (0.0 to 1.0) |
| `source` | string | No | Detection source: "subtitle_analysis", "llm_context", "manual" |
| `note` | string | No | Human-readable note |
| `intensity` | string | No | For blur action: "light", "medium", "heavy" |

---

## Overlay Actions

### mute

Mutes audio during the specified time window.

```json
{
  "id": "cue_001",
  "start_ms": 123456,
  "end_ms": 124500,
  "action": "mute",
  "category": "language.profanity.severe"
}
```

### blur

Applies visual blur overlay during the specified time window.

```json
{
  "id": "cue_002",
  "start_ms": 567890,
  "end_ms": 572000,
  "action": "blur",
  "intensity": "medium",
  "category": "violence.graphic"
}
```

### skip

Skips the specified time window (jumps playback forward).

```json
{
  "id": "cue_003",
  "start_ms": 890000,
  "end_ms": 920000,
  "action": "skip",
  "category": "sexual.explicit"
}
```

---

## Category Taxonomy

Categories use dot-notation hierarchy.

### Language Categories

- `language.profanity.severe` - F-word, etc.
- `language.profanity.moderate` - Damn, hell, etc.
- `language.profanity.mild` - Crap, etc.
- `language.blasphemy.exclamatory` - OMG, etc.
- `language.slurs.racial`
- `language.slurs.other`
- `language.sexual.explicit`
- `language.sexual.innuendo`

### Violence Categories

- `violence.graphic`
- `violence.threats`
- `violence.described`

### Sexual Categories

- `sexual.nudity`
- `sexual.explicit`
- `sexual.suggestive`

### Substance Categories

- `substance.drugs`
- `substance.alcohol`
- `substance.smoking`

### Thematic Categories

- `thematic.suicide`
- `thematic.abuse`
- `thematic.mature`

---

## Example File

```json
{
  "opencue_version": "1.0",
  "content": {
    "title": "Example Movie",
    "source": "netflix",
    "source_id": "81234567",
    "duration_ms": 7200000
  },
  "metadata": {
    "created": "2025-01-06T12:00:00Z",
    "created_by": "user",
    "tool_version": "1.0.0",
    "description": "Family viewing overlay"
  },
  "cues": [
    {
      "id": "cue_001",
      "start_ms": 123456,
      "end_ms": 124500,
      "action": "mute",
      "category": "language.profanity.severe",
      "confidence": 0.95,
      "source": "subtitle_analysis",
      "note": "Detected profanity in dialogue"
    },
    {
      "id": "cue_002",
      "start_ms": 567890,
      "end_ms": 572000,
      "action": "blur",
      "intensity": "medium",
      "category": "violence.described",
      "confidence": 0.78,
      "source": "llm_context",
      "note": "Violence described in dialogue"
    }
  ]
}
```

---

## Validation Rules

1. `start_ms` must be less than `end_ms`
2. `start_ms` must be >= 0
3. `end_ms` must not exceed `content.duration_ms`
4. `confidence` must be between 0.0 and 1.0
5. `action` must be one of: "mute", "blur", "skip"
6. `intensity` is required when `action` is "blur"
7. `id` must be unique within the cues array

---

## Security Considerations

- `.opencue` files contain only timing data, not content
- Files may be encrypted for machine-bound use (see encryption spec)
- No DRM circumvention - works with legitimate playback only
- No content redistribution - cues are meaningless without source

---

## Legal Notice

This specification is designed for lawful personal use under the Family Movie Act of 2005. Users are responsible for ensuring their use complies with applicable laws and terms of service.

---

## Versioning

- **1.0** - Initial specification (current)

Future versions will maintain backward compatibility where possible.
