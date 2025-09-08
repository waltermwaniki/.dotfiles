# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Repository Overview

This is a **dotfiles repository** that uses **GNU Stow** for symlink management. It provides a unified approach to managing shell configurations, application settings, and development environment setup across **macOS and Linux systems**.

### Architecture

- **`home/`** - Contains all dotfiles that mirror the `$HOME` directory structure
- **`bootstrap.py`** - Modern Python-based bootstrap script with enhanced features
- **`brewfile.py`** - Source for the brewfile utility (symlinked to `~/.local/bin/brewfile`)
- **`aptfile.py`** - Source for the aptfile utility (symlinked to `~/.local/bin/aptfile`)
- **`bootstrap.sh`** - Legacy Bash bootstrap script
- **`~/.config/brewfile.json`** - Modern JSON-based package configuration (macOS)
- **`~/Brewfile`** - Generated Brewfile for brew bundle (macOS)
- **`Aptfile`** + **`Dnffile`** - Linux package management for Ubuntu and Rocky Linux
- **`home/.local/bin/brewfile`** - Modern Python-based Brewfile manager (macOS)
- **`home/.local/bin/aptfile`** - Modern Python-based Linux package manager (Linux)
- **`home/.local/bin/brewfile.sh`** - Legacy Bash version (deprecated)

## Bootstrap Process

The bootstrap script follows a logical four-step process for setting up a new machine:

1. **Install package manager** (Homebrew on macOS, apt/dnf on Linux) - Ensures package manager is available
2. **Deploy package management utility** - Symlinks platform-specific utility (`brewfile.py` or `aptfile.py`)
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

#### macOS (Homebrew)
Use the deployed `brewfile` utility for package management:

```bash
brewfile status                     # Show package status and what needs to be installed/removed
brewfile install                    # Install missing packages (interactive)
brewfile cleanup                    # Remove extra packages (interactive)
brewfile sync                       # Install missing + remove extra packages (interactive)
brewfile add <package>              # Install and add package to configuration
brewfile remove <package>           # Remove package from configuration
brewfile init                       # Initialize configuration for new machine
brewfile generate                   # Generate ~/Brewfile from configuration
```

#### Linux (apt/dnf/yum)
Use the deployed `aptfile` utility for package management:

```bash
aptfile install                     # Install all packages from Aptfile/Dnffile
aptfile status                      # Show package installation status
aptfile add <package>               # Install and add package to package file
aptfile remove <package>            # Interactive removal from package file
aptfile edit                        # Open package file in $EDITOR
aptfile path                        # Show path to package file
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
brewfile status                     # Check status of all packages and groups
brewfile sync                       # Install missing + remove extra packages (interactive)

# Adding new packages
brewfile add neovim                 # Install and add to machine configuration
brewfile add steam                  # Automatically placed in appropriate group

# Maintenance
brewfile cleanup                    # Interactive cleanup with confirmation
brewfile generate                   # Regenerate ~/Brewfile from JSON config
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
1. Use brewfile: `brewfile add <package>` (automatically installs and adds to config)
2. Or install normally: `brew install <package>`, then `brewfile adopt` to add to config
3. Run `brewfile generate` to update ~/Brewfile from the JSON configuration

### When Modifying Brewfile Utility
1. Edit the source file: `brewfile.py` in the repository root
2. Test changes by running `python3 brewfile.py <command>`
3. **No deployment needed**: `home/.local/bin/brewfile` is automatically symlinked to the source via stow

### System Maintenance
- Use `brewfile cleanup` regularly to identify unused packages
- The bootstrap script handles cross-platform Stow installation automatically
- Brewfile management supports both incremental updates and complete rebuilds

## Shell Environment Context

This dotfiles setup assumes:
- **zsh** as the primary shell
- **Homebrew** package management on macOS, **apt/dnf** on Linux
- **GNU Stow** for symlink management
- Development tools: Python, Node.js, Neovim, Git
- Terminal enhancements: fzf, zoxide, starship, bat, ripgrep
