"""Abstract base class for video generation providers."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GeneratedVideo:
    data: bytes
    mime_type: str = "video/mp4"
    prompt_used: str = ""
    duration_seconds: float = 0.0

    def save(self, path: Path):
        """Save video data to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(self.data)


@dataclass
class VideoTask:
    """Async video generation task (for polling-based APIs)."""
    task_id: str
    provider: str
    status: str = "pending"  # pending | processing | completed | failed
    progress: float = 0.0
    result: GeneratedVideo | None = None
    error: str | None = None


class BaseVideoGen(ABC):
    """Abstract video generation interface.

    All video APIs are async task-based: submit → poll → download.
    """

    @abstractmethod
    async def text_to_video(
        self,
        prompt: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
    ) -> VideoTask:
        """Generate video from text prompt. Returns a task for polling."""
        ...

    @abstractmethod
    async def image_to_video(
        self,
        prompt: str,
        first_frame: Path,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
    ) -> VideoTask:
        """Generate video from text + first frame image."""
        ...

    @abstractmethod
    async def poll_task(self, task: VideoTask) -> VideoTask:
        """Check task status and download result when complete."""
        ...

    async def wait_for_result(
        self,
        task: VideoTask,
        poll_interval: float = 10.0,
        timeout: float = 300.0,
        on_progress=None,
    ) -> VideoTask:
        """Poll until task completes or times out."""
        elapsed = 0.0
        while elapsed < timeout:
            task = await self.poll_task(task)
            if on_progress:
                on_progress(task)
            if task.status in ("completed", "failed"):
                return task
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        task.status = "failed"
        task.error = f"Timeout after {timeout}s"
        return task
