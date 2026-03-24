"""FFmpeg wrapper for video clip assembly."""

import subprocess
import sys
import tempfile
from pathlib import Path


class FFmpegAssembler:
    """Assemble video clips into a final output."""

    _AUDIO_OPTS = [
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",              # Consistent sample rate
        "-ac", "2",                  # Stereo
    ]
    _GLOBAL_OPTS = [
        "-y",                        # Overwrite output
        "-loglevel", "warning",      # Show warnings (not just errors)
        "-hide_banner",
    ]
    _CONTAINER_OPTS = [
        "-movflags", "+faststart",   # Web/QuickTime playback
    ]

    def __init__(self, crf: int = 18, preset: str = "slow", fps: int = 30):
        """Initialize with encoding quality settings.

        Args:
            crf: Constant Rate Factor (0-51). Lower = better quality. 18 = visually lossless.
            preset: x264 encoding preset. "slow" gives best quality/size ratio.
            fps: Output framerate. 30 ensures consistent playback across all clips.
        """
        self._fps = fps
        # Mac QuickTime compatible encoding settings (instance-level for configurability)
        self._VIDEO_OPTS = [
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",       # MUST be yuv420p for QuickTime
            "-profile:v", "high",
            "-level", "4.1",
            "-preset", preset,
            "-crf", str(crf),
            "-r", str(fps),
        ]

    def trim_clip(
        self,
        clip: Path,
        output: Path,
        trim_start: float = 0.0,
        trim_end: float = None,
    ) -> Path:
        """Trim a video clip to a specific time range.

        Args:
            clip: Input video path
            output: Output video path
            trim_start: Start time in seconds
            trim_end: End time in seconds (None = end of video)
        """
        output.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            *self._GLOBAL_OPTS,
            "-ss", str(trim_start),
        ]
        if trim_end is not None:
            cmd.extend(["-to", str(trim_end)])
        cmd.extend([
            "-i", str(clip),
            *self._VIDEO_OPTS,
        ])
        if self._has_audio_stream(clip):
            cmd.extend(self._AUDIO_OPTS)
        else:
            cmd.append("-an")
        cmd.extend(self._CONTAINER_OPTS)
        cmd.append(str(output))

        self._run_ffmpeg(cmd, desc="trim-clip")
        return output

    def concatenate(
        self,
        clips: list[Path],
        output: Path,
        transition: str = "none",
        transition_duration: float = 0.5,
        trims: list[dict] = None,
    ) -> Path:
        """Concatenate video clips into a single video.

        Uses FFmpeg concat demuxer for simple concatenation,
        or filter_complex for transitions.

        Args:
            clips: List of video clip paths
            output: Output video path
            transition: Transition type (none, fade, dissolve, etc.)
            transition_duration: Transition duration in seconds
            trims: Optional list of trim dicts with 'start' and/or 'end' keys,
                   one per clip. Use to extract the best segment from each clip.
                   Example: [{"start": 1.0, "end": 3.0}, None, {"start": 0, "end": 2.5}]
        """
        if not clips:
            raise ValueError("No clips to concatenate")

        output.parent.mkdir(parents=True, exist_ok=True)

        # Apply trimming if specified
        actual_clips = clips
        trimmed_files = []
        if trims:
            import tempfile as _tmpmod
            actual_clips = []
            for i, clip in enumerate(clips):
                trim = trims[i] if i < len(trims) else None
                if trim and (trim.get("start", 0) > 0 or trim.get("end") is not None):
                    trimmed = Path(_tmpmod.mktemp(suffix=".mp4"))
                    self.trim_clip(
                        clip, trimmed,
                        trim_start=trim.get("start", 0.0),
                        trim_end=trim.get("end"),
                    )
                    actual_clips.append(trimmed)
                    trimmed_files.append(trimmed)
                else:
                    actual_clips.append(clip)

        try:
            if transition == "none" or len(actual_clips) == 1:
                return self._concat_simple(actual_clips, output)
            else:
                return self._concat_with_transition(actual_clips, output, transition, transition_duration)
        finally:
            # Cleanup trimmed temp files
            for f in trimmed_files:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

    def _run_ffmpeg(self, cmd: list[str], desc: str = "") -> subprocess.CompletedProcess:
        """Run an FFmpeg command with proper error handling."""
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
            # Print any warnings to stderr for debugging
            if result.stderr and result.stderr.strip():
                print(f"  [FFmpeg {desc}] {result.stderr.strip()}", file=sys.stderr)
            return result
        except subprocess.CalledProcessError as e:
            # Print the full error for debugging
            print(f"  [FFmpeg ERROR {desc}]", file=sys.stderr)
            if e.stderr:
                print(f"  stderr: {e.stderr.strip()}", file=sys.stderr)
            if e.stdout:
                print(f"  stdout: {e.stdout.strip()}", file=sys.stderr)
            raise

    def _normalize_clip(self, clip: Path, output: Path) -> Path:
        """Re-encode a clip to the target fps to ensure consistent frame timing.

        This prevents the concat demuxer bug where mixed-fps inputs cause
        video stream duration to diverge from audio stream duration.
        """
        # Check if already at target fps
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "csv=p=0",
                str(clip),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            fps_str = result.stdout.strip()
            if "/" in fps_str:
                num, den = fps_str.split("/")
                clip_fps = int(num) / int(den) if int(den) > 0 else 0
            else:
                clip_fps = float(fps_str)
            if abs(clip_fps - self._fps) < 0.5:
                return clip  # Already at target fps, no normalization needed
        except Exception:
            pass  # Can't determine fps, normalize to be safe

        output.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            *self._GLOBAL_OPTS,
            "-i", str(clip),
            *self._VIDEO_OPTS,
        ]
        if self._has_audio_stream(clip):
            cmd.extend(self._AUDIO_OPTS)
        else:
            cmd.append("-an")
        cmd.extend(self._CONTAINER_OPTS)
        cmd.append(str(output))

        self._run_ffmpeg(cmd, desc="normalize-fps")
        return output

    def _normalize_clips(self, clips: list[Path]) -> tuple[list[Path], list[Path]]:
        """Normalize all clips to target fps. Returns (normalized_clips, temp_files_to_cleanup)."""
        normalized = []
        temps = []
        for clip in clips:
            norm_path = Path(tempfile.mktemp(suffix=".mp4"))
            result = self._normalize_clip(clip, norm_path)
            if result == clip:
                # Clip was already at target fps, no temp file created
                normalized.append(clip)
                norm_path.unlink(missing_ok=True)
            else:
                normalized.append(norm_path)
                temps.append(norm_path)
        return normalized, temps

    def _concat_simple(self, clips: list[Path], output: Path) -> Path:
        """Simple concatenation using concat demuxer with re-encoding.

        Normalizes all clips to the target fps first to prevent the mixed-fps
        concat demuxer bug (where video/audio durations diverge).
        Then handles mixed audio/no-audio clips by adding silent audio tracks.
        """
        # Step 0: Normalize all clips to target fps to prevent mixed-fps bugs
        norm_clips, norm_temps = self._normalize_clips(clips)

        try:
            has_audio = any(self._has_audio_stream(c) for c in norm_clips)

            if not has_audio:
                return self._concat_demuxer(norm_clips, output, with_audio=False)

            all_have_audio = all(self._has_audio_stream(c) for c in norm_clips)
            if all_have_audio:
                return self._concat_demuxer(norm_clips, output, with_audio=True)

            # Mixed case: patch clips without audio
            patched_clips = []
            patch_temps = []
            try:
                for clip in norm_clips:
                    if self._has_audio_stream(clip):
                        patched_clips.append(clip)
                    else:
                        patched = Path(tempfile.mktemp(suffix=".mp4"))
                        dur = self._get_duration(clip)
                        cmd = [
                            "ffmpeg",
                            *self._GLOBAL_OPTS,
                            "-i", str(clip),
                            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={dur}",
                            "-c:v", "copy",
                            *self._AUDIO_OPTS,
                            "-shortest",
                            *self._CONTAINER_OPTS,
                            str(patched),
                        ]
                        self._run_ffmpeg(cmd, desc="add-silent-audio")
                        patched_clips.append(patched)
                        patch_temps.append(patched)

                return self._concat_demuxer(patched_clips, output, with_audio=True)
            finally:
                for f in patch_temps:
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass
        finally:
            for f in norm_temps:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

    def _concat_demuxer(self, clips: list[Path], output: Path, with_audio: bool) -> Path:
        """Concatenate using concat demuxer with re-encoding."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for clip in clips:
                f.write(f"file '{clip.resolve()}'\n")
            concat_file = f.name

        try:
            cmd = [
                "ffmpeg",
                *self._GLOBAL_OPTS,
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                *self._VIDEO_OPTS,
            ]
            if with_audio:
                cmd.extend(self._AUDIO_OPTS)
            else:
                cmd.append("-an")
            cmd.extend(self._CONTAINER_OPTS)
            cmd.append(str(output))

            self._run_ffmpeg(cmd, desc="concat-demuxer")
            return output
        finally:
            Path(concat_file).unlink(missing_ok=True)

    def _concat_with_transition(
        self,
        clips: list[Path],
        output: Path,
        transition: str,
        duration: float,
    ) -> Path:
        """Concatenation with crossfade transitions (video + audio)."""
        inputs = []
        for clip in clips:
            inputs.extend(["-i", str(clip)])

        # Normalize timebases for xfade compatibility
        settb_parts = []
        for i in range(len(clips)):
            settb_parts.append(f"[{i}:v]settb=AVTB,fps={self._fps}[norm{i}]")

        # Build video xfade filter chain using normalized streams
        v_parts = []
        current_v = "[norm0]"
        clip_durations = [self._get_duration(c) for c in clips]
        running_duration = clip_durations[0]
        for i in range(1, len(clips)):
            next_v = f"[norm{i}]"
            out_v = f"[v{i}]" if i < len(clips) - 1 else "[outv]"
            offset = max(0, running_duration - duration)
            running_duration = running_duration + clip_durations[i] - duration
            v_parts.append(
                f"{current_v}{next_v}xfade=transition={transition}:"
                f"duration={duration}:offset={offset}{out_v}"
            )
            current_v = out_v

        if not v_parts:
            return self._concat_simple(clips, output)

        # Check if any clip has audio
        has_audio = any(self._has_audio_stream(c) for c in clips)

        if has_audio:
            # Build audio acrossfade filter chain
            a_parts = []
            current_a = "[0:a]"
            for i in range(1, len(clips)):
                next_a = f"[{i}:a]"
                out_a = f"[a{i}]" if i < len(clips) - 1 else "[outa]"
                a_parts.append(
                    f"{current_a}{next_a}acrossfade=d={duration}:c1=tri:c2=tri{out_a}"
                )
                current_a = out_a

            filter_complex = ";".join(settb_parts + v_parts + a_parts)
            cmd = [
                "ffmpeg",
                *self._GLOBAL_OPTS,
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                *self._VIDEO_OPTS,
                *self._AUDIO_OPTS,
                *self._CONTAINER_OPTS,
                str(output),
            ]
        else:
            # Video only
            filter_complex = ";".join(settb_parts + v_parts)
            cmd = [
                "ffmpeg",
                *self._GLOBAL_OPTS,
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                *self._VIDEO_OPTS,
                "-an",
                *self._CONTAINER_OPTS,
                str(output),
            ]

        try:
            self._run_ffmpeg(cmd, desc="xfade-transition")
        except subprocess.CalledProcessError:
            # Fallback: video-only if audio filter fails
            print("  [FFmpeg] Audio crossfade failed, falling back to video-only", file=sys.stderr)
            filter_complex = ";".join(settb_parts + v_parts)
            cmd_fallback = [
                "ffmpeg",
                *self._GLOBAL_OPTS,
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                *self._VIDEO_OPTS,
                "-an",
                *self._CONTAINER_OPTS,
                str(output),
            ]
            self._run_ffmpeg(cmd_fallback, desc="xfade-fallback")

        return output

    def add_audio(
        self,
        video: Path,
        audio: Path,
        output: Path,
    ) -> Path:
        """Add audio track to video."""
        output.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            *self._GLOBAL_OPTS,
            "-i", str(video),
            "-i", str(audio),
            "-c:v", "copy",
            *self._AUDIO_OPTS,
            "-shortest",
            *self._CONTAINER_OPTS,
            str(output),
        ]
        self._run_ffmpeg(cmd, desc="add-audio")
        return output

    def add_text_overlay(
        self,
        video: Path,
        text: str,
        output: Path,
        position: str = "bottom",
        font_size: int = 36,
        font_color: str = "white",
        font_file: str = None,
        start: float = 0.0,
        duration: float = 3.0,
        fade_duration: float = 0.5,
        shadow: bool = True,
        outline: bool = True,
        background_box: bool = False,
    ) -> Path:
        """Add text overlay to video with CJK support and styling.

        Args:
            video: Input video path
            text: Text to display
            output: Output video path
            position: "top", "center", or "bottom"
            font_size: Font size in pixels
            font_color: Font color (FFmpeg color name or hex)
            font_file: Path to font file. If None, auto-detects CJK font on macOS.
            start: Start time in seconds
            duration: Display duration in seconds
            fade_duration: Fade in/out duration in seconds
            shadow: Add drop shadow for readability
            outline: Add text outline/border
            background_box: Add semi-transparent background box behind text
        """
        output.parent.mkdir(parents=True, exist_ok=True)

        y_pos = {"top": "50", "center": "(h-text_h)/2", "bottom": "h-text_h-50"}
        y = y_pos.get(position, "h-text_h-50")

        # Auto-detect CJK font if not specified
        if font_file is None:
            font_file = self._find_cjk_font()

        # Escape text for FFmpeg drawtext
        escaped_text = text.replace("'", "'\\''").replace(":", "\\:")

        # Build drawtext filter parts
        parts = [
            f"drawtext=text='{escaped_text}'",
            f"fontsize={font_size}",
            f"fontcolor={font_color}",
            f"x=(w-text_w)/2",
            f"y={y}",
        ]

        if font_file:
            parts.append(f"fontfile='{font_file}'")

        if shadow:
            parts.append("shadowcolor=black@0.6:shadowx=2:shadowy=2")

        if outline:
            parts.append("borderw=2:bordercolor=black@0.5")

        if background_box:
            parts.append("box=1:boxcolor=black@0.4:boxborderw=8")

        # Fade in/out using alpha expression
        end_time = start + duration
        fade_in_end = start + fade_duration
        fade_out_start = end_time - fade_duration

        alpha_expr = (
            f"if(lt(t\\,{start})\\,0\\,"
            f"if(lt(t\\,{fade_in_end})\\,(t-{start})/{fade_duration}\\,"
            f"if(lt(t\\,{fade_out_start})\\,1\\,"
            f"if(lt(t\\,{end_time})\\,({end_time}-t)/{fade_duration}\\,0))))"
        )
        parts.append(f"alpha='{alpha_expr}'")

        drawtext = ":".join(parts)

        cmd = [
            "ffmpeg",
            *self._GLOBAL_OPTS,
            "-i", str(video),
            "-vf", drawtext,
            "-c:a", "copy",
            *self._VIDEO_OPTS,
            *self._CONTAINER_OPTS,
            str(output),
        ]
        self._run_ffmpeg(cmd, desc="text-overlay")
        return output

    def image_to_still_video(
        self,
        image: Path,
        output: Path,
        duration: float = 3.0,
        motion: str = "zoom_in",
    ) -> Path:
        """Create a video from a single image with optional Ken Burns motion.

        Args:
            image: Source image path
            output: Output video path
            duration: Duration in seconds
            motion: Motion type — "none", "zoom_in", "zoom_out", "pan_left", "pan_right"
        """
        output.parent.mkdir(parents=True, exist_ok=True)
        fps = 30
        total_frames = int(duration * fps)

        if motion == "none":
            cmd = [
                "ffmpeg",
                *self._GLOBAL_OPTS,
                "-loop", "1",
                "-i", str(image),
                "-t", str(duration),
                *self._VIDEO_OPTS,
                "-an",
                *self._CONTAINER_OPTS,
                str(output),
            ]
        else:
            # Ken Burns with zoompan filter
            # Probe image dimensions to determine output size
            out_w, out_h = self._get_image_dimensions(image)
            filter_str = self._build_ken_burns_filter(motion, total_frames, fps, out_w, out_h)
            cmd = [
                "ffmpeg",
                *self._GLOBAL_OPTS,
                "-loop", "1",
                "-i", str(image),
                "-t", str(duration),
                "-vf", filter_str,
                *self._VIDEO_OPTS,
                "-an",
                *self._CONTAINER_OPTS,
                str(output),
            ]

        self._run_ffmpeg(cmd, desc="image-to-video")
        return output

    @staticmethod
    def _build_ken_burns_filter(
        motion: str, total_frames: int, fps: int, out_w: int, out_h: int
    ) -> str:
        """Build zoompan filter string for Ken Burns effect.

        Creates gentle, cinematic motion from a still image.
        """
        if motion == "zoom_in":
            # Gentle zoom in to center: 1.0 -> 1.12 over duration
            return (
                f"scale=8000:-1,"
                f"zoompan=z='min(zoom+0.0004*on,1.12)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={out_w}x{out_h}:fps={fps}"
            )
        elif motion == "zoom_out":
            # Gentle zoom out from center: 1.12 -> 1.0
            return (
                f"scale=8000:-1,"
                f"zoompan=z='if(eq(on,0),1.12,max(zoom-0.0004,1.0))':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={out_w}x{out_h}:fps={fps}"
            )
        elif motion == "pan_left":
            # Slow pan from right to left
            return (
                f"scale=8000:-1,"
                f"zoompan=z='1.12':"
                f"x='iw*0.12*(1-on/{total_frames})':y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={out_w}x{out_h}:fps={fps}"
            )
        elif motion == "pan_right":
            # Slow pan from left to right
            return (
                f"scale=8000:-1,"
                f"zoompan=z='1.12':"
                f"x='iw*0.12*on/{total_frames}':y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={out_w}x{out_h}:fps={fps}"
            )
        else:
            # Default: gentle zoom in
            return (
                f"scale=8000:-1,"
                f"zoompan=z='min(zoom+0.0004*on,1.12)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={out_w}x{out_h}:fps={fps}"
            )

    @staticmethod
    def _get_image_dimensions(image: Path) -> tuple[int, int]:
        """Get image dimensions using ffprobe. Returns (width, height)."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x",
            str(image),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            parts = result.stdout.strip().split("x")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        except Exception:
            pass
        # Fallback: assume 9:16 vertical video
        return 1080, 1920

    def concatenate_advanced(
        self,
        clips: list[Path],
        output: Path,
        transitions: list[str] = None,
        transition_durations: list[float] = None,
        trims: list[dict] = None,
    ) -> Path:
        """Advanced concatenation with per-cut-point transitions.

        Unlike concatenate() which applies one transition globally, this method
        uses a different transition type at each cut point.

        Args:
            clips: Video clip paths in order
            output: Output video path
            transitions: List of transition types, one per cut point (len = clips-1).
                        Values: "none", "fade", "dissolve", "wipeleft", etc.
                        If None, all cuts are hard cuts ("none").
            transition_durations: Duration per transition (len = clips-1).
                        Default 0.5s for each.
            trims: Optional per-clip trim dicts (same as concatenate).
        """
        if not clips:
            raise ValueError("No clips to concatenate")
        if len(clips) == 1:
            return self.concatenate(clips, output, trims=trims)

        output.parent.mkdir(parents=True, exist_ok=True)
        n_cuts = len(clips) - 1

        if transitions is None:
            transitions = ["none"] * n_cuts
        if transition_durations is None:
            transition_durations = [0.5] * n_cuts

        # Pad to correct length
        while len(transitions) < n_cuts:
            transitions.append("none")
        while len(transition_durations) < n_cuts:
            transition_durations.append(0.5)

        # Step 1: Apply trimming
        actual_clips = clips
        trimmed_files = []
        if trims:
            actual_clips = []
            for i, clip in enumerate(clips):
                trim = trims[i] if i < len(trims) else None
                if trim and (trim.get("start", 0) > 0 or trim.get("end") is not None):
                    trimmed = Path(tempfile.mktemp(suffix=".mp4"))
                    self.trim_clip(
                        clip, trimmed,
                        trim_start=trim.get("start", 0.0),
                        trim_end=trim.get("end"),
                    )
                    actual_clips.append(trimmed)
                    trimmed_files.append(trimmed)
                else:
                    actual_clips.append(clip)

        try:
            # Check if any cut point needs a real transition
            has_transitions = any(t != "none" for t in transitions)

            if not has_transitions:
                # All hard cuts — use simple concat
                return self._concat_simple(actual_clips, output)

            # Step 2: Build xfade filter chain with per-cut transitions
            # Group consecutive "none" cuts into segments, apply xfade only where needed
            return self._concat_mixed_transitions(
                actual_clips, output, transitions, transition_durations
            )
        finally:
            for f in trimmed_files:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

    def _concat_mixed_transitions(
        self,
        clips: list[Path],
        output: Path,
        transitions: list[str],
        durations: list[float],
    ) -> Path:
        """Build final video with per-cut-point transitions.

        Groups consecutive clips connected by hard cuts ("none") into segments,
        pre-concatenates each segment with the concat demuxer, then applies
        xfade transitions only between segments.  This avoids the ffmpeg bug
        where very short xfade durations (<1 frame) silently drop all
        subsequent frames.
        """
        # ── Step 1: group clips into segments separated by real transitions ──
        # segments[k] = list of clip indices that are hard-cut together
        # real_transitions[k] = (transition_type, duration) between segment k and k+1
        segments: list[list[int]] = [[0]]
        real_transitions: list[tuple[str, float]] = []

        for i in range(len(clips) - 1):
            if transitions[i] == "none":
                # Hard cut — extend current segment
                segments[-1].append(i + 1)
            else:
                # Real transition — start a new segment
                real_transitions.append((transitions[i], durations[i]))
                segments.append([i + 1])

        # ── Step 2: pre-concatenate each segment ──
        segment_files: list[Path] = []
        temp_segment_files: list[Path] = []

        for seg in segments:
            if len(seg) == 1:
                # Single clip — use directly
                segment_files.append(clips[seg[0]])
            else:
                # Multiple clips — concat with demuxer
                seg_clips = [clips[idx] for idx in seg]
                seg_output = Path(tempfile.mktemp(suffix=".mp4"))
                self._concat_simple(seg_clips, seg_output)
                segment_files.append(seg_output)
                temp_segment_files.append(seg_output)

        try:
            if len(segment_files) == 1:
                # No real transitions — just copy the single segment
                import shutil
                shutil.copy2(str(segment_files[0]), str(output))
                return output

            # ── Step 3: apply xfade between segments ──
            return self._concat_with_transition_list(
                segment_files, output, real_transitions
            )
        finally:
            for f in temp_segment_files:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

    def _concat_with_transition_list(
        self,
        clips: list[Path],
        output: Path,
        transitions: list[tuple[str, float]],
    ) -> Path:
        """Concatenate clips with a specific transition at each cut point.

        Args:
            clips: Video clips (one per segment).
            transitions: List of (transition_type, duration) tuples, len = clips-1.
        """
        inputs = []
        for clip in clips:
            inputs.extend(["-i", str(clip)])

        clip_durations = [self._get_duration(c) for c in clips]

        # Normalize timebases to avoid xfade mismatch errors
        # (e.g. 1/15360 vs 1/12288 from different source encoders)
        settb_parts = []
        for i in range(len(clips)):
            settb_parts.append(f"[{i}:v]settb=AVTB,fps={self._fps}[norm{i}]")

        # Build video xfade chain using normalized streams
        v_parts = []
        current_v = "[norm0]"
        running_duration = clip_durations[0]

        for i in range(len(clips) - 1):
            next_v = f"[norm{i + 1}]"
            is_last = (i == len(clips) - 2)
            out_v = "[outv]" if is_last else f"[v{i + 1}]"

            trans, t_dur = transitions[i]
            offset = max(0, running_duration - t_dur)
            running_duration = running_duration + clip_durations[i + 1] - t_dur

            v_parts.append(
                f"{current_v}{next_v}xfade=transition={trans}:"
                f"duration={t_dur}:offset={offset:.3f}{out_v}"
            )
            current_v = out_v

        has_audio = any(self._has_audio_stream(c) for c in clips)
        filter_complex = ";".join(settb_parts + v_parts)

        if has_audio:
            a_parts = []
            current_a = "[0:a]"
            for i in range(len(clips) - 1):
                next_a = f"[{i + 1}:a]"
                is_last = (i == len(clips) - 2)
                out_a = "[outa]" if is_last else f"[a{i + 1}]"
                _, t_dur = transitions[i]
                a_parts.append(
                    f"{current_a}{next_a}acrossfade=d={t_dur}:c1=tri:c2=tri{out_a}"
                )
                current_a = out_a

            filter_complex = ";".join(settb_parts + v_parts + a_parts)
            cmd = [
                "ffmpeg",
                *self._GLOBAL_OPTS,
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                *self._VIDEO_OPTS,
                *self._AUDIO_OPTS,
                *self._CONTAINER_OPTS,
                str(output),
            ]
        else:
            cmd = [
                "ffmpeg",
                *self._GLOBAL_OPTS,
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                *self._VIDEO_OPTS,
                "-an",
                *self._CONTAINER_OPTS,
                str(output),
            ]

        try:
            self._run_ffmpeg(cmd, desc="segment-xfade")
        except subprocess.CalledProcessError:
            print("  [FFmpeg] Segment xfade failed, falling back to simple concat",
                  file=sys.stderr)
            return self._concat_simple(clips, output)

        return output

    @staticmethod
    def _find_cjk_font() -> str | None:
        """Find a CJK-capable font on the system (macOS-focused)."""
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            # Linux fallbacks
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        for path in candidates:
            if Path(path).exists():
                return path
        return None

    @staticmethod
    def _get_duration(video: Path) -> float:
        """Get video duration in seconds using ffprobe.

        Uses the VIDEO STREAM duration (not container/format duration) to avoid
        mismatches when audio is longer than video (e.g. after mixed-fps concat).
        Falls back to format duration, then to 5.0s default.
        """
        # First try: video stream duration (most accurate for xfade offset calculation)
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=duration,nb_frames,r_frame_rate",
                "-of", "csv=p=0",
                str(video),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            parts = result.stdout.strip().split(",")
            # parts: r_frame_rate, duration, nb_frames (order varies, parse by type)
            stream_dur = None
            nb_frames = None
            fps_num, fps_den = None, None

            for part in parts:
                part = part.strip()
                if "/" in part:
                    nums = part.split("/")
                    if len(nums) == 2 and all(n.isdigit() for n in nums) and int(nums[1]) > 0:
                        fps_num, fps_den = int(nums[0]), int(nums[1])
                elif "." in part:
                    try:
                        stream_dur = float(part)
                    except ValueError:
                        pass
                elif part.isdigit():
                    nb_frames = int(part)

            # Prefer nb_frames / fps (exact frame count → exact duration)
            if nb_frames and fps_num and fps_den and fps_den > 0:
                fps = fps_num / fps_den
                if fps > 0:
                    return nb_frames / fps

            # Fallback: stream duration
            if stream_dur and stream_dur > 0:
                return stream_dur
        except Exception:
            pass

        # Last resort: format/container duration
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(video),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception:
            return 5.0  # Default fallback

    @staticmethod
    def _has_audio_stream(video: Path) -> bool:
        """Check if video file has an audio stream."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(video),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return bool(result.stdout.strip())
        except Exception:
            return False

    @staticmethod
    def check_installed() -> bool:
        """Check if FFmpeg is available."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                check=True,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
