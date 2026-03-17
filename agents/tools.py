"""Tools definitions and LLM configuration module for Takone.

This module contains all tool/prompt definitions, provider registry,
LLM resolution logic, and the system prompt used by the director agent.
Extracted from director.py for modularity.
"""
from __future__ import annotations

import os
from pathlib import Path

from .config import Colors, DirectorConfig

__all__ = [
    # File type constants
    "IMAGE_EXTS",
    "VIDEO_EXTS",
    "_MAX_IMAGE_SIZE",
    "_MAX_VIDEO_SIZE",
    # Input parsing
    "_resolve_file_path",
    "_parse_user_input",
    "_process_reference_files",
    # Multimodal builders
    "_build_multimodal_anthropic",
    "_build_multimodal_openai",
    # Provider / LLM config
    "PROVIDER_REGISTRY",
    "_resolve_llm_config",
    # Tool definitions
    "TOOLS_ANTHROPIC",
    "_tools_to_openai",
    "TOOLS_OPENAI",
    # System prompt
    "SYSTEM_PROMPT",
]


# ── Reference file input parsing ─────────────────────────────────────

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv'}
_MAX_IMAGE_SIZE = 20 * 1024 * 1024   # 20 MB
_MAX_VIDEO_SIZE = 200 * 1024 * 1024  # 200 MB


def _resolve_file_path(token: str) -> Path | None:
    """Resolve a token to a real file path, handling shell escapes.

    Tries the original path first, then strips shell escape backslashes
    (e.g. \\~ → ~) which terminals often insert when copying paths.
    Returns the resolved Path if the file exists, otherwise None.
    """
    candidates = [Path(token).expanduser()]
    # Also try stripping shell escape backslashes (e.g. \~ \( \) \  etc.)
    unescaped = token.replace("\\", "")
    if unescaped != token:
        candidates.append(Path(unescaped).expanduser())
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def _parse_user_input(raw_input: str) -> tuple[str, list[dict]]:
    """Parse user input, extracting file paths mixed with text.

    Returns (text_content, detected_files) where detected_files is:
    [{"path": Path, "type": "image"|"video", "original": str}, ...]
    """
    tokens = raw_input.split()
    text_parts = []
    files = []

    for token in tokens:
        # Check suffix on the raw token (works even with shell escapes)
        suffix = Path(token).suffix.lower()

        if suffix in IMAGE_EXTS or suffix in VIDEO_EXTS:
            resolved = _resolve_file_path(token)
            if resolved:
                ftype = "image" if suffix in IMAGE_EXTS else "video"
                # Size check
                size = resolved.stat().st_size
                limit = _MAX_IMAGE_SIZE if ftype == "image" else _MAX_VIDEO_SIZE
                if size > limit:
                    limit_mb = limit // (1024 * 1024)
                    size_mb = size / (1024 * 1024)
                    print(f"  {Colors.YELLOW}⚠ File too large, skipping: {resolved.name} ({size_mb:.0f}MB, limit {limit_mb}MB){Colors.ENDC}")
                    text_parts.append(token)
                else:
                    files.append({"path": resolved, "type": ftype, "original": token})
            else:
                print(f"  {Colors.YELLOW}⚠ File not found, skipping: {token}{Colors.ENDC}")
                text_parts.append(token)
        else:
            text_parts.append(token)

    return " ".join(text_parts), files


def _process_reference_files(
    files: list[dict],
    project_dir: Path | None,
    num_video_frames: int = 4,
) -> list[dict]:
    """Process reference files into base64-encoded image blocks.

    Returns list of dicts:
    [{"base64": str, "media_type": str, "label": str}, ...]
    For videos, returns multiple entries (one per extracted frame).
    Also copies files to project's assets/references/user/.
    """
    import base64 as b64mod

    results = []
    user_ref_dir = None
    if project_dir:
        user_ref_dir = project_dir / "assets" / "references" / "user"
        user_ref_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        fpath: Path = f["path"]
        ftype: str = f["type"]

        # Copy to project
        if user_ref_dir:
            dest = user_ref_dir / fpath.name
            # Avoid overwriting by appending a suffix
            if dest.exists():
                stem = fpath.stem
                suffix = fpath.suffix
                i = 1
                while dest.exists():
                    dest = user_ref_dir / f"{stem}_{i}{suffix}"
                    i += 1
            shutil.copy2(fpath, dest)

        if ftype == "image":
            with open(fpath, "rb") as fp:
                data = b64mod.b64encode(fp.read()).decode()
            _MIME_MAP = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif",
                ".bmp": "image/bmp", ".tiff": "image/tiff",
            }
            media_type = _MIME_MAP.get(fpath.suffix.lower(), "image/jpeg")
            results.append({
                "base64": data,
                "media_type": media_type,
                "label": fpath.name,
            })

        elif ftype == "video":
            # Extract key frames via FFmpeg
            try:
                from core.vision.base import BaseVision
                frames = BaseVision.extract_frames(fpath, num_video_frames)
            except Exception:
                frames = []

            if not frames:
                print(f"  {Colors.YELLOW}⚠ Failed to extract video frames (FFmpeg required): {fpath.name}{Colors.ENDC}")
                continue

            for frame in frames:
                with open(frame, "rb") as fp:
                    data = b64mod.b64encode(fp.read()).decode()
                results.append({
                    "base64": data,
                    "media_type": "image/jpeg",
                    "label": f"{fpath.name} (frame)",
                })

            # Cleanup temp frames
            for frame in frames:
                try:
                    frame.unlink()
                except Exception:
                    pass

    return results


def _build_multimodal_anthropic(text: str, images: list[dict]) -> list:
    """Build Anthropic multimodal content array."""
    content = []
    for img in images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["media_type"],
                "data": img["base64"],
            },
        })
    hint = (
        "[User provided reference materials (images above). Please analyze these reference materials "
        "for style, color, composition, character features, etc., and incorporate these reference "
        "characteristics into subsequent creative work. Reference materials saved to assets/references/user/.]\n\n"
    )
    content.append({"type": "text", "text": hint + text})
    return content


def _build_multimodal_openai(text: str, images: list[dict]) -> list:
    """Build OpenAI multimodal content array."""
    hint = (
        "[User provided reference materials (images below). Please analyze these reference materials "
        "for style, color, composition, character features, etc., and incorporate these reference "
        "characteristics into subsequent creative work. Reference materials saved to assets/references/user/.]\n\n"
    )
    content = [{"type": "text", "text": hint + text}]
    for img in images:
        data_url = f"data:{img['media_type']};base64,{img['base64']}"
        content.append({
            "type": "image_url",
            "image_url": {"url": data_url},
        })
    return content


# ── Provider registry ─────────────────────────────────────────────────
# provider_name → (protocol, default_base_url)

PROVIDER_REGISTRY: dict[str, tuple[str, str | None]] = {
    "claude":   ("anthropic", None),
    "minimax":  ("openai",    "https://api.minimax.io/v1"),
    "openai":   ("openai",    None),
    "moonshot": ("openai",    "https://api.moonshot.cn/v1"),
    "doubao":   ("openai",    "https://ark.cn-beijing.volces.com/api/v3"),
    "qwen":     ("openai",    "https://dashscope.aliyuncs.com/compatible-mode/v1"),
}


def _resolve_llm_config(config: DirectorConfig) -> tuple[str, str, str, str | None]:
    """Resolve provider name → (protocol, api_key, model, base_url).

    Returns: (protocol, api_key, model, base_url)
    """
    provider = config.llm.provider.lower()

    if provider not in PROVIDER_REGISTRY:
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. "
            f"Available: {list(PROVIDER_REGISTRY.keys())}"
        )

    protocol, default_base = PROVIDER_REGISTRY[provider]

    # Resolve API key and model based on provider
    key_map = {
        "claude":   (config.llm.claude_api_key or os.getenv("ANTHROPIC_API_KEY", ""),
                     config.llm.claude_model),
        "minimax":  (config.llm.minimax_api_key or os.getenv("MINIMAX_API_KEY", ""),
                     config.llm.minimax_model),
        "openai":   (config.llm.openai_api_key or os.getenv("OPENAI_API_KEY", ""),
                     config.llm.openai_model),
        "moonshot": (config.llm.openai_api_key or os.getenv("MOONSHOT_API_KEY", ""),
                     config.llm.openai_model),
        "doubao":   (config.llm.ark_api_key or os.getenv("ARK_API_KEY", ""),
                     config.llm.ark_model),
        "qwen":     (config.llm.openai_api_key or os.getenv("QWEN_API_KEY", ""),
                     config.llm.openai_model),
    }

    api_key, model = key_map[provider]
    if not api_key:
        env_var = {
            "claude": "ANTHROPIC_API_KEY",
            "minimax": "MINIMAX_API_KEY",
            "openai": "OPENAI_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "doubao": "ARK_API_KEY",
            "qwen": "QWEN_API_KEY",
        }[provider]
        raise ValueError(f"Missing {env_var}. Please configure in .env file")

    return protocol, api_key, model, default_base


# ── Tool definitions (Anthropic format, also used to derive OpenAI format) ──

TOOLS_ANTHROPIC = [
    {
        "name": "save_file",
        "description": (
            "Save a YAML or JSON file to the project directory. "
            "Use this whenever you have generated enough content for a file. "
            "Supported files: screenplay.yaml, storyboard.yaml, prompts.json, review.yaml."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename to save (e.g. 'screenplay.yaml', 'storyboard.yaml', 'prompts.json')",
                },
                "content": {
                    "type": "string",
                    "description": "The complete file content as a string (YAML or JSON format)",
                },
                "message": {
                    "type": "string",
                    "description": "Brief description of what was saved (shown to user)",
                },
            },
            "required": ["filename", "content", "message"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read an existing project file to review its content before updating."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename to read from the project directory",
                },
            },
            "required": ["filename"],
        },
    },
    {
        "name": "load_skill",
        "description": (
            "Load skill knowledge on demand. Call this when you need detailed guidance.\n\n"
            "Available skills and files:\n"
            "- pipeline/SKILL.md — Pipeline overview, stage routing, quality gates\n"
            "- scriptwriter/SKILL.md — Screenplay methodology, platform adaptation\n"
            "- scriptwriter/template.md — screenplay.yaml schema (MUST load before saving)\n"
            "- scriptwriter/reference.md — Example scripts, style guides\n"
            "- storyboard/SKILL.md — Shot types, camera language, composition\n"
            "- storyboard/template.md — storyboard.yaml schema (MUST load before saving)\n"
            "- storyboard/reference.md — Storyboard examples\n"
            "- visualizer/SKILL.md — Provider-specific prompt optimization\n"
            "- visualizer/template.md — prompts.json schema (MUST load before saving)\n"
            "- visualizer/reference.md — Example prompts for each provider\n"
            "- designer/SKILL.md — Character/scene reference design for consistency\n"
            "- reviewer/SKILL.md — Quality criteria, common issues\n"
            "- reviewer/template.md — review.yaml schema (MUST load before saving)\n\n"
            "Tip: Load the relevant template.md BEFORE saving any file to ensure correct schema."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "Skill name",
                    "enum": ["pipeline", "scriptwriter", "storyboard", "visualizer", "designer", "reviewer"],
                },
                "file": {
                    "type": "string",
                    "description": "File to load",
                    "enum": ["SKILL.md", "template.md", "reference.md"],
                },
            },
            "required": ["skill", "file"],
        },
    },
    {
        "name": "generate_reference",
        "description": (
            "Generate character reference sheet or scene reference images for visual consistency. "
            "Character refs: multi-view on single image (front/side/back). "
            "Scene refs: key environment from specific angle. "
            "Saved to assets/references/. Must be done BEFORE shot generation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ref_type": {
                    "type": "string",
                    "enum": ["character", "scene"],
                    "description": "'character' for character reference sheet, 'scene' for scene reference",
                },
                "ref_id": {
                    "type": "string",
                    "description": "Reference ID (e.g. 'merchant', 'fox_woman', 'bamboo_forest')",
                },
                "prompt": {
                    "type": "string",
                    "description": "Generation prompt for the reference image",
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["1:1", "9:16", "16:9", "3:4", "4:3"],
                    "description": "1:1 for character sheets, 16:9 for scene panoramas, 9:16 for portrait scene refs (default: 1:1)",
                },
            },
            "required": ["ref_type", "ref_id", "prompt"],
        },
    },
    {
        "name": "generate_image",
        "description": (
            "Generate a key frame image for a specific shot using Seedream. "
            "The image will be saved to assets/images/. "
            "Automatically: 1) loads reference_images from prompts.json for character/scene consistency, "
            "2) appends style_anchor from prompts.json for global style consistency. "
            "Use this after prompts.json and reference images are ready."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "shot_id": {
                    "type": "string",
                    "description": "Shot ID (e.g. 'SHOT_001')",
                },
                "prompt": {
                    "type": "string",
                    "description": "Image generation prompt (or leave empty to use prompts.json)",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "Aspect ratio (default: from project config)",
                    "enum": ["1:1", "9:16", "16:9", "3:4", "4:3"],
                },
            },
            "required": ["shot_id"],
        },
    },
    {
        "name": "generate_video",
        "description": (
            "Generate a video clip for a specific shot using Seedance. "
            "Can generate from text or from a first-frame image. "
            "The video will be saved to assets/videos/. "
            "Automatically injects opening_state/closing_state from prompts.json "
            "for shot-to-shot continuity, and appends style_anchor for style consistency."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "shot_id": {
                    "type": "string",
                    "description": "Shot ID (e.g. 'SHOT_001')",
                },
                "prompt": {
                    "type": "string",
                    "description": "Video generation prompt (or leave empty to use prompts.json)",
                },
                "use_first_frame": {
                    "type": "boolean",
                    "description": "Use generated key frame as first frame (default: true if image exists)",
                },
                "duration_seconds": {
                    "type": "number",
                    "description": "Video duration in seconds (default: 5)",
                },
            },
            "required": ["shot_id"],
        },
    },
    {
        "name": "analyze_media",
        "description": (
            "Send an image or video to Vision API (GPT-4o or Claude) for analysis. "
            "Use this for reviewing generated content quality."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to image or video file relative to project (e.g. 'assets/images/shot_001.png')",
                },
                "prompt": {
                    "type": "string",
                    "description": "Analysis prompt (what to look for)",
                },
            },
            "required": ["file_path", "prompt"],
        },
    },
    {
        "name": "check_continuity",
        "description": (
            "Check visual continuity between two shots using vision AI. "
            "Compares two keyframe images and reports inconsistencies in "
            "character appearance, lighting, color grading, and spatial logic. "
            "Use after generating keyframes to verify consistency."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "shot_id_a": {
                    "type": "string",
                    "description": "First shot ID (e.g. 'SHOT_002')",
                },
                "shot_id_b": {
                    "type": "string",
                    "description": "Second shot ID (e.g. 'SHOT_006')",
                },
            },
            "required": ["shot_id_a", "shot_id_b"],
        },
    },
    {
        "name": "search_reference",
        "description": (
            "Search for trending/viral videos online using Playwright browser. "
            "Useful for finding reference videos and analyzing their techniques."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g. 'lemon sparkling water ad viral')",
                },
                "platform": {
                    "type": "string",
                    "description": "Platform to search on",
                    "enum": ["douyin", "bilibili", "xiaohongshu", "youtube"],
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_assets",
        "description": "List all generated assets (images and videos) in the project.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "assemble_video",
        "description": (
            "Assemble generated video clips into a final complete video using FFmpeg. "
            "By default, automatically reads storyboard.yaml to determine shot order, "
            "per-shot trims (trim_start/trim_end/use_duration), and per-shot transitions "
            "(transition_out). This means you usually just call assemble_video() with no "
            "arguments and it will produce a properly edited video. "
            "Image-only shots (title cards) are auto-converted to still videos. "
            "Output is saved to output/final.mp4."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "shot_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of shot IDs. If empty, reads from storyboard.yaml or auto-detects.",
                },
                "trims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "number"},
                            "end": {"type": "number"},
                        },
                    },
                    "description": "Override per-clip trims. If not provided, reads trim_start/trim_end/use_duration from storyboard.yaml.",
                },
                "transition": {
                    "type": "string",
                    "description": "Global transition override. If not set, uses per-shot transition_out from storyboard.yaml.",
                    "enum": [
                        "none", "fade", "dissolve",
                        "wipeleft", "wiperight", "wipeup", "wipedown",
                        "slideleft", "slideright",
                        "circleopen", "circleclose",
                        "radial", "pixelize",
                        "smoothleft", "smoothright",
                    ],
                },
                "transition_duration": {
                    "type": "number",
                    "description": "Global transition duration override (default: 0.5s)",
                },
                "auto_from_storyboard": {
                    "type": "boolean",
                    "description": "Auto-read storyboard.yaml for shot order, trims, transitions (default: true)",
                },
                "output_filename": {
                    "type": "string",
                    "description": "Output filename (default: 'final.mp4')",
                },
            },
        },
    },
    {
        "name": "validate_before_generate",
        "description": (
            "Run pre-generation validation checks on prompts.json, screenplay.yaml, and storyboard.yaml. "
            "Checks: 1) narrative_beats existence and structure, 2) pacing monotony, "
            "3) style_anchor quality, 4) reference_images existence, "
            "5) opening/closing state continuity, 6) prompt specificity. "
            "Returns a detailed report of issues found. "
            "MUST be called before starting any generate_image/generate_video calls."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "add_audio_track",
        "description": (
            "Add background music and/or voiceover to the assembled video. "
            "Accepts a music file path (relative to project, e.g., 'assets/audio/bgm.mp3') "
            "and/or voiceover text. Music is automatically trimmed to video length with fade-out. "
            "When both music and voiceover are provided, music is ducked during speech. "
            "Output replaces or creates output/final_with_audio.mp4."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "music_path": {
                    "type": "string",
                    "description": "Path to music file relative to project dir (e.g., 'assets/audio/bgm.mp3')",
                },
                "music_volume": {
                    "type": "number",
                    "description": "Music volume 0.0-1.0 (default: 0.4)",
                },
                "video_path": {
                    "type": "string",
                    "description": "Path to video file relative to project dir (default: 'output/final.mp4')",
                },
                "output_filename": {
                    "type": "string",
                    "description": "Output filename (default: 'final_with_audio.mp4')",
                },
            },
        },
    },
]


def _tools_to_openai(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool format to OpenAI function calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


TOOLS_OPENAI = _tools_to_openai(TOOLS_ANTHROPIC)


# ── System prompt ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a professional AI video director, specializing in transforming creative ideas into high-quality short videos.

## How You Work

You learn about the user's video concept through natural conversation, then autonomously drive the entire production pipeline.
You are not an assembly line — you are a director with creative judgment. **Quality is your bottom line — you would rather spend more time polishing than produce rough work.**

## The Director's Three-Layer Thinking

Every creative decision you make must go through three layers of thinking, **strictly in order**:

**Layer 1: Emotional Intent (WHY)**
- What should the audience feel from this video?
- At this specific moment, where should the audience's emotion be on the curve?

**Layer 2: Cinematic Tools (HOW)**
- What cinematic language conveys this emotion? (shot size, camera movement, lighting, rhythm)
- Consult the "Cinematic Language Translator" in storyboard SKILL.md to reverse-engineer technical approach from emotion

**Layer 3: Visual Content (WHAT)**
- What exactly is in the frame? Colors, objects, characters, actions
- This is the last thing to decide, not the first

**Never start from Layer 3.** If you find yourself thinking "this shot should have a cherry blossom tree" without first asking "what should this shot make the audience feel," you have skipped the first two layers. Go back to Layer 1.

## Warning: Most Important Principle — Every Step Must Include Reflection, Evaluation, and Iteration

**Absolutely no "single-pass" work** — You cannot generate screenplay.yaml and immediately move to storyboard.yaml, nor generate storyboard.yaml and jump straight to prompts.json. After generating each file, you must:

1. **Use read_file to read the file you just saved**
2. **Check against reflection/evaluation criteria item by item** (load the reviewer skill to get evaluation criteria)
3. **Identify at least 2-3 areas for improvement** (no file is perfect on the first pass)
4. **Revise and save again**
5. **Use read_file again to confirm the changes took effect**
6. **Only proceed to the next stage after confirming no critical issues remain**

This is not a suggestion — it is mandatory. If you skip reflection and jump to the next step, the generated video quality will be extremely poor.

## Conversation and Creative Workflow

### Step 1: Understand Requirements
- What type? What platform? What style? How long? Any references?
- Even if the user gives just one sentence, you expand and fill in the gaps yourself

### Step 0: Emotional Blueprint (Before Writing Any Scenes!)
1. Based on the user's concept, first design the **emotion_curve** — the emotional intensity curve for the entire video
   - Mark 5-8 time points with emotional intensity (0-10) and emotion type
   - Must have rises and falls — flat lines are forbidden. There must be a valley before the climax (contrast amplifies impact)
2. Design 2-3 **memory_points** — moments the audience cannot forget
   - Each memory point = an extreme visual + emotional combination
   - Not just "beautiful," but "lingers in your mind long after watching"
   - The entire story revolves around memory points
3. Define **characters** psychology for each character:
   - inner_desire (inner longing, not external goals)
   - core_conflict (the contradiction blocking the desire)
   - arc (internal transformation from ___ to ___)
   - signature_detail (one specific detail representing the character's soul)
4. These three elements are the "foundation" of all subsequent creative work — without them, you are building on sand

### Step 2: Write the Script (Must Iterate)
1. load_skill("scriptwriter", "SKILL.md") + load_skill("scriptwriter", "template.md") to load scriptwriting methodology and YAML schema
2. **First define emotion_curve + memory_points + characters, then define narrative_beats, and finally write scenes** (this order is critical!)
   - Common structures: hook → setup → development → climax → resolution
   - Advertising: hook → pain_point → solution → cta
   - Tutorial: hook_result → setup → step_by_step → recap
3. Each beat must be tagged with pacing (fast/medium/slow/building) and target_duration_seconds
4. Duration allocation rules:
   - **hook**: 1-5 seconds (shorter is better — lead with the most striking visuals)
   - **setup**: 15-20% of total video length
   - **development**: 40-60% (core content, tightest pacing)
   - **climax**: 10-20% (not the shortest beat, but the "slowest" beat — let the audience fully absorb it)
   - **resolution**: 10-15%
5. All scenes must link to a beat via beat_ref — a scene without a beat association is a wasted scene and must be removed
6. Write screenplay.yaml and save_file
7. **[Mandatory Reflection]** Immediately read_file("screenplay.yaml") and self-check against these dimensions:
   - **Creative Impact (Highest Priority)**:
     - Does emotion_curve have genuine rises and falls? Is there a "valley → peak" contrast?
     - Are memory_points striking enough? "What will linger in the viewer's mind after watching?"
     - Do characters have psychological arcs (inner_desire + arc)? Or just appearance descriptions + actions?
   - **Narrative Structure**:
     - Are there narrative_beats? Is there a hook and climax?
     - Is there a strong hook in the first 3 seconds? Can it grab the audience?
     - Does the narrative have ups and downs? Suspense, twists, surprises? Or is it a flat chronological account?
     - Are there wasted scenes? Does every scene advance the narrative? Does each have a beat_ref?
   - **Rhythm and Breathing**:
     - Is duration allocation reasonable? Does pacing vary between beats?
     - Does information density have a wave pattern (dense-sparse-dense-sparse)? Or constant throughout?
   - **Consistency**: Period/logic consistency — do props, architecture, costumes, and transportation match the story's setting?
   - **Visual Description Quality**:
     - Is each scene's visual_description a coherent prose passage (200-600 words)? Not fragmented short phrases?
     - After reading the description, can you close your eyes and "see" the image? Are there parts too vague to visualize?
     - Are colors specific (cobalt blue/burnt sienna/pale yellow)? Are positions precise (at the right-third line of the frame)?
     - Is the same character described consistently across scenes, matching characters.visual_definition?
     - Do adjacent scenes' temporal_change (closing_state → opening_state) flow naturally?
     - Does visual_description use YAML `>` folded scalar (not `|`)?
8. **Identify issues, revise screenplay.yaml, and save again**
9. read_file again to confirm improvements
10. Present the final script highlights to the user and wait for confirmation

### Step 3: Storyboard Refinement (Must Iterate)
1. load_skill("storyboard", "SKILL.md") + load_skill("storyboard", "template.md")
2. Generate storyboard.yaml from screenplay.yaml (with detailed visual descriptions). **Each shot must include**:
   - `cinematic_intent` — **Most important**: "Make the audience feel ___" — write this first, then reverse-engineer shot size/movement/lighting
   - `emotional_intensity` — 0-10, corresponding to emotion_curve (3 consecutive identical values = flat line = needs revision)
   - `breathing` — inhale/exhale/hold/rest (must be inhale before climax)
   - `rhythm_relationship` — acceleration/deceleration/contrast/continuation (3 consecutive continuation = rhythm death)
   - `memory_point_ref` — if this is a memory anchor shot, reference the MP id
   - `beat_ref` — which narrative beat this shot belongs to (required, must correspond to screenplay's narrative_beats)
   - `pacing_intent` — fast/medium/slow, determines shot duration and editing rhythm
   - `cut_on` — action/emotion/rhythm/visual_match, determines edit point type
   - `trim_start`/`trim_end`/`use_duration` — trimming parameters automatically used during assembly
   - `transition_out` — transition type from this shot to the next (automatically used during assembly)
3. save_file to save storyboard.yaml
4. **[Mandatory Reflection]** Immediately read_file("storyboard.yaml") and check:
   - **Emotion and Rhythm (Highest Priority)**:
     - Does each shot have a cinematic_intent? Is it derived from emotion or chosen arbitrarily?
     - Does emotional_intensity have variation? 3 consecutive identical values = flat line = needs revision
     - Does breathing alternate? Is there "inhale" before the climax?
     - Does rhythm_relationship avoid consecutive "continuation"?
   - **Structure**:
     - Does every shot have a beat_ref? Does it match screenplay's narrative_beats?
     - Does pacing_intent vary? (All shots being medium = no rhythm)
   - **Continuity**:
     - Does every shot have opening_state and closing_state?
     - Do adjacent shots' closing_state → opening_state flow coherently?
   - **Technical**:
     - Do all key_elements match the period setting?
     - Are transitions appropriate? Hard cuts for hooks, dissolve/fade for emotional segments?
     - Is use_duration allocation reasonable? Hook shots should not exceed 3 seconds; climax shots can be longer
5. **Identify issues, revise storyboard.yaml, and save again**
6. read_file again to confirm

### Step 4: Prompt Design (Must Iterate)
1. load_skill("visualizer", "SKILL.md") + load_skill("visualizer", "template.md")
2. load_skill("designer", "SKILL.md") to determine style_anchor strategy
2.5. **read_file("screenplay.yaml") to get detailed visual descriptions (visual_description)** as core material for prompts
3. **First establish the style_anchor** (a detailed 50-100 word art style description), write it into prompts.json
4. Write prompts for each shot — every shot must specify reference_images — then save_file
5. **[Mandatory Reflection]** Immediately read_file("prompts.json") and check:
   - Is style_anchor detailed enough? Does it cover rendering style, color palette, lighting, texture, exclusions?
   - Does each prompt fully include style_anchor?
   - Is the same character described consistently across different prompts?
   - Does video_prompt include opening_state and closing_state descriptions?
   - Do reference_images cover all recurring characters/scenes?
   - Are there any anachronistic element descriptions?
6. **Identify issues, revise prompts.json, and save again**
7. read_file again to confirm

### Step 5: Design Reference Images
1. Based on the reference_images list in prompts.json, use generate_reference to create each one
2. Use ref_type="character" for character reference sheets, ref_type="scene" for scenes
3. After generation, immediately use analyze_media to verify the reference image style matches style_anchor

### Step 6: Pre-Generation Final Review
1. **Call validate_before_generate** — this is a code-level quality gate; generation cannot proceed without passing
2. If there are blocking issues, fix them and call again
3. Only enter the generation phase after passing

### Step 7: Shot-by-Shot Generation
1. Call generate_image one by one to create keyframes (code automatically injects style_anchor + reference images)
2. After each generation, use analyze_media for a quick check
3. After confirming keyframes, call generate_video
4. After completion, use check_continuity to verify consistency between adjacent shots

### Step 8: Final Assembly
1. Call assemble_video directly (auto_from_storyboard is enabled by default). The code automatically handles:
   - Reading storyboard.yaml, ordering shots by storyboard sequence (not filename order)
   - Automatically applying each shot's trim_start/trim_end/use_duration to extract the best segments
   - Using the storyboard-defined transition_out at each cut point (hard cut/dissolve/fade)
   - Automatically converting image_only shots (e.g., title cards) to static videos of specified duration
2. No need to manually pass trims or transitions — everything is read from storyboard.yaml
3. If there is background music, use add_audio_track to mix it into the final video

## Creative Principles

- **Emotion First** — For every creative decision, first ask "what should the audience feel right now," then ask "what is the visual." Three-layer thinking: WHY → HOW → WHAT
- **Memory Point Driven** — First design 2-3 unforgettable moments for the audience; the story revolves around them. A work without memory points = forgotten after watching
- **Breathing Room** — Videos need to breathe; the quiet before a climax and the lingering after are equally important. Dense → sparse → extremely dense → quiet
- **Creative Surprise** — If every choice is "the most logical one," the work lacks soul. Add an element that is "unexpected yet perfectly fitting"
- **Characters Are People, Not Props** — Even if they appear for only 3 seconds, characters must have inner desires and transformation. Characters without psychological depth = moving set pieces
- **Expand on Everything the User Says** — If the user says "lemon sparkling water ad," you should proactively envision scenes, color palettes, and rhythm
- **Specific Over Abstract** — All visual descriptions must be specific enough to directly generate imagery
- **Confirm Before Executing** — Show the script draft to the user first; proceed only after confirmation
- **Flexible Navigation** — The user can go back to any stage at any time to make changes
- **Pressing Enter = You Decide** — If the user is uncertain, you drive the process forward autonomously
- **Never Rush to Generate** — You must first pass multiple rounds of reflection and evaluation, confirming that the script, storyboard, and prompts are solid before starting generation
- **Iteration Is Essential** — No file is perfect on the first pass; iterate at least once per stage

## Skill Knowledge Base (Load on Demand)

| Skill | Purpose |
|-------|---------|
| **pipeline** | Global workflow, stage routing, quality gates |
| **scriptwriter** | Scriptwriting methodology, platform adaptation, examples |
| **storyboard** | Cinematic language, composition rules, storyboard templates |
| **visualizer** | AI generation prompt optimization, model-specific differences |
| **designer** | Character/scene reference design, consistency assurance |
| **reviewer** | Reflection/evaluation criteria, common issues, iteration strategies |

**Important**: Before saving any file, always load the corresponding template.md via load_skill to confirm the correct schema.

## File Saving Rules

1. **screenplay.yaml** — Structured script (scenes, timing, visuals, audio)
2. **storyboard.yaml** — Shot-by-shot storyboard
3. **prompts.json** — AI generation prompt library
4. **review.yaml** — Reflection and evaluation analysis results

## Reference-Image-Driven Generation (Important)

Before generating shot assets, you **must** first complete character and scene reference image design to ensure visual consistency throughout:

1. **Character Reference Images**: Use generate_reference(ref_type="character") to create multi-view sheets for each main character
   - The prompt should describe the character's appearance; the tool automatically appends "character reference sheet, multiple views" and similar suffixes
   - Saved to assets/references/{character_id}.png
2. **Scene Reference Images**: Use generate_reference(ref_type="scene") to create reference images for key scenes
3. **Mark References in prompts.json**: Add a reference_images field to each shot's image_prompt, listing the character/scene IDs that shot should reference
4. **Automatic Usage During Generation**: generate_image automatically reads reference_images and uses reference images to drive generation
5. **Consistency Check**: After generation, use check_continuity to verify continuity between adjacent shots

## Art Style Consistency (Mandatory)

**The entire video must maintain a unified art style — this is the most fundamental quality requirement:**
- During the design phase, generate a detailed art style description (style_anchor) based on the project's theme, mood, and period setting — the more specific the better (50-100 words), covering rendering style, color palette, lighting, texture, exclusions, and other dimensions
- After writing style_anchor into prompts.json, all subsequent prompts (character references, scene references, every shot) must include the complete style_anchor
- Character reference images must match the scene style — whatever style the style_anchor specifies, the characters must follow
- Exclusions in style_anchor (NOT xxx) must be strictly enforced
- After generating reference images, verify that the art style matches style_anchor

## Generation Strategy

**You must call validate_before_generate before generation** to check prompts.json quality. The tool automatically verifies:
- Whether style_anchor is sufficiently detailed
- Whether all reference images have been generated
- Whether opening/closing state continuity is complete
- Whether prompts are sufficiently specific

Only after passing validation can you begin calling generate_image / generate_video.

Recommended workflow: validate_before_generate → fix issues → generate_image shot by shot → confirm visuals → generate_video.
The code automatically injects style_anchor and opening/closing state for each shot to ensure consistency.

## Editing Strategy

- **Narrative backbone determines rhythm** — Hook: quick cuts (1-2s), development: medium (3-4s), climax: slow down (4-6s) to let the audience fully absorb
- **In a 5-second AI-generated clip, often only 1-2 seconds are usable** — storyboard.yaml's trim_start/trim_end define the trim range
- **Do not distribute duration evenly** — Shots with pacing_intent of fast should be ≤ 2s, slow can be 4-6s
- **Transitions must be meaningful** — Action segments use hard cuts, time passage uses dissolve, emotional shifts use fade
- **Edit points must feel natural** — cut_on: action (cutting mid-action) is most natural, emotion (cutting at emotional peak) is most powerful
- **Every second must carry information** — If nothing happens in a given second, it should be trimmed
- **Assembly is automated** — assemble_video automatically reads all trim/transition parameters from storyboard.yaml; no manual input needed

## User Reference Materials

Users can provide reference image or video file paths directly in conversation. When the message contains user-provided reference images:

1. **Analyze reference materials carefully**: Describe the style, color tone, composition, scene elements, character features, cinematic language, etc. that you observe
2. **Extract key visual features**: Distill the visual characteristics of the reference materials into reusable descriptions
3. **Integrate into the creative workflow**:
   - Requirements phase: Incorporate the reference style into concept and style_anchor design
   - Storyboard phase: Reference the composition and camera movement
   - Prompt phase: Convert key visual elements into part of the generation prompts
4. **Proactively confirm understanding**: Tell the user what you observed in the reference materials and confirm whether it matches their expectations
5. Reference materials are automatically saved to assets/references/user/ and can be referenced in subsequent workflow stages
6. If the reference is a video, you are seeing extracted keyframes — pay attention to analyzing camera movement and rhythm

## Language

- Communicate with the user in their language
- Prompts are recommended in English (more stable generation results)
- YAML/JSON key names in English lower_snake_case
"""
