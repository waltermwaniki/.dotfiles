# Dotfiles (GNU Stow)

This repository manages dotfiles using **GNU Stow** via the `dotty` tool. All your dotfiles are organized under a single `home/` package that mirrors the `$HOME` directory structure.

## Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/waltermwaniki/dotfiles.git ~/.dotfiles
cd ~/.dotfiles
```

### 2. Install Dotty
Installs the `dotty` CLI to `~/.local/bin/dotty` and ensures `stow` is installed.

```bash
./dotty install
```

### 3. Sync Dotfiles
Applies your dotfiles to `$HOME`.

```bash
dotty sync
```

## Dotty CLI

`dotty` is a simple wrapper around GNU Stow that handles cross-platform installation and management.

- **`dotty status`**: Check status of dotfiles (conflicts, broken links).
- **`dotty sync`**: Apply dotfiles. Use `--force` to adopt existing files (overwrite repo with local).
- **`dotty clean`**: Remove all dotfiles symlinks.
- **`dotty install`**: Install `dotty` to PATH and install `stow` if missing.

## System Setup (Bootstrap)

For system-wide setup (Homebrew, Brewfile, etc.), use the bootstrap script:

```bash
./bootstrap.sh
```

This script manages:
- Homebrew installation (macOS)
- Brewfile bundle installation (macOS)
- Core CLI tools installation (Linux)
- Dotty setup

## OS Support

`dotty` automatically installs `stow` on:
- **macOS** (via Homebrew)
- **Ubuntu/Debian** (via apt)
- **Rocky/RHEL** (via dnf/EPEL)
- **Windows** (via **WSL** only)

> **Windows Users**: Please use [WSL (Windows Subsystem for Linux)](https://learn.microsoft.com/en-us/windows/wsl/install). Native Windows is not supported.

## Layout

```txt
.dotfiles/
├─ home/              # mirrors your $HOME directory structure
├─ dotty              # dotfiles management tool
├─ bootstrap.sh       # system setup orchestrator
└─ .gitignore
```
