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
from enum import Enum
from pathlib import Path
from typing import Any, Optional

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


class PackageType(Enum):
    """Package types supported by Homebrew."""

    TAP = "tap"
    BREW = "brew"  # Formula
    CASK = "cask"
    MAS = "mas"  # Mac App Store

    @property
    def plural(self) -> str:
        """Get the plural form used in configuration storage."""
        if self == PackageType.TAP:
            return "taps"
        elif self == PackageType.BREW:
            return "brews"
        elif self == PackageType.CASK:
            return "casks"
        elif self == PackageType.MAS:
            return "mas"
        return self.value + "s"

    @classmethod
    def from_plural(cls, plural: str) -> "PackageType":
        """Create PackageType from plural form."""
        if plural == "taps":
            return cls.TAP
        elif plural == "brews":
            return cls.BREW
        elif plural == "casks":
            return cls.CASK
        elif plural == "mas":
            return cls.MAS
        raise ValueError(f"Unknown plural package type: {plural}")

    @classmethod
    def from_string(cls, value: str) -> "PackageType":
        """Create PackageType from various string representations."""
        value = value.lower().strip()
        if value in ("formula", "brew"):
            return cls.BREW
        elif value == "cask":
            return cls.CASK
        elif value == "tap":
            return cls.TAP
        elif value == "mas":
            return cls.MAS
        # Try plural forms
        try:
            return cls.from_plural(value)
        except ValueError:
            pass
        # Try direct enum value
        for pkg_type in cls:
            if pkg_type.value == value:
                return pkg_type
        raise ValueError(f"Unknown package type: {value}")


class InstallationStatus(Enum):
    """Installation status for packages."""

    UNKNOWN = "unknown"
    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"


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

    def add_package(self, package_type: PackageType, package_name: str) -> None:
        """Add a package to this group."""
        if package_type == PackageType.TAP:
            if package_name not in self.taps:
                self.taps.append(package_name)
        elif package_type == PackageType.BREW:
            if package_name not in self.brews:
                self.brews.append(package_name)
        elif package_type == PackageType.CASK:
            if package_name not in self.casks:
                self.casks.append(package_name)
        elif package_type == PackageType.MAS:
            if package_name not in self.mas:
                self.mas.append(package_name)
        else:
            raise ValueError(f"Unknown package type: {package_type}")

    def remove_package(self, package_type: PackageType, package_name: str) -> bool:
        """Remove a package from this group. Returns True if removed."""
        if package_type == PackageType.TAP and package_name in self.taps:
            self.taps.remove(package_name)
            return True
        elif package_type == PackageType.BREW and package_name in self.brews:
            self.brews.remove(package_name)
            return True
        elif package_type == PackageType.CASK and package_name in self.casks:
            self.casks.remove(package_name)
            return True
        elif package_type == PackageType.MAS and package_name in self.mas:
            self.mas.remove(package_name)
            return True
        return False

    def get_packages_of_type(self, package_type: PackageType) -> list[str]:
        """Get packages of a specific type."""
        if package_type == PackageType.TAP:
            return self.taps.copy()
        elif package_type == PackageType.BREW:
            return self.brews.copy()
        elif package_type == PackageType.CASK:
            return self.casks.copy()
        elif package_type == PackageType.MAS:
            return self.mas.copy()
        else:
            raise ValueError(f"Unknown package type: {package_type}")


@dataclass
class PackageInfo:
    """Information about a package including its metadata and installation status."""

    name: str
    group: str
    package_type: PackageType
    installed: InstallationStatus = field(default_factory=lambda: InstallationStatus.UNKNOWN)


@dataclass
class BrewfileConfig:
    """Complete brewfile configuration."""

    version: str = "1.0"
    packages: dict[str, PackageGroup] = field(default_factory=dict)
    machines: dict[str, list[str]] = field(default_factory=dict)  # hostname -> group names

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

    def ensure_group_exists(self, group_name: str) -> None:
        """Ensure a package group exists."""
        if group_name not in self.packages:
            self.packages[group_name] = PackageGroup()

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

    @property
    def package_infos(self) -> dict[str, list[PackageInfo]]:
        """Rebuild the package infos cache."""
        seen_packages = set()  # Track (package_type, package_name) to avoid duplicates

        packages: dict[str, list[PackageInfo]] = {}
        for group in self.packages:
            group_data = self.packages[group]
            # Process each package type
            for pkg_type in PackageType:
                package_list = getattr(group_data, pkg_type.plural)
                for package in package_list:
                    package_key = (pkg_type.plural, package)
                    if package_key not in seen_packages:
                        if group not in packages:
                            packages[group] = []
                        packages[group].append(
                            PackageInfo(
                                name=package,
                                group=group,
                                package_type=pkg_type,
                            )
                        )
                        seen_packages.add(package_key)
        return packages

    def get_package_info(self, package_name: str) -> Optional[PackageInfo]:
        """Get PackageInfo for a specific package across all groups, or None if not found."""
        for pkg_infos in self.package_infos.values():
            for pkg_info in pkg_infos:
                if pkg_info.name == package_name:
                    return pkg_info
        return None

    def get_machine_packages(self, machine_name: str) -> list[PackageInfo]:
        """Get all packages for a specific machine as PackageInfo objects."""
        machine_groups = self.get_machine_groups(machine_name)
        return [pkg_info for group in machine_groups for pkg_info in self.package_infos.get(group, [])]

        # packages = []
        # seen_packages = set()  # Track (package_type, package_name) to avoid duplicates

        # for group in machine_groups:
        #     if group not in self.packages:
        #         continue

        #     group_data = self.packages[group]

        #     # Process each package type
        #     for pkg_type in PackageType:
        #         package_list = getattr(group_data, pkg_type.plural)
        #         for package in package_list:
        #             package_key = (pkg_type.plural, package)
        #             if package_key not in seen_packages:
        #                 packages.append(
        #                     PackageInfo(
        #                         name=package,
        #                         group=group,
        #                         package_type=pkg_type,
        #                     )
        #                 )
        #                 seen_packages.add(package_key)

        # return packages

    def add_package(
        self,
        group_name: str,
        package_type: PackageType,
        package_name: str,
        config_file: Optional[Path] = None,
    ) -> None:
        """Add a single package to a specific group and auto-save."""
        self.ensure_group_exists(group_name)
        group = self.packages[group_name]

        group.add_package(package_type, package_name)

        # Auto-save if config_file provided
        if config_file:
            self.save(config_file)

    def remove_package(self, package_name: str, config_file: Optional[Path] = None) -> Optional[PackageType]:
        """Remove package from all groups where it exists (searches all package types) and auto-save. Returns the PackageType that was removed, or None if not found."""
        found_package_type = None
        removed_from_any_group = False

        # Search all groups and all package types for the package
        for group_name, group in self.packages.items():
            for package_type in PackageType:
                if group.remove_package(package_type, package_name):
                    found_package_type = package_type
                    removed_from_any_group = True

        # Auto-save if config_file provided and something was removed
        if removed_from_any_group and config_file:
            self.save(config_file)

        return found_package_type


class PackageAnalyzer:
    """Handles all package detection, analysis, and state management."""

    def __init__(self):
        """Initialize analyzer with lazy loading."""
        self._installed_packages = None  # Lazy-loaded

    @property
    def installed_packages(self) -> dict[str, list[str]]:
        """Get installed packages, loading them if needed."""
        if self._installed_packages is None:
            return self.refresh()
        return self._installed_packages

    def refresh(self) -> dict[str, list[str]]:
        """Get currently installed packages by first syncing Brewfile, then using brew bundle list."""
        # Clean up orphaned dependencies using brew autoremove
        try:
            subprocess.run(["brew", "autoremove"], check=False, capture_output=True)
        except subprocess.CalledProcessError:
            # Don't fail if cleanup fails
            pass

        try:
            # First, ensure Brewfile is in sync with system by dumping (overwrites existing)
            self._dump_brewfile_from_system()

            # Now use brew bundle list to get packages from the synced Brewfile
            self._installed_packages = self._get_brewfile_packages()
        except subprocess.CalledProcessError as e:
            die(f"Could not get system packages: {e}")
            self._installed_packages = {pkg_type.plural: [] for pkg_type in PackageType}
        return self._installed_packages

    def update_package_status(self, packages: list[PackageInfo]) -> None:
        """Update installation status for a list of packages."""
        for pkg in packages:
            # Use the plural form for installed_packages lookup
            pkg_type_plural = pkg.package_type.plural

            if pkg.package_type == PackageType.MAS:
                # For MAS apps, check if the app name (without ID) is installed
                if "::" in pkg.name:
                    app_name = pkg.name.split("::")[0]
                    is_installed = app_name in self.installed_packages.get(pkg_type_plural, [])
                else:
                    is_installed = pkg.name in self.installed_packages.get(pkg_type_plural, [])
            else:
                is_installed = pkg.name in self.installed_packages.get(pkg_type_plural, [])

            # Set installation status using enum
            pkg.installed = InstallationStatus.INSTALLED if is_installed else InstallationStatus.NOT_INSTALLED

    def _dump_brewfile_from_system(self) -> None:
        """Generate Brewfile from current system state (all installed packages)."""
        try:
            subprocess.run(["brew", "bundle", "dump", "--force", "--no-vscode"], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            die(f"Could not dump system Brewfile: {e}")

    def _get_brewfile_packages(self) -> dict[str, list[str]]:
        """Get packages from Brewfile using brew bundle list + fallback for commented MAS apps."""
        try:
            packages = {pkg_type.plural: [] for pkg_type in PackageType}

            # Get taps
            result = subprocess.run(
                ["brew", "bundle", "list", "--tap"],
                capture_output=True,
                text=True,
                check=True,
            )
            packages[PackageType.TAP.plural] = [
                line.strip() for line in result.stdout.strip().split("\n") if line.strip()
            ]

            # Get formulas
            result = subprocess.run(
                ["brew", "bundle", "list", "--formula"],
                capture_output=True,
                text=True,
                check=True,
            )
            packages[PackageType.BREW.plural] = [
                line.strip() for line in result.stdout.strip().split("\n") if line.strip()
            ]

            # Get casks
            result = subprocess.run(
                ["brew", "bundle", "list", "--cask"],
                capture_output=True,
                text=True,
                check=True,
            )
            packages[PackageType.CASK.plural] = [
                line.strip() for line in result.stdout.strip().split("\n") if line.strip()
            ]

            # Get mas apps
            result = subprocess.run(
                ["brew", "bundle", "list", "--mas"],
                capture_output=True,
                text=True,
                check=True,
            )
            packages[PackageType.MAS.plural] = [
                line.strip() for line in result.stdout.strip().split("\n") if line.strip()
            ]

            return packages
        except subprocess.CalledProcessError:
            # If brew bundle list fails, fall back to empty
            return {pkg_type.plural: [] for pkg_type in PackageType}

    def get_missing_packages(self, configured_packages: list[PackageInfo]) -> dict[str, list[str]]:
        """Get packages that are configured but not installed."""
        missing = {pkg_type.plural: [] for pkg_type in PackageType}

        # Group configured packages by type
        packages_by_type = {
            pkg_type.plural: [p for p in configured_packages if p.package_type == pkg_type] for pkg_type in PackageType
        }

        # Find missing packages for each type
        for pkg_type, packages in packages_by_type.items():
            if pkg_type == PackageType.MAS.plural:
                # For MAS apps, compare app names (without IDs) against installed apps
                configured_names = set()
                for p in packages:
                    if "::" in p.name:
                        configured_names.add(p.name.split("::")[0])
                    else:
                        configured_names.add(p.name)
                installed = set(self.installed_packages.get(pkg_type, []))
                missing_names = configured_names - installed
                # Convert back to full appName::id format for missing items
                missing_full_names = []
                for p in packages:
                    if "::" in p.name:
                        app_name = p.name.split("::")[0]
                        if app_name in missing_names:
                            missing_full_names.append(p.name)
                    else:
                        if p.name in missing_names:
                            missing_full_names.append(p.name)
                missing[pkg_type] = missing_full_names
            else:
                configured_names = {p.name for p in packages}
                installed = set(self.installed_packages.get(pkg_type, []))
                missing_names = configured_names - installed
                missing[pkg_type] = list(missing_names)

        return missing

    def get_extra_packages(self, configured_packages: list[PackageInfo]) -> dict[str, list[str]]:
        """Get packages that are installed but not configured."""
        extra = {pkg_type.plural: [] for pkg_type in PackageType}

        # Group configured packages by type
        packages_by_type = {
            pkg_type.plural: [p for p in configured_packages if p.package_type == pkg_type] for pkg_type in PackageType
        }

        # Find extra packages for each type
        for pkg_type, packages in packages_by_type.items():
            if pkg_type == PackageType.MAS.plural:
                # For MAS apps, compare app names (without IDs) against installed apps
                configured_names = set()
                for p in packages:
                    if "::" in p.name:
                        configured_names.add(p.name.split("::")[0])
                    else:
                        configured_names.add(p.name)
                installed = set(self.installed_packages.get(pkg_type, []))
                extra_names = installed - configured_names
                extra[pkg_type] = list(extra_names)
            else:
                configured_names = {p.name for p in packages}
                installed = set(self.installed_packages.get(pkg_type, []))
                extra_names = installed - configured_names
                extra[pkg_type] = list(extra_names)

        return extra

    def detect_package_type(self, package_name: str) -> PackageType:
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
            if f"\n{package_name}\n" in result.stdout or result.stdout.strip() == package_name:
                return PackageType.CASK

            # Check if it's a formula
            result = subprocess.run(
                ["brew", "search", package_name],
                capture_output=True,
                text=True,
                check=True,
            )
            # If exact match found in formula search, it's a formula
            if f"\n{package_name}\n" in result.stdout or result.stdout.strip() == package_name:
                return PackageType.BREW

            # If no exact match, default to formula
            warn(f"Could not find exact match for '{package_name}', assuming it's a formula")
            return PackageType.BREW

        except subprocess.CalledProcessError:
            # If search fails, default to formula
            warn(f"Package search failed for '{package_name}', assuming it's a formula")
            return PackageType.BREW


class BrewfileManager:
    """Main CLI orchestrator - delegates to service classes."""

    def __init__(self):
        self.config_file = Path.home() / ".config" / "brewfile" / "config.json"
        self.brewfile_path = Path.home() / "Brewfile"
        self.machine_name = socket.gethostname().split(".")[0]  # Short hostname
        self.config = BrewfileConfig.load(self.config_file)
        self._analyzer = PackageAnalyzer()

    @property
    def analyzer(self) -> PackageAnalyzer:
        """Get analyzer instance, creating or refreshing as needed."""
        return self._analyzer

    @property
    def is_configured(self) -> bool:
        """Check if current machine is configured."""
        return self.machine_name in self.config.machines

    @property
    def machine_groups(self) -> list[str]:
        """Get package groups for current machine."""
        return self.config.get_machine_groups(self.machine_name)

    @property
    def machine_packages(self) -> list[PackageInfo]:
        """Get all packages for current machine."""
        return self.config.get_machine_packages(self.machine_name)

    def _ensure_setup(self, require_brewfile: bool = False) -> tuple[PackageAnalyzer, list[str], list[PackageInfo]]:
        """Common setup: check machine config, get analyzer, groups, and packages.

        Args:
            require_brewfile: Whether to generate Brewfile if missing

        Returns:
            tuple of (analyzer, groups, configured_packages)
        """
        if not self.is_configured:
            die("Machine not configured. Run 'brewfile init' first.")

        if require_brewfile and not self.brewfile_path.exists():
            say("Generating Brewfile first...")
            self._dump_brewfile_from_config()

        return self.analyzer, self.machine_groups, self.machine_packages

    def _dump_brewfile_from_config(self) -> None:
        """Generate Brewfile from config only (configured packages for this machine)."""
        packages = self.config.get_machine_packages(self.machine_name)

        # Group packages by type
        taps = [p.name for p in packages if p.package_type == PackageType.TAP]
        brews = [p.name for p in packages if p.package_type == PackageType.BREW]
        casks = [p.name for p in packages if p.package_type == PackageType.CASK]
        mas_apps = [p.name for p in packages if p.package_type == PackageType.MAS]

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

        # Add mas apps with IDs
        for mas_app in mas_apps:
            if "::" in mas_app:
                app_name, app_id = mas_app.split("::", 1)
                lines.append(f'mas "{app_name}", id: {app_id}')
            else:
                # Fallback for entries without ID
                lines.append(f'# mas "{mas_app}" # ID needed - check with: mas list')

        content = "\n".join(lines) + "\n"
        try:
            with open(self.brewfile_path, "w") as f:
                f.write(content)
        except OSError as e:
            die(f"Could not write Brewfile: {e}")

    def _run_brew_bundle(self, command: str, capture_output: bool = True) -> subprocess.CompletedProcess:
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

        available_groups = list(self.config.packages.keys())

        if not available_groups:
            say("No package groups defined yet. Define groups in your config first.")
            return

        print(f"\nAvailable groups: {', '.join(available_groups)}")

        if self.machine_groups:
            print(f"Current groups: {', '.join(self.machine_groups)}")

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

        self.config.set_machine_groups(self.machine_name, selected_groups)
        self.config.save(self.config_file)
        success(f"Machine {self.machine_name} configured with groups: {', '.join(selected_groups)}")

        # Generate initial Brewfile
        self._dump_brewfile_from_config()
        success(f"Generated ~/Brewfile with packages from: {', '.join(selected_groups)}")

    def cmd_status(self) -> tuple[int, int]:
        """Show package status by comparing config, Brewfile, and system state."""
        # Perform all the setup and analysis internally
        analyzer, groups, configured_packages = self._ensure_setup()

        # Get missing and extra packages using analyzer
        missing_packages = analyzer.get_missing_packages(configured_packages)
        extra_packages = analyzer.get_extra_packages(configured_packages)

        # Update installation status for configured packages
        analyzer.update_package_status(configured_packages)

        # Display the status
        print(f"\n{BLUE}Package Status for {self.machine_name}:{RESET}")
        print(f"Groups: {', '.join(groups)}")

        # Group packages by type for display
        packages_by_type = {
            pkg_type.plural: [p for p in configured_packages if p.package_type == pkg_type] for pkg_type in PackageType
        }

        # Show each package type
        for package_type, packages in packages_by_type.items():
            # Show configured packages
            if packages:
                print(f"\n{package_type.title()}:")
                for pkg in sorted(packages, key=lambda x: x.name):
                    if pkg.installed == InstallationStatus.INSTALLED:
                        print(f"  ✓ {pkg.name} {GRAY}({pkg.group}){RESET}")
                    else:
                        print(f"  {RED}✗{RESET} {pkg.name} {GRAY}({pkg.group}) - missing{RESET}")

            # Show extra packages using DRY data
            extra = extra_packages.get(package_type, [])
            if extra:
                if packages:  # Only add extra header if we had configured packages
                    print(f"\n{package_type.title()} (extra):")
                else:  # No configured packages, so this is the main section
                    print(f"\n{package_type.title()}:")
                for package in sorted(extra):
                    print(f"  {BLUE}+{RESET} {package} {GRAY}- not in config{RESET}")

        # Summary using DRY data
        total_missing = sum(len(pkgs) for pkgs in missing_packages.values())
        total_extra = sum(len(pkgs) for pkgs in extra_packages.values())

        print("\nSummary:")
        if total_missing > 0:
            print(f"  {RED}✗{RESET} {total_missing} package(s) need installation")
        if total_extra > 0:
            print(f"  {BLUE}+{RESET} {total_extra} extra package(s) not in current config")

        if total_missing == 0 and total_extra == 0:
            success("All packages synchronized!")

        return total_missing, total_extra

    def cmd_sync_adopt(self) -> None:
        """Install missing packages and adopt extras to machine group."""
        analyzer, groups, configured_packages = self._ensure_setup(require_brewfile=True)

        missing_packages = analyzer.get_missing_packages(configured_packages)
        extra_packages = analyzer.get_extra_packages(configured_packages)

        if not missing_packages and not extra_packages:
            success("All packages are already synchronized!")
            return

        print(f"\n{YELLOW}Sync + Adopt Summary:{RESET}")
        if missing_packages:
            print(f"\n{GREEN}INSTALL ({sum(len(pkgs) for pkgs in missing_packages.values())}):{RESET}")
            for pkg_type, packages in missing_packages.items():
                if packages:
                    print(f"  {pkg_type.title()}: {', '.join(packages)}")

        if extra_packages:
            print(f"\n{BLUE}ADOPT ({sum(len(pkgs) for pkgs in extra_packages.values())}):{RESET}")
            for pkg_type, packages in extra_packages.items():
                if packages:
                    print(f"  {pkg_type.title()}: {', '.join(packages)}")

        print(f"\nThis will install missing packages and keep all extras in your {self.machine_name} config.")
        print("No packages will be removed from your system.")

        try:
            confirm = input("\nProceed? (y/N): ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not confirm.startswith("y"):
            return

        # Install missing packages
        if missing_packages:
            say("Installing missing packages...")
            self._run_brew_bundle("install", capture_output=False)

        # Adopt extra packages to machine group
        if extra_packages:
            say(f"Adopting extra packages to {self.machine_name} group...")
            self.config.ensure_group_exists(self.machine_name)
            group = self.config.packages[self.machine_name]

            for package_type_str, packages in extra_packages.items():
                for package in packages:
                    package_type = PackageType.from_plural(package_type_str)
                    group.add_package(package_type, package)

            # Add machine group to machine's groups if not already there
            machine_groups = self.config.machines.get(self.machine_name, [])
            if self.machine_name not in machine_groups:
                machine_groups.append(self.machine_name)
                self.config.machines[self.machine_name] = machine_groups

            self.config.save(self.config_file)

            # Regenerate Brewfile
            self._dump_brewfile_from_config()

        success("Sync + Adopt complete!")

    def cmd_sync_cleanup(self) -> None:
        """Install missing packages and remove extras from system."""
        analyzer, groups, configured_packages = self._ensure_setup(require_brewfile=True)

        missing_packages = analyzer.get_missing_packages(configured_packages)
        extra_packages = analyzer.get_extra_packages(configured_packages)

        if not missing_packages and not extra_packages:
            success("All packages are already synchronized!")
            return

        print(f"\n{YELLOW}Sync + Cleanup Summary:{RESET}")
        if missing_packages:
            print(f"\n{GREEN}INSTALL ({sum(len(pkgs) for pkgs in missing_packages.values())}):{RESET}")
            for pkg_type, packages in missing_packages.items():
                if packages:
                    print(f"  {pkg_type.title()}: {', '.join(packages)}")

        if extra_packages:
            print(f"\n{RED}⚠ REMOVE ({sum(len(pkgs) for pkgs in extra_packages.values())}):{RESET}")
            for pkg_type, packages in extra_packages.items():
                if packages:
                    print(f"  {pkg_type.title()}: {', '.join(packages)}")

        print("\nThis will install missing packages and remove extras from your system.")
        if extra_packages:
            print(f"{RED}WARNING: This will uninstall packages from your system!{RESET}")

        try:
            confirm = input("\nProceed? (y/N): ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not confirm.startswith("y"):
            return

        # Generate Brewfile from CONFIG ONLY for both install and cleanup
        self._dump_brewfile_from_config()

        # Install missing packages first
        if missing_packages:
            say("Installing missing packages...")
            self._run_brew_bundle("install", capture_output=False)

        # Remove extra packages
        if extra_packages:
            say("Removing extra packages...")
            try:
                self._run_brew_bundle("cleanup --force", capture_output=False)
                success("Sync + Cleanup complete!")
            except subprocess.CalledProcessError:
                warn("Cleanup portion failed, but install may have succeeded.")
        else:
            success("Sync + Cleanup complete!")

    def cmd_add(self, package_name: str, package_type: Optional[PackageType] = None) -> None:
        """Add package to configuration, Brewfile, and install it."""
        if not self.is_configured:
            die("Machine not configured. Run 'brewfile init' first.")

        try:
            # 1. Auto-detect package type if not specified
            if not package_type:
                say(f"Detecting package type for '{package_name}'...")
                package_type = self.analyzer.detect_package_type(package_name)
                say(f"Detected '{package_name}' as {package_type.value}")

            # 2. Pre-validate: select group before making system changes
            target_group = self._select_group_for_package(package_name)

            # 3. Install the package
            say(f"Installing {package_name}...")
            if package_type == PackageType.CASK:
                subprocess.run(["brew", "install", "--cask", package_name], check=True)
            else:
                subprocess.run(["brew", "install", package_name], check=True)

            # 4. Add to configuration (with rollback on failure)
            try:
                self.config.add_package(target_group, package_type, package_name, self.config_file)
                # Regenerate Brewfile after config change
                self._dump_brewfile_from_config()
                success(f"Added {package_name} to group '{target_group}' and installed successfully")
            except Exception as config_error:
                # Rollback: remove the package we just installed
                warn("Config update failed, rolling back installation...")
                try:
                    if package_type == PackageType.CASK:
                        subprocess.run(
                            ["brew", "uninstall", "--cask", package_name],
                            check=True,
                            capture_output=True,
                        )
                    else:
                        subprocess.run(
                            ["brew", "uninstall", package_name],
                            check=True,
                            capture_output=True,
                        )
                    say(f"Rolled back installation of {package_name}")
                except subprocess.CalledProcessError:
                    warn(f"Could not rollback installation of {package_name} - you may need to remove it manually")
                raise config_error

        except subprocess.CalledProcessError as e:
            error(f"Failed to add {package_name}: {e}")
        except Exception as e:
            error(f"Unexpected error adding {package_name}: {e}")

    def _select_group_for_package(self, package_name: str) -> str:
        """Interactively select which group to add the package to."""
        available_groups = self.machine_groups
        default_group = self.machine_name

        print(f"\nAdd '{package_name}' to group [default: {default_group}]:")
        for i, group in enumerate(available_groups, 1):
            print(f"  {i}. {group}")
        print("  n. Create new group")

        try:
            choice = input("Choice: ").strip().lower()

            if not choice:  # Use default
                return default_group
            elif choice == "n":
                new_group = input("Enter new group name: ").strip()
                if new_group and new_group not in self.config.packages:
                    self.config.ensure_group_exists(new_group)
                    machine_groups = self.config.machines.get(self.machine_name, [])
                    if new_group not in machine_groups:
                        machine_groups.append(new_group)
                        self.config.machines[self.machine_name] = machine_groups
                    self.config.save(self.config_file)
                    return new_group
                warn("Invalid group name, using default")
                return default_group
            elif choice.isdigit() and 1 <= int(choice) <= len(available_groups):
                return available_groups[int(choice) - 1]
            else:
                warn("Invalid choice, using default")
                return default_group

        except (EOFError, KeyboardInterrupt, ValueError):
            print()
            return default_group

    def cmd_remove(self, package_name: str) -> None:
        """Remove package from configuration and system (idempotent - only removes from config if system removal succeeds)."""
        if not self.is_configured:
            die("Machine not configured. Run 'brewfile init' first.")

        try:
            # 1. Find package info before removal
            package_info = self.config.get_package_info(package_name)
            if not package_info:
                warn(f"Package {package_name} not found in configuration")
                return

            # 2. Ask user to confirm removal from both system and config
            print(
                f"Remove {package_name} ({package_info.package_type.value}) from system and configuration? (y/N): ",
                end="",
            )
            try:
                remove_confirmed = input().lower().startswith("y")
            except (EOFError, KeyboardInterrupt):
                print()
                return

            if not remove_confirmed:
                say("Removal cancelled.")
                return

            # 3. Try to remove from system first (idempotent behavior)
            try:
                say(f"Uninstalling {package_name}...")
                if package_info.package_type == PackageType.CASK:
                    subprocess.run(["brew", "uninstall", "--cask", package_name], check=True)
                else:
                    subprocess.run(["brew", "uninstall", package_name], check=True)
            except subprocess.CalledProcessError as e:
                error(f"Failed to uninstall {package_name} from system: {e}")
                error("Package NOT removed from configuration (keeping config in sync with system)")
                return

            # 4. Only remove from config if system removal succeeded
            rm_pkg_type = self.config.remove_package(package_name, self.config_file)

            # 5. Regenerate Brewfile from config
            self._dump_brewfile_from_config()

            success(
                f"Removed {package_name} ({rm_pkg_type.value if rm_pkg_type else 'unknown'}) from system and config"
            )

        except subprocess.CalledProcessError as e:
            error(f"Failed to remove {package_name}: {e}")

    def cmd_interactive(self) -> None:
        """Interactive package management with detailed status and streamlined actions."""
        if not self.is_configured:
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
            # Always show detailed status
            total_missing, total_extra = self.cmd_status()

            if total_missing == 0 and total_extra == 0:
                return

            print("\nWhat would you like to do?")
            print("  (1) Sync + Adopt (install missing + keep extras)")
            print("  (2) Sync + Cleanup (install missing + remove extras)")
            print("  (3) Edit config manually")
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
                self.cmd_sync_adopt()
            elif choice == "2":
                self.cmd_sync_cleanup()
            elif choice == "3":
                self.cmd_edit()
            else:
                warn("Invalid choice.")

            print()  # Space between iterations

    def cmd_edit(self) -> None:
        """Open config file in editor for manual editing."""
        editor = os.environ.get("EDITOR", "nano")
        try:
            subprocess.run([editor, str(self.config_file)], check=True)
            # Reload config after editing
            self.config = BrewfileConfig.load(self.config_file)
            success("Config reloaded after editing.")
        except subprocess.CalledProcessError:
            warn("Failed to open editor.")


def show_help():
    """Display comprehensive help information."""
    print(f"{BLUE}BrewfileManager{RESET} - Intelligent Homebrew package management")
    print("\nUSAGE:")
    print("  brewfile [COMMAND] [OPTIONS]")
    print("  brewfile                    # Interactive mode (default)")

    print("\nCOMMANDS:")
    print(f"  {GREEN}init{RESET}                    Initialize machine configuration")
    print(f"  {GREEN}status{RESET}                  Show package status and synchronization state")
    print(f"  {GREEN}sync-adopt{RESET}              Install missing packages + adopt extras")
    print(f"  {GREEN}sync-cleanup{RESET}            Install missing packages + remove extras")
    print(f"  {GREEN}add{RESET} <package> [--cask]   Add package to configuration and install")
    print(f"  {GREEN}remove{RESET} <package>        Remove package from system and configuration (idempotent)")
    print(f"  {GREEN}edit{RESET}                    Open configuration file in editor")
    print(f"  {GREEN}help{RESET}, -h, --help        Show this help message")

    print("\nEXAMPLES:")
    print("  brewfile status              # Show current package status")
    print("  brewfile add neovim          # Add and install neovim (auto-detected as formula)")
    print("  brewfile add --cask chrome   # Add and install Chrome as cask")
    print("  brewfile remove python       # Remove python from system and config (idempotent)")
    print("  brewfile sync-adopt          # Sync packages and keep all extras")
    print("  brewfile sync-cleanup        # Sync packages and remove extras (destructive)")

    print("\nCONFIGURATION:")
    print(f"  Config file: {GRAY}~/.config/brewfile/config.json{RESET}")
    print(f"  Brewfile:    {GRAY}~/Brewfile{RESET}")

    print("\nMORE INFO:")
    print("  - Uses JSON configuration with package groups")
    print("  - Machine-aware installations")
    print("  - Leverages 'brew bundle' for all operations")
    print("  - Supports taps, formulas, casks, and Mac App Store apps")


def main():
    """Main function."""
    if len(sys.argv) < 2:
        manager = BrewfileManager()
        manager.cmd_interactive()
        return

    # Handle help before creating manager (faster)
    command = sys.argv[1]
    if command in ["help", "-h", "--help"]:
        show_help()
        return

    manager = BrewfileManager()

    if command == "init" or command == "select":
        manager.cmd_init()
    elif command == "status":
        manager.cmd_status()
    elif command == "sync-adopt":
        manager.cmd_sync_adopt()
    elif command == "sync-cleanup":
        manager.cmd_sync_cleanup()
    elif command == "add":
        if len(sys.argv) < 3:
            error("Usage: brewfile add <package_name> [--cask]")
            sys.exit(1)
        package_name = sys.argv[2]
        # Auto-detect package type unless --cask is explicitly specified
        package_type = PackageType.CASK if "--cask" in sys.argv else None
        manager.cmd_add(package_name, package_type)
    elif command == "remove":
        if len(sys.argv) < 3:
            error("Usage: brewfile remove <package_name>")
            sys.exit(1)
        package_name = sys.argv[2]
        manager.cmd_remove(package_name)
    elif command == "edit":
        manager.cmd_edit()
    else:
        error(f"Unknown command: {command}")
        print(f"Run '{GREEN}brewfile help{RESET}' to see available commands.")
        sys.exit(1)


if __name__ == "__main__":
    main()
