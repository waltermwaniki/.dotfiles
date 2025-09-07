#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bootstrap.py — Interactive development environment setup orchestrator.

Provides a unified interface for managing packages (via brewfile) and dotfiles,
with system status overview and guided delegation to specialized tools.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ANSI colors (respect NO_COLOR and non-TTY)
BLUE = "\033[1;34m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
GREEN = "\033[1;32m"
RESET = "\033[0m"

if "NO_COLOR" in os.environ or not sys.stdout.isatty():
    BLUE = YELLOW = RED = GREEN = RESET = ""


def say(msg):
    """Prints a message to the console with a blue '===>' prefix."""
    print(f"{BLUE}===>{RESET} {msg}")


def warn(msg):
    """Prints a warning message to the console."""
    print(f"{YELLOW}[warn]{RESET} {msg}")


def error(msg):
    """Prints an error message to the console."""
    print(f"{RED}[error]{RESET} {msg}", file=sys.stderr)


def success(msg):
    """Prints a success message to the console."""
    print(f"{GREEN}[success]{RESET} {msg}")


def die(msg):
    """Prints an error message and exits the script."""
    error(msg)
    sys.exit(1)


class BootstrapOrchestrator:
    """Orchestrates the development environment setup by delegating to specialized tools."""
    
    def __init__(self):
        self.repo_dir = self._resolve_repo_dir()
        
    def _resolve_repo_dir(self):
        """Resolves the git repository root from the script's location."""
        try:
            return Path(__file__).resolve().parent
        except NameError:
            return Path.cwd()
    
    def _check_homebrew_installed(self):
        """Check if Homebrew is installed (macOS)."""
        return shutil.which("brew") is not None
    
    def _check_stow_installed(self):
        """Check if GNU Stow is installed."""
        return shutil.which("stow") is not None
    
    def _check_brewfile_available(self):
        """Check if brewfile utility is available."""
        brewfile_path = self.repo_dir / "brewfile.py"
        return brewfile_path.exists()
    
    def _check_dotfiles_available(self):
        """Check if dotfiles.py is available."""
        dotfiles_path = self.repo_dir / "dotfiles.py"
        return dotfiles_path.exists()
    
    def _is_brewfile_functional(self):
        """Check if brewfile utility is functional (can run without errors)."""
        if not self._check_brewfile_available():
            return False
        
        try:
            # Just check if it can run - don't parse complex output
            result = subprocess.run(
                [sys.executable, str(self.repo_dir / "brewfile.py"), "status"],
                capture_output=True,
                text=True,
                cwd=self.repo_dir,
                timeout=30  # Prevent hanging
            )
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def _is_dotfiles_functional(self):
        """Check if dotfiles utility is functional."""
        if not self._check_stow_installed() or not self._check_dotfiles_available():
            return False
        
        try:
            # Just check if dotfiles.py can run - let it handle its own status
            result = subprocess.run(
                [sys.executable, str(self.repo_dir / "dotfiles.py")],
                capture_output=True,
                text=True,
                cwd=self.repo_dir,
                timeout=10,  # Shorter timeout since it's interactive
                input="q\n"  # Send quit command to exit gracefully
            )
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def _print_system_status(self):
        """Print simple system status focusing on what's available."""
        print(f"\n{BLUE}Development Environment Status:{RESET}")
        
        # Check package manager
        if not self._check_homebrew_installed():
            print(f"  ! Package manager missing (install Homebrew first)")
            return False
        print(f"  ✓ Package manager installed (Homebrew)")
        
        # Check package management
        if self._is_brewfile_functional():
            print(f"  ✓ Package management ready")
        else:
            print(f"  ! Package management needs attention")
        
        # Check dotfiles management
        if self._is_dotfiles_functional():
            print(f"  ✓ Dotfiles management ready")
        else:
            print(f"  ! Dotfiles management needs attention")
        
        return True
    
    def _launch_brewfile(self):
        """Launch the interactive brewfile tool."""
        try:
            say("Launching package management...")
            brewfile_cmd = [sys.executable, str(self.repo_dir / "brewfile.py")]
            result = subprocess.run(brewfile_cmd, cwd=self.repo_dir)
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            error(f"Failed to launch package management: {e}")
            return False
    
    def _launch_dotfiles(self):
        """Launch the interactive dotfiles tool."""
        try:
            say("Launching dotfiles management...")
            dotfiles_cmd = [sys.executable, str(self.repo_dir / "dotfiles.py")]
            result = subprocess.run(dotfiles_cmd, cwd=self.repo_dir)
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            error(f"Failed to launch dotfiles management: {e}")
            return False
    
    def _show_detailed_status(self):
        """Show detailed status by delegating to specialized tools."""
        say("Showing detailed status from specialized tools...")
        
        # Delegate to brewfile for package status
        if self._is_brewfile_functional():
            print(f"\n{YELLOW}Package Status (via brewfile):{RESET}")
            try:
                result = subprocess.run(
                    [sys.executable, str(self.repo_dir / "brewfile.py"), "status"],
                    cwd=self.repo_dir,
                    timeout=30
                )
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                error("Failed to get package status")
        else:
            print(f"\n{YELLOW}Package Status:{RESET}")
            print(f"  ! Package management not functional")
            print(f"  → Ensure Homebrew is installed and brewfile.py is available")
        
        # Delegate to dotfiles for dotfiles status
        if self._is_dotfiles_functional():
            print(f"\n{YELLOW}Dotfiles Status (via dotfiles utility):{RESET}")
            try:
                result = subprocess.run(
                    [sys.executable, str(self.repo_dir / "dotfiles.py")],
                    cwd=self.repo_dir,
                    timeout=10,
                    input="q\n",  # Quit after showing status
                    text=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                error("Failed to get dotfiles status")
        else:
            print(f"\n{YELLOW}Dotfiles Status:{RESET}")
            print(f"  ! Dotfiles management not functional")
            print(f"  → Ensure GNU Stow is installed and dotfiles.py is available")
    
    def cmd_interactive(self):
        """Main interactive bootstrap orchestrator - delegates to specialized tools."""
        # Print system status
        if not self._print_system_status():
            say("Please install Homebrew first: https://brew.sh")
            return
        
        # Simple delegation-based menu
        print(f"\nWhat would you like to manage?")
        menu_options = []
        option_num = 1
        
        # Always offer package management if brewfile is functional
        if self._is_brewfile_functional():
            print(f"  ({option_num}) Packages (interactive brewfile management)")
            menu_options.append(('packages', self._launch_brewfile))
            option_num += 1
        
        # Always offer dotfiles management if dotfiles is functional
        if self._is_dotfiles_functional():
            print(f"  ({option_num}) Dotfiles (interactive dotfiles management)")
            menu_options.append(('dotfiles', self._launch_dotfiles))
            option_num += 1
        
        # Always offer detailed status
        print(f"  ({option_num}) Show detailed status")
        menu_options.append(('status', self._show_detailed_status))
        
        print(f"  (q) Quit")
        
        try:
            choice = input("Enter your choice [q]: ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            choice = "q"
            print()
        
        if choice == "q" or choice == "":
            say("Goodbye!")
        elif choice.isdigit():
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(menu_options):
                _, action = menu_options[choice_idx]
                action()
            else:
                warn("Invalid choice.")
        else:
            warn("Invalid choice.")


def main():
    """Main function."""
    orchestrator = BootstrapOrchestrator()
    orchestrator.cmd_interactive()


if __name__ == "__main__":
    main()
