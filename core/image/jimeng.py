"""Jimeng (Seedream) / Doubao Seedream image generation adapter.

Uses the OpenAI-compatible Ark API with doubao-seedream models.

Supports all 6 Seedream generation modes mapped to the unified interface:
  text_to_image  (num=1)  → text2img    text only → single image
  text_to_image  (num>1)  → text2imgs   text only → multi-image (streaming)
  image_to_image (1 ref)  → img2img     single image + text → single image
  image_to_image (N refs) → imgs2img    multi-image + text → single image
  image_to_image (1 ref,  num>1) → img2imgs   single image + text → multi-image
  image_to_image (N refs, num>1) → imgs2imgs  multi-image + text → multi-image

Models:
  doubao-seedream-5-0-260128  (5.0 lite)  2K/3K, png/jpeg
  doubao-seedream-4-5-251128  (4.5)       2K/4K, jpeg
  doubao-seedream-4-0-250828  (4.0)       1K/2K/4K, jpeg

Limits: input refs + output images <= 15; single image <= 10MB
"""

import asyncio
import base64
import time
from pathlib import Path

from .base import BaseImageGen, GeneratedImage


# Input refs + output images total limit
MAX_TOTAL_IMAGES = 15

# Retry config for 429 (engine overloaded)
_MAX_RETRIES = 3
_RETRY_DELAYS = [5, 10, 20]  # seconds


class JimengImageGen(BaseImageGen):
    def __init__(
        self,
        api_key: str = "",
        model: str = "doubao-seedream-5-0-260128",
        default_image_size: str = "2K",
        output_format: str = "png",
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
    ):
        self.api_key = api_key
        self.model = model
        # OpenAI SDK appends /images/generations automatically;
        # strip it from base_url to avoid path duplication.
        self.base_url = base_url.rstrip("/").removesuffix("/images/generations")
        self.default_image_size = default_image_size
        self.output_format = output_format

        # Feature detection by model version
        self.is_v5 = "5-0" in model or "5.0" in model
        self._client = None

    def _get_client(self):
        """Lazy-init OpenAI client for Ark API."""
        if self._client is None:
            import httpx as _httpx
            from openai import OpenAI
            # Bypass proxy for domestic Chinese service
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                http_client=_httpx.Client(proxy=None, trust_env=False),
            )
        return self._client

    # ==================== Public Interface ====================

    async def text_to_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        num_images: int = 1,
        image_size: str | None = None,
    ) -> list[GeneratedImage]:
        """Generate images from text prompt."""
        if not self.api_key:
            raise RuntimeError("No Jimeng/Ark API key configured")

        size = self._resolve_size(aspect_ratio, image_size)
        extra = self._build_extra_body(
            sequential=(num_images > 1),
            max_images=min(num_images, 4),
        )

        if num_images > 1:
            return await self._generate_streaming(prompt, size, extra)
        else:
            return await self._generate_single(prompt, size, extra)

    async def image_to_image(
        self,
        prompt: str,
        reference_images: list[Path],
        aspect_ratio: str = "1:1",
        num_images: int = 1,
        image_size: str | None = None,
    ) -> list[GeneratedImage]:
        """Generate images with reference images for character consistency."""
        if not self.api_key:
            raise RuntimeError("No Jimeng/Ark API key configured")

        size = self._resolve_size(aspect_ratio, image_size)
        image_urls = self._encode_references(reference_images)
        if not image_urls:
            print("[Jimeng] WARNING: All reference images failed to load, falling back to text-only generation. Character consistency may be compromised!")
            results = await self.text_to_image(prompt, aspect_ratio, num_images, image_size)
            for r in results:
                r.fallback_warning = "REFERENCE_LOAD_FAILED"
            return results

        max_out = min(num_images, MAX_TOTAL_IMAGES - len(image_urls))
        if max_out < 1:
            max_out = 1
            image_urls = image_urls[:MAX_TOTAL_IMAGES - 1]

        image_param = image_urls[0] if len(image_urls) == 1 else image_urls
        extra = self._build_extra_body(
            image=image_param,
            sequential=(max_out > 1),
            max_images=min(max_out, 4),
        )

        try:
            if max_out > 1:
                return await self._generate_streaming(prompt, size, extra)
            else:
                return await self._generate_single(prompt, size, extra)
        except Exception as e:
            print(f"[Jimeng] WARNING: Reference-driven generation failed: {e}. Falling back to text-only — character consistency may be lost!")
            results = await self.text_to_image(prompt, aspect_ratio, 1, image_size)
            for r in results:
                r.fallback_warning = "GENERATION_FAILED"
            return results

    # ==================== Generation Core ====================

    async def _generate_single(
        self, prompt: str, size: str, extra: dict
    ) -> list[GeneratedImage]:
        """Non-streaming single image generation with 429 retry."""
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _call():
            from openai import RateLimitError
            for attempt in range(_MAX_RETRIES):
                try:
                    return client.images.generate(
                        model=self.model,
                        prompt=prompt,
                        size=size,
                        response_format="b64_json",
                        extra_body=extra,
                    )
                except RateLimitError:
                    if attempt < _MAX_RETRIES - 1:
                        delay = _RETRY_DELAYS[attempt]
                        print(f"[Jimeng] Engine overloaded, retrying in {delay}s... ({attempt + 1}/{_MAX_RETRIES})")
                        time.sleep(delay)
                    else:
                        raise

        response = await loop.run_in_executor(None, _call)
        return self._parse_response(response, prompt)

    async def _generate_streaming(
        self, prompt: str, size: str, extra: dict
    ) -> list[GeneratedImage]:
        """Streaming multi-image generation with 429 retry."""
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _call():
            from openai import RateLimitError
            for attempt in range(_MAX_RETRIES):
                try:
                    return client.images.generate(
                        model=self.model,
                        prompt=prompt,
                        size=size,
                        response_format="b64_json",
                        stream=True,
                        extra_body=extra,
                    )
                except RateLimitError:
                    if attempt < _MAX_RETRIES - 1:
                        delay = _RETRY_DELAYS[attempt]
                        print(f"[Jimeng] Engine overloaded, retrying in {delay}s... ({attempt + 1}/{_MAX_RETRIES})")
                        time.sleep(delay)
                    else:
                        raise

        stream = await loop.run_in_executor(None, _call)
        return await self._collect_stream(stream, prompt, loop)

    # ==================== Response Parsing ====================

    def _parse_response(self, response, prompt: str) -> list[GeneratedImage]:
        """Parse a non-streaming response."""
        results = []
        for item in response.data:
            if hasattr(item, "b64_json") and item.b64_json:
                raw = base64.b64decode(item.b64_json)
                mime = f"image/{self.output_format}"
                results.append(GeneratedImage(
                    data=raw, mime_type=mime, prompt_used=prompt,
                ))
            elif hasattr(item, "url") and item.url:
                import httpx
                r = httpx.get(item.url, timeout=60.0)
                r.raise_for_status()
                results.append(GeneratedImage(
                    data=r.content, prompt_used=prompt,
                ))
        return results

    async def _collect_stream(
        self, stream, prompt: str, loop
    ) -> list[GeneratedImage]:
        """Collect images from a streaming response."""
        mime = f"image/{self.output_format}"

        def _iterate():
            collected = []
            idx = 0
            for event in stream:
                if event is None:
                    continue
                if event.type == "image_generation.partial_succeeded":
                    idx += 1
                    if event.b64_json is not None:
                        raw = base64.b64decode(event.b64_json)
                        collected.append(GeneratedImage(
                            data=raw, mime_type=mime, prompt_used=prompt,
                        ))
                        print(f"[Jimeng] Image {idx} generated")
                elif event.type == "image_generation.partial_failed":
                    idx += 1
                    print(f"[Jimeng] Image {idx} failed: "
                          f"{getattr(event, 'error', 'unknown')}")
                elif event.type == "image_generation.completed":
                    break
            return collected

        return await loop.run_in_executor(None, _iterate)

    # ==================== Helpers ====================

    def _build_extra_body(
        self,
        image=None,
        sequential: bool = False,
        max_images: int = 4,
    ) -> dict:
        """Build extra_body for Seedream API calls."""
        extra = {"watermark": False}

        if image is not None:
            extra["image"] = image

        if sequential:
            extra["sequential_image_generation"] = "auto"
            extra["sequential_image_generation_options"] = {
                "max_images": max_images,
            }
        else:
            extra["sequential_image_generation"] = "disabled"

        if self.is_v5 and self.output_format:
            extra["output_format"] = self.output_format

        return extra

    def _resolve_size(
        self, aspect_ratio: str, image_size: str | None = None
    ) -> str:
        """Convert aspect_ratio + image_size into Seedream size parameter."""
        tier = image_size or self.default_image_size

        if tier == "1K":
            tier = "2K"

        if aspect_ratio == "1:1":
            return tier

        base = self._aspect_to_size_1k(aspect_ratio)
        w, h = map(int, base.split("x"))
        scale = {"2K": 2, "3K": 3, "4K": 4}.get(tier, 2)
        return f"{w * scale}x{h * scale}"

    @staticmethod
    def _aspect_to_size_1k(aspect_ratio: str) -> str:
        """Convert aspect ratio to 1K-tier pixel dimensions."""
        mapping = {
            "1:1": "1024x1024",
            "16:9": "1280x720",
            "9:16": "720x1280",
            "4:3": "1152x864",
            "3:4": "864x1152",
            "3:2": "1248x832",
            "2:3": "832x1248",
        }
        return mapping.get(aspect_ratio, "1024x1024")

    @staticmethod
    def _encode_references(reference_images: list[Path]) -> list[str]:
        """Encode reference images as base64 data URIs."""
        urls = []
        for ref_path in reference_images:
            if not ref_path.exists():
                continue
            try:
                with open(ref_path, "rb") as f:
                    data = f.read()
                if len(data) > 10 * 1024 * 1024:
                    print(f"[Jimeng] Skipping {ref_path.name}: exceeds 10MB limit")
                    continue
                b64 = base64.b64encode(data).decode()
                # Detect MIME type from file extension
                ext = ref_path.suffix.lower()
                mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(ext, "image/png")
                urls.append(f"data:{mime};base64,{b64}")
            except Exception as e:
                print(f"[Jimeng] Failed to encode {ref_path}: {e}")
        return urls
