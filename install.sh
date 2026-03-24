#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  Takone Installer
#  Works on macOS & Linux. Installs everything you need.
#
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/wormholeportal/takone/main/install.sh | bash
#    # or
#    bash install.sh            # install from GitHub
#    bash install.sh --local    # install from current directory (dev mode)
#
#  Options (env vars):
#    TAKONE_INSTALL_DIR   Where to clone (default: ~/.takone)
#    TAKONE_NO_DEPS       Skip system deps if set to 1
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colors ───────────────────────────────────────────────────
BOLD='\033[1m'
DIM='\033[2m'
YELLOW='\033[1;33m'
GREEN='\033[1;32m'
RED='\033[1;31m'
CYAN='\033[1;36m'
RESET='\033[0m'

info()  { echo -e "${CYAN}▸${RESET} $*"; }
ok()    { echo -e "${GREEN}✓${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
fail()  { echo -e "${RED}✗${RESET} $*" >&2; exit 1; }

# ── Banner ───────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}${BOLD}"
cat << 'BANNER'
  ████████╗ █████╗ ██╗  ██╗ ██████╗ ███╗   ██╗███████╗
  ╚══██╔══╝██╔══██╗██║ ██╔╝██╔═══██╗████╗  ██║██╔════╝
     ██║   ███████║█████╔╝ ██║   ██║██╔██╗ ██║█████╗
     ██║   ██╔══██║██╔═██╗ ██║   ██║██║╚██╗██║██╔══╝
     ██║   ██║  ██║██║  ██╗╚██████╔╝██║ ╚████║███████╗
     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝
BANNER
echo -e "${RESET}"
echo -e "${DIM}  AI Video Creation Agent — from concept to export${RESET}"
echo ""

# ── Detect OS ────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)      fail "Unsupported OS: $OS. Takone supports macOS and Linux." ;;
esac

info "Detected ${BOLD}$PLATFORM${RESET} ($ARCH)"

# ── Helper: check if command exists ──────────────────────────
has() { command -v "$1" &>/dev/null; }

# ── Install system dependencies ──────────────────────────────
install_deps() {
    if [[ "${TAKONE_NO_DEPS:-0}" == "1" ]]; then
        warn "Skipping system dependencies (TAKONE_NO_DEPS=1)"
        return
    fi

    # -- Python 3.10+ --
    if has python3; then
        PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 10 ]]; then
            ok "Python $PY_VER"
        else
            warn "Python $PY_VER found, but 3.10+ is required"
            install_python
        fi
    else
        warn "Python not found"
        install_python
    fi

    # -- FFmpeg --
    if has ffmpeg; then
        ok "FFmpeg $(ffmpeg -version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?')"
    else
        info "Installing FFmpeg..."
        install_ffmpeg
    fi

    # -- pipx (for isolated install) --
    if ! has pipx; then
        info "Installing pipx..."
        if [[ "$PLATFORM" == "macos" ]] && has brew; then
            brew install pipx
        elif [[ "$PLATFORM" == "linux" ]]; then
            if has apt-get; then
                sudo apt-get install -y -qq pipx
            elif has dnf; then
                sudo dnf install -y pipx
            else
                python3 -m pip install --user --break-system-packages pipx 2>/dev/null \
                    || python3 -m pip install --user pipx 2>/dev/null \
                    || true
            fi
        fi
        pipx ensurepath 2>/dev/null || true
        export PATH="$HOME/.local/bin:$PATH"
    fi
    if has pipx; then ok "pipx"; fi
}

install_python() {
    if [[ "$PLATFORM" == "macos" ]]; then
        if has brew; then
            info "Installing Python via Homebrew..."
            brew install python@3.12
        else
            fail "Please install Python 3.10+ first: https://www.python.org/downloads/"
        fi
    else
        if has apt-get; then
            info "Installing Python via apt..."
            sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip python3-venv
        elif has dnf; then
            info "Installing Python via dnf..."
            sudo dnf install -y python3 python3-pip
        elif has pacman; then
            info "Installing Python via pacman..."
            sudo pacman -S --noconfirm python python-pip
        else
            fail "Please install Python 3.10+ first: https://www.python.org/downloads/"
        fi
    fi
    ok "Python installed"
}

install_ffmpeg() {
    if [[ "$PLATFORM" == "macos" ]]; then
        if has brew; then
            brew install ffmpeg
        else
            fail "Please install FFmpeg: brew install ffmpeg"
        fi
    else
        if has apt-get; then
            sudo apt-get update -qq && sudo apt-get install -y -qq ffmpeg
        elif has dnf; then
            sudo dnf install -y ffmpeg
        elif has pacman; then
            sudo pacman -S --noconfirm ffmpeg
        else
            fail "Please install FFmpeg manually: https://ffmpeg.org/download.html"
        fi
    fi
    ok "FFmpeg installed"
}

# ── Install Takone ───────────────────────────────────────────
install_takone() {
    local INSTALL_DIR="${TAKONE_INSTALL_DIR:-$HOME/.takone}"

    if [[ "$LOCAL_MODE" == true ]]; then
        # --local: install from current directory (dev mode)
        local SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        info "Installing from local source: $SRC_DIR"
        INSTALL_DIR="$SRC_DIR"
    elif [[ -d "$INSTALL_DIR" ]]; then
        info "Updating existing installation at $INSTALL_DIR..."
        cd "$INSTALL_DIR"
        git reset --hard HEAD --quiet 2>/dev/null || true
        git pull --quiet
    else
        info "Cloning Takone..."
        git clone --quiet https://github.com/wormholeportal/takone.git "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi

    # Install with pipx (editable) or fallback to venv
    info "Installing Takone package..."
    if has pipx; then
        pipx install -e "$INSTALL_DIR[all]" --force 2>/dev/null || {
            info "pipx failed, falling back to venv..."
            pip_install "$INSTALL_DIR"
        }
    else
        pip_install "$INSTALL_DIR"
    fi

    ok "Takone installed"

    # Install Playwright Chromium
    info "Installing Chromium browser (for web research)..."
    playwright install chromium 2>/dev/null && ok "Chromium installed" || warn "Chromium install failed — run 'playwright install chromium' manually"

    # Ensure ~/.takone/.env exists (standard config location)
    local CONFIG_DIR="$HOME/.takone"
    mkdir -p "$CONFIG_DIR"
    if [[ ! -f "$CONFIG_DIR/.env" && -f "$INSTALL_DIR/.env.example" ]]; then
        cp "$INSTALL_DIR/.env.example" "$CONFIG_DIR/.env"
        warn "Created .env from template — edit ${BOLD}$CONFIG_DIR/.env${RESET} to add your API keys"
    fi
}

pip_install() {
    local dir="$1"
    python3 -m venv "$dir/.venv"
    # Upgrade pip first (Python 3.14 bundles an old pip that breaks build isolation)
    "$dir/.venv/bin/python" -m pip install --upgrade pip --quiet 2>/dev/null || true
    "$dir/.venv/bin/pip" install --upgrade "setuptools>=75.0" wheel --quiet
    # --no-build-isolation: use the venv's setuptools directly, avoids the
    # "Cannot import setuptools.backends._legacy" crash on Python 3.14
    "$dir/.venv/bin/pip" install --no-build-isolation -e "$dir[all]" --quiet

    # Create wrapper script
    local BIN_DIR="$HOME/.local/bin"
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/takone" << WRAPPER
#!/usr/bin/env bash
exec "$dir/.venv/bin/takone" "\$@"
WRAPPER
    chmod +x "$BIN_DIR/takone"

    # Ensure ~/.local/bin is in PATH
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        add_to_path "$BIN_DIR"
    fi
}

add_to_path() {
    local bin_dir="$1"
    local shell_rc=""

    if [[ -n "${ZSH_VERSION:-}" ]] || [[ "$SHELL" == *"zsh"* ]]; then
        shell_rc="$HOME/.zshrc"
    elif [[ -n "${BASH_VERSION:-}" ]] || [[ "$SHELL" == *"bash"* ]]; then
        shell_rc="$HOME/.bashrc"
    fi

    if [[ -n "$shell_rc" ]]; then
        echo "" >> "$shell_rc"
        echo "# Takone" >> "$shell_rc"
        echo "export PATH=\"$bin_dir:\$PATH\"" >> "$shell_rc"
        info "Added $bin_dir to PATH in $shell_rc"
    fi

    export PATH="$bin_dir:$PATH"
}

# ── Parse args ────────────────────────────────────────────────
LOCAL_MODE=false
if [[ "${1:-}" == "--local" ]]; then
    LOCAL_MODE=true
fi

# ── Main ─────────────────────────────────────────────────────
main() {
    install_deps
    install_takone

    echo ""
    echo -e "${GREEN}${BOLD}  ✅ Takone is ready!${RESET}"
    echo ""
    echo -e "  ${BOLD}Get started:${RESET}"
    echo -e "    ${YELLOW}1.${RESET} Edit your API keys:  ${DIM}~/.takone/.env${RESET}"
    echo -e "    ${YELLOW}2.${RESET} Launch:              ${CYAN}${BOLD}takone${RESET}"
    echo ""
    echo -e "  ${DIM}Documentation: https://github.com/wormholeportal/takone${RESET}"
    echo ""

    # Hint to reload shell if PATH was modified
    if ! has takone; then
        warn "Restart your terminal or run: ${BOLD}source ~/.zshrc${RESET}"
    fi
}

main "$@"
