"""Tools definitions and LLM configuration module for Takone.

This module contains all tool/prompt definitions, provider registry,
LLM resolution logic, and the system prompt used by the director agent.
Extracted from director.py for modularity.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import Colors, DirectorConfig

__all__ = [
    # File type constants
    "IMAGE_EXTS",
    "VIDEO_EXTS",
    "DOCUMENT_EXTS",
    "_MAX_IMAGE_SIZE",
    "_MAX_VIDEO_SIZE",
    "_MAX_DOC_SIZE",
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
DOCUMENT_EXTS = {'.txt', '.pdf', '.docx', '.md'}
_MAX_IMAGE_SIZE = 20 * 1024 * 1024   # 20 MB
_MAX_VIDEO_SIZE = 200 * 1024 * 1024  # 200 MB
_MAX_DOC_SIZE = 50 * 1024 * 1024     # 50 MB


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
    [{"path": Path, "type": "image"|"video"|"document", "original": str}, ...]
    """
    tokens = raw_input.split()
    text_parts = []
    files = []

    _TYPE_MAP = {
        **{ext: "image" for ext in IMAGE_EXTS},
        **{ext: "video" for ext in VIDEO_EXTS},
        **{ext: "document" for ext in DOCUMENT_EXTS},
    }
    _LIMIT_MAP = {
        "image": _MAX_IMAGE_SIZE,
        "video": _MAX_VIDEO_SIZE,
        "document": _MAX_DOC_SIZE,
    }

    for token in tokens:
        # Check suffix on the raw token (works even with shell escapes)
        suffix = Path(token).suffix.lower()
        ftype = _TYPE_MAP.get(suffix)

        if ftype:
            resolved = _resolve_file_path(token)
            if resolved:
                size = resolved.stat().st_size
                limit = _LIMIT_MAP[ftype]
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


def _extract_document_text(fpath: Path) -> str:
    """Extract text content from a document file."""
    suffix = fpath.suffix.lower()

    if suffix == ".txt" or suffix == ".md":
        return fpath.read_text(encoding="utf-8", errors="replace")

    if suffix == ".pdf":
        try:
            import pymupdf
            doc = pymupdf.open(str(fpath))
            pages = [page.get_text() for page in doc]
            doc.close()
            return "\n\n".join(pages)
        except ImportError:
            try:
                import subprocess
                result = subprocess.run(
                    ["pdftotext", str(fpath), "-"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    return result.stdout
            except Exception:
                pass
            return f"[Unable to extract PDF text — install pymupdf: pip install pymupdf]"

    if suffix == ".docx":
        try:
            import docx
            doc = docx.Document(str(fpath))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            return f"[Unable to extract DOCX text — install python-docx: pip install python-docx]"

    return f"[Unsupported document format: {suffix}]"


def _process_reference_files(
    files: list[dict],
    project_dir: Path | None,
    num_video_frames: int = 4,
) -> list[dict]:
    """Process reference files into base64-encoded image blocks, video refs, or text blocks.

    Returns list of dicts:
    - Image:    {"base64": str, "media_type": str, "label": str}
    - Video:    {"video": str, "label": str}          # path relative to project
    - Document: {"text": str, "label": str}
    Videos are NOT converted to frames here — the LLM should use analyze_media
    to analyze the video file directly (which uses Vision API with more frames
    and preserves temporal/motion context).
    Copies all user files to assets/user/.
    """
    import base64 as b64mod

    results = []
    user_dir = None
    if project_dir:
        user_dir = project_dir / "assets" / "user"
        user_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        fpath: Path = f["path"]
        ftype: str = f["type"]

        # Copy to project — all user files go to assets/user/
        dest = None
        if user_dir:
            dest = user_dir / fpath.name
            if dest.exists():
                stem = fpath.stem
                suffix = fpath.suffix
                i = 1
                while dest.exists():
                    dest = user_dir / f"{stem}_{i}{suffix}"
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
            # Don't extract frames into the conversation — just record the path
            # so the hint tells the LLM to use analyze_media for full video analysis.
            rel_path = f"assets/user/{dest.name}" if dest else f"assets/user/{fpath.name}"
            results.append({
                "video": rel_path,
                "label": fpath.name,
            })

        elif ftype == "document":
            text = _extract_document_text(fpath)
            if text:
                results.append({
                    "text": text,
                    "label": fpath.name,
                })

    return results


def _build_media_hint(
    media: list[dict],
    position: str = "above",
) -> str:
    """Build a hint string describing user-provided media.

    Handles three item types: base64 images, video references, and documents.
    Tells the LLM exact local paths and instructs it to use analyze_media.
    """
    image_labels = [item["label"] for item in media if "base64" in item]
    video_paths = [item["video"] for item in media if "video" in item]

    if not image_labels and not video_paths:
        return ""

    parts = []
    if video_paths:
        vlist = ", ".join(video_paths)
        parts.append(
            f"User provided reference video(s) saved to: {vlist}. "
            "IMPORTANT: You must call analyze_media with the video file_path to analyze "
            "the video content (motion, rhythm, transitions, style, etc.). "
            "The video has NOT been inlined in this conversation — analyze_media is the "
            "only way to see it."
        )
    if image_labels:
        ilist = ", ".join(f"assets/user/{fn}" for fn in image_labels)
        parts.append(
            f"User provided reference images ({position}). "
            f"Image files saved to: {ilist}. "
            "Use analyze_media with these paths for detailed analysis."
        )

    parts.append(
        "All reference files are already saved locally — do NOT attempt to download "
        "any URLs. Analyze style, color, composition, character features, etc., "
        "and incorporate into subsequent creative work."
    )
    return "[" + " ".join(parts) + "]"


def _build_multimodal_anthropic(text: str, media: list[dict]) -> list:
    """Build Anthropic multimodal content array (images + documents)."""
    content = []
    doc_texts = []

    for item in media:
        if "base64" in item:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": item["media_type"],
                    "data": item["base64"],
                },
            })
        elif "text" in item:
            doc_texts.append(f"--- {item['label']} ---\n{item['text']}")
        # "video" items have no inline content — handled by hint only

    hints = []
    media_hint = _build_media_hint(media, position="above")
    if media_hint:
        hints.append(media_hint)
    if doc_texts:
        hints.append(
            "[User provided reference documents. Please read and understand the content below, "
            "and incorporate relevant information into subsequent creative work. "
            "Documents saved to assets/user/.]\n\n" + "\n\n".join(doc_texts)
        )

    hint = "\n\n".join(hints) + "\n\n" if hints else ""
    content.append({"type": "text", "text": hint + text})
    return content


def _build_multimodal_openai(text: str, media: list[dict]) -> list:
    """Build OpenAI multimodal content array (images + documents)."""
    doc_texts = []

    for item in media:
        if "text" in item:
            doc_texts.append(f"--- {item['label']} ---\n{item['text']}")
        # "video" items have no inline content — handled by hint only

    hints = []
    media_hint = _build_media_hint(media, position="below")
    if media_hint:
        hints.append(media_hint)
    if doc_texts:
        hints.append(
            "[User provided reference documents. Please read and understand the content below, "
            "and incorporate relevant information into subsequent creative work. "
            "Documents saved to assets/user/.]\n\n" + "\n\n".join(doc_texts)
        )

    hint = "\n\n".join(hints) + "\n\n" if hints else ""
    content = [{"type": "text", "text": hint + text}]
    for item in media:
        if "base64" in item:
            data_url = f"data:{item['media_type']};base64,{item['base64']}"
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
    "moonshot": ("openai",    "https://api.moonshot.ai/v1"),
    "kimi":     ("openai",    "https://api.moonshot.ai/v1"),
    "zhipu":    ("openai",    "https://open.bigmodel.cn/api/paas/v4"),
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
        "moonshot": (config.llm.moonshot_api_key or os.getenv("MOONSHOT_API_KEY", ""),
                     config.llm.moonshot_model),
        "kimi":     (config.llm.kimi_api_key or os.getenv("MOONSHOT_API_KEY", ""),
                     config.llm.kimi_model),
        "zhipu":    (config.llm.zhipu_api_key or os.getenv("ZHIPU_API_KEY", ""),
                     config.llm.zhipu_model),
        "doubao":   (config.llm.ark_api_key or os.getenv("ARK_API_KEY", ""),
                     config.llm.ark_model),
        "qwen":     (config.llm.qwen_api_key or os.getenv("QWEN_API_KEY", "") or os.getenv("DASHSCOPE_API_KEY", ""),
                     config.llm.qwen_model),
    }

    api_key, model = key_map[provider]
    if not api_key:
        env_var = {
            "claude": "ANTHROPIC_API_KEY",
            "minimax": "MINIMAX_API_KEY",
            "openai": "OPENAI_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "kimi": "MOONSHOT_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
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
            "Primary files: feeling.yaml, shots.yaml. "
            "Legacy files also supported: screenplay.yaml, storyboard.yaml, prompts.json, review.yaml."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename to save (e.g. 'feeling.yaml', 'shots.yaml', 'prompts.json')",
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
            "- pipeline/SKILL.md — 4-stage pipeline (Discover/Design/Generate/Assemble), shot budget\n"
            "- scriptwriter/SKILL.md — Feeling-first creation, shots.yaml format\n"
            "- scriptwriter/template.md — shots.yaml schema (load before saving)\n"
            "- scriptwriter/reference.md — Example scripts, style guides\n"
            "- storyboard/SKILL.md — Cinematic reference guide (shot types, camera, composition)\n"
            "- visualizer/SKILL.md — Provider-specific prompt optimization\n"
            "- visualizer/template.md — prompts.json schema (legacy format)\n"
            "- visualizer/reference.md — Example prompts for each provider\n"
            "- designer/SKILL.md — Character/scene reference design for consistency\n"
            "- reviewer/SKILL.md — Scroll-stop test, visual quality checks\n"
            "- learn/SKILL.md — Mandatory research, feeling extraction\n"
            "- memory/SKILL.md — When and how to read and update user memory\n\n"
            "Tip: Load scriptwriter/SKILL.md for the shots.yaml format before designing shots."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "Skill name",
                    "enum": ["pipeline", "scriptwriter", "storyboard", "visualizer", "designer", "reviewer", "learn", "memory"],
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
            "Saved to assets/design/. Must be done BEFORE shot generation. "
            "IMPORTANT: You MUST choose aspect_ratio based on sub-image count and orientation — "
            "the canvas must have enough space for all views with correct human proportions. "
            "For character sheets: 2 views → 3:4, 3 views → 3:2, 4+ views → 16:9. "
            "For scenes: match the project's default ratio."
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
                    "description": (
                        "Generation prompt. For characters: MUST include detailed physical description "
                        "(height, body proportions, face, hair, clothing details, colors), full style_anchor, "
                        "AND multi-view keywords. Emphasize 'correct human anatomy, natural body proportions, "
                        "proper head-to-body ratio' to avoid distortion. Prompt must be detailed (100+ words)."
                    ),
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3"],
                    "description": (
                        "REQUIRED. Choose based on sub-image layout: "
                        "2 views side-by-side → 3:4; "
                        "3 views side-by-side → 3:2 or 16:9; "
                        "4-5 views → 16:9; "
                        "single scene → match project ratio. "
                        "Wrong ratio causes figure distortion!"
                    ),
                },
                "reference_images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of reference image IDs from assets/learn/ to use as style references "
                        "via image-to-image generation. Pick the best learn images that capture the target "
                        "visual style (color palette, lighting, texture, mood). These are the ACTUAL images "
                        "downloaded during the learn phase — using them preserves visual details that text "
                        "descriptions cannot capture. Examples: ['learn/image/ref_01.png', 'learn/image/style_sample.jpg']. "
                        "Also supports design/ and user/ paths. When provided, generation uses img2img "
                        "instead of text-only, producing results that inherit the visual DNA of the references."
                    ),
                },
            },
            "required": ["ref_type", "ref_id", "prompt", "aspect_ratio"],
        },
    },
    {
        "name": "generate_image",
        "description": (
            "Generate key frame image(s) for a specific shot using Seedream. "
            "Saved to assets/image/. Use 'variations' to generate multiple versions "
            "for comparison (default: 2, user can request more or fewer). "
            "Automatically loads reference_images and style_anchor from shots.yaml/prompts.json."
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
                    "description": "Image generation prompt (or leave empty to use shots.yaml/prompts.json)",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "Aspect ratio (default: from project config)",
                    "enum": ["1:1", "9:16", "16:9", "3:4", "4:3"],
                },
                "variations": {
                    "type": "integer",
                    "description": "Number of variations to generate for comparison (default: 2)",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 2,
                },
            },
            "required": ["shot_id"],
        },
    },
    {
        "name": "compare_shots",
        "description": (
            "Compare multiple image/video variations and select the best one. "
            "Sends all variations to vision model with the prompt: "
            "'Which would make you stop scrolling on Douyin?' "
            "Returns ranked results. Use after generating multiple variations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "shot_id": {
                    "type": "string",
                    "description": "Shot ID whose variations to compare (e.g. 'SHOT_001')",
                },
                "media_type": {
                    "type": "string",
                    "description": "Type of media to compare",
                    "enum": ["image", "video"],
                    "default": "image",
                },
                "reference_path": {
                    "type": "string",
                    "description": "Optional path to a reference image to compare against (from feeling.yaml references)",
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
            "The video will be saved to assets/video/. "
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
                    "description": "Path to image or video file relative to project (e.g. 'assets/image/shot_001.png')",
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
        "name": "evaluate_shot",
        "description": (
            "Evaluate a generated shot using Walter Murch's editing priorities "
            "(Emotion 51%, Story 23%, Rhythm 10%, Eye-trace 7%, 2D Composition 5%, "
            "3D Space 4%). Sends the current shot plus context from recent confirmed "
            "shots to vision API. Returns PASS/FAIL verdict with dimension scores and "
            "actionable fix suggestions. Call after generate_image or generate_video "
            "to decide whether to accept or regenerate the shot."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "shot_id": {
                    "type": "string",
                    "description": "Current shot ID being evaluated (e.g. 'SHOT_003')",
                },
                "media_type": {
                    "type": "string",
                    "enum": ["image", "video"],
                    "description": "'image' for keyframe evaluation, 'video' for video clip evaluation",
                },
                "context_shot_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "IDs of previous confirmed shots for sequence context "
                        "(e.g. ['SHOT_001', 'SHOT_002']). Recommend last 2-3 shots. "
                        "Empty array for the first shot."
                    ),
                },
                "emotion_context": {
                    "type": "string",
                    "description": (
                        "Where we are on the emotion curve: what the audience should "
                        "feel at this point, what came before emotionally, what comes next. "
                        "If not provided, auto-extracted from storyboard.yaml."
                    ),
                },
                "story_context": {
                    "type": "string",
                    "description": (
                        "What narrative beat this shot belongs to and what it should advance. "
                        "If not provided, auto-extracted from storyboard.yaml."
                    ),
                },
            },
            "required": ["shot_id", "media_type"],
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
        "name": "learn_browse",
        "description": (
            "Browse the web for creative research. Supports: "
            "web search (baidu/google/zhihu/baike), "
            "image search (baidu_image/google_image — auto-downloads top 3 + vision analysis), "
            "video search (douyin/bilibili/xiaohongshu/youtube), "
            "or direct URL browsing to extract page content. "
            "search_images results include 'vision_analysis' with actual visual content description. "
            "For platforms requiring login, will wait for user to complete login. "
            "Load the 'learn' skill first for research methodology."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search_web", "search_images", "search_videos", "browse_url"],
                    "description": (
                        "search_web: text search on baidu/google/zhihu/baike; "
                        "search_images: image search on baidu_image/google_image; "
                        "search_videos: video search on douyin/bilibili/xiaohongshu/youtube; "
                        "browse_url: visit a URL and extract its main text content"
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Search keywords (for search actions) or full URL (for browse_url). "
                        "E.g. '武松打虎 历史背景' or 'https://baike.baidu.com/item/武松打虎'"
                    ),
                },
                "platform": {
                    "type": "string",
                    "description": (
                        "Platform/engine to use. "
                        "For search_web: baidu (default), google, zhihu, baike. "
                        "For search_images: baidu_image (default), google_image. "
                        "For search_videos: douyin (default), bilibili, xiaohongshu, youtube. "
                        "Not needed for browse_url."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return. Default: 10 for web, 20 for images/videos.",
                },
            },
            "required": ["action", "query"],
        },
    },
    {
        "name": "learn_download",
        "description": (
            "Download reference materials (images, videos, files) to assets/learn/. "
            "IMPORTANT: Download sparingly — only the most valuable 2-3 items per research session. "
            "Prefer browsing and noting URLs over downloading. Never batch-download search results. "
            "Images are auto-analyzed by vision AI (style, color, composition). "
            "Videos via yt-dlp, limited to 1080p and 5 minutes. "
            "IMPORTANT for videos: url MUST be a specific video page URL "
            "(e.g. douyin.com/video/xxxxx, bilibili.com/video/BVxxxxx), "
            "NOT a search/listing/hashtag page. Use learn_browse first to find video URLs. "
            "Falls back to browser screenshot if direct download fails. "
            "Downloaded images can be used directly in prompts.json reference_images by filename. "
            "A 2-5 second delay is enforced between consecutive downloads to respect server limits."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to download from",
                },
                "media_type": {
                    "type": "string",
                    "enum": ["image", "video", "file"],
                    "description": (
                        "image: direct HTTP download; "
                        "video: yt-dlp download (for platform videos); "
                        "file: generic HTTP download"
                    ),
                },
                "filename": {
                    "type": "string",
                    "description": "Custom filename (optional). Auto-generated if not provided.",
                },
                "analyze": {
                    "type": "boolean",
                    "description": (
                        "Auto-analyze downloaded images using vision AI. "
                        "Produces structured analysis of style, color, composition, lighting. "
                        "Analysis saved as .analysis.md sidecar file. "
                        "Default: true for images, ignored for video/file."
                    ),
                },
            },
            "required": ["url", "media_type"],
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
    {
        "name": "memory_read",
        "description": (
            "Read memory files from ~/.takone/memory/. "
            "Call with no arguments to read MEMORY.md (the main index). "
            "Call with a filename to read a specific topic file (e.g., 'projects.md', 'feedback.md').\n\n"
            "When to read:\n"
            "- At session start: memory_read() to load user preferences\n"
            "- When user references past work: memory_read('projects.md')\n"
            "- When making subjective creative decisions: check preferences in MEMORY.md"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "File to read (default: 'MEMORY.md'). Examples: 'MEMORY.md', 'projects.md', 'feedback.md'",
                },
            },
        },
    },
    {
        "name": "memory_write",
        "description": (
            "Write a memory file to ~/.takone/memory/. The content replaces the entire file. "
            "To update, first memory_read the file, integrate new info, then memory_write the full updated content. "
            "Do NOT announce memory updates to the user — just do it silently.\n\n"
            "When to write:\n"
            "- User expresses aesthetic preference → update MEMORY.md\n"
            "- User corrects/rejects a choice → update MEMORY.md + feedback.md\n"
            "- Project completes → update MEMORY.md summary + projects.md details\n\n"
            "Keep MEMORY.md under 200 lines. Move details to topic files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "File to write (default: 'MEMORY.md'). Examples: 'MEMORY.md', 'projects.md', 'feedback.md'",
                },
                "content": {
                    "type": "string",
                    "description": "Full markdown content to write to the file.",
                },
            },
            "required": ["content"],
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

SYSTEM_PROMPT = """You are a professional AI video director. You create short videos (10-60 seconds for Douyin/TikTok, or 1-3 minutes max) that make people stop scrolling.

## Core Philosophy

**The essence of creation is FEELING.** Not structure, not process, not checklists — feeling.

You are not an assembly line. You are a director with taste. Before you write a single word of script, you must FEEL what the video should be. And the only way to develop that feeling is to study what already works.

## Memory — Knowing Your User

You have persistent memory in `~/.takone/memory/`. Read `memory_read()` at session start. Write `memory_write()` silently when you learn preferences, corrections, or project outcomes. Keep MEMORY.md under 200 lines.

## The Director's Three-Layer Thinking

Every creative decision, strictly in order:

1. **FEELING (WHY)** — What should the audience feel? Trust your gut first.
2. **TECHNIQUE (HOW)** — What cinematic tools create that feeling? (shot size, movement, lighting, color, rhythm)
3. **CONTENT (WHAT)** — What's in the frame? This is LAST, not first.

**Never start from Layer 3.** If you're thinking "cherry blossom tree" before asking "what should this feel like," go back to Layer 1.

## The Four-Stage Pipeline

### Stage 1: DISCOVER — Find Your Feeling (MANDATORY)

**Before writing ANY script or shots, you MUST research.** This is not optional.

1. **Search platforms** — Use `learn_browse` to search Douyin/Bilibili/Xiaohongshu for the best content in your target category
2. **Download references** — Use `learn_download` to save the 3-5 best reference frames/images
3. **Analyze with vision** — Use `analyze_media` on downloaded references: Why does this work? What feeling does it create? What technique drives it?
4. **Write feeling.yaml** — Your creative anchor:
   ```yaml
   target_feeling: "The viewer should feel ___"
   references:
     - image: "assets/learn/ref_01.png"
       why: "The slow reveal through mist creates perfect tension"
   visual_dna:
     color_mood: "cold tones, blue-gray dominant"
     pacing: "slow build → explosive release"
     first_3_seconds: "static frame, sudden motion"
   anti_patterns:
     - "no cartoon look"
     - "no over-saturated colors"
   ```
5. **Only after research, proceed to Stage 2**

Research is also available at ANY point later — whenever you're unsure about something, search for it.

### Stage 2: DESIGN — Write Your Shots + Generate Character References

Load `scriptwriter`, `visualizer`, and `designer` skills. Create `shots.yaml`, then generate character reference images.

```yaml
feeling: "One sentence — what should watching this FEEL like"
style_anchor: "50-100 word visual style description (render, color, lighting, texture, exclusions)"
characters:
  - id: character_name
    visual: "50-100 word character appearance"
    inner_desire: "what drives them"
references:
  - image: "assets/design/character_name.png"

shots:
  - id: SHOT_001
    feeling: "what this specific shot should evoke"
    duration: 3
    prompt: "detailed image generation prompt including style_anchor"
    video_prompt: >
      motion description with opening/closing states.
      [If narration:] The narrator says in a calm voice "他走了很远的路",
      footsteps on gravel, wind, melancholic piano underscore.
    reference_images: ["character_name"]
    transition_out: cut
    audio:                    # optional — creative intent for sound
      narration:
        speaker: "narrator"
        text: "他走了很远的路"
        tone: "calm, nostalgic"
      music: "melancholic piano"
      sfx: "footsteps, wind"
```

**Shot Budget (STRICT):**

| Target Duration | Max Shots | Variations Per Shot |
|----------------|-----------|-------------------|
| 5-15 seconds   | 1-3       | Generate 5, pick best |
| 15-30 seconds  | 3-5       | Generate 3, pick best |
| 30-60 seconds  | 5-8       | Generate 2, pick best |
| 1-3 minutes    | 8-15      | Generate 2, pick best |

**Exceeding these limits = planning failure. Cut shots ruthlessly. 2 stunning shots > 8 mediocre ones.**

**Duration Planning (CRITICAL — avoid waste):**

Seedance 2: **4–15s** (any integer). Seedance 1.x: **5s** or **10s** only. Plan each shot's `duration` accordingly.

Rules for duration planning:
1. **Prefer 5s shots** — most shots only need 3-5s of effective content.
2. **Use precise durations** — don't pad unnecessarily.
3. **Merge short adjacent shots** — two shots of 2s+3s should be ONE 5s shot.
4. **Sum check** — before finalizing, add up all shot durations. Compare against target duration. If total generated duration is >1.5× target, you have too many shots or durations are too large. Consolidate.
5. **Audio completeness** — Seedance generates audio WITH video. All dialogue, narration, and sound effects in `video_prompt` MUST complete within the shot's duration. A 5s shot cannot contain a 7s sentence. If dialogue is long, either split it across shots at natural pauses, or use a longer duration.

Example: Target 30s video
- ❌ Bad: 6 shots × duration:6 → generates 6×10s = 60s (2× waste)
- ✅ Good: 5 shots × duration:5 + 1 shot × duration:5 = 6×5s = 30s generated for 30s target

Key principles:
- Every shot needs a `feeling` — this is the soul of the shot
- style_anchor (50-100 words) must appear in EVERY prompt verbatim
- Characters need reference images for consistency
- For short videos (≤15s): skip elaborate narrative structures. Just make every frame count.
- **Story check:** Ask yourself: "What changes in this video? Can the viewer say what happened?" If nothing changes — it's a mood piece, not a story. Both are valid, but know which one you're making.
- **Audio in video_prompt:** Seedance 1.5 generates audio with video. Dialogue in quotes, voice tone near speaker, sound effects comma-separated. Silence is the default — add voice only when it deepens the story. ALL audio must fit within the shot's duration — do not write dialogue that takes longer to speak than the shot lasts.

**Prompt Quality Requirements (HARD RULES — load visualizer skill for full details):**

Image prompts MUST include ALL of these for human subjects:
1. **Skin texture**: `natural skin texture, visible pores` + anti-smoothing keywords — without this, skin looks plastic
2. **Camera/lens**: focal length + aperture, e.g. `85mm f/1.4, shallow depth of field`
3. **Lighting direction**: 3-point system (key + fill + rim), e.g. `warm tungsten from upper-right, soft ambient bounce from left`
4. **Clothing to fabric+state level**: e.g. `fitted black silk slip dress, thin straps, fabric catching warm lamplight, one strap slipping off shoulder`
5. **Environment 3+ specific details**: e.g. `messy bedsheets, warm lamp glow, phone charger on nightstand, sheer curtains`
6. **Negative prompt**: always include to prevent AI artifacts

❌ NEVER write prompts like: `woman standing in bedroom, wearing dark elegant silk top, cinematic, 4k, film grain`
✅ ALWAYS write prompts like: `Ultra-realistic cinematic portrait. Young woman standing by full-length mirror in dimly lit bedroom, long dark hair with loose waves catching warm backlight from bedside tungsten lamp. Sleepy half-lidded eyes, slightly parted lips, natural skin texture with visible pores. Fitted black silk slip dress, thin spaghetti straps, fabric tension from slight twist, one strap slipping off shoulder. Messy white linen bedsheets, fairy lights on headboard, phone face-down on nightstand, sheer curtains filtering city neon. Key: warm tungsten from bedside lamp right. Fill: soft city glow from window left. Rim: fairy light halo on hair. Shot on 85mm f/1.4, shallow DOF, tack sharp on eyes. Film grain, warm color grade, intimate. 9:16. No cartoon, no plastic skin, no beauty retouching, no oversaturated.`

After writing shots.yaml, ask yourself: **"If this appeared in my feed, would I stop scrolling?"** If no, rewrite until yes.

**MANDATORY — Generate ALL reference images before leaving Stage 2:**
After shots.yaml is finalized, load `designer` skill and generate reference images:
1. **Select best learn images as style references** — Review images in `assets/learn/image/` and their `.analysis.md` files. Pick 1-3 images that best capture the target visual style (color, lighting, texture, mood). These will be passed as `reference_images` to generate_reference for img2img generation, preserving visual DNA that text alone cannot capture.
2. For each character in shots.yaml `characters` list:
   → `generate_reference(ref_type="character", ref_id="{character.id}", prompt="<detailed prompt with full style_anchor + anatomy keywords>", aspect_ratio="3:2", reference_images=["learn/image/best_ref.png"])`
3. For each distinct scene/location that appears across shots:
   → `generate_reference(ref_type="scene", ref_id="{scene_id}", prompt="<detailed prompt with full style_anchor + lighting + environment details>", aspect_ratio="9:16", reference_images=["learn/image/best_ref.png"])`
4. Add all generated reference IDs to each shot's `reference_images` list (both characters AND scenes appearing in that shot)
5. Verify: all `reference_images` entries in shots have corresponding files in `assets/design/`

**Do NOT proceed to Stage 3 without generating ALL references. generate_image will BLOCK if references are missing.**

### Stage 3: GENERATE — Create and Select

**Pre-check: Verify all reference images (characters + scenes) exist in `assets/design/`.** If any are missing, generate them with `generate_reference()` first. `generate_image` will refuse to run if specified references are not found.

For each shot:
1. **Generate keyframe variations** — generate_image (default 2 variations, user can request more or fewer)
2. **Compare and select** — Use `compare_shots` to send all variations to vision model: "Which one would make you stop scrolling? Why?"
3. **Generate video** from the best keyframe
4. **Evaluate the shot** — Use `evaluate_shot`: Does this FEEL right? Is it visually distinct? Does it fit the sequence?
5. If the shot fails evaluation, adjust the prompt and regenerate. Max 3 attempts.

**After generating each shot, ask: "Would I scroll past this?"** If yes, it fails. Regenerate or rethink.

### Stage 4: ASSEMBLE — Put It Together

1. Call `assemble_video` — code reads shots.yaml for ordering, trimming, and transitions
2. Add background music with `add_audio_track` if needed. Voiceover/narration is generated as part of the video itself (Seedance 1.5) — dialogue is included in video_prompt during Stage 3.
3. Watch the assembled video via `analyze_media` — does the whole piece work as a unit?

## Self-Review: The Scroll-Stop Test

After completing each stage, apply this single test:

**"If this appeared in my Douyin feed right now, would I stop scrolling and watch?"**

- If **yes** → proceed
- If **no** → figure out WHY and fix it before moving on
- If **not sure** → compare against your reference videos. What's the gap?

Do NOT use checklists of 10+ items. Use your creative judgment. Trust your gut. If something feels off, it IS off.

## Skills (Load on Demand)

| Skill | Purpose |
|-------|---------|
| **pipeline** | Workflow routing, shot budget |
| **scriptwriter** | Feeling-first creation, shots.yaml format |
| **visualizer** | Prompt optimization for different AI models |
| **designer** | Character/scene reference design |
| **reviewer** | Scroll-stop evaluation, visual quality checks |
| **learn** | Browser research, reference download, feeling extraction |
| **memory** | User preferences, aesthetic patterns |

## Reference-Driven Generation

Before generating shots, create reference images for visual consistency:
1. Character references: `generate_reference(ref_type="character")` → `assets/design/{id}.png`
2. Scene references: `generate_reference(ref_type="scene")`
3. Mark `reference_images` in each shot of shots.yaml
4. style_anchor MUST appear in every prompt (characters, scenes, shots)
5. After generation, `check_continuity` for cross-shot consistency

## Editing Principles

- Hook: 1-3s, fast. Development: 3-4s, medium. Climax: 4-6s, slow (let it breathe)
- In a 5-second AI clip, often only 1-2 seconds are usable — trim aggressively
- Transitions must be meaningful: hard cuts for action, dissolve for time, fade for emotion
- Every second must carry feeling or information. Dead time = trim it.
- Assembly is automated: shots.yaml defines trim/transition; assemble_video handles the rest

## User References

When users provide reference images/videos:
1. Analyze carefully — extract style, color, composition, mood
2. Integrate into feeling.yaml and style_anchor
3. Confirm your understanding with the user
4. References auto-saved to assets/user/

## Language

- Communicate in the user's language
- Generation prompts in English (more stable results)
- YAML/JSON keys in English lower_snake_case
"""
