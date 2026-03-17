"""
Director Agent System Configuration
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Base paths
DIRECTOR_ROOT = Path(__file__).parent.parent
PROJECTS_DIR = DIRECTOR_ROOT / "projects"
SKILLS_DIR = DIRECTOR_ROOT / "skills"

# Ensure directories exist
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# Model defaults (used as fallback; actual model is resolved from config)
DIRECTOR_MODEL = "MiniMax-M2.5"
VISION_MODEL = "gpt-4o"

# Skill directory mapping
SKILLS = {
    "pipeline": SKILLS_DIR / "pipeline",
    "scriptwriter": SKILLS_DIR / "scriptwriter",
    "storyboard": SKILLS_DIR / "storyboard",
    "visualizer": SKILLS_DIR / "visualizer",
    "designer": SKILLS_DIR / "designer",
    "reviewer": SKILLS_DIR / "reviewer",
}

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    WHITE = '\033[97m'
    MAGENTA = '\033[35m'
    # 256-color for subtle tones
    GRAY = '\033[38;5;245m'
    LIGHT_BLUE = '\033[38;5;111m'
    ORANGE = '\033[38;5;214m'


# ── Config dataclasses ──────────────────────────────────────────────────

@dataclass
class LLMConfig:
    provider: str = "minimax"  # "minimax" | "claude" | "openai" | "doubao" | "moonshot" | "qwen"
    # Minimax
    minimax_api_key: str = ""
    minimax_model: str = "MiniMax-M2.5"
    # Claude
    claude_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    # Doubao (Volcengine Ark)
    ark_api_key: str = ""
    ark_model: str = "doubao-seed-1-6-251015"
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"


@dataclass
class ImageGenConfig:
    provider: str = "jimeng"  # "jimeng" | "gemini"
    jimeng_api_key: str = ""
    jimeng_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    jimeng_model: str = "doubao-seedream-5-0-260128"
    jimeng_image_size: str = "2K"
    jimeng_output_format: str = "png"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-image"


@dataclass
class VideoGenConfig:
    provider: str = "seedance"  # "seedance" | "minimax" | "sora"
    seedance_api_key: str = ""  # Falls back to jimeng_api_key
    seedance_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    seedance_model: str = "doubao-seedance-1-5-pro-251215"
    seedance_resolution: str = "720p"  # "720p" or "1080p"
    minimax_api_key: str = ""
    minimax_model: str = "video-01"
    sora_model: str = "sora"
    default_duration: float = 5.0
    default_aspect_ratio: str = "9:16"
    poll_interval: float = 10.0
    poll_timeout: float = 300.0
    # FFmpeg encoding quality
    encoding_crf: int = 18               # 0-51, lower = better quality. 18 = visually lossless
    encoding_preset: str = "slow"         # ultrafast/fast/medium/slow/veryslow
    encoding_fps: int = 30                # Output framerate for consistent playback


@dataclass
class VisionConfig:
    provider: str = "doubao"  # "doubao" | "gpt4o" | "claude"
    doubao_model: str = "doubao-1-5-vision-pro-32k-250115"
    sample_frames: int = 8


@dataclass
class AudioConfig:
    tts_provider: str = "none"         # "openai" | "volcengine" | "none"
    default_music_volume: float = 0.4  # 0.0-1.0, background music volume when mixed with voiceover
    default_vo_volume: float = 1.0     # 0.0-1.0, voiceover volume
    fade_out_seconds: float = 2.0      # Fade-out duration at the end of music
    fade_in_seconds: float = 1.0       # Fade-in duration at the start of music
    loudness_normalize: bool = True    # Apply EBU R128 loudness normalization


@dataclass
class ProjectConfig:
    default_platform: str = "douyin"
    default_aspect_ratio: str = "9:16"
    default_duration: int = 30
    default_language: str = "zh"


@dataclass
class DirectorConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    image: ImageGenConfig = field(default_factory=ImageGenConfig)
    video: VideoGenConfig = field(default_factory=VideoGenConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    project: ProjectConfig = field(default_factory=ProjectConfig)


def load_config() -> DirectorConfig:
    """Load config from config.yaml + environment variables."""
    cfg = DirectorConfig()

    # Try config.yaml
    config_path = DIRECTOR_ROOT / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        for section_name in ("llm", "image", "video", "vision", "audio", "project"):
            if section_name in data:
                section = getattr(cfg, section_name)
                for k, v in data[section_name].items():
                    if hasattr(section, k):
                        setattr(section, k, v)

    # Environment variables override
    cfg.llm.minimax_api_key = os.getenv("MINIMAX_API_KEY", cfg.llm.minimax_api_key)
    cfg.llm.claude_api_key = os.getenv("ANTHROPIC_API_KEY", cfg.llm.claude_api_key)
    cfg.llm.openai_api_key = os.getenv("OPENAI_API_KEY", cfg.llm.openai_api_key)
    cfg.llm.ark_api_key = os.getenv("ARK_API_KEY", cfg.llm.ark_api_key)
    cfg.image.jimeng_api_key = os.getenv("JIMENG_API_KEY", cfg.image.jimeng_api_key)
    cfg.image.gemini_api_key = os.getenv("GEMINI_API_KEY", cfg.image.gemini_api_key)
    cfg.video.minimax_api_key = os.getenv("MINIMAX_VIDEO_API_KEY", cfg.video.minimax_api_key)

    # ARK_API_KEY is shared across Jimeng image + Seedance video
    ark_key = cfg.llm.ark_api_key
    if ark_key:
        if not cfg.image.jimeng_api_key:
            cfg.image.jimeng_api_key = ark_key
        if not cfg.video.seedance_api_key:
            cfg.video.seedance_api_key = ark_key

    # Provider overrides
    for env_var, attr in [
        ("LLM_PROVIDER", "llm.provider"),
        ("IMAGE_PROVIDER", "image.provider"),
        ("VIDEO_PROVIDER", "video.provider"),
    ]:
        val = os.getenv(env_var)
        if val:
            section_name, field_name = attr.split(".")
            setattr(getattr(cfg, section_name), field_name, val)

    return cfg
