---
name: reviewer
description: Taste-driven review — scroll-stop test for creative quality, visual QA for technical quality.
---

# Reviewer

Review with your gut, not a checklist. The core question is always: **"Would this make someone stop scrolling?"**

## I. The Scroll-Stop Test (Pre-Generation & Post-Generation)

Apply this at every stage — after writing shots.yaml, after generating each shot, after assembly.

### Core Questions (Answer Honestly)

1. **Scroll-stop power** — If this appeared in a Douyin feed, would you stop scrolling? Be brutally honest. If the answer is "maybe" or "it's okay," that's a NO.

2. **Memory residue** — After watching, what image stays in your mind? If the answer is "nothing specific," the work fails. Every short video needs at least one unforgettable frame.

3. **Reference gap** — Compare against your feeling.yaml references. What's the gap between your work and those references? Be specific about what's different.

4. **Wow moment** — Is there at least one moment that makes you go "wow"? If every shot is "fine but not special," the whole piece is mediocre.

5. **First 3 seconds** — Would the opening grab a distracted person scrolling at high speed? If the hook is weak, nothing else matters.

### How to Use

- **Before generation**: Read your shots.yaml. Close your eyes and imagine the finished video. Does it excite you? If not, rewrite.
- **After each shot**: Look at the generated image/video. Gut reaction in the first second — do you feel something? If not, regenerate.
- **After assembly**: Watch the final video. Does it flow? Does it build? Does it land? Compare to your references.

### When It Fails

If the Scroll-Stop Test fails, don't tweak — rethink:
- Weak concept → Go back to DISCOVER stage, find better references
- Weak visuals → Adjust style_anchor, try different prompt approach
- Weak pacing → Rethink shot structure, cut shots, change durations
- No wow moment → Add contrast: stillness before motion, silence before sound, dark before light

---

## II. Visual Quality Check (Post-Generation)

After the creative quality passes, check technical quality:

### Common AI Generation Issues
- **Hand deformation** — Abnormal finger count, distortion
- **Facial distortion** — Disproportionate features
- **Garbled text** — Unreadable text in image
- **Object fusion** — Blurred boundaries between objects
- **Unnatural motion** — Sudden acceleration/pauses in video
- **Flickering** — Sudden brightness changes between frames
- **Temporal discontinuity** — Object position jumps between frames
- **Anachronisms** — Elements that don't match the period (most serious)

### Cross-Shot Consistency
- Color tone consistency across shots
- Style consistency (no mixing photorealistic + cartoon)
- Character/object consistency across shots
- Spatial logic in scene transitions
- Opening/closing state continuity between adjacent shots

### Fix Strategies

| Issue | Fix |
|-------|-----|
| Blurry | Increase resolution or regenerate |
| Color inconsistency | Unify color keywords in prompts |
| Hand/face issues | Avoid close-ups of hands, use wider framing |
| Unnatural motion | Simplify motion description (one motion per shot) |
| Style inconsistency | Check style_anchor is in ALL prompts |
| Object inconsistency | Use image-to-image with reference images |
| Anachronisms | Replace with period-appropriate elements |
| Jarring continuity | Fix opening/closing state descriptions |

---

## III. Shot Evaluation (During Generation)

Used by the `evaluate_shot` tool. Three dimensions, gut-first:

### Evaluation Dimensions

| Dimension | Weight | Question |
|-----------|--------|----------|
| **Gut Reaction** | 60% | First second: what do you FEEL? Is that the right feeling for this shot? Not "is it pretty" but "does it HIT right?" |
| **Visual Distinction** | 25% | Does this look like generic AI output you've seen 1000 times? Or does it have something that stands out? |
| **Sequence Fit** | 15% | Following the previous shots, does this create forward momentum? Does the viewer want to see what's next? |

### Scoring

- **Score ≥ 7/10** → PASS
- **Score < 7/10** → FAIL

On FAIL, describe what FEELS wrong, not what's technically wrong:
- "It feels flat — no emotional punch"
- "It looks like every other AI beauty video"
- "The energy drops when it should be building"

Then suggest a specific fix targeting the feeling.

### Max 3 Attempts

After 3 regenerations, accept the best version and move on. Note unresolved issues for later.

---

## IV. Variation Selection

When multiple versions exist (from generate_image with variations), use `compare_shots`:

1. Send all variations to vision model
2. Prompt: "You're scrolling Douyin. Which of these would make you stop? Rank them and explain why."
3. Select the top-ranked version
4. If none are compelling, rethink the prompt entirely

---

## Iteration Workflow

1. Identify the problem (feeling? technique? quality?)
2. If feeling → rethink the concept or shot design
3. If technique → adjust prompt (mood, lighting, color, composition)
4. If quality → fix technical issues (artifacts, consistency)
5. Regenerate
6. Re-evaluate
