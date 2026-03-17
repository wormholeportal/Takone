"""Minimax video generation adapter.

Uses the Minimax API for video generation.
Pattern: create async task → poll status → download video URL.

Models:
  video-01        (standard quality)
  video-01-live2d (anime style)
"""

import asyncio
import base64
from pathlib import Path

from .base import BaseVideoGen, VideoTask, GeneratedVideo


class MinimaxVideoGen(BaseVideoGen):
    API_BASE = "https://api.minimax.chat/v1"

    def __init__(
        self,
        api_key: str = "",
        model: str = "video-01",
    ):
        self.api_key = api_key
        self.model = model

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def text_to_video(
        self,
        prompt: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
    ) -> VideoTask:
        """Generate video from text prompt."""
        if not self.api_key:
            raise RuntimeError("No Minimax API key configured")

        import httpx
        loop = asyncio.get_event_loop()

        def _create():
            with httpx.Client(timeout=60.0) as c:
                r = c.post(
                    f"{self.API_BASE}/video_generation",
                    headers=self._headers(),
                    json={
                        "model": self.model,
                        "prompt": prompt,
                    },
                )
                r.raise_for_status()
                return r.json()

        data = await loop.run_in_executor(None, _create)
        task_id = data.get("task_id", "")
        print(f"[Minimax] Task created: {task_id}")

        return VideoTask(
            task_id=task_id,
            provider="minimax",
            status="processing",
        )

    async def image_to_video(
        self,
        prompt: str,
        first_frame: Path,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
    ) -> VideoTask:
        """Generate video from text + first frame image."""
        if not self.api_key:
            raise RuntimeError("No Minimax API key configured")

        # Encode first frame
        with open(first_frame, "rb") as f:
            img_data = f.read()
        b64 = base64.b64encode(img_data).decode()

        import httpx
        loop = asyncio.get_event_loop()

        def _create():
            with httpx.Client(timeout=60.0) as c:
                r = c.post(
                    f"{self.API_BASE}/video_generation",
                    headers=self._headers(),
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "first_frame_image": f"data:image/png;base64,{b64}",
                    },
                )
                r.raise_for_status()
                return r.json()

        data = await loop.run_in_executor(None, _create)
        task_id = data.get("task_id", "")
        print(f"[Minimax] Task created (image-to-video): {task_id}")

        return VideoTask(
            task_id=task_id,
            provider="minimax",
            status="processing",
        )

    async def poll_task(self, task: VideoTask) -> VideoTask:
        """Check task status."""
        import httpx
        loop = asyncio.get_event_loop()

        def _query():
            with httpx.Client(timeout=30.0) as c:
                r = c.get(
                    f"{self.API_BASE}/query/video_generation",
                    headers=self._headers(),
                    params={"task_id": task.task_id},
                )
                r.raise_for_status()
                return r.json()

        data = await loop.run_in_executor(None, _query)
        status = data.get("status", "unknown")

        if status == "Success":
            task.status = "completed"
            task.progress = 1.0
            file_id = data.get("file_id", "")
            if file_id:
                video_data = await self._download_file(file_id)
                task.result = GeneratedVideo(data=video_data)
                print(f"[Minimax] Video downloaded ({len(video_data)} bytes)")
            else:
                task.error = "No file_id in response"
                task.status = "failed"
        elif status in ("Fail", "Failed"):
            task.status = "failed"
            task.error = data.get("error", "Unknown error")
        else:
            task.status = "processing"

        return task

    async def _download_file(self, file_id: str) -> bytes:
        """Download video file by file_id."""
        import httpx
        loop = asyncio.get_event_loop()

        def _dl():
            with httpx.Client(timeout=120.0) as c:
                r = c.get(
                    f"{self.API_BASE}/files/retrieve",
                    headers=self._headers(),
                    params={"file_id": file_id},
                )
                r.raise_for_status()
                return r.content

        return await loop.run_in_executor(None, _dl)
