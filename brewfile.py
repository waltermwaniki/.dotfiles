#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BrewfileManager — Intelligent Homebrew package management using brew bundle.

Uses JSON configuration with package groups and machine-aware installations,
while leveraging brew bundle for all actual package operations.
"""

import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

# ANSI colors (respect NO_COLOR and non-TTY)
BLUE = "\033[1;34m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
GREEN = "\033[1;32m"
GRAY = "\033[0;37m"
RESET = "\033[0m"

if "NO_COLOR" in os.environ or not sys.stdout.isatty():
    BLUE = YELLOW = RED = GREEN = GRAY = RESET = ""


def say(msg: str) -> None:
    """Prints a message with blue prefix."""
    print(f"{BLUE}===>{RESET} {msg}")


def warn(msg: str) -> None:
    """Prints a warning message."""
    print(f"{YELLOW}[warn]{RESET} {msg}")


def error(msg: str) -> None:
    """Prints an error message."""
    print(f"{RED}[error]{RESET} {msg}", file=sys.stderr)


def success(msg: str) -> None:
    """Prints a success message."""
    print(f"{GREEN}[success]{RESET} {msg}")


def die(msg: str) -> None:
    """Prints an error and exits."""
    error(msg)
    sys.exit(1)


@dataclass
class PackageGroup:
    """Represents a group of packages with taps, brews, casks, and mas apps."""

    taps: list[str] = field(default_factory=list)
    brews: list[str] = field(default_factory=list)
    casks: list[str] = field(default_factory=list)
    mas: list[str] = field(default_factory=list)

    def get_all_packages(self) -> dict[str, list[str]]:
        """Get all packages as a dictionary."""
        return {
            "taps": self.taps.copy(),
            "brews": self.brews.copy(),
            "casks": self.casks.copy(),
            "mas": self.mas.copy(),
        }

    def add_package(self, package_type: str, package_name: str) -> None:
        """Add a package to this group."""
        if package_type == "taps":
            if package_name not in self.taps:
                self.taps.append(package_name)
        elif package_type == "brews":
            if package_name not in self.brews:
                self.brews.append(package_name)
        elif package_type == "casks":
            if package_name not in self.casks:
                self.casks.append(package_name)
        elif package_type == "mas":
            if package_name not in self.mas:
                self.mas.append(package_name)
        else:
            raise ValueError(f"Unknown package type: {package_type}")

    def remove_package(self, package_type: str, package_name: str) -> bool:
        """Remove a package from this group. Returns True if removed."""
        if package_type == "taps" and package_name in self.taps:
            self.taps.remove(package_name)
            return True
        elif package_type == "brews" and package_name in self.brews:
            self.brews.remove(package_name)
            return True
        elif package_type == "casks" and package_name in self.casks:
            self.casks.remove(package_name)
            return True
        elif package_type == "mas" and package_name in self.mas:
            self.mas.remove(package_name)
            return True
        return False


@dataclass
class PackageInfo:
    """Information about a package including its status and metadata."""

    name: str
    group: str
    package_type: str  # 'tap', 'brew', 'cask', 'mas'
    installed: bool


@dataclass
class BrewfileConfig:
    """Complete brewfile configuration."""

    version: str = "1.0"
    packages: dict[str, PackageGroup] = field(default_factory=dict)
    machines: dict[str, list[str]] = field(
        default_factory=dict
    )  # hostname -> group names

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BrewfileConfig":
        """Create config from dictionary (loaded JSON)."""
        # Convert package groups from dict to PackageGroup objects
        packages = {}
        for name, pkg_data in data.get("packages", {}).items():
            packages[name] = PackageGroup(
                taps=pkg_data.get("taps", []),
                brews=pkg_data.get("brews", []),
                casks=pkg_data.get("casks", []),
                mas=pkg_data.get("mas", []),
            )

        return cls(
            version=data.get("version", "1.0"),
            packages=packages,
            machines=data.get("machines", {}),
        )

    @classmethod
    def load(cls, config_file: Path) -> "BrewfileConfig":
        """Load configuration from JSON file."""
        if not config_file.exists():
            return cls()  # Return default config

        try:
            with open(config_file, "r") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            warn(f"Could not load config: {e}")
            return cls()  # Return default config

    def save(self, config_file: Path) -> None:
        """Save configuration to JSON file."""
        config_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(config_file, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
        except OSError as e:
            die(f"Could not save config: {e}")

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for JSON serialization."""
        packages_dict = {}
        for name, pkg_group in self.packages.items():
            packages_dict[name] = {
                "taps": pkg_group.taps,
                "brews": pkg_group.brews,
                "casks": pkg_group.casks,
                "mas": pkg_group.mas,
            }

        return {
            "version": self.version,
            "packages": packages_dict,
            "machines": self.machines,
        }

    def get_machine_groups(self, machine_name: str) -> list[str]:
        """Get package groups for a specific machine."""
        groups = self.machines.get(machine_name, [])

        # Auto-include machine-specific group if it exists
        if machine_name in self.packages:
            if machine_name not in groups:
                groups = groups + [machine_name]

        return groups

    def set_machine_groups(self, machine_name: str, groups: list[str]) -> None:
        """set package groups for a specific machine."""
        self.machines[machine_name] = groups

    def get_available_groups(self) -> list[str]:
        """Get all available package groups."""
        return list(self.packages.keys())

    def ensure_group_exists(self, group_name: str) -> None:
        """Ensure a package group exists."""
        if group_name not in self.packages:
            self.packages[group_name] = PackageGroup()

    def collect_packages_for_groups(self, groups: list[str]) -> list[PackageInfo]:
        """Collect all packages for given groups with status information."""
        packages = []
        seen_packages = set()  # Track (package_type, package_name) to avoid duplicates

        for group in groups:
            if group not in self.packages:
                continue

            group_data = self.packages[group]

            # Process each package type
            for package_type in ["taps", "brews", "casks", "mas"]:
                package_list = getattr(group_data, package_type)
                for package in package_list:
                    package_key = (package_type, package)
                    if package_key not in seen_packages:
                        # Handle package type naming (remove 's' for most, keep 'mas' as 'mas')
                        display_type = (
                            package_type[:-1] if package_type != "mas" else "mas"
                        )
                        packages.append(
                            PackageInfo(
                                name=package,
                                group=group,
                                package_type=display_type,
                                installed=False,  # Will be updated by caller
                            )
                        )
                        seen_packages.add(package_key)

        return packages


class PackageAnalyzer:
    """Handles all package detection, analysis, and state management."""

    def __init__(
        self,
        configured_packages: Union[list[PackageInfo], None] = None,
        clean_first: bool = True,
    ):
        """Initialize analyzer and detect installed packages."""
        self.configured_packages = configured_packages or []
        self.installed_packages = self._detect_installed_packages(clean_first)

    def refresh(self, clean_first: bool = True) -> None:
        """Refresh installed package state."""
        self.installed_packages = self._detect_installed_packages(clean_first)

    def _detect_installed_packages(
        self, clean_first: bool = True
    ) -> dict[str, list[str]]:
        """Get currently installed packages using native brew bundle list."""
        if clean_first:
            self._clean_brew_system()

        try:
            # First, sync any configured packages that are installed but missing from Brewfile
            self._sync_brewfile_with_installed_packages(self.configured_packages)

            # return self._get_brewfile_packages()

        except subprocess.CalledProcessError as e:
            die(f"Could not get system packages: {e}")
            return {"taps": [], "brews": [], "casks": [], "mas": []}
        else:
            # Then use brew bundle list to get packages from the Brewfile
            return self._get_brewfile_packages()

    def _clean_brew_system(self) -> None:
        """Clean brew system before package discovery."""
        try:
            say("Cleaning brew packages...")
            # Remove orphaned dependencies
            subprocess.run(["brew", "autoremove"], check=False, capture_output=True)
            # Clear caches
            subprocess.run(["brew", "cleanup"], check=False, capture_output=True)
        except subprocess.CalledProcessError:
            # Don't fail if cleanup fails
            pass

    def _sync_brewfile_with_installed_packages(
        self, configured_packages: list[PackageInfo]
    ) -> None:
        """Ensure configured packages that are installed are in the Brewfile using brew bundle add."""
        try:
            # Get all installed formulae and casks
            result = subprocess.run(
                ["brew", "list", "--formula"],
                capture_output=True,
                text=True,
                check=True,
            )
            installed_brews = set(result.stdout.strip().split())

            result = subprocess.run(
                ["brew", "list", "--cask"], capture_output=True, text=True, check=True
            )
            installed_casks = set(result.stdout.strip().split())

            # Get what's currently in the Brewfile
            brewfile_packages = self._get_brewfile_packages()
            current_brews = set(brewfile_packages["brews"])
            current_casks = set(brewfile_packages["casks"])

            # Find configured packages that are installed but missing from Brewfile
            configured_brews = {
                p.name for p in configured_packages if p.package_type == "brew"
            }
            configured_casks = {
                p.name for p in configured_packages if p.package_type == "cask"
            }

            missing_brews = (configured_brews & installed_brews) - current_brews
            missing_casks = (configured_casks & installed_casks) - current_casks

            # Use brew bundle add to add missing packages directly to Brewfile
            # Change to home directory first since brew bundle add looks for Brewfile there
            original_dir = os.getcwd()
            try:
                os.chdir(Path.home())
                for brew in missing_brews:
                    subprocess.run(
                        ["brew", "bundle", "add", brew], check=True, capture_output=True
                    )

                for cask in missing_casks:
                    subprocess.run(
                        ["brew", "bundle", "add", "--cask", cask],
                        check=True,
                        capture_output=True,
                    )
            finally:
                os.chdir(original_dir)

        except subprocess.CalledProcessError:
            # If sync fails, continue (the calling code will handle detection)
            pass

    def _get_brewfile_packages(self) -> dict[str, list[str]]:
        """Get packages from Brewfile using brew bundle list + fallback for commented MAS apps."""
        try:
            packages = {"taps": [], "brews": [], "casks": [], "mas": []}

            # Get taps
            result = subprocess.run(
                ["brew", "bundle", "list", "--tap"],
                capture_output=True,
                text=True,
                check=True,
            )
            packages["taps"] = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]

            # Get formulas
            result = subprocess.run(
                ["brew", "bundle", "list", "--formula"],
                capture_output=True,
                text=True,
                check=True,
            )
            packages["brews"] = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]

            # Get casks
            result = subprocess.run(
                ["brew", "bundle", "list", "--cask"],
                capture_output=True,
                text=True,
                check=True,
            )
            packages["casks"] = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]

            # Get mas apps (brew bundle list won't include commented ones)
            result = subprocess.run(
                ["brew", "bundle", "list", "--mas"],
                capture_output=True,
                text=True,
                check=True,
            )
            packages["mas"] = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]

            # Fallback: Also check for commented MAS apps in the Brewfile
            # This handles our case where MAS apps are generated as comments
            self._add_commented_mas_apps(packages)

            return packages
        except subprocess.CalledProcessError:
            # If brew bundle list fails, fall back to empty
            return {"taps": [], "brews": [], "casks": [], "mas": []}

    def _add_commented_mas_apps(self, packages: dict[str, list[str]]) -> None:
        """Add commented MAS apps from Brewfile to packages list."""
        try:
            brewfile_path = Path.home() / "Brewfile"
            if not brewfile_path.exists():
                return

            with open(brewfile_path, "r") as f:
                for line in f:
                    line = line.strip()
                    # Look for commented MAS entries like: # mas "App Name" # ID needed - check with: mas list
                    if line.startswith("# mas "):
                        try:
                            app_name = line.split('"')[1]
                            if app_name not in packages["mas"]:
                                packages["mas"].append(app_name)
                        except IndexError:
                            # Skip malformed lines
                            continue
        except OSError:
            # If reading Brewfile fails, continue without MAS apps
            pass

    def check_brewfile_status(self) -> bool:
        """Check if all Brewfile dependencies are satisfied using brew bundle check."""
        try:
            _ = subprocess.run(
                ["brew", "bundle", "check"], capture_output=True, text=True, check=True
            )
            return True  # Exit code 0 means everything is satisfied
        except subprocess.CalledProcessError:
            return False  # Exit code 1 means something is missing

    def get_missing_packages(
        self, configured_packages: list[PackageInfo]
    ) -> dict[str, list[str]]:
        """Get packages that are configured but not installed."""
        missing = {"taps": [], "brews": [], "casks": [], "mas": []}

        # Group configured packages by type
        packages_by_type = {
            "taps": [p for p in configured_packages if p.package_type == "tap"],
            "brews": [p for p in configured_packages if p.package_type == "brew"],
            "casks": [p for p in configured_packages if p.package_type == "cask"],
            "mas": [p for p in configured_packages if p.package_type == "mas"],
        }

        # Find missing packages for each type
        for pkg_type, packages in packages_by_type.items():
            configured_names = {p.name for p in packages}
            installed = set(self.installed_packages.get(pkg_type, []))
            missing_names = configured_names - installed
            missing[pkg_type] = list(missing_names)

        return missing

    def get_extra_packages(
        self, configured_packages: list[PackageInfo]
    ) -> dict[str, list[str]]:
        """Get packages that are installed but not configured."""
        extra = {"taps": [], "brews": [], "casks": [], "mas": []}

        # Group configured packages by type
        packages_by_type = {
            "taps": [p for p in configured_packages if p.package_type == "tap"],
            "brews": [p for p in configured_packages if p.package_type == "brew"],
            "casks": [p for p in configured_packages if p.package_type == "cask"],
            "mas": [p for p in configured_packages if p.package_type == "mas"],
        }

        # Find extra packages for each type
        for pkg_type, packages in packages_by_type.items():
            configured_names = {p.name for p in packages}
            installed = set(self.installed_packages.get(pkg_type, []))
            extra_names = installed - configured_names
            extra[pkg_type] = list(extra_names)

        return extra

    def update_package_status(self, packages: list[PackageInfo]) -> None:
        """Update installation status for a list of packages."""
        for pkg in packages:
            # Convert package type to plural form for installed_packages lookup
            if pkg.package_type == "mas":
                pkg_type_plural = (
                    "mas"  # MAS is already plural form in installed_packages
                )
            else:
                pkg_type_plural = f"{pkg.package_type}s"
            pkg.installed = pkg.name in self.installed_packages.get(pkg_type_plural, [])


class BrewfileManager:
    """Main CLI orchestrator - delegates to service classes."""

    def __init__(self):
        self.config_file = Path.home() / ".config" / "brewfile" / "config.json"
        self.brewfile_path = Path.home() / "Brewfile"
        self.machine_name = socket.gethostname().split(".")[0]  # Short hostname
        self.config = BrewfileConfig.load(self.config_file)
        self.analyzer = None  # Lazy initialization

    def _save_config(self) -> None:
        """Save current config to file."""
        self.config.save(self.config_file)

    def _get_analyzer(self, clean_first: bool = True) -> PackageAnalyzer:
        """Get analyzer instance, creating or refreshing as needed."""
        # Get configured packages for more targeted detection
        groups = self._get_machine_groups()
        configured_packages = self._collect_packages_for_groups(groups)

        if self.analyzer is None:
            self.analyzer = PackageAnalyzer(
                configured_packages=configured_packages, clean_first=clean_first
            )
        else:
            self.analyzer.configured_packages = (
                configured_packages  # Update configured packages
            )
            self.analyzer.refresh(clean_first=clean_first)
        return self.analyzer

    def _get_machine_groups(self) -> list[str]:
        """Get package groups for current machine."""
        return self.config.get_machine_groups(self.machine_name)

    def _set_machine_groups(self, groups: list[str]) -> None:
        """set package groups for current machine."""
        self.config.set_machine_groups(self.machine_name, groups)
        self._save_config()

    def _get_available_groups(self) -> list[str]:
        """Get all available package groups."""
        return self.config.get_available_groups()

    def _collect_packages_for_groups(self, groups: list[str]) -> list[PackageInfo]:
        """Collect all packages for given groups with status information."""
        return self.config.collect_packages_for_groups(groups)

    def _check_machine_configured(self) -> bool:
        """Check if current machine is configured."""
        return self.machine_name in self.config.machines

    def _ensure_machine_group_exists(self) -> None:
        """Ensure machine-specific package group exists in config."""
        self.config.ensure_group_exists(self.machine_name)
        self._save_config()

    def _generate_brewfile_content(self, groups: list[str]) -> str:
        """Generate Brewfile content for given groups."""
        packages = self._collect_packages_for_groups(groups)

        # Group packages by type
        taps = [p.name for p in packages if p.package_type == "tap"]
        brews = [p.name for p in packages if p.package_type == "brew"]
        casks = [p.name for p in packages if p.package_type == "cask"]
        mas_apps = [p.name for p in packages if p.package_type == "mas"]

        lines = []

        # Add taps
        for tap in taps:
            lines.append(f'tap "{tap}"')

        if taps:
            lines.append("")  # Empty line after taps

        # Add brews
        for brew in brews:
            lines.append(f'brew "{brew}"')

        if brews:
            lines.append("")  # Empty line after brews

        # Add casks
        for cask in casks:
            lines.append(f'cask "{cask}"')

        if casks:
            lines.append("")  # Empty line after casks

        # Add mas apps (note: we can't regenerate IDs, so this is basic)
        for mas_app in mas_apps:
            lines.append(f'# mas "{mas_app}" # ID needed - check with: mas list')

        return "\n".join(lines) + "\n"

    def _write_brewfile(self, content: str) -> None:
        """Write content to ~/Brewfile."""
        try:
            with open(self.brewfile_path, "w") as f:
                f.write(content)
        except OSError as e:
            die(f"Could not write Brewfile: {e}")

    def _run_brew_bundle(
        self, command: str, capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        """Run brew bundle command."""
        cmd = ["brew", "bundle"] + command.split()

        try:
            if capture_output:
                return subprocess.run(cmd, capture_output=True, text=True, check=True)
            else:
                return subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            if capture_output:
                error(f"brew bundle failed: {e.stderr}")
            die(f"Command failed: {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 1)  # Should not reach here

    def cmd_init(self) -> None:
        """Initialize or update machine configuration."""
        say(f"Configuring package groups for machine: {self.machine_name}")

        available_groups = self._get_available_groups()
        current_groups = self._get_machine_groups()

        if not available_groups:
            say("No package groups defined yet. Define groups in your config first.")
            return

        print(f"\nAvailable groups: {', '.join(available_groups)}")

        if current_groups:
            print(f"Current groups: {', '.join(current_groups)}")

        print("\nSelect groups for this machine (space-separated):")
        try:
            selection = input("Groups: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not selection:
            say("No changes made.")
            return

        selected_groups = [g.strip() for g in selection.split()]

        # Validate selections
        invalid_groups = [g for g in selected_groups if g not in available_groups]
        if invalid_groups:
            warn(f"Invalid groups: {', '.join(invalid_groups)}")
            return

        self._set_machine_groups(selected_groups)
        success(
            f"Machine {self.machine_name} configured with groups: {', '.join(selected_groups)}"
        )

        # Generate initial Brewfile
        self.cmd_generate()

    def cmd_generate(self) -> None:
        """Generate ~/Brewfile from config for current machine."""
        if not self._check_machine_configured():
            say("Machine not configured. Run 'brewfile init' first.")
            return

        groups = self._get_machine_groups()
        if not groups:
            say("No groups configured for this machine.")
            return

        say(f"Generating Brewfile for groups: {', '.join(groups)}")

        content = self._generate_brewfile_content(groups)
        self._write_brewfile(content)

        success(f"Generated ~/Brewfile with packages from: {', '.join(groups)}")

    def cmd_status(self) -> None:
        """Show package status by comparing config, Brewfile, and system state."""
        if not self._check_machine_configured():
            say("Machine not configured. Run 'brewfile init' first.")
            return

        # Get analyzer with fresh system state
        analyzer = self._get_analyzer(clean_first=True)

        groups = self._get_machine_groups()
        configured_packages = self._collect_packages_for_groups(groups)

        # Get missing and extra packages using analyzer
        missing_packages = analyzer.get_missing_packages(configured_packages)
        extra_packages = analyzer.get_extra_packages(configured_packages)

        # Update installation status for configured packages
        analyzer.update_package_status(configured_packages)

        print(f"\n{BLUE}Package Status for {self.machine_name}:{RESET}")
        print(f"Groups: {', '.join(groups)}")

        # Group packages by type for display
        packages_by_type = {
            "taps": [p for p in configured_packages if p.package_type == "tap"],
            "brews": [p for p in configured_packages if p.package_type == "brew"],
            "casks": [p for p in configured_packages if p.package_type == "cask"],
            "mas": [p for p in configured_packages if p.package_type == "mas"],
        }

        # Show each package type
        for package_type, packages in packages_by_type.items():
            # Show configured packages
            if packages:
                print(f"\n{package_type.title()}:")
                for pkg in sorted(packages, key=lambda x: x.name):
                    if pkg.installed:
                        print(f"  ✓ {pkg.name} {GRAY}({pkg.group}){RESET}")
                    else:
                        print(f"  ! {pkg.name} {GRAY}({pkg.group}){RESET}")

            # Show extra packages using DRY data
            extra = extra_packages.get(package_type, [])
            if extra:
                if packages:  # Only add extra header if we had configured packages
                    print(f"\n{package_type.title()} (extra):")
                else:  # No configured packages, so this is the main section
                    print(f"\n{package_type.title()}:")
                for package in sorted(extra):
                    print(f"  * {package}")

        # Summary using DRY data
        total_missing = sum(len(pkgs) for pkgs in missing_packages.values())
        total_extra = sum(len(pkgs) for pkgs in extra_packages.values())

        print("\nSummary:")
        if total_missing > 0:
            print(f"  ! {total_missing} package(s) need installation")
        if total_extra > 0:
            print(f"  * {total_extra} extra package(s) not in current config")

        if total_missing == 0 and total_extra == 0:
            success("All packages synchronized!")

    def cmd_install(self) -> None:
        """Install packages using brew bundle."""
        if not self._check_machine_configured():
            say("Machine not configured. Run 'brewfile init' first.")
            return

        if not self.brewfile_path.exists():
            say("Generating Brewfile first...")
            self.cmd_generate()

        # Get analyzer without cleaning (faster)
        analyzer = self._get_analyzer(clean_first=False)

        groups = self._get_machine_groups()
        configured_packages = self._collect_packages_for_groups(groups)

        # Get what would be installed
        missing_packages = analyzer.get_missing_packages(configured_packages)
        if not missing_packages:
            success("All packages are already installed!")
            return

        # Show summary and ask for confirmation
        print(f"\n\n{YELLOW}Packages to be installed:{RESET}")
        for pkg_type, packages in missing_packages.items():
            if packages:
                print(f"  {pkg_type.title()}: {', '.join(packages)}")

        total_count = sum(len(pkgs) for pkgs in missing_packages.values())
        print(f"\nTotal: {total_count} package(s) will be installed.")

        try:
            confirm = input("\nProceed with installation? (y/N): ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            say("Installation cancelled.")
            print()
            return

        if not confirm.startswith("y"):
            print()
            say("Installation cancelled.")
            print()
            return

        say("Installing packages via brew bundle...")
        self._run_brew_bundle("install", capture_output=False)
        success("Package installation complete!")

    def cmd_cleanup(self) -> None:
        """Remove packages not in Brewfile using brew bundle."""
        if not self._check_machine_configured():
            say("Machine not configured. Run 'brewfile init' first.")
            return

        if not self.brewfile_path.exists():
            say("No Brewfile found. Generate one first.")
            return

        # Get analyzer and configured packages
        analyzer = self._get_analyzer(clean_first=False)

        groups = self._get_machine_groups()
        configured_packages = self._collect_packages_for_groups(groups)

        # Get what would be removed
        extra_packages = analyzer.get_extra_packages(configured_packages)
        if not extra_packages:
            success("No extra packages to remove!")
            return

        # Show summary and ask for confirmation
        print(f"\n\n{YELLOW}Packages to be REMOVED:{RESET}")
        for pkg_type, packages in extra_packages.items():
            if packages:
                print(f"  {pkg_type.title()}: {', '.join(packages)}")

        total_count = sum(len(pkgs) for pkgs in extra_packages.values())
        print(f"\nTotal: {total_count} package(s) will be REMOVED.")
        print(f"{RED}WARNING: This will uninstall packages from your system!{RESET}")

        try:
            confirm = input("\nProceed with removal? (y/N): ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            say("Cleanup cancelled.")
            print()
            return

        if not confirm.startswith("y"):
            print()
            say("Cleanup cancelled.")
            print()
            return

        say("Removing packages not in Brewfile...")
        try:
            self._run_brew_bundle("cleanup", capture_output=False)
            success("Package cleanup complete!")
        except subprocess.CalledProcessError:
            warn("Cleanup cancelled or failed.")

    def cmd_sync(self) -> None:
        """Install missing and remove extra packages."""
        if not self._check_machine_configured():
            say("Machine not configured. Run 'brewfile init' first.")
            return

        if not self.brewfile_path.exists():
            say("Generating Brewfile first...")
            self.cmd_generate()

        # Get analyzer and configured packages
        analyzer = self._get_analyzer(clean_first=True)

        groups = self._get_machine_groups()
        configured_packages = self._collect_packages_for_groups(groups)

        # Get what would be changed
        missing_packages = analyzer.get_missing_packages(configured_packages)
        extra_packages = analyzer.get_extra_packages(configured_packages)

        if not missing_packages and not extra_packages:
            success("All packages are already synchronized!")
            return

        # Show comprehensive summary
        print(f"\n\n{YELLOW}Synchronization Summary:{RESET}")

        if missing_packages:
            print(f"\n{GREEN}Packages to be INSTALLED:{RESET}")
            for pkg_type, packages in missing_packages.items():
                if packages:
                    print(f"  {pkg_type.title()}: {', '.join(packages)}")

        if extra_packages:
            print(f"\n{RED}Packages to be REMOVED:{RESET}")
            for pkg_type, packages in extra_packages.items():
                if packages:
                    print(f"  {pkg_type.title()}: {', '.join(packages)}")

        install_count = (
            sum(len(pkgs) for pkgs in missing_packages.values())
            if missing_packages
            else 0
        )
        remove_count = (
            sum(len(pkgs) for pkgs in extra_packages.values()) if extra_packages else 0
        )

        print(f"\nTotal: {install_count} to install, {remove_count} to remove.")
        if remove_count > 0:
            print(
                f"{RED}WARNING: This will uninstall packages from your system!{RESET}"
            )

        try:
            confirm = input("\nProceed with synchronization? (y/N): ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            say("Synchronization cancelled.")
            print()
            return

        if not confirm.startswith("y"):
            print()
            say("Synchronization cancelled.")
            print()
            return

        say("Synchronizing packages...")

        # Install first, then cleanup
        if missing_packages:
            say("Installing missing packages...")
            self._run_brew_bundle("install", capture_output=False)

        if extra_packages:
            say("Removing extra packages...")
            try:
                self._run_brew_bundle("cleanup", capture_output=False)
            except subprocess.CalledProcessError:
                warn("Cleanup portion failed, but install may have succeeded.")
                return

        success("Package synchronization complete!")

    def cmd_adopt(self) -> None:
        """Interactively adopt extra packages into configuration."""
        if not self._check_machine_configured():
            say("Machine not configured. Run 'brewfile init' first.")
            return

        # Get analyzer and configured packages
        analyzer = self._get_analyzer(clean_first=False)

        groups = self._get_machine_groups()
        configured_packages = self._collect_packages_for_groups(groups)

        # Find extra packages using analyzer
        extra_packages_dict = analyzer.get_extra_packages(configured_packages)
        extra_packages = []
        for package_type, packages in extra_packages_dict.items():
            for package in packages:
                extra_packages.append((package_type, package))

        if not extra_packages:
            success("No extra packages to adopt!")
            return

        say(f"Found {len(extra_packages)} extra package(s) not in config:")
        for package_type, package in extra_packages[:10]:  # Show first 10
            print(f"  * {package} ({package_type[:-1]})")

        if len(extra_packages) > 10:
            print(f"  ... and {len(extra_packages) - 10} more")

        print("\nHow would you like to handle these packages?")
        print("  (1) Add to existing group")
        print(f"  (2) Add to machine group ({self.machine_name})")
        print("  (3) Create new group")
        print("  (4) Edit config manually")
        print("  (5) Remove from system")
        print("  (q) Skip for now")

        try:
            choice = input("Enter your choice [q]: ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            choice = "q"
            print()

        if choice == "q" or choice == "":
            return
        elif choice == "1":
            self._adopt_to_existing_group(extra_packages)
        elif choice == "2":
            self._adopt_to_machine_group(extra_packages)
        elif choice == "3":
            self._adopt_to_new_group(extra_packages)
        elif choice == "4":
            self._edit_config_manually()
        elif choice == "5":
            self._remove_extra_packages(extra_packages)
        else:
            warn("Invalid choice.")

    def _adopt_to_existing_group(self, packages: list[tuple[str, str]]) -> None:
        """Adopt packages to an existing group."""
        available_groups = self._get_available_groups()
        if not available_groups:
            warn("No existing groups available.")
            return

        print(f"\nAvailable groups: {', '.join(available_groups)}")
        try:
            group = input("Enter group name: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if group not in available_groups:
            warn(f"Group '{group}' does not exist.")
            return

        self._add_packages_to_group(packages, group)

    def _adopt_to_machine_group(self, packages: list[tuple[str, str]]) -> None:
        """Adopt packages to machine-specific group."""
        self._ensure_machine_group_exists()
        self._add_packages_to_group(packages, self.machine_name)

        # Add machine group to machine's groups if not already there
        machine_groups = self.config.machines.get(self.machine_name, [])
        if self.machine_name not in machine_groups:
            machine_groups.append(self.machine_name)
            self.config.machines[self.machine_name] = machine_groups
            self._save_config()

    def _adopt_to_new_group(self, packages: list[tuple[str, str]]) -> None:
        """Adopt packages to a new group."""
        try:
            group_name = input("Enter new group name: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not group_name:
            warn("Group name cannot be empty.")
            return

        if group_name in self.config.packages:
            warn(f"Group '{group_name}' already exists.")
            return

        # Create new group
        self.config.ensure_group_exists(group_name)

        self._add_packages_to_group(packages, group_name)

        # Ask if they want to add this group to current machine
        print(f"\nAdd '{group_name}' to this machine's groups? (y/N): ", end="")
        try:
            if input().lower().startswith("y"):
                machine_groups = self.config.machines.get(self.machine_name, [])
                machine_groups.append(group_name)
                self.config.machines[self.machine_name] = machine_groups
                self._save_config()
        except (EOFError, KeyboardInterrupt):
            print()

    def _add_packages_to_group(
        self, packages: list[tuple[str, str]], group_name: str
    ) -> None:
        """Add packages to a specific group."""
        if group_name not in self.config.packages:
            self.config.ensure_group_exists(group_name)

        group = self.config.packages[group_name]

        for package_type, package in packages:
            group.add_package(package_type, package)

        self._save_config()
        success(f"Added {len(packages)} package(s) to group '{group_name}'.")

    def _edit_config_manually(self) -> None:
        """Open config file in editor."""
        editor = os.environ.get("EDITOR", "nano")
        try:
            subprocess.run([editor, str(self.config_file)], check=True)
            # Reload config after editing
            self.config = BrewfileConfig.load(self.config_file)
            success("Config reloaded after editing.")
        except subprocess.CalledProcessError:
            warn("Failed to open editor.")

    def _remove_extra_packages(self, packages: list[tuple[str, str]]) -> None:
        """Remove extra packages from system."""
        print(f"\nThis will remove {len(packages)} package(s) from your system.")
        print("Are you sure? (y/N): ", end="")
        try:
            if not input().lower().startswith("y"):
                return
        except (EOFError, KeyboardInterrupt):
            print()
            return

        for package_type, package in packages:
            try:
                if package_type == "casks":
                    subprocess.run(["brew", "uninstall", "--cask", package], check=True)
                else:
                    subprocess.run(["brew", "uninstall", package], check=True)
            except subprocess.CalledProcessError:
                warn(f"Failed to remove {package}")

        success("Package removal complete.")

    def cmd_add(self, package_name: str, package_type: Optional[str] = None) -> None:
        """Add package to configuration, Brewfile, and install it."""
        if not self._check_machine_configured():
            say("Machine not configured. Run 'brewfile init' first.")
            return

        try:
            # 1. Auto-detect package type if not specified
            if not package_type:
                say(f"Detecting package type for '{package_name}'...")
                package_type = self._detect_package_type(package_name)
                say(f"Detected '{package_name}' as {package_type}")

            # 2. Pre-validate: select group before making system changes
            target_group = self._select_group_for_package(package_name, package_type)

            # 3. Install the package
            say(f"Installing {package_name}...")
            self._install_package(package_name, package_type)

            # 4. Add to configuration (with rollback on failure)
            try:
                self._add_to_config_group(package_name, package_type, target_group)
                self.cmd_generate()
                success(
                    f"Added {package_name} to group '{target_group}' and installed successfully"
                )
            except Exception as config_error:
                # Rollback: remove the package we just installed
                warn("Config update failed, rolling back installation...")
                self._rollback_installation(package_name, package_type)
                raise config_error

        except subprocess.CalledProcessError as e:
            error(f"Failed to add {package_name}: {e}")
        except Exception as e:
            error(f"Unexpected error adding {package_name}: {e}")

    def cmd_remove(self, package_name: str, package_type: str = "formula") -> None:
        """Remove package from configuration, Brewfile, and uninstall it."""
        if not self._check_machine_configured():
            say("Machine not configured. Run 'brewfile init' first.")
            return

        try:
            # 1. Remove from JSON configuration
            removed = self._remove_from_config(package_name, package_type)
            if not removed:
                warn(f"Package {package_name} not found in configuration")
                return

            # 2. Regenerate Brewfile from config
            self.cmd_generate()

            # 3. Ask user if they want to uninstall
            print(f"Remove {package_name} from system? (y/N): ", end="")
            try:
                if input().lower().startswith("y"):
                    say(f"Uninstalling {package_name}...")
                    if package_type == "cask":
                        subprocess.run(
                            ["brew", "uninstall", "--cask", package_name], check=True
                        )
                    else:
                        subprocess.run(["brew", "uninstall", package_name], check=True)
                    success(f"Removed and uninstalled {package_name}")
                else:
                    success(
                        f"Removed {package_name} from configuration (kept installed)"
                    )
            except (EOFError, KeyboardInterrupt):
                print()
                success(f"Removed {package_name} from configuration (kept installed)")

        except subprocess.CalledProcessError as e:
            error(f"Failed to remove {package_name}: {e}")

    def _select_group_for_package(self, package_name: str, package_type: str) -> str:
        """Interactively select which group to add the package to."""
        available_groups = self._get_machine_groups()

        # Always default to machine group for simplicity
        default_group = self.machine_name

        print(f"\nWhere should '{package_name}' be added?")
        for i, group in enumerate(available_groups, 1):
            marker = " (default)" if group == default_group else ""
            print(f"  ({i}) {group}{marker}")
        print(f"  ({len(available_groups) + 1}) Create new group")
        print(f"  (Enter) Use default: {default_group}")

        try:
            choice = input("Choice: ").strip()

            if not choice:  # Use default
                return default_group
            elif choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(available_groups):
                    return available_groups[choice_num - 1]
                elif choice_num == len(available_groups) + 1:
                    # Create new group
                    new_group = input("Enter new group name: ").strip()
                    if new_group and new_group not in self.config.packages:
                        self.config.ensure_group_exists(new_group)
                        # Add to machine groups if not already there
                        machine_groups = self.config.machines.get(self.machine_name, [])
                        if new_group not in machine_groups:
                            machine_groups.append(new_group)
                            self.config.machines[self.machine_name] = machine_groups
                        self._save_config()
                        return new_group
                    else:
                        warn("Invalid group name or group already exists")
                        return default_group

            warn("Invalid choice, using default group")
            return default_group

        except (EOFError, KeyboardInterrupt):
            print()
            return default_group

    def _add_to_config_group(
        self, package_name: str, package_type: str, target_group: str
    ) -> None:
        """Add package to specific group in configuration."""
        # Ensure the group exists
        if target_group not in self.config.packages:
            self.config.ensure_group_exists(target_group)

        group = self.config.packages[target_group]
        if package_type == "cask":
            group.add_package("casks", package_name)
        else:
            group.add_package("brews", package_name)

        self._save_config()

    def _remove_from_config(self, package_name: str, package_type: str) -> bool:
        """Remove package from configuration. Returns True if found and removed."""
        removed = False

        # Search all groups for the package
        for group_name, group in self.config.packages.items():
            if package_type == "cask":
                if group.remove_package("casks", package_name):
                    say(f"Removed {package_name} from group '{group_name}'")
                    removed = True
            else:
                if group.remove_package("brews", package_name):
                    say(f"Removed {package_name} from group '{group_name}'")
                    removed = True

        if removed:
            self._save_config()

        return removed

    def _detect_package_type(self, package_name: str) -> str:
        """Auto-detect if package is a cask or formula."""
        try:
            # First check if it's a cask
            result = subprocess.run(
                ["brew", "search", "--cask", package_name],
                capture_output=True,
                text=True,
                check=True,
            )
            # If exact match found in cask search, it's a cask
            if (
                f"\n{package_name}\n" in result.stdout
                or result.stdout.strip() == package_name
            ):
                return "cask"

            # Check if it's a formula
            result = subprocess.run(
                ["brew", "search", package_name],
                capture_output=True,
                text=True,
                check=True,
            )
            # If exact match found in formula search, it's a formula
            if (
                f"\n{package_name}\n" in result.stdout
                or result.stdout.strip() == package_name
            ):
                return "formula"

            # If no exact match, default to formula
            warn(
                f"Could not find exact match for '{package_name}', assuming it's a formula"
            )
            return "formula"

        except subprocess.CalledProcessError:
            # If search fails, default to formula
            warn(f"Package search failed for '{package_name}', assuming it's a formula")
            return "formula"

    def _install_package(self, package_name: str, package_type: str) -> None:
        """Install a specific package using brew."""
        if package_type == "cask":
            subprocess.run(["brew", "install", "--cask", package_name], check=True)
        else:
            subprocess.run(["brew", "install", package_name], check=True)

    def _rollback_installation(self, package_name: str, package_type: str) -> None:
        """Remove a package that was installed but failed to be added to config."""
        try:
            if package_type == "cask":
                subprocess.run(
                    ["brew", "uninstall", "--cask", package_name],
                    check=True,
                    capture_output=True,
                )
            else:
                subprocess.run(
                    ["brew", "uninstall", package_name], check=True, capture_output=True
                )
            say(f"Rolled back installation of {package_name}")
        except subprocess.CalledProcessError:
            warn(
                f"Could not rollback installation of {package_name} - you may need to remove it manually"
            )

    def cmd_check(self) -> None:
        """Validate consistency between config, Brewfile, and system state."""
        if not self._check_machine_configured():
            say("Machine not configured. Run 'brewfile init' first.")
            return

        issues = []

        # Check if Brewfile exists and is up to date
        if not self.brewfile_path.exists():
            issues.append("~/Brewfile does not exist")
        else:
            # Check if config and Brewfile are in sync
            try:
                analyzer = self._get_analyzer(clean_first=False)
                groups = self._get_machine_groups()
                configured_packages = self._collect_packages_for_groups(groups)

                # Use brew bundle check to validate system state
                result = subprocess.run(
                    ["brew", "bundle", "check"], capture_output=True, text=True
                )
                if result.returncode != 0:
                    issues.append("Some packages in Brewfile are not installed")

                # Check for extra packages
                extra_packages = analyzer.get_extra_packages(configured_packages)
                total_extra = sum(len(pkgs) for pkgs in extra_packages.values())
                if total_extra > 0:
                    issues.append(f"{total_extra} packages installed but not in config")

            except Exception as e:
                issues.append(f"Failed to validate system state: {e}")

        # Report results
        if issues:
            warn("Issues found:")
            for issue in issues:
                print(f"  • {issue}")
            print("\nRun 'brewfile doctor' to fix common issues.")
        else:
            success("All checks passed! System is consistent.")

    def cmd_doctor(self) -> None:
        """Diagnose and fix common issues."""
        if not self._check_machine_configured():
            say("Machine not configured. Run 'brewfile init' first.")
            return

        say("Running diagnostics...")

        # Fix 1: Regenerate Brewfile if missing or out of sync
        if not self.brewfile_path.exists():
            say("~/Brewfile missing - regenerating...")
            self.cmd_generate()

        # Fix 2: Check for config/system inconsistencies
        try:
            analyzer = self._get_analyzer(clean_first=True)
            groups = self._get_machine_groups()
            configured_packages = self._collect_packages_for_groups(groups)

            missing_packages = analyzer.get_missing_packages(configured_packages)
            total_missing = sum(len(pkgs) for pkgs in missing_packages.values())

            if total_missing > 0:
                print(
                    f"\nFound {total_missing} configured packages that are not installed:"
                )
                for pkg_type, packages in missing_packages.items():
                    if packages:
                        print(f"  {pkg_type.title()}: {', '.join(packages)}")
                print("\nRun 'brewfile install' to install missing packages.")

            extra_packages = analyzer.get_extra_packages(configured_packages)
            total_extra = sum(len(pkgs) for pkgs in extra_packages.values())

            if total_extra > 0:
                print(f"\nFound {total_extra} installed packages not in config:")
                # Show only first few to avoid spam
                shown = 0
                for pkg_type, packages in extra_packages.items():
                    for pkg in packages[:3]:
                        if shown < 5:
                            print(f"  {pkg} ({pkg_type[:-1]})")
                            shown += 1
                if total_extra > 5:
                    print(f"  ... and {total_extra - 5} more")
                print(
                    "\nRun 'brewfile adopt' to add them to config or 'brewfile cleanup' to remove them."
                )

            if total_missing == 0 and total_extra == 0:
                success("System is healthy - no issues found!")

        except Exception as e:
            error(f"Diagnostics failed: {e}")

    def cmd_interactive(self) -> None:
        """Interactive package management."""
        if not self._check_machine_configured():
            say(f"Machine {self.machine_name} is not configured.")
            print("Would you like to configure it now? (y/N): ", end="")
            try:
                if input().lower().startswith("y"):
                    self.cmd_init()
                else:
                    return
            except (EOFError, KeyboardInterrupt):
                print()
                return

        while True:
            self.cmd_status()

            print("\nWhat would you like to do?")
            print("  (1) Install missing packages")
            print("  (2) Remove extra packages")
            print("  (3) Adopt extra packages to config")
            print("  (4) Sync both (install + remove)")
            print("  (5) Reconfigure machine groups")
            print("  (6) Regenerate Brewfile")
            print("  (7) Edit config manually")
            print("  (q) Quit")

            try:
                choice = input("Enter your choice [q]: ").lower().strip()
            except (EOFError, KeyboardInterrupt):
                choice = "q"
                print()

            if choice == "q" or choice == "":
                say("Goodbye!")
                break
            elif choice == "1":
                self.cmd_install()
            elif choice == "2":
                self.cmd_cleanup()
            elif choice == "3":
                self.cmd_adopt()
            elif choice == "4":
                self.cmd_sync()
            elif choice == "5":
                self.cmd_init()
            elif choice == "6":
                self.cmd_generate()
            elif choice == "7":
                self._edit_config_manually()
            else:
                warn("Invalid choice.")

            print()  # Space between iterations


def main():
    """Main function."""
    if len(sys.argv) < 2:
        manager = BrewfileManager()
        manager.cmd_interactive()
        return

    manager = BrewfileManager()
    command = sys.argv[1]

    if command == "init" or command == "select":
        manager.cmd_init()
    elif command == "generate":
        manager.cmd_generate()
    elif command == "status":
        manager.cmd_status()
    elif command == "install":
        manager.cmd_install()
    elif command == "cleanup":
        manager.cmd_cleanup()
    elif command == "sync":
        manager.cmd_sync()
    elif command == "adopt":
        manager.cmd_adopt()
    elif command == "add":
        if len(sys.argv) < 3:
            error("Usage: brewfile add <package_name> [--cask]")
            sys.exit(1)
        package_name = sys.argv[2]
        # Auto-detect package type unless --cask is explicitly specified
        package_type = "cask" if "--cask" in sys.argv else None
        manager.cmd_add(package_name, package_type)
    elif command == "remove":
        if len(sys.argv) < 3:
            error("Usage: brewfile remove <package_name> [--cask]")
            sys.exit(1)
        package_name = sys.argv[2]
        package_type = "cask" if "--cask" in sys.argv else "formula"
        manager.cmd_remove(package_name, package_type)
    elif command == "check":
        manager.cmd_check()
    elif command == "doctor":
        manager.cmd_doctor()
    elif command == "edit":
        manager._edit_config_manually()
    else:
        error(f"Unknown command: {command}")
        print(
            "Available commands: init, select, generate, status, install, cleanup, sync, adopt, add, remove, check, doctor, edit"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
