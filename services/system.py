"""
system.py - System capabilities detection and environment setup.
"""

import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

from utils import LoadingIndicator, error, say, success, warn


@dataclass
class SystemState:
    """System capabilities and readiness state"""

    homebrew_available: bool = False
    stow_available: bool = False
    mas_available: bool = False
    mas_signed_in: bool = False
    mas_account: Optional[str] = None
    uv_available: bool = False
    brewfile_functional: bool = False


class SystemService:
    """System capabilities detection and environment setup service"""

    def __init__(self):
        self._ensure_homebrew_installed()
        self._state = self._fetch_system_state()

    @property
    def state(self) -> SystemState:
        """Get system state (auto-detects and attempts setup on first access)"""
        return self._state

    def launch_brewfile(self) -> bool:
        """Launch interactive package management"""
        try:
            say("Launching package management...")
            result = subprocess.run(["brewfile"])
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            error(f"Failed to launch package management: {e}")
            return False

    def _ensure_homebrew_installed(self):
        """Ensure Homebrew is installed before proceeding"""
        if _check_command("brew"):
            return  # Already installed

        say("Homebrew is required for development environment setup")
        say("This will install Homebrew package manager from https://brew.sh")
        say("")

        try:
            response = input("Install Homebrew now? (y/N): ")
        except (EOFError, KeyboardInterrupt):
            response = "n"
            print()

        if response.lower().strip() != "y":
            say("Homebrew installation skipped")
            say("Note: Many features will be unavailable without Homebrew")
            return

        try:
            # Use the official Homebrew installation script
            install_cmd = (
                '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            )

            say("Installing Homebrew...")
            say("You may be prompted for your password")

            # Run interactively so user can respond to prompts
            result = subprocess.run(install_cmd, shell=True)

            if result.returncode == 0:
                success("Homebrew installed successfully!")

                # Check if brew is in PATH, if not provide guidance
                if not _check_command("brew"):
                    warn("Homebrew installed but 'brew' command not found in PATH")
                    say("You may need to run the commands shown above to add Homebrew to your PATH")
                    say("After that, restart this bootstrap script")
            else:
                error("Homebrew installation failed or was cancelled")

        except Exception as e:
            error(f"Failed to install Homebrew: {e}")

    def _fetch_system_state(self) -> SystemState:
        """Refresh system state and attempt full environment setup"""
        with LoadingIndicator("Setting up development environment"):
            # Detect current capabilities
            current_state = SystemState(
                homebrew_available=_check_command("brew"),
                stow_available=_check_command("stow"),
                mas_available=_check_command("mas"),
                uv_available=_check_command("uv"),
            )

            # Note: Homebrew installation requires user interaction, so we skip auto-install

            if current_state.homebrew_available:
                # Try to install missing foundational tools
                self._attempt_foundational_tools_install()
                current_state.stow_available = _check_command("stow")
                current_state.mas_available = _check_command("mas")
                current_state.uv_available = _check_command("uv")

                # Try to install brewfile if uv is available
                if current_state.uv_available:
                    self._attempt_brewfile_install()
                    current_state.brewfile_functional = _check_brewfile_functional()
                else:
                    current_state.brewfile_functional = False
            else:
                current_state.brewfile_functional = False

            # Check MAS sign-in if available
            if current_state.mas_available:
                current_state.mas_signed_in, current_state.mas_account = _check_mas_signed_in()

        # Update cached state
        self._state = current_state
        return self._state

    def _attempt_foundational_tools_install(self) -> bool:
        """Silently attempt to install missing foundational tools"""
        if not _check_command("brew"):
            return False

        missing_tools = ["stow", "mas", "uv"]

        for tool in missing_tools:
            if not shutil.which(tool):
                try:
                    subprocess.run(
                        ["brew", "install", tool],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    # Ignore failures - just continue
                    pass

        return True

    def _attempt_brewfile_install(self) -> bool:
        """Silently attempt to install brewfile package manager"""
        if not _check_command("uv"):
            return False

        # Check if already installed
        try:
            result = subprocess.run(["uv", "tool", "list"], capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and "brewfile" in result.stdout:
                return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

        # Install from GitHub silently
        try:
            github_url = "git+https://github.com/waltermwaniki/brewfile.git"
            result = subprocess.run(["uv", "tool", "install", github_url], capture_output=True, text=True, timeout=120)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False


def _check_command(command: str) -> bool:
    """Check if a command is available"""
    return shutil.which(command) is not None


def _check_mas_signed_in() -> tuple[bool, Optional[str]]:
    """Check if user is signed into Mac App Store"""
    try:
        # Try 'mas account' first
        result = subprocess.run(["mas", "account"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return True, result.stdout.strip()

        # Try 'mas list' as fallback
        result = subprocess.run(["mas", "list"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return True, "signed in (email unavailable)"

        return False, None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False, None


def _check_brewfile_functional() -> bool:
    """Check if brewfile command is functional"""
    if not _check_command("brewfile"):
        return False

    try:
        result = subprocess.run(
            ["brewfile", "status"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False
