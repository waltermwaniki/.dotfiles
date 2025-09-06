#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bootstrap.py — A comprehensive development environment bootstrap system.

This script handles complete system setup including package managers, packages,
and dotfiles with backup management and persistent state tracking.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from datetime import datetime
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


class BaseBootstrap(ABC):
    """Abstract base class for dotfiles bootstrapping using GNU Stow."""

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

    @abstractmethod
    def install_package_manager_and_stow(self, preview_only=False):
        """Install the platform's package manager and GNU Stow (essential for all operations)."""
        pass

    @abstractmethod
    def install_packages(self, preview_only=False):
        """Install all packages including GNU Stow from Brewfile."""
        pass

    def _check_stow_installed(self):
        """Checks if GNU Stow is installed."""
        return shutil.which("stow") is not None

    def _get_state_file_path(self):
        """Get path to bootstrap state file."""
        return self.repo_dir / ".bootstrap.state.json"

    def _load_state(self):
        """Load bootstrap state from file."""
        state_file = self._get_state_file_path()
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                warn("Could not read bootstrap state file. Starting fresh.")
        
        # Default state
        return {
            "target_directory": None,
            "last_stow": None,
            "installed_packages": False,
            "deployed_utilities": [],
            "backup_directory": ".bootstrap.stow"
        }

    def _save_state(self, state):
        """Save bootstrap state to file."""
        state_file = self._get_state_file_path()
        try:
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except IOError as e:
            warn(f"Could not save bootstrap state: {e}")

    def _backup_existing_files(self, target, adopt=False):
        """Backup existing files that would conflict with stow."""
        if adopt:
            return True  # adopt mode handles conflicts differently
        
        target_path = Path(target).expanduser().resolve()
        backup_timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        backup_dir = target_path / ".bootstrap.stow" / backup_timestamp
        
        # Preview what stow would do to find conflicts
        cmd = ["stow", "-n", "-v", "-t", str(target_path), self.package]
        try:
            result = subprocess.run(cmd, cwd=self.repo_dir, capture_output=True, text=True)
            
            if "cannot stow" in result.stderr.lower():
                say(f"Creating backup directory: {backup_dir}")
                backup_dir.mkdir(parents=True, exist_ok=True)
                
                # Parse conflicts and backup files
                conflicts = self._parse_stow_conflicts(result.stderr)
                for conflict_file in conflicts:
                    source_file = target_path / conflict_file
                    if source_file.exists() and source_file.is_file():
                        backup_file = backup_dir / conflict_file
                        backup_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_file, backup_file)
                        say(f"Backed up: {conflict_file}")
                
                return True
            return True
            
        except subprocess.CalledProcessError as e:
            error(f"Failed to check for conflicts: {e}")
            return False

    def _parse_stow_conflicts(self, stderr_output):
        """Parse stow error output to find conflicting files."""
        conflicts = []
        for line in stderr_output.split('\n'):
            if "cannot stow" in line and "existing target" in line:
                # Extract filename from error message
                # Format: "cannot stow X over existing target Y"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "target" and i + 1 < len(parts):
                        conflict_file = parts[i + 1]
                        if conflict_file not in conflicts:
                            conflicts.append(conflict_file)
                        break
        return conflicts

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
        
        # Backup existing files unless adopting
        if not self._backup_existing_files(target_path, adopt):
            error("Failed to backup existing files")
            return False
        
        args = ["-v"]  # -v for verbose
        if adopt:
            args.append("--adopt")
            warn("Using --adopt mode. Existing files will be moved into the repository!")
        
        success = self._run_stow_command(args, target_path)
        
        if success:
            # Update state
            state = self._load_state()
            state["target_directory"] = str(target_path)
            state["last_stow"] = datetime.now().isoformat()
            self._save_state(state)
            
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

    @abstractmethod
    def deploy_package_manager_utility(self):
        """Deploy platform-specific package management utility."""
        pass

    @abstractmethod
    def deploy_stow_utility(self):
        """Deploy platform-aware stow management utility."""
        pass

    @abstractmethod
    def get_system_status(self):
        """Get current system status including packages and dotfiles."""
        pass

    def bootstrap(self, target="~", preview_only=False, adopt=False):
        """Main bootstrap function."""
        say("Starting dotfiles bootstrap...")
        
        # Step 1: Install package manager
        if not self.install_package_manager():
            die("Cannot proceed without package manager")
        
        # Step 2: Deploy package management utility
        if not self.deploy_package_manager_utility():
            die("Cannot proceed without package management utility")
        
        # Step 3: Install packages (includes GNU Stow)
        if not self.install_packages():
            die("Cannot proceed without required packages")
        
        # Step 4: Apply dotfiles with stow
        target_path = Path(target).expanduser().resolve()
        
        if preview_only:
            return self.preview(target_path, adopt)
        else:
            return self.apply(target_path, adopt)

    def setup_command(self, target="~", preview_only=False, adopt=False, skip_packages=False, skip_dotfiles=False):
        """Complete system setup command."""
        say("Starting complete system setup...")
        
        if not skip_packages:
            # Step 1: Install package manager and stow
            if not self.install_package_manager_and_stow(preview_only=preview_only):
                die("Cannot proceed without package manager and stow")
            
            # Step 2: Deploy package management utility
            if not self.deploy_package_manager_utility():
                die("Cannot proceed without package management utility")
            
            # Step 3: Install packages (includes GNU Stow)
            if not self.install_packages(preview_only=preview_only):
                die("Cannot proceed without required packages")
        
        if not skip_dotfiles:
            # Step 4: Deploy stow utility
            if not self.deploy_stow_utility():
                warn("Failed to deploy stow utility")
            
            # Step 5: Apply dotfiles with stow
            target_path = Path(target).expanduser().resolve()
            
            if preview_only:
                return self.preview(target_path, adopt)
            else:
                return self.apply(target_path, adopt)
        
        return True

    def packages_command(self, preview_only=False):
        """Package management only command."""
        say("Managing packages...")
        
        # Install package manager and stow
        if not self.install_package_manager_and_stow(preview_only=preview_only):
            return False
        
        # Deploy package management utility (needed for preview)
        if not self.deploy_package_manager_utility():
            return False
        
        # Install packages (with preview support)
        if not self.install_packages(preview_only=preview_only):
            return False
        
        # Update state
        state = self._load_state()
        state["installed_packages"] = True
        self._save_state(state)
        
        return True

    def dotfiles_command(self, target="~", preview_only=False, adopt=False, restow=False):
        """Dotfiles management only command."""
        say("Managing dotfiles...")
        
        target_path = Path(target).expanduser().resolve()
        
        if restow:
            return self.restow(target_path)
        elif preview_only:
            return self.preview(target_path, adopt)
        else:
            return self.apply(target_path, adopt)

    def deploy_command(self):
        """Deploy utilities only command."""
        say("Deploying utilities...")
        
        success = True
        
        if not self.deploy_package_manager_utility():
            success = False
        
        if not self.deploy_stow_utility():
            success = False
        
        if success:
            state = self._load_state()
            state["deployed_utilities"] = ["package_manager", "stow_helper"]
            self._save_state(state)
        
        return success

    def status_command(self):
        """Show bootstrap and dotfiles status."""
        say("Bootstrap Status:")
        
        state = self._load_state()
        
        print(f"  Target Directory: {state.get('target_directory', 'Not set')}")
        print(f"  Last Stow: {state.get('last_stow', 'Never')}")
        print(f"  Packages Installed: {'Yes' if state.get('installed_packages') else 'No'}")
        print(f"  Deployed Utilities: {', '.join(state.get('deployed_utilities', []))}")
        
        # Get platform-specific status
        platform_status = self.get_system_status()
        for key, value in platform_status.items():
            print(f"  {key}: {value}")
        
        return True


class DarwinBootstrap(BaseBootstrap):
    """Darwin/macOS-specific bootstrap implementation."""

    def install_package_manager_and_stow(self, preview_only=False):
        """Install Homebrew and GNU Stow (essential tools)."""
        # Step 1: Install Homebrew
        if not self._check_brew_installed():
            if preview_only:
                say("Preview: Would install Homebrew package manager")
            else:
                say("Installing Homebrew...")
                try:
                    install_script = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
                    subprocess.run(install_script, shell=True, check=True)
                    
                    # Add brew to PATH for this session
                    brew_paths = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]
                    for brew_path in brew_paths:
                        if Path(brew_path).exists():
                            os.environ["PATH"] = f"{Path(brew_path).parent}:{os.environ['PATH']}"
                            break
                    
                    success("Homebrew installed successfully.")
                except subprocess.CalledProcessError as e:
                    error(f"Failed to install Homebrew: {e}")
                    return False
        else:
            say("Homebrew is already installed.")
        
        # Step 2: Always ensure Stow is available (even in preview mode)
        if not self._check_stow_installed():
            if preview_only:
                say("Preview: Would install GNU Stow (required for dotfiles preview)")
                # Actually install stow even in preview mode since we need it
                say("Installing GNU Stow (required for preview)...")
            else:
                say("Installing GNU Stow...")
            
            try:
                subprocess.run(["brew", "install", "stow"], check=True)
                success("GNU Stow installed successfully.")
            except subprocess.CalledProcessError as e:
                error(f"Failed to install GNU Stow: {e}")
                return False
        else:
            say("GNU Stow is already available.")
        
        return True

    def deploy_package_manager_utility(self):
        """Deploy the brewfile utility for Homebrew package management."""
        source_brewfile = self.repo_dir / "brewfile.py"
        target_dir = self.repo_dir / "home" / ".local" / "bin"
        target_brewfile = target_dir / "brewfile"
        
        if not source_brewfile.exists():
            warn("brewfile.py not found in repository root. Skipping deployment.")
            return True
        
        say("Deploying brewfile utility...")
        try:
            # Ensure target directory exists
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy the file
            shutil.copy2(source_brewfile, target_brewfile)
            
            # Make it executable
            target_brewfile.chmod(0o755)
            
            success(f"Deployed brewfile utility to {target_brewfile}")
            return True
            
        except OSError as e:
            error(f"Failed to deploy brewfile utility: {e}")
            return False

    def install_packages(self, preview_only=False):
        """Install all packages from Brewfile using the brewfile utility."""
        brewfile_script = self.repo_dir / "home" / ".local" / "bin" / "brewfile"
        
        if preview_only:
            say("Checking package status from Brewfile...")
            try:
                # Use brewfile status to show current state
                result = subprocess.run(
                    ["python3", str(brewfile_script), "status", "--include", "extra"],
                    cwd=self.repo_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                print(result.stdout)
                say("Preview: Missing packages would be installed during setup")
                return True
            except subprocess.CalledProcessError as e:
                # Fallback to basic preview
                say("Preview: Would install packages from Brewfile and Brewfile.extra")
                return True
        
        say("Installing packages from Brewfile...")
        try:
            # Run brewfile install with extra packages
            subprocess.run(
                ["python3", str(brewfile_script), "install", "--include", "extra"],
                cwd=self.repo_dir,
                check=True
            )
            
            # Verify stow is now available
            if not self._check_stow_installed():
                error("GNU Stow was not installed despite package installation.")
                return False
                
            success("All packages installed successfully.")
            return True
            
        except subprocess.CalledProcessError as e:
            error(f"Failed to install packages: {e}")
            return False
        except FileNotFoundError:
            error("Python3 not found. Cannot run brewfile utility.")
            return False

    def deploy_stow_utility(self):
        """Deploy the dotfiles management utility."""
        stow_utility_content = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dotfiles management utility - deployed by bootstrap.py"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

def load_bootstrap_state():
    """Load bootstrap state to get target directory."""
    state_file = Path.cwd() / ".bootstrap.state.json"
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def main():
    parser = argparse.ArgumentParser(description="Manage dotfiles with stow")
    parser.add_argument("action", choices=["status", "restow", "conflicts"], help="Action to perform")
    args = parser.parse_args()
    
    state = load_bootstrap_state()
    target = state.get("target_directory", Path.home())
    
    if args.action == "status":
        print(f"Dotfiles target: {target}")
        print(f"Last stow: {state.get('last_stow', 'Never')}")
    elif args.action == "restow":
        print(f"Re-applying dotfiles to {target}")
        result = subprocess.run(["stow", "-Rvt", str(target), "home"])
        sys.exit(result.returncode)
    elif args.action == "conflicts":
        print("Checking for conflicts...")
        result = subprocess.run(["stow", "-nvt", str(target), "home"], capture_output=True, text=True)
        if "cannot stow" in result.stderr:
            print("Conflicts found:")
            print(result.stderr)
        else:
            print("No conflicts detected.")

if __name__ == "__main__":
    main()
'''
        
        target_dir = self.repo_dir / "home" / ".local" / "bin"
        target_file = target_dir / "dotfiles"
        
        say("Deploying dotfiles utility...")
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            with open(target_file, 'w') as f:
                f.write(stow_utility_content)
            target_file.chmod(0o755)
            success(f"Deployed dotfiles utility to {target_file}")
            return True
        except OSError as e:
            error(f"Failed to deploy dotfiles utility: {e}")
            return False

    def get_system_status(self):
        """Get Darwin-specific system status."""
        status = {}
        
        # Check Homebrew
        status["Homebrew Installed"] = "Yes" if self._check_brew_installed() else "No"
        
        # Check Stow
        status["GNU Stow Available"] = "Yes" if self._check_stow_installed() else "No"
        
        # Check brewfile utility
        brewfile_path = self.repo_dir / "home" / ".local" / "bin" / "brewfile"
        status["Brewfile Utility"] = "Yes" if brewfile_path.exists() else "No"
        
        # Check dotfiles utility
        dotfiles_path = self.repo_dir / "home" / ".local" / "bin" / "dotfiles"
        status["Dotfiles Utility"] = "Yes" if dotfiles_path.exists() else "No"
        
        return status

    def _check_brew_installed(self):
        """Check if Homebrew is installed."""
        return shutil.which("brew") is not None


def main():
    """Main function and argument parser."""
    parser = argparse.ArgumentParser(
        description="Bootstrap a complete development environment with package management and dotfiles",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Available commands"
    )
    
    # Setup command - full bootstrap
    setup_parser = subparsers.add_parser(
        "setup", help="Complete system setup (package manager + packages + dotfiles)"
    )
    setup_parser.add_argument(
        "target",
        nargs="?",
        default="~",
        help="Target directory for dotfiles (default: ~)",
    )
    setup_parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview all operations without making changes",
    )
    setup_parser.add_argument(
        "--adopt",
        action="store_true",
        help="Adopt existing dotfiles into the repository",
    )
    setup_parser.add_argument(
        "--skip-packages",
        action="store_true",
        help="Skip package installation, only apply dotfiles",
    )
    setup_parser.add_argument(
        "--skip-dotfiles",
        action="store_true",
        help="Skip dotfiles application, only install packages",
    )
    
    # Packages command - just package management
    packages_parser = subparsers.add_parser(
        "packages", help="Install or manage packages only"
    )
    packages_parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview package operations without installing",
    )
    
    # Dotfiles command - just dotfiles management
    dotfiles_parser = subparsers.add_parser(
        "dotfiles", help="Apply or manage dotfiles only"
    )
    dotfiles_parser.add_argument(
        "target",
        nargs="?",
        default="~",
        help="Target directory for dotfiles (default: ~)",
    )
    dotfiles_parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview dotfiles operations without applying",
    )
    dotfiles_parser.add_argument(
        "--adopt",
        action="store_true",
        help="Adopt existing dotfiles into the repository",
    )
    dotfiles_parser.add_argument(
        "--restow",
        action="store_true",
        help="Re-apply dotfiles after making changes",
    )
    
    # Deploy command - deploy utilities only
    deploy_parser = subparsers.add_parser(
        "deploy", help="Deploy package management and stow utilities"
    )
    
    # Status command - show current state
    status_parser = subparsers.add_parser(
        "status", help="Show bootstrap and dotfiles status"
    )

    args = parser.parse_args()
    
    # Determine which bootstrap class to use based on OS
    system = platform.system().lower()
    if system == "darwin":
        bootstrap = DarwinBootstrap()
    else:
        die(f"Unsupported platform: {system}. Currently only Darwin/macOS is supported.")
    
    try:
        success = False
        
        if args.command == "setup":
            success = bootstrap.setup_command(
                target=args.target,
                preview_only=args.preview,
                adopt=args.adopt,
                skip_packages=args.skip_packages,
                skip_dotfiles=args.skip_dotfiles,
            )
        elif args.command == "packages":
            success = bootstrap.packages_command(
                preview_only=args.preview,
            )
        elif args.command == "dotfiles":
            success = bootstrap.dotfiles_command(
                target=args.target,
                preview_only=args.preview,
                adopt=args.adopt,
                restow=args.restow,
            )
        elif args.command == "deploy":
            success = bootstrap.deploy_command()
        elif args.command == "status":
            success = bootstrap.status_command()
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\nBootstrap interrupted by user.")
        sys.exit(1)
    except Exception as e:
        die(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
