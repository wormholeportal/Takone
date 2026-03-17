"""
Takone — Terminal UI module.

All terminal display helpers, split-terminal management, spinner,
input watcher, and streaming printer live here.
"""
from __future__ import annotations

import sys
import os
import re
import threading
import itertools
import time
import select
import shutil
import termios
import tty
from typing import Any

from .config import Colors

__all__ = [
    "_term_width",
    "_visual_len",
    "_visual_pad",
    "_term_height",
    "_bottom_lock",
    "_query_cursor_pos",
    "_cbreak_read_key",
    "_TrackedStdout",
    "SplitTerminal",
    "_split_terminal",
    "Spinner",
    "InputWatcher",
    "_print_divider",
    "_strip_thinking",
    "_print_thinking",
    "_AGENT_ROLES",
    "_TOOL_ROLES",
    "_DEFAULT_ROLE",
    "_print_director_response",
    "_TOOL_LABELS",
    "_tool_label",
    "_print_tool_call",
    "_print_tool_done",
    "_StreamPrinter",
]


# ── Display helpers ───────────────────────────────────────────────────

def _term_width() -> int:
    """Get terminal width, default 80."""
    return shutil.get_terminal_size((80, 24)).columns


def _visual_len(s: str) -> int:
    """Visual width of string, accounting for ANSI codes and wide chars."""
    clean = re.sub(r'\033\[[^m]*m', '', s)
    w = 0
    for ch in clean:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0xF900 <= cp <= 0xFAFF or 0xFF01 <= cp <= 0xFF60 or
            0x3000 <= cp <= 0x303F):
            w += 2
        else:
            w += 1
    return w


def _visual_pad(s: str, width: int) -> str:
    """Pad string to visual width, accounting for ANSI codes and wide chars."""
    return s + ' ' * max(0, width - _visual_len(s))


def _term_height() -> int:
    """Get terminal height, default 24."""
    return shutil.get_terminal_size((80, 24)).lines


# Lock serialises all writes to the bottom fixed area (status bar + input line).
# Each write is a single sys.stdout.write() containing a complete
# save-cursor / move / clear / draw / restore-cursor escape sequence,
# so the terminal always sees an atomic update.
_bottom_lock = threading.Lock()


def _query_cursor_pos() -> tuple[int, int]:
    """Query terminal cursor position via DSR (\\033[6n]).  Returns (row, col)."""
    fd = sys.stdin.fileno()
    try:
        old_settings = termios.tcgetattr(fd)
    except termios.error:
        return _term_height() - 2, 1  # safe fallback
    try:
        tty.setcbreak(fd)
        # Drain any already-buffered input so it doesn't pollute the response
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if not r:
                break
            os.read(fd, 1024)
        # Try up to 2 times for reliability
        for _attempt in range(2):
            sys.stdout.write("\033[6n")
            sys.stdout.flush()
            resp = b""
            deadline = time.time() + 0.3
            while time.time() < deadline:
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    ch = os.read(fd, 1)
                    resp += ch
                    if ch == b"R":
                        break
            text = resp.decode("ascii", errors="ignore")
            m = re.search(r"\[(\d+);(\d+)R", text)
            if m:
                return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return _term_height() - 2, 1  # safe fallback within scroll region


def _cbreak_read_key(fd) -> tuple[str, Any] | None:
    """Read one keypress from a cbreak-mode fd.

    Reads byte-by-byte so that control characters (backspace, enter, etc.)
    are never accidentally merged with multi-byte UTF-8 character data.

    Returns:
        ("char", str)   — a printable character (possibly multi-byte UTF-8)
        ("ctrl", int)   — a control byte  (0x03=Ctrl-C, 0x0a=Enter, 0x7f=BS…)
        ("esc",  bytes) — an escape sequence
        None            — nothing available or invalid byte
    """
    b0 = os.read(fd, 1)
    if not b0:
        return None
    byte = b0[0]

    # Escape sequence (arrow keys, function keys, …)
    if byte == 0x1b:
        seq = b0
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 0.02)
            if not r:
                break
            more = os.read(fd, 1)
            seq += more
            # CSI sequences end with a byte in 0x40-0x7E
            if len(seq) > 1 and more[0] in range(0x40, 0x7F):
                break
        return ("esc", seq)

    # Control characters (< 0x20 or DEL 0x7f)
    if byte < 0x20 or byte == 0x7f:
        return ("ctrl", byte)

    # ASCII printable (0x20 – 0x7E)
    if byte < 0x80:
        return ("char", chr(byte))

    # Multi-byte UTF-8
    if byte < 0xC0:
        return None  # stray continuation byte
    elif byte < 0xE0:
        need = 1
    elif byte < 0xF0:
        need = 2
    else:
        need = 3
    rest = b""
    while len(rest) < need:
        chunk = os.read(fd, need - len(rest))
        if not chunk:
            return None
        rest += chunk
    try:
        return ("char", (b0 + rest).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


class _TrackedStdout:
    """Wraps real stdout.  Erases inline bottom decoration before content output.

    When the SplitTerminal bottom bar is visible, any normal print() output
    first erases it, writes the content, updates the tracked cursor row, and
    leaves the bottom un-drawn so that it can be redrawn at the new position
    later (by read_input or the spinner).
    """

    def __init__(self, real, split_terminal):
        self._real = real
        self._st = split_terminal

    def write(self, text):
        st = self._st
        if st._active and text:
            with _bottom_lock:
                if st._bottom_drawn:
                    st._erase_bottom()
                result = self._real.write(text)
                self._real.flush()
                newlines = text.count('\n')
                if newlines:
                    rows = _term_height()
                    st._out_row = min(st._out_row + newlines, rows)
                # Do NOT redraw bottom here — streaming tokens without newlines
                # would get overwritten. Bottom is redrawn by spinner/read_input.
            return result
        result = self._real.write(text)
        self._real.flush()
        return result

    def flush(self):
        return self._real.flush()

    def fileno(self):
        return self._real.fileno()

    def isatty(self):
        return self._real.isatty()

    @property
    def encoding(self):
        return self._real.encoding

    @property
    def errors(self):
        return self._real.errors

    @property
    def buffer(self):
        return self._real.buffer

    def __getattr__(self, name):
        return getattr(self._real, name)


class SplitTerminal:
    """Inline bottom decoration that follows content.

    NO scroll regions.  The 4-line decoration (status / footer / border /
    input) is drawn right below the last line of content and moves down as
    new content is printed.  When content fills the screen the terminal's
    natural scroll takes over.

    Row layout (relative to content):
        _out_row + 0    status bar     (⠋ Thinking • 3s)
        _out_row + 1    footer info    (Director | minimax/MiniMax-M2.5)
        _out_row + 2    editor border  (─────────────)
        _out_row + 3    input line     (cursor only, no prompt)
    """

    FIXED_ROWS = 4  # status / footer / border / input

    # Reverse-video space looks like the native block cursor
    CURSOR_CHAR = "\033[7m \033[27m"

    # Default input prompt
    DEFAULT_PROMPT = f"  {Colors.DIM}>{Colors.ENDC} "

    # UI colors
    BORDER_COLOR = "\033[38;5;240m"   # dark gray for ─ borders
    STATUS_COLOR = "\033[38;5;214m"   # gold/orange for status text
    FOOTER_COLOR = "\033[38;5;245m"   # dim gray for footer info

    def __init__(self):
        self._active = False
        self._out_row = 1        # row where next content line goes (= first bottom row)
        self._bottom_drawn = False
        self._real_stdout = None  # original sys.stdout (before wrapping)
        self._footer_text = ""   # cached footer content
        self._status_text = ""   # cached status content
        self._input_text = ""    # cached input buffer
        self._input_prompt = "  "

    # ── lifecycle ────────────────────────────────────────────

    def enter(self, footer_text: str = ""):
        """Activate inline-decoration mode."""
        if self._active:
            return
        self._footer_text = footer_text
        cur_row, _ = _query_cursor_pos()
        self._out_row = cur_row
        self._active = True
        self._real_stdout = sys.stdout
        sys.stdout = _TrackedStdout(self._real_stdout, self)
        self._draw_bottom()

    def exit(self):
        """Restore normal terminal."""
        if not self._active:
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()
            return
        self._active = False
        with _bottom_lock:
            if self._bottom_drawn:
                self._erase_bottom()
        if self._real_stdout:
            sys.stdout = self._real_stdout
            self._real_stdout = None
        sys.stdout.write("\033[?25h\n")
        sys.stdout.flush()

    # ── raw I/O (bypasses TrackedStdout) ─────────────────────

    def _raw_write(self, data: str):
        """Write directly to the real stdout, bypassing TrackedStdout."""
        out = self._real_stdout or sys.stdout
        out.write(data)
        out.flush()

    # ── inline bottom decoration ─────────────────────────────

    def _draw_bottom(self):
        """Draw 4 decoration lines starting at _out_row.  Must hold _bottom_lock or be init."""
        if self._bottom_drawn:
            return
        rows = _term_height()
        cols = _term_width()
        border_w = cols - 4
        s = self._out_row
        end = s + self.FIXED_ROWS - 1
        # Scroll terminal up if bottom would go off-screen
        if end > rows:
            scroll_by = end - rows
            self._raw_write(f"\033[{rows};1H" + "\n" * scroll_by)
            self._out_row -= scroll_by
            s = self._out_row
        self._raw_write(
            f"\033[?25l"
            f"\033[{s};1H\033[K  {self._status_text}"
            f"\033[{s+1};1H\033[K  {self.FOOTER_COLOR}{self._footer_text}\033[0m"
            f"\033[{s+2};1H\033[K  {self.BORDER_COLOR}{'─' * border_w}\033[0m"
            f"\033[{s+3};1H\033[K{self._input_prompt}{self._input_text}{self.CURSOR_CHAR}"
        )
        self._bottom_drawn = True

    def _erase_bottom(self):
        """Erase 4 decoration lines, cursor back to _out_row.  Must hold _bottom_lock."""
        if not self._bottom_drawn:
            return
        s = self._out_row
        self._raw_write(
            f"\033[{s};1H\033[K"
            f"\033[{s+1};1H\033[K"
            f"\033[{s+2};1H\033[K"
            f"\033[{s+3};1H\033[K"
            f"\033[{s};1H"
        )
        self._bottom_drawn = False

    # ── thread-safe bottom-area updates ─────────────────────

    def update_status(self, text: str):
        """Update status bar.  Draws bottom if not visible.  Thread-safe."""
        if not self._active:
            return
        self._status_text = text
        with _bottom_lock:
            if not self._bottom_drawn:
                self._draw_bottom()
            else:
                s = self._out_row
                self._raw_write(
                    f"\033[{s};1H\033[K  {text}"
                    f"\033[{s+3};1H"
                )

    def clear_status(self):
        """Clear status bar text.  Thread-safe."""
        if not self._active:
            return
        self._status_text = ""
        with _bottom_lock:
            if self._bottom_drawn:
                s = self._out_row
                self._raw_write(
                    f"\033[{s};1H\033[K"
                    f"\033[{s+3};1H"
                )

    def update_footer(self, text: str):
        """Update footer info line.  Thread-safe."""
        if not self._active:
            return
        self._footer_text = text
        with _bottom_lock:
            if self._bottom_drawn:
                s = self._out_row
                self._raw_write(
                    f"\033[{s+1};1H\033[K  {self.FOOTER_COLOR}{text}\033[0m"
                    f"\033[{s+3};1H"
                )

    def update_input(self, text: str, prompt: str = None):
        """Update input line display.  Thread-safe."""
        if not self._active:
            return
        if prompt is None:
            prompt = self.DEFAULT_PROMPT
        self._input_text = text
        self._input_prompt = prompt
        with _bottom_lock:
            if self._bottom_drawn:
                s = self._out_row
                self._raw_write(
                    f"\033[{s+3};1H\033[K"
                    f"{prompt}{text}{self.CURSOR_CHAR}"
                )

    def read_input(self, prompt: str = None) -> str:
        """Read a line of input in cbreak mode, rendering on the input line.

        Draws the bottom decoration if not visible, reads keystrokes,
        then erases the decoration on Enter so content can follow.
        """
        if not self._active:
            return input().strip()
        if prompt is None:
            prompt = self.DEFAULT_PROMPT
        self._input_text = ""
        self._input_prompt = prompt
        # Ensure bottom is drawn
        with _bottom_lock:
            if not self._bottom_drawn:
                self._draw_bottom()
        fd = sys.stdin.fileno()
        try:
            old_settings = termios.tcgetattr(fd)
        except termios.error:
            return input().strip()
        buf = ""
        self.update_input("", prompt)
        try:
            tty.setcbreak(fd)
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not ready:
                    continue
                key = _cbreak_read_key(fd)
                if key is None:
                    continue
                kind, value = key
                if kind == "esc":
                    continue
                if kind == "ctrl":
                    if value == 0x03:  # Ctrl+C
                        self._input_text = ""
                        self._input_prompt = self.DEFAULT_PROMPT
                        raise KeyboardInterrupt
                    if value == 0x04:  # Ctrl+D
                        self._input_text = ""
                        self._input_prompt = self.DEFAULT_PROMPT
                        raise EOFError
                    if value in (0x0A, 0x0D):  # Enter
                        # Reset cached state so next _draw_bottom shows clean input
                        self._input_text = ""
                        self._input_prompt = self.DEFAULT_PROMPT
                        with _bottom_lock:
                            self._erase_bottom()
                        return buf.strip()
                    if value in (0x7F, 0x08):  # Backspace
                        if buf:
                            buf = buf[:-1]
                            self.update_input(buf, prompt)
                    continue
                if kind == "char":
                    buf += value
                    self.update_input(buf, prompt)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# Singleton
_split_terminal = SplitTerminal()


class Spinner:
    """Animated thinking spinner with elapsed time.

    In split-terminal mode the animation runs in the status bar (row N-3).
    Format: ⠋ Thinking • 3s
    """

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, msg: str = "Thinking"):
        self.msg = msg
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_time: float = 0

    def start(self):
        self._stop.clear()
        self._start_time = time.monotonic()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _elapsed_str(self) -> str:
        elapsed = int(time.monotonic() - self._start_time)
        if elapsed < 60:
            return f"{elapsed}s"
        return f"{elapsed // 60}m{elapsed % 60:02d}s"

    def _spin(self):
        if _split_terminal._active:
            self._spin_status_bar()
        else:
            self._spin_inline()

    def _spin_inline(self):
        for frame in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            elapsed = self._elapsed_str()
            print(
                f"\r{Colors.DIM}  {frame} {self.msg} • {elapsed}{Colors.ENDC}",
                end="", flush=True,
            )
            time.sleep(0.08)
        print(f"\r{' ' * (_term_width() - 1)}\r", end="", flush=True)

    def _spin_status_bar(self):
        for frame in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            elapsed = self._elapsed_str()
            _split_terminal.update_status(
                f"{SplitTerminal.STATUS_COLOR}{frame} {Colors.BOLD}{self.msg}\033[22m • {elapsed}\033[0m"
            )
            time.sleep(0.08)
        _split_terminal.clear_status()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


class InputWatcher:
    """Watch stdin in cbreak mode during model execution.

    Reads character-by-character without terminal echo.
    Typed characters are shown in the SplitTerminal input line in real-time.
    Pressing Enter or Ctrl+C triggers the interrupt event immediately.
    """

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._interrupt_event = threading.Event()
        self._captured: str | None = None
        self._old_settings = None

    def start(self):
        self._stop_event.clear()
        self._interrupt_event.clear()
        self._captured = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        fd = sys.stdin.fileno()
        try:
            self._old_settings = termios.tcgetattr(fd)
        except termios.error:
            self._run_fallback()
            return
        buf = ""
        # Clear any stale input text from previous read_input
        _split_terminal.update_input("")
        try:
            tty.setcbreak(fd)
            while not self._stop_event.is_set():
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not ready:
                    continue
                key = _cbreak_read_key(fd)
                if key is None:
                    continue
                kind, value = key
                if kind == "esc":
                    continue
                if kind == "ctrl":
                    if value == 0x03:  # Ctrl+C
                        self._captured = "/int"
                        self._interrupt_event.set()
                        self._drain_stdin(fd)
                        break
                    if value in (0x0A, 0x0D):  # Enter
                        self._captured = buf.strip()
                        self._interrupt_event.set()
                        self._drain_stdin(fd)
                        break
                    if value in (0x7F, 0x08):  # Backspace
                        if buf:
                            buf = buf[:-1]
                            _split_terminal.update_input(buf)
                    continue
                if kind == "char":
                    buf += value
                    _split_terminal.update_input(buf)
        except Exception:
            pass
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, self._old_settings)
            except Exception:
                pass

    def _run_fallback(self):
        """Fallback for non-terminal stdin."""
        try:
            while not self._stop_event.is_set():
                ready, _, _ = select.select([sys.stdin], [], [], 0.2)
                if ready:
                    line = sys.stdin.readline()
                    self._captured = line.strip() if line else ""
                    self._interrupt_event.set()
                    break
        except Exception:
            pass

    @staticmethod
    def _drain_stdin(fd):
        """Consume remaining buffered input."""
        try:
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                if not ready:
                    break
                os.read(fd, 1024)
        except Exception:
            pass

    @property
    def interrupted(self) -> bool:
        return self._interrupt_event.is_set()

    def stop(self) -> str | None:
        """Stop watching and return captured input (None = nothing typed)."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._old_settings:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_settings)
            except Exception:
                pass
        result = self._captured
        self._captured = None
        self._interrupt_event.clear()
        return result


# ── Print helpers ─────────────────────────────────────────────────────

def _print_divider(char: str = "─", style: str = Colors.DIM):
    """Print a thin divider line."""
    w = min(_term_width() - 4, 72)
    print(f"  {style}{char * w}{Colors.ENDC}")


def _strip_thinking(text: str) -> tuple[str, str]:
    """Extract <think> blocks from model output.

    Returns (visible_text, thinking_text).
    Handles MiniMax/DeepSeek style <think>...</think> tags.
    """
    thinking_parts = []
    visible_parts = []

    # Match <think>...</think> blocks (greedy within, handles multiline)
    pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
    last_end = 0
    for m in pattern.finditer(text):
        visible_parts.append(text[last_end:m.start()])
        thinking_parts.append(m.group(1).strip())
        last_end = m.end()
    visible_parts.append(text[last_end:])

    visible = "".join(visible_parts).strip()
    thinking = "\n".join(thinking_parts).strip()
    return visible, thinking


def _print_thinking(thinking: str):
    """Print thinking block with distinct styling."""
    if not thinking.strip():
        return
    # Truncate very long thinking to keep output clean
    lines = thinking.split("\n")
    max_lines = 8
    print(f"\n  {Colors.DIM}{Colors.ITALIC}💭 Thinking...{Colors.ENDC}")
    for i, line in enumerate(lines[:max_lines]):
        print(f"  {Colors.DIM}{Colors.ITALIC}│ {line}{Colors.ENDC}")
    if len(lines) > max_lines:
        print(f"  {Colors.DIM}{Colors.ITALIC}│ ... ({len(lines) - max_lines} more lines){Colors.ENDC}")
    print(f"  {Colors.DIM}{Colors.ITALIC}╰─{Colors.ENDC}")


# ── Agent role identity ──────────────────────────────────────────────
# Maps skill names and tool names to display roles.
# Each role = (emoji, role_name, color_code)

_AGENT_ROLES = {
    "scriptwriter":      ("✍️",  "Scriptwriter",     Colors.GREEN),
    "storyboard":        ("🎬", "Storyboard Artist",   Colors.CYAN),
    "visualizer":        ("🎨", "Visual Designer", Colors.MAGENTA),
    "designer":          ("🎨", "Art Director", Colors.MAGENTA),
    "reviewer":          ("🔍", "Reviewer",     Colors.YELLOW),
    "pipeline":          ("📋", "Producer",     Colors.ORANGE),
}

_TOOL_ROLES = {
    "assemble_video":     ("✂️",  "Editor",   Colors.CYAN),
    "add_audio_track":    ("🎵", "Sound Engineer",   Colors.GREEN),
    "generate_image":     ("🖼️", "Generating",   Colors.MAGENTA),
    "generate_video":     ("🎬", "Generating",   Colors.MAGENTA),
    "generate_reference": ("🎨", "Art Director", Colors.MAGENTA),
}

_DEFAULT_ROLE = ("🎬", "Director", Colors.LIGHT_BLUE)


def _print_director_response(text: str, role: tuple = None):
    """Print model response with agent role styling.

    Strips <think> blocks and displays them separately.
    Role is a tuple of (emoji, name, color_code).
    """
    if not text.strip():
        return

    if role is None:
        role = _DEFAULT_ROLE
    emoji, name, color = role

    # Separate thinking from visible content
    visible, thinking = _strip_thinking(text)

    # Print thinking (if any) with distinct style
    if thinking:
        _print_thinking(thinking)

    # Print visible response
    if not visible.strip():
        return
    print(f"\n  {Colors.BOLD}{color}{emoji} {name}{Colors.ENDC}")
    for line in visible.split("\n"):
        print(f"  {line}")


_TOOL_LABELS = {
    "save_file": "💾 Save File",
    "read_file": "📖 Read File",
    "load_skill": "📚 Load Skill",
    "generate_reference": "🎨 Generate Reference",
    "generate_image": "🖼️  Generate Image",
    "generate_video": "🎬 Generate Video",
    "analyze_media": "🔍 Analyze Media",
    "check_continuity": "🔗 Continuity Check",
    "validate_before_generate": "✅ Pre-generation Validation",
    "search_reference": "🔎 Search Reference",
    "list_assets": "📂 List Assets",
    "assemble_video": "🎞️  Assemble Video",
    "add_audio_track": "🎵 Add Audio",
}


def _tool_label(tool_name: str) -> str:
    return _TOOL_LABELS.get(tool_name, f"🔧 {tool_name}")


def _print_tool_call(tool_name: str):
    """Print a tool call indicator and show spinner in status bar."""
    label = _tool_label(tool_name)
    print(f"  {Colors.DIM}┌ {label}{Colors.ENDC}")


def _print_tool_done():
    """Print tool completion indicator and clear status bar."""
    print(f"  {Colors.DIM}└ Done{Colors.ENDC}")


class _StreamPrinter:
    """Streaming text printer with <think> tag handling.

    Feeds text chunks from LLM streaming and prints visible text immediately.
    Thinking content (<think>...</think> tags or Anthropic thinking blocks)
    is shown in dim/italic style with a distinct visual treatment.
    """

    _MAX_THINK_LINES = 12  # truncate thinking display after this many lines

    def __init__(self, role: tuple):
        self.role = role
        self.header_printed = False
        self._in_think = False
        self._pending = ""       # partial tag buffer
        self._full_text = []     # accumulate full text for message history
        self._need_indent = True # next visible char needs "  " indent
        # Thinking display state
        self._think_header_shown = False
        self._think_line_count = 0
        self._think_need_indent = True
        self._think_truncated = False

    def feed(self, chunk: str, thinking: bool = False):
        """Feed a streaming chunk.  Text is printed immediately.

        If thinking=True, the chunk is displayed as thinking regardless of tags
        (used for Anthropic extended thinking blocks).
        """
        self._full_text.append(chunk)
        if thinking:
            self._emit_thinking(chunk)
            return

        text = self._pending + chunk
        self._pending = ""
        visible_parts = []

        while text:
            if self._in_think:
                idx = text.find("</think>")
                if idx >= 0:
                    # Emit thinking content before closing tag
                    if idx > 0:
                        self._emit_thinking(text[:idx])
                    self._close_thinking()
                    self._in_think = False
                    text = text[idx + 8:]
                else:
                    # check partial closing tag at end
                    safe_end = len(text)
                    for i in range(min(8, len(text)), 0, -1):
                        if "</think>"[:i] == text[-i:]:
                            self._pending = text[-i:]
                            safe_end = len(text) - i
                            break
                    if safe_end > 0:
                        self._emit_thinking(text[:safe_end])
                    text = ""
            else:
                idx = text.find("<think>")
                if idx >= 0:
                    visible_parts.append(text[:idx])
                    self._in_think = True
                    text = text[idx + 7:]
                else:
                    # check partial opening tag at end
                    for i in range(min(7, len(text)), 0, -1):
                        if "<think>"[:i] == text[-i:]:
                            visible_parts.append(text[:-i])
                            self._pending = text[-i:]
                            text = ""
                            break
                    else:
                        visible_parts.append(text)
                        text = ""

        visible = "".join(visible_parts)
        if visible:
            self._emit(visible)

    def _emit(self, text: str):
        """Write visible text to stdout with role header and indentation."""
        buf = []
        if not self.header_printed:
            emoji, name, color = self.role
            buf.append(f"\n  {Colors.BOLD}{color}{emoji} {name}{Colors.ENDC}\n")
            self.header_printed = True
            self._need_indent = True

        for ch in text:
            if self._need_indent:
                buf.append("  ")
                self._need_indent = False
            if ch == "\n":
                buf.append("\n")
                self._need_indent = True
            else:
                buf.append(ch)
        sys.stdout.write("".join(buf))
        sys.stdout.flush()

    def _emit_thinking(self, text: str):
        """Write thinking text in dim/italic style with │ border."""
        if self._think_truncated:
            return  # already hit line limit
        buf = []
        if not self._think_header_shown:
            buf.append(f"\n  {Colors.DIM}{Colors.ITALIC}💭 Thinking...{Colors.ENDC}\n")
            self._think_header_shown = True
            self._think_need_indent = True
            self._think_line_count = 0

        DIM_PRE = f"{Colors.DIM}{Colors.ITALIC}"
        for ch in text:
            if self._think_line_count >= self._MAX_THINK_LINES:
                self._think_truncated = True
                break
            if self._think_need_indent:
                buf.append(f"  {DIM_PRE}│ ")
                self._think_need_indent = False
            if ch == "\n":
                buf.append(f"{Colors.ENDC}\n")
                self._think_need_indent = True
                self._think_line_count += 1
            else:
                buf.append(ch)

        if buf:
            sys.stdout.write("".join(buf))
            sys.stdout.flush()

    def _close_thinking(self):
        """Close the thinking block with a footer line."""
        if not self._think_header_shown:
            return
        buf = ""
        if not self._think_need_indent:
            buf += f"{Colors.ENDC}\n"  # close unclosed line
        if self._think_truncated:
            buf += f"  {Colors.DIM}{Colors.ITALIC}│ ...{Colors.ENDC}\n"
        buf += f"  {Colors.DIM}{Colors.ITALIC}╰─{Colors.ENDC}\n"
        sys.stdout.write(buf)
        sys.stdout.flush()
        # Reset for potential next thinking block
        self._think_header_shown = False
        self._think_line_count = 0
        self._think_need_indent = True
        self._think_truncated = False

    def finish(self) -> str:
        """Flush remaining buffer, redraw bottom decoration, return full text."""
        if self._in_think:
            self._close_thinking()
        if self._pending and not self._in_think:
            self._emit(self._pending)
        self._pending = ""
        if self.header_printed or self._think_header_shown:
            sys.stdout.write("\n")
            sys.stdout.flush()
        # Immediately redraw bottom so input line reappears after streaming
        with _bottom_lock:
            if _split_terminal._active and not _split_terminal._bottom_drawn:
                _split_terminal._draw_bottom()
        return "".join(self._full_text)
