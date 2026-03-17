"""Vision analysis provider factory."""
from __future__ import annotations


def create_vision(config):
    """Create vision analysis instance from config.

    Accepts DirectorConfig to access both vision settings and API keys.
    """
    vision_cfg = config.vision
    llm_cfg = config.llm

    if vision_cfg.provider == "doubao":
        from .doubao import DoubaoVision
        # Use ARK_API_KEY (shared with Jimeng/Seedance)
        return DoubaoVision(
            api_key=llm_cfg.ark_api_key,
            model=vision_cfg.doubao_model,
            base_url=llm_cfg.ark_base_url,
        )
    elif vision_cfg.provider == "gpt4o":
        from .gpt4o import GPT4oVision
        return GPT4oVision(
            api_key=llm_cfg.openai_api_key,
            model=llm_cfg.openai_model,
        )
    elif vision_cfg.provider == "claude":
        from .claude import ClaudeVision
        return ClaudeVision(
            api_key=llm_cfg.claude_api_key,
            model=llm_cfg.claude_model,
        )
    raise ValueError(f"Unknown vision provider: {vision_cfg.provider}")
