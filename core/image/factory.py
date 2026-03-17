"""Image generation provider factory."""


def create_image_gen(config):
    """Create image generation instance from ImageGenConfig."""
    if config.provider == "jimeng":
        from .jimeng import JimengImageGen
        return JimengImageGen(
            api_key=config.jimeng_api_key,
            model=config.jimeng_model,
            default_image_size=config.jimeng_image_size,
            output_format=config.jimeng_output_format,
            base_url=config.jimeng_base_url,
        )
    raise ValueError(f"Unknown image provider: {config.provider}")
