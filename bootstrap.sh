#!/usr/bin/env bash

# bootstrap.sh - System setup and dotfiles installation
# Handles Homebrew (macOS), Core Tools (Linux), and Dotty integration.

set -e

# Configuration
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BREWFILE_JSON="$REPO_DIR/home/.config/brewfile.json"

# Colors
BLUE='\033[1;34m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
RESET='\033[0m'

say() { echo -e "${BLUE}===>${RESET} $1"; }
success() { echo -e "${GREEN}[success]${RESET} $1"; }
warn() { echo -e "${YELLOW}[warn]${RESET} $1"; }
error() { echo -e "${RED}[error]${RESET} $1" >&2; }

# --- Shared Setup ---
install_tpm() {
    if [ ! -d "$HOME/.tmux/plugins/tpm" ]; then
        say "Installing Tmux Plugin Manager (TPM)..."
        git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm
    else
        success "TPM already installed"
    fi
}

# --- macOS Setup ---
install_homebrew() {
    if ! command -v brew >/dev/null 2>&1; then
        say "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # Add brew to path for immediate use
        if [[ -f /opt/homebrew/bin/brew ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -f /usr/local/bin/brew ]]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
    else
        success "Homebrew already installed"
    fi
}

setup_macos() {
    say "Starting macOS setup..."

    install_homebrew

    say "Installing foundational tools..."
    brew install mas

    # Install brewfile tool
    if ! command -v brewfile >/dev/null 2>&1; then
        say "Installing brewfile tool..."
        brew tap waltermwaniki/brewfile
        brew install brewfile
    fi

    # Run Dotty
    say "Setting up dotfiles..."
    "$REPO_DIR/dotty" install
    "$REPO_DIR/dotty" sync

    # Install TPM
    install_tpm

    # Run Brewfile
    if command -v brewfile >/dev/null 2>&1; then
        say "Running Brewfile to install packages..."
        brewfile || warn "Brewfile finished with warnings/errors"
    else
        warn "Brewfile command not found, skipping package installation"
    fi
}

# --- Linux Setup ---
install_linux_packages() {
    say "Installing core tools for Linux..."

    local packages="zsh tmux neovim fzf ripgrep bat tree curl git nodejs npm"
    # 'fd' is often 'fd-find' on Debian/Ubuntu

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [[ "$ID" == "ubuntu" || "$ID" == "debian" || "$ID_LIKE" == *"debian"* ]]; then
            sudo apt-get update
            sudo apt-get install -y $packages fd-find zsh-autosuggestions zsh-syntax-highlighting

            # Install GitHub CLI (gh) if missing
            if ! command -v gh >/dev/null 2>&1; then
                say "Installing GitHub CLI..."
                type -p curl >/dev/null || (sudo apt update && sudo apt install curl -y)
                curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
                && sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
                && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
                && sudo apt update \
                && sudo apt install gh -y
            fi

            # Symlink fdfind to fd if needed
            if ! command -v fd >/dev/null 2>&1 && command -v fdfind >/dev/null 2>&1; then
                 mkdir -p ~/.local/bin
                 ln -sf $(which fdfind) ~/.local/bin/fd
            fi
        elif [[ "$ID" == "rocky" || "$ID" == "rhel" || "$ID" == "centos" || "$ID_LIKE" == *"rhel"* ]]; then
            sudo dnf install -y epel-release
            sudo dnf install -y $packages fd-find zsh-autosuggestions zsh-syntax-highlighting gh
        else
            warn "Unsupported Linux distribution for auto-install: $ID"
            warn "Please manually install: $packages"
        fi
    fi
}

install_extra_tools() {
    say "Installing extra tools (Starship, uv, pnpm, zoxide)..."

    # Starship
    if ! command -v starship >/dev/null 2>&1; then
        say "Installing Starship..."
        curl -sS https://starship.rs/install.sh | sh -s -- -y
    fi

    # uv
    if ! command -v uv >/dev/null 2>&1; then
        say "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi

    # zoxide
    if ! command -v zoxide >/dev/null 2>&1; then
        say "Installing zoxide..."
        curl -sS https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | bash
    fi

    # pnpm
    if ! command -v pnpm >/dev/null 2>&1; then
        say "Installing pnpm..."
        curl -fsSL https://get.pnpm.io/install.sh | sh -
    fi

    # Curlie (via go install if go exists, otherwise skip for now as it has no simple script)
    if command -v go >/dev/null 2>&1 && ! command -v curlie >/dev/null 2>&1; then
        say "Installing curlie via go..."
        go install github.com/rs/curlie@latest
    fi
}

setup_linux() {
    say "Starting Linux setup..."

    # Run Dotty
    say "Setting up dotfiles..."
    "$REPO_DIR/dotty" install
    "$REPO_DIR/dotty" sync

    # Install Core Tools
    install_linux_packages
    install_extra_tools

    # Install TPM
    install_tpm

    # Print Brewfile for reference
    if [ -f "$BREWFILE_JSON" ]; then
        say "Printing brewfile.json for reference (install these manually if needed):"
        echo "---------------------------------------------------"
        cat "$BREWFILE_JSON"
        echo "---------------------------------------------------"
    fi
}

# --- Main ---
main() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        setup_macos
    else
        setup_linux
    fi

    echo ""
    success "Bootstrap complete!"
    "$REPO_DIR/dotty" status
}

main "$@"
