"""Video generation provider factory."""


def create_video_gen(config):
    """Create video generation instance from VideoGenConfig."""
    if config.provider == "seedance":
        from .seedance import SeedanceVideoGen
        return SeedanceVideoGen(
            api_key=config.seedance_api_key,
            model=config.seedance_model,
            base_url=config.seedance_base_url,
            resolution=getattr(config, "seedance_resolution", "720p"),
            generate_audio=getattr(config, "seedance_generate_audio", True),
        )
    elif config.provider == "minimax":
        from .minimax import MinimaxVideoGen
        return MinimaxVideoGen(
            api_key=config.minimax_api_key,
            model=config.minimax_model,
        )
    elif config.provider == "sora":
        from .sora import SoraVideoGen
        # Sora uses OpenAI API key from LLM config — caller must pass it
        return SoraVideoGen(
            api_key=config.sora_api_key if hasattr(config, "sora_api_key") else "",
            model=config.sora_model,
        )
    raise ValueError(f"Unknown video provider: {config.provider}")
