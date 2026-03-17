"""Claude vision analysis adapter."""

import asyncio
import base64
from pathlib import Path

from .base import BaseVision


class ClaudeVision(BaseVision):
    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.api_key) if self.api_key else Anthropic()
        return self._client

    async def analyze_image(
        self,
        image_path: Path,
        prompt: str,
    ) -> str:
        """Analyze image using Claude Vision."""
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        media_type = "image/png" if image_path.suffix == ".png" else "image/jpeg"

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _call():
            return client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            )

        response = await loop.run_in_executor(None, _call)
        return response.content[0].text

    async def analyze_video(
        self,
        video_path: Path,
        prompt: str,
        sample_frames: int = 8,
    ) -> str:
        """Analyze video by extracting frames and sending to Claude."""
        frames = await self.extract_frames_async(video_path, sample_frames)
        if not frames:
            return "Failed to extract frames from video. Is FFmpeg installed?"

        content = []
        for frame in frames:
            with open(frame, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": b64,
                },
            })
        content.append({
            "type": "text",
            "text": f"{prompt}\n\nAbove are {len(frames)} keyframes from the video. Please analyze the video quality.",
        })

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _call():
            return client.messages.create(
                model=self.model,
                max_tokens=3000,
                messages=[{"role": "user", "content": content}],
            )

        response = await loop.run_in_executor(None, _call)

        for frame in frames:
            try:
                frame.unlink()
            except Exception:
                pass

        return response.content[0].text
