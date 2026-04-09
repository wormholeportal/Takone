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

1. **Study References First** — Look at your feeling.yaml references and downloaded images in assets/learn/. Use `analyze_media` on them to extract visual vocabulary (color palette, lighting style, texture quality).
2. **Select best learn images as style references** — From `assets/learn/image/`, pick 1-3 images that best represent the target visual style. These will be used as `reference_images` in generate_reference calls, enabling img2img generation that inherits the actual visual DNA (colors, textures, lighting, mood) from your research. Text descriptions alone lose too much visual information — the actual images are irreplaceable as style anchors.
3. **Derive style_anchor from references** — Don't invent from scratch. Base your style_anchor on what you actually SEE in the reference images. If the references have muted teal tones with film grain, say that specifically.
4. **Write to shots.yaml / prompts.json** — Save the style_anchor and the selected learn image paths
5. **Apply Globally** — All subsequent character references, scene references, and every shot's prompt must include the style_anchor

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

### Aspect Ratio Selection (Critical!)

The aspect ratio MUST match the number of sub-views to avoid figure distortion. Wrong ratios cause compressed/stretched human proportions:

| Views | Recommended Ratio | Reason |
|-------|------------------|--------|
| 2 views (front + back) | `3:4` | Two standing figures need moderate width |
| 3 views (front + 3/4 + side) | `3:2` | Three standing figures need wide canvas but enough height |
| 4-5 views (turnaround) | `16:9` | Many figures need maximum width |
| Single character portrait | `3:4` or `2:3` | Vertical orientation for standing pose |

**Never use 16:9 for 2-3 views** — it forces the model to stretch figures horizontally or shrink them vertically, resulting in distorted proportions.

### Human Character Prompt Requirements

For human/humanoid characters, the prompt MUST be detailed (100+ words) and include:

1. **Anatomy keywords** — `correct human anatomy, natural body proportions, proper head-to-body ratio (1:7.5), anatomically correct limbs`
2. **Detailed physical description** — height/build, face shape, skin tone, eye color, hair style/color/length, expression
3. **Clothing details** — specific garments, materials, colors, fit, accessories
4. **Full style_anchor** — copied verbatim from prompts.json
5. **View specification** — exact views requested
6. **Quality keywords** — `high quality, high resolution, detailed, sharp focus`
7. **Technical keywords** — `white background, full body, consistent design, same outfit, same hairstyle, same face across all views`
8. **Exclusions** — `NOT distorted, NOT chibi, NOT deformed proportions` + style_anchor exclusions

### Three-View Sheet (Recommended)

Suitable for most characters. Use `aspect_ratio: "3:2"`.

**Correct example (human character, detailed prompt):**
```
A young Asian woman, early 20s, slender build, correct human anatomy, natural body proportions,
proper head-to-body ratio, 165cm tall, oval face, fair skin, long straight black hair
reaching mid-back, gentle smile, dark brown eyes, wearing a fitted black crop top and
high-waisted white leggings, white sneakers, minimalist style,
{full style_anchor here},
character reference sheet, three views, front view, three-quarter view, side view,
white background, full body, high quality, high resolution, detailed, sharp focus,
consistent design, same outfit, same hairstyle, same face across all views,
NOT distorted, NOT chibi, NOT deformed proportions
```

**Incorrect examples:**
```
❌ girl in black top and white pants, character sheet (too vague, no anatomy keywords, no proportions)
❌ beautiful woman, three views, white background (missing details, will cause inconsistency)
```

### Five-View Sheet (Complex Characters)

Suitable for characters with rich visual details. Use `aspect_ratio: "16:9"`.

```
{detailed character description with anatomy keywords}, {full style_anchor},
character reference sheet, five views, front, left side, right side, back, three-quarter,
turnaround, white background, full body, high quality, high resolution,
consistent design, same face, same outfit, same hairstyle,
NOT distorted, NOT deformed proportions
```

### Character Reference Key Points

- **aspect_ratio**: MUST match view count — `3:2` for 3 views, `16:9` for 4-5 views, `3:4` for 2 views
- **Human proportions**: Always include anatomy/proportion keywords to prevent distortion
- **Prompt length**: Must be 100+ words for human characters — short prompts produce low-quality results
- **White background**: Makes it easier for the model to extract character features
- **Full body**: Ensures complete clothing details
- **consistent design**: Key phrase for ensuring multi-view consistency
- **Must include style_anchor** — Every character prompt must fully reference the style_anchor from prompts.json
- **Consistent exclusions** — NOT keywords from the style_anchor must also appear in character prompts
- **Quality keywords**: Always include `high quality, high resolution, detailed, sharp focus`

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

- Characters: `assets/design/{character_id}.png` (e.g., `merchant.png`, `fox_woman.png`)
- Scenes: `assets/design/{scene_id}.png` (e.g., `bamboo_forest.png`, `moonlit_clearing.png`)

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

The `generate_image` tool searches for reference images in this order:
1. `assets/design/{id}.png/.jpg/.jpeg/.webp`
2. `assets/learn/{id}.png/.jpg/.jpeg/.webp`

This means images downloaded via `learn_download` can be used directly as references without copying.
You can also use relative paths: `"reference_images": ["merchant", "learn/style_sample.png"]`

## Workflow

1. **Study references and generate style_anchor** — Read feeling.yaml and analyze reference images. Derive a 50-100 word style_anchor from what you actually see in the references, covering render style, color, lighting, texture, and exclusions. Write to shots.yaml / prompts.json.
2. **Select best learn images for style transfer** — Review all images in `assets/learn/image/` and their `.analysis.md` sidecar files. Pick 1-3 images that best capture the target visual style (color palette, lighting quality, texture, mood). These will be passed as `reference_images` to generate_reference, enabling img2img generation that preserves visual details text cannot capture.
3. **Analyze characters and scenes** — Read shots.yaml, identify all characters and key scenes that appear
4. **Generate character references** — For each character, call `generate_reference(ref_type="character", ref_id="xxx", prompt="...", reference_images=["learn/image/best_ref.png", ...])`
   - The prompt must include the complete style_anchor
   - The prompt must be specific enough: include body type, proportions, clothing materials, colors, expressions, and other details
   - Exclusion items (NOT xxx) from the style_anchor must also be reflected in the character prompt
   - `reference_images`: pass the best learn images so the generated character inherits the real visual style
5. **Generate scene references** — For key scenes, call `generate_reference(ref_type="scene", ref_id="xxx", prompt="...", reference_images=["learn/image/mood_ref.png", ...])`
   - Pass learn images with matching mood, lighting, or color palette as style references
6. **Review and evaluate references** — Confirm all reference images strictly maintain consistent art style matching the style_anchor
7. Add reference_images to each shot's image_prompt in prompts.json
8. Generate keyframes with generate_image (automatically uses reference images + style_anchor)
9. Use check_continuity to verify consistency between adjacent shots
