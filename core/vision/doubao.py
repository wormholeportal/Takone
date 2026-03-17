"""Doubao vision analysis adapter.

Uses Volcengine Ark API (OpenAI-compatible) for image/video understanding.
Shares ARK_API_KEY with Jimeng/Seedance.

Model: doubao-1-5-vision-pro-32k-250115
"""

import asyncio
import base64
from pathlib import Path

import httpx

from .base import BaseVision


class DoubaoVision(BaseVision):
    def __init__(
        self,
        api_key: str = "",
        model: str = "doubao-1-5-vision-pro-32k-250115",
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _get_client(self):
        """Create OpenAI client pointing to Ark API."""
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
        """Analyze image using Doubao Vision."""
        if not self.api_key:
            raise RuntimeError("No ARK_API_KEY configured for Doubao Vision")

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        ext = image_path.suffix.lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
        data_url = f"data:{mime};base64,{b64}"

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _call():
            return client.chat.completions.create(
                model=self.model,
                max_tokens=3000,
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
        """Analyze video by extracting frames and sending to Doubao Vision."""
        if not self.api_key:
            raise RuntimeError("No ARK_API_KEY configured for Doubao Vision")

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
                max_tokens=4000,
                messages=[{"role": "user", "content": content}],
            )

        response = await loop.run_in_executor(None, _call)

        # Cleanup temp frames
        for frame in frames:
            try:
                frame.unlink()
            except Exception:
                pass

        return response.choices[0].message.content
