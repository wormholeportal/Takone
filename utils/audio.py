"""Audio utilities for the Director video pipeline.

Provides AudioManager for:
- Importing/converting user-provided audio files
- Mixing background music + voiceover tracks
- Volume control and fade in/out
- Adding mixed audio to assembled video
"""

import subprocess
import shutil
import sys
from pathlib import Path


class AudioManager:
    """Manage audio tracks for video projects."""

    _GLOBAL_OPTS = [
        "-y",
        "-loglevel", "warning",
        "-hide_banner",
    ]

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.audio_dir = project_dir / "assets" / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def _run_ffmpeg(self, cmd: list, desc: str = "audio") -> subprocess.CompletedProcess:
        """Run an ffmpeg command with error handling."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                print(f"  [audio] ffmpeg {desc} warning: {result.stderr[:300]}", file=sys.stderr)
            return result
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"ffmpeg {desc} timed out after 120s")
        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found. Please install ffmpeg.")

    def import_music(self, source: Path, name: str = "bgm") -> Path:
        """Import a music file into the project's audio assets.

        Converts to AAC .m4a for consistency.

        Args:
            source: Path to the source audio file (mp3, wav, m4a, etc.)
            name: Output filename (without extension)

        Returns:
            Path to the imported audio file
        """
        if not source.exists():
            raise FileNotFoundError(f"Audio source not found: {source}")

        output = self.audio_dir / f"{name}.m4a"

        # Convert to AAC for consistency
        cmd = [
            "ffmpeg",
            *self._GLOBAL_OPTS,
            "-i", str(source),
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            str(output),
        ]
        self._run_ffmpeg(cmd, desc="import-music")
        return output

    def trim_audio(
        self,
        audio: Path,
        output: Path,
        duration: float,
        fade_out: float = 2.0,
        fade_in: float = 0.0,
    ) -> Path:
        """Trim audio to a specific duration with optional fade in/out.

        Args:
            audio: Input audio file
            output: Output audio file
            duration: Target duration in seconds
            fade_out: Fade out duration in seconds (at the end)
            fade_in: Fade in duration in seconds (at the start)

        Returns:
            Path to trimmed audio
        """
        output.parent.mkdir(parents=True, exist_ok=True)

        # Build audio filter chain
        filters = []
        if fade_in > 0:
            filters.append(f"afade=t=in:st=0:d={fade_in}")

        fade_start = max(0, duration - fade_out)
        if fade_out > 0:
            filters.append(f"afade=t=out:st={fade_start}:d={fade_out}")

        af_str = ",".join(filters) if filters else "anull"

        cmd = [
            "ffmpeg",
            *self._GLOBAL_OPTS,
            "-i", str(audio),
            "-t", str(duration),
            "-af", af_str,
            "-c:a", "aac",
            "-b:a", "192k",
            str(output),
        ]
        self._run_ffmpeg(cmd, desc="trim-audio")
        return output

    def normalize_loudness(
        self,
        audio: Path,
        output: Path,
        target_lufs: float = -14.0,
    ) -> Path:
        """Normalize audio loudness using EBU R128 standard.

        Uses FFmpeg's loudnorm filter. Target of -14 LUFS matches
        YouTube/Spotify/Douyin streaming standards.

        Args:
            audio: Input audio file
            output: Output audio file
            target_lufs: Target integrated loudness in LUFS (default: -14)

        Returns:
            Path to normalized audio
        """
        output.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg",
            *self._GLOBAL_OPTS,
            "-i", str(audio),
            "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            str(output),
        ]
        self._run_ffmpeg(cmd, desc="normalize-loudness")
        return output

    def adjust_volume(
        self,
        audio: Path,
        output: Path,
        volume: float = 0.4,
    ) -> Path:
        """Adjust audio volume.

        Args:
            audio: Input audio file
            output: Output audio file
            volume: Volume multiplier (0.0 = silent, 1.0 = original, >1.0 = louder)

        Returns:
            Path to volume-adjusted audio
        """
        output.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            *self._GLOBAL_OPTS,
            "-i", str(audio),
            "-af", f"volume={volume}",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output),
        ]
        self._run_ffmpeg(cmd, desc="adjust-volume")
        return output

    def mix_tracks(
        self,
        music: Path | None = None,
        voiceover: Path | None = None,
        output: Path | None = None,
        music_volume: float = 0.4,
        voiceover_volume: float = 1.0,
        duck_music_during_vo: bool = True,
    ) -> Path:
        """Mix background music and voiceover into a single audio track.

        When duck_music_during_vo is True and both tracks are provided,
        music volume is automatically reduced when voiceover is active.

        Args:
            music: Background music file path
            voiceover: Voiceover file path
            output: Output file path (defaults to audio_dir/mixed.m4a)
            music_volume: Background music volume (0.0-1.0)
            voiceover_volume: Voiceover volume (0.0-1.0)
            duck_music_during_vo: Whether to duck music during voiceover

        Returns:
            Path to mixed audio file
        """
        if not music and not voiceover:
            raise ValueError("At least one of music or voiceover must be provided")

        if output is None:
            output = self.audio_dir / "mixed.m4a"
        output.parent.mkdir(parents=True, exist_ok=True)

        # Single track — just adjust volume
        if music and not voiceover:
            return self.adjust_volume(music, output, music_volume)
        if voiceover and not music:
            return self.adjust_volume(voiceover, output, voiceover_volume)

        # Both tracks — mix with amix
        # Build filter: adjust volumes then mix
        filter_complex = (
            f"[0:a]volume={music_volume}[m];"
            f"[1:a]volume={voiceover_volume}[v];"
            f"[m][v]amix=inputs=2:duration=longest:dropout_transition=3[out]"
        )

        if duck_music_during_vo:
            # Use sidechaincompress for ducking: voiceover compresses music
            filter_complex = (
                f"[0:a]volume={music_volume}[m];"
                f"[1:a]volume={voiceover_volume}[v];"
                f"[m][v]sidechaincompress=threshold=0.02:ratio=6:attack=200:release=1000[ducked];"
                f"[ducked][v]amix=inputs=2:duration=longest:dropout_transition=3[out]"
            )

        cmd = [
            "ffmpeg",
            *self._GLOBAL_OPTS,
            "-i", str(music),
            "-i", str(voiceover),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            str(output),
        ]
        result = self._run_ffmpeg(cmd, desc="mix-tracks")

        # Fallback: if sidechaincompress fails, use simple amix
        if result.returncode != 0 and duck_music_during_vo:
            filter_simple = (
                f"[0:a]volume={music_volume}[m];"
                f"[1:a]volume={voiceover_volume}[v];"
                f"[m][v]amix=inputs=2:duration=longest:dropout_transition=3[out]"
            )
            cmd_fallback = [
                "ffmpeg",
                *self._GLOBAL_OPTS,
                "-i", str(music),
                "-i", str(voiceover),
                "-filter_complex", filter_simple,
                "-map", "[out]",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
                str(output),
            ]
            self._run_ffmpeg(cmd_fallback, desc="mix-tracks-fallback")

        return output

    def add_audio_to_video(
        self,
        video: Path,
        audio: Path,
        output: Path,
        replace_existing: bool = True,
    ) -> Path:
        """Add an audio track to a video file.

        Args:
            video: Input video file
            audio: Audio file to add
            output: Output video file
            replace_existing: If True, replace existing audio; if False, mix with existing

        Returns:
            Path to output video with audio
        """
        output.parent.mkdir(parents=True, exist_ok=True)

        if replace_existing:
            cmd = [
                "ffmpeg",
                *self._GLOBAL_OPTS,
                "-i", str(video),
                "-i", str(audio),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                "-movflags", "+faststart",
                str(output),
            ]
        else:
            # Mix with existing audio
            cmd = [
                "ffmpeg",
                *self._GLOBAL_OPTS,
                "-i", str(video),
                "-i", str(audio),
                "-c:v", "copy",
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:duration=shortest:dropout_transition=3[a]",
                "-map", "0:v:0",
                "-map", "[a]",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                str(output),
            ]

        self._run_ffmpeg(cmd, desc="add-audio-to-video")
        return output
