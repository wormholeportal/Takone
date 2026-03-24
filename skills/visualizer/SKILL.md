---
name: visualizer
description: Optimize prompts for image/video generation models. Platform-specific strategies for Jimeng/Seedream, Gemini, and Seedance.
---

# Visualizer — Prompt Engineering for AI Generation

Optimize generation prompts for different AI models. Used when writing or refining the `prompt` and `video_prompt` fields in `shots.yaml`.

## Input Reference

Before writing prompts, read:
- `shots.yaml` — Shot feelings, durations, style_anchor, character definitions
- `feeling.yaml` — Target feeling, references, visual DNA

## Universal Prompt Principles

**A prompt is a blueprint, not a wish.** Every word must carry information.

1. **Front-load the subject** — first 10 words define what the model focuses on
2. **Be a photographer, not a poet** — describe as if briefing a camera operator
3. **Specificity beats verbosity** — "85mm f/1.8, golden hour side light" > "beautiful cinematic high quality photo"
4. **Every detail must be concrete** — ❌ "good lighting" ✅ "warm tungsten lamp from upper-right, soft shadows"
5. **style_anchor must appear in EVERY prompt verbatim** — never summarize or shorten it

---

## Narrative Visuals — Prompts That Tell Stories

A technically perfect prompt produces a beautiful, empty frame. A narrative prompt produces a frame that makes the viewer ask "what happened here?" or "what happens next?"

**The difference:**
- Aesthetic prompt: "Beautiful Chinese woman in flowing silk, moonlight, cherry blossoms, ethereal atmosphere" → Viewer thinks: "Pretty." Scrolls past.
- Narrative prompt: "Close-up of an ornate war-council table, two empty chairs, a woman's golden hairpin driven into the wood between them, splitting the grain — scattered wine cups, one still rolling" → Viewer thinks: "What the hell happened here?" Stops scrolling.

**How to add narrative weight to any prompt:**

1. **Include evidence of a story** — not beauty floating in air, but traces on surfaces. A muddy footprint on silk, an unfinished letter with ink still wet, a chair knocked over at a feast table. These details imply a before and an after.

2. **One detail that doesn't belong** — an anachronism, a contrast, something slightly wrong. A warrior's sword with a child's ribbon tied to the hilt. A pristine dress with one bloodstain on the sleeve. These create questions.

3. **Asymmetry over perfection** — Perfect composition = forgettable. A frame where something is off-center, incomplete, or interrupted has tension. One empty seat at a full table. A half-open door. A figure at the edge of frame, almost leaving.

4. **Show the aftermath, not the action** — The moment after the sword falls is more powerful than the swing. The empty room after the argument. The still water after the stone sinks. Aftermath gives the viewer's imagination room to work.

**Apply this to every prompt:** After writing a prompt, ask: "Does this frame ONLY look beautiful, or does it also make the viewer curious about what happened?" If it's only beautiful, add one narrative detail.

---

## Platform 1: Jimeng/Seedream (即梦) — Image Generation

Seedream is bilingual (Chinese + English). Supports both languages natively.

### Prompt Formula (6 Modules, in order)

```
[风格/画质锚定] + [人物描述] + [服装穿搭] + [场景/背景] + [构图/视角] + [画质/氛围增强]
```

### Module 1: Style Anchor (MUST be first)

Place quality/style keywords in the first 10 words:

| Style | Keywords | Use Case |
|-------|----------|----------|
| Photorealistic | `ultra-realistic photograph, DSLR, raw photo` | Real-world scenes |
| Cinematic | `cinematic portrait, film still, movie scene` | Moody, story-driven |
| Korean Manhwa | `韩漫画风, 韩漫风格的精致线稿+厚涂质感` | Illustration style |
| Fashion Editorial | `high-end editorial fashion photography, Vogue style` | Fashion/beauty |

### Module 2: Subject/Character Description

**For photorealistic humans — MUST include ALL of these:**

| Element | Required Detail | Example |
|---------|----------------|---------|
| Skin texture | Natural imperfections | `natural skin texture, visible pores, no beauty retouching` |
| Face structure | Specific features | `high cheekbones, soft jawline, expressive almond-shaped eyes` |
| Hair | Color + length + texture + state | `long dark brown hair, loose waves, wind-blown strands crossing face` |
| Expression | Specific emotion, not generic | `sleepy sensual gaze, slightly parted lips` (not "beautiful face") |
| Body type | Clear proportion | `slender hourglass, athletic, petite curvy` |

**Skin texture keywords (pick 2-3):**
```
natural skin texture, visible pores, subtle freckles, sun-kissed glow,
slightly dewy, porcelain pale, fair with natural flush, warm undertone,
real skin with tiny moles, slight under-eye softness
```

**Anti-smoothing — ALWAYS include to prevent AI plastic look:**
```
no beauty retouching, no plastic skin, no airbrushed texture, no over-smoothed face
```

### Module 3: Outfit/Clothing

**Description formula (5 layers):**
```
[type] + [color] + [material/fabric] + [fit] + [state/dynamic]
```

❌ "wearing a black dress"
✅ "fitted black silk slip dress, thin spaghetti straps, fabric catching warm lamplight, slight wrinkles from sitting, one strap slipping off shoulder"

**Fabric keywords:** `silk, linen, cashmere, ribbed knit, sheer, satin, velvet, mesh, lace, chiffon, patent leather`

**State keywords (make clothing alive):**
```
slightly wrinkled, fabric tension from pose, slipping off shoulder,
wind-caught, catching light on glossy surface, natural drape and fold,
unbuttoned halfway, ridden up from sitting
```

### Module 4: Scene/Environment

**Must include 3+ specific detail elements.** Never just "bedroom" or "street."

| Scene | Required Detail Elements |
|-------|------------------------|
| Bedroom | `messy bedding, fairy lights, warm lamp glow, phone charger on nightstand, sheer curtains` |
| Urban night | `wet asphalt, neon reflections, graffiti walls, bokeh city lights, steam from grate` |
| Café | `warm tungsten bulb, wooden tables, espresso cups, vintage decor, ambient haze` |
| Bathroom | `tiled walls, chrome fixtures, mirror reflection, wet surfaces, steam` |
| Balcony night | `neon glow from city, dim Edison bulb, dark shadows, urban night skyline, potted plant` |

### Module 5: Camera & Composition

**Must include focal length + aperture at minimum.**

| Focal Length | Effect | Use Case |
|-------------|--------|----------|
| 24mm | Wide angle, spatial depth | Full environment, establishing shots |
| 35mm | Natural, close to human eye | Street, lifestyle, environmental portrait |
| 50mm | Standard, no distortion | Universal, half-body, natural |
| 85mm | Portrait golden ratio, bg compression | Face close-up, fashion, beauty |
| 135mm | Strong bokeh, dreamy | Dreamy feel, telephoto portrait |

| Aperture | Depth Effect | Use |
|----------|-------------|-----|
| f/1.2-1.4 | Ultra shallow, creamy bokeh | Dreamy close-up |
| f/1.8-2.0 | Shallow, subject sharp + soft bg | Standard portrait |
| f/2.8-4.0 | Medium, bg recognizable | Environmental portrait |
| f/5.6-8 | Deep, everything sharp | Landscape, group |

**Example:** `shot on Canon EOS R5, 85mm f/1.4, shallow depth of field, tack sharp on subject's eyes`

### Module 6: Lighting System

**MUST specify direction + quality + color temperature. Never just "cinematic lighting."**

**3-Point Lighting Description:**
```
Key Light:  [type] + [direction] + [intensity]    — e.g. "warm tungsten from upper-right"
Fill Light: [type] + [effect]                      — e.g. "gentle ambient bounce from left wall"
Rim/Accent: [type] + [effect]                      — e.g. "subtle golden backlight creating hair halo"
```

| Light Type | Keywords |
|-----------|----------|
| Natural | `golden hour sun, dappled sunlight through leaves, overcast diffused, window light` |
| Artificial | `tungsten lamp, neon glow, ring light, soft-box, direct flash` |
| Quality | `soft diffused, harsh direct, crisp shadows, gentle wrap-around` |
| Direction | `side-lit, backlit, top-down, Rembrandt, split lighting, rim light` |
| Temperature | `warm tungsten (3200K), cool daylight (5600K), mixed neon pink/blue` |
| Effect | `lens flare, light bloom, god rays, volumetric haze, specular highlights` |

### Quality Enhancement Suffix (append to every prompt)

**For photorealistic:**
```
natural skin texture, visible pores, sharp focus, 8K, ultra-detailed, film grain, cinematic color grading
```

**For Korean manhwa (韩漫):**
```
精致线条，肌肤细腻，低饱和色调，光影特效，超高清壁纸画质
```

### Negative Prompt (ALWAYS include)

**Standard negative (use for all photorealistic):**
```
cartoon, anime, illustration, 3d render, CGI, plastic skin, over-smoothed face,
bad anatomy, extra fingers, extra limbs, distorted body, low quality, blurry,
watermark, text, logo, beauty retouching, artificial perfection, airbrushed texture,
oversaturated colors, oversharpened
```

### Seedream Specific Rules
- **30-100 words sweet spot.** Longer degrades quality
- Bilingual: Chinese terms like 水墨感, 留白, 意境 work natively
- Subject in first 10 words
- One or two quality terms enough — don't stack "masterpiece, best quality, ultra HD, 4K, 8K"

---

## Platform 2: Gemini — Photorealistic Image Generation

Gemini responds best to English prompts and excels with camera parameters.

### Two Format Options

**Format A: Natural Language (simple scenes)**
```
[quality anchor], [shot type]. [subject description], [outfit]. [pose/action]. [environment]. [lighting]. [camera params]. [mood]. [technical tags]. [negative prompt].
```

**Format B: JSON Structure (complex scenes — Gemini understands JSON very well)**
```json
{
  "meta": { "quality", "resolution", "camera", "lens", "aspect_ratio", "style" },
  "subject": { "description", "face": {}, "hair": {}, "body": {} },
  "outfit": { "top": {}, "bottom": {}, "footwear", "accessories" },
  "pose": { "position", "limbs", "head", "gaze", "micro_motion" },
  "environment": { "location", "background": [], "time_of_day", "atmosphere" },
  "lighting": { "type", "key_light", "fill_light", "shadows", "color_temperature" },
  "camera": { "angle", "lens", "aperture", "depth_of_field", "focus" },
  "color_palette": { "dominant": [], "accent": [], "saturation", "tone" },
  "negative_prompt": []
}
```

### Gemini Core Rules
1. `natural skin texture, visible pores` is MANDATORY for any human subject
2. Camera parameters (focal length + aperture) dramatically improve results
3. Lighting must have direction, not just "good lighting"
4. Clothing must reach fabric/material level
5. Environment needs 3+ specific detail elements
6. 150-800 words (English), more complex scenes need more words
7. Always include negative prompt

### Gemini Quality Checklist
- [ ] Quality anchor in first 10 words?
- [ ] Skin texture specified (natural skin texture)?
- [ ] Clothing described to fabric level?
- [ ] Lighting has direction?
- [ ] At least one focal length/aperture?
- [ ] 3+ environment detail elements?
- [ ] Pose includes hand/gaze detail?
- [ ] Aspect ratio specified?
- [ ] Negative prompt included?

---

## Platform 3: Seedance 1.5 — Video Generation

Generates video **with synchronized audio**. Prompts have 4 layers.

### Four-Layer Video Prompt Structure

```
Layer 1: [Subject + Visual Action]     — what you SEE
Layer 2: [Dialogue / Key Sound]        — what you HEAR (in quotes)
Layer 3: [Environmental Audio]          — ambient sounds, comma-separated
Layer 4: [Music + Visual Style]         — mood and aesthetic
```

### Core Rules
- Describe motion direction and speed explicitly
- Describe camera movement separately from subject movement
- Opening and closing states MUST connect with adjacent shots
- First-frame image significantly improves consistency
- One main action per shot (3-5 seconds)

### Audio in Prompts
- **Dialogue:** Wrap in quotes with tone: `The woman whispers "来这边" in a soft playful voice`
- **SFX:** Specific: `silk fabric rustling, heels clicking on marble floor, soft breathing`
- **Music:** Describe emotion + style: `slow sensual lo-fi beat, deep bass, minimal`
- **Silence is valid:** Omit audio = natural ambient only

### Video Continuity Template
```
The video begins with [opening state matching previous shot's end],
[main action with direction and speed],
[camera movement described separately],
ending with [closing state matching next shot's opening].
[Dialogue/audio descriptions]. [Style tags].
```

### Motion Realism Rules
- ❌ "The glass moves to the table" → ✅ "She places the glass on the table with her right hand"
- Every motion needs an agent (hand, wind, gravity)
- **Forbidden:** appears, floats, emerges, materializes, hovers
- **Use instead:** picks up, lifts, holds, places, reaches for, sets down

---

## Prompt Quality Checklist (All Platforms)

Before finalizing ANY prompt:
- [ ] Subject in first 10 words?
- [ ] Lighting has direction + quality (not just "cinematic")?
- [ ] Camera/lens specified for photorealistic shots?
- [ ] Skin texture + anti-smoothing for human subjects?
- [ ] Clothing described to fabric + state level?
- [ ] Environment has 3+ specific detail elements?
- [ ] style_anchor included verbatim (not shortened)?
- [ ] No contradictory terms?
- [ ] Negative prompt present?
- [ ] For video: opening state, main action, closing state described?

**If any item fails → fix before generating.**

---

## Common Prompt Mistakes

| Bad | Why | Fix |
|-----|-----|-----|
| `beautiful woman in bedroom` | Zero specificity | Full 6-module description |
| `cinematic lighting` | No direction | `warm tungsten from upper-right, soft shadows on left` |
| `wearing black dress` | No fabric/state | `fitted black silk slip dress, thin straps, fabric catching lamplight` |
| `4K, 8K, masterpiece, best quality, ultra HD` | Keyword stacking, noise | Pick one: `8K, ultra-detailed` |
| `perfect skin, flawless` | Triggers plastic AI look | `natural skin texture, visible pores, subtle imperfections` |
| `nice background` | Meaningless | `messy bedding, warm lamp glow, sheer curtains, phone charger on nightstand` |
| `good looking face` | Vague | `high cheekbones, sleepy sensual gaze, slightly parted lips, minimal makeup` |
