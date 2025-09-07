#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aptfile.py — A Python-based manager for Linux package dependencies.

This script handles package management for apt (Ubuntu/Debian) and dnf (Rocky/RHEL/Fedora) systems.
"""

import argparse
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


class LinuxPackageManager:
    """Manages Linux package operations for apt and dnf systems."""

    def __init__(self):
        self.repo_dir = self._resolve_repo_dir()
        self.pkg_manager, self.pkg_file = self._detect_package_manager()

    def _resolve_repo_dir(self):
        """Resolves the git repository root from the script's location."""
        try:
            script_path = Path(__file__).resolve()
            return script_path.parent.parent.parent.parent
        except NameError:
            return Path.cwd()

    def _detect_package_manager(self) -> tuple[str, Path]:
        """Detect available package manager and corresponding package file."""
        if shutil.which("apt"):
            return "apt", self.repo_dir / "Aptfile"
        elif shutil.which("dnf"):
            return "dnf", self.repo_dir / "Dnffile"
        elif shutil.which("yum"):
            return "yum", self.repo_dir / "Dnffile"  # Use same file as dnf
        else:
            die("No supported package manager found (apt, dnf, yum)")
            return "None", Path()  # Unreachable

    def _read_package_file(self, file_path):
        """Read packages from package file, ignoring comments and empty lines."""
        if not file_path.exists():
            return []

        packages = []
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    packages.append(line)
        return packages

    def _is_package_installed(self, package):
        """Check if a package is installed."""
        try:
            if self.pkg_manager == "apt":
                result = subprocess.run(["dpkg", "-l", package], capture_output=True, check=False)
                return result.returncode == 0
            elif self.pkg_manager in ["dnf", "yum"]:
                result = subprocess.run(
                    [self.pkg_manager, "list", "installed", package], capture_output=True, check=False
                )
                return result.returncode == 0
        except FileNotFoundError:
            return False
        return False

    def cmd_install(self, args):
        """Install all packages from the package file."""
        packages = self._read_package_file(self.pkg_file)
        if not packages:
            warn(f"No packages found in {self.pkg_file.name}")
            return

        say(f"Installing packages from {self.pkg_file.name}...")

        try:
            if self.pkg_manager == "apt":
                # Update package lists first
                subprocess.run(["sudo", "apt", "update"], check=True)
                subprocess.run(["sudo", "apt", "install", "-y"] + packages, check=True)
            elif self.pkg_manager in ["dnf", "yum"]:
                subprocess.run(["sudo", self.pkg_manager, "install", "-y"] + packages, check=True)

            success("All packages installed successfully.")

        except subprocess.CalledProcessError as e:
            error(f"Failed to install packages: {e}")
            return False

        return True

    def cmd_status(self, args):
        """Show status of all packages in the package file."""
        packages = self._read_package_file(self.pkg_file)
        if not packages:
            warn(f"No packages found in {self.pkg_file.name}")
            return

        say(f"Checking package status from {self.pkg_file.name}...")

        installed = []
        missing = []

        for package in packages:
            if self._is_package_installed(package):
                installed.append(package)
            else:
                missing.append(package)

        print(f"\n{self.pkg_file.name}:")
        if installed:
            installed_display = ", ".join(installed)
            print(f"  installed ({len(installed)}): {installed_display}")

        if missing:
            missing_display = ", ".join([f"{pkg} {YELLOW}(not installed){RESET}" for pkg in missing])
            print(f"  missing ({len(missing)}): {missing_display}")

        if not missing:
            print("  ✓ All packages are installed.")

        return True

    def cmd_add(self, args):
        """Add a package to the package file and install it."""
        package_name = args.package_name

        # Check if package is already in file
        packages = self._read_package_file(self.pkg_file)
        if package_name in packages:
            warn(f"Package '{package_name}' is already in {self.pkg_file.name}")
            return True

        say(f"Adding '{package_name}' to {self.pkg_file.name}...")

        # Install the package first
        try:
            if self.pkg_manager == "apt":
                subprocess.run(["sudo", "apt", "install", "-y", package_name], check=True)
            elif self.pkg_manager in ["dnf", "yum"]:
                subprocess.run(["sudo", self.pkg_manager, "install", "-y", package_name], check=True)
        except subprocess.CalledProcessError as e:
            error(f"Failed to install '{package_name}': {e}")
            return False

        # Add to package file
        with open(self.pkg_file, "a") as f:
            f.write(f"{package_name}\n")

        success(f"Successfully added and installed '{package_name}'.")
        return True

    def cmd_remove(self, args):
        """Remove a package from the package file and optionally uninstall it."""
        package_name = args.package_name

        # Check if package is in file
        packages = self._read_package_file(self.pkg_file)
        if package_name not in packages:
            error(f"Package '{package_name}' not found in {self.pkg_file.name}")
            return False

        print(f"Found '{package_name}' in {self.pkg_file.name}")
        print("What would you like to do?")
        print("  (1) Uninstall package and remove from file")
        print("  (2) Remove from file only")
        print("  (3) Cancel")

        try:
            response = input("Enter your choice [3]: ")
        except (EOFError, KeyboardInterrupt):
            response = "3"
            print()

        choice = response.lower().strip()

        if choice == "1":
            # Uninstall package
            try:
                if self.pkg_manager == "apt":
                    subprocess.run(["sudo", "apt", "remove", "-y", package_name], check=True)
                elif self.pkg_manager in ["dnf", "yum"]:
                    subprocess.run(["sudo", self.pkg_manager, "remove", "-y", package_name], check=True)
                success(f"Uninstalled '{package_name}'")
            except subprocess.CalledProcessError as e:
                error(f"Failed to uninstall '{package_name}': {e}")
                return False

        if choice in ["1", "2"]:
            # Remove from file
            updated_packages = [pkg for pkg in packages if pkg != package_name]
            with open(self.pkg_file, "w") as f:
                f.write("# Package file managed by aptfile\n")
                for pkg in updated_packages:
                    f.write(f"{pkg}\n")
            success(f"Removed '{package_name}' from {self.pkg_file.name}")
        else:
            say("Cancelled.")

        return True

    def cmd_edit(self, args):
        """Open the package file in the default editor."""
        editor = os.environ.get("EDITOR", "vi")
        say(f"Opening {self.pkg_file.name} in {editor}...")
        subprocess.run([editor, str(self.pkg_file)])

    def cmd_path(self, args):
        """Print the path to the package file."""
        print(self.pkg_file)


def main():
    """Main function and argument parser."""
    parser = argparse.ArgumentParser(
        description="A Linux package manager for Aptfile and Dnffile dependencies.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    commands = {
        "install": "Install all packages from the package file.",
        "status": "Show status of all packages and compare with system state.",
        "add": "Install a package and add it to the package file.",
        "remove": "Remove a package from the package file interactively.",
        "edit": "Open package file in $EDITOR.",
        "path": "Print path to the package file.",
    }

    for cmd, help_text in commands.items():
        subparser = subparsers.add_parser(cmd, help=help_text)

        if cmd == "add":
            subparser.add_argument("package_name", help="The name of the package to add.")
        if cmd == "remove":
            subparser.add_argument("package_name", help="The name of the package to remove.")

    args = parser.parse_args()

    manager = LinuxPackageManager()
    command_func = getattr(manager, f"cmd_{args.command}", None)

    if command_func:
        success = command_func(args)
        sys.exit(0 if success else 1)
    else:
        die(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
