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
    
    def _get_package_status(self):
        """Get package management status by running brewfile status check."""
        if not self._check_brewfile_available():
            return {
                'available': False,
                'has_issues': True,
                'issue_count': 0,
                'status': 'brewfile_missing'
            }
        
        try:
            # Run brewfile status to check for issues
            result = subprocess.run(
                [sys.executable, str(self.repo_dir / "brewfile.py"), "status"],
                capture_output=True,
                text=True,
                cwd=self.repo_dir
            )
            
            output = result.stdout
            
            # Parse output to find issues
            has_missing = "need installation" in output
            has_extra = "not in current config" in output
            
            # Count issues if we can parse them
            missing_count = 0
            extra_count = 0
            
            for line in output.split('\n'):
                if "package(s) need installation" in line:
                    # Extract number from line like "! 3 package(s) need installation"
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.isdigit():
                            missing_count = int(part)
                            break
                elif "extra package(s) not in current config" in line:
                    # Extract number from line like "* 6 extra package(s) not in current config"
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.isdigit():
                            extra_count = int(part)
                            break
            
            return {
                'available': True,
                'has_issues': has_missing or has_extra,
                'missing_count': missing_count,
                'extra_count': extra_count,
                'status': 'ready'
            }
            
        except (subprocess.CalledProcessError, FileNotFoundError):
            return {
                'available': False,
                'has_issues': True,
                'issue_count': 0,
                'status': 'error'
            }
    
    def _get_dotfiles_status(self):
        """Get dotfiles status by analyzing stow state."""
        if not self._check_stow_installed():
            return {
                'available': False,
                'has_issues': True,
                'status': 'stow_missing'
            }
        
        try:
            # Check for conflicts and broken symlinks by running a stow dry-run
            target = Path.home()
            cmd = ["stow", "-n", "-v", "-t", str(target), "home"]
            result = subprocess.run(cmd, cwd=self.repo_dir, capture_output=True, text=True)
            
            output = result.stdout + result.stderr
            has_conflicts = "cannot stow" in output
            
            # Check for properly linked files
            linked_count = 0
            try:
                for item in target.rglob("*"):
                    if item.is_symlink():
                        try:
                            resolved = item.resolve()
                            if str(resolved).startswith(str(self.repo_dir / "home")):
                                linked_count += 1
                        except (OSError, ValueError):
                            pass
            except PermissionError:
                pass
            
            return {
                'available': True,
                'has_issues': has_conflicts,
                'linked_count': linked_count,
                'status': 'ready'
            }
            
        except (subprocess.CalledProcessError, FileNotFoundError):
            return {
                'available': False,
                'has_issues': True,
                'status': 'error'
            }
    
    def _print_system_status(self):
        """Print comprehensive system status."""
        print(f"\n{BLUE}Development Environment Status:{RESET}")
        
        # Check package manager
        if self._check_homebrew_installed():
            print(f"  ✓ Package manager installed (Homebrew)")
        else:
            print(f"  ! Package manager missing (install Homebrew first)")
            return False
        
        # Check package status
        package_status = self._get_package_status()
        if package_status['available']:
            if package_status['has_issues']:
                missing = package_status.get('missing_count', 0)
                extra = package_status.get('extra_count', 0)
                issues = []
                if missing > 0:
                    issues.append(f"{missing} missing")
                if extra > 0:
                    issues.append(f"{extra} extra")
                print(f"  ! Package issues detected ({', '.join(issues)})")
            else:
                print(f"  ✓ Packages properly managed")
        else:
            print(f"  ! Package management not available")
        
        # Check dotfiles status
        dotfiles_status = self._get_dotfiles_status()
        if dotfiles_status['available']:
            if dotfiles_status['has_issues']:
                print(f"  ! Dotfile issues detected")
            else:
                linked = dotfiles_status.get('linked_count', 0)
                print(f"  ✓ Dotfiles properly linked ({linked} files)")
        else:
            print(f"  ! Dotfiles management not available (install GNU Stow)")
        
        # Check utilities
        if self._check_brewfile_available():
            print(f"  ✓ Package management utility available")
        else:
            print(f"  ! Package management utility missing")
        
        if self._check_dotfiles_available():
            print(f"  ✓ Dotfiles management utility available")
        else:
            print(f"  ! Dotfiles management utility missing")
        
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
        """Show detailed status including specific issues."""
        print(f"\n{BLUE}Detailed System Status:{RESET}")
        
        # Package details
        package_status = self._get_package_status()
        if package_status['available']:
            print(f"\n{YELLOW}Package Management:{RESET}")
            if package_status['has_issues']:
                missing = package_status.get('missing_count', 0)
                extra = package_status.get('extra_count', 0)
                if missing > 0:
                    print(f"  ! {missing} package(s) need installation")
                if extra > 0:
                    print(f"  * {extra} package(s) would be removed (not in current scope)")
                print(f"  → Run 'python3 brewfile.py' for interactive management")
            else:
                print(f"  ✓ All packages properly managed")
        else:
            print(f"\n{YELLOW}Package Management:{RESET}")
            print(f"  ! Package management not available")
            print(f"  → Run 'python3 bootstrap.py' to set up package management")
        
        # Dotfiles details
        dotfiles_status = self._get_dotfiles_status()
        print(f"\n{YELLOW}Dotfiles Management:{RESET}")
        if dotfiles_status['available']:
            linked = dotfiles_status.get('linked_count', 0)
            print(f"  ✓ {linked} file(s) currently linked")
            if dotfiles_status['has_issues']:
                print(f"  ! Conflicts detected")
                print(f"  → Run 'python3 dotfiles.py' for interactive conflict resolution")
            else:
                print(f"  ✓ No conflicts detected")
        else:
            print(f"  ! GNU Stow not installed")
            print(f"  → Install with: brew install stow")
    
    def cmd_interactive(self):
        """Main interactive bootstrap orchestrator."""
        # Print system status
        if not self._print_system_status():
            say("Please install Homebrew first: https://brew.sh")
            return
        
        # Check if everything is perfect
        package_status = self._get_package_status()
        dotfiles_status = self._get_dotfiles_status()
        
        has_package_issues = package_status.get('has_issues', True)
        has_dotfiles_issues = dotfiles_status.get('has_issues', True)
        
        if not has_package_issues and not has_dotfiles_issues:
            success("✓ Development environment is fully configured!")
            say("Your packages and dotfiles are perfectly synchronized.")
            return
        
        # Show interactive menu for issues
        print(f"\nWhat would you like to manage?")
        menu_options = []
        option_num = 1
        
        if has_package_issues and package_status.get('available', False):
            print(f"  ({option_num}) Packages (interactive brewfile management)")
            menu_options.append(('packages', self._launch_brewfile))
            option_num += 1
        
        if has_dotfiles_issues and dotfiles_status.get('available', False):
            print(f"  ({option_num}) Dotfiles (interactive dotfiles management)")
            menu_options.append(('dotfiles', self._launch_dotfiles))
            option_num += 1
        
        print(f"  ({option_num}) Show detailed status")
        menu_options.append(('status', self._show_detailed_status))
        option_num += 1
        
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
