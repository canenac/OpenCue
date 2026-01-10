# OpenCue Profile Specification v1.0

## Overview

A **profile** defines what content to filter and how. Users can:
- Select from preset profiles
- Create and save custom profiles
- Modify presets as starting points

Taxonomy blended from [VidAngel](https://help.vidangel.com/hc/en-us/articles/360055496752-What-Filters-options-do-you-provide) and [ClearPlay](https://help.clearplay.com/docs/adjusting-filtering-settings).

---

## Unified Filter Taxonomy

### Category 1: LANGUAGE (Audio)

| Filter | Description | Source | Action |
|--------|-------------|--------|--------|
| `lang.profanity.extreme` | F-word, C-word, MF-word | Both | mute |
| `lang.profanity.strong` | S-word, B-word, A-word | Both | mute |
| `lang.profanity.mild` | Damn, hell, crap | Both | mute |
| `lang.blasphemy` | GD, JC as exclamations | Both | mute |
| `lang.slurs` | Racial, ethnic, homophobic | Both | mute |
| `lang.crude` | Bathroom humor, insults (stupid, idiot) | VidAngel | mute |
| `lang.sexual.explicit` | Graphic sexual terms | Both | mute |
| `lang.sexual.innuendo` | Suggestive but not explicit | VidAngel | mute |

### Category 2: NUDITY & SEX (Visual)

| Filter | Description | Source | Action |
|--------|-------------|--------|--------|
| `sex.nudity.full` | Full frontal/rear nudity | Both | blur |
| `sex.nudity.partial` | Partial nudity, topless | Both | blur |
| `sex.nudity.rear` | Rear nudity, buttocks | VidAngel | blur |
| `sex.scene.explicit` | Sex acts shown | Both | skip |
| `sex.scene.implied` | Sex implied, not shown | Both | blur |
| `sex.assault` | Sexual violence | VidAngel | skip |
| `sex.kissing.hetero` | Heterosexual passionate kissing | VidAngel | skip |
| `sex.kissing.lgbtq` | LGBTQ+ kissing/romance | VidAngel | skip |
| `sex.immodesty` | Revealing clothing, underwear | VidAngel | blur |

### Category 3: VIOLENCE (Visual)

| Filter | Description | Source | Action |
|--------|-------------|--------|--------|
| `viol.gore` | Blood, dismemberment, graphic injury | Both | skip |
| `viol.brutal` | Torture, prolonged violence | ClearPlay | skip |
| `viol.graphic` | Clear on-screen violence with impact | Both | skip |
| `viol.moderate` | Fighting, weapons, no blood | ClearPlay | blur |
| `viol.disturbing` | Horror imagery, jump scares | VidAngel | skip |
| `viol.domestic` | Domestic violence, abuse | New | skip |
| `viol.suicide` | Suicide scenes, attempts | VidAngel | skip |
| `viol.selfharm` | Self-harm, cutting | VidAngel | skip |

### Category 4: SUBSTANCES

| Filter | Description | Source | Action |
|--------|-------------|--------|--------|
| `subs.drugs.use` | Illegal drug use on screen | Both | skip |
| `subs.drugs.reference` | Drug discussion, dealing | VidAngel | skip |
| `subs.alcohol.use` | Drinking on screen | Both | skip |
| `subs.alcohol.intoxication` | Drunken behavior | VidAngel | skip |
| `subs.smoking` | Tobacco, vaping, marijuana | VidAngel | skip |

### Category 5: THEMATIC

| Filter | Description | Source | Action |
|--------|-------------|--------|--------|
| `theme.lgbtq` | LGBTQ+ themes/storylines | VidAngel | skip |
| `theme.occult` | Witchcraft, demons, séances | VidAngel | skip |
| `theme.taboo` | Incest, bestiality, other taboo | New | skip |
| `theme.political` | Strong political messaging | New | skip |
| `theme.religious` | Religious proselytizing | New | skip |

### Category 6: OTHER

| Filter | Description | Source | Action |
|--------|-------------|--------|--------|
| `other.bodily` | Vomiting, urination, flatulence | VidAngel | skip |
| `other.medical` | Surgery, needles, medical blood | VidAngel | skip |
| `other.gambling` | Gambling scenes | VidAngel | skip |
| `other.spoilers` | Plot spoilers in recaps | New | skip |

### Category 7: PLAYBACK

| Filter | Description | Source | Action |
|--------|-------------|--------|--------|
| `play.intro` | Show intros/theme songs | VidAngel | skip |
| `play.credits` | End credits | VidAngel | skip |
| `play.recap` | "Previously on..." recaps | VidAngel | skip |

---

## Implementation Status

### IMPLEMENTED (Available Now)

These filters are functional and selectable in the UI:

| Filter | Category | Notes |
|--------|----------|-------|
| `lang.profanity.extreme` | Language | F-word, C-word, MF-word |
| `lang.profanity.strong` | Language | S-word, B-word, A-word |
| `lang.profanity.mild` | Language | Damn, hell, crap |
| `lang.blasphemy` | Language | GD, JC exclamations |
| `lang.slurs` | Language | All slur types |

### PLANNED (Greyed Out in UI)

These filters appear in the menu but are **greyed out and unselectable** until implemented:

| Filter | Category | Unlock When |
|--------|----------|-------------|
| `lang.crude` | Language | Milestone 1.3 - wordlist expansion |
| `lang.sexual.*` | Language | Milestone 1.3 - wordlist expansion |
| `sex.*` | Nudity/Sex | Milestone 2.1 - blur overlay implementation |
| `viol.*` | Violence | Milestone 2.1 - blur/skip for video |
| `subs.*` | Substances | Milestone 2.2 - scene detection |
| `theme.*` | Thematic | Milestone 2.2 - scene detection |
| `other.*` | Other | Milestone 2.2 - scene detection |
| `play.*` | Playback | Milestone 2.3 - intro/credits detection |

### UI Display for Unavailable Filters

```
┌─────────────────────────────────────────────┐
│ LANGUAGE FILTERS                            │
│ ☑ Extreme Profanity (F-word, etc.)         │
│ ☑ Strong Profanity (S-word, etc.)          │
│ ☐ Mild Profanity (damn, hell)              │
│ ☑ Blasphemy                                 │
│ ☑ Slurs                                     │
│ ░ Crude Language        [Coming Soon]       │  ← Greyed out
│ ░ Sexual Language       [Coming Soon]       │  ← Greyed out
├─────────────────────────────────────────────┤
│ VISUAL FILTERS                              │
│ ░ Nudity               [Coming Soon]        │  ← Greyed out
│ ░ Sexual Content       [Coming Soon]        │  ← Greyed out
│ ░ Violence             [Coming Soon]        │  ← Greyed out
│                                             │
│ ⓘ Visual filters require video analysis    │
│   capabilities (planned for v0.3)           │
└─────────────────────────────────────────────┘
```

### Code Notes for Future Implementation

```javascript
// In popup.js or settings UI component:
//
// FILTER_AVAILABILITY defines which filters are currently functional.
// When implementing a new filter category:
// 1. Add detection logic to backend (profanity/detector.py or new module)
// 2. Add cue generation in overlay_engine.py
// 3. Add action handler in content.js (mute/blur/skip)
// 4. Update FILTER_AVAILABILITY to enable the filter
// 5. Remove "Coming Soon" badge and greyed-out styling
//
// Example:
// const FILTER_AVAILABILITY = {
//   language: {
//     profanity_extreme: true,   // Implemented
//     profanity_strong: true,    // Implemented
//     profanity_mild: true,      // Implemented
//     blasphemy: true,           // Implemented
//     slurs: true,               // Implemented
//     crude: false,              // TODO: Milestone 1.3
//     sexual_explicit: false,    // TODO: Milestone 1.3
//     sexual_innuendo: false,    // TODO: Milestone 1.3
//   },
//   sex: {
//     nudity_full: false,        // TODO: Milestone 2.1 - requires blur
//     nudity_partial: false,     // TODO: Milestone 2.1 - requires blur
//     // ... all false until blur implemented
//   },
//   violence: {
//     gore: false,               // TODO: Milestone 2.1 - requires skip/blur
//     // ... all false until video filtering implemented
//   },
//   // ... etc
// };
//
// UI should check FILTER_AVAILABILITY[category][filter] before enabling checkbox
```

---

## Profile Structure

```json
{
  "id": "profile-uuid",
  "name": "Family Movie Night",
  "icon": "family",
  "is_custom": false,
  "based_on": "moderate",
  "created": "2024-01-15T10:30:00Z",
  "modified": "2024-01-20T14:22:00Z",

  "language": {
    "profanity_extreme": true,
    "profanity_strong": true,
    "profanity_mild": false,
    "blasphemy": true,
    "slurs": true,
    "crude": false,
    "sexual_explicit": true,
    "sexual_innuendo": false
  },

  "sex": {
    "nudity_full": true,
    "nudity_partial": true,
    "nudity_rear": false,
    "scene_explicit": true,
    "scene_implied": false,
    "assault": true,
    "kissing_hetero": false,
    "kissing_lgbtq": false,
    "immodesty": false
  },

  "violence": {
    "gore": true,
    "brutal": true,
    "graphic": true,
    "moderate": false,
    "disturbing": true,
    "suicide": true,
    "selfharm": true
  },

  "substances": {
    "drugs_use": false,
    "drugs_reference": false,
    "alcohol_use": false,
    "alcohol_intoxication": false,
    "smoking": false
  },

  "thematic": {
    "lgbtq": false,
    "occult": false,
    "taboo": true,
    "political": false,
    "religious": false
  },

  "other": {
    "bodily": false,
    "medical": false,
    "gambling": false,
    "spoilers": false
  },

  "playback": {
    "intro": false,
    "credits": false,
    "recap": false
  },

  "custom_words": []
}
```

---

## Preset Profiles

### STRICT (Young Children)
Everything ON - maximum protection.

```json
{
  "name": "Young Kids",
  "language": { "profanity_extreme": true, "profanity_strong": true, "profanity_mild": true, "blasphemy": true, "slurs": true, "crude": true, "sexual_explicit": true, "sexual_innuendo": true },
  "sex": { "nudity_full": true, "nudity_partial": true, "nudity_rear": true, "scene_explicit": true, "scene_implied": true, "assault": true, "kissing_hetero": true, "kissing_lgbtq": true, "immodesty": true },
  "violence": { "gore": true, "brutal": true, "graphic": true, "moderate": true, "disturbing": true, "domestic": true, "suicide": true, "selfharm": true },
  "substances": { "drugs_use": true, "drugs_reference": true, "alcohol_use": true, "alcohol_intoxication": true, "smoking": true },
  "thematic": { "lgbtq": true, "occult": true, "taboo": true, "political": true, "religious": true },
  "other": { "bodily": true, "medical": true, "gambling": true, "spoilers": true },
  "playback": { "intro": true, "credits": true, "recap": true }
}
```

### MODERATE (Family Night)
Common family settings - blocks explicit content, allows mild.

```json
{
  "name": "Family Night",
  "language": { "profanity_extreme": true, "profanity_strong": true, "profanity_mild": false, "blasphemy": true, "slurs": true, "crude": false, "sexual_explicit": true, "sexual_innuendo": false },
  "sex": { "nudity_full": true, "nudity_partial": true, "nudity_rear": false, "scene_explicit": true, "scene_implied": false, "assault": true, "kissing_hetero": false, "kissing_lgbtq": false, "immodesty": false },
  "violence": { "gore": true, "brutal": true, "graphic": true, "moderate": false, "disturbing": true, "domestic": true, "suicide": true, "selfharm": true },
  "substances": { "drugs_use": false, "drugs_reference": false, "alcohol_use": false, "alcohol_intoxication": false, "smoking": false },
  "thematic": { "lgbtq": false, "occult": false, "taboo": true, "political": false, "religious": false },
  "other": { "bodily": false, "medical": false, "gambling": false, "spoilers": false },
  "playback": { "intro": false, "credits": false, "recap": false }
}
```

### TEEN (Older Kids)
Blocks only extreme/explicit content.

```json
{
  "name": "Teen",
  "language": { "profanity_extreme": true, "profanity_strong": false, "profanity_mild": false, "blasphemy": false, "slurs": true, "crude": false, "sexual_explicit": true, "sexual_innuendo": false },
  "sex": { "nudity_full": true, "nudity_partial": false, "nudity_rear": false, "scene_explicit": true, "scene_implied": false, "assault": true, "kissing_hetero": false, "kissing_lgbtq": false, "immodesty": false },
  "violence": { "gore": true, "brutal": true, "graphic": false, "moderate": false, "disturbing": false, "domestic": true, "suicide": true, "selfharm": true },
  "substances": { "drugs_use": false, "drugs_reference": false, "alcohol_use": false, "alcohol_intoxication": false, "smoking": false },
  "thematic": { "lgbtq": false, "occult": false, "taboo": true, "political": false, "religious": false },
  "other": { "bodily": false, "medical": false, "gambling": false, "spoilers": false },
  "playback": { "intro": false, "credits": false, "recap": false }
}
```

### LANGUAGE ONLY (Audio Filter)
Only filters spoken language, no visual filtering.

```json
{
  "name": "Language Only",
  "language": { "profanity_extreme": true, "profanity_strong": true, "profanity_mild": false, "blasphemy": true, "slurs": true, "crude": false, "sexual_explicit": true, "sexual_innuendo": false },
  "sex": { "nudity_full": false, "nudity_partial": false, "nudity_rear": false, "scene_explicit": false, "scene_implied": false, "assault": false, "kissing_hetero": false, "kissing_lgbtq": false, "immodesty": false },
  "violence": { "gore": false, "brutal": false, "graphic": false, "moderate": false, "disturbing": false, "domestic": false, "suicide": false, "selfharm": false },
  "substances": { "drugs_use": false, "drugs_reference": false, "alcohol_use": false, "alcohol_intoxication": false, "smoking": false },
  "thematic": { "lgbtq": false, "occult": false, "taboo": false, "political": false, "religious": false },
  "other": { "bodily": false, "medical": false, "gambling": false, "spoilers": false },
  "playback": { "intro": false, "credits": false, "recap": false }
}
```

### LANGUAGE & NUDITY (Audio + Visual Basics)
Filters language and nudity only - allows other content.

```json
{
  "name": "Language & Nudity",
  "language": { "profanity_extreme": true, "profanity_strong": true, "profanity_mild": false, "blasphemy": true, "slurs": true, "crude": false, "sexual_explicit": true, "sexual_innuendo": false },
  "sex": { "nudity_full": true, "nudity_partial": true, "nudity_rear": false, "scene_explicit": true, "scene_implied": false, "assault": true, "kissing_hetero": false, "kissing_lgbtq": false, "immodesty": false },
  "violence": { "gore": false, "brutal": false, "graphic": false, "moderate": false, "disturbing": false, "domestic": false, "suicide": false, "selfharm": false },
  "substances": { "drugs_use": false, "drugs_reference": false, "alcohol_use": false, "alcohol_intoxication": false, "smoking": false },
  "thematic": { "lgbtq": false, "occult": false, "taboo": false, "political": false, "religious": false },
  "other": { "bodily": false, "medical": false, "gambling": false, "spoilers": false },
  "playback": { "intro": false, "credits": false, "recap": false }
}
```

---

## Mapping to .opencue Cue Categories

| Profile Filter | Cue File Category |
|----------------|-------------------|
| `language.profanity_extreme` | `language.profanity.severe` |
| `language.profanity_strong` | `language.profanity.moderate` |
| `language.profanity_mild` | `language.profanity.mild` |
| `language.blasphemy` | `language.blasphemy` |
| `language.slurs` | `language.slurs` |
| `language.crude` | `language.crude` |
| `language.sexual_*` | `language.sexual` |
| `sex.nudity_*` | `visual.nudity` |
| `sex.scene_*` | `visual.sexual` |
| `sex.assault` | `visual.sexual.assault` |
| `violence.gore` | `visual.violence.gore` |
| `violence.brutal` | `visual.violence.brutal` |
| `violence.graphic` | `visual.violence.graphic` |
| `violence.moderate` | `visual.violence.moderate` |
| `violence.disturbing` | `visual.disturbing` |
| `violence.selfharm` | `visual.selfharm` |
| `substances.*` | `substances.*` |
| `other.*` | `other.*` |

---

## Filter Count Summary

| Category | Filters | Granularity |
|----------|---------|-------------|
| Language | 8 | High - word-level control |
| Sex/Nudity | 9 | High - scene type control |
| Violence | 8 | Medium - intensity levels |
| Substances | 5 | Medium - substance types |
| Thematic | 5 | Medium - theme control |
| Other | 4 | Low - misc categories |
| Playback | 3 | Low - skip intro/credits/recap |
| **Total** | **42** | - |

## Preset Summary

| Preset | Use Case | Language | Visual | Other |
|--------|----------|----------|--------|-------|
| **Strict** | Young kids | All ON | All ON | All ON |
| **Moderate** | Family night | Strong ON | Explicit ON | Taboo ON |
| **Teen** | Older kids | Extreme only | Explicit only | Taboo ON |
| **Language Only** | Audio filter | Strong ON | All OFF | All OFF |
| **Language & Nudity** | Audio + nudity | Strong ON | Nudity ON | All OFF |

---

## Profile Management

### How Profiles Work

All profiles (presets and custom) can be modified and saved:

1. **Select** a profile from the list
2. **Modify** any filter settings
3. **Save** changes to that profile
4. Changes persist in browser storage

### Preset Behavior

Presets are editable templates that users can customize:

- **Presets CAN be modified** - Users can change any settings
- **Presets CAN be saved** - Changes persist for that user
- **Presets CAN be reset** - "Reset to Default" restores original settings
- **Presets CANNOT be deleted** - Always available as starting points

```
┌─────────────────────────────────────────────┐
│ PROFILES                                    │
│                                             │
│ ● Strict (modified)   [Edit] [Clone] [Reset]│
│ ○ Moderate            [Edit] [Clone]        │
│ ○ Teen                [Edit] [Clone]        │
│ ○ Language Only       [Edit] [Clone]        │
│ ○ Language & Nudity   [Edit] [Clone]        │
│ ─────────────────────────                   │
│ ○ Grandma's House     [Edit] [Clone] [Delete]│
│ ○ Date Night          [Edit] [Clone] [Delete]│
│                                             │
│ [+ Create New Profile]                      │
└─────────────────────────────────────────────┘
```

### Editing a Profile

Click [Edit] to open the filter settings panel:

```
┌─────────────────────────────────────────────┐
│ ← Back            EDIT: Strict              │
├─────────────────────────────────────────────┤
│ LANGUAGE FILTERS                            │
│ ☑ Extreme Profanity (F-word, etc.)         │
│ ☑ Strong Profanity (S-word, etc.)          │
│ ☐ Mild Profanity (damn, hell)              │
│ ☑ Blasphemy                                 │
│ ☑ Slurs                                     │
│ ░ Crude Language        [Coming Soon]       │
│ ░ Sexual Language       [Coming Soon]       │
├─────────────────────────────────────────────┤
│ VISUAL FILTERS                              │
│ ░ Nudity               [Coming Soon]        │
│ ░ Sexual Content       [Coming Soon]        │
│ ░ Violence             [Coming Soon]        │
├─────────────────────────────────────────────┤
│ CUSTOM WORDS                                │
│ + Add custom word...                        │
├─────────────────────────────────────────────┤
│                                             │
│ [Save]  [Cancel]  [Reset to Default]        │
└─────────────────────────────────────────────┘
```

**Edit Flow:**
1. User clicks [Edit] on any profile
2. Filter settings panel opens
3. User toggles filters on/off
4. User clicks [Save] to save changes
5. Returns to profile list

### Cloning a Profile

Click [Clone] to duplicate any profile as a new custom profile:

```
┌─────────────────────────────────────────────┐
│ CLONE PROFILE                               │
├─────────────────────────────────────────────┤
│                                             │
│ Cloning from: Strict                        │
│                                             │
│ New profile name:                           │
│ ┌─────────────────────────────────────────┐ │
│ │ Kids Movie Night                        │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ ☑ Open editor after cloning                 │
│                                             │
│ [Create Clone]  [Cancel]                    │
└─────────────────────────────────────────────┘
```

**Clone Flow:**
1. User clicks [Clone] on any profile (preset or custom)
2. Prompt asks for new profile name
3. Option to open editor immediately after cloning
4. New custom profile created with all settings copied
5. User can then edit the cloned profile

**Use Cases:**
- Clone "Strict" → "Kids Movie Night" (tweak a few settings)
- Clone "Grandma's House" → "Grandpa's House" (slight variations)
- Clone "Moderate" → "Date Night" (customize for adults)

### Creating a Custom Profile

1. Click "Create New Profile"
2. Enter a name (e.g., "Grandma's House")
3. Optionally start from a preset as template
4. Modify filter settings
5. Click "Save"

### Profile Storage Structure

```json
{
  "profiles": {
    "strict": {
      "name": "Strict",
      "is_preset": true,
      "is_modified": true,
      "default_settings": { ... },
      "user_settings": {
        "language": { "profanity_mild": false },
        "playback": { "intro": false }
      }
    },
    "moderate": {
      "name": "Moderate",
      "is_preset": true,
      "is_modified": false,
      "default_settings": { ... },
      "user_settings": null
    },
    "custom-uuid-123": {
      "name": "Grandma's House",
      "is_preset": false,
      "is_modified": false,
      "settings": { ... },
      "custom_words": [
        { "word": "dagnabbit", "enabled": true }
      ]
    }
  },
  "active_profile": "strict"
}
```

### Profile Actions

| Action | Presets | Custom Profiles |
|--------|---------|-----------------|
| Select | ✓ | ✓ |
| Edit | ✓ | ✓ |
| Save | ✓ | ✓ |
| Clone | ✓ | ✓ |
| Reset to Default | ✓ | ✗ (no default) |
| Delete | ✗ | ✓ |
| Rename | ✗ | ✓ |

### Modified Preset Indicator

When a preset has been modified from its default:
- Show "(modified)" label next to name
- Show "Reset" button to restore defaults
- Store only the diff from default (saves space)

```javascript
// Example: User modified "Strict" preset
// Only store the changes, not full profile
{
  "strict": {
    "is_modified": true,
    "user_settings": {
      "language.profanity_mild": false,  // Changed from true
      "playback.intro": false            // Changed from true
    }
  }
}

// To get full settings: merge default_settings + user_settings
```

---

## References

- [VidAngel Filters](https://help.vidangel.com/hc/en-us/articles/360055496752-What-Filters-options-do-you-provide)
- [ClearPlay Settings](https://help.clearplay.com/docs/adjusting-filtering-settings)
- [VidAngel Filter Guidelines](https://help.vidangel.com/hc/en-us/articles/360058972011-VidAngel-s-Filter-Guidelines)
