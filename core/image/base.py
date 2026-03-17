"""Abstract base class for image generation providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GeneratedImage:
    data: bytes
    mime_type: str = "image/png"
    prompt_used: str = ""
    fallback_warning: str = ""   # Non-empty if reference-driven generation fell back to text-only

    def save(self, path: Path):
        """Save image data. Converts to PNG if needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".png" and self.mime_type != "image/png":
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(self.data))
                img.save(path, "PNG")
                return
            except Exception:
                pass
        with open(path, "wb") as f:
            f.write(self.data)


class BaseImageGen(ABC):
    """Abstract image generation interface."""

    @abstractmethod
    async def text_to_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        num_images: int = 1,
        image_size: str | None = None,
    ) -> list[GeneratedImage]:
        ...

    @abstractmethod
    async def image_to_image(
        self,
        prompt: str,
        reference_images: list[Path],
        aspect_ratio: str = "1:1",
        num_images: int = 1,
        image_size: str | None = None,
    ) -> list[GeneratedImage]:
        ...
