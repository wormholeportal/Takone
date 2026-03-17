---
name: pipeline
description: End-to-end video creation pipeline. Orchestrates all stages from creative concept to final video export.
---

# Video Pipeline

Manage the complete lifecycle of video creation — from a vague creative idea to a publishable short video.

## Pipeline Stages

| Stage | Skill | Input | Output |
|-------|-------|-------|--------|
| 0. Emotion Blueprint | `scriptwriter` | Creative idea | emotion_curve + memory_points + characters |
| 1. Script + Visuals | `scriptwriter` | Emotion blueprint | `screenplay.yaml` (with narrative_beats + novel-level visual descriptions + character visual profiles) |
| 2. Storyboard | `storyboard` | `screenplay.yaml` | `storyboard.yaml` (with cinematic_intent/emotional_intensity/breathing) |
| 3. Prompts | `visualizer` | `storyboard.yaml` + `screenplay.yaml` | `prompts.json` |
| 3.5 Design | `designer` | `prompts.json` | `assets/references/` |
| 4. Generation | (code) | `prompts.json` + reference images | `assets/images/`, `assets/videos/` |
| 5. Review | `reviewer` | Generated assets | `review.yaml` |
| 6. Iteration | Loop back to Stage 3 | `review.yaml` | Updated assets |
| 7. Assembly | (FFmpeg) | All video clips + storyboard.yaml | `output/final.mp4` (smart transitions/trimming) |
| 8. Audio | (FFmpeg) | `output/final.mp4` + music file | `output/final_with_audio.mp4` |

## Routing Rules

Determine which stage to start from based on user intent:

- **"I have a creative idea"** → Start from Stage 0 (design the emotion blueprint first, then write the script + visuals)
- **"Here is my script"** → Start from Stage 2 (storyboard)
- **"Help me write visual descriptions"** → Jump to Stage 1 (supplement/refine visual_description in screenplay.yaml)
- **"Regenerate shot 3"** → Jump to a specific shot in Stage 4
- **"Design character references first"** → Jump to Stage 3.5
- **"Review and improve"** → Jump to Stage 5
- **"Show me trending references"** → Call the search_reference tool
- **"Export the final video"** → Jump to Stage 7
- **"Add background music"** → Jump to Stage 8

## Cross-Stage Consistency

Before advancing each stage, check:

1. **Visual anchors** — Color tone and style remain consistent across all shots
2. **Temporal continuity** — Scene timelines connect logically
3. **Aspect ratio** — All shots use the same aspect_ratio
4. **Character consistency** — The same character/object maintains consistent appearance across different shots
5. **Period consistency** — All props, architecture, and costumes match the story's historical setting
6. **Shot continuity** — Adjacent shots' opening/closing states connect smoothly

## Quality Gates

### Pre-Generation Gate (Stage 3 → 3.5 → 4)

**All checks must pass before generation begins; each may require multiple iterations:**

**Creative Impact (Highest Priority — Before All Technical Checks!):**
- [ ] screenplay.yaml contains emotion_curve with genuine fluctuation (not flat; valleys before climax)
- [ ] screenplay.yaml contains at least 2 memory_points ("What will stick in the viewer's mind after watching?")
- [ ] screenplay.yaml characters have inner_desire and arc (characters are not props)
- [ ] storyboard.yaml every shot has cinematic_intent (intent first, then technique — not arbitrary framing)
- [ ] storyboard.yaml every shot has emotional_intensity without 3+ consecutive identical values
- [ ] storyboard.yaml every shot has breathing annotation with alternation (inhale → exhale pattern)
- [ ] storyboard.yaml rhythm_relationship has no 3+ consecutive "continuation"

**Narrative Skeleton:**
- [ ] screenplay.yaml contains narrative_beats (hook/setup/development/climax/resolution)
- [ ] narrative_beats includes a hook (strong hook in the first 1-5s)
- [ ] narrative_beats includes a climax (emotional peak)
- [ ] Pacing varies between beats (not all at the same rhythm)
- [ ] Total beat duration matches target duration
- [ ] All scenes are linked to a beat via beat_ref (no wasted scenes)

**Script Quality:**
- [ ] screenplay.yaml contains all three emotional foundations: emotion_curve, memory_points, characters
- [ ] screenplay.yaml every scene has emotional_function and memory_point_ref (if applicable)
- [ ] screenplay.yaml contains complete scene breakdowns with time annotations
- [ ] screenplay.yaml all scene props/environments match the historical period (no anachronisms)
- [ ] screenplay.yaml has a strong enough hook in the first 3 seconds
- [ ] screenplay.yaml narrative structure has ups and downs (not a flat chronological account), with suspense and rhythm changes
- [ ] screenplay.yaml has no "wasted scenes" — every scene advances the narrative
- [ ] screenplay.yaml time allocation is reasonable with no dragging sections

**Visual Description Quality (Embedded in screenplay.yaml):**
- [ ] Every scene has a 200-600 word visual_description (novel-level continuous prose)
- [ ] Memory anchor scenes have the most detailed descriptions (400-600 words)
- [ ] Each character in characters has a visual_definition (50-100 word visual profile)
- [ ] The same character's appearance/costume description in visual_description across scenes matches their visual_definition
- [ ] Adjacent scenes' temporal_change (opening_state/closing_state) can naturally connect
- [ ] All descriptions contain no anachronistic elements
- [ ] Color/lighting tone matches the emotion_curve and visual_tone

**Storyboard Quality:**
- [ ] storyboard.yaml every shot has beat_ref (linked to the narrative skeleton)
- [ ] storyboard.yaml every shot has pacing_intent with fast/slow variation (not all medium)
- [ ] storyboard.yaml every shot has clear visual description
- [ ] storyboard.yaml every shot has opening_state and closing_state
- [ ] storyboard.yaml adjacent shots' start/end states can naturally connect
- [ ] storyboard.yaml all key_elements match the historical period
- [ ] storyboard.yaml hook shots are ≤ 5s, use_duration allocation has rhythmic variation
- [ ] storyboard.yaml every shot has cut_on annotation (action/emotion/rhythm/visual_match)
- [ ] storyboard.yaml transitions are appropriate (hard cuts for action, dissolves/fades for emotional segments), every shot has transition_out

**Style Consistency:**
- [ ] prompts.json style_anchor is sufficiently detailed (50-100 words, covering render/color/lighting/texture/exclusions)
- [ ] prompts.json all shot prompts fully include the style_anchor
- [ ] Reference image style matches the style_anchor (no cartoon characters + photorealistic scenes dissonance)
- [ ] Reference images have been fully generated (assets/references/)

**Prompt Quality:**
- [ ] prompts.json every shot has a prompt optimized for the target model
- [ ] prompts.json all prompts contain no anachronistic elements
- [ ] prompts.json same character descriptions are consistent across different prompts
- [ ] prompts.json video prompts include opening and closing state descriptions
- [ ] prompts.json all involved characters/scenes have specified reference_images

### Post-Generation Gate (Stage 4 → 5 → 7)

- [ ] All generated images/videos confirmed through manual or AI review
- [ ] check_continuity verifies consistency across all adjacent shots
- [ ] Final video duration and aspect ratio meet target platform requirements

## Generation Strategy

Recommended generation workflow (rather than all at once):

1. **Images first, then video** — Use Seedream to generate keyframe images, confirm the visuals, then use Seedance to generate video
2. **Shot by shot** — Don't generate all shots at once; do them one at a time for easier iteration
3. **Reference-driven** — If the user has reference images, use image_to_image to maintain style consistency
