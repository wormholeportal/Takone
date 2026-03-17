"""Abstract base class for vision/video analysis providers."""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path


class BaseVision(ABC):
    """Abstract vision analysis interface."""

    @abstractmethod
    async def analyze_image(
        self,
        image_path: Path,
        prompt: str,
    ) -> str:
        """Analyze a single image with a prompt. Returns textual analysis."""
        ...

    @abstractmethod
    async def analyze_video(
        self,
        video_path: Path,
        prompt: str,
        sample_frames: int = 8,
    ) -> str:
        """Analyze a video (via frame sampling) with a prompt."""
        ...

    @staticmethod
    def extract_frames(video_path: Path, num_frames: int = 8) -> list[Path]:
        """Extract key frames from video using FFmpeg (sync version)."""
        import subprocess
        import tempfile

        output_dir = Path(tempfile.mkdtemp())
        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-vf", f"select='not(mod(n,{max(1, 30 // num_frames)}))',setpts=N/FRAME_RATE/TB",
            "-frames:v", str(num_frames),
            "-q:v", "2",
            str(output_dir / "frame_%03d.jpg"),
            "-y", "-loglevel", "error",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

        frames = sorted(output_dir.glob("frame_*.jpg"))
        return frames[:num_frames]

    @staticmethod
    async def extract_frames_async(video_path: Path, num_frames: int = 8) -> list[Path]:
        """Extract key frames from video using FFmpeg (async, non-blocking)."""
        return await asyncio.to_thread(BaseVision.extract_frames, video_path, num_frames)
