# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Repository Overview

This is a **dotfiles repository** that uses **GNU Stow** for symlink management. It provides a unified approach to managing shell configurations, application settings, and development environment setup across macOS and Linux systems.

### Architecture

- **`home/`** - Contains all dotfiles that mirror the `$HOME` directory structure
- **`bootstrap.py`** - Modern Python-based bootstrap script with enhanced features
- **`brewfile.py`** - Source for the brewfile utility (deployed by bootstrap)
- **`bootstrap.sh`** - Legacy Bash bootstrap script
- **`Brewfile`** + **`Brewfile.extra`** - Homebrew package management via Bundle
- **`home/.local/bin/brewfile`** - Modern Python-based Brewfile manager (deployed from brewfile.py)
- **`home/.local/bin/brewfile.sh`** - Legacy Bash version (deprecated)

## Bootstrap Process

The bootstrap script follows a logical four-step process for setting up a new machine:

1. **Install package manager** (Homebrew on macOS) - Ensures package manager is available
2. **Deploy package management utility** - Copies `brewfile.py` to `home/.local/bin/brewfile`
3. **Install packages** - Uses the deployed utility to install all dependencies including GNU Stow
4. **Apply dotfiles** - Uses Stow to create symlinks to your configurations

This sequence ensures all dependencies are met before attempting to apply dotfiles.

## Common Commands

### Initial Setup
```bash
# Clone and bootstrap the entire development environment
git clone <repo-url> "$HOME/.dotfiles"
cd "$HOME/.dotfiles"
./bootstrap.py setup
```

### Complete System Setup
```bash
# Full setup (packages + dotfiles)
./bootstrap.py setup                # Complete setup
./bootstrap.py setup --preview      # Preview all operations
./bootstrap.py setup --skip-packages  # Only dotfiles
./bootstrap.py setup --skip-dotfiles   # Only packages
./bootstrap.py setup --adopt        # Adopt existing files
```

### Individual Components
```bash
# Package management only
./bootstrap.py packages             # Install all packages
./bootstrap.py packages --preview   # Preview package operations

# Dotfiles management only
./bootstrap.py dotfiles             # Apply dotfiles
./bootstrap.py dotfiles --preview   # Preview dotfiles operations
./bootstrap.py dotfiles --restow    # Re-apply after changes
./bootstrap.py dotfiles --adopt     # Adopt existing files

# Utility deployment
./bootstrap.py deploy               # Deploy brewfile + dotfiles utilities

# System status
./bootstrap.py status               # Show current bootstrap state
```

### Package Management

Use the deployed `brewfile` utility for package management:

```bash
brewfile install                    # Install all packages
brewfile install --include extra    # Include Brewfile.extra
brewfile status                     # Show dependencies with install status
brewfile status --include extra     # Include extra files
brewfile sync                       # Install + cleanup in one command
brewfile dump                       # Update Brewfile from system (append)
brewfile dump --force               # Overwrite Brewfile completely
brewfile cleanup                    # Interactive cleanup of unused packages
brewfile add <package>              # Install and add package to Brewfile
brewfile add <package> --to extra   # Add to Brewfile.extra
brewfile remove <package>           # Interactive removal from Brewfile
brewfile edit                       # Open Brewfile in $EDITOR
```

### Dotfiles Management

Use the deployed `dotfiles` utility for quick dotfiles operations:

```bash
dotfiles status                     # Show dotfiles status
dotfiles restow                     # Re-apply from remembered location
dotfiles conflicts                  # Check for stow conflicts
```

### Shell Environment
```bash
# Reload shell configuration
source ~/.zshrc
# or use the alias
src~
```

## Key Development Features

### Shell Enhancements
- **Starship prompt** with custom configuration
- **fzf** integration with `fd` for fast file/directory search
- **zoxide** for intelligent directory jumping (`cd` command replacement)
- **Python virtual environment** helper (`pyactivate` or `venv` alias)

### Useful Aliases & Functions
- `fcd` - Interactive directory navigation with fzf + preview
- `fzfp` - fzf with bat preview
- Standard navigation: `..`, `...`, `....`, etc.
- Git shortcuts: `g`, `gs`, `gd`, `gb`, `gm`
- `cat` → `bat` (syntax highlighting)
- `vim` → `nvim`

## Advanced Brewfile Management

The repository includes a sophisticated Brewfile management system:

### Key Features
- **Interactive package management**: Add/remove packages with confirmation prompts
- **Installation status tracking**: Shows which declared packages are actually installed
- **Smart package placement**: Automatically detects whether packages are formulae or casks
- **Comprehensive listing**: Groups packages by type with visual install status indicators
- **Sync command**: One-step install + cleanup workflow
- **Split configurations**: Main `Brewfile` + optional `Brewfile.extra` for different package sets
- **Smart dumping**: Preserves existing package organization when updating from system state
- **Cleanup detection**: Identifies packages installed on system but not in Brewfiles
- **Include system**: Mix and match different Brewfile configurations

### Recommended Workflows
```bash
# Daily workflow
brewfile status --include extra     # Check status of all packages
brewfile sync --include extra       # Install missing + remove unused

# Adding new packages
brewfile add neovim                 # Install and add to main Brewfile
brewfile add steam --to extra       # Install and add to Brewfile.extra

# Maintenance
brewfile cleanup --include extra    # Interactive cleanup with confirmation
```

## File Organization Logic

### Stow Structure
The `home/` directory mirrors your actual home directory:
- `home/.zshrc` → `~/.zshrc`
- `home/.config/nvim/init.lua` → `~/.config/nvim/init.lua`
- `home/.local/bin/brewfile.sh` → `~/.local/bin/brewfile.sh`

### Configuration Loading
Shell configurations are modular:
1. `.zshenv` - Environment setup
2. `.zprofile` - Login shell setup  
3. `.zshrc` - Interactive shell (sources `.aliases` and `.exports`)

## Best Practices for This Repository

### When Adding New Dotfiles
1. Place files in `home/` maintaining the directory structure
2. Test with `stow -nv -t "$HOME" home` (preview mode) first
3. Apply with `stow -v -t "$HOME" home`

### When Adding New Packages
1. Install normally: `brew install <package>`
2. Update Brewfile: `brewfile dump --include extra` (appends to Brewfile.extra)
3. Or for main packages: `brewfile dump` (appends to main Brewfile)

### When Modifying Brewfile Utility
1. Edit the source file: `brewfile.py` in the repository root
2. Test changes by running `python3 brewfile.py <command>`
3. Deploy to dotfiles: `./bootstrap.py` will copy `brewfile.py` → `home/.local/bin/brewfile`

### System Maintenance
- Use `brewfile cleanup --include extra` regularly to identify unused packages
- The bootstrap script handles cross-platform Stow installation automatically
- Brewfile management supports both incremental updates and complete rebuilds

## Shell Environment Context

This dotfiles setup assumes:
- **zsh** as the primary shell
- **Homebrew** package management on macOS
- **GNU Stow** for symlink management
- Development tools: Python (via uv), Node.js (via pnpm), Neovim, Git
- Terminal enhancements: fzf, zoxide, starship, bat, ripgrep
