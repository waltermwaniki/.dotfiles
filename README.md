# Dotfiles (GNU Stow)

This repository manages dotfiles using **GNU Stow**. Instead of multiple top-level package directories, all your dotfiles are organized under a single `home/` package that mirrors the `$HOME` directory structure.

## Quick start

```bash
# Clone the repository
git clone <your-repo-url> "$HOME/dotfiles"
cd "$HOME/dotfiles"

# Run the bootstrap script to install stow (if needed) and set up your dotfiles
./bootstrap.sh
```

The bootstrap script runs the following commands internally:

```bash
# Preview what will be linked (no changes)
stow -nv -t "$HOME" home

# Apply (create symlinks in $HOME)
stow -v -t "$HOME" home

# Re-stow after edits
stow -Rvt "$HOME" home
```

> Tip: If you already have dotfiles in `$HOME`, consider backing them up first.
> `stow --adopt` can move existing files into this repo (be careful and commit often).

## Layout

```txt
.dotfiles/
├─ home/              # mirrors your $HOME directory structure
├─ home-macos/        # optional overlays for macOS
├─ home-linux/        # optional overlays for Linux
├─ .stow-local-ignore  # files that stow should ignore
├─ Makefile           # convenience commands
├─ bootstrap.sh       # optional one-shot setup helper
└─ .gitignore
```

## Common commands

- **Preview**: `stow -nv -t "$HOME" home`
- **Stow**: `stow -v -t "$HOME" home`
- **Re-stow**: `stow -Rv -t "$HOME" home`
- **Unstow**: `stow -Dv -t "$HOME" home`
- **Adopt existing files** (moves files from `$HOME` into repo): `stow --adopt -v -t "$HOME" home`

### Notes

- The directory tree inside `home/` should mirror your home directory.
  For example, `home/.config/nvim/init.lua` becomes `~/.config/nvim/init.lua`.
- You can use overlays like `home-macos/` or `home-linux/` for host- or OS-specific tweaks.
- Secrets: keep them **out** of git or use tools like `git-crypt` or `age`.
- See the `Makefile` for additional convenience commands.

## Installing GNU Stow manually

If you prefer to install GNU Stow manually, use the following commands for your OS:

```bash
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y stow

# Fedora/RHEL/CentOS/Rocky
sudo dnf install -y stow

# Arch
sudo pacman -S stow

# macOS (Homebrew)
brew install stow
```
