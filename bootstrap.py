#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bootstrap.py — Interactive development environment setup orchestrator.

Provides a unified interface for managing packages (via brewfile) and dotfiles,
with system status overview and guided delegation to specialized tools.
"""

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

    def _check_mas_installed(self):
        """Check if mas (Mac App Store CLI) is installed."""
        return shutil.which("mas") is not None

    def _check_mas_signed_in(self):
        """Check if user is signed into Mac App Store via mas."""
        if not self._check_mas_installed():
            return False, None

        try:
            # First try 'mas account' (works on older macOS versions)
            result = subprocess.run(["mas", "account"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return True, result.stdout.strip()  # Returns email

            # If 'mas account' fails, try 'mas list' as a sign-in check
            # If user is signed in, this should work; if not, it may fail
            result = subprocess.run(["mas", "list"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # mas list works, user is probably signed in, but we don't have email
                return True, "signed in (email unavailable)"

            return False, None
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return False, None

    def _install_foundational_tools(self):
        """Install foundational tools needed for full functionality."""
        if not self._check_homebrew_installed():
            error("Homebrew is required to install foundational tools")
            return False

        foundational_tools = [
            ("stow", "GNU Stow (required for dotfiles management)"),
            ("mas", "Mac App Store CLI (for App Store apps)"),
        ]

        for tool, description in foundational_tools:
            if not shutil.which(tool):
                say(f"Installing {description}...")
                try:
                    _ = subprocess.run(
                        ["brew", "install", tool],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    success(f"{tool} installed successfully")
                except subprocess.CalledProcessError as e:
                    warn(f"Failed to install {tool}: {e.stderr if e.stderr else str(e)}")
                    if tool == "stow":
                        warn("GNU Stow is recommended for dotfiles management")
            else:
                say(f"{tool} already installed")

        return True

    def _prompt_mas_signin_if_needed(self):
        """Guide user through App Store sign-in if needed."""
        if not self._check_mas_installed():
            return  # mas not installed, skip

        signed_in, account = self._check_mas_signed_in()
        if signed_in:
            return  # Already signed in, no action needed

        warn("Not signed into Mac App Store")
        say("To manage App Store apps, please:")
        say("  1. Open the App Store application")
        say("  2. Sign in with your Apple ID")
        say("  3. Run 'mas account' to verify, or restart this bootstrap")
        say("")
        say("You can continue without App Store sign-in (other features will work)")

        # Don't block the process, just inform

    def _install_and_setup_tools(self):
        """Install foundational tools and check mas sign-in status."""
        say("Setting up foundational tools...")

        if not self._install_foundational_tools():
            error("Failed to install foundational tools")
            return False

        # Check mas sign-in status and provide guidance
        self._prompt_mas_signin_if_needed()

        success("Foundational tools setup complete!")
        say("You can now use package and dotfiles management features.")

        return True

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
                timeout=30,  # Prevent hanging
            )
            return result.returncode == 0
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
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
                input="q\n",  # Send quit command to exit gracefully
            )
            return result.returncode == 0
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return False

    def _print_system_status(self):
        """Print simple system status focusing on what's available."""
        print(f"\n{BLUE}Development Environment Status:{RESET}")

        # Check package manager
        if not self._check_homebrew_installed():
            print("  ! Package manager missing (install Homebrew first)")
            return False
        print("  ✓ Package manager installed (Homebrew)")

        # Check foundational tools status
        needs_install = []
        if not self._check_stow_installed():
            needs_install.append("stow")
        if not self._check_mas_installed():
            needs_install.append("mas")

        if needs_install:
            print(f"  ! Foundational tools missing: {', '.join(needs_install)}")
            print("  → Add '(0) Install foundational tools' option to menu")
        else:
            print("  ✓ Foundational tools installed (stow, mas)")

        # Check mas sign-in status
        if self._check_mas_installed():
            signed_in, account = self._check_mas_signed_in()
            if signed_in:
                print(f"  ✓ App Store management ready ({account})")
            else:
                print("  ! App Store management available (sign-in needed)")

        # Check package management
        if self._is_brewfile_functional():
            print("  ✓ Package management ready")
        else:
            print("  ! Package management needs attention")

        # Check dotfiles management
        if self._is_dotfiles_functional():
            print("  ✓ Dotfiles management ready")
        else:
            print("  ! Dotfiles management needs attention")

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
                _ = subprocess.run(
                    [sys.executable, str(self.repo_dir / "brewfile.py"), "status"],
                    cwd=self.repo_dir,
                    timeout=30,
                )
            except (
                subprocess.CalledProcessError,
                FileNotFoundError,
                subprocess.TimeoutExpired,
            ):
                error("Failed to get package status")
        else:
            print(f"\n{YELLOW}Package Status:{RESET}")
            print("  ! Package management not functional")
            print("  → Ensure Homebrew is installed and brewfile.py is available")

        # Delegate to dotfiles for dotfiles status
        if self._is_dotfiles_functional():
            print(f"\n{YELLOW}Dotfiles Status (via dotfiles utility):{RESET}")
            try:
                _ = subprocess.run(
                    [sys.executable, str(self.repo_dir / "dotfiles.py")],
                    cwd=self.repo_dir,
                    timeout=10,
                    input="q\n",  # Quit after showing status
                    text=True,
                )
            except (
                subprocess.CalledProcessError,
                FileNotFoundError,
                subprocess.TimeoutExpired,
            ):
                error("Failed to get dotfiles status")
        else:
            print(f"\n{YELLOW}Dotfiles Status:{RESET}")
            print("  ! Dotfiles management not functional")
            print("  → Ensure GNU Stow is installed and dotfiles.py is available")

    def cmd_interactive(self):
        """Main interactive bootstrap orchestrator - delegates to specialized tools."""
        # Print system status
        if not self._print_system_status():
            say("Please install Homebrew first: https://brew.sh")
            return

        # Simple delegation-based menu
        print("\nWhat would you like to manage?")
        menu_options = []
        option_num = 1

        # Check if foundational tools need installation
        needs_install = []
        if not self._check_stow_installed():
            needs_install.append("stow")
        if not self._check_mas_installed():
            needs_install.append("mas")

        # Offer foundational tools installation if needed
        if needs_install:
            print(f"  ({option_num}) Install foundational tools ({', '.join(needs_install)})")
            menu_options.append(("install_tools", self._install_and_setup_tools))
            option_num += 1

        # Always offer package management if brewfile is functional
        if self._is_brewfile_functional():
            print(f"  ({option_num}) Packages (interactive brewfile management)")
            menu_options.append(("packages", self._launch_brewfile))
            option_num += 1

        # Always offer dotfiles management if dotfiles is functional
        if self._is_dotfiles_functional():
            print(f"  ({option_num}) Dotfiles (interactive dotfiles management)")
            menu_options.append(("dotfiles", self._launch_dotfiles))
            option_num += 1

        # Always offer detailed status
        print(f"  ({option_num}) Show detailed status")
        menu_options.append(("status", self._show_detailed_status))

        print("  (q) Quit")

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
