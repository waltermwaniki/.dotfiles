#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dotfiles.py — Interactive dotfiles management with GNU Stow.

Provides a user-friendly interface for managing dotfiles with conflict resolution,
adoption, and status reporting.
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict

from utils import AnsiColor, die, error, say, success, warn


class DotfilesStatus(TypedDict):
    stow_available: bool
    target_directory: Path
    conflicts: list[str]
    broken_symlinks: list[str]
    applied_files: list[str]
    status: Literal["ready", "conflicts", "broken_symlinks", "stow_missing"]


class DotfilesManager:
    """Interactive dotfiles management using GNU Stow."""

    def __init__(self):
        self.repo_dir = self._resolve_repo_dir()
        self.package = "home"
        self.default_target = Path.home()

    def _resolve_repo_dir(self):
        """Resolves the git repository root from the script's location."""
        try:
            script_path = Path(__file__).resolve()
            # If this is the deployed version in ~/.local/bin/, navigate back to the repo
            if ".local/bin" in str(script_path):
                return script_path.parent.parent.parent.parent
            else:
                # If running from the repo root directly, use current directory
                return Path.cwd()
        except NameError:
            return Path.cwd()

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
                with open(state_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                warn("Could not read bootstrap state file. Starting fresh.")

        return {
            "target_directory": str(self.default_target),
            "last_stow": None,
            "installed_packages": False,
            "deployed_utilities": [],
            "backup_directory": ".bootstrap.stow",
        }

    def _save_state(self, state):
        """Save bootstrap state to file."""
        state_file = self._get_state_file_path()
        try:
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)
        except IOError as e:
            warn(f"Could not save bootstrap state: {e}")

    def _get_target_directory(self):
        """Get the current target directory from state or default."""
        state = self._load_state()
        target = state.get("target_directory", str(self.default_target))
        if target and isinstance(target, str) and Path(target).expanduser().is_dir():
            return Path(target).expanduser().resolve()
        return self.default_target

    def _analyze_dotfiles_status(self) -> DotfilesStatus:
        """Analyze current dotfiles status and return structured data."""
        if not self._check_stow_installed():
            return {
                "stow_available": False,
                "target_directory": self._get_target_directory(),
                "conflicts": [],
                "broken_symlinks": [],
                "applied_files": [],
                "status": "stow_missing",
            }

        target = self._get_target_directory()

        # Check for conflicts (what would happen if we tried to stow)
        conflicts = self._check_conflicts(target)

        # Check for broken symlinks
        broken_symlinks = self._check_broken_symlinks(target)

        # Check what's currently applied
        applied_files = self._get_applied_files(target)

        return {
            "stow_available": True,
            "target_directory": target,
            "conflicts": conflicts,
            "broken_symlinks": broken_symlinks,
            "applied_files": applied_files,
            "status": "ready",
        }

    def _check_conflicts(self, target):
        """Check for files that would conflict with stowing."""
        try:
            cmd = ["stow", "-n", "-v", "-t", str(target), self.package]
            result = subprocess.run(cmd, cwd=self.repo_dir, capture_output=True, text=True)

            conflicts = []
            output = result.stdout + result.stderr

            for line in output.split("\n"):
                if "cannot stow" in line and "existing target" in line:
                    # Extract filename from error message
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "target" and i + 1 < len(parts):
                            conflict_file = parts[i + 1].rstrip(".,;:")
                            if conflict_file not in conflicts:
                                conflicts.append(conflict_file)
                            break

            return conflicts
        except subprocess.CalledProcessError:
            return []

    def _check_broken_symlinks(self, target):
        """Check for broken symlinks in the target directory."""
        broken = []
        try:
            # Find symlinks that point to our repo but are broken
            for item in target.rglob("*"):
                if item.is_symlink():
                    try:
                        resolved = item.resolve()
                        # If it resolves to something in our repo but doesn't exist
                        if str(resolved).startswith(str(self.repo_dir)) and not resolved.exists():
                            relative_path = item.relative_to(target)
                            broken.append(str(relative_path))
                    except (OSError, ValueError):
                        # Broken symlink
                        try:
                            relative_path = item.relative_to(target)
                            broken.append(str(relative_path))
                        except ValueError:
                            pass
        except PermissionError:
            pass

        return broken

    def _get_applied_files(self, target):
        """Get list of files that are currently applied via stow."""
        applied = []
        try:
            # Find symlinks that point to our repo
            for item in target.rglob("*"):
                if item.is_symlink():
                    try:
                        resolved = item.resolve()
                        if str(resolved).startswith(str(self.repo_dir / self.package)):
                            relative_path = item.relative_to(target)
                            applied.append(str(relative_path))
                    except (OSError, ValueError):
                        pass
        except PermissionError:
            pass

        return applied

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

    def _print_status_summary(self, status_data):
        """Print a summary of the dotfiles status."""
        target = status_data["target_directory"]
        conflicts = status_data["conflicts"]
        broken_symlinks = status_data["broken_symlinks"]
        applied_files = status_data["applied_files"]

        print(f"\n{AnsiColor.BLUE}Dotfiles Status:{AnsiColor.RESET}")
        print(f"  Target: {target}")
        print(f"  ✓ {len(applied_files)} files properly linked")

        if conflicts:
            print(f"  * {len(conflicts)} conflicts detected")

        if broken_symlinks:
            print(f"  ! {len(broken_symlinks)} broken symlinks")

        if not conflicts and not broken_symlinks:
            print("  ✓ No issues detected")

    def _handle_conflicts_interactively(self, conflicts, target):
        """Handle conflicts interactively with user choices."""
        if not conflicts:
            say("No conflicts to resolve.")
            return True

        print(f"\n{AnsiColor.YELLOW}Conflicting files:{AnsiColor.RESET}")
        for conflict in conflicts:
            print(f"  {conflict}")

        print("\nHow would you like to handle conflicts?")
        print("  (1) Backup and replace (recommended)")
        print("  (2) Adopt existing files into repository")
        print("  (3) Show conflicts and exit")
        print("  (q) Cancel")

        try:
            choice = input("Enter your choice [1]: ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            choice = "q"
            print()

        if choice in ["", "1"]:
            return self._backup_and_apply(target)
        elif choice == "2":
            return self._adopt_and_apply(target)
        elif choice == "3":
            self._show_detailed_conflicts(conflicts, target)
            return False
        else:
            say("Operation cancelled.")
            return False

    def _backup_and_apply(self, target):
        """Backup existing files and apply dotfiles."""
        backup_timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        backup_dir = target / ".bootstrap.stow" / backup_timestamp

        say(f"Creating backup directory: {backup_dir}")
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Run stow preview to find conflicts
        try:
            cmd = ["stow", "-n", "-v", "-t", str(target), self.package]
            result = subprocess.run(cmd, cwd=self.repo_dir, capture_output=True, text=True)

            # Parse and backup conflicting files
            output = result.stdout + result.stderr
            conflicts = []
            for line in output.split("\n"):
                if "cannot stow" in line and "existing target" in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "target" and i + 1 < len(parts):
                            conflict_file = parts[i + 1].rstrip(".,;:")
                            if conflict_file not in conflicts:
                                conflicts.append(conflict_file)
                            break

            # Backup and remove conflicting files
            for conflict_file in conflicts:
                source_file = target / conflict_file
                if source_file.exists() and source_file.is_file():
                    backup_file = backup_dir / conflict_file
                    backup_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, backup_file)
                    source_file.unlink()
                    say(f"Backed up and removed: {conflict_file}")

            # Now apply dotfiles
            return self._apply_dotfiles(target)

        except subprocess.CalledProcessError as e:
            error(f"Failed to backup conflicts: {e}")
            return False

    def _adopt_and_apply(self, target):
        """Adopt existing files and apply dotfiles."""
        warn("Using adopt mode. Existing files will be moved into the repository!")
        try:
            response = input("Are you sure you want to continue? (y/N): ")
        except (EOFError, KeyboardInterrupt):
            response = "n"
            print()

        if response.lower().strip() != "y":
            say("Adopt operation cancelled.")
            return False

        return self._apply_dotfiles(target, adopt=True)

    def _apply_dotfiles(self, target, adopt=False):
        """Apply dotfiles using stow."""
        args = ["-v"]
        if adopt:
            args.append("--adopt")

        result = self._run_stow_command(args, target)

        if result:
            # Update state
            state = self._load_state()
            state["target_directory"] = str(target)
            state["last_stow"] = datetime.now().isoformat()
            self._save_state(state)

            success("Dotfiles applied successfully!")
            return True

        return False

    def _restow_dotfiles(self, target):
        """Re-apply dotfiles after making changes."""
        say(f"Re-applying dotfiles to: {target}")

        args = ["-R", "-v"]  # -R for restow, -v for verbose

        result = self._run_stow_command(args, target)

        if result:
            success("Dotfiles re-applied successfully!")
            return True

        return False

    def _fix_broken_symlinks(self, broken_symlinks, target):
        """Fix broken symlinks by re-stowing."""
        if not broken_symlinks:
            say("No broken symlinks to fix.")
            return True

        print(f"\n{AnsiColor.YELLOW}Broken symlinks:{AnsiColor.RESET}")
        for link in broken_symlinks:
            print(f"  {link}")

        say("Re-stowing to fix broken symlinks...")
        return self._restow_dotfiles(target)

    def _show_detailed_conflicts(self, conflicts, target):
        """Show detailed information about conflicts."""
        print(f"\n{AnsiColor.YELLOW}Detailed conflict information:{AnsiColor.RESET}")

        for conflict in conflicts:
            conflict_path = target / conflict
            if conflict_path.exists():
                print(f"\n  {conflict}:")
                print(f"    Existing: {conflict_path}")
                if conflict_path.is_file():
                    try:
                        stat = conflict_path.stat()
                        size = stat.st_size
                        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        print(f"    Size: {size} bytes, Modified: {mtime}")
                    except OSError:
                        print("    Could not read file stats")

                # Show what would replace it
                repo_file = self.repo_dir / self.package / conflict
                if repo_file.exists():
                    print(f"    Would be replaced with: {repo_file}")

    def cmd_interactive(self):
        """Main interactive dotfiles management interface."""
        # Check if stow is available
        if not self._check_stow_installed():
            error("GNU Stow is not installed or not found in PATH.")
            say("Please install GNU Stow first:")
            say("  macOS: brew install stow")
            say("  Ubuntu/Debian: sudo apt install stow")
            say("  Rocky Linux: sudo dnf install stow")
            return

        # Analyze current status
        status_data = self._analyze_dotfiles_status()

        # Print status summary
        self._print_status_summary(status_data)

        # If no issues, just confirm and exit
        conflicts = status_data["conflicts"]
        broken_symlinks = status_data["broken_symlinks"]

        if not conflicts and not broken_symlinks:
            say("✓ Dotfiles are properly configured.")
            return

        # Show issue summary
        print(f"\n{AnsiColor.YELLOW}Issues found:{AnsiColor.RESET}")
        if conflicts:
            print(f"  * {len(conflicts)} file(s) have conflicts (existing files)")
        if broken_symlinks:
            print(f"  ! {len(broken_symlinks)} symlink(s) are broken")

        # Interactive menu
        print("\nWhat would you like to do?")
        print("  (1) Apply all dotfiles (handle conflicts)")
        print("  (2) Fix conflicts only")
        print("  (3) Fix broken symlinks")
        print("  (4) Re-stow all dotfiles")
        print("  (q) Quit")

        try:
            choice = input("Enter your choice [q]: ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            choice = "q"
            print()

        target = status_data["target_directory"]

        if choice == "1":
            if conflicts:
                self._handle_conflicts_interactively(conflicts, target)
            elif broken_symlinks:
                self._fix_broken_symlinks(broken_symlinks, target)
            else:
                self._apply_dotfiles(target)
        elif choice == "2" and conflicts:
            self._handle_conflicts_interactively(conflicts, target)
        elif choice == "2" and not conflicts:
            say("No conflicts to fix.")
        elif choice == "3" and broken_symlinks:
            self._fix_broken_symlinks(broken_symlinks, target)
        elif choice == "3" and not broken_symlinks:
            say("No broken symlinks to fix.")
        elif choice == "4":
            self._restow_dotfiles(target)
        elif choice in ["q", ""]:
            say("Goodbye!")
        else:
            warn("Invalid choice.")


def main():
    """Main function and argument parser."""
    manager = DotfilesManager()

    # For now, just run interactive mode
    # In the future, we could add command-line arguments like brewfile.py
    manager.cmd_interactive()


if __name__ == "__main__":
    main()
