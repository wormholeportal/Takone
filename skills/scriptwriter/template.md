---
name: scriptwriter/template
description: YAML schema for screenplay.yaml output
---

# screenplay.yaml Schema

```yaml
meta:
  project: "project_name"
  version: "1.0"
  duration_seconds: 30
  aspect_ratio: "9:16"        # 9:16 | 16:9 | 1:1 | 3:4
  platform: "douyin"           # douyin | bilibili | xiaohongshu | youtube | instagram
  style: "cinematic"           # cinematic | minimal | energetic | vintage | flat
  language: "zh"

concept:
  one_liner: "One-sentence summary of what this video will do"
  target_audience: "Target audience description"
  mood: "Overall emotional tone"
  time_period: "The era in which the story takes place (e.g., primordial, Pre-Qin, Tang Dynasty, modern, etc.)"
  world_setting: "World-building setting (e.g., ancient Chinese mythology, cyberpunk metropolis, medieval Europe, etc.)"
  forbidden_elements:
    - "Element that should not appear 1 (e.g., modern vehicles)"
    - "Element that should not appear 2 (e.g., plastic products)"
  color_palette:
    - "#F5E6D3"
    - "#2C5F2D"
    - "#FFD700"

# ============================================================
# Narrative Angle (narrative_angle) — MUST define before anything else
# ============================================================
# This is the most important section. If audience_expects and audience_will_see
# are basically the same thing, you have a 流水账 — go back and find a real angle.
narrative_angle:
  one_sentence_pitch: "This is a story about ___ told from the perspective of ___"
  audience_expects: "When they hear [topic], the audience pictures ___"
  audience_will_see: "But what they will actually see is ___"
  the_question: "After watching, the viewer will wonder ___"

# ============================================================
# Emotion Curve (emotion_curve) — The emotional blueprint of the entire video
# ============================================================
# Before writing any scenes, map out the emotional arc.
# For SHORT videos (≤30s), use the simple 3-point arc below.
# For LONG videos (>60s), use the full emotion_curve with 5+ sample points.

# --- SHORT VIDEO ARC (≤30s) — use this instead of emotion_curve ---
arc:
  start: "what the viewer feels at the start (1-3 words, e.g., 'curiosity', 'unease')"
  pivot: "the moment everything shifts — describe the MECHANISM, not just the emotion (e.g., 'the camera pulls back to reveal the table is set for two, but one chair is overturned')"
  end: "what the viewer feels at the end (1-3 words, e.g., 'heartbreak', 'awe')"

# --- LONG VIDEO EMOTION CURVE (>60s) — full version ---
# The curve must have ups and downs — flat lines are forbidden.
# There must be a "valley" before the climax (contrast amplifies impact).
emotion_curve:
  - time_pct: 0                   # Time percentage 0-100
    intensity: 3                  # Emotional intensity 0-10
    emotion: "curiosity"          # Emotion type keyword
    note: "Suspenseful opening, audience drawn in by the unknown"
  - time_pct: 20
    intensity: 5
    emotion: "empathy"
    note: "Character situation established, audience begins to care"
  - time_pct: 40
    intensity: 3
    emotion: "quiet tension"
    note: "Calm before the storm (valley — building up to the climax)"
  - time_pct: 60
    intensity: 9
    emotion: "shock"
    note: "Core memory point erupts"
  - time_pct: 80
    intensity: 7
    emotion: "awe"
    note: "Climax resonance"
  - time_pct: 100
    intensity: 4
    emotion: "bittersweet"
    note: "Lingering aftertaste, space for reflection"

# ============================================================
# Memory Anchors (memory_points) — Design first, then build the story around them
# ============================================================
# Before writing any scenes, first design 2-3 "moments the audience cannot forget."
# Not "beautiful shots" but "images that linger in the mind after watching."
# The entire story revolves around memory points; other scenes pave the way or wind down.
memory_points:
  - id: "MP01"
    moment: "Describe this 'unforgettable image' in one sentence"
    emotion: "What this moment should make the audience feel"
    visual_hook: >
      NOT a mood or atmosphere. ONE concrete, specific, slightly unexpected visual element.
      Ask: "Has AI generated this exact image a thousand times?" If yes, find something else.
      Bad: "Cherry blossoms falling around a beautiful woman"
      Good: "A hairpin driven into a war-council table, splitting the wood"
    why_unforgettable: >
      The viewer remembers this tomorrow not because it is beautiful (AI makes everything beautiful)
      but because it is ___. (Fill in: surprising / disturbing / ironic / impossibly specific / etc.)
    placement: "climax"           # Corresponds to a narrative_beat
  - id: "MP02"
    moment: "Second memory anchor"
    emotion: "Another intense emotion"
    visual_hook: "A specific, unexpected visual — not generic beauty"
    why_unforgettable: "Because it is ___"
    placement: "hook"

# ============================================================
# Character Psychology (characters) — Not just appearance, but soul
# ============================================================
# Every character needs inner psychology, even if they only appear for 3 seconds.
# A character's inner desire and arc determine the story's emotional depth.
# visual_definition is the character's visual profile (50-100 words), reused across all scenes for consistency.
characters:
  - id: "char_01"
    name: "Character name"
    appearance: "Appearance description (specific enough to be drawn)"
    visual_definition: >
      50-100 word fixed visual profile describing hairstyle/hair color, skin tone, body type, signature features,
      typical clothing material/color/wear details, etc. All scene visual descriptions must match this.
      Example: A twelve or thirteen-year-old boy, lean but sturdy, with wheat-colored skin. Black short hair,
      slightly curly, with a strand of bangs falling over his forehead. Usually wears a faded navy blue
      cotton T-shirt with a loose collar, khaki loose shorts with a worn hole at the right knee.
      Barefoot or wearing woven straw sandals.
    inner_desire: "Deepest longing (not an external goal, but an internal need)"
    core_conflict: "The contradiction blocking the desire"
    arc: "Change from ___ to ___ (internal change, not just circumstantial)"
    signature_detail: "A specific detail representing the character's soul (action/object/expression)"
    voice: "Optional: voice description for narration/dialogue — tone, pace, texture (e.g., 'low, weathered, unhurried')"

# ============================================================
# Global Visual Tone (visual_tone) — Overall color/lighting/texture style
# ============================================================
# Describes the visual tone for the entire piece; all scene visual descriptions should reference this.
visual_tone: >
  The overall palette oscillates between ocean blue-gray and dusk warm gold as two poles,
  shifting between cool and warm tones following the emotion curve. Daytime scenes lean toward
  bright, translucent watercolor feel; dusk and nighttime scenes lean toward the rich, heavy
  feel of oil painting. Lighting is primarily natural, favoring side light and backlight for
  creating silhouette effects. Texture pursues the authentic feel of film grain, avoiding the
  overly clean digital look.

# ============================================================
# Narrative Skeleton (narrative_beats) — Must be defined before writing scenes!
# ============================================================
# Each beat is a key rhythmic point in the story.
# All scenes must belong to a beat; a scene without a beat = wasted scene.
#
# SHORT VIDEOS (≤30s): Use 3 beats only — hook / pivot / landing
# LONG VIDEOS (>60s): Use the full 5-beat structure below

# --- SHORT VIDEO BEATS (≤30s) ---
# narrative_beats:
#   - beat: "hook"
#     description: "The disruption that stops the scroll — name the MECHANISM"
#     target_duration_seconds: 2
#     pacing: "fast"
#     scenes: ["S01"]
#   - beat: "pivot"
#     description: "The turn — viewer's understanding shifts"
#     target_duration_seconds: 8
#     pacing: "building"
#     scenes: ["S02", "S03"]
#   - beat: "landing"
#     description: "The image/feeling that lingers"
#     target_duration_seconds: 5
#     pacing: "slow"
#     scenes: ["S04"]

# --- LONG VIDEO BEATS (>60s) ---
narrative_beats:
  - beat: "hook"                  # Hook — The most engaging image/question
    description: "One sentence describing what this beat conveys"
    target_duration_seconds: 3    # 1-5s, shorter is better
    pacing: "fast"                # fast | medium | slow | building
    emotional_tone: "mystery"     # Emotional tone keyword
    scenes: ["S01"]               # List of scenes belonging to this beat

  - beat: "setup"                 # Setup — Quickly establish context
    description: "Introduce background and characters"
    target_duration_seconds: 8
    pacing: "medium"
    emotional_tone: "curiosity"
    scenes: ["S02"]

  - beat: "development"           # Development — Core content
    description: "Main plot unfolds"
    target_duration_seconds: 15
    pacing: "building"
    emotional_tone: "tension"
    scenes: ["S03", "S04"]

  - beat: "climax"                # Climax — Emotional peak/twist
    description: "The most striking moment"
    target_duration_seconds: 8
    pacing: "slow"                # Climax should be slow to let the audience fully absorb
    emotional_tone: "awe"
    scenes: ["S05"]

  - beat: "resolution"            # Resolution — Leave an aftertaste
    description: "The story's resonance"
    target_duration_seconds: 6
    pacing: "slow"
    emotional_tone: "bittersweet"
    scenes: ["S06"]

scenes:
  - id: "S01"
    title: "Opening"
    beat_ref: "hook"              # [Required] Which narrative beat this scene belongs to
    duration: "0:00-0:03"
    duration_seconds: 3
    description: "Brief scene overview (1-2 sentences)"

    # ════════════════════════════════════════════════════════
    # visual_description — Novel-level visual prose (core field)
    # 200-600 word continuous prose covering character, environment, lighting, color, motion
    # Uses > folded scalar to avoid unwanted line breaks
    # ════════════════════════════════════════════════════════
    visual_description: >
      [Write novel-like continuous prose describing the entire scene here, 200-600 words.
      All details (character appearance/clothing, objects/props, spatial layout, environment, color,
      lighting, camera suggestions, time changes) woven into the narrative seamlessly.
      After reading, closing your eyes should let you "see" the scene.]

    temporal_change:
      opening_state: "The starting visual of this scene's video"
      closing_state: "The ending visual of this scene's video — setting up the next scene"

    camera: "close-up, slow dolly in"
    key_elements:
      - "element_1"
      - "element_2"
    audio:
      music: "low drone, building tension"
      sfx: "wind howling"
      narration:                              # Optional — only when voice deepens the story
        speaker: "narrator"                   # or a character id from characters list
        text: "The actual spoken words"
        tone: "low, calm, like recalling a distant memory"
    text_overlay: null
    transition_to_next: "cut"     # cut | dissolve | wipe | match_cut | fade
    contrast_to_next: >           # REQUIRED for all scenes except the last. What SHIFTS between this shot and the next?
      Name at least 2 dimensions that change: scale (close↔wide), energy (still↔violent),
      temperature (warm↔cold), density (sparse↔packed), perspective (whose eyes).
      If you can't name the shift, these shots should be merged.
      Example: "S01 is tight close-up, warm amber, still → S02 explodes into wide landscape, cold blue, wind"
    memory_point_ref: null        # If this scene contains a memory anchor, reference the id from memory_points (e.g., "MP01")

  - id: "S02"
    title: "Development"
    beat_ref: "setup"
    duration: "0:03-0:11"
    duration_seconds: 8
    description: "..."
    visual_description: >
      [Continuous prose visual description...]
    temporal_change:
      opening_state: "Continues from the previous scene's closing_state"
      closing_state: "Sets up the next scene"
    # ... same structure as above

audio:
  music_style: "epic orchestral with tension"
  sound_effects:
    - "wind"
    - "footsteps"
  narration_style: "calm, narrative — a storyteller recounting events"  # Overall narration tone
  narration_language: "zh"                                              # Primary language for spoken words
```

## Field Rules

### narrative_angle

**MUST be defined first, before everything else. This is the anti-流水账 gate.**

- `one_sentence_pitch`: Forces you to articulate the unique perspective
- `audience_expects` vs `audience_will_see`: If these two are basically the same → you have a 流水账. Go back.
- `the_question`: What the viewer is left wondering. If there's no lingering question, the video is forgettable.

### arc (short videos ≤30s) / emotion_curve (long videos >60s)

**For ≤30s videos:** Use the simple 3-point `arc` (start / pivot / end). The `pivot` must describe the MECHANISM of change, not just name an emotion.

**For >60s videos:** Use full `emotion_curve` with 5+ sample points.
- `time_pct`: Time percentage from 0-100
- `intensity`: Emotional intensity from 0-10. Flat lines are forbidden
- `emotion`: Emotion type keyword
- `note`: Brief explanation of narrative function
- Classic pattern: low → medium → low → very high → decline (valley before climax is key)

### memory_points

**At least 1 for short videos, at least 2 for long. The story revolves around them.**

- `id`: MP01, MP02... numbered sequentially
- `moment`: One-sentence description — "an image the audience can still recall a day after watching"
- `emotion`: The core emotion this moment should trigger
- `visual_hook`: NOT a mood or atmosphere. One concrete, specific, slightly unexpected visual element. If AI has generated it a thousand times, find something else.
- `why_unforgettable`: Why will the viewer remember this? Not because it's beautiful (everything AI makes is beautiful), but because it's ___ (surprising / disturbing / ironic / impossibly specific).
- `placement`: Which narrative beat it corresponds to

### characters

- `inner_desire`: Not an external goal ("find the treasure"), but an internal need ("to be recognized", "to find belonging")
- `core_conflict`: The force blocking the desire — can be external or internal
- `arc`: From ___ to ___; must be an internal change. "From fear to courage", "From closed off to open"
- `signature_detail`: A specific detail the audience can remember — not an abstract description
- `visual_definition`: 50-100 word fixed visual profile describing appearance/clothing/signature features. All visual_descriptions of this character across scenes must match this

### visual_tone

Describes the overall color/lighting/texture style for all scene visual descriptions to reference. Should include: color temperature direction, lighting style, texture goals, period visual characteristics, etc.

### narrative_beats

**Must be defined before writing scenes.**

**Short videos (≤30s):** Use 3 beats only:
- **hook** → **pivot** → **landing**
- Characters don't need `core_conflict` or full `arc` at this length

**Long videos (>60s):** Use full structure:
- **Story**: hook → setup → development → climax → resolution
- **Ad**: hook → pain_point → solution → cta
- **Tutorial**: hook_result → setup → step_by_step → recap

Pacing options:
- `fast` — Quick cuts, 1-2s shots, high information density
- `medium` — Standard rhythm, 3-4s shots
- `slow` — Slow pacing, 4-6s shots, emotional immersion
- `building` — Gradual acceleration from slow to fast

Duration allocation guidelines:
- hook: 1-5s (shorter is better)
- setup: 15-20% of total video length
- development: 40-60%
- climax: 10-20% (not the shortest, but the "slowest" beat)
- resolution: 10-15%

### scenes

- `id`: S01, S02, S03... numbered sequentially
- `beat_ref`: **Required** — Which narrative beat this scene belongs to
- `duration`: Precise time segment in seconds "start:end"
- `description`: Brief scene overview (1-2 sentences)
- `visual_description`: **Core field** — 200-600 word novel-level continuous visual prose. Uses `>` folded scalar (not `|`). Memory anchor scenes minimum 400 words; regular scenes minimum 200 words. All character descriptions must match the visual_definition in characters
- `temporal_change`: Contains `opening_state` and `closing_state` to ensure visual continuity between scenes. SCENE_N's closing_state must logically connect with SCENE_N+1's opening_state
- `camera`: Use standard cinematographic terminology (close-up, medium, wide, POV, tracking)
- `transition_to_next`: null for the last scene
- `contrast_to_next`: REQUIRED for all scenes except the last. Name at least 2 dimensions that shift between this scene and the next (scale, energy, temperature, density, perspective). If you can't name the shift, merge the scenes.
- `memory_point_ref`: If this scene contains a memory anchor, reference the memory_points id. Scenes containing memory points are the core of the entire piece; other scenes serve them
- `time_period`: Specify the historical period; all props/costumes/architecture in all scenes must match
- `forbidden_elements`: List of elements that should not appear in the visuals
- All YAML key names use lower_snake_case
