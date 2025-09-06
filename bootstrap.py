#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bootstrap.py — A Python-based dotfiles bootstrap script using GNU Stow.

This script provides the same functionality as bootstrap.sh but with improved
error handling, cross-platform support, and cleaner output.
"""

import argparse
import os
import platform
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


class DotfilesBootstrap:
    """Handles dotfiles bootstrapping using GNU Stow."""

    def __init__(self):
        self.repo_dir = self._resolve_repo_dir()
        self.package = "home"
        self.os_type = self._detect_os()

    def _resolve_repo_dir(self):
        """Resolves the repository directory from the script's location."""
        try:
            return Path(__file__).resolve().parent
        except NameError:
            return Path.cwd()

    def _detect_os(self):
        """Detects the operating system type."""
        system = platform.system().lower()
        if system == "darwin":
            return "macos"
        elif system == "linux":
            # Try to determine the Linux distribution
            if shutil.which("dnf"):
                return "fedora"
            elif shutil.which("apt-get"):
                return "debian"
            elif shutil.which("pacman"):
                return "arch"
            else:
                return "linux"
        else:
            return "unknown"

    def _check_stow_installed(self):
        """Checks if GNU Stow is installed."""
        return shutil.which("stow") is not None

    def _install_stow(self):
        """Installs GNU Stow based on the detected OS."""
        if self._check_stow_installed():
            say("GNU Stow is already installed.")
            return True

        say(f"Detected OS: {self.os_type}")
        say("Installing GNU Stow...")

        try:
            if self.os_type == "macos":
                subprocess.run(["brew", "install", "stow"], check=True)
            elif self.os_type == "fedora":
                subprocess.run(["sudo", "dnf", "install", "-y", "stow"], check=True)
            elif self.os_type == "debian":
                subprocess.run(["sudo", "apt-get", "update"], check=True)
                subprocess.run(["sudo", "apt-get", "install", "-y", "stow"], check=True)
            elif self.os_type == "arch":
                subprocess.run(["sudo", "pacman", "-S", "--noconfirm", "stow"], check=True)
            else:
                warn("Unknown OS. Please install GNU Stow manually.")
                return False

            success("GNU Stow installed successfully.")
            return True

        except subprocess.CalledProcessError as e:
            error(f"Failed to install GNU Stow: {e}")
            return False
        except FileNotFoundError:
            error(f"Package manager not found for {self.os_type}. Please install GNU Stow manually.")
            return False

    def _validate_target_directory(self, target):
        """Validates and creates the target directory if needed."""
        target_path = Path(target).expanduser().resolve()
        
        if not target_path.exists():
            say(f"Target directory {target_path} does not exist. Creating it...")
            try:
                target_path.mkdir(parents=True, exist_ok=True)
                success(f"Created target directory: {target_path}")
            except PermissionError:
                die(f"Permission denied creating {target_path}")
            except OSError as e:
                die(f"Failed to create {target_path}: {e}")
        
        return target_path

    def _run_stow_command(self, args, target):
        """Runs a stow command with the given arguments."""
        cmd = ["stow"] + args + ["-t", str(target), self.package]
        
        try:
            say(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, cwd=self.repo_dir, capture_output=True, text=True)
            
            if result.stdout:
                print(result.stdout)
            
            if result.returncode != 0:
                error(f"Stow command failed with exit code {result.returncode}")
                if result.stderr:
                    print(result.stderr, file=sys.stderr)
                return False
            
            return True
            
        except subprocess.CalledProcessError as e:
            error(f"Failed to run stow command: {e}")
            return False
        except FileNotFoundError:
            die("GNU Stow not found. Please install it first.")

    def preview(self, target, adopt=False):
        """Preview what stow would do without making changes."""
        target_path = self._validate_target_directory(target)
        
        say(f"Previewing changes for target: {target_path}")
        
        args = ["-n", "-v"]  # -n for dry-run, -v for verbose
        if adopt:
            args.append("--adopt")
        
        success = self._run_stow_command(args, target_path)
        
        if success:
            say("Preview completed. No changes were made.")
        
        return success

    def apply(self, target, adopt=False):
        """Apply the dotfiles using stow."""
        target_path = self._validate_target_directory(target)
        
        say(f"Applying dotfiles to target: {target_path}")
        say(f"Repository directory: {self.repo_dir}")
        
        args = ["-v"]  # -v for verbose
        if adopt:
            args.append("--adopt")
            warn("Using --adopt mode. Existing files will be moved into the repository!")
        
        success = self._run_stow_command(args, target_path)
        
        if success:
            success("Dotfiles applied successfully!")
            say("You may need to restart your shell or source your RC files to see changes.")
        
        return success

    def restow(self, target):
        """Re-apply dotfiles after making changes."""
        target_path = self._validate_target_directory(target)
        
        say(f"Re-applying dotfiles to target: {target_path}")
        
        args = ["-R", "-v"]  # -R for restow, -v for verbose
        
        success = self._run_stow_command(args, target_path)
        
        if success:
            success("Dotfiles re-applied successfully!")
        
        return success

    def bootstrap(self, target="~", preview_only=False, adopt=False):
        """Main bootstrap function."""
        say("Starting dotfiles bootstrap...")
        
        # Install stow if needed
        if not self._install_stow():
            die("Cannot proceed without GNU Stow")
        
        # Expand and resolve target path
        target_path = Path(target).expanduser().resolve()
        
        if preview_only:
            return self.preview(target_path, adopt)
        else:
            return self.apply(target_path, adopt)


def main():
    """Main function and argument parser."""
    parser = argparse.ArgumentParser(
        description="Bootstrap dotfiles using GNU Stow",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    
    parser.add_argument(
        "target",
        nargs="?",
        default="~",
        help="Target directory for dotfiles (default: ~)",
    )
    
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Only preview the stow operations and exit",
    )
    
    parser.add_argument(
        "--adopt",
        action="store_true",
        help="Use 'stow --adopt' to pull existing files into the repo",
    )
    
    parser.add_argument(
        "--restow",
        action="store_true",
        help="Re-apply dotfiles after making changes",
    )

    args = parser.parse_args()
    
    bootstrap = DotfilesBootstrap()
    
    try:
        if args.restow:
            success = bootstrap.restow(args.target)
        else:
            success = bootstrap.bootstrap(
                target=args.target,
                preview_only=args.preview,
                adopt=args.adopt,
            )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\nBootstrap interrupted by user.")
        sys.exit(1)
    except Exception as e:
        die(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
