---
name: reviewer
description: Multi-stage review — pre-generation script/logic review and post-generation visual quality review.
---

# Reviewer

Review skill — includes pre-generation script/logic review and post-generation visual quality review.

## Review Modes

Reviewer has two modes. **Pre-generation review** is the most critical, as it costs far less than reworking after generation.

---

## I. Pre-Generation Review

**Before generating any images/videos, all of the following review dimensions must be passed.**

### P1. Period & Logic Consistency (Highest Priority)

Review all elements scene by scene to ensure they match the story's historical period and world-building:

- **Anachronisms** — Do ancient/historical stories contain modern elements?
  - Transportation: Modern ships, cars, airplanes → Should be replaced with rafts, dugout canoes, horse-drawn carts
  - Daily items: Plastic products, glass bottles, paper (paper did not exist before the Warring States period)
  - Architecture: Reinforced concrete, glass curtain walls → Should be replaced with thatched huts, adobe, stone buildings
  - Clothing: Modern garments, zippers, buttons → Should be replaced with animal skins, rough cloth, ties/bindings
  - Tools: Metal implements (did they exist in the corresponding era?)
- **Prop plausibility** — Do all objects that appear fit the world-building?
- **Natural environment** — Are vegetation, terrain, and weather plausible?
- **Cultural consistency** — Do language, symbols, and rituals match the setting?

### P2. Story Logic Consistency

- **Character continuity** — Is the character's identity and features consistent across all scenes?
- **Plot coherence** — Is the cause-and-effect chain from Scene A → B → C smooth? Any jumps or contradictions?
- **Spatial logic** — Is the character's spatial transition from Scene A to Scene B reasonable?
- **Theme relevance** — Does every shot serve the core theme? Is there any off-topic content?
- **Emotional arc** — Is the overall emotional progression smooth? Any jarring emotional jumps?

### P3. Shot Continuity Review

- **beat_ref completeness** — Does every shot have a beat_ref corresponding to screenplay's narrative_beats? A shot without beat_ref = wasted shot
- **Start/end states** — Does each shot's opening_state connect with the previous shot's closing_state?
- **Motion direction** — Is the motion direction consistent between adjacent shots (left/right)?
- **Lighting transitions** — Do adjacent shots transition naturally in lighting and color temperature?
- **Transition appropriateness** — Is the chosen transition method suitable for the content? Does each shot have transition_out and cut_on?
- **Rhythm feel** — Does the shot duration allocation have fast/slow rhythmic variation? pacing_intent cannot all be medium

### P4. Art Style & style_anchor Review

- **style_anchor quality** — Is the style_anchor sufficiently detailed (50-100 words)? Does it cover dimensions like render style, color, lighting, texture, and exclusions? "cinematic, high quality" is too vague and unacceptable
- **Global consistency** — Does the style_anchor appear in all shot prompts? Any omissions?
- **Character style matching** — Does the character reference art style match the style_anchor? Is there a disconnect with cartoon characters but photorealistic scenes?
- **Exclusion enforcement** — Are the NOT keywords in the style_anchor enforced across all prompts?

### P5. Prompt Quality Review

- **Specificity** — Is the prompt specific enough to directly generate an image? Any vague descriptions?
- **Period accuracy** — Do all elements described in the prompt (props, costumes, architecture) match the era?
- **Character consistency** — Are descriptions of the same character consistent across different prompts?
- **Reference image coverage** — Do recurring characters/scenes have reference_images specified?
- **Video continuity** — Do video_prompts include opening_state and closing_state?

### P6. Narrative Quality Review

- **Hook** — Is there enough grabbing power in the first 3 seconds? Can it capture the audience?
- **Pacing** — Is the duration allocation reasonable? Any dragging "wasted scenes"? Is there rhythmic variation?
- **Narrative structure** — Is there suspense? Any twists or surprises? Is it a flat chronological account or does it have ups and downs?
- **Emotional arc** — Is the overall emotional progression smooth? Is the core emotion focused?
- **Information density** — Does every second carry information? Any blank segments where "nothing happens"?

### P7. Creative Impact Review (Highest Level Audit)

**This is not checking "is it correct" but "is it good." A technically perfect but emotionally barren work = failure.**

**Core Questions (each must be answered positively, otherwise needs rework):**
- **Memory point** — After watching this video, what image will stay in the audience's mind? If the answer is "nothing in particular," it fails
- **Emotional fluctuation** — Does the emotion_curve have genuine ups and downs? Or is it a "medium-intensity flat line"?
- **Jaw-dropping moment** — Is there at least one "gasp-inducing" moment?
- **Build-up and release** — Is there sufficient "quiet" before the climax to amplify impact?
- **Character arc** — Does the character have an arc? Is there internal change from beginning to end? Or are they just a prop?
- **Breathing feel** — Is the overall feel "rhythmic breathing" or a "steady-pace treadmill"?

**Creative Surprise Check:**
- Is there one element the audience completely wouldn't expect? (Twist / unexpected combination / surprising perspective)
- If all decisions are "the most logical choice," it lacks creativity — good work needs "unexpected yet logical"

**Rhythm Quantitative Check:**
- Count consecutive shots with the same emotional_intensity. If >= 3 → rhythm problem
- Count consecutive shots with the same breathing. If >= 3 → breathing problem
- Count consecutive rhythm_relationship = "continuation". If >= 3 → rhythm death
- Fast shot immediately followed by fast shot? Check if it's intentional

### Pre-Generation Review Workflow (Multiple Iterations, Not Done in One Pass!)

```
Round Zero: Creative Impact Audit (P7) — Before all technical audits!
 ├─ Read screenplay.yaml
 ├─ Check if emotion_curve has genuine fluctuation (not flat)
 ├─ Check if memory_points are sufficiently striking ("What will stick in the mind after watching?")
 ├─ Check if characters have psychological arcs (inner_desire + arc)
 ├─ Check if information density has breathing
 ├─ This is the hardest audit to pass — if the concept itself is mediocre, perfect technique can't save it
 ├─ Fail → Return to scriptwriter to redesign emotion curve and memory points
 └─ Only proceed to technical audits after passing

Round One: Script Review (P1 + P2 + P6)
 ├─ Read screenplay.yaml
 ├─ Check period/logic/causality/props (P1)
 ├─ Check story logic consistency (P2)
 ├─ Check narrative quality: hook, pacing, structure, emotional arc (P6)
 ├─ Found issues → Modify screenplay.yaml
 └─ Re-evaluate until passed

Round Two: Storyboard Review (P3 + P7 rhythm section)
 ├─ Read storyboard.yaml
 ├─ Check beat_ref completeness, continuity, transitions, opening_state/closing_state
 ├─ Check if cinematic_intent exists for every shot (emotion-driven or arbitrary choice?)
 ├─ Check emotional_intensity fluctuation (3 consecutive identical values = flat line)
 ├─ Check breathing alternation (is there inhale before climax?)
 ├─ Check rhythm_relationship (3 consecutive continuation = rhythm death)
 ├─ Check all key_elements match the historical period
 ├─ Check pacing and duration allocation
 ├─ Found issues → Modify storyboard.yaml
 └─ Re-evaluate until passed

Round Three: Art Style Review (P4)
 ├─ Read prompts.json
 ├─ Check style_anchor quality (detailed enough? covers required dimensions?)
 ├─ Check if all prompts include the complete style_anchor
 ├─ Check if character reference art style matches
 ├─ Found issues → Modify style_anchor or related prompts in prompts.json
 └─ Re-evaluate until passed

Round Four: Prompt Review (P5)
 ├─ Read prompts.json
 ├─ Check each prompt for quality, period accuracy, consistency
 ├─ Check reference_images coverage
 ├─ Check video_prompt continuity descriptions
 ├─ Found issues → Modify prompts.json
 └─ Re-evaluate until passed

All passed → Ready to begin generation
```

**Important: Each round may require multiple iterations until that round has no issues. Don't rush to the next stage.**

---

## II. Post-Generation Review

### 1. Visual Quality
- **Sharpness** — Is the image blurry or has artifacts?
- **Color** — Does the color tone match expectations? Any color cast?
- **Composition** — Is the subject position reasonable?
- **Lighting** — Is the lighting natural and consistent?

### 2. Common AI Generation Issues
- **Hand deformation** — Abnormal finger count, distortion
- **Facial distortion** — Disproportionate facial features
- **Garbled text** — Unreadable text in the image
- **Object fusion** — Blurred boundaries between two objects merging together
- **Unnatural motion** — Sudden acceleration/pauses in video movement
- **Flickering** — Sudden brightness changes between video frames
- **Temporal discontinuity** — Object position jumps between frames
- **Anachronisms** — Elements appearing that don't match the historical period (the most serious issue)

### 3. Cross-Shot Consistency
- **Color tone consistency** — Are all shots within the same color temperature range?
- **Style consistency** — Is the visual style unified (no mixing photorealistic and cartoon)?
- **Object consistency** — Is the same product/character consistent across different shots?
- **Spatial logic** — Do scene transitions follow spatial logic?
- **Smooth continuity** — Are adjacent shots' start/end visuals connected?

### 4. Narrative Rhythm
- **Duration appropriateness** — Does each shot's duration match its content?
- **Rhythm variation** — Is there alternation between fast and slow?
- **Information density** — Does each shot convey sufficient information?

## Review Output Format

Score each shot (1-10) and provide specific issues and suggestions.

## Improvement Strategies

| Issue | Fix Strategy |
|-------|-------------|
| Blurry image | Increase image_size or regenerate |
| Inconsistent color tone | Adjust color descriptions in prompt, unify color_grading keywords |
| Hand/face deformation | Avoid hand close-ups, use wider framing |
| Unnatural motion | Simplify motion description, describe only one motion per shot |
| Inconsistent style | Check if style_anchor is consistent across all prompts |
| Inconsistent objects | Use image_to_image with reference images |
| Anachronisms | Modify element descriptions in prompt, replace with period-appropriate alternatives |
| Jarring continuity | Modify opening/closing state descriptions in video_prompt |

## Iteration Workflow

1. Review identifies issues
2. Locate the problematic shot
3. Analyze the cause (prompt issue / model limitation / parameter issue / logic issue)
4. Modify the corresponding prompt or parameters
5. Regenerate that shot
6. Review again to confirm
