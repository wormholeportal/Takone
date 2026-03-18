#!/usr/bin/env python3
"""
Takone — Model-driven conversational agent for AI video creation.

The model decides the workflow: script → storyboard → prompts → generation → review.
Skills are loaded on-demand via tool calls to minimize token usage.

Provider pattern:
  Anthropic protocol  →  Claude, MiniMax
  OpenAI protocol     →  OpenAI, Moonshot, Doubao, Qwen
"""
from __future__ import annotations

import sys
import os
import json
import re
import asyncio
import queue
import threading
import yaml
import time
from pathlib import Path
from typing import Any
from datetime import datetime

from .config import (
    Colors, SKILLS, PROJECTS_DIR,
    load_config, DirectorConfig,
)
from .tui import (
    _term_width, _term_height, _visual_len, _visual_pad,
    _bottom_lock, _split_terminal, SplitTerminal,
    Spinner, InputWatcher, _StreamPrinter,
    _print_divider, _strip_thinking, _print_thinking,
    _print_director_response, _print_tool_call, _print_tool_done,
    _tool_label,
    _AGENT_ROLES, _TOOL_ROLES, _DEFAULT_ROLE, _TOOL_LABELS,
)
from .tools import (
    IMAGE_EXTS, VIDEO_EXTS,
    _resolve_file_path, _parse_user_input, _process_reference_files,
    _build_multimodal_anthropic, _build_multimodal_openai,
    PROVIDER_REGISTRY, _resolve_llm_config,
    TOOLS_ANTHROPIC, _tools_to_openai, TOOLS_OPENAI,
    SYSTEM_PROMPT,
)
from .log import logger, setup_logging


def _load_env_file(path):
    """Load .env file into os.environ. No dependencies needed."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key:
                        os.environ[key] = value
    except Exception:
        pass


# ── Constants ────────────────────────────────────────────────────────

YAML_FOLD_THRESHOLD = 80        # fold long strings in YAML output
YAML_DUMP_WIDTH = 120           # line width for YAML dumps
FILE_CONTENT_MAX_CHARS = 8000   # truncate file content shown to LLM
MAX_LLM_TOKENS = 16000          # max_tokens for LLM requests
VISUAL_DESC_MIN_CHARS = 100     # minimum chars for visual_description validation
VISUAL_DESC_WARN_WORDS = 80     # word count threshold for warnings
VISUAL_DESC_WARN_CHARS = 400    # char count threshold for warnings


# ── Main Director Class ───────────────────────────────────────────────

class VideoDirector:
    """Model-driven video director with lazy skill loading.

    Supports two protocols:
      - Anthropic protocol: Claude, MiniMax
      - OpenAI protocol: OpenAI, Moonshot, Doubao, Qwen
    """

    def __init__(self, project_name: str = None):
        # Load .env: ~/.takone/.env first (user install dir), then repo-local as fallback
        home_env = Path.home() / ".takone" / ".env"
        local_env = Path(__file__).resolve().parent.parent / ".env"
        if home_env.exists():
            _load_env_file(home_env)
        elif local_env.exists():
            _load_env_file(local_env)

        setup_logging()
        self.config = load_config()

        # Resolve provider → protocol + client
        protocol, api_key, model, base_url = _resolve_llm_config(self.config)
        self.protocol = protocol
        self.model = model

        if protocol == "anthropic":
            try:
                from anthropic import Anthropic
            except ImportError:
                print(f"{Colors.RED}Missing anthropic library, please run: pip install anthropic{Colors.ENDC}")
                sys.exit(1)
            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self.client = Anthropic(**kwargs)
        else:
            try:
                from openai import OpenAI
            except ImportError:
                print(f"{Colors.RED}Missing openai library, please run: pip install openai{Colors.ENDC}")
                sys.exit(1)
            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self.client = OpenAI(**kwargs)

        self.messages: list[dict] = []
        self.project_name = project_name
        self.project_dir: Path | None = None
        self.saved_files: list[str] = []
        self.generated_assets: list[str] = []

        # State flags for quality gates
        self._review_passed = False   # Set True after validate_before_generate passes

        # Current agent role for display (changes when skills are loaded)
        self._current_role = _DEFAULT_ROLE  # (emoji, name, color)

        # Background input watcher for interrupt during model execution
        self._pending_input: str | None = None

        # Lazy-init providers
        self._image_gen = None
        self._video_gen = None

        provider_name = self.config.llm.provider
        print(f"{Colors.DIM}  LLM: {provider_name} / {model}{Colors.ENDC}")

    # ── Tool handlers ─────────────────────────────────────────────

    def handle_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call and return the result string."""
        # Tool-triggered role switch (e.g., assemble_video → editor)
        if tool_name in _TOOL_ROLES:
            self._current_role = _TOOL_ROLES[tool_name]

        handlers = {
            "save_file": self._tool_save_file,
            "read_file": self._tool_read_file,
            "load_skill": self._tool_load_skill,
            "generate_reference": self._tool_generate_reference,
            "generate_image": self._tool_generate_image,
            "generate_video": self._tool_generate_video,
            "analyze_media": self._tool_analyze_media,
            "check_continuity": self._tool_check_continuity,
            "validate_before_generate": self._tool_validate_before_generate,
            "search_reference": self._tool_search_reference,
            "list_assets": self._tool_list_assets,
            "assemble_video": self._tool_assemble_video,
            "add_audio_track": self._tool_add_audio_track,
        }
        handler = handlers.get(tool_name)
        if handler:
            return handler(tool_input)
        return f"Unknown tool: {tool_name}"

    # Reflection hints: after saving key files, remind the model to self-reflect and evaluate
    _REVIEW_HINTS = {
        "screenplay.yaml": (
            "\n\n🔍 MANDATORY REFLECTION: You just saved screenplay.yaml. You MUST now:\n"
            "1. Call read_file('screenplay.yaml') to re-read it\n"
            "2. Check: Does the opening 3 seconds have a strong hook?\n"
            "3. Check: Is the narrative structure compelling (not a boring chronological list)?\n"
            "4. Check: Are there any wasted scenes that don't advance the story?\n"
            "5. Check: Do all props/costumes/buildings match the era/setting?\n"
            "6. Check: Is the pacing varied (not monotonous)?\n"
            "7. Check: Is every visual_description written as DENSE NOVELISTIC PROSE (200-600 words)? NOT fragmented bullet points!\n"
            "8. Check: Can you 'SEE' the scene when you close your eyes? If vague, rewrite with concrete details.\n"
            "9. Check: Are colors specific (cobalt blue, amber gold) NOT generic (blue, warm)?\n"
            "10. Check: Do adjacent scenes' closing_state → opening_state connect naturally?\n"
            "11. Check: Is YAML using '>' (folded scalar) NOT '|' for visual_description?\n"
            "12. Find AT LEAST 2 improvements, modify, and save again.\n"
            "13. Only proceed to storyboard AFTER you have iterated and confirmed quality."
        ),
        "storyboard.yaml": (
            "\n\n🔍 MANDATORY REFLECTION: You just saved storyboard.yaml. You MUST now:\n"
            "1. Call read_file('storyboard.yaml') to re-read it\n"
            "2. Check: Does EVERY shot have opening_state and closing_state?\n"
            "3. Check: Do adjacent shots' closing→opening states connect smoothly?\n"
            "4. Check: Are all key_elements era-appropriate?\n"
            "5. Check: Is there rhythm variation (fast/slow pacing)?\n"
            "6. Find AT LEAST 2 improvements, modify, and save again.\n"
            "7. Only proceed to prompts AFTER you have iterated and confirmed quality."
        ),
        "prompts.json": (
            "\n\n🔍 MANDATORY REFLECTION: You just saved prompts.json. You MUST now:\n"
            "1. Call read_file('prompts.json') to re-read it\n"
            "2. Check: Is style_anchor detailed enough (50-100 words)?\n"
            "3. Check: Does every prompt include the full style_anchor?\n"
            "4. Check: Are character descriptions consistent across shots?\n"
            "5. Check: Do video_prompts include opening/closing state descriptions?\n"
            "6. Check: Does every shot specify reference_images?\n"
            "7. Find AT LEAST 2 improvements, modify, and save again.\n"
            "8. Only proceed to reference generation AFTER confirming prompt quality."
        ),
    }

    @staticmethod
    def _yaml_dump_folded(data, stream):
        """Dump YAML with folded scalar style (>) for long strings."""
        class _FoldedStr(str):
            pass

        def _folded_representer(dumper, data):
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=">")

        def _fold_long_strings(obj, threshold=YAML_FOLD_THRESHOLD):
            """Recursively convert long strings to folded style."""
            if isinstance(obj, str):
                if len(obj) > threshold and "\n" not in obj.rstrip():
                    return _FoldedStr(obj)
                return obj
            elif isinstance(obj, dict):
                return {k: _fold_long_strings(v, threshold) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_fold_long_strings(v, threshold) for v in obj]
            return obj

        class _FoldedDumper(yaml.Dumper):
            pass
        _FoldedDumper.add_representer(_FoldedStr, _folded_representer)

        folded_data = _fold_long_strings(data)
        yaml.dump(
            folded_data, stream,
            Dumper=_FoldedDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=YAML_DUMP_WIDTH,
        )

    def _tool_save_file(self, args: dict) -> str:
        filename = args["filename"]
        content = args["content"]
        message = args.get("message", "")

        if not self.project_dir:
            return "Error: project directory not initialized"

        filepath = self.project_dir / filename
        try:
            if filename.endswith(".yaml"):
                data = yaml.safe_load(content)
                with open(filepath, "w", encoding="utf-8") as f:
                    self._yaml_dump_folded(data, f)
            elif filename.endswith(".json"):
                data = json.loads(content)
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)

            if filename not in self.saved_files:
                self.saved_files.append(filename)

            # Track save count per file for iteration tracking
            save_key = f"_saves_{filename}"
            if not hasattr(self, save_key):
                setattr(self, save_key, 0)
            setattr(self, save_key, getattr(self, save_key) + 1)
            save_count = getattr(self, save_key)

            print(f"{Colors.GREEN}  [Saved] {filename} — {message} (v{save_count}){Colors.ENDC}")

            # Reset review gate when prompts.json is modified
            if filename == "prompts.json" and self._review_passed:
                self._review_passed = False
                print(f"{Colors.DIM}  ℹ prompts.json modified, needs re-validation via validate_before_generate{Colors.ENDC}")

            result = f"Successfully saved {filename} (version {save_count})"

            # Auto-inject review reminder for key files (only on first save)
            if save_count == 1 and filename in self._REVIEW_HINTS:
                hint = self._REVIEW_HINTS[filename]
                print(f"{Colors.MAGENTA}  📋 Reflection reminder injected{Colors.ENDC}")
                result += hint
            elif save_count > 1 and filename in self._REVIEW_HINTS:
                result += (
                    f"\n\n✅ Good — this is iteration #{save_count} of {filename}. "
                    "Re-read it with read_file to confirm your improvements, then proceed."
                )

            return result

        except (yaml.YAMLError, json.JSONDecodeError) as e:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"{Colors.YELLOW}  [Saved] {filename} (format corrected) — {message}{Colors.ENDC}")
            return f"Saved {filename} as raw text (parse warning: {e})"
        except Exception as e:
            print(f"{Colors.RED}  [Save failed] {filename}: {e}{Colors.ENDC}")
            return f"Error saving {filename}: {e}"

    def _tool_read_file(self, args: dict) -> str:
        filename = args["filename"]
        if not self.project_dir:
            return "Error: project directory not initialized"

        filepath = self.project_dir / filename
        if not filepath.exists():
            return f"File {filename} does not exist yet"

        try:
            content = filepath.read_text(encoding="utf-8")
            if len(content) > FILE_CONTENT_MAX_CHARS:
                content = content[:FILE_CONTENT_MAX_CHARS] + "\n... [truncated]"
            return content
        except Exception as e:
            return f"Error reading {filename}: {e}"

    def _tool_load_skill(self, args: dict) -> str:
        skill_name = args["skill"]
        filename = args["file"]

        skill_dir = SKILLS.get(skill_name)
        if not skill_dir:
            return f"Unknown skill: {skill_name}. Available: {', '.join(SKILLS.keys())}"

        filepath = skill_dir / filename
        if not filepath.exists():
            return f"File {skill_name}/{filename} not found"

        try:
            content = filepath.read_text(encoding="utf-8")
            # Switch displayed agent role based on loaded skill
            if skill_name in _AGENT_ROLES:
                self._current_role = _AGENT_ROLES[skill_name]
            print(f"{Colors.DIM}  [Loading skill] {skill_name}/{filename}{Colors.ENDC}")
            return content
        except Exception as e:
            return f"Error loading {skill_name}/{filename}: {e}"

    def _tool_generate_reference(self, args: dict) -> str:
        ref_type = args["ref_type"]
        ref_id = args["ref_id"]
        prompt = args["prompt"]
        aspect_ratio = args.get("aspect_ratio", "1:1")

        if not self.project_dir:
            return "Error: project directory not initialized"

        # Load style_anchor from prompts.json if available
        style_anchor = ""
        prompts_file = self.project_dir / "prompts.json"
        if prompts_file.exists():
            try:
                with open(prompts_file) as f:
                    pdata = json.load(f)
                style_anchor = pdata.get("style_anchor", "")
            except Exception:
                pass

        if not style_anchor:
            print(f"{Colors.YELLOW}  ⚠ Warning: style_anchor not found in prompts.json, reference images may lack style constraints{Colors.ENDC}")

        # Auto-enhance prompt for character reference sheets
        if ref_type == "character":
            suffix = (
                ", character reference sheet, multiple views, front view, "
                "side view, back view, white background, consistent design, "
                "same outfit, same hairstyle, high quality"
            )
            if "reference sheet" not in prompt.lower():
                prompt = prompt + suffix
            # Append style anchor for consistency
            if style_anchor and style_anchor.lower() not in prompt.lower():
                prompt = prompt + ", " + style_anchor
        elif ref_type == "scene":
            # Append style anchor for scene references too
            if style_anchor and style_anchor.lower() not in prompt.lower():
                prompt = prompt + ", " + style_anchor

        # Create image generator
        if not self._image_gen:
            from core.image.factory import create_image_gen

            self._image_gen = create_image_gen(self.config.image)

        try:
            refs_dir = self.project_dir / "assets" / "references"
            refs_dir.mkdir(parents=True, exist_ok=True)
            save_path = refs_dir / f"{ref_id}.png"

            print(f"{Colors.CYAN}  [Generating reference] {ref_type}/{ref_id}...{Colors.ENDC}")
            images = asyncio.run(self._image_gen.text_to_image(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            ))

            if images:
                images[0].save(save_path)
                self.generated_assets.append(str(save_path))
                print(f"{Colors.GREEN}  ✓ Reference image generated: {ref_id}.png{Colors.ENDC}")
                return f"Reference image saved: assets/references/{ref_id}.png"
            return f"Reference generation returned no results for {ref_id}"

        except Exception as e:
            print(f"{Colors.RED}  ✗ Reference generation failed {ref_id}: {e}{Colors.ENDC}")
            return f"Reference generation failed for {ref_id}: {e}"

    def _tool_generate_image(self, args: dict) -> str:
        # Quality gate: must call validate_before_generate first
        if not self._review_passed:
            print(f"{Colors.YELLOW}  ⚠ Pre-generation validation not passed, please call validate_before_generate first{Colors.ENDC}")
            return ("BLOCKED: You must call validate_before_generate first and pass all checks "
                    "before generating images. This ensures style_anchor, reference_images, "
                    "and continuity are properly set up. Please also load the reviewer skill "
                    "and review screenplay/storyboard/prompts BEFORE generation.")

        shot_id = args["shot_id"]
        prompt = args.get("prompt", "")
        aspect_ratio = args.get("aspect_ratio", self.config.project.default_aspect_ratio)

        # If no prompt provided, try reading from prompts.json
        prompts_data = None
        if not prompt:
            prompts_file = self.project_dir / "prompts.json"
            if prompts_file.exists():
                try:
                    with open(prompts_file) as f:
                        prompts_data = json.load(f)
                    shot_prompts = prompts_data.get("shots", {}).get(shot_id, {})
                    image_prompt = shot_prompts.get("image_prompt", {})
                    prompt = image_prompt.get("prompt", "")
                    aspect_ratio = image_prompt.get("aspect_ratio", aspect_ratio)
                except Exception:
                    pass

        if not prompt:
            return f"No prompt found for {shot_id}. Please provide a prompt or save prompts.json first."

        # Auto-append style_anchor from prompts.json for global style consistency
        if prompts_data:
            style_anchor = prompts_data.get("style_anchor", "")
            if style_anchor and style_anchor.lower() not in prompt.lower():
                prompt = f"{prompt}, {style_anchor}"

        # Auto-inject character descriptions from screenplay.yaml characters.visual_definition
        screenplay_file = self.project_dir / "screenplay.yaml"
        storyboard_file = self.project_dir / "storyboard.yaml"
        sb_data = None
        if storyboard_file.exists():
            try:
                with open(storyboard_file) as f:
                    sb_data = yaml.safe_load(f) or {}
            except Exception:
                pass

        if screenplay_file.exists() and sb_data:
            try:
                with open(screenplay_file) as f:
                    sp_data = yaml.safe_load(f) or {}
                # Build char_profiles from characters list
                char_profiles = {}
                for char in sp_data.get("characters", []):
                    cid = char.get("id", "")
                    vis_def = char.get("visual_definition", "")
                    if cid and vis_def:
                        char_profiles[cid] = vis_def

                if char_profiles:
                    # Find which scene this shot belongs to
                    scene_ref = None
                    for s in sb_data.get("shots", []):
                        if s.get("id") == shot_id:
                            scene_ref = s.get("scene_ref")
                            break
                    if scene_ref:
                        for scene in sp_data.get("scenes", []):
                            if scene.get("id") == scene_ref:
                                chars_in_scene = scene.get("characters_in_scene", [])
                                char_descs = []
                                for c in chars_in_scene:
                                    cref = c.get("char_ref", "") if isinstance(c, dict) else str(c)
                                    if cref in char_profiles:
                                        vis_def = char_profiles[cref]
                                        if vis_def and vis_def.strip()[:30].lower() not in prompt.lower():
                                            char_descs.append(vis_def.strip())
                                if char_descs:
                                    char_block = "; ".join(char_descs)
                                    prompt = f"[Character appearance: {char_block}] {prompt}"
                                    print(f"{Colors.DIM}  [Character lock] Injected {len(char_descs)} character description(s){Colors.ENDC}")
                                break
            except Exception:
                pass

        # Load reference images from prompts.json
        ref_paths = []
        if prompts_data is None:
            prompts_file = self.project_dir / "prompts.json"
            if prompts_file.exists():
                try:
                    with open(prompts_file) as f:
                        prompts_data = json.load(f)
                except Exception:
                    pass
        if prompts_data:
            shot_prompts = prompts_data.get("shots", {}).get(shot_id, {})
            image_prompt = shot_prompts.get("image_prompt", {})
            ref_ids = image_prompt.get("reference_images", [])
            for rid in ref_ids:
                ref_path = self.project_dir / "assets" / "references" / f"{rid}.png"
                if ref_path.exists():
                    ref_paths.append(ref_path)

        # Adjacent shot visual chaining (Solution A) — use previous shot's keyframe as reference
        prev_shot_id = None
        if sb_data:
            try:
                sb_shots = sb_data.get("shots", [])
                shot_ids_ordered = [s.get("id", "") for s in sb_shots]
                if shot_id in shot_ids_ordered:
                    idx = shot_ids_ordered.index(shot_id)
                    if idx > 0:
                        prev_shot_id = shot_ids_ordered[idx - 1]
                        prev_keyframe = self.project_dir / "assets" / "images" / f"{prev_shot_id.lower()}.png"
                        if prev_keyframe.exists():
                            ref_paths.append(prev_keyframe)
                            print(f"{Colors.DIM}  [Chain reference] {prev_shot_id} → {shot_id}{Colors.ENDC}")
            except Exception:
                pass

        # Create image generator
        if not self._image_gen:
            from core.image.factory import create_image_gen

            self._image_gen = create_image_gen(self.config.image)

        try:
            if ref_paths:
                ref_names = [p.stem for p in ref_paths]
                print(f"{Colors.CYAN}  [Generating image] {shot_id} (references: {', '.join(ref_names)})...{Colors.ENDC}")
                images = asyncio.run(self._image_gen.image_to_image(
                    prompt=prompt,
                    reference_images=ref_paths,
                    aspect_ratio=aspect_ratio,
                ))
            else:
                print(f"{Colors.CYAN}  [Generating image] {shot_id}...{Colors.ENDC}")
                images = asyncio.run(self._image_gen.text_to_image(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                ))

            if images:
                save_path = self.project_dir / "assets" / "images" / f"{shot_id.lower()}.png"
                images[0].save(save_path)
                self.generated_assets.append(str(save_path))

                # Check for fallback warning (reference images failed)
                fallback_warn = getattr(images[0], 'fallback_warning', None)
                if fallback_warn:
                    print(f"{Colors.YELLOW}  ⚠ {shot_id} reference images not applied, fell back to text-only generation! Consistency may be compromised{Colors.ENDC}")
                    return (
                        f"⚠️ WARNING: Image saved as {save_path.name}, but reference images FAILED to apply "
                        f"(reason: {fallback_warn}). This shot was generated with text-only mode — "
                        f"character appearance may be INCONSISTENT with other shots. "
                        f"Consider: 1) Re-generate the reference images, 2) Check reference file paths, "
                        f"3) Try regenerating this shot."
                    )

                print(f"{Colors.GREEN}  ✓ {shot_id} keyframe generated{Colors.ENDC}")
                ref_info = f" (with {len(ref_paths)} reference images)" if ref_paths else ""
                result_msg = f"Image saved: {save_path.name}{ref_info}"

                # Auto-continuity check (Solution F) — compare with previous shot
                if prev_shot_id:
                    prev_keyframe = self.project_dir / "assets" / "images" / f"{prev_shot_id.lower()}.png"
                    if prev_keyframe.exists():
                        try:
                            print(f"{Colors.DIM}  [Continuity check] {prev_shot_id} ↔ {shot_id}...{Colors.ENDC}")
                            cont_result = self._tool_check_continuity({
                                "shot_id_a": prev_shot_id,
                                "shot_id_b": shot_id,
                            })
                            result_msg += (
                                f"\n\n## Auto continuity check ({prev_shot_id} ↔ {shot_id}):\n"
                                f"{cont_result}\n\n"
                                f"If there are severe inconsistencies, consider regenerating {shot_id}."
                            )
                        except Exception:
                            pass  # continuity check failure should not block generation

                return result_msg
            return f"Image generation returned no results for {shot_id}"

        except Exception as e:
            print(f"{Colors.RED}  ✗ {shot_id} generation failed: {e}{Colors.ENDC}")
            return f"Image generation failed for {shot_id}: {e}"

    def _tool_generate_video(self, args: dict) -> str:
        # Quality gate: must call validate_before_generate first
        if not self._review_passed:
            print(f"{Colors.YELLOW}  ⚠ Pre-generation validation not passed, please call validate_before_generate first{Colors.ENDC}")
            return ("BLOCKED: You must call validate_before_generate first and pass all checks "
                    "before generating videos. Please review screenplay/storyboard/prompts first.")

        shot_id = args["shot_id"]
        prompt = args.get("prompt", "")
        use_first_frame = args.get("use_first_frame", True)
        duration = args.get("duration_seconds", self.config.video.default_duration)
        aspect_ratio = args.get("aspect_ratio", self.config.video.default_aspect_ratio)

        # Try reading from prompts.json
        prompts_data = None
        prompts_file = self.project_dir / "prompts.json"
        if prompts_file.exists():
            try:
                with open(prompts_file) as f:
                    prompts_data = json.load(f)
            except Exception:
                pass

        if not prompt and prompts_data:
            shot_prompts = prompts_data.get("shots", {}).get(shot_id, {})
            video_prompt = shot_prompts.get("video_prompt", {})
            prompt = video_prompt.get("prompt", "")
            duration = video_prompt.get("duration_seconds", duration)
            aspect_ratio = video_prompt.get("aspect_ratio", aspect_ratio)

            # Auto-inject opening/closing state for continuity
            opening = video_prompt.get("opening_state", "")
            closing = video_prompt.get("closing_state", "")
            if opening and opening.lower() not in prompt.lower():
                prompt = f"The video begins with {opening}. {prompt}"
            if closing and closing.lower() not in prompt.lower():
                prompt = f"{prompt} The video ends with {closing}."

        # Auto-append style_anchor from prompts.json
        if prompts_data:
            style_anchor = prompts_data.get("style_anchor", "")
            if style_anchor and style_anchor.lower() not in prompt.lower():
                prompt = f"{prompt}, {style_anchor}"

        if not prompt:
            return f"No prompt found for {shot_id}. Please provide a prompt or save prompts.json first."

        # Create video generator
        if not self._video_gen:
            from core.video.factory import create_video_gen

            self._video_gen = create_video_gen(self.config.video)

        try:
            # Check for first frame image
            first_frame = self.project_dir / "assets" / "images" / f"{shot_id.lower()}.png"
            has_first_frame = first_frame.exists() and use_first_frame

            print(f"{Colors.CYAN}  [Generating video] {shot_id} ({'image-to-video' if has_first_frame else 'text-to-video'})...{Colors.ENDC}")

            if has_first_frame:
                task = asyncio.run(self._video_gen.image_to_video(
                    prompt=prompt,
                    first_frame=first_frame,
                    duration_seconds=duration,
                    aspect_ratio=aspect_ratio,
                ))
            else:
                task = asyncio.run(self._video_gen.text_to_video(
                    prompt=prompt,
                    duration_seconds=duration,
                    aspect_ratio=aspect_ratio,
                ))

            # Poll for result
            def _progress(t):
                if t.progress > 0:
                    print(f"{Colors.DIM}  Progress: {t.progress:.0%}{Colors.ENDC}")

            task = asyncio.run(self._video_gen.wait_for_result(
                task,
                poll_interval=self.config.video.poll_interval,
                timeout=self.config.video.poll_timeout,
                on_progress=_progress,
            ))

            if task.status == "completed" and task.result:
                save_path = self.project_dir / "assets" / "videos" / f"{shot_id.lower()}.mp4"
                task.result.save(save_path)
                self.generated_assets.append(str(save_path))
                print(f"{Colors.GREEN}  ✓ {shot_id} video generated{Colors.ENDC}")
                return f"Video saved: {save_path.name}"
            else:
                error = task.error or "Unknown error"
                print(f"{Colors.RED}  ✗ {shot_id} video generation failed: {error}{Colors.ENDC}")
                return f"Video generation failed for {shot_id}: {error}"

        except Exception as e:
            print(f"{Colors.RED}  ✗ {shot_id} generation failed: {e}{Colors.ENDC}")
            return f"Video generation failed for {shot_id}: {e}"

    def _tool_analyze_media(self, args: dict) -> str:
        file_path = args["file_path"]
        prompt = args.get("prompt", "Analyze this image's quality, composition, and color tone. Point out any issues.")

        full_path = self.project_dir / file_path
        if not full_path.exists():
            return f"File not found: {file_path}"

        try:
            from core.vision.factory import create_vision

            vision = create_vision(self.config)

            print(f"{Colors.CYAN}  [Analyzing] {file_path}...{Colors.ENDC}")

            if full_path.suffix.lower() in ('.mp4', '.mov', '.avi'):
                result = asyncio.run(vision.analyze_video(full_path, prompt))
            else:
                result = asyncio.run(vision.analyze_image(full_path, prompt))

            print(f"{Colors.GREEN}  ✓ Analysis complete{Colors.ENDC}")
            return result

        except Exception as e:
            return f"Analysis failed: {e}"

    def _tool_check_continuity(self, args: dict) -> str:
        shot_id_a = args["shot_id_a"]
        shot_id_b = args["shot_id_b"]

        if not self.project_dir:
            return "Error: project directory not initialized"

        img_a = self.project_dir / "assets" / "images" / f"{shot_id_a.lower()}.png"
        img_b = self.project_dir / "assets" / "images" / f"{shot_id_b.lower()}.png"

        if not img_a.exists():
            return f"Keyframe not found: {shot_id_a}. Generate it first."
        if not img_b.exists():
            return f"Keyframe not found: {shot_id_b}. Generate it first."

        try:
            import base64 as b64mod
            from core.vision.factory import create_vision

            vision = create_vision(self.config)

            print(f"{Colors.CYAN}  [Continuity check] {shot_id_a} ↔ {shot_id_b}...{Colors.ENDC}")

            # Build a multi-image prompt for comparison
            continuity_prompt = (
                f"Compare the following two keyframe images ({shot_id_a} and {shot_id_b}), check visual continuity:\n"
                "1. Character appearance consistency: Are the same character's facial features, clothing, and hairstyle consistent?\n"
                "2. Color tone and lighting: Are the overall color temperature and lighting direction coordinated?\n"
                "3. Scene coherence: Are spatial relationships reasonable?\n"
                "4. Style unity: Is the visual style (realistic/anime/ink painting, etc.) consistent?\n\n"
                "Please specifically point out inconsistencies and provide improvement suggestions. If consistency is good, please confirm."
            )

            # Use GPT-4o style multi-image analysis
            # Read both images as base64
            with open(img_a, "rb") as f:
                b64_a = b64mod.b64encode(f.read()).decode()
            with open(img_b, "rb") as f:
                b64_b = b64mod.b64encode(f.read()).decode()

            mime_a = "image/png" if img_a.suffix == ".png" else "image/jpeg"
            mime_b = "image/png" if img_b.suffix == ".png" else "image/jpeg"

            # Use OpenAI-compatible vision API directly for multi-image
            from openai import OpenAI
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                # Fallback: analyze each image separately
                result_a = asyncio.run(vision.analyze_image(img_a, f"Describe the character appearance, clothing, color tone, and lighting in this image."))
                result_b = asyncio.run(vision.analyze_image(img_b, f"Describe the character appearance, clothing, color tone, and lighting in this image."))
                print(f"{Colors.GREEN}  ✓ Continuity check complete (single-image mode){Colors.ENDC}")
                return (
                    f"## {shot_id_a} Analysis\n{result_a}\n\n"
                    f"## {shot_id_b} Analysis\n{result_b}\n\n"
                    "Please compare the descriptions of the two images above to assess consistency."
                )

            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": continuity_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_a};base64,{b64_a}"}},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_b};base64,{b64_b}"}},
                    ],
                }],
            )

            result = response.choices[0].message.content
            print(f"{Colors.GREEN}  ✓ Continuity check complete{Colors.ENDC}")
            return result

        except Exception as e:
            print(f"{Colors.RED}  ✗ Continuity check failed: {e}{Colors.ENDC}")
            return f"Continuity check failed: {e}"

    def _tool_validate_before_generate(self, args: dict) -> str:
        """Run pre-generation validation checks on prompts.json, screenplay.yaml, and storyboard.yaml."""
        if not self.project_dir:
            return "Error: project directory not initialized"

        prompts_file = self.project_dir / "prompts.json"
        if not prompts_file.exists():
            return "FAIL: prompts.json not found. Create it first using the visualizer skill."

        try:
            with open(prompts_file) as f:
                data = json.load(f)
        except Exception as e:
            return f"FAIL: Cannot parse prompts.json: {e}"

        issues = []
        warnings = []

        # ── 0. Narrative spine & pacing checks (screenplay + storyboard) ──

        screenplay_file = self.project_dir / "screenplay.yaml"
        storyboard_file = self.project_dir / "storyboard.yaml"

        # 0a. Check narrative_beats in screenplay
        if screenplay_file.exists():
            try:
                with open(screenplay_file) as f:
                    sp = yaml.safe_load(f) or {}
                beats = sp.get("narrative_beats", [])
                if not beats:
                    issues.append("[P0-NARRATIVE] screenplay.yaml missing narrative_beats (narrative spine). Must define hook/setup/development/climax/resolution beats before writing scenes.")
                else:
                    beat_names = [b.get("beat", "") for b in beats]
                    if "hook" not in beat_names:
                        issues.append("[P1-NARRATIVE] narrative_beats missing 'hook'. The first 1-5 seconds must have a strong hook to capture the audience.")
                    if "climax" not in beat_names:
                        warnings.append("[P2-NARRATIVE] narrative_beats missing 'climax'. The story should have an emotional peak or twist.")

                    # Check beat duration totals vs target
                    total_beat_dur = sum(b.get("target_duration_seconds", 0) for b in beats)
                    meta = sp.get("meta", {})
                    target_dur = meta.get("duration_seconds", 0)
                    if target_dur and total_beat_dur:
                        ratio = total_beat_dur / target_dur
                        if ratio < 0.7 or ratio > 1.5:
                            warnings.append(f"[P2-NARRATIVE] Total beat duration ({total_beat_dur}s) significantly differs from target duration ({target_dur}s) (ratio {ratio:.1f}). Check target_duration_seconds allocation.")

                    # Check pacing monotony — are all beats the same pacing?
                    pacings = [b.get("pacing", "") for b in beats if b.get("pacing")]
                    if len(set(pacings)) <= 1 and len(pacings) > 2:
                        warnings.append(f"[P2-PACING] All beats have pacing '{pacings[0]}', rhythm is too monotonous. The story needs tempo variation.")

                    # Check scenes belong to beats
                    scenes = sp.get("scenes", [])
                    beat_scene_ids = set()
                    for b in beats:
                        for s in b.get("scenes", []):
                            beat_scene_ids.add(s)
                    orphan_scenes = [s.get("id", "?") for s in scenes if s.get("id") not in beat_scene_ids]
                    if orphan_scenes:
                        warnings.append(f"[P2-NARRATIVE] The following scenes are not linked to any beat (orphan scenes?): {', '.join(orphan_scenes)}")
            except Exception as e:
                warnings.append(f"[P2-NARRATIVE] Cannot parse screenplay.yaml: {e}")
        else:
            warnings.append("[P2-NARRATIVE] screenplay.yaml does not exist, cannot perform narrative spine validation.")

        # 0b. Check storyboard pacing & beat coverage
        if storyboard_file.exists():
            try:
                with open(storyboard_file) as f:
                    sb = yaml.safe_load(f) or {}
                sb_shots = sb.get("shots", [])
                if sb_shots:
                    # Check pacing_intent distribution
                    pacing_values = [s.get("pacing_intent", "") for s in sb_shots if s.get("pacing_intent")]
                    if pacing_values and len(set(pacing_values)) <= 1 and len(pacing_values) > 3:
                        warnings.append(f"[P2-PACING] All shots in storyboard have pacing_intent '{pacing_values[0]}', rhythm is too monotonous.")

                    # Check hook shot duration
                    for s in sb_shots:
                        if s.get("beat_ref") == "hook":
                            dur = s.get("use_duration") or s.get("duration_seconds", 0)
                            if dur and dur > 5:
                                warnings.append(f"[P2-PACING] Hook shot {s.get('id', '?')} duration {dur}s is too long. Hook should be ≤ 5s, shorter is better.")

                    # Check beat_ref coverage
                    shots_without_beat = [s.get("id", "?") for s in sb_shots if not s.get("beat_ref")]
                    if shots_without_beat:
                        warnings.append(f"[P2-NARRATIVE] The following shots are missing beat_ref: {', '.join(shots_without_beat)}. Every shot must be linked to a narrative beat.")

                    # Check use_duration monotony — all same duration is a red flag
                    durations = [s.get("use_duration", 0) for s in sb_shots if s.get("use_duration")]
                    if durations and len(set(durations)) == 1 and len(durations) > 3:
                        warnings.append(f"[P2-PACING] All shots have use_duration {durations[0]}s, indicating no rhythm variation. Must have both fast and slow pacing.")
                    # Check shot-size jumps (Solution C) — detect extreme framing transitions
                    _SHOT_SIZE_SCALE = {
                        "ews": 0, "extreme wide shot": 0, "extreme wide": 0, "aerial": 0,
                        "ws": 1, "wide shot": 1, "wide": 1, "full shot": 1,
                        "ms": 2, "medium shot": 2, "medium": 2,
                        "mcu": 3, "medium close-up": 3, "medium close up": 3,
                        "cu": 4, "close-up": 4, "close up": 4, "closeup": 4,
                        "ecu": 5, "extreme close-up": 5, "extreme close up": 5, "detail": 5,
                    }
                    for i in range(len(sb_shots) - 1):
                        cur = sb_shots[i]
                        nxt = sb_shots[i + 1]
                        cur_type = (cur.get("shot_type", "") or "").strip().lower()
                        nxt_type = (nxt.get("shot_type", "") or "").strip().lower()
                        cur_scale = _SHOT_SIZE_SCALE.get(cur_type)
                        nxt_scale = _SHOT_SIZE_SCALE.get(nxt_type)
                        if cur_scale is not None and nxt_scale is not None:
                            jump = abs(cur_scale - nxt_scale)
                            if jump >= 3:
                                # Allow intentional dramatic jumps (breathing == "hold")
                                nxt_breathing = (nxt.get("breathing", "") or "").lower()
                                if nxt_breathing != "hold":
                                    warnings.append(
                                        f"[P2-CONTINUITY] Shot {cur.get('id', '?')}({cur_type.upper()}) → "
                                        f"{nxt.get('id', '?')}({nxt_type.upper()}) shot size jump too large ({jump} levels apart). "
                                        f"Consider inserting a transition shot, or mark breathing='hold' for intentional dramatic jump cut."
                                    )

            except Exception as e:
                warnings.append(f"[P2-PACING] Cannot parse storyboard.yaml: {e}")

        # ── 0c. Check visual_description in screenplay.yaml ──
        sp_file = self.project_dir / "screenplay.yaml"
        if sp_file.exists():
            try:
                with open(sp_file) as f:
                    sp = yaml.safe_load(f) or {}
                sp_scenes = sp.get("scenes", [])
                for vs in sp_scenes:
                    desc = vs.get("visual_description", "")
                    sid = vs.get("id", "?")
                    if not desc or len(desc.strip()) < VISUAL_DESC_MIN_CHARS:
                        warnings.append(f"[P2-VISUAL_DESC] Scene {sid} visual_description is too short (<{VISUAL_DESC_MIN_CHARS} chars), visual description should be 200-600 words of detailed prose.")
                    elif len(desc.split()) < VISUAL_DESC_WARN_WORDS and len(desc) < VISUAL_DESC_WARN_CHARS:
                        warnings.append(f"[P2-VISUAL_DESC] Scene {sid} visual_description may not be detailed enough ({len(desc)} chars), recommend writing as novelistic continuous prose (200-600 words).")
            except Exception as e:
                warnings.append(f"[P2-VISUAL_DESC] Cannot parse screenplay.yaml: {e}")

        # ── 1. Check style_anchor quality ──
        style_anchor = data.get("style_anchor", "")
        if not style_anchor:
            issues.append("[P0-CRITICAL] style_anchor is MISSING. Must generate a detailed style description before any generation.")
        else:
            word_count = len(style_anchor.split())
            if word_count < 20:
                issues.append(f"[P1-STYLE] style_anchor is too short ({word_count} words). Should be 50-100 words covering render style, color, lighting, texture, exclusions.")
            elif word_count < 40:
                warnings.append(f"[P2-STYLE] style_anchor could be more detailed ({word_count} words). Recommend 50-100 words.")

            has_not = "not " in style_anchor.lower() or "NOT " in style_anchor
            if not has_not:
                warnings.append("[P2-STYLE] style_anchor has no exclusion terms (NOT xxx). Consider adding what styles to avoid.")

        # 2. Check reference images
        shots = data.get("shots", {})
        ref_dir = self.project_dir / "assets" / "references"
        missing_refs = []
        shots_without_refs = []

        for shot_id, shot_data in shots.items():
            img_prompt = shot_data.get("image_prompt")
            if not img_prompt:
                continue
            ref_ids = img_prompt.get("reference_images", [])
            if not ref_ids:
                shots_without_refs.append(shot_id)
            for rid in ref_ids:
                ref_path = ref_dir / f"{rid}.png"
                if not ref_path.exists():
                    missing_refs.append(f"{shot_id} → {rid}.png")

        if missing_refs:
            issues.append(f"[P1-REFS] Missing reference images: {'; '.join(missing_refs)}. Generate them with generate_reference first.")
        if shots_without_refs:
            issues.append(
                f"[P1-REFS] The following shots have no reference_images: {', '.join(shots_without_refs)}. "
                "Without reference images, each shot will be generated independently, causing severe inconsistency in character appearance and scene style. "
                "Please use generate_reference to create character/scene references, and add them to reference_images in each shot of prompts.json."
            )

        # 3. Check opening/closing state continuity
        shot_ids_sorted = sorted(shots.keys())
        continuity_breaks = []
        for i in range(len(shot_ids_sorted) - 1):
            curr_id = shot_ids_sorted[i]
            next_id = shot_ids_sorted[i + 1]
            curr_video = shots[curr_id].get("video_prompt") or {}
            next_video = shots[next_id].get("video_prompt") or {}

            curr_closing = curr_video.get("closing_state", "")
            next_opening = next_video.get("opening_state", "")

            if not curr_closing and not next_opening:
                continuity_breaks.append(f"{curr_id}→{next_id}: both missing opening/closing state")
            elif not curr_closing:
                continuity_breaks.append(f"{curr_id}: missing closing_state")
            elif not next_opening:
                continuity_breaks.append(f"{next_id}: missing opening_state")

        if continuity_breaks:
            warnings.append(f"[P2-CONTINUITY] Missing opening/closing states: {'; '.join(continuity_breaks)}")

        # 4. Check prompt specificity (very short prompts are likely low quality)
        short_prompts = []
        for shot_id, shot_data in shots.items():
            img_prompt = shot_data.get("image_prompt")
            if img_prompt and img_prompt.get("prompt"):
                words = len(img_prompt["prompt"].split())
                if words < 15:
                    short_prompts.append(f"{shot_id} image ({words} words)")
            vid_prompt = shot_data.get("video_prompt")
            if vid_prompt and vid_prompt.get("prompt"):
                words = len(vid_prompt["prompt"].split())
                if words < 10:
                    short_prompts.append(f"{shot_id} video ({words} words)")

        if short_prompts:
            warnings.append(f"[P2-QUALITY] Prompts may be too short: {'; '.join(short_prompts)}")

        # 5. Check style_anchor presence in prompts
        if style_anchor:
            # Check a sample of key style words (first 3 significant words)
            style_words = [w.strip(",. ") for w in style_anchor.split() if len(w) > 3][:5]
            missing_style = []
            for shot_id, shot_data in shots.items():
                img_prompt = shot_data.get("image_prompt")
                if img_prompt and img_prompt.get("prompt"):
                    prompt_lower = img_prompt["prompt"].lower()
                    matches = sum(1 for w in style_words if w.lower() in prompt_lower)
                    if matches < 2:
                        missing_style.append(f"{shot_id}")
            if missing_style:
                warnings.append(f"[P2-STYLE] style_anchor keywords may be missing in shots: {', '.join(missing_style)}. "
                               "Note: style_anchor is auto-appended during generation, but it's better to include in original prompts too.")

        # Build report
        report = "=== Pre-Generation Validation Report ===\n\n"

        if not issues and not warnings:
            report += "✅ ALL CHECKS PASSED. Ready to generate!\n"
            report += f"\n📊 Stats: {len(shots)} shots, style_anchor={len(style_anchor.split())} words"
            ref_count = len(list(ref_dir.glob("*.png"))) if ref_dir.exists() else 0
            report += f", {ref_count} reference images"
            self._review_passed = True
        else:
            if issues:
                report += f"❌ {len(issues)} BLOCKING ISSUE(S) — must fix before generating:\n"
                for issue in issues:
                    report += f"  • {issue}\n"
                report += "\n"
            if warnings:
                report += f"⚠️  {len(warnings)} WARNING(S) — recommended to fix:\n"
                for warn in warnings:
                    report += f"  • {warn}\n"

            if issues:
                report += "\n🚫 CANNOT proceed with generation until blocking issues are resolved."
                self._review_passed = False
            else:
                report += "\n⚡ Can proceed with generation, but fixing warnings will improve quality."
                self._review_passed = True

        print(f"{Colors.CYAN}  [Validation] Pre-generation check complete{Colors.ENDC}")
        return report

    def _tool_search_reference(self, args: dict) -> str:
        query = args["query"]
        platform = args.get("platform", "douyin")

        try:
            from core.browser.playwright import PlaywrightBrowser, BrowserConnectionError


            print(f"{Colors.CYAN}  [Search] {platform}: {query}...{Colors.ENDC}")

            async def _search():
                browser = PlaywrightBrowser()
                try:
                    return await browser.search_videos(query, platform)
                finally:
                    await browser.close()

            try:
                results = asyncio.run(_search())
            except BrowserConnectionError as e:
                print(f"{Colors.YELLOW}  ⚠ Browser connection failed{Colors.ENDC}")
                print(f"  {Colors.DIM}{e}{Colors.ENDC}")
                return (
                    f"Browser connection failed: {e}\n"
                    "Please inform the user to quit Chrome first, then re-run the command. "
                    "Takone will automatically launch Chrome in debug mode and preserve login state."
                )

            if results:
                print(f"{Colors.GREEN}  ✓ Found {len(results)} reference video(s){Colors.ENDC}")
                return json.dumps(results, ensure_ascii=False, indent=2)
            return "No results found"

        except ImportError as e:
            return f"Playwright not installed: {e}. Please run: pip install playwright && playwright install chromium"
        except Exception as e:
            return f"Search failed: {e}"

    def _tool_list_assets(self, args: dict) -> str:
        if not self.project_dir:
            return "No project directory"

        result = {"images": [], "videos": []}

        images_dir = self.project_dir / "assets" / "images"
        videos_dir = self.project_dir / "assets" / "videos"

        if images_dir.is_dir():
            result["images"] = sorted(f.name for f in images_dir.iterdir() if f.is_file())
        if videos_dir.is_dir():
            result["videos"] = sorted(f.name for f in videos_dir.iterdir() if f.is_file())

        return json.dumps(result, ensure_ascii=False, indent=2)

    # Storyboard transition → FFmpeg transition name mapping
    _TRANSITION_MAP = {
        # Basic transitions
        "cut": "none",
        "dissolve": "dissolve",
        "fade": "fade",
        "fade from black": "fade",
        "fade to black": "fade",
        "match_cut": "none",
        "wipe": "wipeleft",
        "white flash": "fade",
        "cross_dissolve": "dissolve",
        "none": "none",
        # Directional wipes
        "wipe_left": "wipeleft",
        "wipe_right": "wiperight",
        "wipe_up": "wipeup",
        "wipe_down": "wipedown",
        # Slide transitions
        "slide_left": "slideleft",
        "slide_right": "slideright",
        # Reveal transitions
        "circle_open": "circleopen",
        "circle_close": "circleclose",
        "radial": "radial",
        "pixelize": "pixelize",
        # Smooth transitions
        "smooth_left": "smoothleft",
        "smooth_right": "smoothright",
        # Squeeze
        "squeeze_h": "squeezeh",
        "squeeze_v": "squeezev",
    }

    def _tool_assemble_video(self, args: dict) -> str:
        shot_ids = args.get("shot_ids", [])
        trims = args.get("trims", None)
        transition = args.get("transition", None)  # None = auto from storyboard
        transition_duration = args.get("transition_duration", 0.5)
        auto_storyboard = args.get("auto_from_storyboard", True)
        output_filename = args.get("output_filename", "final.mp4")

        if not self.project_dir:
            return "Error: project directory not initialized"

        videos_dir = self.project_dir / "assets" / "videos"
        images_dir = self.project_dir / "assets" / "images"

        # Load storyboard for metadata
        storyboard_data = None
        if auto_storyboard:
            storyboard_file = self.project_dir / "storyboard.yaml"
            if storyboard_file.exists():
                try:
                    with open(storyboard_file) as f:
                        storyboard_data = yaml.safe_load(f)
                except Exception:
                    pass

        # Build shot metadata lookup from storyboard
        shot_meta = {}
        if storyboard_data:
            for s in storyboard_data.get("shots", []):
                shot_meta[s["id"]] = s

        # Determine shot order
        if not shot_ids:
            if storyboard_data:
                # Use storyboard order (authoritative)
                shot_ids = [s["id"] for s in storyboard_data.get("shots", [])]
            elif videos_dir.is_dir():
                files = sorted(f for f in videos_dir.iterdir() if f.suffix == ".mp4")
                shot_ids = [f.stem.upper() for f in files]
            if not shot_ids:
                return "No shots found. Generate video clips first."

        try:
            from utils.ffmpeg import FFmpegAssembler


            assembler = FFmpegAssembler(
                crf=self.config.video.encoding_crf,
                preset=self.config.video.encoding_preset,
                fps=self.config.video.encoding_fps,
            )
            if not assembler.check_installed():
                return "FFmpeg is not installed. Please install FFmpeg first: brew install ffmpeg"

            # Collect clips, handling image_only shots and missing clips
            clips = []
            clip_metas = []
            missing = []
            still_temps = []

            for sid in shot_ids:
                clip = videos_dir / f"{sid.lower()}.mp4"
                meta = shot_meta.get(sid, {})

                if clip.exists():
                    clips.append(clip)
                    clip_metas.append(meta)
                else:
                    # Check for image_only shots (title cards, ending frames)
                    img = images_dir / f"{sid.lower()}.png"
                    gen_strategy = meta.get("gen_strategy", "")
                    use_dur = meta.get("use_duration", meta.get("duration_seconds", 3))

                    if img.exists() and gen_strategy == "image_only":
                        # Convert image to video with Ken Burns motion
                        still_video = videos_dir / f"{sid.lower()}.mp4"
                        motion = meta.get("motion", "zoom_in")
                        print(f"{Colors.DIM}  [Assembly] Converting still image {sid} to {use_dur}s video (motion={motion}){Colors.ENDC}")
                        assembler.image_to_still_video(img, still_video, use_dur, motion=motion)
                        clips.append(still_video)
                        clip_metas.append(meta)
                        still_temps.append(still_video)
                    elif img.exists():
                        # Has image but no video — skip with warning
                        print(f"{Colors.YELLOW}  ⚠ {sid} no video asset, skipping{Colors.ENDC}")
                    else:
                        missing.append(sid)

            if not clips:
                return "No valid clips to assemble. Generate video/image clips first."

            if missing:
                print(f"{Colors.YELLOW}  ⚠ Missing clips: {', '.join(missing)}, these shots will be skipped{Colors.ENDC}")

            # Auto-build trims from storyboard if not explicitly provided
            auto_trims = None
            if trims is None and storyboard_data:
                auto_trims = []
                has_any_trim = False
                for meta in clip_metas:
                    trim_s = meta.get("trim_start", 0.0) or 0.0
                    trim_e = meta.get("trim_end", None)
                    use_dur = meta.get("use_duration", None)

                    # If use_duration specified, calculate end from start + use_duration
                    if use_dur and trim_e is None and use_dur < 5.0:
                        trim_e = trim_s + use_dur

                    if trim_s > 0 or trim_e is not None:
                        auto_trims.append({"start": trim_s, "end": trim_e})
                        has_any_trim = True
                    else:
                        auto_trims.append(None)

                if not has_any_trim:
                    auto_trims = None  # Don't pass empty trims

            final_trims = trims if trims is not None else auto_trims

            # Auto-build per-shot transitions from storyboard
            per_transitions = None
            per_durations = None
            use_advanced = False

            if transition is None and storyboard_data and len(clips) > 1:
                per_transitions = []
                per_durations = []
                for i, meta in enumerate(clip_metas[:-1]):
                    t_out = meta.get("transition_out", "cut")
                    t_mapped = self._TRANSITION_MAP.get(
                        str(t_out).lower().strip(), "none"
                    )
                    per_transitions.append(t_mapped)
                    per_durations.append(transition_duration)

                # Check if we actually have any real transitions
                if any(t != "none" for t in per_transitions):
                    use_advanced = True

            # Build info string for display
            n_trimmed = sum(1 for t in (final_trims or []) if t) if final_trims else 0
            n_transitions = sum(1 for t in (per_transitions or []) if t != "none") if per_transitions else 0
            info_parts = [f"{len(clips)} clip(s)"]
            if n_trimmed:
                info_parts.append(f"{n_trimmed} trim(s)")
            if n_transitions:
                info_parts.append(f"{n_transitions} transition(s)")
            elif transition and transition != "none":
                info_parts.append(f"global {transition} transition")

            print(f"{Colors.CYAN}  [Assembly] Smart assembly: {', '.join(info_parts)}...{Colors.ENDC}")

            output_path = self.project_dir / "output" / output_filename

            if use_advanced:
                # Per-shot transitions
                result_path = assembler.concatenate_advanced(
                    clips=clips,
                    output=output_path,
                    transitions=per_transitions,
                    transition_durations=per_durations,
                    trims=final_trims,
                )
            elif transition and transition != "none":
                # Global transition override
                result_path = assembler.concatenate(
                    clips=clips,
                    output=output_path,
                    transition=transition,
                    transition_duration=transition_duration,
                    trims=final_trims,
                )
            else:
                # Simple concat (with trims if available)
                result_path = assembler.concatenate(
                    clips=clips,
                    output=output_path,
                    transition="none",
                    trims=final_trims,
                )

            # Get final video info
            duration = assembler._get_duration(result_path)
            size_mb = result_path.stat().st_size / (1024 * 1024)

            print(f"{Colors.GREEN}  ✓ Video assembly complete: {result_path.name} ({duration:.1f}s, {size_mb:.1f}MB){Colors.ENDC}")

            result_msg = (
                f"Video assembled: {output_filename}\n"
                f"Clips: {len(clips)}\n"
                f"Duration: {duration:.1f}s\n"
                f"Size: {size_mb:.1f}MB\n"
                f"Path: {result_path}"
            )
            if n_trimmed:
                result_msg += f"\nTrimmed: {n_trimmed} clips (from storyboard metadata)"
            if n_transitions:
                trans_summary = ", ".join(
                    f"{per_transitions[i]}" for i in range(len(per_transitions))
                    if per_transitions[i] != "none"
                )
                result_msg += f"\nTransitions: {trans_summary}"
            if storyboard_data:
                result_msg += "\n(Auto-configured from storyboard.yaml)"

            return result_msg

        except Exception as e:
            print(f"{Colors.RED}  ✗ Video assembly failed: {e}{Colors.ENDC}")
            return f"Assembly failed: {e}"

    def _tool_add_audio_track(self, args: dict) -> str:
        """Add background music (and optionally voiceover) to assembled video."""
        if not self.project_dir:
            return "Error: project directory not initialized"

        music_path_str = args.get("music_path", "")
        music_volume = args.get("music_volume", self.config.audio.default_music_volume)
        video_path_str = args.get("video_path", "output/final.mp4")
        output_filename = args.get("output_filename", "final_with_audio.mp4")

        video_path = self.project_dir / video_path_str
        if not video_path.exists():
            return f"Error: Video not found at {video_path_str}. Run assemble_video first."

        if not music_path_str:
            return "Error: music_path is required. Provide a path to a music file (e.g., 'assets/audio/bgm.mp3')."

        music_path = self.project_dir / music_path_str
        if not music_path.exists():
            # Try absolute path
            music_path = Path(music_path_str)
            if not music_path.exists():
                return f"Error: Music file not found at {music_path_str}"

        try:
            from utils.audio import AudioManager


            audio_mgr = AudioManager(self.project_dir)

            # Import and prepare music
            print(f"{Colors.CYAN}  [Audio] Importing audio: {music_path.name}{Colors.ENDC}")
            imported = audio_mgr.import_music(music_path, name="bgm")

            # Get video duration to trim music
            from utils.ffmpeg import FFmpegAssembler
            assembler = FFmpegAssembler(
                crf=self.config.video.encoding_crf,
                preset=self.config.video.encoding_preset,
                fps=self.config.video.encoding_fps,
            )
            video_duration = assembler._get_duration(video_path)

            # Trim music to video length with fade in/out
            trimmed = audio_mgr.trim_audio(
                imported,
                audio_mgr.audio_dir / "bgm_trimmed.m4a",
                duration=video_duration,
                fade_out=self.config.audio.fade_out_seconds,
                fade_in=self.config.audio.fade_in_seconds,
            )

            # Adjust volume
            volume_adjusted = audio_mgr.adjust_volume(
                trimmed,
                audio_mgr.audio_dir / "bgm_final.m4a",
                volume=music_volume,
            )

            # Apply loudness normalization
            if self.config.audio.loudness_normalize:
                normalized = audio_mgr.normalize_loudness(
                    volume_adjusted,
                    audio_mgr.audio_dir / "bgm_normalized.m4a",
                )
                volume_adjusted = normalized

            # Add to video
            output_path = self.project_dir / "output" / output_filename
            print(f"{Colors.CYAN}  [Audio] Mixing audio and video...{Colors.ENDC}")
            audio_mgr.add_audio_to_video(video_path, volume_adjusted, output_path)

            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"{Colors.GREEN}  ✓ Audio added: {output_filename} ({video_duration:.1f}s, {size_mb:.1f}MB){Colors.ENDC}")

            return (
                f"Audio track added successfully.\n"
                f"Output: {output_filename}\n"
                f"Music: {music_path.name} (volume: {music_volume})\n"
                f"Duration: {video_duration:.1f}s\n"
                f"Size: {size_mb:.1f}MB\n"
                f"Path: {output_path}"
            )

        except Exception as e:
            print(f"{Colors.RED}  ✗ Audio addition failed: {e}{Colors.ENDC}")
            return f"Audio track failed: {e}"

    # ── Conversation engine — Anthropic protocol ─────────────────

    def _send_anthropic(self, user_content: str | list | None, *, watcher: InputWatcher | None = None):
        """Anthropic messages API loop with streaming (Claude, MiniMax)."""
        if user_content is not None:
            self.messages.append({"role": "user", "content": user_content})

        def _check_interrupted():
            return (watcher and watcher.interrupted)

        while True:
            spinner = Spinner(msg=f"{self._current_role[1]} thinking")
            spinner.start()

            # Stream events into a queue from daemon thread
            event_q: queue.Queue = queue.Queue()
            def _do_stream():
                try:
                    with self.client.messages.stream(
                        model=self.model,
                        max_tokens=MAX_LLM_TOKENS,
                        system=SYSTEM_PROMPT,
                        messages=self.messages,
                        tools=TOOLS_ANTHROPIC,
                    ) as stream:
                        for event in stream:
                            event_q.put(("event", event))
                        event_q.put(("done", stream.get_final_message()))
                except Exception as exc:
                    event_q.put(("error", exc))

            api_thread = threading.Thread(target=_do_stream, daemon=True)
            api_thread.start()

            # Consume stream events, printing text deltas immediately
            spinner_stopped = False
            stream_printer = _StreamPrinter(self._current_role)
            response = None

            while True:
                if _check_interrupted():
                    if not spinner_stopped:
                        spinner.stop()
                    stream_printer.finish()
                    if self.messages and self.messages[-1].get("role") == "user":
                        self.messages.pop()
                    return

                # Drain all available events (batch processing for lower latency)
                events = []
                try:
                    events.append(event_q.get(timeout=0.02))
                    # Grab any additional queued events without blocking
                    while True:
                        events.append(event_q.get_nowait())
                except queue.Empty:
                    pass
                if not events:
                    continue

                done = False
                for kind, data in events:
                    if kind == "error":
                        if not spinner_stopped:
                            spinner.stop()
                        stream_printer.finish()
                        print(f"\n{Colors.RED}  API call failed: {data}{Colors.ENDC}")
                        return

                    if kind == "event":
                        event = data
                        if hasattr(event, "type") and event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                if not spinner_stopped:
                                    spinner.stop()
                                    spinner_stopped = True
                                stream_printer.feed(event.delta.text)
                            elif hasattr(event.delta, "thinking"):
                                # Anthropic extended thinking block
                                if not spinner_stopped:
                                    spinner.stop()
                                    spinner_stopped = True
                                stream_printer.feed(event.delta.thinking, thinking=True)

                    if kind == "done":
                        if not spinner_stopped:
                            spinner.stop()
                        stream_printer.finish()
                        response = data
                        done = True
                        break

                if done:
                    break

            if response is None:
                return

            # Start a processing spinner to cover the gap between
            # streaming end and tool execution (or return)
            proc_spinner = Spinner(msg="Processing")
            proc_spinner.start()

            # Check for interrupt after stream completed
            if _check_interrupted():
                proc_spinner.stop()
                assistant_content = response.content
                self.messages.append({"role": "assistant", "content": assistant_content})
                tool_results = [
                    {"type": "tool_result", "tool_use_id": b.id, "content": "⚠ User interrupted, this tool was not executed"}
                    for b in assistant_content if b.type == "tool_use"
                ]
                if tool_results:
                    self.messages.append({"role": "user", "content": tool_results})
                return

            assistant_content = response.content
            self.messages.append({"role": "assistant", "content": assistant_content})

            # Handle tool calls (text already printed via streaming)
            has_tool_use = any(b.type == "tool_use" for b in assistant_content)
            if not has_tool_use:
                proc_spinner.stop()

            tool_results = []
            interrupted = False
            for block in assistant_content:
                if block.type == "tool_use":
                    # Stop processing spinner before first tool spinner
                    if not proc_spinner._stop.is_set():
                        proc_spinner.stop()
                    if interrupted:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "⚠ User interrupted, this tool was not executed",
                        })
                        continue
                    if _check_interrupted():
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "⚠ User interrupted, this tool was not executed",
                        })
                        interrupted = True
                        continue
                    _print_tool_call(block.name)
                    # Show spinner during tool execution
                    tool_spinner = Spinner(msg=_tool_label(block.name))
                    tool_spinner.start()
                    _tool_result = [None, None]
                    def _run_tool(_name=block.name, _inp=block.input):
                        try:
                            _tool_result[0] = self.handle_tool(_name, _inp)
                        except Exception as exc:
                            _tool_result[1] = exc
                    tool_thread = threading.Thread(target=_run_tool, daemon=True)
                    tool_thread.start()
                    while tool_thread.is_alive():
                        if _check_interrupted():
                            interrupted = True
                            break
                        tool_thread.join(timeout=0.2)
                    tool_spinner.stop()
                    if interrupted:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "⚠ User interrupted this operation",
                        })
                        continue
                    _print_tool_done()
                    if _tool_result[1] is not None:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Tool execution error: {_tool_result[1]}",
                        })
                    else:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": _tool_result[0],
                        })

            if interrupted:
                self._current_role = _DEFAULT_ROLE
                self.messages.append({"role": "user", "content": tool_results})
                self.messages.append({"role": "user", "content": (
                    "⚠ User interrupted the current workflow. "
                    "Please respond as the director, stop the current operation, and wait for the user's next instructions. Do not continue the previous workflow."
                )})
                return

            if response.stop_reason == "tool_use" and tool_results:
                self.messages.append({"role": "user", "content": tool_results})
                continue

            break

    # ── Conversation engine — OpenAI protocol ────────────────────

    def _send_openai(self, user_content: str | list | None, *, watcher: InputWatcher | None = None):
        """OpenAI chat completions loop with streaming (OpenAI, Moonshot, Doubao, Qwen, MiniMax)."""
        if user_content is not None:
            self.messages.append({"role": "user", "content": user_content})

        # Ensure system message is first
        if not self.messages or self.messages[0].get("role") != "system":
            self.messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

        def _check_interrupted():
            return (watcher and watcher.interrupted)

        while True:
            spinner = Spinner(msg=f"{self._current_role[1]} thinking")
            spinner.start()

            # Stream chunks into a queue from daemon thread
            event_q: queue.Queue = queue.Queue()
            def _do_stream():
                try:
                    stream = self.client.chat.completions.create(
                        model=self.model,
                        messages=self.messages,
                        tools=TOOLS_OPENAI,
                        max_tokens=MAX_LLM_TOKENS,
                        stream=True,
                    )
                    for chunk in stream:
                        event_q.put(("chunk", chunk))
                    event_q.put(("end", None))
                except Exception as exc:
                    event_q.put(("error", exc))

            api_thread = threading.Thread(target=_do_stream, daemon=True)
            api_thread.start()

            # Consume stream, accumulating the full response
            spinner_stopped = False
            stream_printer = _StreamPrinter(self._current_role)
            full_content = ""
            tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments}
            finish_reason = None

            while True:
                if _check_interrupted():
                    if not spinner_stopped:
                        spinner.stop()
                    stream_printer.finish()
                    if self.messages and self.messages[-1].get("role") == "user":
                        self.messages.pop()
                    return

                # Drain all available events (batch processing for lower latency)
                events = []
                try:
                    events.append(event_q.get(timeout=0.02))
                    while True:
                        events.append(event_q.get_nowait())
                except queue.Empty:
                    pass
                if not events:
                    continue

                done = False
                for kind, data in events:
                    if kind == "error":
                        if not spinner_stopped:
                            spinner.stop()
                        stream_printer.finish()
                        print(f"\n{Colors.RED}  API call failed: {data}{Colors.ENDC}")
                        return

                    if kind == "chunk":
                        chunk = data
                        if not chunk.choices:
                            continue
                        choice = chunk.choices[0]
                        delta = choice.delta

                        if delta and delta.content:
                            if not spinner_stopped:
                                spinner.stop()
                                spinner_stopped = True
                            full_content += delta.content
                            stream_printer.feed(delta.content)

                        if delta and delta.tool_calls:
                            for tc_delta in delta.tool_calls:
                                idx = tc_delta.index
                                if idx not in tool_calls_acc:
                                    tool_calls_acc[idx] = {
                                        "id": tc_delta.id or "",
                                        "name": (tc_delta.function.name if tc_delta.function and tc_delta.function.name else ""),
                                        "arguments": "",
                                    }
                                else:
                                    if tc_delta.id:
                                        tool_calls_acc[idx]["id"] = tc_delta.id
                                    if tc_delta.function and tc_delta.function.name:
                                        tool_calls_acc[idx]["name"] = tc_delta.function.name
                                if tc_delta.function and tc_delta.function.arguments:
                                    tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

                        if choice.finish_reason:
                            finish_reason = choice.finish_reason

                    if kind == "end":
                        if not spinner_stopped:
                            spinner.stop()
                        stream_printer.finish()
                        done = True
                        break

                if done:
                    break

            # Start a processing spinner to cover the gap between
            # streaming end and tool execution (or return)
            proc_spinner = Spinner(msg="Processing")
            proc_spinner.start()

            # Build assistant message for history
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if full_content:
                assistant_msg["content"] = full_content
            tool_calls_list = []
            if tool_calls_acc:
                for idx in sorted(tool_calls_acc):
                    tc = tool_calls_acc[idx]
                    tool_calls_list.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    })
                assistant_msg["tool_calls"] = tool_calls_list
            self.messages.append(assistant_msg)

            # Check for interrupt after stream
            if _check_interrupted():
                proc_spinner.stop()
                for tc in tool_calls_list:
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": "⚠ User interrupted, this tool was not executed",
                    })
                return

            # Handle tool calls
            if tool_calls_list:
                interrupted = False
                for tc in tool_calls_list:
                    # Stop processing spinner before first tool spinner
                    if not proc_spinner._stop.is_set():
                        proc_spinner.stop()
                    if interrupted:
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": "⚠ User interrupted, this tool was not executed",
                        })
                        continue
                    if _check_interrupted():
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": "⚠ User interrupted, this tool was not executed",
                        })
                        interrupted = True
                        continue
                    _print_tool_call(tc["function"]["name"])
                    # Show spinner during tool execution
                    tool_spinner = Spinner(msg=_tool_label(tc["function"]["name"]))
                    tool_spinner.start()
                    try:
                        tool_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}
                    _tool_result = [None, None]
                    def _run_tool(_name=tc["function"]["name"], _args=tool_args):
                        try:
                            _tool_result[0] = self.handle_tool(_name, _args)
                        except Exception as exc:
                            _tool_result[1] = exc
                    tool_thread = threading.Thread(target=_run_tool, daemon=True)
                    tool_thread.start()
                    while tool_thread.is_alive():
                        if _check_interrupted():
                            interrupted = True
                            break
                        tool_thread.join(timeout=0.2)
                    tool_spinner.stop()
                    if interrupted:
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": "⚠ User interrupted this operation",
                        })
                        continue
                    _print_tool_done()
                    if _tool_result[1] is not None:
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": f"Tool execution error: {_tool_result[1]}",
                        })
                    else:
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": _tool_result[0],
                        })

                if interrupted:
                    self._current_role = _DEFAULT_ROLE
                    self.messages.append({"role": "user", "content": (
                        "⚠ User interrupted the current workflow. "
                        "Please respond as the director, stop the current operation, and wait for the user's next instructions. Do not continue the previous workflow."
                    )})
                    return

                continue

            # No tool calls — stop processing spinner and return
            proc_spinner.stop()
            break

    # ── Unified send_message ─────────────────────────────────────

    def send_message(self, user_content: str | list | None = None, watcher: InputWatcher | None = None):
        """Send a message using the appropriate protocol."""
        if self.protocol == "anthropic":
            self._send_anthropic(user_content, watcher=watcher)
        else:
            self._send_openai(user_content, watcher=watcher)

    # ── Project management ───────────────────────────────────────

    def _detect_stage(self) -> list[str]:
        """Detect existing files to determine project stage."""
        if not self.project_dir:
            return []
        files = []
        for fname in ["screenplay.yaml", "storyboard.yaml", "prompts.json", "review.yaml"]:
            if (self.project_dir / fname).exists():
                files.append(fname)
                if fname not in self.saved_files:
                    self.saved_files.append(fname)
        return files

    @staticmethod
    def get_project_name() -> str:
        """Get project name from user input."""
        while True:
            raw = _split_terminal.read_input(
                prompt=f"  {Colors.DIM}Project name:{Colors.ENDC} "
            )
            if not raw:
                print(f"  {Colors.RED}Project name cannot be empty{Colors.ENDC}")
                continue
            name = re.sub(r'[/\\:*?"<>|\x00-\x1f]+', '_', raw)
            name = re.sub(r'[\s_]+', '_', name).strip('_')
            if name:
                return name
            print(f"  {Colors.RED}Name contains invalid characters, please re-enter{Colors.ENDC}")

    def save_metadata(self):
        """Save project metadata."""
        if not self.project_dir:
            return
        metadata = {
            "name": self.project_name,
            "created": datetime.now().isoformat(),
            "provider": self.config.llm.provider,
            "model": self.model,
            "files": self.saved_files,
            "assets": self.generated_assets,
            "format": "v1",
        }
        meta_path = self.project_dir / "_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    # ── Slash commands ─────────────────────────────────────────────

    def _handle_slash_command(self, raw_input: str) -> str | None:
        """Handle slash commands. Returns 'quit', 'handled', or None (fall through)."""
        parts = raw_input.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        handlers = {
            "/int": lambda: self._cmd_interrupt(arg),
            "/new": lambda: self._cmd_new(),
            "/resume": lambda: self._cmd_resume(arg),
            "/status": lambda: self._cmd_status(),
            "/list": lambda: self._cmd_list(),
            "/login": lambda: self._cmd_login(arg),
            "/learn": lambda: self._cmd_learn(arg),
            "/help": lambda: self._cmd_help(),
            "/quit": lambda: "quit",
            "/exit": lambda: "quit",
            "/q": lambda: "quit",
        }

        handler = handlers.get(cmd)
        if handler:
            return handler()

        print(f"  {Colors.YELLOW}Unknown command: {cmd}{Colors.ENDC}")
        print(f"  {Colors.DIM}Type /help to see available commands{Colors.ENDC}")
        return "handled"

    def _require_project(self) -> bool:
        """Check if a project is active. Print hint if not."""
        if self.project_name:
            return True
        print(f"  {Colors.YELLOW}No project is open{Colors.ENDC}")
        print(f"  {Colors.DIM}Use /new to create a new project or /resume to open an existing one{Colors.ENDC}")
        return False

    def _cmd_interrupt(self, arg: str) -> str:
        """Interrupt current workflow, optionally with new instructions."""
        if not self._require_project():
            return "handled"
        # Reset to director role
        self._current_role = _DEFAULT_ROLE
        if arg:
            msg = (
                "⚠ User interrupted the current workflow.\n"
                f"User's new request: {arg}\n"
                "Please respond as the director, execute the user's new request, do not continue the previous workflow."
            )
        else:
            msg = (
                "⚠ User interrupted the current workflow. "
                "Please respond as the director, stop the current operation, and wait for the user's next instructions. Do not continue the previous workflow."
            )
        print(f"  {Colors.YELLOW}⏸ Current workflow interrupted{Colors.ENDC}")
        self._send_with_watcher(msg)
        return "handled"

    def _cmd_new(self) -> str:
        """Save current project and start a new one."""
        if self.project_name:
            self.save_metadata()
            print(f"  {Colors.CYAN}Current project '{self.project_name}' saved{Colors.ENDC}")

        try:
            new_name = self.get_project_name()
        except (KeyboardInterrupt, EOFError):
            print()
            return "handled"

        self._reset_project(new_name)
        self._enter_project()
        return "handled"

    def _cmd_resume(self, arg: str) -> str:
        """Save current project and switch to another."""
        if not arg:
            self._cmd_list()
            try:
                arg = _split_terminal.read_input(
                    prompt=f"  {Colors.DIM}Project name:{Colors.ENDC} "
                )
            except (KeyboardInterrupt, EOFError):
                print()
                return "handled"
            if not arg:
                return "handled"

        # Support selecting by number
        if arg.isdigit():
            projects = self._list_project_names()
            idx = int(arg) - 1
            if 0 <= idx < len(projects):
                arg = projects[idx]
            else:
                print(f"  {Colors.RED}Number out of range{Colors.ENDC}")
                return "handled"

        project_path = PROJECTS_DIR / arg
        if not project_path.is_dir():
            print(f"  {Colors.RED}Project '{arg}' does not exist{Colors.ENDC}")
            return "handled"

        if arg == self.project_name:
            print(f"  {Colors.DIM}Already in current project{Colors.ENDC}")
            return "handled"

        if self.project_name:
            self.save_metadata()
            print(f"  {Colors.CYAN}Current project '{self.project_name}' saved{Colors.ENDC}")

        self._reset_project(arg)
        self._enter_project()
        return "handled"

    def _cmd_login(self, arg: str) -> str:
        """Log in to a platform for research."""
        platform = arg or "douyin"
        print(f"  {Colors.CYAN}Starting {platform} login...{Colors.ENDC}")
        try:
            import asyncio
            from core.browser.playwright import PlaywrightBrowser

            async def do_login():
                browser = PlaywrightBrowser()
                try:
                    success = await browser.ensure_logged_in(platform)
                    if success:
                        print(f"  {Colors.GREEN}✓ Login successful{Colors.ENDC}")
                    else:
                        print(f"  {Colors.YELLOW}Login incomplete, please retry /login {platform}{Colors.ENDC}")
                finally:
                    await browser.close()

            asyncio.run(do_login())
        except ImportError as e:
            print(f"  {Colors.RED}Missing dependency: {e}{Colors.ENDC}")
            print(f"  {Colors.YELLOW}Please run: pip install playwright && playwright install chromium{Colors.ENDC}")
        except Exception as e:
            print(f"  {Colors.RED}Login failed: {e}{Colors.ENDC}")
        return "handled"

    _LEARN_PLATFORMS = {"douyin", "bilibili", "xiaohongshu", "youtube"}

    def _cmd_learn(self, arg: str) -> str:
        """Search and analyze trending videos with VLM + LLM report."""
        if not arg:
            print(f"  {Colors.YELLOW}Usage: /learn <keyword> [platform]{Colors.ENDC}")
            print(f"  {Colors.DIM}e.g.: /learn food vlog{Colors.ENDC}")
            print(f"  {Colors.DIM}      /learn AI short film bilibili{Colors.ENDC}")
            print(f"  {Colors.DIM}Platforms: douyin(default) bilibili xiaohongshu youtube{Colors.ENDC}")
            return "handled"

        # Ensure a project exists so report can be saved
        if not self._ensure_project():
            return "handled"

        # Parse: last word may be a platform name
        parts = arg.rsplit(None, 1)
        if len(parts) == 2 and parts[1].lower() in self._LEARN_PLATFORMS:
            query, platform = parts[0], parts[1].lower()
        else:
            query, platform = arg, "douyin"

        try:
            from .researcher import VideoResearcher
            researcher = VideoResearcher(config=self.config)
            report = researcher.run(
                query=query,
                platform=platform,
                project_dir=self.project_dir,
            )
            # Inject report summary into conversation context for follow-up
            if report:
                summary = report[:2000] if len(report) > 2000 else report
                self.messages.append({
                    "role": "user" if self.protocol == "anthropic" else "system",
                    "content": (
                        f"[System] The user just researched trending videos for '{query}' ({platform}) via the /learn command. "
                        f"Here is a summary of the research report for creative reference:\n\n{summary}"
                    ),
                })
        except ImportError as e:
            print(f"  {Colors.RED}Missing dependency: {e}{Colors.ENDC}")
            print(f"  {Colors.YELLOW}Please run: pip install playwright && playwright install chromium{Colors.ENDC}")
        except Exception as e:
            print(f"  {Colors.RED}Search failed: {e}{Colors.ENDC}")
        return "handled"

    def _cmd_status(self) -> str:
        """Show current project status."""
        if not self._require_project():
            return "handled"
        print(f"\n  {Colors.BOLD}{Colors.CYAN}{self.project_name}{Colors.ENDC}")
        existing = self._detect_stage()
        if existing:
            print(f"  {Colors.DIM}Files: {', '.join(existing)}{Colors.ENDC}")
        else:
            print(f"  {Colors.DIM}No files yet{Colors.ENDC}")

        images_dir = self.project_dir / "assets" / "images"
        videos_dir = self.project_dir / "assets" / "videos"
        refs_dir = self.project_dir / "assets" / "references"

        imgs = list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpg")) if images_dir.is_dir() else []
        vids = list(videos_dir.glob("*.mp4")) if videos_dir.is_dir() else []
        refs = list(refs_dir.glob("*.png")) + list(refs_dir.glob("*.jpg")) if refs_dir.is_dir() else []

        if imgs or vids or refs:
            parts = []
            if refs:
                parts.append(f"{len(refs)} reference(s)")
            if imgs:
                parts.append(f"{len(imgs)} image(s)")
            if vids:
                parts.append(f"{len(vids)} video(s)")
            print(f"  {Colors.DIM}Assets: {' | '.join(parts)}{Colors.ENDC}")

        if (self.project_dir / "output" / "final.mp4").exists():
            print(f"  {Colors.GREEN}✓ Final video exported{Colors.ENDC}")
        print()
        return "handled"

    def _cmd_list(self) -> str:
        """List all projects."""
        projects = self._list_project_names()

        if not projects:
            print(f"  {Colors.YELLOW}No other projects{Colors.ENDC}")
            return "handled"

        print(f"\n  {Colors.BOLD}{Colors.CYAN}Project list:{Colors.ENDC}")
        for i, name in enumerate(projects, 1):
            marker = f" {Colors.GREEN}← current{Colors.ENDC}" if name == self.project_name else ""
            print(f"    {i}. {Colors.BOLD}{name}{Colors.ENDC}{marker}")
        print()
        return "handled"

    def _cmd_help(self) -> str:
        """Show available slash commands."""
        B = Colors.BOLD
        D = Colors.DIM
        E = Colors.ENDC
        print(f"\n  {B}{Colors.CYAN}Available commands:{E}\n")
        cmds = [
            ("/int [instruction]", "Interrupt current workflow, optionally with new instructions"),
            ("/new", "Save current project and start a new one"),
            ("/resume [name]", "Switch to another project"),
            ("/status", "View current project status"),
            ("/list", "List all projects"),
            ("/login [platform]", "Login to a platform (default: douyin)"),
            ("/learn <keyword> [platform]", "Search and analyze trending videos"),
            ("/help", "Show help"),
            ("/quit", "Save and exit"),
        ]
        col = max(len(c) for c, _ in cmds) + 2
        for cmd, desc in cmds:
            print(f"    {B}{cmd:<{col}}{E} {D}{desc}{E}")
            if cmd.startswith("/learn"):
                print(f"    {D}{'':<{col}} Platforms: douyin bilibili xiaohongshu youtube{E}")
        print(f"\n  {D}Press Enter = let the director freestyle | Supports reference image/video paths{E}\n")
        return "handled"

    def _reset_project(self, new_name: str):
        """Reset project state for switching to a new/different project."""
        self.project_name = new_name
        self.project_dir = PROJECTS_DIR / new_name
        self.messages = []
        self.saved_files = []
        self.generated_assets = []
        self._review_passed = False
        self._current_role = _DEFAULT_ROLE

    def _setup_project_dirs(self):
        """Create standard project directory structure."""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        for sub in [
            "assets/images", "assets/videos", "assets/references",
            "assets/references/user", "assets/audio", "output",
        ]:
            (self.project_dir / sub).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _list_project_names() -> list[str]:
        """List all project directory names, sorted by modification time."""
        if not PROJECTS_DIR.is_dir():
            return []
        dirs = [
            d for d in PROJECTS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        return [d.name for d in dirs]

    # ── Main loop ────────────────────────────────────────────────

    def _enter_project(self) -> bool:
        """Set up the current project and send initial message to LLM.

        Returns True if completed normally, False if user interrupted.
        """
        self._setup_project_dirs()
        existing = self._detect_stage()

        # Update footer with project info
        _split_terminal.update_footer(
            f"{self.project_name} | {self.config.llm.provider}/{self.model}"
        )

        print(f"\n  {Colors.GREEN}Project{Colors.ENDC}  {Colors.BOLD}{self.project_name}{Colors.ENDC}")
        _print_divider("─")

        if existing:
            interrupted = self._send_with_watcher(
                f"Resuming project '{self.project_name}'. Existing files: {', '.join(existing)}. "
                "Please inform the user of the current progress and ask what they'd like to do."
            )
        else:
            interrupted = self._send_with_watcher(
                f"Starting new project '{self.project_name}'. Please greet the user and learn what kind of video they want to create."
            )
        return not interrupted

    def _ensure_project(self) -> bool:
        """Make sure a project is active. Returns False if user cancelled or interrupted."""
        if self.project_name:
            return True

        projects = self._list_project_names()
        D = Colors.DIM
        B = Colors.BOLD
        E = Colors.ENDC

        if projects:
            # Show existing projects for selection
            print(f"\n  {Colors.CYAN}Select project (enter number or new name):{E}")
            for i, name in enumerate(projects[:8], 1):
                print(f"    {D}{i}.{E} {name}")
            print(f"    {D}Or enter a new project name{E}")
        else:
            print(f"\n  {Colors.CYAN}Enter project name to begin:{E}")

        try:
            raw = _split_terminal.read_input(
                prompt=f"  {D}Project:{E} "
            )
        except (KeyboardInterrupt, EOFError):
            print()
            return False

        if not raw:
            return False

        # Check if user entered a number to select existing project
        if projects and raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(projects[:8]):
                self._reset_project(projects[idx])
                if not self._enter_project():
                    return False  # interrupted during initial greeting
                return True

        # Sanitize as new project name
        name = re.sub(r'[/\\:*?"<>|\x00-\x1f]+', '_', raw)
        name = re.sub(r'[\s_]+', '_', name).strip('_')
        if not name:
            print(f"  {Colors.RED}Invalid project name{E}")
            return False

        self._reset_project(name)
        if not self._enter_project():
            return False  # interrupted during initial greeting
        return True

    def _send_with_watcher(self, content) -> bool:
        """Send message with InputWatcher for interrupt support.

        Assumes split terminal is already active (persistent mode).
        Returns True if the user interrupted during execution.
        """
        watcher = InputWatcher()
        watcher.start()
        try:
            self.send_message(content, watcher=watcher)
        finally:
            captured = watcher.stop()
        if captured is not None:
            self._pending_input = captured if captured and captured != "/int" else None
            self._current_role = _DEFAULT_ROLE
            print(f"  {Colors.DIM}Current workflow interrupted{Colors.ENDC}")
            return True
        return False

    def _send_user_input(self, user_input: str):
        """Process user input (text + possible file attachments) and send to LLM."""
        text_content, detected_files = _parse_user_input(user_input)

        if not detected_files:
            self._send_with_watcher(user_input)
            return

        # Show detected files
        print(f"  {Colors.CYAN}Detected {len(detected_files)} reference file(s):{Colors.ENDC}")
        for df in detected_files:
            icon = "🖼️" if df["type"] == "image" else "🎬"
            print(f"    {icon}  {df['path'].name}")

        processed = _process_reference_files(detected_files, self.project_dir)

        if not processed:
            print(f"  {Colors.YELLOW}Reference file processing failed, sending text only{Colors.ENDC}")
            self._send_with_watcher(user_input)
            return

        video_count = sum(1 for df in detected_files if df["type"] == "video")
        if video_count:
            print(f"  {Colors.DIM}Video keyframes extracted{Colors.ENDC}")
        print(f"  {Colors.DIM}Reference files saved to assets/references/user/{Colors.ENDC}")

        msg_text = text_content.strip() or "Please analyze these reference materials and share your understanding."
        if self.protocol == "anthropic":
            content = _build_multimodal_anthropic(msg_text, processed)
        else:
            content = _build_multimodal_openai(msg_text, processed)

        self._send_with_watcher(content)

    def run(self):
        bold_yellow = f"{Colors.BOLD}{Colors.YELLOW}"
        end = Colors.ENDC
        dim = Colors.DIM

        # ── ASCII banner (matches install.sh) ──
        print()
        print(f"{bold_yellow}"
              f"  ████████╗ █████╗ ██╗  ██╗ ██████╗ ███╗   ██╗███████╗\n"
              f"  ╚══██╔══╝██╔══██╗██║ ██╔╝██╔═══██╗████╗  ██║██╔════╝\n"
              f"     ██║   ███████║█████╔╝ ██║   ██║██╔██╗ ██║█████╗\n"
              f"     ██║   ██╔══██║██╔═██╗ ██║   ██║██║╚██╗██║██╔══╝\n"
              f"     ██║   ██║  ██║██║  ██╗╚██████╔╝██║ ╚████║███████╗\n"
              f"     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝"
              f"{end}")
        print(f"  {dim}AI Video Creation Agent — from concept to export{end}")
        print()
        print(f"  {dim}{self.config.llm.provider} / {self.model}{end}")
        print(f"  {dim}Type /help to see all commands{end}")
        print()

        # Enter persistent split terminal (inline bottom decoration)
        footer_text = f"Director | {self.config.llm.provider}/{self.model}"
        _split_terminal.enter(footer_text=footer_text)
        try:
            # If project_name was given via CLI arg, enter it directly
            if self.project_name:
                self.project_dir = PROJECTS_DIR / self.project_name
                self._enter_project()
            # Interactive loop
            while True:
                # Check for pending input captured during model execution
                if self._pending_input is not None:
                    user_input = self._pending_input
                    self._pending_input = None
                else:
                    try:
                        user_input = _split_terminal.read_input()
                    except (KeyboardInterrupt, EOFError):
                        print(f"\n  {Colors.CYAN}Saving progress...{Colors.ENDC}")
                        break

                # Echo user input with charcoal background
                cols = _term_width()
                user_line = f"  {user_input}"
                # Charcoal bg (#2B2F36 ≈ 236), cream text (#F3EEE0 ≈ 223)
                # Use visual padding to handle CJK double-width characters
                padded = _visual_pad(user_line, cols)
                print()
                print(f"\033[48;5;236m\033[38;5;223m{padded}\033[0m")
                print()

                if user_input.lower() in ("exit", "quit", "q"):
                    break

                # Slash commands (always available, even without a project)
                if user_input.startswith("/"):
                    result = self._handle_slash_command(user_input)
                    if result == "quit":
                        break
                    if result == "handled":
                        continue

                # Empty input
                if not user_input:
                    if not self.project_name:
                        continue  # No project yet — do nothing on empty Enter
                    self._send_with_watcher("Continue, you decide what to do next.")
                    continue

                # Normal message — make sure we have a project first
                if not self._ensure_project():
                    continue

                self._send_user_input(user_input)
        finally:
            _split_terminal.exit()

        if self.project_name:
            self.save_metadata()
        print()
        _print_divider("━")
        if self.saved_files:
            print(f"  {Colors.GREEN}Saved files:{Colors.ENDC}")
            for f in self.saved_files:
                print(f"    {Colors.DIM}{f}{Colors.ENDC}")
        if self.generated_assets:
            print(f"  {Colors.GREEN}Generated assets: {len(self.generated_assets)}{Colors.ENDC}")
        if self.project_dir:
            print(f"  {Colors.GREEN}Project data saved at: {self.project_dir}{Colors.ENDC}")
        _print_divider("━")
        print()


# ── Entry point ────────────────────────────────────────────────────────

def main():
    try:
        director = VideoDirector()
        director.run()
    except ValueError as e:
        _split_terminal.exit()  # ensure terminal is restored
        print(f"{Colors.RED}  {e}{Colors.ENDC}")
        sys.exit(1)
    except KeyboardInterrupt:
        _split_terminal.exit()  # ensure terminal is restored
        print(f"\n{Colors.YELLOW}  Interrupted{Colors.ENDC}\n")
        sys.exit(0)
    except Exception:
        _split_terminal.exit()  # ensure terminal is restored
        raise


if __name__ == "__main__":
    main()
