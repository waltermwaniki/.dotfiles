"""
dotfiles_service.py - Handles dotfiles operations with stow and loading indicators.
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from utils import AnsiColor, LoadingIndicator, colorize, error, say, success, warn


@dataclass
class DotfilesState:
    """Cached dotfiles analysis results"""

    target_directory: Path
    stow_available: bool = True
    conflicts: list[str] = field(default_factory=list)
    broken_symlinks: list[str] = field(default_factory=list)
    applied_files: list[str] = field(default_factory=list)
    status: Literal["ready", "conflicts", "broken_symlinks", "stow_missing"] = "ready"

    @property
    def has_issues(self) -> bool:
        """Check if there are any dotfiles issues"""
        return bool(self.conflicts or self.broken_symlinks)

    @property
    def has_conflicts(self) -> bool:
        """Check if there are stow conflicts"""
        return bool(self.conflicts)

    @property
    def has_broken_symlinks(self) -> bool:
        """Check if there are broken symlinks"""
        return bool(self.broken_symlinks)

    @property
    def files_count(self) -> int:
        """Get count of properly applied files"""
        return len(self.applied_files)

    def update_status(self):
        """Update status based on current conditions"""
        if not self.stow_available:
            self.status = "stow_missing"
        elif self.conflicts:
            self.status = "conflicts"
        elif self.broken_symlinks:
            self.status = "broken_symlinks"
        else:
            self.status = "ready"


class DotfilesService:
    """Handles dotfiles operations with stow"""

    def __init__(self, repo_dir: Path, package: str = "home"):
        self.repo_dir = Path(repo_dir)
        self.package = package
        self.default_target = Path.home()
        self._state = None

    @property
    def state(self) -> DotfilesState:
        """Get current dotfiles state, analyzing if needed"""
        if self._state is None:
            self._state = self.refresh()
        return self._state

    def refresh(self) -> DotfilesState:
        """Force refresh of dotfiles analysis"""
        self._state = self._analyze()
        self._state.update_status()
        return self.state

    def _analyze(self, stow_available: bool = True) -> DotfilesState:
        """Analyze dotfiles status with loading indicator"""
        if not stow_available:
            state = DotfilesState(target_directory=self.default_target, stow_available=False, status="stow_missing")
            return state

        target = self.default_target

        with LoadingIndicator("Analyzing dotfiles"):
            # Check for conflicts (what would happen if we tried to stow)
            conflicts = self._check_conflicts(repo_dir=self.repo_dir, target=target, package=self.package)

            # Check for broken symlinks
            broken_symlinks = self._check_broken_symlinks(repo_dir=self.repo_dir, target=target)

            # Check what's currently applied
            applied_files = self._get_applied_files(repo_dir=self.repo_dir, target=target, package=self.package)

            state = DotfilesState(
                target_directory=target,
                stow_available=True,
                conflicts=conflicts,
                broken_symlinks=broken_symlinks,
                applied_files=applied_files,
            )
            return state

    def _run_stow_command(self, args: list[str], target: Path) -> bool:
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
            error("GNU Stow not found. Please install it first.")
            return False

    def apply(self, adopt: bool = False) -> bool:
        """Apply dotfiles using stow."""
        # Ensure we have current state
        current_state = self.state

        if not current_state.stow_available:
            error("GNU Stow not available. Cannot apply dotfiles.")
            return False

        args = ["-v"]
        if adopt:
            args.append("--adopt")

        with LoadingIndicator("Applying dotfiles"):
            result = self._run_stow_command(args, current_state.target_directory)

        if result:
            success("Dotfiles applied successfully!")
            # Refresh state after successful application
            self.refresh()
            return True

        return False

    def restow(self) -> bool:
        """Re-apply dotfiles after making changes."""
        # Ensure we have current state
        current_state = self.state

        if not current_state.stow_available:
            error("GNU Stow not available. Cannot restow dotfiles.")
            return False

        say(f"Re-applying dotfiles to: {current_state.target_directory}")

        args = ["-R", "-v"]  # -R for restow, -v for verbose

        with LoadingIndicator("Re-stowing dotfiles"):
            result = self._run_stow_command(args, current_state.target_directory)

        if result:
            success("Dotfiles re-applied successfully!")
            # Refresh state after successful re-stow
            self.refresh()
            return True

        return False

    def resolve_conflicts_backup(self) -> bool:
        """Resolve conflicts by backing up existing files."""
        current_state = self.state

        if not current_state.has_conflicts:
            say("No conflicts to resolve.")
            return True

        target = current_state.target_directory
        conflicts = current_state.conflicts

        print(f"\n{colorize('Conflicts to resolve:', AnsiColor.YELLOW)}")
        for conflict in conflicts:
            print(f"  {conflict}")

        print("\nThis will backup existing files and replace them with dotfiles.")
        try:
            response = input("Continue? (y/N): ")
        except (EOFError, KeyboardInterrupt):
            response = "n"
            print()

        if response.lower().strip() != "y":
            say("Operation cancelled.")
            return False

        return self._backup_and_apply(target)

    def resolve_conflicts_adopt(self) -> bool:
        """Resolve conflicts by adopting existing files into the repository."""
        current_state = self.state

        if not current_state.has_conflicts:
            say("No conflicts to resolve.")
            return True

        conflicts = current_state.conflicts

        print(f"\n{colorize('Conflicts to resolve:', AnsiColor.YELLOW)}")
        for conflict in conflicts:
            print(f"  {conflict}")

        warn("This will move existing files into the repository!")
        print("Your existing files will replace the ones in the dotfiles repo.")
        try:
            response = input("Are you sure you want to continue? (y/N): ")
        except (EOFError, KeyboardInterrupt):
            response = "n"
            print()

        if response.lower().strip() != "y":
            say("Operation cancelled.")
            return False

        return self.apply(adopt=True)

    def _backup_and_apply(self, target: Path) -> bool:
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
            return self.apply()

        except subprocess.CalledProcessError as e:
            error(f"Failed to backup conflicts: {e}")
            return False

    def print_status_summary(self, state: Optional[DotfilesState] = None):
        """Print a summary of the dotfiles status."""
        if state is None:
            state = self.state

        target = state.target_directory
        conflicts = state.conflicts
        broken_symlinks = state.broken_symlinks
        applied_files = state.applied_files

        print(f"\n{colorize('Dotfiles Status:', AnsiColor.BLUE)}")
        print(f"  Target: {target}")
        print(f"  ✓ {len(applied_files)} files properly linked")

        if broken_symlinks:
            if len(broken_symlinks) == 1:
                print(f"  ! 1 broken symlink: {broken_symlinks[0]}")
            else:
                truncated_list = broken_symlinks[:3]
                extra = "... and more" if len(broken_symlinks) > 3 else ""
                print(f"  ! {len(broken_symlinks)} broken symlinks: {', '.join(truncated_list)}{extra}")

        if conflicts:
            if len(conflicts) == 1:
                print(f"  * 1 conflict detected: {conflicts[0]}")
            else:
                truncated_list = conflicts[:3]
                extra = "... and more" if len(conflicts) > 3 else ""
                print(f"  * {len(conflicts)} conflicts detected: {', '.join(truncated_list)}{extra}")

        if not conflicts and not broken_symlinks:
            print("  ✓ No issues detected")

    def show_detailed_conflicts(self, conflicts: Optional[list[str]] = None):
        """Show detailed information about conflicts."""
        if conflicts is None:
            current_state = self.state
            if not current_state.has_conflicts:
                say("No conflicts to display.")
                return
            conflicts = current_state.conflicts

        target = self.state.target_directory

        print(f"\n{colorize('Detailed conflict information:', AnsiColor.YELLOW)}")

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

    def is_functional(self) -> bool:
        """Check if dotfiles functionality is available."""
        if not shutil.which("stow"):
            return False

        # Check if home package directory exists
        home_package = self.repo_dir / self.package
        return home_package.exists() and home_package.is_dir()

    @staticmethod
    def _check_conflicts(repo_dir: Path, target: Path, package: str) -> list[str]:
        """Check for files that would conflict with stowing."""
        try:
            cmd = ["stow", "-n", "-v", "-t", str(target), package]
            result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)

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

    @staticmethod
    def _check_broken_symlinks(repo_dir: Path, target: Path) -> list[str]:
        """Check for broken symlinks in the target directory."""
        broken = []
        try:
            # Find symlinks that point to our repo but are broken
            for item in target.rglob("*"):
                if item.is_symlink():
                    try:
                        resolved = item.resolve()
                        # If it resolves to something in our repo but doesn't exist
                        if str(resolved).startswith(str(repo_dir)) and not resolved.exists():
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

    @staticmethod
    def _get_applied_files(repo_dir: Path, target: Path, package: str) -> list[str]:
        """Get list of files that are currently applied via stow."""
        applied = []
        try:
            # Find symlinks that point to our repo
            for item in target.rglob("*"):
                if item.is_symlink():
                    try:
                        resolved = item.resolve()
                        if str(resolved).startswith(str(repo_dir / package)):
                            relative_path = item.relative_to(target)
                            applied.append(str(relative_path))
                    except (OSError, ValueError):
                        pass
        except PermissionError:
            pass

        return applied
