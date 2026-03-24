---
name: storyboard
description: Cinematic reference guide — shot types, camera movements, composition rules, and emotion-to-technique mapping. Used as a lookup when writing shots.yaml.
---

# Storyboard — Cinematic Reference Guide

This is a **reference document**, not a workflow. Consult it when writing shots in `shots.yaml` to choose the right cinematic techniques for your desired feeling.

**The new workflow outputs `shots.yaml` directly (combining script + storyboard + prompts). This guide helps you make better technical choices within that format.**

## Emotion-to-Technique Mapping

**Every shot starts with: "What should the audience FEEL?"** Then look up the technique:

| Desired Feeling | Framing | Movement | Rhythm | Lighting |
|----------------|---------|----------|--------|----------|
| Loneliness | EWS, tiny figure | Static or very slow | Slow | Cool side light |
| Tension/Unease | CU/ECU | Handheld shake | Quick cuts | High contrast hard light |
| Warmth/Safety | MCU | Slow push in | Medium-slow | Warm soft light |
| Awe/Wonder | EWS + ECU alternating | Crane/sweeping | Slow then fast | Dramatic light |
| Mystery/Curiosity | Partial close-up | Slow lateral track | Slow | Dark edge light |
| Freedom/Release | EWS/Aerial | Pull back/Rise | Fast to slow | Bright natural light |
| Intimacy | ECU eyes/hands | Static | Very slow | Soft natural light |
| Oppression | ECU + low angle | Slow push in | Slow sustained | Top or bottom light |
| Surprise/Twist | Sudden framing change | Rapid movement | Sudden acceleration | Abrupt change |

## Shot Types

| Type | Abbreviation | Use Case |
|------|-------------|----------|
| Extreme Wide Shot | EWS | Environment, scale, loneliness |
| Wide Shot | WS | Full body, spatial relationships |
| Medium Shot | MS | Interaction, product showcase |
| Medium Close-up | MCU | Expression + upper body |
| Close-up | CU | Emotion, product detail |
| Extreme Close-up | ECU | Eyes, hands, texture |
| Point of View | POV | Immersion |
| Over-the-shoulder | OTS | Dialogue, perspective |

## Camera Movement

| Movement | Effect |
|----------|--------|
| Static | Stable, solemn, contemplative |
| Push in | Focus, tension, intimacy |
| Pull out | Reveal, expand, release |
| Pan/Tilt | Surveying, tracking |
| Tracking | Follow motion, energy |
| Crane | Grand, ceremonial |
| Handheld | Raw, tense, documentary |
| Orbit | 360° showcase |

## Composition Rules

1. **Rule of Thirds** — Subject at intersection points
2. **Leading Lines** — Guide eye to focal point
3. **Foreground Depth** — Add layers for dimension
4. **Negative Space** — Leave space in motion direction
5. **Symmetry** — Ceremonial, formal, product shots

## Transitions

| Transition | When to Use |
|-----------|------------|
| Cut | Default. Action sequences. Fast pacing. |
| Dissolve | Time passage. Mood shift. |
| Fade | Beginning/ending. Strong emotional break. |
| Match cut | Visual similarity between scenes. |
| Jump cut | Fast pacing. Vlog style. |

## Shot Continuity

Each shot's `video_prompt` should describe:
- **opening_state** — What the frame looks like at the start (connects with previous shot's end)
- **closing_state** — What the frame looks like at the end (sets up next shot's start)

Rule: Shot N's closing → Shot N+1's opening must connect naturally.

Avoid:
- Hard cuts between completely unrelated visuals (unless deliberate)
- Reversed motion direction between adjacent shots
- Abrupt lighting changes (unless intentional contrast)

## AI Video Generation Notes

- **Physical anchoring** — "He lifts the shell" not "the shell moves"
- **One action per shot** — Only one clear primary action in 3-5 seconds
- **Simple motions** — Complex human movements deform in AI video
- **3-5 seconds optimal** — Current AI models work best at this duration
- **Trim aggressively** — A 5s clip often yields only 1-2s of good footage

## Duration & Rhythm

- Hook shots: 1-3s
- Action: 1-2s quick cuts
- Mood: 2-3s establishing shots
- Climax: 4-6s (let it breathe)
- Quiet before climax amplifies impact
- Vary the pace: fast → slow → fast → slower
