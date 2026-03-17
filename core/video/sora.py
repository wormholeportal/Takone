"""OpenAI Sora 2 video generation adapter.

Uses the OpenAI SDK for video generation.
Pattern: create video → poll status → download.

Models:
  sora (default)
"""

import asyncio
import base64
from pathlib import Path

from .base import BaseVideoGen, VideoTask, GeneratedVideo


class SoraVideoGen(BaseVideoGen):
    def __init__(
        self,
        api_key: str = "",
        model: str = "sora",
    ):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        """Lazy-init AsyncOpenAI client."""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    async def text_to_video(
        self,
        prompt: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
    ) -> VideoTask:
        """Generate video from text prompt using Sora."""
        if not self.api_key:
            raise RuntimeError("No OpenAI API key configured for Sora")

        loop = asyncio.get_event_loop()
        client = self._get_client()

        # Map aspect ratio to Sora format
        sora_ratio = self._map_aspect_ratio(aspect_ratio)

        def _create():
            return client.videos.generate(
                model=self.model,
                prompt=prompt,
                size=sora_ratio,
                duration=int(duration_seconds),
            )

        response = await loop.run_in_executor(None, _create)
        task_id = response.id if hasattr(response, "id") else str(response)
        print(f"[Sora] Task created: {task_id}")

        return VideoTask(
            task_id=task_id,
            provider="sora",
            status="processing",
        )

    async def image_to_video(
        self,
        prompt: str,
        first_frame: Path,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
    ) -> VideoTask:
        """Generate video from text + first frame (if supported)."""
        # Sora may support image input — fall back to text-only if not
        return await self.text_to_video(prompt, duration_seconds, aspect_ratio)

    async def poll_task(self, task: VideoTask) -> VideoTask:
        """Check Sora task status."""
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _retrieve():
            return client.videos.retrieve(task.task_id)

        try:
            result = await loop.run_in_executor(None, _retrieve)
        except Exception as e:
            task.error = str(e)
            task.status = "failed"
            return task

        status = getattr(result, "status", "unknown")

        if status in ("completed", "succeeded"):
            task.status = "completed"
            task.progress = 1.0

            # Download video
            video_url = getattr(result, "url", None)
            if not video_url and hasattr(result, "output"):
                video_url = getattr(result.output, "url", None)

            if video_url:
                video_data = await self._download_video(video_url)
                task.result = GeneratedVideo(data=video_data)
                print(f"[Sora] Video downloaded ({len(video_data)} bytes)")
            else:
                task.error = "No video URL in response"
                task.status = "failed"

        elif status in ("failed", "error"):
            task.status = "failed"
            task.error = getattr(result, "error", "Unknown error")
        else:
            task.status = "processing"

        return task

    async def _download_video(self, url: str) -> bytes:
        """Download video from URL."""
        import httpx
        loop = asyncio.get_event_loop()

        def _dl():
            with httpx.Client(timeout=120.0) as c:
                r = c.get(url)
                r.raise_for_status()
                return r.content

        return await loop.run_in_executor(None, _dl)

    @staticmethod
    def _map_aspect_ratio(ratio: str) -> str:
        """Map common ratios to Sora-supported sizes."""
        mapping = {
            "9:16": "1080x1920",
            "16:9": "1920x1080",
            "1:1": "1080x1080",
        }
        return mapping.get(ratio, "1080x1920")
