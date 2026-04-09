#!/usr/bin/env python3
"""
Takone — Model-driven conversational agent for AI video creation.

The model decides the workflow: script → storyboard → prompts → generation → review.
Skills are loaded on-demand via tool calls to minimize token usage.

Provider pattern:
  Anthropic protocol  →  Claude, MiniMax
  OpenAI protocol     →  OpenAI, Kimi, Zhipu/GLM, Moonshot, Doubao, Qwen
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
    Colors, SKILLS, PROJECTS_DIR, MEMORY_DIR,
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

# ── Murch Evaluation Prompt Template ──────────────────────────────────
# Sent to vision API when evaluate_shot is called.
# Based on Walter Murch's six editing priorities from "In the Blink of an Eye".
_MURCH_EVAL_PROMPT = """\
You are evaluating a shot as if you were a viewer scrolling through Douyin/TikTok.
Three dimensions, gut-first:

1. GUT REACTION (60%) — In the first second of seeing this, what do you FEEL? \
Is that the RIGHT feeling for this shot? Not "is it pretty" but "does it HIT right?" \
A technically beautiful shot with the wrong feeling scores LOW.

2. VISUAL DISTINCTION (25%) — Does this look like generic AI output you've seen \
1000 times? Or does it have something unexpected, something that stands out? \
AI content often has a samey quality — does this break through?

3. SEQUENCE FIT (15%) — Given the previous shots, does this create forward momentum? \
Does the viewer want to see what comes next? Or does the energy stall?

---
Evaluating: {shot_id} ({media_type})

WHAT THIS SHOT SHOULD FEEL LIKE:
{emotion_context}

WHAT THIS SHOT SHOULD DO IN THE STORY:
{story_context}

WHAT CAME BEFORE:
{context_description}
---

Score each dimension 1-10. Be brutally honest.

Then calculate WEIGHTED TOTAL using the percentages above.
VERDICT: PASS (weighted >= 7.0) or FAIL.

If FAIL, describe what FEELS wrong (not what's technically wrong):
- What's missing emotionally?
- Why would someone scroll past this?
- What specific change would make it compelling?

Format:
GUT_REACTION: [score]/10 — [what you felt in the first second]
VISUAL_DISTINCTION: [score]/10 — [generic or distinctive?]
SEQUENCE_FIT: [score]/10 — [momentum or stall?]
WEIGHTED: [score]/10
VERDICT: PASS or FAIL
ISSUES: [if FAIL, what feels wrong and how to fix it]
"""

from .tools import (
    IMAGE_EXTS, VIDEO_EXTS,
    _resolve_file_path, _parse_user_input, _process_reference_files,
    _build_multimodal_anthropic, _build_multimodal_openai,
    PROVIDER_REGISTRY, _resolve_llm_config,
    TOOLS_ANTHROPIC, _tools_to_openai, TOOLS_OPENAI,
    SYSTEM_PROMPT,
)
from .log import logger, setup_logging
from .transcript import ProjectLogger


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

        # Project-level conversation logger (initialized when project_dir is set)
        self._plog = None  # type: ProjectLogger | None

        # Lazy-init providers
        self._image_gen = None
        self._video_gen = None

        # Cache for system prompt with memory injected
        self._cached_system_prompt = None

        provider_name = self.config.llm.provider
        print(f"{Colors.DIM}  LLM: {provider_name} / {model}{Colors.ENDC}")

    # ── System prompt with memory injection ──────────────────────

    def _get_system_prompt(self) -> str:
        """Build system prompt with persistent memory auto-injected."""
        if self._cached_system_prompt:
            return self._cached_system_prompt

        memory_file = MEMORY_DIR / "MEMORY.md"
        if memory_file.exists():
            try:
                memory_content = memory_file.read_text(encoding="utf-8").strip()
                if memory_content:
                    # Inject first 200 lines of memory into system prompt
                    lines = memory_content.split("\n")[:200]
                    memory_block = "\n".join(lines)
                    self._cached_system_prompt = (
                        f"{SYSTEM_PROMPT}\n\n"
                        f"## User Memory (auto-loaded from ~/.takone/memory/MEMORY.md)\n\n"
                        f"{memory_block}"
                    )
                    print(f"{Colors.DIM}  [Memory] Auto-loaded MEMORY.md ({len(lines)} lines){Colors.ENDC}")
                    return self._cached_system_prompt
            except Exception:
                pass

        self._cached_system_prompt = SYSTEM_PROMPT
        return self._cached_system_prompt

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
            "evaluate_shot": self._tool_evaluate_shot,
            "compare_shots": self._tool_compare_shots,
            "validate_before_generate": self._tool_validate_before_generate,
            "search_reference": self._tool_search_reference,
            "learn_browse": self._tool_learn_browse,
            "learn_download": self._tool_learn_download,
            "list_assets": self._tool_list_assets,
            "assemble_video": self._tool_assemble_video,
            "add_audio_track": self._tool_add_audio_track,
            "memory_read": self._tool_memory_read,
            "memory_write": self._tool_memory_write,
        }
        handler = handlers.get(tool_name)
        if handler:
            return handler(tool_input)
        return f"Unknown tool: {tool_name}"

    # After saving key files, a simple creative gut-check reminder
    _REVIEW_HINTS = {
        "shots.yaml": (
            "\n\n💡 Quick gut-check: Read back what you just wrote. "
            "Would this make YOU stop scrolling on Douyin? If not, fix it before moving on."
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

    def _resolve_reference_image(self, rid: str):
        """Resolve reference image ID to file path.

        Searches assets/design/ first, then assets/learn/.
        Also supports relative paths like 'learn/style_sample.png'.
        """
        assets = self.project_dir / "assets"

        # Support relative path form (e.g., "learn/style_sample.png")
        if "/" in rid or "\\" in rid:
            p = assets / rid
            if p.exists():
                return p
            return None

        # Search by priority: design/ first, then learn/, then user/
        for directory in ["design", "learn", "user"]:
            for ext in [".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov"]:
                p = assets / directory / f"{rid}{ext}"
                if p.exists():
                    return p
            # Also try exact filename match (with extension already in rid)
            p = assets / directory / rid
            if p.exists():
                return p
        return None

    def _tool_generate_reference(self, args: dict) -> str:
        ref_type = args["ref_type"]
        ref_id = args["ref_id"]
        prompt = args["prompt"]
        aspect_ratio = args.get("aspect_ratio")
        reference_image_ids = args.get("reference_images", [])

        if not self.project_dir:
            return "Error: project directory not initialized"

        # aspect_ratio is now required in the tool schema — the LLM picks
        # the best ratio based on the number of sub-views.  Fallback only
        # for backwards-compat if somehow omitted.
        if not aspect_ratio:
            if ref_type == "character":
                aspect_ratio = "3:2"   # Reasonable default for 3-view sheets
            else:
                aspect_ratio = "9:16"  # Default project ratio for scenes

        # The prompt is used AS-IS from the LLM — no auto-appended suffixes.
        # The LLM (guided by designer skill) already crafts complete prompts
        # including style_anchor, view descriptions, and all necessary details.
        # Auto-appending caused prompt conflicts (e.g. "cinematic" + "white background")
        # and unnatural results. Trust the LLM's prompt.

        # Resolve reference images from learn/design/user assets
        ref_paths = []
        if reference_image_ids:
            missing_refs = []
            for rid in reference_image_ids:
                ref_path = self._resolve_reference_image(rid)
                if ref_path:
                    ref_paths.append(ref_path)
                    print(f"{Colors.DIM}  [Style ref] {ref_path.name}{Colors.ENDC}")
                else:
                    missing_refs.append(rid)
            if missing_refs:
                print(f"{Colors.YELLOW}  ⚠ Some style references not found: {missing_refs} (continuing without them){Colors.ENDC}")

        # Create image generator
        if not self._image_gen:
            from core.image.factory import create_image_gen

            self._image_gen = create_image_gen(self.config.image)

        try:
            refs_dir = self.project_dir / "assets" / "design"
            refs_dir.mkdir(parents=True, exist_ok=True)
            save_path = refs_dir / f"{ref_id}.png"

            if ref_paths:
                ref_names = [p.stem for p in ref_paths]
                print(f"{Colors.CYAN}  [Generating reference] {ref_type}/{ref_id} (style refs: {', '.join(ref_names)})...{Colors.ENDC}")
                images = asyncio.run(self._image_gen.image_to_image(
                    prompt=prompt,
                    reference_images=ref_paths,
                    aspect_ratio=aspect_ratio,
                ))
            else:
                print(f"{Colors.CYAN}  [Generating reference] {ref_type}/{ref_id}...{Colors.ENDC}")
                images = asyncio.run(self._image_gen.text_to_image(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                ))

            if images:
                images[0].save(save_path)
                self.generated_assets.append(str(save_path))
                ref_info = f" (with {len(ref_paths)} style references)" if ref_paths else ""
                print(f"{Colors.GREEN}  ✓ Reference image generated: {ref_id}.png{ref_info}{Colors.ENDC}")
                return f"Reference image saved: assets/design/{ref_id}.png{ref_info}"
            return f"Reference generation returned no results for {ref_id}"

        except Exception as e:
            print(f"{Colors.RED}  ✗ Reference generation failed {ref_id}: {e}{Colors.ENDC}")
            return f"Reference generation failed for {ref_id}: {e}"

    def _tool_compare_shots(self, args: dict) -> str:
        """Compare multiple variations of a shot and rank them by scroll-stop power."""
        shot_id = args["shot_id"]
        media_type = args.get("media_type", "image")
        reference_path = args.get("reference_path")

        # Find all variations
        ext = "png" if media_type == "image" else "mp4"
        subdir = "image" if media_type == "image" else "video"
        asset_dir = self.project_dir / "assets" / subdir

        variations = sorted(asset_dir.glob(f"{shot_id.lower()}_v*.{ext}"))
        # Also include the base file if it exists
        base_file = asset_dir / f"{shot_id.lower()}.{ext}"
        if base_file.exists() and base_file not in variations:
            variations.insert(0, base_file)

        if len(variations) < 2:
            return f"Need at least 2 variations to compare. Found {len(variations)} for {shot_id}. Generate more variations first."

        # Load vision model
        try:
            if not self._vision:
                from core.vision.factory import create_vision
                self._vision = create_vision(self.config)
        except Exception as e:
            return f"Vision model not available: {e}"

        # Build comparison prompt
        compare_prompt = (
            f"You are scrolling through Douyin/TikTok. You see these {len(variations)} versions of the same shot.\n\n"
            f"RANK them from best to worst based on:\n"
            f"1. Scroll-stop power — which one would make you STOP scrolling?\n"
            f"2. Emotional impact — which one HITS hardest?\n"
            f"3. Visual distinction — which one stands out from generic AI content?\n\n"
            f"For each, give a score (1-10) and one sentence explaining why.\n"
            f"End with: BEST: [filename] and explain what makes it the winner."
        )

        print(f"{Colors.CYAN}  [Comparing] {len(variations)} variations of {shot_id}...{Colors.ENDC}")

        try:
            # Send all variations to vision model
            image_paths = variations[:]
            if reference_path:
                ref = Path(reference_path)
                if ref.exists():
                    compare_prompt += f"\n\nAlso compare against this reference image (the target feeling)."
                    image_paths.append(ref)

            result = asyncio.run(self._vision.analyze_images(image_paths, compare_prompt))
            if result:
                print(f"{Colors.GREEN}  ✓ Comparison complete for {shot_id}{Colors.ENDC}")
                return f"## Shot Comparison: {shot_id}\n\nVariations compared: {', '.join(p.name for p in variations)}\n\n{result}"
            return f"Vision model returned no results for comparison"
        except Exception as e:
            # Fallback: analyze each individually
            try:
                results = []
                for vpath in variations:
                    r = asyncio.run(self._vision.analyze_image(
                        vpath,
                        f"Rate this image 1-10 for scroll-stop power on Douyin. "
                        f"Would you stop scrolling? What do you feel? One paragraph."
                    ))
                    if r:
                        results.append(f"**{vpath.name}**: {r}")
                if results:
                    print(f"{Colors.GREEN}  ✓ Individual analysis complete for {shot_id}{Colors.ENDC}")
                    return f"## Shot Comparison: {shot_id}\n\n" + "\n\n".join(results)
            except Exception as e2:
                pass
            return f"Comparison failed: {e}"

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
        variations = args.get("variations", 2)

        # If no prompt provided, try reading from shots.yaml first, then prompts.json
        prompts_data = None
        shots_data = None
        if not prompt:
            # Try shots.yaml (new format)
            shots_file = self.project_dir / "shots.yaml"
            if shots_file.exists():
                try:
                    with open(shots_file) as f:
                        shots_data = yaml.safe_load(f) or {}
                    for shot in shots_data.get("shots", []):
                        if shot.get("id") == shot_id:
                            prompt = shot.get("prompt", "")
                            break
                except Exception:
                    pass

            # Fall back to prompts.json (legacy format)
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
            return f"No prompt found for {shot_id}. Please provide a prompt or save shots.yaml/prompts.json first."

        # Auto-append style_anchor for global style consistency
        style_anchor = ""
        if shots_data:
            style_anchor = shots_data.get("style_anchor", "")
        elif prompts_data:
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

        # Fallback: inject character descriptions from shots.yaml characters[].visual
        # Only inject characters referenced in this shot's reference_images
        if shots_data and "[Character appearance:" not in prompt:
            # Get this shot's reference_images to know which characters are in frame
            shot_ref_ids = set()
            for shot in shots_data.get("shots", []):
                if shot.get("id") == shot_id:
                    shot_ref_ids = set(shot.get("reference_images", []))
                    break

            chars = shots_data.get("characters", [])
            char_descs = []
            for char in chars:
                char_id = char.get("id", "")
                # Only inject if this character is referenced in the shot
                if shot_ref_ids and char_id not in shot_ref_ids:
                    continue
                vis = char.get("visual", "")
                if vis and vis.strip()[:30].lower() not in prompt.lower():
                    char_descs.append(vis.strip())
            if char_descs:
                char_block = "; ".join(char_descs)
                prompt = f"[Character appearance: {char_block}] {prompt}"
                print(f"{Colors.DIM}  [Character lock] Injected {len(char_descs)} character description(s) from shots.yaml{Colors.ENDC}")

        # Load reference images from shots.yaml or prompts.json
        ref_paths = []
        ref_ids = []

        # Try shots.yaml first (new format)
        if shots_data:
            for shot in shots_data.get("shots", []):
                if shot.get("id") == shot_id:
                    ref_ids = shot.get("reference_images", [])
                    break

        # Fall back to prompts.json (legacy format)
        if not ref_ids:
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

        # Resolve reference IDs to file paths
        missing_refs = []
        for rid in ref_ids:
            ref_path = self._resolve_reference_image(rid)
            if ref_path:
                ref_paths.append(ref_path)
                if "learn" in str(ref_path):
                    print(f"{Colors.DIM}  [Learn ref] {ref_path.name}{Colors.ENDC}")
            else:
                missing_refs.append(rid)

        # Hard check: if reference_images are specified but files are missing, block generation
        if missing_refs:
            print(f"{Colors.RED}  ✗ Missing reference images: {missing_refs}{Colors.ENDC}")
            return (
                f"BLOCKED: Reference images not found for: {missing_refs}. "
                f"You MUST call generate_reference() for each missing character/scene "
                f"before generating shots. Character consistency requires reference images — "
                f"text-only fallback is not allowed when reference_images are specified.\n\n"
                f"For each missing reference, call:\n"
                + "\n".join(
                    f"  generate_reference(ref_type=\"character\", ref_id=\"{rid}\", "
                    f"prompt=\"<detailed prompt with style_anchor>\", aspect_ratio=\"3:2\")"
                    for rid in missing_refs
                )
            )

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
                        prev_keyframe = self.project_dir / "assets" / "image" / f"{prev_shot_id.lower()}.png"
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
            saved_paths = []
            for vi in range(variations):
                suffix = f"_v{vi+1}" if variations > 1 else ""
                label = f" (variation {vi+1}/{variations})" if variations > 1 else ""

                if ref_paths:
                    ref_names = [p.stem for p in ref_paths]
                    print(f"{Colors.CYAN}  [Generating image] {shot_id}{label} (refs: {', '.join(ref_names)})...{Colors.ENDC}")
                    images = asyncio.run(self._image_gen.image_to_image(
                        prompt=prompt,
                        reference_images=ref_paths,
                        aspect_ratio=aspect_ratio,
                    ))
                else:
                    print(f"{Colors.CYAN}  [Generating image] {shot_id}{label}...{Colors.ENDC}")
                    images = asyncio.run(self._image_gen.text_to_image(
                        prompt=prompt,
                        aspect_ratio=aspect_ratio,
                    ))

                if images:
                    save_path = self.project_dir / "assets" / "image" / f"{shot_id.lower()}{suffix}.png"
                    images[0].save(save_path)
                    self.generated_assets.append(str(save_path))
                    saved_paths.append(save_path)

                    # Check for fallback warning (reference images failed)
                    fallback_warn = getattr(images[0], 'fallback_warning', None)
                    if fallback_warn:
                        print(f"{Colors.YELLOW}  ⚠ {shot_id}{suffix} reference images not applied, fell back to text-only{Colors.ENDC}")

                    print(f"{Colors.GREEN}  ✓ {shot_id}{suffix} keyframe generated{Colors.ENDC}")

            if not saved_paths:
                return f"Image generation returned no results for {shot_id}"

            ref_info = f" (with {len(ref_paths)} reference images)" if ref_paths else ""
            if variations > 1:
                names = [p.name for p in saved_paths]
                result_msg = (
                    f"Generated {len(saved_paths)} variations: {', '.join(names)}{ref_info}\n\n"
                    f"**Next step:** Use compare_shots(shot_id=\"{shot_id}\") to select the best variation."
                )
            else:
                result_msg = f"Image saved: {saved_paths[0].name}{ref_info}"

            # Auto-continuity check with previous shot (only for single generation or first variation)
            if prev_shot_id and len(saved_paths) == 1:
                prev_keyframe = self.project_dir / "assets" / "image" / f"{prev_shot_id.lower()}.png"
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
                        pass

            return result_msg

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

        # Try reading from shots.yaml first, then prompts.json
        prompts_data = None
        shots_data = None

        if not prompt:
            # Try shots.yaml (new format)
            shots_file = self.project_dir / "shots.yaml"
            if shots_file.exists():
                try:
                    with open(shots_file) as f:
                        shots_data = yaml.safe_load(f) or {}
                    for shot in shots_data.get("shots", []):
                        if shot.get("id") == shot_id:
                            prompt = shot.get("video_prompt", "")
                            duration = shot.get("duration", duration)
                            break
                except Exception:
                    pass

            # Fall back to prompts.json (legacy format)
            if not prompt:
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

        # Auto-append style_anchor
        style_anchor = ""
        if shots_data:
            style_anchor = shots_data.get("style_anchor", "")
        elif prompts_data:
            style_anchor = prompts_data.get("style_anchor", "")
        if style_anchor and prompt and style_anchor.lower() not in prompt.lower():
            prompt = f"{prompt}, {style_anchor}"

        if not prompt:
            return f"No prompt found for {shot_id}. Please provide a prompt or save shots.yaml/prompts.json first."

        # Create video generator
        if not self._video_gen:
            from core.video.factory import create_video_gen

            self._video_gen = create_video_gen(self.config.video)

        try:
            # Check for first frame image (fallback to _v1 variation if base not found)
            first_frame = self.project_dir / "assets" / "image" / f"{shot_id.lower()}.png"
            if not first_frame.exists():
                v1 = self.project_dir / "assets" / "image" / f"{shot_id.lower()}_v1.png"
                if v1.exists():
                    first_frame = v1
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
                save_path = self.project_dir / "assets" / "video" / f"{shot_id.lower()}.mp4"
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

        img_a = self.project_dir / "assets" / "image" / f"{shot_id_a.lower()}.png"
        img_b = self.project_dir / "assets" / "image" / f"{shot_id_b.lower()}.png"

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

    def _tool_evaluate_shot(self, args: dict) -> str:
        """Evaluate a shot using Walter Murch's editing priorities via vision API."""
        shot_id = args["shot_id"]
        media_type = args.get("media_type", "image")
        context_shot_ids = args.get("context_shot_ids", [])
        emotion_context = args.get("emotion_context", "")
        story_context = args.get("story_context", "")

        if not self.project_dir:
            return "Error: project directory not initialized"

        # Resolve current shot file
        if media_type == "video":
            current_file = self.project_dir / "assets" / "video" / f"{shot_id.lower()}.mp4"
        else:
            current_file = self.project_dir / "assets" / "image" / f"{shot_id.lower()}.png"

        if not current_file.exists():
            return f"{media_type.capitalize()} not found for {shot_id}. Generate it first."

        # Auto-fill emotion_context and story_context from shots.yaml or storyboard.yaml
        if not emotion_context or not story_context:
            shot_entry = None

            # Try shots.yaml first (new format)
            shots_file = self.project_dir / "shots.yaml"
            if shots_file.exists():
                try:
                    with open(shots_file) as f:
                        shots_yaml = yaml.safe_load(f) or {}
                    for s in shots_yaml.get("shots", []):
                        if s.get("id", "").upper() == shot_id.upper():
                            shot_entry = s
                            break
                    if shot_entry:
                        if not emotion_context:
                            feeling = shot_entry.get("feeling", "not specified")
                            emotion_context = f"Target feeling: {feeling}."
                        if not story_context:
                            story_context = f"Shot feeling: {shot_entry.get('feeling', 'not specified')}."
                except Exception:
                    pass

            # Fall back to storyboard.yaml (legacy format)
            if not shot_entry:
                storyboard_file = self.project_dir / "storyboard.yaml"
                if storyboard_file.exists():
                    try:
                        with open(storyboard_file) as f:
                            storyboard = yaml.safe_load(f)
                        for s in storyboard.get("shots", []):
                            if s.get("id", "").upper() == shot_id.upper():
                                shot_entry = s
                                break
                        if shot_entry:
                            if not emotion_context:
                                intent = shot_entry.get("cinematic_intent", "not specified")
                                intensity = shot_entry.get("emotional_intensity", "?")
                                breathing = shot_entry.get("breathing", "?")
                                emotion_context = (
                                    f"Cinematic intent: {intent}. "
                                    f"Emotional intensity: {intensity}/10. "
                                    f"Breathing: {breathing}."
                                )
                            if not story_context:
                                beat_ref = shot_entry.get("beat_ref", "not specified")
                                story_context = f"Narrative beat: {beat_ref}."
                    except Exception:
                        pass

        if not emotion_context:
            emotion_context = "Not provided — judge based on visual impression."
        if not story_context:
            story_context = "Not provided — judge based on visual narrative."

        try:
            print(f"{Colors.CYAN}  [Murch evaluation] {shot_id} ({media_type})...{Colors.ENDC}")

            # Use the shared vision model (Chat Completions API, compatible with Ark)
            if not self._vision:
                from core.vision.factory import create_vision
                self._vision = create_vision(self.config)

            # Build context description from previous shots
            context_description_parts = []
            context_images = []
            for ctx_id in context_shot_ids:
                ctx_img = self.project_dir / "assets" / "image" / f"{ctx_id.lower()}.png"
                if ctx_img.exists():
                    context_images.append((ctx_id, ctx_img))
                    context_description_parts.append(f"{ctx_id} (confirmed)")

            if context_description_parts:
                context_description = f"Previous confirmed shots in sequence: {', '.join(context_description_parts)}. Images provided above."
            else:
                context_description = "This is the first shot in the sequence — no previous context."

            # Format the evaluation prompt
            eval_prompt = _MURCH_EVAL_PROMPT.format(
                shot_id=shot_id,
                media_type=media_type,
                emotion_context=emotion_context,
                story_context=story_context,
                context_description=context_description,
            )

            # Route to image or video analysis via the shared vision model (Chat Completions API)
            if media_type == "video":
                result = asyncio.run(self._vision.analyze_video(current_file, eval_prompt))
            else:
                result = asyncio.run(self._vision.analyze_image(current_file, eval_prompt))

            # Parse verdict from result
            verdict = "UNKNOWN"
            weighted = "?"
            for line in result.splitlines():
                line_stripped = line.strip().upper()
                if line_stripped.startswith("VERDICT:"):
                    verdict = "PASS" if "PASS" in line_stripped else "FAIL"
                elif line_stripped.startswith("WEIGHTED:"):
                    weighted = line.strip().split(":", 1)[1].strip()

            icon = "✓" if verdict == "PASS" else "✗"
            color = Colors.GREEN if verdict == "PASS" else Colors.YELLOW
            print(f"{color}  {icon} Murch evaluation: {verdict} (weighted: {weighted}){Colors.ENDC}")

            return f"## Murch Evaluation: {shot_id} ({media_type})\n\n{result}"

        except Exception as e:
            print(f"{Colors.RED}  ✗ Murch evaluation failed: {e}{Colors.ENDC}")
            return f"Murch evaluation failed for {shot_id}: {e}"

    def _tool_validate_before_generate(self, args: dict) -> str:
        """Run pre-generation validation checks. Supports both shots.yaml (new) and prompts.json (legacy)."""
        if not self.project_dir:
            return "Error: project directory not initialized"

        # Try shots.yaml first (new format), then prompts.json (legacy)
        shots_file = self.project_dir / "shots.yaml"
        prompts_file = self.project_dir / "prompts.json"

        data = None  # Will hold prompts-like data
        using_shots_yaml = False

        if shots_file.exists():
            try:
                with open(shots_file) as f:
                    shots_yaml = yaml.safe_load(f) or {}
                # Adapt shots.yaml to prompts.json-like structure for validation
                style_anchor = shots_yaml.get("style_anchor", "")
                shots_dict = {}
                for s in shots_yaml.get("shots", []):
                    sid = s.get("id", "")
                    shots_dict[sid] = {
                        "image_prompt": {
                            "prompt": s.get("prompt", ""),
                            "reference_images": s.get("reference_images", []),
                        },
                        "video_prompt": {
                            "prompt": s.get("video_prompt", ""),
                        },
                    }
                data = {"style_anchor": style_anchor, "shots": shots_dict}
                using_shots_yaml = True
            except Exception as e:
                return f"FAIL: Cannot parse shots.yaml: {e}"
        elif prompts_file.exists():
            try:
                with open(prompts_file) as f:
                    data = json.load(f)
            except Exception as e:
                return f"FAIL: Cannot parse prompts.json: {e}"
        else:
            return "FAIL: Neither shots.yaml nor prompts.json found. Create one first."

        issues = []
        warnings = []

        # ── 0. Narrative checks (skip for shots.yaml — it has minimal structure by design) ──

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
        elif not using_shots_yaml:
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
        ref_dir = self.project_dir / "assets" / "design"
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
                report += f"⚠️ {len(warnings)} WARNING(S) — recommended to fix:\n"
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

    def _tool_learn_browse(self, args: dict) -> str:
        """Browse the web for creative research."""
        action = args.get("action", "search_web")
        query = args.get("query", "")
        platform = args.get("platform")
        max_results = args.get("max_results")

        if not query:
            return "Error: query is required"

        try:
            from core.browser.playwright import PlaywrightBrowser, BrowserConnectionError
        except ImportError as e:
            return f"Playwright not installed: {e}. Please run: pip install playwright && playwright install chromium"

        try:
            async def _do_browse():
                browser = PlaywrightBrowser()
                try:
                    if action == "search_web":
                        engine = platform or "baidu"
                        mr = max_results or 10
                        print(f"{Colors.CYAN}  [Learn] Searching {engine}: {query}...{Colors.ENDC}")
                        return await browser.search_web(query, engine, mr)

                    elif action == "search_images":
                        engine = platform or "baidu_image"
                        mr = max_results or 20
                        print(f"{Colors.CYAN}  [Learn] Image search {engine}: {query}...{Colors.ENDC}")
                        results = await browser.search_images(query, engine, mr)

                        # Auto-download & vision-analyze top 3 images
                        if results and self.project_dir:
                            await self._auto_download_top_images(results, query)

                        return results

                    elif action == "search_videos":
                        plat = platform or "douyin"
                        mr = max_results or 20
                        print(f"{Colors.CYAN}  [Learn] Video search {plat}: {query}...{Colors.ENDC}")

                        # Auto-screenshot search results page into learn dir
                        screenshot_dir = None
                        if self.project_dir:
                            screenshot_dir = self.project_dir / "assets" / "learn" / "video"
                            screenshot_dir.mkdir(parents=True, exist_ok=True)

                        results = await browser.search_videos(query, plat, mr, screenshot_dir=screenshot_dir)

                        # Auto-save a summary note so Director has material to reference
                        if results and self.project_dir:
                            await self._auto_save_video_notes(results, query, plat)

                        return results

                    elif action == "browse_url":
                        print(f"{Colors.CYAN}  [Learn] Browsing: {query[:80]}...{Colors.ENDC}")
                        result = await browser.browse_url(query)
                        print(f"{Colors.GREEN}  ✓ Page loaded: {result.get('title', '')[:60]}{Colors.ENDC}")
                        return result

                    else:
                        return {"error": f"Unknown action: {action}"}
                finally:
                    await browser.close()

            result = asyncio.run(_do_browse())

            # Format output
            if isinstance(result, list):
                valid = [r for r in result if isinstance(r, dict) and "error" not in r]
                if valid:
                    print(f"{Colors.GREEN}  ✓ Found {len(valid)} result(s){Colors.ENDC}")
                else:
                    errors = [r.get("error", "") for r in result if isinstance(r, dict) and "error" in r]
                    if errors:
                        print(f"{Colors.YELLOW}  ⚠ {errors[0]}{Colors.ENDC}")
                return json.dumps(result, ensure_ascii=False, indent=2)
            elif isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False, indent=2)
            return str(result)

        except BrowserConnectionError as e:
            print(f"{Colors.YELLOW}  ⚠ Browser connection failed{Colors.ENDC}")
            return (
                f"Browser connection failed: {e}\n"
                "Please inform the user to quit Chrome first, then re-run."
            )
        except Exception as e:
            return f"Learn browse failed: {e}"

    def _tool_learn_download(self, args: dict) -> str:
        """Download reference materials to assets/learn/. Falls back to screenshot if direct download fails."""
        url = args.get("url", "")
        media_type = args.get("media_type", "file")
        subfolder = args.get("subfolder")
        filename = args.get("filename")
        auto_analyze = args.get("analyze", True)

        if not url:
            return "Error: url is required"

        if not self.project_dir:
            return "Error: No project directory. Create or open a project first."

        # Reject search/listing pages — yt-dlp can only handle individual video URLs
        _SEARCH_PATTERNS = [
            "/search/", "/search?", "/explore", "/discover",
            "/hashtag/", "/tag/", "/topic/",
        ]
        if media_type == "video" and any(pat in url for pat in _SEARCH_PATTERNS):
            return (
                f"Error: '{url}' is a search/listing page, not a video URL. "
                "yt-dlp cannot download from search pages. "
                "Use learn_browse to search first, then pass the specific video URL "
                "(e.g. douyin.com/video/xxxxx) to learn_download."
            )

        # All learn materials saved flat in assets/learn/
        save_dir = self.project_dir / "assets" / "learn"
        save_dir.mkdir(parents=True, exist_ok=True)

        try:
            from core.browser.downloader import MediaDownloader, DownloadError

            downloader = MediaDownloader()
            config = self.config

            async def _do_download_and_analyze():
                """Download + optional vision analysis in a single async context."""
                download_failed = False
                result_path = None

                # Step 1: Download
                try:
                    if media_type == "image":
                        result_path = await downloader.download_image(url, save_dir, filename)
                    elif media_type == "video":
                        result_path = await downloader.download_video(url, save_dir, filename=filename)
                    else:
                        result_path = await downloader.download_file(url, save_dir, filename)
                except (DownloadError, Exception) as e:
                    download_failed = True
                    print(f"{Colors.YELLOW}  ⚠ Direct download failed: {e}{Colors.ENDC}")

                # Step 2: Fallback to screenshot
                if download_failed or (result_path and result_path.stat().st_size < 1000):
                    print(f"{Colors.CYAN}  [Learn] Falling back to browser screenshot...{Colors.ENDC}")
                    try:
                        from core.browser.playwright import PlaywrightBrowser
                        import hashlib as _hashlib

                        ss_name = filename or _hashlib.md5(url.encode()).hexdigest()[:12]
                        if not ss_name.endswith(('.png', '.jpg')):
                            ss_name += '.png'
                        ss_path = save_dir / ss_name

                        browser = PlaywrightBrowser()
                        try:
                            await browser._ensure_browser()
                            page = await browser._context.new_page()
                            try:
                                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                                await page.wait_for_timeout(3000)
                                ss_path.parent.mkdir(parents=True, exist_ok=True)
                                await page.screenshot(path=str(ss_path), full_page=False, type="png")
                                result_path = ss_path
                            finally:
                                await page.close()
                        finally:
                            await browser.close()

                        print(f"{Colors.GREEN}  ✓ Screenshot saved (fallback): {ss_name}{Colors.ENDC}")
                    except Exception as e2:
                        print(f"{Colors.RED}  ✗ Screenshot fallback also failed: {e2}{Colors.ENDC}")
                        return None, ""

                # Step 3: Auto-analyze images with vision API
                analysis_text = ""
                if (auto_analyze and media_type == "image"
                        and result_path and result_path.exists()
                        and result_path.stat().st_size >= 1000):
                    try:
                        from core.vision.factory import create_vision
                        vision = create_vision(config)

                        analysis_prompt = (
                            "分析这张图片的创作参考价值，提供结构化分析：\n"
                            "1. **画风**: 艺术风格类型\n"
                            "2. **色调**: 主要色彩和整体冷暖\n"
                            "3. **构图**: 布局和视觉焦点\n"
                            "4. **光影**: 光源方向和氛围\n"
                            "5. **关键元素**: 值得借鉴的视觉元素\n"
                            "6. **创作建议**: 如何将此风格应用到项目中\n"
                            "每点1-2句话。"
                        )

                        print(f"{Colors.CYAN}  [Learn] 分析图片中...{Colors.ENDC}")
                        analysis_text = await vision.analyze_image(result_path, analysis_prompt)

                        from datetime import datetime as _dt
                        meta_path = result_path.with_suffix(".analysis.md")
                        meta_path.write_text(
                            f"# {result_path.name}\n"
                            f"来源: {url}\n"
                            f"日期: {_dt.now().strftime('%Y-%m-%d')}\n\n"
                            f"{analysis_text}\n",
                            encoding="utf-8",
                        )
                        print(f"{Colors.GREEN}  ✓ 分析已保存: {meta_path.name}{Colors.ENDC}")
                    except Exception as e:
                        print(f"{Colors.YELLOW}  ⚠ 自动分析失败: {e}{Colors.ENDC}")

                return result_path, analysis_text

            print(f"{Colors.CYAN}  [Learn] Downloading {media_type}: {url[:80]}...{Colors.ENDC}")

            result_path, analysis_text = asyncio.run(_do_download_and_analyze())

            if not result_path or not result_path.exists():
                return "Download failed: no file saved"

            # Return relative path for cleaner output
            try:
                rel_path = result_path.relative_to(self.project_dir)
            except ValueError:
                rel_path = result_path

            size = result_path.stat().st_size
            if size > 1024 * 1024:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            else:
                size_str = f"{size / 1024:.0f} KB"

            print(f"{Colors.GREEN}  ✓ Saved: {rel_path} ({size_str}){Colors.ENDC}")
            msg = f"Saved to: {rel_path} ({size_str})"

            # Hint: usable as reference_images in prompts.json
            if media_type == "image" and result_path:
                ref_id = result_path.stem
                msg += f'\n可直接在 reference_images 中使用: "{ref_id}"'

            # Append analysis if available
            if analysis_text:
                msg += f"\n\n## 图片分析\n{analysis_text}"

            return msg

        except ImportError as e:
            return f"Missing dependency: {e}"
        except Exception as e:
            print(f"{Colors.RED}  ✗ Download failed: {e}{Colors.ENDC}")
            return f"Download failed: {e}"

    async def _auto_save_video_notes(
        self, results: list[dict], query: str, platform: str
    ) -> None:
        """Auto-save video search results as a structured note + analyze screenshots with vision.

        This gives the Director actual reference material instead of just JSON metadata.
        """
        valid = [r for r in results if isinstance(r, dict) and "error" not in r and r.get("title")]
        if not valid:
            return

        notes_dir = self.project_dir / "assets" / "learn" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        from datetime import datetime as _dt
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        slug = query.replace(" ", "_")[:30]
        note_path = notes_dir / f"video_{platform}_{slug}_{ts}.md"

        lines = [
            f"# Video Research: {query}",
            f"Platform: {platform} | Date: {_dt.now().strftime('%Y-%m-%d %H:%M')}",
            f"Results: {len(valid)}",
            "",
            "## Top Results",
            "",
        ]
        for i, v in enumerate(valid[:10]):
            title = v.get("title", "?")
            likes = v.get("likes", "?")
            duration = v.get("duration", "?")
            author = v.get("author", "?")
            url = v.get("url", "")
            lines.append(f"{i+1}. **{title}**")
            lines.append(f"   Likes: {likes} | Duration: {duration} | Author: @{author}")
            if url:
                lines.append(f"   URL: {url}")
            lines.append("")

        note_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"{Colors.GREEN}  ✓ Saved video research note: {note_path.name}{Colors.ENDC}")

        # Vision-analyze search result screenshots if they exist
        screenshot_dir = self.project_dir / "assets" / "learn" / "video"
        screenshots = sorted(screenshot_dir.glob("search_*.jpg"))
        if screenshots:
            try:
                from core.vision.factory import create_vision
                vision = create_vision(self.config)

                analysis_prompt = (
                    "这是短视频搜索结果页面的截图。请分析：\n"
                    "1. 哪些封面最吸引眼球？为什么？（构图、色彩、表情）\n"
                    "2. 标题有什么共同模式？\n"
                    "3. 点赞最多的视频有什么视觉特征？\n"
                    "4. 给出3个具体的创作灵感。\n"
                    "简洁回答，每点1-2句话。"
                )

                # Analyze the top screenshot
                analysis = await vision.analyze_image(screenshots[0], analysis_prompt)

                analysis_path = screenshot_dir / f"analysis_{slug}_{ts}.md"
                analysis_path.write_text(
                    f"# Visual Analysis: {query}\n\n{analysis}\n",
                    encoding="utf-8",
                )
                print(f"{Colors.GREEN}  ✓ Vision-analyzed search results{Colors.ENDC}")

                # Attach analysis to results for LLM context
                if valid:
                    valid[0]["search_page_analysis"] = analysis

            except Exception as e:
                print(f"{Colors.YELLOW}  ⚠ Vision analysis of screenshots failed: {e}{Colors.ENDC}")

    async def _auto_download_top_images(
        self, results: list[dict], query: str, top_n: int = 3
    ) -> None:
        """Auto-download and vision-analyze the top N images from search results.

        Runs after search_images to give the LLM actual visual analysis
        instead of just metadata (titles/URLs).
        """
        # Filter results that have image URLs
        candidates = [
            r for r in results
            if isinstance(r, dict)
            and r.get("image_url")
            and "error" not in r
        ]
        if not candidates:
            return

        candidates = candidates[:top_n]
        save_dir = self.project_dir / "assets" / "learn" / "image"
        save_dir.mkdir(parents=True, exist_ok=True)

        from core.browser.downloader import MediaDownloader, DownloadError

        downloader = MediaDownloader()

        downloaded = 0
        for i, item in enumerate(candidates):
            image_url = item["image_url"]
            try:
                result_path = await downloader.download_image(image_url, save_dir)
                downloaded += 1

                # Vision analysis
                try:
                    from core.vision.factory import create_vision
                    vision = create_vision(self.config)

                    analysis_prompt = (
                        "分析这张图片的创作参考价值，提供结构化分析：\n"
                        "1. **画风**: 艺术风格类型\n"
                        "2. **色调**: 主要色彩和整体冷暖\n"
                        "3. **构图**: 布局和视觉焦点\n"
                        "4. **光影**: 光源方向和氛围\n"
                        "5. **关键元素**: 值得借鉴的视觉元素\n"
                        "6. **创作建议**: 如何将此风格应用到项目中\n"
                        "每点1-2句话。"
                    )

                    analysis_text = await vision.analyze_image(result_path, analysis_prompt)

                    from datetime import datetime as _dt
                    meta_path = result_path.with_suffix(".analysis.md")
                    meta_path.write_text(
                        f"# {result_path.name}\n"
                        f"来源: {image_url}\n"
                        f"搜索词: {query}\n"
                        f"日期: {_dt.now().strftime('%Y-%m-%d')}\n\n"
                        f"{analysis_text}\n",
                        encoding="utf-8",
                    )

                    # Attach analysis back to the search result for the LLM
                    item["auto_downloaded"] = True
                    item["local_path"] = str(result_path.relative_to(self.project_dir))
                    item["vision_analysis"] = analysis_text
                    print(f"{Colors.GREEN}  ✓ Auto-analyzed [{i+1}/{top_n}]: {result_path.name}{Colors.ENDC}")

                except Exception as e:
                    item["auto_downloaded"] = True
                    item["local_path"] = str(result_path.relative_to(self.project_dir))
                    item["vision_analysis"] = f"(分析失败: {e})"
                    print(f"{Colors.YELLOW}  ⚠ Vision analysis failed for {result_path.name}: {e}{Colors.ENDC}")

            except (DownloadError, Exception) as e:
                item["auto_downloaded"] = False
                item["download_error"] = str(e)
                print(f"{Colors.YELLOW}  ⚠ Auto-download failed [{i+1}/{top_n}]: {e}{Colors.ENDC}")

        if downloaded > 0:
            print(f"{Colors.GREEN}  ✓ Auto-downloaded & analyzed {downloaded}/{top_n} images{Colors.ENDC}")

    def _tool_list_assets(self, args: dict) -> str:
        if not self.project_dir:
            return "No project directory"

        result = {"images": [], "videos": []}

        images_dir = self.project_dir / "assets" / "image"
        videos_dir = self.project_dir / "assets" / "video"

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

        videos_dir = self.project_dir / "assets" / "video"
        images_dir = self.project_dir / "assets" / "image"

        # Load shot metadata: try shots.yaml (new format) first, then storyboard.yaml (legacy)
        storyboard_data = None
        if auto_storyboard:
            # New format: shots.yaml
            shots_file = self.project_dir / "shots.yaml"
            if shots_file.exists():
                try:
                    with open(shots_file) as f:
                        shots_yaml = yaml.safe_load(f) or {}
                    # Adapt shots.yaml format to storyboard_data shape for downstream compatibility
                    storyboard_data = {"shots": shots_yaml.get("shots", [])}
                except Exception:
                    pass

            # Legacy format: storyboard.yaml
            if not storyboard_data:
                storyboard_file = self.project_dir / "storyboard.yaml"
                if storyboard_file.exists():
                    try:
                        with open(storyboard_file) as f:
                            storyboard_data = yaml.safe_load(f)
                    except Exception:
                        pass

        # Build shot metadata lookup from storyboard/shots data
        shot_meta = {}
        if storyboard_data:
            for s in storyboard_data.get("shots", []):
                shot_meta[s.get("id", "")] = s

        # Determine shot order
        if not shot_ids:
            if storyboard_data:
                # Use storyboard/shots order (authoritative)
                shot_ids = [s.get("id", "") for s in storyboard_data.get("shots", []) if s.get("id")]
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
                for i, meta in enumerate(clip_metas):
                    trim_s = meta.get("trim_start", 0.0) or 0.0
                    trim_e = meta.get("trim_end", None)
                    use_dur = meta.get("use_duration", None) or meta.get("duration", None)

                    # If duration specified and clip is longer, trim to match
                    if use_dur and trim_e is None:
                        clip_path = clips[i] if i < len(clips) else None
                        if clip_path:
                            clip_dur = assembler._get_duration(clip_path)
                            if clip_dur > use_dur + 0.1:
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

    # ── Memory — persistent user understanding ────────────────────

    def _tool_memory_read(self, args: dict) -> str:
        """Read a memory file (markdown)."""
        filename = args.get("filename", "MEMORY.md")
        if not filename.endswith(".md"):
            filename += ".md"

        filepath = MEMORY_DIR / filename
        if not filepath.exists():
            if filename == "MEMORY.md":
                return "(No memory yet. Create it with memory_write when you learn something about the user.)"
            return f"Memory file '{filename}' does not exist. Available files: {self._list_memory_files()}"

        content = filepath.read_text(encoding="utf-8")
        if len(content) > 50000:
            content = content[:50000] + "\n... [truncated]"
        print(f"{Colors.DIM}  [Memory] Read {filename} ({len(content)} chars){Colors.ENDC}")
        return content

    def _tool_memory_write(self, args: dict) -> str:
        """Write a memory file (full content replacement)."""
        filename = args.get("filename", "MEMORY.md")
        content = args.get("content", "")

        if not filename.endswith(".md"):
            filename += ".md"
        if not content.strip():
            return "Error: content is empty."

        # Safety: only allow writing to memory dir
        filepath = MEMORY_DIR / filename
        if ".." in filename or "/" in filename:
            return "Error: filename must be a simple name (no paths)."

        filepath.write_text(content, encoding="utf-8")

        # Invalidate cached system prompt so memory updates take effect
        if filename == "MEMORY.md":
            self._cached_system_prompt = None

        lines = content.count("\n") + 1
        print(f"{Colors.DIM}  [Memory] Wrote {filename} ({lines} lines){Colors.ENDC}")

        # Warn if MEMORY.md exceeds 200 lines
        if filename == "MEMORY.md" and lines > 200:
            return (
                f"Memory '{filename}' saved ({lines} lines). "
                f"WARNING: MEMORY.md has {lines} lines (recommended max: 200). "
                f"Consider moving details to topic files."
            )
        return f"Memory '{filename}' saved ({lines} lines)."

    def _list_memory_files(self) -> str:
        """List existing memory files."""
        files = sorted(MEMORY_DIR.glob("*.md"))
        if not files:
            return "(none)"
        return ", ".join(f.name for f in files)

    def _trigger_memory_save(self):
        """Silently ask the agent to persist anything learned this session."""
        user_turns = sum(1 for m in self.messages if m.get("role") == "user")
        if user_turns < 2:
            return  # Too short to have learned anything useful

        print(f"  {Colors.DIM}[Memory] Saving session insights...{Colors.ENDC}")

        memory_prompt = (
            "[SESSION END — INTERNAL] "
            "Review this conversation and update persistent memory if anything is worth saving. "
            "Call memory_read() to load current MEMORY.md, then memory_write() to save new "
            "user preferences, aesthetic corrections, project outcomes, or terminology. "
            "If nothing is worth saving, respond with just 'done'."
        )

        try:
            if self.protocol == "anthropic":
                self._memory_save_anthropic(memory_prompt)
            else:
                self._memory_save_openai(memory_prompt)
            print(f"  {Colors.DIM}[Memory] Done{Colors.ENDC}")
        except Exception:
            pass  # Never block exit due to memory save failure

    def _memory_save_anthropic(self, prompt: str):
        """Non-streaming Anthropic call for silent memory save."""
        # Use a separate message list so we don't pollute the main conversation
        save_messages = list(self.messages)
        save_messages.append({"role": "user", "content": prompt})

        # Only expose memory tools
        memory_tools = [t for t in TOOLS_ANTHROPIC if t["name"] in ("memory_read", "memory_write")]

        for _ in range(5):  # max tool-call rounds
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self._get_system_prompt(),
                messages=save_messages,
                tools=memory_tools,
            )

            if response.stop_reason != "tool_use":
                break

            # Execute tool calls silently
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self.handle_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            save_messages.append({"role": "assistant", "content": response.content})
            save_messages.append({"role": "user", "content": tool_results})

    def _memory_save_openai(self, prompt: str):
        """Non-streaming OpenAI call for silent memory save."""
        save_messages = [
            {"role": "system", "content": self._get_system_prompt()},
            *self.messages,
            {"role": "user", "content": prompt},
        ]

        memory_tools = [
            t for t in _tools_to_openai(TOOLS_ANTHROPIC)
            if t["function"]["name"] in ("memory_read", "memory_write")
        ]

        for _ in range(5):
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=2048,
                messages=save_messages,
                tools=memory_tools,
            )

            choice = response.choices[0]
            if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
                break

            save_messages.append(choice.message)
            for tc in choice.message.tool_calls:
                import json as _json
                args = _json.loads(tc.function.arguments) if tc.function.arguments else {}
                result = self.handle_tool(tc.function.name, args)
                save_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

    # ── Conversation engine — Anthropic protocol ─────────────────

    def _send_anthropic(self, user_content: str | list | None, *, watcher: InputWatcher | None = None):
        """Anthropic messages API loop with streaming (Claude, MiniMax)."""
        if user_content is not None:
            self.messages.append({"role": "user", "content": user_content})
            if self._plog:
                self._plog.log_user(user_content)

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
                        system=self._get_system_prompt(),
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
                        if self._plog:
                            self._plog.log_error(f"API call failed: {data}")
                        return

                    if kind == "event":
                        event = data
                        if hasattr(event, "type") and event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                if not spinner_stopped:
                                    spinner.stop()
                                    spinner_stopped = True
                                stream_printer.feed(event.delta.text)
                                if self._plog:
                                    self._plog.log_assistant_chunk(event.delta.text)
                            elif hasattr(event.delta, "thinking"):
                                # Anthropic extended thinking block
                                if not spinner_stopped:
                                    spinner.stop()
                                    spinner_stopped = True
                                stream_printer.feed(event.delta.thinking, thinking=True)
                                if self._plog:
                                    self._plog.log_thinking_chunk(event.delta.thinking)

                    if kind == "done":
                        if not spinner_stopped:
                            spinner.stop()
                        stream_printer.finish()
                        if self._plog:
                            self._plog.log_assistant_end()
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
                    if self._plog:
                        self._plog.log_tool_call(block.name, block.input or {})
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
                        if self._plog:
                            self._plog.log_tool_result(block.name, f"ERROR: {_tool_result[1]}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Tool execution error: {_tool_result[1]}",
                        })
                    else:
                        if self._plog:
                            self._plog.log_tool_result(block.name, _tool_result[0])
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
            if self._plog:
                self._plog.log_user(user_content)

        # Ensure system message is first
        if not self.messages or self.messages[0].get("role") != "system":
            self.messages.insert(0, {"role": "system", "content": self._get_system_prompt()})

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
            reasoning_content = ""  # For models with thinking mode (e.g. Kimi K2.5)
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
                        if self._plog:
                            self._plog.log_error(f"API call failed: {data}")
                        return

                    if kind == "chunk":
                        chunk = data
                        if not chunk.choices:
                            continue
                        choice = chunk.choices[0]
                        delta = choice.delta

                        # Capture reasoning_content (thinking mode, e.g. Kimi K2.5)
                        if delta and getattr(delta, "reasoning_content", None):
                            reasoning_content += delta.reasoning_content

                        if delta and delta.content:
                            if not spinner_stopped:
                                spinner.stop()
                                spinner_stopped = True
                            full_content += delta.content
                            stream_printer.feed(delta.content)
                            if self._plog:
                                self._plog.log_assistant_chunk(delta.content)

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
                        if self._plog:
                            self._plog.log_assistant_end()
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
            # Preserve reasoning_content for models with thinking mode (Kimi K2.5 requires this)
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
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
                    if self._plog:
                        self._plog.log_tool_call(tc["function"]["name"], tool_args)
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
                        if self._plog:
                            self._plog.log_tool_result(tc["function"]["name"], f"ERROR: {_tool_result[1]}")
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": f"Tool execution error: {_tool_result[1]}",
                        })
                    else:
                        if self._plog:
                            self._plog.log_tool_result(tc["function"]["name"], _tool_result[0])
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
        for fname in ["feeling.yaml", "shots.yaml", "screenplay.yaml", "storyboard.yaml", "prompts.json", "review.yaml"]:
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
            "/config": lambda: self._cmd_config(),
            "/show": lambda: self._cmd_show(),
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
        """Autonomous web research — load learn skill and let AI drive the research."""
        if not arg:
            print(f"  {Colors.YELLOW}Usage: /learn <topic or keyword>{Colors.ENDC}")
            print(f"  {Colors.DIM}e.g.: /learn 武松打虎的历史背景{Colors.ENDC}")
            print(f"  {Colors.DIM}      /learn 水墨画风格 老虎{Colors.ENDC}")
            print(f"  {Colors.DIM}      /learn trending AI short films bilibili{Colors.ENDC}")
            print(f"  {Colors.DIM}The AI will autonomously search, browse, and download references.{Colors.ENDC}")
            return "handled"

        # Ensure a project exists so materials can be saved
        if not self._ensure_project():
            return "handled"

        # Load learn skill into context
        learn_skill_content = ""
        skill_dir = SKILLS.get("learn")
        if skill_dir:
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                learn_skill_content = skill_file.read_text(encoding="utf-8")

        # Inject the research request into conversation
        self.messages.append({
            "role": "user" if self.protocol == "anthropic" else "system",
            "content": (
                f"[System] The user wants to research: '{arg}'\n\n"
                f"Use the learn_browse and learn_download tools to autonomously:\n"
                f"1. Search for relevant information (web, images, videos as appropriate)\n"
                f"2. Browse promising results to extract key content\n"
                f"3. Download valuable reference materials to assets/learn/\n"
                f"4. Compile research findings as a note in assets/learn/\n\n"
                f"Research methodology:\n{learn_skill_content[:3000] if learn_skill_content else 'Load the learn skill for guidance.'}"
            ),
        })

        print(f"  {Colors.CYAN}Starting autonomous research: {arg}{Colors.ENDC}")
        print(f"  {Colors.DIM}The AI will search, browse, and download references...{Colors.ENDC}\n")

        # Let the AI take over — send to the model for autonomous research
        self._send_with_watcher(
            f"Please research '{arg}' for this project using learn_browse and learn_download tools.\n\n"
            f"Quick research flow:\n"
            f"1. search_videos on douyin → auto-saves screenshots + notes to learn/\n"
            f"2. search_images for style refs → auto-downloads top 3 to learn/\n"
            f"3. If any result is particularly inspiring, download it with learn_download\n"
            f"4. After 2-3 searches, write feeling.yaml based on what you found\n"
            f"Don't over-research. 2-3 focused searches is enough."
        )
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

        images_dir = self.project_dir / "assets" / "image"
        videos_dir = self.project_dir / "assets" / "video"
        refs_dir = self.project_dir / "assets" / "design"

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

    def _cmd_show(self) -> str:
        """Show current model configuration."""
        from .cli import show_config
        show_config()
        return "handled"

    def _cmd_config(self) -> str:
        """Interactive model configuration."""
        from .cli import run_config
        saved = run_config()
        if not saved:
            return "handled"
        # Reload config after changes
        self.config = load_config()
        protocol, api_key, model, base_url = _resolve_llm_config(self.config)
        self.protocol = protocol
        self.model = model
        if protocol == "anthropic":
            from anthropic import Anthropic
            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self.client = Anthropic(**kwargs)
        else:
            from openai import OpenAI
            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self.client = OpenAI(**kwargs)
        # Reset lazy providers so they pick up new config
        self._image_gen = None
        self._video_gen = None
        self._cached_system_prompt = None
        provider_name = self.config.llm.provider
        print(f"  {Colors.DIM}Reloaded: {provider_name} / {model}{Colors.ENDC}")
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
            ("/config", "Configure models for each stage (LLM/image/video/vision)"),
            ("/show", "Show current model configuration"),
            ("/help", "Show help"),
            ("/quit", "Save and exit"),
        ]
        col = max(len(c) for c, _ in cmds) + 2
        for cmd, desc in cmds:
            print(f"    {B}{cmd:<{col}}{E} {D}{desc}{E}")
            if cmd.startswith("/learn"):
                print(f"    {D}{'':<{col}} Platforms: douyin bilibili xiaohongshu youtube{E}")
        print(f"\n  {D}Press Enter = let the director freestyle | Supports image/video/document file paths{E}\n")
        return "handled"

    def _reset_project(self, new_name: str):
        """Reset project state for switching to a new/different project."""
        # Close previous logger if any
        if self._plog:
            self._plog.close()
            self._plog = None
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
            "assets/image", "assets/video", "assets/design",
            "assets/user", "assets/audio", "assets/learn",
            "output", "logs",
        ]:
            (self.project_dir / sub).mkdir(parents=True, exist_ok=True)

        # Initialize project-level conversation logger
        if self._plog is None:
            self._plog = ProjectLogger(self.project_dir, model=self.model)
            print(f"{Colors.DIM}  Log: {self._plog.path.relative_to(self.project_dir)}{Colors.ENDC}")

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
        _ICON_MAP = {"image": "🖼️", "video": "🎬", "document": "📄"}
        print(f"  {Colors.CYAN}Detected {len(detected_files)} file(s):{Colors.ENDC}")
        for df in detected_files:
            icon = _ICON_MAP.get(df["type"], "📎")
            print(f"    {icon} {df['path'].name}")

        processed = _process_reference_files(detected_files, self.project_dir)

        if not processed:
            print(f"  {Colors.YELLOW}File processing failed, sending text only{Colors.ENDC}")
            self._send_with_watcher(user_input)
            return

        video_count = sum(1 for df in detected_files if df["type"] == "video")
        if video_count:
            print(f"  {Colors.DIM}Video saved (will be analyzed via analyze_media){Colors.ENDC}")
        print(f"  {Colors.DIM}Files saved to assets/user/{Colors.ENDC}")

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
                    if self._plog:
                        self._plog.log_command(user_input)
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

            # Session ended — persist any learned preferences before cleanup
            self._trigger_memory_save()
        finally:
            _split_terminal.exit()

        if self.project_name:
            self.save_metadata()
        if self._plog:
            self._plog.close()

        # ── Goodbye ──
        print(f"\n  {Colors.YELLOW}Takone — Good bye 👋{Colors.ENDC}\n")

        if self.saved_files or self.generated_assets or self.project_dir:
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
    # Handle subcommands before starting the director
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "config":
            from .cli import run_config
            run_config()
            return
        elif cmd == "show":
            from .cli import show_config
            show_config()
            return

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
