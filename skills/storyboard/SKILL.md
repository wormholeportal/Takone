---
name: storyboard
description: Convert screenplays into shot-by-shot storyboards with precise visual and camera specifications.
---

# Storyboard

Break down the script into a shot-by-shot storyboard with precise shot language, composition rules, and motion descriptions.

## Input Reference

Before designing the storyboard, **the following files must be read first**:
- `screenplay.yaml` — Narrative skeleton, emotion curve, character definitions, **novel-level visual descriptions** (200-600 word visual_description per scene), character visual profiles (visual_definition), and global visual tone (visual_tone). The visual descriptions serve as the bridge from story to shots; the storyboard artist should use them as the basis for designing each shot's composition, movement, and rhythm.

## Shot Types

| Type | English | Use Case |
|------|---------|----------|
| Extreme Wide Shot | Extreme Wide Shot (EWS) | Environment establishment, opening/closing |
| Wide Shot | Wide Shot (WS) | Full body display, spatial relationships |
| Medium Shot | Medium Shot (MS) | Character interaction, product showcase |
| Medium Close-up | Medium Close-up (MCU) | Expression + upper body |
| Close-up | Close-up (CU) | Expression, product detail |
| Extreme Close-up | Extreme Close-up (ECU) | Eyes, hands, texture |
| Point of View | POV | First-person experience |
| Over-the-shoulder | Over-the-shoulder (OTS) | Dialogue, peeping |

## Camera Movement

| Movement | English | Effect |
|----------|---------|--------|
| Static | Static | Stable, solemn |
| Push in | Push in / Dolly in | Focus, tension |
| Pull out | Pull out / Dolly out | Reveal, expand |
| Pan/Tilt | Pan (horizontal) / Tilt (vertical) | Tracking, surveying |
| Tracking | Tracking | Follow motion |
| Crane | Crane | Grand, ceremonial |
| Handheld | Handheld | Realism, tension |
| Orbit | Orbit | Circular showcase |

## Composition Rules

1. **Rule of Thirds** — Place the subject at the intersection of 1/3 lines
2. **Leading Lines** — Use lines to guide the eye to the focal point
3. **Foreground Layers** — Add foreground elements for depth
4. **Negative Space** — Leave space in the direction of motion
5. **Symmetry** — Used for ceremonial feel, product showcase

## Scene Transitions

| Transition | English | Use Case |
|-----------|---------|----------|
| Hard Cut | Cut | Default, fast pacing |
| Dissolve | Dissolve | Time passage, mood transition |
| Fade In/Out | Fade in/out | Beginning/ending |
| Match Cut | Match cut | Two visually related scenes |
| Wipe | Wipe | Playful, retro |
| Jump Cut | Jump cut | Fast pacing, Vlog |

## Shot Continuity Design (Critical)

Each shot must have well-designed start/end transitions to ensure smooth editing:

### opening_state / closing_state

- `opening_state`: The starting visual of this shot's video — should naturally connect with the previous shot's ending
- `closing_state`: The ending visual of this shot's video — should set up the opening of the next shot

**Rule:** SHOT_N's `closing_state` must logically connect with SHOT_N+1's `opening_state`.

Example:
```yaml
- id: SHOT_003
  closing_state: "The merchant turns to look into the distance, sunset reflecting on his face"
- id: SHOT_004
  opening_state: "A distant silhouette under the sunset, gradually approaching"
```

### Transition Matching

| Continuity Relationship | Recommended Transition | Example |
|------------------------|----------------------|---------|
| Continuous action in same scene | Cut | Character turns → Character walks |
| Time passage | Dissolve | Day → Night |
| Spatial jump | Match cut | Hand touches water → Hand touches petals |
| Mood shift | Fade | Joy → Sadness |
| Flashback/Memory | White flash | Present → Past |

### Avoiding Jarring Edits

- **Don't hard-cut between two completely unrelated visuals** — Unless deliberately creating impact
- **Maintain visual element continuity** — Adjacent shots should share at least one common element (color, shape, direction of motion)
- **Consistent motion direction** — If the character moves right in the previous shot, they shouldn't suddenly move left in the next
- **Natural lighting transitions** — Lighting in adjacent shots shouldn't change abruptly (unless intentional light/dark contrast)

## Period & Logic Consistency (Critical)

- **Specify the historical period** — Write the story's era in continuity.time_period
- **List forbidden elements** — List modern/anachronistic elements that should not appear in continuity.forbidden_elements
- **Prop review** — All key_elements must match the historical period (e.g., ancient mythology → no modern ships, plastic products, electronic devices)
- **Architecture review** — Architectural styles in scenes must match the era
- **Costume review** — Character costumes must match the era and cultural setting

## Cinematic Language Translator

**Shots are not about "what to film" but "what to make the audience feel."** Every technical decision for each shot must start from emotional intent, not be chosen arbitrarily by instinct.

### Emotion-to-Technique Mapping Table

| Desired Audience Feeling | Framing | Movement | Rhythm | Lighting |
|-------------------------|---------|----------|--------|----------|
| Loneliness/Insignificance | EWS, tiny figure | Static or very slow push | Slow | Cool side light |
| Tension/Unease | CU/ECU | Handheld slight shake | Quick cuts | High contrast hard light |
| Warmth/Safety | MCU | Slow push in | Medium-slow | Warm soft light |
| Awe/Wonder | EWS + ECU alternating | Crane/large-scale movement | Slow then fast | Dramatic light |
| Mystery/Curiosity | Partial close-up | Slow lateral track | Slow | Dark edge light |
| Release/Freedom | EWS/Aerial | Pull back/Rise | Fast to slow | Bright natural light |
| Intimacy/Empathy | ECU of eyes/hands | Static | Very slow | Soft natural light |
| Oppression/Suffocation | ECU + low angle | Slow continuous push | Slow but sustained | Top light or bottom light |
| Surprise/Twist | Sudden framing change | Rapid movement | Sudden acceleration | Abrupt lighting change |

### Usage Rules

1. **Write `cinematic_intent` first** ("make the audience feel ___"), then consult the table for framing/movement/lighting
2. **Never select technical parameters directly** — If you find yourself thinking "use a close-up" without first thinking "what should this shot make the audience feel," you've skipped the emotional layer
3. **The same emotion can have multiple expressions** — The table is a reference, not a rigid rule. But you must be able to explain "why this choice"

## Rhythm & Breathing Control

**Videos need "breathing" — you can't stuff every second with information, nor leave every second empty.**

### Breathing Model

Each shot has a "breathing attribute":
- **inhale (build-up)** — Quiet, slow, space. Prepares for the next climax. Effect: doubles the climax's impact
- **exhale (release)** — Emotional burst, climax, impact. This is the moment the audience "gets hit"
- **hold (held breath)** — Extreme moment, time seems to stop. The most striking second
- **rest (rest)** — Space for the audience to digest. Must follow dense information segments

### Rhythm Patterns

- **Breathing pattern**: Dense-sparse-dense-sparse (most basic, suits most videos)
- **Wave pattern**: Gradual build → sudden release → gradual build → bigger release (suits emotional progression)
- **Heartbeat pattern**: Strong-weak-strong-weak (suits tension/suspense)

### Inter-Shot Rhythm Relationships

**Shots cannot be designed in isolation —** SHOT_N and SHOT_N+1 must have a clear rhythmic relationship:

- `acceleration` — Faster/more tense/denser than the previous shot
- `deceleration` — Slower/quieter/sparser than the previous shot
- `contrast` — Strong contrast with the previous shot (the most powerful rhythm tool)
- `continuation` — Continues the previous shot's rhythm

**Rhythm Death Warning:**
- 3+ consecutive identical `rhythm_relationship` (especially continuation) = rhythm is dead
- Fast shot immediately followed by fast shot = audience numbness (unless deliberately creating suffocation)
- Slow shot followed by fast shot = doubled impact (use this technique well)
- **The shot before a climax shot (exhale/hold) must be inhale** — No build-up means no payoff

## AI Video Generation Notes

- **Describe the agent of action** — Don't write "the shell moves close to the ear" (who is moving it?); write "the boy lifts the shell to his right ear with his left hand"
- **Objects don't float by themselves** — All object movement must have reasonable contact/grip descriptions; don't write "the shell drifts toward" or "petals fall into the hand"
- **One action per shot** — Describe only one clear primary action within 3-5 seconds; don't have multiple things happening simultaneously
- **Avoid complex actions** — Complex human movements tend to deform in AI-generated video
- **Recommended** — Still-life close-ups, natural landscapes, slow movement, product showcases
- **Use with caution** — Facial expression changes, fine hand movements, multi-person interactions
- **One motion per shot** — Don't describe multiple simultaneous movements in one shot
- **3-5 seconds is optimal** — Current AI video generation achieves the highest quality at 3-5 seconds
