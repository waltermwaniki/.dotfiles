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

    def analyze_dotfiles(self, stow_available: bool = True, force_refresh: bool = False) -> Optional[DotfilesState]:
        """Analyze dotfiles status with loading indicator"""
        if self._state is not None and not force_refresh:
            return self._state

        if not stow_available:
            return DotfilesState(target_directory=self.default_target, stow_available=False, status="stow_missing")

        target = self.default_target

        with LoadingIndicator("Analyzing dotfiles"):
            # Check for conflicts (what would happen if we tried to stow)
            conflicts = self._check_conflicts(target)

            # Check for broken symlinks
            broken_symlinks = self._check_broken_symlinks(target)

            # Check what's currently applied
            applied_files = self._get_applied_files(target)

            self._state = DotfilesState(
                target_directory=target,
                stow_available=True,
                conflicts=conflicts,
                broken_symlinks=broken_symlinks,
                applied_files=applied_files,
            )
            self._state.update_status()

        return self._state

    def refresh_analysis(self, stow_available: bool = True) -> Optional[DotfilesState]:
        """Force refresh of dotfiles analysis"""
        return self.analyze_dotfiles(stow_available, force_refresh=True)

    def _check_conflicts(self, target: Path) -> list[str]:
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

    def _check_broken_symlinks(self, target: Path) -> list[str]:
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

    def _get_applied_files(self, target: Path) -> list[str]:
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

    def apply_dotfiles(self, adopt: bool = False) -> bool:
        """Apply dotfiles using stow."""
        if not self._state:
            error("Dotfiles state not analyzed. Call analyze_dotfiles() first.")
            return False

        args = ["-v"]
        if adopt:
            args.append("--adopt")

        with LoadingIndicator("Applying dotfiles"):
            result = self._run_stow_command(args, self._state.target_directory)

        if result:
            success("Dotfiles applied successfully!")
            # Refresh state after successful application
            self.refresh_analysis(stow_available=True)
            return True

        return False

    def restow_dotfiles(self) -> bool:
        """Re-apply dotfiles after making changes."""
        if not self._state:
            error("Dotfiles state not analyzed. Call analyze_dotfiles() first.")
            return False

        say(f"Re-applying dotfiles to: {self._state.target_directory}")

        args = ["-R", "-v"]  # -R for restow, -v for verbose

        with LoadingIndicator("Re-stowing dotfiles"):
            result = self._run_stow_command(args, self._state.target_directory)

        if result:
            success("Dotfiles re-applied successfully!")
            # Refresh state after successful re-stow
            self.refresh_analysis(stow_available=True)
            return True

        return False

    def resolve_conflicts_backup(self) -> bool:
        """Resolve conflicts by backing up existing files."""
        if not self._state or not self._state.has_conflicts:
            say("No conflicts to resolve.")
            return True

        target = self._state.target_directory
        conflicts = self._state.conflicts

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
        if not self._state or not self._state.has_conflicts:
            say("No conflicts to resolve.")
            return True

        _ = self._state.target_directory
        conflicts = self._state.conflicts

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

        return self.apply_dotfiles(adopt=True)

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
            return self.apply_dotfiles()

        except subprocess.CalledProcessError as e:
            error(f"Failed to backup conflicts: {e}")
            return False

    def print_status_summary(self, state: Optional[DotfilesState] = None):
        """Print a summary of the dotfiles status."""
        if state is None:
            state = self._state

        if not state:
            print(f"\n{colorize('Dotfiles Status:', AnsiColor.BLUE)}")
            print("  ! Dotfiles management not available")
            return

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
            if not self._state or not self._state.has_conflicts:
                say("No conflicts to display.")
                return
            conflicts = self._state.conflicts

        target = self._state.target_directory if self._state else self.default_target

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
