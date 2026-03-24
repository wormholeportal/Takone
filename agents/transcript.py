"""
Takone — Project-level conversation logger.

Records the COMPLETE conversation trace for each project session:
- User input (text, file paths)
- Assistant output (text, thinking/reasoning)
- Tool calls (name, arguments, results)
- Timestamps and metadata

Logs are stored per-project in: <project_dir>/logs/session_<timestamp>.jsonl
Each line is a JSON object with a "type" field.

Usage:
    plog = ProjectLogger(project_dir)
    plog.log_user(content)
    plog.log_assistant_text(text)
    plog.log_thinking(text)
    plog.log_tool_call(name, args)
    plog.log_tool_result(name, result)
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path


class ProjectLogger:
    """Append-only JSONL logger for project conversations."""

    def __init__(self, project_dir: Path, model: str = ""):
        self._dir = project_dir / "logs"
        self._dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = self._dir / f"session_{ts}.jsonl"
        self._model = model
        self._f = open(self._path, "a", encoding="utf-8", buffering=1)  # line-buffered

        # Write session header
        self._write({
            "type": "session_start",
            "model": model,
            "project": str(project_dir.name),
        })

        # Accumulators for streaming
        self._text_acc: list[str] = []
        self._thinking_acc: list[str] = []

    # ── Public API ──────────────────────────────────────────────

    def log_user(self, content: str | list) -> None:
        """Log user input."""
        if isinstance(content, list):
            # Multimodal content — extract text parts, note file refs
            text_parts = []
            file_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") in ("image", "image_url"):
                        file_parts.append("[image]")
                    else:
                        file_parts.append(f"[{item.get('type', '?')}]")
                elif isinstance(item, str):
                    text_parts.append(item)
            self._write({
                "type": "user",
                "text": "\n".join(text_parts),
                "attachments": file_parts if file_parts else None,
            })
        else:
            self._write({"type": "user", "text": str(content)})

    def log_assistant_chunk(self, chunk: str) -> None:
        """Accumulate streaming text chunks (flushed on log_assistant_end)."""
        self._text_acc.append(chunk)

    def log_thinking_chunk(self, chunk: str) -> None:
        """Accumulate streaming thinking chunks (flushed on log_assistant_end)."""
        self._thinking_acc.append(chunk)

    def log_assistant_end(self) -> None:
        """Flush accumulated assistant text + thinking to log."""
        text = "".join(self._text_acc)
        thinking = "".join(self._thinking_acc)
        entry: dict = {"type": "assistant"}
        if thinking:
            entry["thinking"] = thinking
        if text:
            entry["text"] = text
        if text or thinking:
            self._write(entry)
        self._text_acc.clear()
        self._thinking_acc.clear()

    def log_tool_call(self, name: str, args: dict) -> None:
        """Log a tool call with its arguments."""
        # Truncate very large args (e.g. base64 image data)
        args_str = json.dumps(args, ensure_ascii=False, default=str)
        if len(args_str) > 5000:
            args_str = args_str[:5000] + "...(truncated)"
        self._write({
            "type": "tool_call",
            "tool": name,
            "args": args_str,
        })

    def log_tool_result(self, name: str, result: str) -> None:
        """Log a tool result."""
        result_str = str(result) if result else ""
        if len(result_str) > 10000:
            result_str = result_str[:10000] + "...(truncated)"
        self._write({
            "type": "tool_result",
            "tool": name,
            "result": result_str,
        })

    def log_error(self, error: str) -> None:
        """Log an error."""
        self._write({"type": "error", "error": str(error)})

    def log_command(self, command: str) -> None:
        """Log a user slash command."""
        self._write({"type": "command", "command": command})

    def close(self) -> None:
        """Close the log file."""
        self._write({"type": "session_end"})
        self._f.close()

    # ── Internal ────────────────────────────────────────────────

    def _write(self, entry: dict) -> None:
        entry["ts"] = time.time()
        entry["dt"] = datetime.now().strftime("%H:%M:%S")
        try:
            self._f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass  # Never crash the main program for logging

    @property
    def path(self) -> Path:
        return self._path
