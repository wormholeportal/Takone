<p align="center">
  <img src="assets/takone.png" width="160" alt="Takone" />
</p>

<h1 align="center">Takone</h1>

<p align="center">
  <strong>Autonomous AI video director — from script to screen.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &nbsp;&middot;&nbsp;
  <a href="#how-it-works">How It Works</a> &nbsp;&middot;&nbsp;
  <a href="#features">Features</a> &nbsp;&middot;&nbsp;
  <a href="https://github.com/wormholeportal/takone/issues">Issues</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/license-AGPL--3.0-green" alt="License" />
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Status" />
</p>

Takone is an AI agent that **directs the entire video production pipeline autonomously**. Describe your vision, and it handles scriptwriting, storyboarding, image/video generation, quality review, and final assembly — all through a single CLI session.

> *One vision. One take. Takone.*

<br/>

## Quick Start

### Install (recommended)

One command installs everything — Python deps, FFmpeg, Chromium:

```bash
curl -fsSL https://raw.githubusercontent.com/wormholeportal/takone/main/install.sh | bash
```

Then:

```bash
vim ~/.takone/.env    # add your API keys
takone               # launch
```

### Manual

```bash
git clone https://github.com/wormholeportal/takone.git && cd takone
pip install -e ".[all]"
brew install ffmpeg            # or: apt install ffmpeg
playwright install chromium
cp .env.example .env           # add your API keys
takone
```

> **Requires:** Python 3.10+ &nbsp;|&nbsp; FFmpeg &nbsp;|&nbsp; Chromium

<br/>

## How It Works

Takone runs a **multi-step autonomous pipeline** — each step is a skill the AI agent invokes on demand:

```
  Describe your idea
        │
        ▼
  ┌─────────────┐
  │  Scriptwriter │──▶  Emotion curves, character arcs, visual treatment
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Storyboard  │──▶  Shot breakdown, pacing, composition
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Designer    │──▶  Optimized prompts for generation models
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Generator   │──▶  AI image & video generation (Seedream, Seedance, Sora...)
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Reviewer    │──▶  Frame-level quality analysis, auto-iteration
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Assembler   │──▶  FFmpeg compositing, transitions, audio mix
  └──────┬──────┘
         ▼
    Final video
```

The agent decides **what to do and when** — you just provide creative direction.

<br/>

## Features

**Scriptwriting** &nbsp; Emotion-driven narratives with memory anchors, character psychology, and cinematic visual descriptions (200-600 words per scene).

**Storyboarding** &nbsp; Intelligent shot breakdown with breathing rhythm, pacing control, and composition guidance.

**Generation** &nbsp; Multi-provider support — Jimeng/Seedream, Seedance, Minimax, Sora, and more. Automatic prompt optimization per model.

**Quality Review** &nbsp; Vision-model analysis at the frame level. Catches issues before assembly and auto-iterates.

**Assembly** &nbsp; FFmpeg-powered compositing with smart transitions, audio mixing, and multi-platform export (YouTube, Instagram, Douyin, Bilibili, Xiaohongshu).

**Research** &nbsp; Built-in viral video analyzer — scrapes trending content, runs VLM analysis, and generates creative briefs.

<br/>

## Configuration

| File | Purpose |
|------|---------|
| `.env` | API keys — Anthropic, OpenAI, MiniMax, Doubao, Jimeng, etc. |
| `config.yaml` | Model selection, pipeline settings, output preferences |

<br/>

## Tech Stack

| Layer | Providers |
|-------|-----------|
| **LLM** | Claude, MiniMax, OpenAI, Doubao, Moonshot, Qwen |
| **Image** | Jimeng (Seedream), Gemini |
| **Video** | Seedance, Minimax, Sora |
| **Vision** | Doubao, Claude, GPT-4o |
| **Core** | Python, FFmpeg, Playwright |

<br/>

## Project Structure

```
takone/
├── agents/          # Core agent modules
│   ├── director.py  # Main VideoDirector agent (2500 lines)
│   ├── tui.py       # Terminal UI (split screen, spinners)
│   ├── tools.py     # Tool definitions & system prompt
│   ├── config.py    # Configuration & constants
│   └── researcher.py# Viral video research agent
├── core/
│   ├── browser/     # Playwright browser automation
│   ├── image/       # Image generation (Jimeng/Seedream)
│   ├── video/       # Video generation (Seedance, Minimax, Sora)
│   └── vision/      # Vision analysis (Doubao, Claude, GPT-4o)
├── skills/          # Skill templates (markdown)
├── utils/           # FFmpeg, audio utilities
├── site/            # Landing page
├── install.sh       # One-liner installer
└── takone-cli       # CLI entry point (no pip install needed)
```

<br/>

## License [![AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](./LICENSE)

This project is dual-licensed:

- **Open Source:** [AGPL-3.0](LICENSE) — Free to use, modify, and distribute. If you offer this software as a network service, you must release your modifications under the same license.
- **Commercial:** For proprietary use, SaaS deployment, or closed-source integration, a commercial license is available. See [COMMERCIAL.md](COMMERCIAL.md) for details.

Contributions are welcome! By submitting a pull request, you agree to our [Contributor License Agreement](CLA.md).
