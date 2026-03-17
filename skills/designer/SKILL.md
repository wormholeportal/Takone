---
name: designer
description: Character and scene reference design for visual consistency across all shots.
---

# Designer

Design character reference sheets and scene reference images for video projects, ensuring visual consistency across all shots.

## Why Reference Images Are Needed

Images generated from pure text prompts result in vastly different appearances for the same character across different shots (facial features, clothing, hair color, etc.).
By first generating character reference images, then using those references to drive each shot's generation (image_to_image), consistency is significantly improved.

## Style Locking (Highest Priority)

**The entire project must use a unified art style.** This is the most common consistency issue — scenes rendered in photorealistic style while characters use cartoon/3D style, creating visual dissonance.

### Style Determination (Model-Generated, the More Detailed the Better)

The art style is **not selected from a preset list**, but rather generated as a **detailed style description** (i.e., `style_anchor`) by the model after comprehensively evaluating the project's theme, mood, audience, and content. The more specific this description, the better. It should cover the following dimensions:

1. **Render Style** — Photorealistic / digital painting / ink wash / 3D / anime / hybrid? To what degree? (e.g., "highly realistic cinematic photography quality" vs. "concept art-leaning digital painting")
2. **Color System** — Overall color temperature, dominant hues, contrast (e.g., "warm golden tones dominant, shadows leaning cyan-blue, high contrast")
3. **Lighting Style** — Natural / artificial / dramatic? Light quality? (e.g., "golden hour natural light, volumetric rays, strong rim lighting from backlight")
4. **Texture & Detail** — Film grain? Smooth CG? Brushstroke feel? (e.g., "subtle film grain, shallow depth of field, lens flare")
5. **Reference Aesthetics** — Close to which visual style? (e.g., "Terrence Malick's naturalistic poetic cinematography", "Studio Ghibli watercolor animation")
6. **Composition Tendency** — Expansive negative space? Dense composition? (e.g., "abundant negative space, low horizon line, sky-dominant frames")
7. **Exclusions** — Explicitly state what styles to avoid (e.g., "NOT cartoon, NOT cute, NOT low-poly, NOT pixel art")

**Example — A Good style_anchor:**

```
cinematic photorealistic, film grain, 2K resolution, golden hour natural lighting,
volumetric god rays, shallow depth of field, warm amber and teal color grading,
high contrast with rich shadows, epic scale compositions, Terrence Malick and
Roger Deakins inspired cinematography, NOT cartoon, NOT 3D render, NOT anime
```

**Example — A Poor style_anchor (too vague):**

```
❌ cinematic, high quality, beautiful
```

### Style Generation Workflow

1. **Analyze the Project** — Read screenplay.yaml, understand the genre, era, mood, and target audience
2. **Generate style_anchor** — Synthesize the above dimensions to produce a 50-100 word detailed English style description
3. **Write to prompts.json** — Save the style_anchor to the `style_anchor` field in prompts.json
4. **Apply Globally** — All subsequent character references, scene references, and every shot's prompt must include the style_anchor

### Style Consistency Rules

- **style_anchor must appear in all prompts** — Including character references, scene references, and every shot
- **Character reference art style must match scenes** — If the style_anchor is photorealistic, characters must never be cartoonish
- **No mixing** — Once the style_anchor is established, all elements must strictly follow it
- **Genre matching** — Characters in serious/epic themes must not be designed in cute/chibi/cartoon styles
- **Exclusions must be explicit** — Use NOT keywords in the style_anchor to exclude unwanted styles

### Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Style dissonance | Photorealistic landscapes, cartoon characters | Include the complete style_anchor in all prompts |
| Character style mismatch | Characters look like "Angry Birds" in a serious story | Add "NOT cute, NOT cartoon, realistic proportions" to style_anchor |
| Inconsistency across shots | Some shots look like photos, others like CG renders | Every prompt must include the full style_anchor without omission |
| style_anchor too vague | "cinematic, high quality" is not specific enough | Cover at least 5 dimensions: render style, color, lighting, texture, exclusions |

## Character Reference Design

### Three-View Sheet (Recommended)

Suitable for most characters. Prompt format:

```
{character base description}, {full style_anchor}, character reference sheet, three views,
front view, three-quarter view, back view, white background, full body,
consistent design, same outfit, same hairstyle
```

### Style Matching Examples

**Correct (full style_anchor + specific character description):**
```
Mythical crimson bird, brilliant red plumage with gold highlights, sharp fierce eyes,
small graceful body, natural proportions, detailed feather texture,
cinematic photorealistic, film grain, golden hour lighting, warm amber tones,
NOT cartoon, NOT cute, NOT round body,
character reference sheet, three views, front view, side view, back view,
white background
```

**Incorrect (missing style_anchor, description too simple):**
```
❌ cute red bird, round body, big eyes, cartoon style
❌ red bird, character sheet (too simple, no style information included)
```

### Five-View Sheet (Complex Characters)

Suitable for characters with rich visual details:

```
{character base description}, {full style_anchor}, character reference sheet, five views,
front, left side, right side, back, three-quarter, turnaround,
white background, full body
```

### Character Reference Key Points

- **aspect_ratio**: Recommended `1:1` or `16:9` (more space for views)
- **White background**: Makes it easier for the model to extract character features
- **Full body**: Ensures complete clothing details
- **consistent design**: Key phrase for ensuring multi-view consistency
- **Must include style_anchor** — Every character prompt must fully reference the style_anchor from prompts.json
- **Consistent exclusions** — NOT keywords from the style_anchor must also appear in character prompts

## Scene Reference Design

Generate reference images for key scenes from specific angles:

- **Establishing shot** (wide establishing shot) — Shows the full scene overview
- **Medium shot** (medium shot) — Shows the area of character activity within the scene
- **Atmospheric detail** (close-up detail) — Shows scene texture and lighting

### Scene Reference Key Points

- **aspect_ratio**: Recommended to use the project's default ratio (e.g., `9:16`)
- Clearly describe lighting, color tone, and time of day (dawn/dusk/night)
- Maintain consistency with the overall color system
- **Art style must match character references**

## Naming Convention

- Characters: `assets/references/{character_id}.png` (e.g., `merchant.png`, `fox_woman.png`)
- Scenes: `assets/references/{scene_id}.png` (e.g., `bamboo_forest.png`, `moonlit_clearing.png`)

## References in prompts.json

Add a `reference_images` array to each shot's `image_prompt`, listing the reference image IDs needed for that shot:

```json
{
  "SHOT_002": {
    "image_prompt": {
      "prompt": "...",
      "reference_images": ["merchant", "bamboo_forest"],
      "aspect_ratio": "9:16"
    }
  }
}
```

The `generate_image` tool will automatically look for corresponding `.png` files under `assets/references/`,
using `image_to_image` mode to generate, ensuring characters and scenes match the reference images.

## Workflow

1. **Analyze the project and generate style_anchor** — Read screenplay.yaml, synthesize genre/era/mood/audience, generate a 50-100 word detailed English style description, and write it to the `style_anchor` field in prompts.json
2. **Analyze characters and scenes** — Read storyboard.yaml, identify all characters and key scenes that appear
3. **Generate character references** — For each character, call `generate_reference(ref_type="character", ref_id="xxx", prompt="...")`
   - The prompt must include the complete style_anchor
   - The prompt must be specific enough: include body type, proportions, clothing materials, colors, expressions, and other details
   - Exclusion items (NOT xxx) from the style_anchor must also be reflected in the character prompt
4. **Generate scene references** — For key scenes, call `generate_reference(ref_type="scene", ref_id="xxx", prompt="...")`
5. **Review and evaluate references** — Confirm all reference images strictly maintain consistent art style matching the style_anchor
6. Add reference_images to each shot's image_prompt in prompts.json
7. Generate keyframes with generate_image (automatically uses reference images + style_anchor)
8. Use check_continuity to verify consistency between adjacent shots
