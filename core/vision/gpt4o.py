"""GPT-4o vision analysis adapter."""

import asyncio
import base64
from pathlib import Path

from .base import BaseVision


class GPT4oVision(BaseVision):
    def __init__(self, api_key: str = "", model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    async def analyze_image(
        self,
        image_path: Path,
        prompt: str,
    ) -> str:
        """Analyze image using GPT-4o Vision."""
        if not self.api_key:
            raise RuntimeError("No OpenAI API key configured for vision")

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        mime = "image/png" if image_path.suffix == ".png" else "image/jpeg"
        data_url = f"data:{mime};base64,{b64}"

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _call():
            return client.chat.completions.create(
                model=self.model,
                max_tokens=2000,
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
        """Analyze video by extracting frames and sending to GPT-4o."""
        frames = await self.extract_frames_async(video_path, sample_frames)
        if not frames:
            return "Failed to extract frames from video. Is FFmpeg installed?"

        # Build multi-image message
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
                max_tokens=3000,
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
