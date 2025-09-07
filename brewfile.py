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
        return self.config.get('machines', {}).get(self.machine_name, [])
    
    def _set_machine_groups(self, groups: List[str]) -> None:
        """Set package groups for current machine."""
        if 'machines' not in self.config:
            self.config['machines'] = {}
        self.config['machines'][self.machine_name] = groups
        self._save_config()
    
    def _get_available_groups(self) -> List[str]:
        """Get all available package groups."""
        return list(self.config.get('packages', {}).keys())
    
    def _collect_packages_for_groups(self, groups: List[str]) -> Dict[str, List[str]]:
        """Collect all packages for given groups."""
        collected = {'taps': [], 'brews': [], 'casks': []}
        
        for group in groups:
            group_packages = self.config.get('packages', {}).get(group, {})
            for package_type in ['taps', 'brews', 'casks']:
                packages = group_packages.get(package_type, [])
                for package in packages:
                    if package not in collected[package_type]:
                        collected[package_type].append(package)
        
        return collected
    
    def _generate_brewfile_content(self, groups: List[str]) -> str:
        """Generate Brewfile content for given groups."""
        packages = self._collect_packages_for_groups(groups)
        
        lines = []
        
        # Add taps
        for tap in packages['taps']:
            lines.append(f'tap "{tap}"')
        
        if packages['taps']:
            lines.append('')  # Empty line after taps
        
        # Add brews
        for brew in packages['brews']:
            lines.append(f'brew "{brew}"')
        
        if packages['brews']:
            lines.append('')  # Empty line after brews
        
        # Add casks
        for cask in packages['casks']:
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
    
    def _get_system_packages(self) -> Dict[str, List[str]]:
        """Get currently installed packages using brew bundle dump."""
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.brewfile', delete=False) as f:
            temp_brewfile = f.name
        
        try:
            # Use brew bundle dump to get current state
            result = subprocess.run(
                ['brew', 'bundle', 'dump', '--file', temp_brewfile, '--force'],
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
        system_packages = self._get_system_packages()
        
        print(f"\n{BLUE}Package Status for {self.machine_name}:{RESET}")
        print(f"Groups: {', '.join(groups)}")
        
        # Check each package type
        for package_type in ['taps', 'brews', 'casks']:
            configured = set(configured_packages[package_type])
            installed = set(system_packages[package_type])
            
            missing = configured - installed
            extra = installed - configured
            
            if configured:
                print(f"\n{package_type.title()}:")
                for package in sorted(configured):
                    if package in missing:
                        print(f"  ! {package} {GRAY}(missing){RESET}")
                    else:
                        print(f"  ✓ {package}")
            
            if extra:
                print(f"\n{package_type.title()} (extra):")
                for package in sorted(extra):
                    print(f"  * {package} {GRAY}(not in config){RESET}")
        
        # Summary
        total_missing = len(configured_packages['taps'] + configured_packages['brews'] + configured_packages['casks'])
        total_extra = len(system_packages['taps'] + system_packages['brews'] + system_packages['casks'])
        
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
            print(f"  (3) Sync both (install + remove)")
            print(f"  (4) Reconfigure machine groups")
            print(f"  (5) Regenerate Brewfile")
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
                self.cmd_sync()
            elif choice == "4":
                self.cmd_init()
            elif choice == "5":
                self.cmd_generate()
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
    else:
        error(f"Unknown command: {command}")
        print("Available commands: init, select, generate, status, install, cleanup, sync")
        sys.exit(1)


if __name__ == "__main__":
    main()
