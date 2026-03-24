"""Kimi K2.5 vision analysis adapter.

Uses Moonshot AI API (OpenAI-compatible) for image/video understanding.
Kimi K2.5 natively supports video_url content type — no frame extraction needed.

Model: kimi-k2.5 (256K context, multimodal)
API: https://api.moonshot.ai/v1
"""

import asyncio
import base64
from pathlib import Path

import httpx

from .base import BaseVision


class KimiVision(BaseVision):
    def __init__(
        self,
        api_key: str = "",
        model: str = "kimi-k2.5",
        base_url: str = "https://api.moonshot.ai/v1",
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _get_client(self):
        """Create OpenAI client pointing to Moonshot AI API."""
        from openai import OpenAI
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=httpx.Client(proxy=None, trust_env=False),
        )

    async def analyze_image(
        self,
        image_path: Path,
        prompt: str,
    ) -> str:
        """Analyze image using Kimi K2.5."""
        if not self.api_key:
            raise RuntimeError("No MOONSHOT_API_KEY configured for Kimi Vision")

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        ext = image_path.suffix.lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/png")
        data_url = f"data:{mime};base64,{b64}"

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _call():
            return client.chat.completions.create(
                model=self.model,
                max_completion_tokens=3000,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }],
            )

        response = await loop.run_in_executor(None, _call)
        return response.choices[0].message.content

    async def analyze_video(
        self,
        video_path: Path,
        prompt: str,
        sample_frames: int = 8,
    ) -> str:
        """Analyze video using Kimi K2.5 native video understanding.

        Kimi K2.5 supports video_url content type directly — no frame extraction needed.
        For videos over 100MB, falls back to frame extraction.
        """
        if not self.api_key:
            raise RuntimeError("No MOONSHOT_API_KEY configured for Kimi Vision")

        file_size = video_path.stat().st_size

        # Kimi has 100MB request body limit; for large videos, fall back to frame extraction
        if file_size > 80 * 1024 * 1024:  # 80MB safety margin
            return await self._analyze_video_frames(video_path, prompt, sample_frames)

        with open(video_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        ext = video_path.suffix.lower().lstrip(".")
        mime = {"mp4": "video/mp4", "mov": "video/quicktime", "avi": "video/x-msvideo",
                "webm": "video/webm", "mkv": "video/x-matroska", "flv": "video/x-flv",
                "wmv": "video/x-ms-wmv", "mpeg": "video/mpeg", "mpg": "video/mpeg",
                "3gpp": "video/3gpp"}.get(ext, "video/mp4")
        data_url = f"data:{mime};base64,{b64}"

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _call():
            return client.chat.completions.create(
                model=self.model,
                max_completion_tokens=4000,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "video_url", "video_url": {"url": data_url}},
                    ],
                }],
            )

        response = await loop.run_in_executor(None, _call)
        return response.choices[0].message.content

    async def _analyze_video_frames(
        self,
        video_path: Path,
        prompt: str,
        sample_frames: int = 8,
    ) -> str:
        """Fallback: analyze video via frame extraction (for large videos)."""
        frames = await self.extract_frames_async(video_path, sample_frames)
        if not frames:
            return "Failed to extract frames from video. Please check FFmpeg installation."

        content = [{"type": "text", "text": f"{prompt}\n\nBelow are {len(frames)} keyframes from the video:"}]
        for frame in frames:
            with open(frame, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _call():
            return client.chat.completions.create(
                model=self.model,
                max_completion_tokens=4000,
                messages=[{"role": "user", "content": content}],
            )

        response = await loop.run_in_executor(None, _call)

        for frame in frames:
            try:
                frame.unlink()
            except Exception:
                pass

        return response.choices[0].message.content
