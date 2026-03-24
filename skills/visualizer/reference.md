---
name: visualizer/reference
description: High-quality prompt examples for each platform — use as templates
---

# Prompt Reference — Production Quality Examples

## Jimeng/Seedream Image Prompts

### Example 1: Bedroom Portrait (Photorealistic, Moody)

```
Ultra-realistic cinematic portrait, raw photo. A young East Asian woman sitting on the edge of a messy bed,
long dark hair falling over one shoulder, loose waves, strands catching warm backlight.
Sleepy half-lidded eyes, slightly parted lips, soft natural expression, bare minimal makeup,
natural skin texture with visible pores, slight flush on cheeks.
Wearing an oversized cream knitted sweater slipping off one shoulder, soft ribbed cotton texture,
fabric bunched at wrists. Bare legs tucked underneath.
Dimly lit bedroom: warm tungsten bedside lamp casting golden pool of light, fairy lights on headboard,
rumpled white linen sheets, phone face-down on nightstand, sheer curtains filtering city glow.
Key light: warm tungsten from bedside lamp right. Fill: soft ambient city light from window left.
Rim: subtle warm backlight from fairy lights creating hair halo.
Shot on Sony A7R V, 85mm f/1.4, shallow depth of field, tack sharp on eyes, creamy bokeh background.
Warm color grade, slight desaturation, film grain, intimate mood.
9:16 vertical. No cartoon, no anime, no plastic skin, no over-smoothed, no beauty retouching.
```

### Example 2: Urban Night (Cinematic, Neon)

```
Cinematic low-light portrait, film noir aesthetic. A young woman leaning against a rain-wet brick wall
in a narrow city alley at night. Short messy dark hair, damp from drizzle, strands stuck to forehead.
Tired but magnetic expression, dark eyes reflecting neon, natural skin texture slightly dewy from rain.
Black fitted leather jacket over white ribbed tank top, slight fabric transparency from moisture,
dark cargo pants, chunky silver chain necklace.
Wet asphalt reflecting pink and blue neon signs, steam rising from a grate, graffiti on opposite wall,
blurred taxi passing at alley mouth, puddles catching colored light.
Key: neon pink from sign upper-left. Fill: cool blue ambient from opposite sign. Accent: warm sodium streetlight rim from behind.
High contrast chiaroscuro, deep shadows, mixed color temperature.
Shot on 35mm film, Kodak Vision3 250D, visible grain, 50mm f/1.8.
Moody cinematic color grade, cool shadows, warm highlights. 9:16 vertical.
No cartoon, no anime, no plastic skin, no oversaturated, no beauty retouching.
```

### Example 3: Korean Manhwa Style (韩漫)

```
韩漫画风，韩漫风格的精致线稿+厚涂质感。
一位高颜值御姐，冷俊锐利五官，魅惑眼神，黑色眼球，肌肤冷白细腻，
黑色长直发飘逸，刘海微遮一只眼。
上身黑色蕾丝吊带，半透明材质，搭配深灰色西装外套随意披在肩上，
银色choker项链，小巧耳钉。
昏暗卧室，落地窗外是城市夜景霓虹，暖色台灯打出侧光，
白色床单微皱，墙上有装饰画。
半身构图，轻微仰视视角，强烈的明暗对比，
低饱和色调，精致线条，光影特效，电影氛围感，超高清壁纸画质。9:16竖构图。
```

### Example 4: Mirror Shot (Intimate, Self-Aware)

```
Ultra-realistic intimate portrait, candid iPhone selfie aesthetic. A young woman photographing herself
in a full-length bedroom mirror, phone held at chest level, one hand pushing hair behind ear.
Soft sleepy eyes with slight dark circles, natural unperfect skin, a tiny mole near lip,
messy morning hair — dark brown, shoulder-length, tousled bedhead with flyaway strands.
Oversized white button-down shirt hanging open over black bralette, bare legs,
fabric rumpled and lived-in. Nail polish slightly chipped on fingernails.
Mirror with thin gold frame, reflection showing unmade bed with grey duvet,
warm reading lamp on floor, stack of books, trailing phone charger cable.
Soft natural window light from right, gentle shadows, warm morning tones.
Shot on iPhone 15 Pro, 24mm wide, natural grain, slight lens distortion.
Intimate crop: face + chest in mirror reflection. 9:16 vertical.
No retouching, no plastic skin, no perfect symmetry, no studio perfection.
```

---

## Gemini Image Prompts

### Example 5: Editorial Fashion (JSON Format)

```json
{
  "meta": {
    "quality": "ultra photorealistic, raw photo",
    "resolution": "8K",
    "camera": "Canon EOS R5",
    "lens": "85mm f/1.4",
    "aspect_ratio": "9:16",
    "style": "high-end editorial fashion photography, moody cinematic"
  },
  "subject": {
    "description": "young East Asian woman, early 20s",
    "face": {
      "structure": "oval face, high cheekbones, defined jawline",
      "skin": "natural skin texture, visible pores, fair with warm undertone, slight flush on cheeks",
      "eyes": "dark brown, heavy-lidded, sleepy sensual gaze, catchlights visible",
      "expression": "calm self-assured, soft mysterious smile",
      "makeup": "minimal — soft k-beauty: dewy skin, rosy lip tint, subtle smoky eye"
    },
    "hair": {
      "color": "dark brown with subtle warm highlights",
      "length": "long, past shoulders",
      "style": "center part, loose natural waves",
      "state": "wind-swept strands crossing face, catching backlight"
    }
  },
  "outfit": {
    "top": {
      "type": "fitted black silk camisole",
      "material": "glossy silk, thin spaghetti straps",
      "fit": "body-hugging, slight fabric tension",
      "details": "subtle lace trim at neckline, one strap slipping off shoulder"
    },
    "bottom": "high-waisted black wide-leg trousers, soft wool blend, natural drape",
    "footwear": "black pointed stilettos",
    "accessories": ["thin gold chain necklace", "small hoop earrings", "delicate ring on index finger"]
  },
  "pose": {
    "position": "standing, leaning against door frame, body angled 30 degrees",
    "limbs": "one hand resting on door frame above head, other hand relaxed at side",
    "head": "tilted slightly right, chin lowered",
    "gaze": "direct eye contact through lowered lashes",
    "micro_motion": "subtle weight shift to one hip, fabric settling from movement"
  },
  "environment": {
    "location": "dimly lit apartment hallway",
    "background": ["textured concrete wall", "warm Edison bulb pendant", "out-of-focus doorway leading to bedroom", "coat hooks with draped scarf"],
    "time_of_day": "late evening",
    "atmosphere": "intimate, private, slightly voyeuristic"
  },
  "lighting": {
    "key_light": "warm tungsten Edison bulb from above-left, creating Rembrandt triangle on cheek",
    "fill_light": "soft ambient bounce from white wall on right",
    "rim_light": "subtle warm glow from bedroom doorway behind, creating edge light on hair and shoulder",
    "shadows": "deep but not harsh, gradient falloff",
    "color_temperature": "warm 2700K dominant"
  },
  "camera": {
    "angle": "eye level, very slightly low",
    "depth_of_field": "shallow, creamy bokeh dissolving hallway behind",
    "focus": "tack sharp on near eye"
  },
  "color_palette": {
    "dominant": ["deep charcoal", "warm amber"],
    "accent": ["gold jewelry highlights", "skin warmth"],
    "tone": "warm with cool shadow undertones"
  },
  "negative_prompt": ["cartoon", "anime", "3d render", "plastic skin", "over-smoothed", "beauty retouching", "oversaturated", "flat lighting", "extra fingers"]
}
```

---

## Seedance 1.5 Video Prompts

### Example 6: Mirror Turn-Around (Moody)

```
The video begins with a close-up of a full-length mirror reflecting a dimly lit bedroom —
warm tungsten lamp glow, rumpled bedsheets visible in background.
A woman's silhouette enters frame from right, her reflection appearing in the mirror.
She is wearing a fitted black silk slip dress, long dark hair swaying with movement.
She slowly turns from profile to face the mirror directly,
one hand reaching up to push hair behind her ear.
Camera holds steady, slight push-in toward the mirror reflection.
Her eyes meet the camera through the mirror — direct, confident, unhurried.
Ambient: soft fabric rustling, distant city hum through window, gentle breathing.
Warm cinematic color grade, shallow depth of field, intimate mood.
```

### Example 7: Walking Toward Camera (Confident)

```
A young woman walks slowly toward the camera down a dimly lit apartment hallway.
Warm Edison bulb overhead casts golden pool of light, deep shadows on walls.
She wears a black oversized blazer over white tank top, heels clicking on hardwood floor.
Long hair sways with each step, catching rim light from behind.
Camera positioned low, slight upward angle, slowly tracking backward as she approaches.
Her expression shifts from neutral to a subtle knowing smile as she gets closer.
The video ends with her filling the frame, stopping just before the camera.
Heels clicking on wood floor, fabric rustling, soft ambient room tone.
Slow sensual lo-fi beat, minimal, deep bass undertone.
Cinematic, warm tungsten tones, film grain, 9:16 vertical.
```

### Example 8: Window Morning (Gentle)

```
The video opens on sheer white curtains billowing gently in morning breeze,
soft golden daylight flooding through. Camera slowly pans right to reveal
a young woman sitting on the windowsill, knees drawn up, wearing an oversized white shirt.
She turns her head from window to camera, messy morning hair catching backlight,
sleepy soft expression, natural skin glowing in warm light.
She stretches one arm overhead lazily, fabric riding up slightly.
Camera holds on her face as she smiles — gentle, private, unguarded.
Ambient: birdsong outside, curtain fabric fluttering, distant traffic hum.
No music — pure ambient silence.
Natural daylight, warm tones, intimate candid feel.
```

---

## Style Anchor Examples

### Dark Cinematic Bedroom
```
ultra-realistic cinematic photography, warm tungsten accent lighting, deep shadows,
shallow depth of field, film grain, Kodak Vision3, high contrast chiaroscuro,
dark amber and charcoal palette, intimate mood, natural skin texture visible pores,
NOT cartoon, NOT anime, NOT 3D render, NOT oversaturated, NOT beauty retouching
```

### Bright Natural Lifestyle
```
candid lifestyle photography, natural daylight, soft diffused shadows,
clean warm tones, slight desaturation, 35mm film aesthetic, visible grain,
Instagram-authentic feel, natural skin imperfections, dewy fresh,
NOT studio, NOT airbrushed, NOT plastic, NOT oversharpened
```

### Korean Manhwa (韩漫)
```
韩漫画风，精致线稿+厚涂质感，低饱和冷色调，强烈明暗对比，
精致五官，肌肤冷白细腻，电影氛围感，超高清壁纸画质，
光影特效，禁欲高级感
```
