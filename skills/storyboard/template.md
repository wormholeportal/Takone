---
name: storyboard/template
description: YAML schema for storyboard.yaml output
---

# storyboard.yaml Schema

```yaml
meta:
  project: "project_name"
  total_shots: 8
  screenplay_version: "1.0"
  aspect_ratio: "9:16"

shots:
  - id: "SHOT_001"
    scene_ref: "S01"              # Corresponds to the scene id in screenplay.yaml
    beat_ref: "hook"              # [Required] Which narrative beat this shot belongs to (corresponds to narrative_beats in screenplay.yaml)
    pacing_intent: "fast"         # fast(1-2s) | medium(3-4s) | slow(4-6s) — The pacing intent for this shot
    cut_on: "action"              # action | emotion | rhythm | visual_match — The edit point type for this shot
    # Emotion & rhythm layer (derive technical decisions from emotional intent)
    cinematic_intent: "Make the audience feel ___"  # [Required] Write the emotional intent first, then derive framing/movement/lighting
    emotional_intensity: 7        # 0-10, the emotional intensity of this shot (corresponds to emotion_curve in screenplay)
    breathing: "inhale"           # inhale(build-up) | exhale(release) | hold(held breath) | rest(rest)
    rhythm_relationship: "contrast"  # Rhythmic relationship with the previous shot: acceleration | deceleration | contrast | continuation
    memory_point_ref: null        # If this is a memory anchor shot, reference the memory_point id from screenplay
    shot_type: "close-up"         # EWS | WS | MS | MCU | CU | ECU | POV | OTS
    duration_seconds: 3
    description: "Detailed visual description, specific enough to be directly converted into a generation prompt"
    camera_angle: "eye-level, 45-degree"    # high | low | eye-level | bird-eye | worm-eye
    camera_movement: "slow dolly forward"    # static | dolly | pan | tilt | tracking | handheld | orbit
    lighting: "natural sunlight from left, warm tone 5500K"
    composition: "rule of thirds, subject right third"
    key_elements:
      - "element_1"
      - "element_2"
    color_grading: "warm, slightly desaturated, +10 orange tint"
    motion_notes: "slow motion 0.5x"         # Description of object motion within the frame
    reference_style: "Wes Anderson flat composition"   # Optional style reference

    # Shot continuity
    transition_in: "fade from black"           # Transition method from the previous shot
    transition_out: "dissolve"                 # Transition method to the next shot
    opening_state: "Description of the visual starting state"           # The state that should appear at the beginning of the video
    closing_state: "Description of the visual ending state"           # The state at the end of the video (starting point for the next shot)

    # Generation & editing parameters
    gen_strategy: "image_to_video"    # text_to_video | image_to_video | image_only
    gen_provider_hint: "seedance"     # seedance | minimax | sora (suggested model)
    aspect_ratio: "9:16"
    trim_start: 0.0                  # Trim start point (seconds), extract the best segment from the material
    trim_end: null                   # Trim end point (seconds), null = use to end of material
    use_duration: 3                  # Final duration used in the assembled video (seconds), can be less than material duration

  - id: "SHOT_002"
    scene_ref: "S01"
    # ... same structure as above

continuity:
  color_consistency: "Overall warm tones, color temperature 5500K-6000K"
  character_anchors: "Consistency requirements for recurring characters/objects"
  spatial_logic: "Kitchen → Tabletop → Balcony → Outdoors"
  style_notes: "All shots maintain Japanese-style color palette, low saturation"
  time_period: "The historical period of the story; all props and scenes must match this era"
  forbidden_elements: "Elements inconsistent with the era/theme (e.g., modern items that should not appear in ancient stories)"
```

## Field Rules

- `id`: SHOT_001, SHOT_002... numbered sequentially with three digits
- `scene_ref`: Corresponds to the scene id in screenplay.yaml; one scene can have multiple shots
- `beat_ref`: **Required** — Which narrative beat from screenplay.yaml this shot belongs to (e.g., hook/setup/development/climax/resolution). A shot without beat_ref = wasted shot
- `pacing_intent`: The pacing intent for this shot, which determines the final use duration
  - `fast` — Quick cut, 1-2 seconds, high information density, suitable for hooks and action segments
  - `medium` — Standard rhythm, 3-4 seconds, suitable for narrative development
  - `slow` — Slow pacing, 4-6 seconds, emotional immersion, suitable for climax and resolution
- `cut_on`: The edit point type for this shot (when to cut to the next shot)
  - `action` — Action cut: cut during an action in progress (most common, most natural)
  - `emotion` — Emotion cut: cut when emotion reaches its peak or turning point
  - `rhythm` — Rhythm cut: cut on the music beat (requires background music)
  - `visual_match` — Visual match: cut using similar composition/color/shape (strongest transition feel)
- `cinematic_intent`: **One of the most important fields**. Format: "Make the audience feel [emotion]." Write this first, then derive framing, movement, and lighting. If you find yourself choosing framing first and then thinking about emotion, the order is reversed
- `emotional_intensity`: 0-10, must correspond to the emotion_curve in screenplay. **3+ consecutive identical intensity values = flat line = needs revision**
- `breathing`: The breathing attribute of the shot
  - `inhale` — Build-up, preparing for the next climax (quiet, slow, space)
  - `exhale` — Release, emotional burst (climax, impact, turning point)
  - `hold` — Held breath, extreme moment (the most striking second)
  - `rest` — Rest, space for audience to digest
  - **The shot before a climax shot must be "inhale"; the climax itself is "exhale" or "hold"**
- `rhythm_relationship`: Rhythmic relationship with the previous shot (null for the first shot)
  - `acceleration` — Faster/more tense than the previous shot
  - `deceleration` — Slower/quieter than the previous shot
  - `contrast` — Strong contrast with the previous shot (slow→fast or fast→slow)
  - `continuation` — Continues the previous shot's rhythm
  - **3+ consecutive "continuation" = rhythm death, must revise**
- `memory_point_ref`: If this shot contains a memory anchor, reference the memory_point id from screenplay. Memory point shots are the core of the entire piece and should receive the most visual investment
- `description`: The most critical field; must be detailed enough
- `gen_strategy`:
  - `image_to_video` — Generate a keyframe image first, then convert to video (recommended, more controllable quality)
  - `text_to_video` — Generate video directly from text (suitable for simple scenes)
  - `image_only` — Only need a static image (e.g., product showcase, text card)
- `duration_seconds`: 3-5 seconds per shot is ideal
- `transition_in/out`: Transition methods between shots
- `opening_state`: The starting visual state of this shot's video (must connect with the previous shot's closing_state)
- `closing_state`: The ending visual state of this shot's video (must connect with the next shot's opening_state)
- `trim_start/trim_end`: Extract the best segment from generated material. In AI-generated 5-second material, only 1-2 seconds may be usable
- `use_duration`: Final duration used in the assembled video; can be much less than the generated material duration
- `continuity`: Global parameters to ensure cross-shot consistency
- `time_period`: Specify the historical period to prevent anachronistic elements
- `forbidden_elements`: List elements that should not appear (e.g., modern items in ancient scenes)
