#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./bootstrap.sh                 # defaults to $HOME
#   ./bootstrap.sh /some/otherdir  # custom target dir
#   ./bootstrap.sh --preview       # only show what would change (no stowing)
#   ./bootstrap.sh --adopt         # supports --adopt flag
#   ./bootstrap.sh -h|--help       # show help

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG=home

say() { printf "\033[1;34m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[warn]\033[0m %s\n" "$*"; }

# --- argument parsing ---
PREVIEW=0
ADOPT=0
TARGET_ARG=""

print_help() {
  cat <<'EOF'
Usage: ./bootstrap.sh [--preview] [--adopt] [TARGET_DIR]

Options:
  --preview     Only preview the stow operations and exit
  --adopt       Use `stow --adopt` to pull existing files into the repo
  -h, --help    Show this help

Examples:
  ./bootstrap.sh                # stow into $HOME
  ./bootstrap.sh --preview      # dry-run only
  ./bootstrap.sh --adopt        # adopt existing files
  ./bootstrap.sh /tmp/test      # target /tmp/test
EOF
}

parse_args() {
  while (( "$#" )); do
    case "$1" in
      --preview)
        PREVIEW=1; shift ;;
      --adopt)
        ADOPT=1; shift ;;
      -h|--help)
        print_help; exit 0 ;;
      --)
        shift; break ;;
      -*)
        warn "Unknown option: $1"; print_help; exit 2 ;;
      *)
        if [[ -z "$TARGET_ARG" ]]; then
          TARGET_ARG="$1"; shift
        else
          warn "Unexpected extra argument: $1"; print_help; exit 2
        fi ;;
    esac
  done
}

detect_os() {
  if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if command -v dnf >/dev/null 2>&1; then echo "fedora"; return; fi
    if command -v apt-get >/dev/null 2>&1; then echo "debian"; return; fi
    if command -v pacman >/dev/null 2>&1; then echo "arch"; return; fi
    echo "linux"
  elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "macos"
  else
    echo "unknown"
  fi
}

install_stow() {
  if command -v stow >/dev/null 2>&1; then
    say "GNU Stow already installed."
    return
  fi

  local os="$1"
  case "$os" in
    fedora|linux) sudo dnf install -y stow || true ;;
    debian) sudo apt-get update && sudo apt-get install -y stow ;;
    arch) sudo pacman -S --noconfirm stow ;;
    macos) brew install stow ;;
    *) warn "Please install GNU Stow manually.";;
  esac
}

main() {
  local target
  target="${TARGET_ARG:-$HOME}"

  if [[ ! -d "$target" ]]; then
    say "Target directory $target does not exist. Creating it."
    mkdir -p "$target"
  fi

  local os
  os=$(detect_os)

  say "Bootstrapping dotfiles..."
  say "Detected OS: $os"
  install_stow "$os"
  say "Repository directory: $REPO_DIR"
  say "Target directory: $target"
  cd "$REPO_DIR"

  if [[ "$PREVIEW" == "1" ]]; then
    say "Previewing → target: $target"
    PREVIEW_ARGS=(-nv -t "$target")
    if [[ "$ADOPT" == "1" ]]; then
      PREVIEW_ARGS=(--adopt "${PREVIEW_ARGS[@]}")
    fi
    stow "${PREVIEW_ARGS[@]}" "$PKG"
    say "Preview-only mode; exiting without applying changes."
    return 0
  fi

  ARGS=(-v -t "$target")
  if [[ "$ADOPT" == "1" ]]; then
    ARGS=(--adopt "${ARGS[@]}")
  fi

  say "Applying"
  stow "${ARGS[@]}" "$PKG"
  say "Done. Restart your shell or source your rc files."
}

parse_args "$@"
main
