#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BrewfileManager — Intelligent Homebrew package management using brew bundle.

Uses JSON configuration with package groups and machine-aware installations,
while leveraging brew bundle for all actual package operations.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any

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
    taps: List[str] = field(default_factory=list)
    brews: List[str] = field(default_factory=list)
    casks: List[str] = field(default_factory=list)
    mas: List[str] = field(default_factory=list)

    def get_all_packages(self) -> Dict[str, List[str]]:
        """Get all packages as a dictionary."""
        return {
            'taps': self.taps.copy(),
            'brews': self.brews.copy(),
            'casks': self.casks.copy(),
            'mas': self.mas.copy()
        }

    def add_package(self, package_type: str, package_name: str) -> None:
        """Add a package to this group."""
        if package_type == 'taps':
            if package_name not in self.taps:
                self.taps.append(package_name)
        elif package_type == 'brews':
            if package_name not in self.brews:
                self.brews.append(package_name)
        elif package_type == 'casks':
            if package_name not in self.casks:
                self.casks.append(package_name)
        elif package_type == 'mas':
            if package_name not in self.mas:
                self.mas.append(package_name)
        else:
            raise ValueError(f"Unknown package type: {package_type}")

    def remove_package(self, package_type: str, package_name: str) -> bool:
        """Remove a package from this group. Returns True if removed."""
        if package_type == 'taps' and package_name in self.taps:
            self.taps.remove(package_name)
            return True
        elif package_type == 'brews' and package_name in self.brews:
            self.brews.remove(package_name)
            return True
        elif package_type == 'casks' and package_name in self.casks:
            self.casks.remove(package_name)
            return True
        elif package_type == 'mas' and package_name in self.mas:
            self.mas.remove(package_name)
            return True
        return False


@dataclass
class PackageStatus:
    """Status information for a package."""
    name: str
    group: str
    package_type: str  # 'tap', 'brew', 'cask'
    installed: bool


@dataclass
class BrewfileConfig:
    """Complete brewfile configuration."""
    version: str = "1.0"
    packages: Dict[str, PackageGroup] = field(default_factory=dict)
    machines: Dict[str, List[str]] = field(default_factory=dict)  # hostname -> group names

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BrewfileConfig':
        """Create config from dictionary (loaded JSON)."""
        # Convert package groups from dict to PackageGroup objects
        packages = {}
        for name, pkg_data in data.get('packages', {}).items():
            packages[name] = PackageGroup(
                taps=pkg_data.get('taps', []),
                brews=pkg_data.get('brews', []),
                casks=pkg_data.get('casks', []),
                mas=pkg_data.get('mas', [])
            )

        return cls(
            version=data.get('version', '1.0'),
            packages=packages,
            machines=data.get('machines', {})
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for JSON serialization."""
        packages_dict = {}
        for name, pkg_group in self.packages.items():
            packages_dict[name] = {
                'taps': pkg_group.taps,
                'brews': pkg_group.brews,
                'casks': pkg_group.casks,
                'mas': pkg_group.mas
            }

        return {
            'version': self.version,
            'packages': packages_dict,
            'machines': self.machines
        }

    def get_machine_groups(self, machine_name: str) -> List[str]:
        """Get package groups for a specific machine."""
        groups = self.machines.get(machine_name, [])

        # Auto-include machine-specific group if it exists
        if machine_name in self.packages:
            if machine_name not in groups:
                groups = groups + [machine_name]

        return groups

    def set_machine_groups(self, machine_name: str, groups: List[str]) -> None:
        """Set package groups for a specific machine."""
        self.machines[machine_name] = groups

    def get_available_groups(self) -> List[str]:
        """Get all available package groups."""
        return list(self.packages.keys())

    def ensure_group_exists(self, group_name: str) -> None:
        """Ensure a package group exists."""
        if group_name not in self.packages:
            self.packages[group_name] = PackageGroup()

    def collect_packages_for_groups(self, groups: List[str]) -> List[PackageStatus]:
        """Collect all packages for given groups with status information."""
        packages = []
        seen_packages = set()  # Track (package_type, package_name) to avoid duplicates

        for group in groups:
            if group not in self.packages:
                continue

            group_data = self.packages[group]

            # Process each package type
            for package_type in ['taps', 'brews', 'casks', 'mas']:
                package_list = getattr(group_data, package_type)
                for package in package_list:
                    package_key = (package_type, package)
                    if package_key not in seen_packages:
                        # Handle package type naming (remove 's' for most, keep 'mas' as 'mas')
                        display_type = package_type[:-1] if package_type != 'mas' else 'mas'
                        packages.append(PackageStatus(
                            name=package,
                            group=group,
                            package_type=display_type,
                            installed=False  # Will be updated by caller
                        ))
                        seen_packages.add(package_key)

        return packages


class BrewfileManager:
    """Manages Homebrew packages using JSON config and brew bundle."""

    def __init__(self):
        self.config_dir = Path.home() / ".config" / "brewfile"
        self.config_file = self.config_dir / "config.json"
        self.brewfile_path = Path.home() / "Brewfile"
        self.machine_name = socket.gethostname().split('.')[0]  # Short hostname
        self.config = self._load_config()

    def _load_config(self) -> BrewfileConfig:
        """Load configuration from JSON file."""
        if not self.config_file.exists():
            return self._create_default_config()

        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)

            # Validate basic structure
            required_keys = ['version', 'packages', 'machines']
            for key in required_keys:
                if key not in data:
                    warn(f"Config missing required key: {key}")
                    return self._create_default_config()

            return BrewfileConfig.from_dict(data)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            warn(f"Could not load config: {e}")
            return self._create_default_config()

    def _create_default_config(self) -> BrewfileConfig:
        """Create default configuration structure."""
        return BrewfileConfig()

    def _save_config(self) -> None:
        """Save configuration to JSON file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config.to_dict(), f, indent=2)
        except OSError as e:
            die(f"Could not save config: {e}")

    def _get_machine_groups(self) -> List[str]:
        """Get package groups for current machine."""
        return self.config.get_machine_groups(self.machine_name)

    def _set_machine_groups(self, groups: List[str]) -> None:
        """Set package groups for current machine."""
        self.config.set_machine_groups(self.machine_name, groups)
        self._save_config()

    def _get_available_groups(self) -> List[str]:
        """Get all available package groups."""
        return self.config.get_available_groups()

    def _collect_packages_for_groups(self, groups: List[str]) -> List[PackageStatus]:
        """Collect all packages for given groups with status information."""
        return self.config.collect_packages_for_groups(groups)

    def _generate_brewfile_content(self, groups: List[str]) -> str:
        """Generate Brewfile content for given groups."""
        packages = self._collect_packages_for_groups(groups)

        # Group packages by type
        taps = [p.name for p in packages if p.package_type == 'tap']
        brews = [p.name for p in packages if p.package_type == 'brew']
        casks = [p.name for p in packages if p.package_type == 'cask']
        mas_apps = [p.name for p in packages if p.package_type == 'mas']

        lines = []

        # Add taps
        for tap in taps:
            lines.append(f'tap "{tap}"')

        if taps:
            lines.append('')  # Empty line after taps

        # Add brews
        for brew in brews:
            lines.append(f'brew "{brew}"')

        if brews:
            lines.append('')  # Empty line after brews

        # Add casks
        for cask in casks:
            lines.append(f'cask "{cask}"')

        if casks:
            lines.append('')  # Empty line after casks

        # Add mas apps (note: we can't regenerate IDs, so this is basic)
        for mas_app in mas_apps:
            lines.append(f'# mas "{mas_app}" # ID needed - check with: mas list')

        return '\n'.join(lines) + '\n'

    def _write_brewfile(self, content: str) -> None:
        """Write content to ~/Brewfile."""
        try:
            with open(self.brewfile_path, 'w') as f:
                f.write(content)
        except OSError as e:
            die(f"Could not write Brewfile: {e}")

    def _run_brew_bundle(self, command: str, capture_output: bool = True) -> subprocess.CompletedProcess:
        """Run brew bundle command."""
        cmd = ['brew', 'bundle'] + command.split()

        try:
            if capture_output:
                return subprocess.run(cmd, capture_output=True, text=True, check=True)
            else:
                return subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            if capture_output:
                error(f"brew bundle failed: {e.stderr}")
            die(f"Command failed: {' '.join(cmd)}")

    def _clean_brew_system(self) -> None:
        """Clean brew system before package discovery."""
        try:
            say("Cleaning brew packages...")
            # Remove orphaned dependencies
            subprocess.run(['brew', 'autoremove'], check=False, capture_output=True)
            # Clear caches
            subprocess.run(['brew', 'cleanup'], check=False, capture_output=True)
        except subprocess.CalledProcessError:
            # Don't fail if cleanup fails
            pass

    def _get_system_packages(self, clean_first: bool = True) -> Dict[str, List[str]]:
        """Get currently installed packages using brew bundle dump."""
        if clean_first:
            self._clean_brew_system()

        with tempfile.NamedTemporaryFile(mode='w+', suffix='.brewfile', delete=False) as f:
            temp_brewfile = f.name

        try:
            # Use brew bundle dump to get current state (excluding VS Code extensions)
            result = subprocess.run(
                ['brew', 'bundle', 'dump', '--file', temp_brewfile, '--force', '--no-vscode'],
                capture_output=True, text=True, check=True
            )

            # Parse the generated Brewfile
            packages = {'taps': [], 'brews': [], 'casks': [], 'mas': []}

            with open(temp_brewfile, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('tap '):
                        tap = line.split('"')[1]
                        packages['taps'].append(tap)
                    elif line.startswith('brew '):
                        brew = line.split('"')[1]
                        packages['brews'].append(brew)
                    elif line.startswith('cask '):
                        cask = line.split('"')[1]
                        packages['casks'].append(cask)
                    elif line.startswith('mas '):
                        # Parse mas entry like: mas "App Name", id: 123456
                        mas_name = line.split('"')[1]
                        packages['mas'].append(mas_name)

            # Fallback: Check for packages missing from brew bundle dump but actually installed
            # This can happen if packages were installed as dependencies
            self._add_missing_installed_packages(packages)

            return packages

        except subprocess.CalledProcessError as e:
            die(f"Could not get system packages: {e}")
        finally:
            Path(temp_brewfile).unlink(missing_ok=True)

    def _add_missing_installed_packages(self, packages: Dict[str, List[str]]) -> None:
        """Add packages that are installed but missing from brew bundle dump."""
        try:
            # Get all installed formulae
            result = subprocess.run(['brew', 'list', '--formula'], capture_output=True, text=True, check=True)
            installed_brews = set(result.stdout.strip().split())
            
            # Get all installed casks  
            result = subprocess.run(['brew', 'list', '--cask'], capture_output=True, text=True, check=True)
            installed_casks = set(result.stdout.strip().split())
            
            # Add missing brews
            current_brews = set(packages['brews'])
            missing_brews = installed_brews - current_brews
            packages['brews'].extend(list(missing_brews))
            
            # Add missing casks
            current_casks = set(packages['casks'])
            missing_casks = installed_casks - current_casks
            packages['casks'].extend(list(missing_casks))
            
        except subprocess.CalledProcessError:
            # If fallback detection fails, continue with what we have
            pass

    def _check_machine_configured(self) -> bool:
        """Check if current machine is configured."""
        return self.machine_name in self.config.machines

    def _ensure_machine_group_exists(self) -> None:
        """Ensure machine-specific package group exists in config."""
        self.config.ensure_group_exists(self.machine_name)
        self._save_config()

    def _get_missing_packages(self) -> Dict[str, List[str]]:
        """Get packages that are configured but not installed."""
        system_packages = self._get_system_packages(clean_first=False)
        groups = self._get_machine_groups()
        configured_packages = self._collect_packages_for_groups(groups)

        missing = {'taps': [], 'brews': [], 'casks': [], 'mas': []}

        # Group configured packages by type
        packages_by_type = {
            'taps': [p for p in configured_packages if p.package_type == 'tap'],
            'brews': [p for p in configured_packages if p.package_type == 'brew'],
            'casks': [p for p in configured_packages if p.package_type == 'cask'],
            'mas': [p for p in configured_packages if p.package_type == 'mas']
        }

        # Find missing packages for each type
        for pkg_type, packages in packages_by_type.items():
            configured_names = {p.name for p in packages}
            installed = set(system_packages.get(pkg_type, []))
            missing_names = configured_names - installed
            missing[pkg_type] = list(missing_names)

        return missing

    def _get_extra_packages(self) -> Dict[str, List[str]]:
        """Get packages that are installed but not configured."""
        system_packages = self._get_system_packages(clean_first=False)
        groups = self._get_machine_groups()
        configured_packages = self._collect_packages_for_groups(groups)

        extra = {'taps': [], 'brews': [], 'casks': [], 'mas': []}

        # Group configured packages by type
        packages_by_type = {
            'taps': [p for p in configured_packages if p.package_type == 'tap'],
            'brews': [p for p in configured_packages if p.package_type == 'brew'],
            'casks': [p for p in configured_packages if p.package_type == 'cask'],
            'mas': [p for p in configured_packages if p.package_type == 'mas']
        }

        # Find extra packages for each type
        for pkg_type, packages in packages_by_type.items():
            configured_names = {p.name for p in packages}
            installed = set(system_packages.get(pkg_type, []))
            extra_names = installed - configured_names
            extra[pkg_type] = list(extra_names)

        return extra

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
        success(f"Machine {self.machine_name} configured with groups: {', '.join(selected_groups)}")

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

        groups = self._get_machine_groups()
        configured_packages = self._collect_packages_for_groups(groups)

        # Get missing and extra packages using DRY helper methods
        missing_packages = self._get_missing_packages()
        extra_packages = self._get_extra_packages()

        # Update installation status for configured packages
        system_packages = self._get_system_packages(clean_first=True)
        for pkg in configured_packages:
            # Convert package type to plural form for system_packages lookup
            if pkg.package_type == 'mas':
                pkg_type_plural = 'mas'  # MAS is already plural form in system_packages
            else:
                pkg_type_plural = f"{pkg.package_type}s"
            pkg.installed = pkg.name in system_packages.get(pkg_type_plural, [])

        print(f"\n{BLUE}Package Status for {self.machine_name}:{RESET}")
        print(f"Groups: {', '.join(groups)}")

        # Group packages by type for display
        packages_by_type = {
            'taps': [p for p in configured_packages if p.package_type == 'tap'],
            'brews': [p for p in configured_packages if p.package_type == 'brew'],
            'casks': [p for p in configured_packages if p.package_type == 'cask'],
            'mas': [p for p in configured_packages if p.package_type == 'mas']
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

        print(f"\nSummary:")
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

        # Get what would be installed
        missing_packages = self._get_missing_packages()
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

        if not confirm.startswith('y'):
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

        # Get what would be removed
        extra_packages = self._get_extra_packages()
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

        if not confirm.startswith('y'):
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

        # Get what would be changed
        missing_packages = self._get_missing_packages()
        extra_packages = self._get_extra_packages()

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

        install_count = sum(len(pkgs) for pkgs in missing_packages.values()) if missing_packages else 0
        remove_count = sum(len(pkgs) for pkgs in extra_packages.values()) if extra_packages else 0

        print(f"\nTotal: {install_count} to install, {remove_count} to remove.")
        if remove_count > 0:
            print(f"{RED}WARNING: This will uninstall packages from your system!{RESET}")

        try:
            confirm = input("\nProceed with synchronization? (y/N): ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            say("Synchronization cancelled.")
            print()
            return

        if not confirm.startswith('y'):
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

        groups = self._get_machine_groups()
        configured_packages = self._collect_packages_for_groups(groups)
        system_packages = self._get_system_packages(clean_first=False)  # Don't clean again

        # Find extra packages
        extra_packages = []
        for package_type in ['taps', 'brews', 'casks', 'mas']:
            # Handle package type naming for comparison
            compare_type = package_type[:-1] if package_type != 'mas' else 'mas'
            configured_names = {p.name for p in configured_packages if p.package_type == compare_type}
            installed = set(system_packages[package_type])
            extra = installed - configured_names

            for package in extra:
                extra_packages.append((package_type, package))

        if not extra_packages:
            success("No extra packages to adopt!")
            return

        say(f"Found {len(extra_packages)} extra package(s) not in config:")
        for package_type, package in extra_packages[:10]:  # Show first 10
            print(f"  * {package} ({package_type[:-1]})")

        if len(extra_packages) > 10:
            print(f"  ... and {len(extra_packages) - 10} more")

        print(f"\nHow would you like to handle these packages?")
        print(f"  (1) Add to existing group")
        print(f"  (2) Add to machine group ({self.machine_name})")
        print(f"  (3) Create new group")
        print(f"  (4) Edit config manually")
        print(f"  (5) Remove from system")
        print(f"  (q) Skip for now")

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

    def _adopt_to_existing_group(self, packages: List[Tuple[str, str]]) -> None:
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

    def _adopt_to_machine_group(self, packages: List[Tuple[str, str]]) -> None:
        """Adopt packages to machine-specific group."""
        self._ensure_machine_group_exists()
        self._add_packages_to_group(packages, self.machine_name)

        # Add machine group to machine's groups if not already there
        machine_groups = self.config.machines.get(self.machine_name, [])
        if self.machine_name not in machine_groups:
            machine_groups.append(self.machine_name)
            self.config.machines[self.machine_name] = machine_groups
            self._save_config()

    def _adopt_to_new_group(self, packages: List[Tuple[str, str]]) -> None:
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
            if input().lower().startswith('y'):
                machine_groups = self.config.machines.get(self.machine_name, [])
                machine_groups.append(group_name)
                self.config.machines[self.machine_name] = machine_groups
                self._save_config()
        except (EOFError, KeyboardInterrupt):
            print()

    def _add_packages_to_group(self, packages: List[Tuple[str, str]], group_name: str) -> None:
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
        editor = os.environ.get('EDITOR', 'nano')
        try:
            subprocess.run([editor, str(self.config_file)], check=True)
            # Reload config after editing
            self.config = self._load_config()
            success("Config reloaded after editing.")
        except subprocess.CalledProcessError:
            warn("Failed to open editor.")

    def _remove_extra_packages(self, packages: List[Tuple[str, str]]) -> None:
        """Remove extra packages from system."""
        print(f"\nThis will remove {len(packages)} package(s) from your system.")
        print("Are you sure? (y/N): ", end="")
        try:
            if not input().lower().startswith('y'):
                return
        except (EOFError, KeyboardInterrupt):
            print()
            return

        for package_type, package in packages:
            try:
                if package_type == 'casks':
                    subprocess.run(['brew', 'uninstall', '--cask', package], check=True)
                else:
                    subprocess.run(['brew', 'uninstall', package], check=True)
            except subprocess.CalledProcessError:
                warn(f"Failed to remove {package}")

        success("Package removal complete.")

    def cmd_interactive(self) -> None:
        """Interactive package management."""
        if not self._check_machine_configured():
            say(f"Machine {self.machine_name} is not configured.")
            print("Would you like to configure it now? (y/N): ", end="")
            try:
                if input().lower().startswith('y'):
                    self.cmd_init()
                else:
                    return
            except (EOFError, KeyboardInterrupt):
                print()
                return

        while True:
            self.cmd_status()

            print(f"\nWhat would you like to do?")
            print(f"  (1) Install missing packages")
            print(f"  (2) Remove extra packages")
            print(f"  (3) Adopt extra packages to config")
            print(f"  (4) Sync both (install + remove)")
            print(f"  (5) Reconfigure machine groups")
            print(f"  (6) Regenerate Brewfile")
            print(f"  (7) Edit config manually")
            print(f"  (q) Quit")

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
    elif command == "edit":
        manager._edit_config_manually()
    else:
        error(f"Unknown command: {command}")
        print("Available commands: init, select, generate, status, install, cleanup, sync, adopt, edit")
        sys.exit(1)


if __name__ == "__main__":
    main()
