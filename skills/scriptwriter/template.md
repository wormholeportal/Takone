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
# Emotion Curve (emotion_curve) — The emotional blueprint of the entire video
# ============================================================
# Before writing any scenes, first map out the emotional intensity curve of the entire video.
# This is the foundation for all subsequent decisions: beat pacing, shot duration, music choices all derive from the curve.
# The curve must have ups and downs — flat lines are forbidden (constant medium intensity = a lullaby).
# There must be a "valley" before the climax (contrast amplifies emotional impact).
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
    visual_hook: "The single most impactful visual element on screen"
    placement: "climax"           # Corresponds to a narrative_beat
  - id: "MP02"
    moment: "Second memory anchor"
    emotion: "Another intense emotion"
    visual_hook: "Another impactful visual element"
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
      voiceover: null
    text_overlay: null
    transition_to_next: "cut"     # cut | dissolve | wipe | match_cut | fade
    emotional_function: "hook"    # This scene's role on the emotion curve: hook(capture attention) | buildup(build tension) | release(release) | turn(pivot) | breath(breathing space)
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
  voiceover_tone: "calm, narrative"
  voiceover_language: "zh"
```

## Field Rules

### emotion_curve

**Defined before narrative_beats; this is the foundation for all subsequent decisions.**

- `time_pct`: Time percentage from 0-100, with at least 5 sample points (opening, setup, valley, climax, ending)
- `intensity`: Emotional intensity from 0-10. Flat lines are forbidden — if all points fall between 4-6, there is no variation
- `emotion`: Emotion type keyword (curiosity / tension / empathy / shock / awe / warmth / sadness / joy / bittersweet, etc.)
- `note`: Brief explanation of the narrative function at this moment
- Classic pattern: low → medium → low → very high → decline (three-act structure; the valley before the climax is key)

### memory_points

**At least 2, defined before narrative_beats. The entire story revolves around them.**

- `id`: MP01, MP02... numbered sequentially
- `moment`: One-sentence description — the standard is "an image the audience can still recall a day after watching"
- `emotion`: The core emotion this moment should trigger
- `visual_hook`: The single most prominent visual element on screen (just one — not a list)
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

**The most important field; must be defined before writing scenes.**

Common beat types:
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
- `emotional_function`: This scene's role on the emotion curve. Every scene must have a clear emotional function — not just "showing a visual"
- `memory_point_ref`: If this scene contains a memory anchor, reference the memory_points id. Scenes containing memory points are the core of the entire piece; other scenes serve them
- `time_period`: Specify the historical period; all props/costumes/architecture in all scenes must match
- `forbidden_elements`: List of elements that should not appear in the visuals
- All YAML key names use lower_snake_case
