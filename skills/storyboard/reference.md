---
name: storyboard/reference
description: Storyboard examples and visual storytelling guides
---

# Storyboard Reference

## Example: Lemon Sparkling Water Ad Storyboard

```yaml
shots:
  - id: "SHOT_001"
    scene_ref: "S01"
    shot_type: "CU"
    duration_seconds: 4
    description: "Golden sunlight streams through the folds of white linen curtains onto a light natural wood table surface, creating dappled light and shadow. On the table sits an open hardcover book and a pair of metal-frame sunglasses. The scene is serene and warm."
    camera_angle: "slightly high angle, 30-degree"
    camera_movement: "very slow dolly in"
    lighting: "natural side lighting from left window, warm 5000K"
    composition: "book at left third, sunlight streaks diagonal"
    key_elements: ["sunlight", "linen_curtain", "book", "sunglasses", "wooden_table"]
    color_grading: "warm, +15 highlights, slightly faded shadows"
    gen_strategy: "image_to_video"

  - id: "SHOT_002"
    scene_ref: "S02"
    shot_type: "MS"
    duration_seconds: 5
    description: "A retro white rounded-corner refrigerator door is slowly opened, cold light emanates from inside, and a slender hand reaches in to take a bottle of lemon sparkling water from the middle shelf. Fine condensation droplets cling to the bottle surface."
    camera_angle: "eye-level, frontal"
    camera_movement: "static"
    lighting: "cool fridge interior light + warm ambient from behind"
    composition: "fridge centered, hand enters from right"
    key_elements: ["white_fridge", "hand", "bottle", "condensation"]
    color_grading: "cool interior, warm exterior contrast"
    gen_strategy: "image_to_video"
```

## Shot Pairing Techniques

### Rhythm Control
- **Fast pace**: 2-3 seconds per shot, primarily hard cuts
- **Slow pace**: 4-6 seconds per shot, dissolves/fades
- **Mixed pace**: Slow-slow-fast-fast-slow, creating contrast

### Framing Variation
- **Don't use the same framing consecutively** — Alternate wide-medium-close-wide
- **Use close-ups for emphasis** — Key information / emotional climax
- **Use wide shots for establishing** — New scenes / new environments
- **Use medium shots for transitions** — Bridging between scenes

### AI Generation Best Practices
- Still-life close-ups work best (products, food, nature)
- Slow camera movements are more stable than fast ones
- Avoid describing multiple moving objects in one shot
- Use image_to_video strategy to control the starting frame
