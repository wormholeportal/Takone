"""Media Downloader — download images, videos, and files for creative research.

- Images: direct HTTP download via httpx
- Videos: yt-dlp for platform videos (Bilibili, YouTube, Douyin, etc.)
- Files: generic HTTP download
"""

import asyncio
import hashlib
import random
import re
import shutil
import sys
import time as _time
from pathlib import Path
from urllib.parse import urlparse, unquote


class DownloadError(Exception):
    """Raised when a download fails."""
    pass


# Module-level download throttle — shared across all MediaDownloader instances
_last_download_time: float = 0.0
_DOWNLOAD_MIN_INTERVAL = 2.0  # seconds
_DOWNLOAD_MAX_INTERVAL = 5.0  # seconds


class MediaDownloader:
    """Download various media files for research."""

    @staticmethod
    async def _throttle():
        """Enforce a random delay between consecutive downloads to avoid anti-scraping."""
        global _last_download_time
        now = _time.monotonic()
        elapsed = now - _last_download_time
        required = random.uniform(_DOWNLOAD_MIN_INTERVAL, _DOWNLOAD_MAX_INTERVAL)
        if elapsed < required:
            await asyncio.sleep(required - elapsed)
        _last_download_time = _time.monotonic()

    # ── Image download ────────────────────────────────────────────────

    async def download_image(
        self,
        url: str,
        save_dir: Path,
        filename: str | None = None,
    ) -> Path:
        """Download an image via HTTP.

        Args:
            url: Image URL.
            save_dir: Directory to save the image.
            filename: Optional custom filename. Auto-generated if not provided.

        Returns:
            Path to the saved image file.
        """
        await self._throttle()
        import httpx

        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Encode URL for safe HTTP usage (handle non-ASCII chars like Chinese)
            from urllib.parse import quote, urlparse as _urlparse, urlunparse
            from core.browser.playwright import random_ua

            _p = _urlparse(url)
            safe_url = urlunparse(_p._replace(path=quote(_p.path, safe='/'), query=quote(_p.query, safe='=&')))

            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                verify=False,
                headers={
                    "User-Agent": random_ua(),
                    "Referer": safe_url,
                },
            ) as client:
                # Retry with exponential backoff
                max_retries = 3
                resp = None
                for attempt in range(max_retries):
                    try:
                        resp = await client.get(safe_url)
                        if resp.status_code == 429:
                            retry_after = int(resp.headers.get("Retry-After", 3 * (2 ** attempt)))
                            await asyncio.sleep(min(retry_after, 60))
                            continue
                        resp.raise_for_status()
                        break
                    except httpx.HTTPStatusError as e:
                        if attempt < max_retries - 1 and e.response.status_code in (429, 503):
                            await asyncio.sleep(3 * (2 ** attempt))
                            continue
                        raise

                if resp is None:
                    raise DownloadError(f"Failed after {max_retries} retries: {url}")

                # Determine extension from content-type or URL
                content_type = resp.headers.get("content-type", "")
                ext = _ext_from_content_type(content_type) or _ext_from_url(url) or ".jpg"

                if not filename:
                    filename = _safe_filename_from_url(url, ext)

                # Ensure extension
                if not Path(filename).suffix:
                    filename += ext

                save_path = save_dir / filename
                save_path.write_bytes(resp.content)

                size_kb = len(resp.content) / 1024
                print(f"  ✓ Image downloaded: {save_path.name} ({size_kb:.0f} KB)", file=sys.stderr)
                return save_path

        except httpx.HTTPStatusError as e:
            raise DownloadError(f"HTTP {e.response.status_code} downloading image: {url}") from e
        except Exception as e:
            raise DownloadError(f"Failed to download image: {e}") from e

    # ── Video download (yt-dlp) ───────────────────────────────────────

    async def download_video(
        self,
        url: str,
        save_dir: Path,
        max_duration: int = 300,
        filename: str | None = None,
    ) -> Path:
        """Download a video using yt-dlp.

        Supports: Bilibili, YouTube, Douyin, Xiaohongshu, and many more.

        Args:
            url: Video page URL.
            save_dir: Directory to save the video.
            max_duration: Max video duration in seconds (default: 5 min). 0 = no limit.
            filename: Optional custom filename (without extension).

        Returns:
            Path to the saved video file.
        """
        await self._throttle()
        # Check yt-dlp availability
        ytdlp = shutil.which("yt-dlp")
        if not ytdlp:
            raise DownloadError(
                "yt-dlp not found. Install it:\n"
                "  brew install yt-dlp   (macOS)\n"
                "  pip install yt-dlp    (pip)"
            )

        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        # Build output template
        if filename:
            # Strip extension if provided
            filename = Path(filename).stem
            output_template = str(save_dir / f"{filename}.%(ext)s")
        else:
            output_template = str(save_dir / "%(title).80s.%(ext)s")

        cmd = [
            ytdlp,
            "--no-playlist",
            "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "--merge-output-format", "mp4",
            "-o", output_template,
            "--no-overwrites",
            "--no-warnings",
            "--quiet",
            "--progress",
        ]

        # Add duration limit if set
        if max_duration > 0:
            cmd.extend(["--match-filter", f"duration<={max_duration}"])

        # Platform-specific cookies (use browser cookies if available)
        cookies_dir = Path.home() / ".director" / "browser-profile"
        if cookies_dir.exists():
            # Try to use cookies from Chrome profile for authenticated downloads
            cmd.extend(["--cookies-from-browser", f"chrome:{cookies_dir}"])

        cmd.append(url)

        print(f"  ⏳ Downloading video: {url[:80]}...", file=sys.stderr)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=600,  # 10 min max
        )

        if proc.returncode != 0:
            error_msg = stderr.decode(errors="replace").strip()
            # Common error: duration filter
            if "does not pass filter" in error_msg:
                raise DownloadError(
                    f"Video exceeds max duration ({max_duration}s). "
                    f"Set max_duration=0 to disable limit."
                )
            raise DownloadError(f"yt-dlp failed (exit {proc.returncode}): {error_msg[:500]}")

        # Find the downloaded file (yt-dlp may adjust the filename)
        if filename:
            # Look for the specific file
            candidates = list(save_dir.glob(f"{filename}.*"))
        else:
            # Find the most recently created .mp4 file
            candidates = sorted(save_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)

        if not candidates:
            # Fallback: any new video file
            candidates = sorted(
                [p for p in save_dir.iterdir() if p.suffix in {".mp4", ".mkv", ".webm", ".flv"}],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

        if not candidates:
            raise DownloadError("yt-dlp completed but no video file found")

        result = candidates[0]
        size_mb = result.stat().st_size / (1024 * 1024)
        print(f"  ✓ Video downloaded: {result.name} ({size_mb:.1f} MB)", file=sys.stderr)
        return result

    # ── Generic file download ─────────────────────────────────────────

    async def download_file(
        self,
        url: str,
        save_dir: Path,
        filename: str | None = None,
    ) -> Path:
        """Download any file via HTTP.

        Args:
            url: File URL.
            save_dir: Directory to save the file.
            filename: Optional custom filename.

        Returns:
            Path to the saved file.
        """
        await self._throttle()
        import httpx

        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        try:
            from core.browser.playwright import random_ua

            async with httpx.AsyncClient(
                timeout=60,
                follow_redirects=True,
                verify=False,
                headers={
                    "User-Agent": random_ua(),
                },
            ) as client:
                # Retry with exponential backoff
                max_retries = 3
                resp = None
                for attempt in range(max_retries):
                    try:
                        resp = await client.get(url)
                        if resp.status_code == 429:
                            await asyncio.sleep(3 * (2 ** attempt))
                            continue
                        resp.raise_for_status()
                        break
                    except httpx.HTTPStatusError as e:
                        if attempt < max_retries - 1 and e.response.status_code in (429, 503):
                            await asyncio.sleep(3 * (2 ** attempt))
                            continue
                        raise

                if resp is None:
                    raise DownloadError(f"Failed after {max_retries} retries: {url}")

                if not filename:
                    # Try Content-Disposition header
                    cd = resp.headers.get("content-disposition", "")
                    if "filename=" in cd:
                        filename = re.search(r'filename="?(.+?)"?$', cd)
                        filename = filename.group(1) if filename else None

                if not filename:
                    filename = _safe_filename_from_url(url, _ext_from_url(url) or "")

                save_path = save_dir / filename
                save_path.write_bytes(resp.content)

                size_kb = len(resp.content) / 1024
                print(f"  ✓ File downloaded: {save_path.name} ({size_kb:.0f} KB)", file=sys.stderr)
                return save_path

        except Exception as e:
            raise DownloadError(f"Failed to download file: {e}") from e


# ── Helpers ───────────────────────────────────────────────────────────

def _ext_from_content_type(ct: str) -> str | None:
    """Map Content-Type to file extension."""
    ct = ct.split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "image/bmp": ".bmp",
        "application/pdf": ".pdf",
        "text/html": ".html",
        "text/plain": ".txt",
    }
    return mapping.get(ct)


def _ext_from_url(url: str) -> str | None:
    """Extract file extension from URL path."""
    path = urlparse(url).path
    ext = Path(path).suffix.lower()
    if ext and len(ext) <= 5 and ext.isascii():
        return ext
    return None


def _safe_filename_from_url(url: str, ext: str) -> str:
    """Generate a safe filename from a URL."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    name = Path(path).stem

    # Clean up
    name = re.sub(r'[/\\:*?"<>|\s]+', '_', name).strip('_')

    if not name or len(name) < 3:
        # Fallback: hash of URL
        name = hashlib.md5(url.encode()).hexdigest()[:12]

    # Truncate
    name = name[:80]

    return name + ext
