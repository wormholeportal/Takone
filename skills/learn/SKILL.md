---
name: learn
description: Mandatory research and feeling extraction — browse platforms, find references, extract the feeling that makes content scroll-stopping.
---

# Learn — Research & Feeling Extraction

Browse the web to find what works, extract why it works, and bring that feeling into your creation.

**This is not optional research. It is the FIRST STEP of every project.**

## Why Research First?

Creating in a vacuum = generic output. Every great director studies reference material before shooting. You must:
1. See what's trending on the target platform
2. Find content that achieves your target feeling
3. Understand WHY it works (technique, not just content)
4. Bring those techniques into your own creation

## The Feeling Extraction Process

### Step 1: Search for Inspiration

Search the target platform for content in your category:

```
learn_browse(action="search_videos", query="{concept} {mood}", platform="douyin")
learn_browse(action="search_images", query="{concept} aesthetic cinematic")
learn_browse(action="search_videos", query="{concept}", platform="bilibili")
```

### Step 2: Download References

Download the 3-5 best frames/images that capture the feeling you want:

```
learn_download(url="https://...", media_type="image", subfolder="image")
```

### Step 3: Analyze with Vision

Use `analyze_media` on each downloaded reference. Focus on:
- **Emotional impact** — What do you FEEL when you see this? Why?
- **Color mood** — What's the dominant palette? Warm/cool? Saturated/muted?
- **Composition** — Where's the subject? What's the framing?
- **Lighting** — Direction, quality, color temperature?
- **What makes it scroll-stopping?** — Be specific about the technique

### Step 4: Write feeling.yaml

Distill your research into a creative anchor:

```yaml
target_feeling: "The viewer should feel ___"
references:
  - image: "assets/learn/ref_01.png"
    why: "The mist and low contrast create perfect mystery"
  - image: "assets/learn/ref_02.png"
    why: "This color palette — muted teal and amber — is exactly right"
visual_dna:
  color_mood: "muted teal and warm amber, low saturation"
  pacing: "slow reveal, then sudden burst"
  first_3_seconds: "extreme close-up detail, rack focus to reveal scene"
anti_patterns:
  - "no over-processed HDR look"
  - "no generic AI smoothness"
```

## Research Types

| Type | Use Case | Platforms |
|------|----------|-----------|
| Feeling extraction | Find content with your target feeling | Douyin, Bilibili, Xiaohongshu |
| Visual reference | Art style, color, composition | Baidu Image, Google Images |
| Story background | Historical context, story details | Baidu Baike, Zhihu, Wikipedia |
| Technique study | Editing, pacing, transitions | Bilibili, YouTube |

## Tool Usage

### `learn_browse` — Web Research

```
# Search platforms
learn_browse(action="search_videos", query="古风 水墨 短视频", platform="douyin")
learn_browse(action="search_images", query="ink wash cinematic tiger", platform="google_image")
learn_browse(action="search_web", query="武松打虎 原文", platform="baike")

# Browse specific page
learn_browse(action="browse_url", query="https://baike.baidu.com/item/武松打虎")
```

### `learn_download` — Download References

```
learn_download(url="https://...", media_type="image", subfolder="image")
learn_download(url="https://www.bilibili.com/video/BV...", media_type="video", subfolder="video")
```

## Research Principles

- **Feeling over content** — When searching, look for things that FEEL right, not just match the topic
- **3-5 references is enough** — Don't over-research. Find your feeling, then create.
- **Image search auto-downloads** — `search_images` automatically downloads top 3 results with vision analysis
- **Auto-analysis** — All downloads get vision AI analysis in `.analysis.md` sidecar files
- **Direct reference usage** — Downloaded images in `assets/learn/` can be used directly in `reference_images`
- **Research serves creation** — Every search should influence your next creative decision
- **Screenshot fallback** — If downloads fail, browser screenshots are saved as backup

## Asset Organization

```
assets/learn/      # All reference materials flat: images, videos, scripts, notes, analysis files
```

## Research as a Reflex

Beyond the mandatory Stage 1 research, keep researching whenever you need it:

| Situation | Action |
|-----------|--------|
| Unsure about historical details | Search baike |
| Can't visualize the style | Search images |
| Need pacing reference | Search videos on bilibili |
| Found something inspiring | Download it |
| Generated shot doesn't feel right | Search for better references |

Don't overthink it. Don't research everything. But never create in a vacuum.
