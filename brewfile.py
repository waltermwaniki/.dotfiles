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


class BrewfileManager:
    """Manages Homebrew packages using JSON config and brew bundle."""
    
    def __init__(self):
        self.config_dir = Path.home() / ".config" / "brewfile"
        self.config_file = self.config_dir / "config.json"
        self.brewfile_path = Path.home() / "Brewfile"
        self.machine_name = socket.gethostname().split('.')[0]  # Short hostname
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        if not self.config_file.exists():
            return self._create_default_config()
        
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            # Validate basic structure
            required_keys = ['version', 'packages', 'machines']
            for key in required_keys:
                if key not in config:
                    warn(f"Config missing required key: {key}")
                    return self._create_default_config()
            
            return config
        except (json.JSONDecodeError, FileNotFoundError) as e:
            warn(f"Could not load config: {e}")
            return self._create_default_config()
    
    def _create_default_config(self) -> Dict[str, Any]:
        """Create default configuration structure."""
        return {
            "version": "1.0",
            "packages": {},
            "machines": {}
        }
    
    def _save_config(self) -> None:
        """Save configuration to JSON file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except OSError as e:
            die(f"Could not save config: {e}")
    
    def _get_machine_groups(self) -> List[str]:
        """Get package groups for current machine."""
        groups = self.config.get('machines', {}).get(self.machine_name, [])
        
        # Auto-include machine-specific group if it exists
        if self.machine_name in self.config.get('packages', {}):
            if self.machine_name not in groups:
                groups.append(self.machine_name)
        
        return groups
    
    def _set_machine_groups(self, groups: List[str]) -> None:
        """Set package groups for current machine."""
        if 'machines' not in self.config:
            self.config['machines'] = {}
        self.config['machines'][self.machine_name] = groups
        self._save_config()
    
    def _get_available_groups(self) -> List[str]:
        """Get all available package groups."""
        return list(self.config.get('packages', {}).keys())
    
    def _collect_packages_for_groups(self, groups: List[str]) -> Dict[str, List[Tuple[str, str]]]:
        """Collect all packages for given groups, with group information."""
        collected = {'taps': [], 'brews': [], 'casks': []}
        
        for group in groups:
            group_packages = self.config.get('packages', {}).get(group, {})
            for package_type in ['taps', 'brews', 'casks']:
                packages = group_packages.get(package_type, [])
                for package in packages:
                    # Check if package already exists
                    existing = next((p for p, g in collected[package_type] if p == package), None)
                    if not existing:
                        collected[package_type].append((package, group))
        
        return collected
    
    def _generate_brewfile_content(self, groups: List[str]) -> str:
        """Generate Brewfile content for given groups."""
        packages = self._collect_packages_for_groups(groups)
        
        lines = []
        
        # Add taps
        for tap, group in packages['taps']:
            lines.append(f'tap "{tap}"')
        
        if packages['taps']:
            lines.append('')  # Empty line after taps
        
        # Add brews
        for brew, group in packages['brews']:
            lines.append(f'brew "{brew}"')
        
        if packages['brews']:
            lines.append('')  # Empty line after brews
        
        # Add casks
        for cask, group in packages['casks']:
            lines.append(f'cask "{cask}"')
        
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
            packages = {'taps': [], 'brews': [], 'casks': []}
            
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
            
            return packages
            
        except subprocess.CalledProcessError as e:
            die(f"Could not get system packages: {e}")
        finally:
            Path(temp_brewfile).unlink(missing_ok=True)
    
    def _check_machine_configured(self) -> bool:
        """Check if current machine is configured."""
        return self.machine_name in self.config.get('machines', {})
    
    def _ensure_machine_group_exists(self) -> None:
        """Ensure machine-specific package group exists in config."""
        if self.machine_name not in self.config.get('packages', {}):
            self.config.setdefault('packages', {})[self.machine_name] = {
                'taps': [],
                'brews': [],
                'casks': []
            }
            self._save_config()
    
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
        
        # Always get fresh system state
        system_packages = self._get_system_packages(clean_first=True)
        
        groups = self._get_machine_groups()
        configured_packages = self._collect_packages_for_groups(groups)
        
        print(f"\n{BLUE}Package Status for {self.machine_name}:{RESET}")
        print(f"Groups: {', '.join(groups)}")
        
        # Check each package type
        for package_type in ['taps', 'brews', 'casks']:
            # Extract just the package names for comparison
            configured_names = [p for p, g in configured_packages[package_type]]
            installed = set(system_packages[package_type])
            
            missing_names = set(configured_names) - installed
            extra = installed - set(configured_names)
            
            # Show configured packages first
            if configured_packages[package_type]:
                print(f"\n{package_type.title()}:")
                for package, group in sorted(configured_packages[package_type]):
                    if package in missing_names:
                        print(f"  ! {package} {GRAY}({group}){RESET}")
                    else:
                        print(f"  ✓ {package} {GRAY}({group}){RESET}")
            
            # Show extra packages that aren't in any group
            if extra:
                if configured_packages[package_type]:  # Only add extra header if we had configured packages
                    print(f"\n{package_type.title()} (extra):")
                else:  # No configured packages, so this is the main section
                    print(f"\n{package_type.title()}:")
                for package in sorted(extra):
                    print(f"  * {package}")
        
        # Summary
        total_missing = 0
        total_extra = 0
        
        for package_type in ['taps', 'brews', 'casks']:
            configured_names = [p for p, g in configured_packages[package_type]]
            installed = set(system_packages[package_type])
            
            total_missing += len(set(configured_names) - installed)
            total_extra += len(installed - set(configured_names))
        
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
        
        say("Removing packages not in Brewfile...")
        try:
            self._run_brew_bundle("cleanup", capture_output=False)
            success("Package cleanup complete!")
        except subprocess.CalledProcessError:
            warn("Cleanup cancelled or failed.")
    
    def cmd_sync(self) -> None:
        """Install missing and remove extra packages."""
        say("Synchronizing packages...")
        self.cmd_install()
        self.cmd_cleanup()
        success("Package sync complete!")
    
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
        for package_type in ['taps', 'brews', 'casks']:
            configured_names = [p for p, g in configured_packages[package_type]]
            installed = set(system_packages[package_type])
            extra = installed - set(configured_names)
            
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
        machine_groups = self.config.get('machines', {}).get(self.machine_name, [])
        if self.machine_name not in machine_groups:
            machine_groups.append(self.machine_name)
            self.config.setdefault('machines', {})[self.machine_name] = machine_groups
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
        
        if group_name in self.config.get('packages', {}):
            warn(f"Group '{group_name}' already exists.")
            return
        
        # Create new group
        self.config.setdefault('packages', {})[group_name] = {
            'taps': [],
            'brews': [],
            'casks': []
        }
        
        self._add_packages_to_group(packages, group_name)
        
        # Ask if they want to add this group to current machine
        print(f"\nAdd '{group_name}' to this machine's groups? (y/N): ", end="")
        try:
            if input().lower().startswith('y'):
                machine_groups = self.config.get('machines', {}).get(self.machine_name, [])
                machine_groups.append(group_name)
                self.config.setdefault('machines', {})[self.machine_name] = machine_groups
                self._save_config()
        except (EOFError, KeyboardInterrupt):
            print()
    
    def _add_packages_to_group(self, packages: List[Tuple[str, str]], group_name: str) -> None:
        """Add packages to a specific group."""
        group = self.config['packages'][group_name]
        
        for package_type, package in packages:
            if package not in group[package_type]:
                group[package_type].append(package)
        
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
