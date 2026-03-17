---
name: reviewer/template
description: YAML schema for review.yaml output
---

# review.yaml Schema

```yaml
meta:
  project: "project_name"
  review_version: "1.0"
  reviewed_at: "2024-01-01T12:00:00"
  reviewer: "gpt4o"          # gpt4o | claude

overall:
  score: 8.0                  # 1-10 overall score
  summary: "Overall effect is good with consistent color tones, but the second shot lacks sharpness"
  strengths:
    - "Harmonious color palette"
    - "Proper composition"
  weaknesses:
    - "Some shots lack sharpness"
    - "SHOT_003 motion is not natural enough"

  # Creative Impact Assessment (P7 — Highest Level Audit)
  creative_impact:
    memorable_moment: "The image most likely to stay in the audience's mind after watching is ___"
    emotional_arc: "pass"       # pass | flat (no fluctuation) | needs_work (has fluctuation but insufficient)
    rhythm_quality: "breathing" # breathing (has breathing feel) | monotone (steady pace, no variation) | rushed (too hurried)
    surprise_element: "yes"     # yes | no — Is there an unexpected creative element?
    character_arc: "pass"       # pass | missing (no arc) | shallow (too shallow)
    verdict: "Is this work worth remembering? One-sentence judgment"

shots:
  - id: "SHOT_001"
    score: 9.0
    status: "pass"             # pass | needs_fix | regenerate
    issues: []
    suggestions: []

  - id: "SHOT_002"
    score: 5.0
    status: "regenerate"
    issues:
      - category: "quality"    # quality | consistency | motion | artifact | composition
        severity: "high"       # low | medium | high
        description: "The overall image is blurry and lacks sharpness"
    suggestions:
      - "Increase image_size to 3K and regenerate"
      - "Add 'sharp focus, high detail' to the prompt"

  - id: "SHOT_003"
    score: 6.5
    status: "needs_fix"
    issues:
      - category: "motion"
        severity: "medium"
        description: "The hand holding the bottle suddenly accelerates mid-motion"
      - category: "consistency"
        severity: "low"
        description: "Bottle color slightly shifts to green, not fully consistent with other shots"
    suggestions:
      - "Simplify the motion description, remove unnecessary action details"
      - "Specify 'yellow lemon water' instead of 'sparkling water' in the prompt"

continuity_check:
  color_consistency: "pass"
  style_consistency: "pass"
  object_consistency: "needs_fix"
  spatial_logic: "pass"
  notes: "Bottle color slightly shifts to green in SHOT_003"

action_items:
  - shot_id: "SHOT_002"
    action: "regenerate"
    priority: "high"
    prompt_changes: "Add 'sharp focus, high detail, 8k'"

  - shot_id: "SHOT_003"
    action: "fix_prompt"
    priority: "medium"
    prompt_changes: "Replace 'sparkling water' with 'yellow lemon sparkling water'"
```

## Field Rules

- `score`: 1-10 floating point
- `status`:
  - `pass` — Quality acceptable, no modification needed
  - `needs_fix` — Can be fixed by adjusting the prompt
  - `regenerate` — Needs to be completely regenerated
- `category`: Issue classification
- `severity`: low (aesthetic) / medium (noticeable) / high (must fix)
- `action_items`: Auto-generated fix list that Director Agent can use to automatically execute repairs
- `creative_impact`: Creative impact assessment (P7), the highest-level audit
  - `memorable_moment`: What will stay in the audience's mind after watching? If you can't answer = failure
  - `emotional_arc`: Does the emotion curve have genuine fluctuation? `flat` = constant medium intensity, needs emotion_curve redesign
  - `rhythm_quality`: Does the rhythm have breathing? `monotone` = steady-pace treadmill, needs breathing redesign
  - `surprise_element`: Is there a creative surprise? If all choices are "the most logical" = lacking soul
  - `character_arc`: Does the character have internal change? `missing` = character is just a prop
  - `verdict`: One-sentence ultimate judgment — Is this work worth the audience spending 30-60 seconds to watch?
