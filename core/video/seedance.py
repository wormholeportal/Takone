"""Jimeng Seedance video generation adapter.

Uses Volcengine Ark REST API (NOT the OpenAI SDK — Seedance has its own endpoints).

Endpoints:
  POST /api/v3/contents/generations/tasks   — create task
  GET  /api/v3/contents/generations/tasks/{id} — poll status

Models:
  doubao-seedance-1-0-lite-250428   (lite, fast)
  doubao-seedance-1-0-pro-250428    (standard, higher quality)
  doubao-seedance-1-0-pro-fast-250528 (pro fast)
  doubao-seedance-1-5-pro-251215    (1.5 pro, supports audio — DEFAULT)

Auth: ARK_API_KEY as Bearer token.

Task status values: queued → running → succeeded / failed / expired / cancelled
Video URLs expire after 24 hours.
"""

import asyncio
import base64
from pathlib import Path

import httpx

from .base import BaseVideoGen, VideoTask, GeneratedVideo


class SeedanceVideoGen(BaseVideoGen):
    def __init__(
        self,
        api_key: str = "",
        model: str = "doubao-seedance-1-5-pro-251215",
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        resolution: str = "720p",
        generate_audio: bool = True,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.resolution = resolution
        self.generate_audio = generate_audio

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers=self._headers(),
            proxy=None,
            trust_env=False,
            timeout=60.0,
        )

    async def text_to_video(
        self,
        prompt: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
    ) -> VideoTask:
        """Generate video from text prompt."""
        if not self.api_key:
            raise RuntimeError("No Seedance/Ark API key configured")

        payload = {
            "model": self.model,
            "content": [
                {"type": "text", "text": prompt},
            ],
            "ratio": aspect_ratio,
            "duration": self._resolve_duration(duration_seconds),
            "resolution": self.resolution,
            "generate_audio": self.generate_audio,
        }

        loop = asyncio.get_event_loop()

        def _create():
            with self._http_client() as client:
                resp = client.post("/contents/generations/tasks", json=payload)
                resp.raise_for_status()
                return resp.json()

        data = await loop.run_in_executor(None, _create)
        task_id = data.get("id", "")
        print(f"[Seedance] Task created: {task_id}")

        return VideoTask(
            task_id=task_id,
            provider="seedance",
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
            raise RuntimeError("No Seedance/Ark API key configured")

        # Encode first frame as base64 data URI
        with open(first_frame, "rb") as f:
            img_data = f.read()
        b64 = base64.b64encode(img_data).decode()
        ext = first_frame.suffix.lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "png")
        image_url = f"data:image/{mime};base64,{b64}"

        payload = {
            "model": self.model,
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                    "role": "first_frame",
                },
            ],
            "ratio": "adaptive",  # use adaptive for image-to-video
            "duration": self._resolve_duration(duration_seconds),
            "resolution": self.resolution,
            "generate_audio": self.generate_audio,
        }

        loop = asyncio.get_event_loop()

        def _create():
            with self._http_client() as client:
                resp = client.post("/contents/generations/tasks", json=payload)
                resp.raise_for_status()
                return resp.json()

        data = await loop.run_in_executor(None, _create)
        task_id = data.get("id", "")
        print(f"[Seedance] Task created (image-to-video): {task_id}")

        return VideoTask(
            task_id=task_id,
            provider="seedance",
            status="processing",
        )

    async def poll_task(self, task: VideoTask) -> VideoTask:
        """Check task status and download result when complete."""
        loop = asyncio.get_event_loop()

        def _retrieve():
            with self._http_client() as client:
                resp = client.get(f"/contents/generations/tasks/{task.task_id}")
                resp.raise_for_status()
                return resp.json()

        try:
            result = await loop.run_in_executor(None, _retrieve)
        except Exception as e:
            task.error = str(e)
            task.status = "failed"
            return task

        status = result.get("status", "unknown")

        if status == "succeeded":
            task.status = "completed"
            task.progress = 1.0

            # Extract video URL from response
            video_url = None
            content = result.get("content")
            if isinstance(content, dict):
                video_url = content.get("video_url")
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "video_url":
                        video_url = item.get("video_url", {}).get("url") or item.get("url")
                        break

            if video_url:
                video_data = await self._download_video(video_url)
                task.result = GeneratedVideo(
                    data=video_data,
                    prompt_used="",
                )
                print(f"[Seedance] Video downloaded ({len(video_data)} bytes)")
            else:
                task.error = f"No video URL in response: {result}"
                task.status = "failed"

        elif status in ("failed", "expired", "cancelled"):
            task.status = "failed"
            error_info = result.get("error", {})
            if isinstance(error_info, dict):
                task.error = error_info.get("message", str(error_info))
            else:
                task.error = str(error_info)

        else:
            # queued or running
            task.status = "processing"

        return task

    async def _download_video(self, url: str) -> bytes:
        """Download video from URL (URLs expire after 24h)."""
        loop = asyncio.get_event_loop()

        def _dl():
            with httpx.Client(proxy=None, trust_env=False, timeout=120.0) as c:
                r = c.get(url)
                r.raise_for_status()
                return r.content

        return await loop.run_in_executor(None, _dl)

    @staticmethod
    def _resolve_duration(seconds: float) -> int:
        """Convert seconds to Seedance duration parameter (integer)."""
        if seconds <= 5:
            return 5
        elif seconds <= 10:
            return 10
        return 5
