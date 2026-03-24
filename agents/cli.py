"""CLI configuration for Takone — hierarchical menu-based model selection."""

from pathlib import Path

import yaml

from .config import Colors, DIRECTOR_ROOT

_HOME_DIR = Path.home() / ".takone"


class _Back(Exception):
    """Go back to parent menu."""
    pass


# ── Provider definitions ──────────────────────────────────────

STAGES = {
    "llm": {
        "label": "LLM",
        "desc": "Main agent brain",
        "providers": {
            "minimax":  {"model_field": "minimax_model", "default_model": "minimax-m2.7"},
            "moonshot": {"model_field": "kimi_model",     "default_model": "kimi-k2.5"},
            "zhipu":    {"model_field": "zhipu_model",   "default_model": "glm-5"},
            "claude":   {"model_field": "claude_model",  "default_model": "claude-sonnet-4-20250514"},
            "openai":   {"model_field": "openai_model",  "default_model": "gpt-4o"},
            "doubao":   {"model_field": "ark_model",     "default_model": "doubao-seed-2-0-pro-260215"},
            "qwen":     {"model_field": "qwen_model",    "default_model": "qwen3.5-plus"},
        },
    },
    "image": {
        "label": "Image",
        "desc": "Image generation",
        "providers": {
            "jimeng": {"model_field": "jimeng_model", "default_model": "doubao-seedream-5-0-260128"},
            "gemini": {"model_field": "gemini_model", "default_model": "gemini-2.5-flash-image"},
        },
    },
    "video": {
        "label": "Video",
        "desc": "Video generation",
        "providers": {
            "seedance": {"model_field": "seedance_model", "default_model": "doubao-seedance-1-5-pro-251215"},
            "minimax":  {"model_field": "minimax_model",  "default_model": "video-01"},
            "sora":     {"model_field": "sora_model",     "default_model": "sora"},
        },
    },
    "vision": {
        "label": "Vision",
        "desc": "Image/video understanding",
        "providers": {
            "doubao": {"model_field": "doubao_model", "default_model": "doubao-1-5-vision-pro-32k-250115"},
            "kimi":   {"model_field": "kimi_model",   "default_model": "kimi-k2.5"},
            "zhipu":  {"model_field": "zhipu_model",  "default_model": "glm-4.6v"},
            "qwen":   {"model_field": "qwen_model",   "default_model": "qwen3.5-plus"},
            "openai": {"model_field": None,           "default_model": "gpt-4o"},
            "claude": {"model_field": None,           "default_model": "claude-sonnet-4-20250514"},
        },
    },
}


# ── Helpers ───────────────────────────────────────────────────

def _load_current_config() -> dict:
    config_path = _HOME_DIR / "config.yaml" if (_HOME_DIR / "config.yaml").exists() else DIRECTOR_ROOT / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_config(data: dict):
    _HOME_DIR.mkdir(parents=True, exist_ok=True)
    config_path = _HOME_DIR / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"  {Colors.DIM}Saved → {config_path}{Colors.ENDC}")


def _input(prompt: str = "") -> str:
    """Read input, raise _Back on q/Ctrl+C."""
    try:
        raw = input(f"  {Colors.CYAN}{prompt}>{Colors.ENDC} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise _Back()
    if raw.lower() in ("q", "quit", "/quit", "b", "back"):
        raise _Back()
    return raw


def _get_stage_summary(data: dict, stage_key: str) -> str:
    """One-line summary of a stage's current config."""
    stage = STAGES[stage_key]
    section = data.get(stage_key, {})
    provider = section.get("provider", "?")
    providers = stage["providers"]
    if provider in providers:
        info = providers[provider]
        model_field = info["model_field"]
        model = section.get(model_field, info["default_model"]) if model_field else info["default_model"]
        return f"{provider} / {model}"
    return provider


# ── Menu screens ──────────────────────────────────────────────

def _menu_main(data: dict) -> bool:
    """Top-level: pick which stage to configure. Returns True if anything was saved."""
    saved = False
    while True:
        stage_keys = list(STAGES.keys())
        # Compute column widths from actual data
        col_label = max(len(f"{i}) {STAGES[k]['label']}") for i, k in enumerate(stage_keys, 1)) + 2
        col_desc  = max(len(STAGES[k]["desc"]) for k in stage_keys) + 2
        col_val   = max(len(_get_stage_summary(data, k)) for k in stage_keys)
        W = 2 + col_label + col_desc + col_val + 1  # inner width
        C, B, E = Colors.CYAN, Colors.BOLD, Colors.ENDC

        print(f"\n{C}  ┌─ {B}Model Configuration{E}{C} {'─' * (W - 22)}┐{E}")
        for i, key in enumerate(stage_keys, 1):
            stage = STAGES[key]
            summary = _get_stage_summary(data, key)
            label = f"{i}) {stage['label']}"
            print(f"{C}  │{E}  {B}{label:<{col_label}}{E}"
                  f"{Colors.DIM}{stage['desc']:<{col_desc}}{E}"
                  f"{Colors.GREEN}{summary:<{col_val}}{E} {C}│{E}")
        qpad = W - 10
        left = qpad // 2
        right = qpad - left
        print(f"{C}  └{'─' * left} q = back {'─' * right}┘{E}")

        try:
            raw = _input()
        except _Back:
            return saved

        if not raw:
            continue

        try:
            idx = int(raw) - 1
            if 0 <= idx < len(stage_keys):
                if _menu_stage(data, stage_keys[idx]):
                    saved = True
                continue
        except ValueError:
            pass

        # Try matching by name
        raw_lower = raw.lower()
        for key in stage_keys:
            if key == raw_lower or STAGES[key]["label"].lower() == raw_lower:
                if _menu_stage(data, key):
                    saved = True
                break
        else:
            print(f"  {Colors.RED}Enter 1-{len(stage_keys)} or stage name.{Colors.ENDC}")


def _menu_stage(data: dict, stage_key: str) -> bool:
    """Configure a specific stage. Returns True if saved."""
    stage = STAGES[stage_key]
    providers = stage["providers"]
    provider_names = list(providers.keys())
    section = data.setdefault(stage_key, {})
    current_provider = section.get("provider", provider_names[0])

    while True:
        print(f"\n  {Colors.BOLD}{stage['label']}{Colors.ENDC} {Colors.DIM}— {stage['desc']}{Colors.ENDC}")
        print(f"  {'─' * 40}")
        for i, name in enumerate(provider_names, 1):
            marker = f"{Colors.GREEN}*{Colors.ENDC}" if name == current_provider else " "
            info = providers[name]
            model_field = info["model_field"]
            current_model = section.get(model_field, info["default_model"]) if model_field else info["default_model"]
            print(f"  {marker} {i}) {name:<12} {Colors.DIM}{current_model}{Colors.ENDC}")
        print(f"  {'─' * 40}")
        print(f"  {Colors.DIM}q = back{Colors.ENDC}")

        try:
            raw = _input(stage['label'].lower())
        except _Back:
            return False

        if not raw:
            continue

        chosen = None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(provider_names):
                chosen = provider_names[idx]
        except ValueError:
            if raw in provider_names:
                chosen = raw

        if not chosen:
            print(f"  {Colors.RED}Enter 1-{len(provider_names)} or provider name.{Colors.ENDC}")
            continue

        # Provider selected — now pick model
        info = providers[chosen]
        model_field = info["model_field"]
        if model_field:
            current_model = section.get(model_field, info["default_model"])
            print(f"  {Colors.DIM}  Model [{current_model}] — Enter to keep, or type new model:{Colors.ENDC}")
            try:
                model_raw = _input(f"{chosen}")
            except _Back:
                continue  # back to provider list, not out of stage
            model = model_raw if model_raw else current_model
            section[model_field] = model

        section["provider"] = chosen
        _save_config(data)

        summary = _get_stage_summary(data, stage_key)
        print(f"  {Colors.DIM}  {stage['label']}: {summary}{Colors.ENDC}")
        return True


# ── Public API ────────────────────────────────────────────────

def run_config() -> bool:
    """Interactive hierarchical config. Returns True if any changes were saved."""
    data = _load_current_config()
    for key in STAGES:
        data.setdefault(key, {})
    return _menu_main(data)


def show_config():
    """Show current configuration in a compact table."""
    data = _load_current_config()
    if not data:
        print(f"  {Colors.YELLOW}No config found. Run /config to set up.{Colors.ENDC}")
        return

    print(f"\n  {Colors.BOLD}Current Configuration{Colors.ENDC}")
    print(f"  {'─' * 40}")
    for key in STAGES:
        stage = STAGES[key]
        summary = _get_stage_summary(data, key)
        print(f"  {Colors.CYAN}{stage['label']:<10}{Colors.ENDC} {summary}")
    print(f"  {'─' * 40}")

    config_path = _HOME_DIR / "config.yaml" if (_HOME_DIR / "config.yaml").exists() else DIRECTOR_ROOT / "config.yaml"
    print(f"  {Colors.DIM}{config_path}{Colors.ENDC}")
