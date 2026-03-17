---
name: visualizer/reference
description: Example prompts for each provider
---

# Prompt Reference

## Seedream Image Prompt Examples

### Product Close-up
```
A transparent glass bottle of lemon sparkling water on a rustic wooden table,
golden sunlight streaming through white linen curtains creating dappled shadows,
condensation droplets on the bottle surface, shallow depth of field,
warm color palette, cinematic composition, photorealistic, 8k, masterpiece
```

### Food Photography
```
overhead view of a bowl of colorful poke bowl with fresh salmon, avocado,
edamame, and sesame seeds on a marble countertop, natural side lighting,
food photography style, appetizing, vibrant colors, high detail
```

### Natural Landscape
```
a serene lake at golden hour, mountains in the background reflected in still water,
warm orange and pink sky, lone wooden dock extending into the water,
cinematic wide shot, landscape photography, 8k resolution
```

## Seedance Video Prompt Examples

### Product Showcase
```
A hand slowly picks up a glass bottle of lemon sparkling water from a wooden table,
the camera follows the hand upward, condensation droplets catch the warm sunlight,
smooth slow motion, shallow depth of field, warm cinematic color grading
```

### Pouring Close-up
```
Sparkling lemon water being poured into a clear glass filled with ice cubes and
a slice of lemon, bubbles rising rapidly, camera positioned at 45-degree angle,
extreme close-up, slow motion, studio lighting from left side
```

### Environment Showcase
```
Camera slowly pans across a sunlit balcony with green plants, a small table
with a glass of sparkling water, gentle breeze moving the curtains,
warm afternoon light, peaceful atmosphere, cinematic
```

## Minimax Video Prompt Example

```
A summer afternoon, a hand gently twists open the cap of a lemon sparkling water bottle,
bubbles surge out, close-up shot, slow motion, warm sunlight from the left side,
background blurred, cinematic quality
```

## Consistency Prompt Template

Insert `character_anchors` and `style_anchor` into every prompt:

```
{anchor.bottle}, placed on {scene description},
{lighting description}, {camera description},
{style_anchor}
```

Actual generation:
```
transparent glass bottle with yellow lemon sparkling water and condensation droplets,
placed on a light wooden table next to an open book,
warm golden hour sunlight from left window,
close-up shot at 30-degree angle,
cinematic, warm golden hour, shallow depth of field, film grain, Fujifilm color science
```
