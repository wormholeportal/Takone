---
name: pipeline
description: Feeling-first video creation pipeline. Four stages from inspiration to final export.
---

# Video Pipeline

Create short videos that make people stop scrolling. Four stages, feeling-first.

## The Four Stages

| Stage | What Happens | Input | Output |
|-------|-------------|-------|--------|
| 1. DISCOVER | Browse platforms, find references, define feeling | Creative idea | `feeling.yaml` + reference images |
| 2. DESIGN | Write shot plan + generate character references | `feeling.yaml` + references | `shots.yaml` + `assets/design/*.png` |
| 3. GENERATE | Generate variations per shot, compare and select best | `shots.yaml` + references | `assets/image/`, `assets/video/` |
| 4. ASSEMBLE | FFmpeg assembly + audio mixing | Video clips + `shots.yaml` | `output/final.mp4` |

**Research (`learn`) is available at ANY point — not just Stage 1.** Whenever you're unsure, go look it up.

## Shot Budget (STRICTLY ENFORCED)

| Target Duration | Max Shots | Variations Per Shot |
|----------------|-----------|-------------------|
| 5-15 seconds   | 1-3       | Generate 5, pick best |
| 15-30 seconds  | 3-5       | Generate 3, pick best |
| 30-60 seconds  | 5-8       | Generate 2, pick best |
| 1-3 minutes    | 8-15      | Generate 2, pick best |

**Exceeding these limits = planning failure.** Cut ruthlessly. 2 stunning shots are infinitely better than 8 mediocre ones. If your shot count exceeds the limit, combine or remove shots until it fits.

## Routing Rules

Determine where to start based on user intent:

- **"I have a creative idea"** → Stage 1 (DISCOVER: research first, then create)
- **"Here's my reference video"** → Stage 1, skip search, go straight to feeling extraction
- **"Regenerate shot 3"** → Stage 3 for that specific shot
- **"Export the final video"** → Stage 4
- **"Add background music"** → Stage 4 (audio step)

## Stage 1: DISCOVER — Find Your Feeling AND Your Angle

**This is MANDATORY. Never skip it.**

### Step 1: Narrative Research (do this FIRST)

For well-known stories, myths, or historical figures — research how others have told it:
1. `learn_browse(action="search_videos", query="{concept}", platform="douyin")`
2. Watch 5-10 versions. Note what they ALL do the same way — that's what you must NOT do.
3. Ask: What angle has NOT been taken? Whose perspective is missing? What 3 seconds has no one shown?

### Step 2: Visual Research

1. `learn_browse(action="search_images", query="{concept} aesthetic")`
2. Download the 3-5 best reference frames/images
3. Analyze references with vision model: What feeling do they create? What technique drives it?

### Step 3: Write `feeling.yaml`

```yaml
target_feeling: "The viewer should feel ___"

narrative_angle:                                    # MANDATORY — define before anything visual
  conventional_telling: "How most people tell this story (1 sentence)"
  this_telling: "What makes THIS version different (1 sentence)"
  the_subversion: "The one thing the viewer does NOT expect"

references:
  - image: "assets/learn/ref_01.png"
    why: "The slow reveal through mist creates tension"
visual_dna:
  color_mood: "cold, blue-gray dominant"
  pacing: "slow build → burst"
  first_3_seconds: "static frame, then sudden motion"
anti_patterns:
  - "no cartoon look"
  - "no over-saturated colors"
```

**Research as a Reflex** — Also available at any later stage:

| Situation | Action |
|-----------|--------|
| Unsure about historical details | `learn_browse(action="search_web", query="...", platform="baike")` |
| Can't picture the style | `learn_browse(action="search_images", query="...")` |
| Need pacing reference | `learn_browse(action="search_videos", query="...", platform="bilibili")` |
| Found something great | `learn_download(url="...", media_type="image")` |

### Gate: Kill the Obvious

**Before moving to Stage 2, answer this:**

> If I described this video to a friend in one sentence, would they say "I've seen that before"?

If yes — go back and find a different angle. Beauty is not an angle. Chronological retelling is not an angle. "The same story but with better visuals" is not an angle.

## Stage 2: DESIGN — Write Your Shots + Generate Character References

Load `scriptwriter` + `visualizer` + `designer` skills. Output `shots.yaml` + character reference images.

### Contrast Mapping (do this BEFORE writing shots)

List the shift between each adjacent pair of shots. Every pair must differ in at least TWO dimensions:
- **Scale**: close-up ↔ wide
- **Energy**: still ↔ violent motion
- **Temperature**: warm ↔ cold
- **Density**: sparse/empty ↔ packed with detail
- **Perspective**: whose eyes are we looking through?

If two adjacent shots have no shift — merge them or cut one.

### Key Requirements
- Every shot has a `feeling` field — this is the creative anchor
- Prompts must be specific (photographer language: lens, lighting, color)
- `style_anchor` (50-100 words) in every prompt
- Characters need `reference_images` for consistency
- For ≤15s videos: skip elaborate structure. Just make every frame stunning.

**After writing shots.yaml, apply the Scroll-Stop Test:** "Would I stop scrolling for this?" If not, rewrite.

### MANDATORY: Generate ALL Reference Images (before leaving Stage 2)

After shots.yaml is finalized:
1. Load `designer` skill
2. For each character in `characters` list → `generate_reference(ref_type="character", ref_id="{id}", prompt="...", aspect_ratio="3:2")`
   - Prompt must include: full style_anchor, anatomy keywords, detailed physical description, clothing, view specification
3. For each distinct scene/location → `generate_reference(ref_type="scene", ref_id="{scene_id}", prompt="...", aspect_ratio="9:16")`
   - Prompt must include: full style_anchor, lighting, color tone, time of day, environment details
4. Add all generated reference IDs to each shot's `reference_images` (both characters AND scenes in that shot)
5. Verify all `reference_images` entries have corresponding files in `assets/design/`

**Do NOT proceed to Stage 3 without ALL references. `generate_image` will BLOCK if references are missing.**

## Stage 3: GENERATE — Create and Select

1. **Pre-check** — Verify all reference images (characters + scenes) exist in `assets/design/`. If missing, generate them first.
2. **Multiple variations per shot** — Use `variations` parameter on generate_image
3. **Compare and select** — Use `compare_shots` to pick the best version
4. **Generate video** from the best keyframe
5. **Evaluate** — Use `evaluate_shot`. If it doesn't feel right, regenerate (max 3 attempts)

## Stage 4: ASSEMBLE

1. `assemble_video` — reads shots.yaml for order, trimming, transitions
2. `add_audio_track` if additional background music needed (Seedance 1.5 already generates audio with each video clip — dialogue, sound effects, and music are baked into the video during Stage 3 via video_prompt)
3. Final review: watch the assembled piece. Does it work as a whole? Does it tell a story?

## Quality Gate: The Scroll-Stop Test

**At every stage, one question:**

> "If this appeared in my Douyin feed right now, would I stop scrolling and watch?"

- **Yes** → proceed
- **No** → figure out why, fix it
- **Not sure** → compare against your reference videos. What's the gap?

This replaces all checklists. Trust your creative judgment.

## Cross-Shot Consistency

Before generation:
- style_anchor appears in all prompts
- Character descriptions consistent across shots
- Adjacent shots' opening/closing states connect naturally
- All elements match the story's period/setting
- Same aspect_ratio throughout

## Generation Strategy

1. **Images first, then video** — Confirm the visual before animating
2. **Shot by shot** — Don't batch generate; iterate per shot
3. **Reference-driven** — Use image-to-image for consistency
4. **Multiple variations** — Never accept the first generation; always compare options
