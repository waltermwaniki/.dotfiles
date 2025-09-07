#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brewfile.py — A Python-based manager for Brewfile dependencies.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

# ANSI colors (respect NO_COLOR and non-TTY)
BLUE = "\033[1;34m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
RESET = "\033[0m"

if "NO_COLOR" in os.environ or not sys.stdout.isatty():
    BLUE = YELLOW = RED = RESET = ""

# Regex for parsing package lines
PACKAGE_LINE_RE = re.compile(r"^(tap|brew|cask|mas|whalebrew|vscode)\s+\"([^\"]+)\"")


def say(msg):
    """Prints a message to the console with a blue '===>' prefix."""
    print(f"{BLUE}===>{RESET} {msg}")


def warn(msg):
    """Prints a warning message to the console."""
    print(f"{YELLOW}[warn]{RESET} {msg}")


def die(msg):
    """Prints an error message and exits the script."""
    print(f"{RED}[err]{RESET} {msg}", file=sys.stderr)
    sys.exit(1)


class BrewfileManager:
    """Manages Brewfile operations."""

    def __init__(self):
        self.repo_dir = self._resolve_repo_dir()
        self.brewfile = self.repo_dir / "Brewfile"
        self.extra_brewfile = self.repo_dir / "Brewfile.extra"

    # --- Helper Methods ---

    def _resolve_repo_dir(self):
        """Resolves the git repository root from the script's location."""
        try:
            script_path = Path(__file__).resolve()
            # If this is the deployed version in ~/.local/bin/, navigate back to the repo
            if '.local/bin' in str(script_path):
                return script_path.parent.parent.parent.parent
            else:
                # If running from the repo root directly, use current directory
                return Path.cwd()
        except NameError:
            return Path.cwd()

    def _ensure_brew(self):
        """Checks for the 'brew' executable in the system's PATH."""
        if not shutil.which("brew"):
            die("Homebrew command 'brew' not found in your PATH.")

    def _resolve_include_files(self, args):
        """Resolves and returns a list of include files based on args."""
        include_files = []
        if args.all:
            for path in sorted(self.repo_dir.glob("Brewfile.*")):
                if path.is_file():
                    include_files.append(path)
        elif args.include:
            names = args.include.split(",")
            for name in names:
                if name:
                    f = self.repo_dir / f"Brewfile.{name}"
                    if f.is_file():
                        include_files.append(f)
        return include_files

    @contextmanager
    def _get_merged_brewfile_path(self, args):
        """Provides the path to a temporary, merged Brewfile."""
        files_to_merge = [self.brewfile] + self._resolve_include_files(args)
        all_lines = set()
        for file_path in files_to_merge:
            if file_path.exists():
                with open(file_path, "r") as f:
                    for line in f:
                        if line.strip():
                            all_lines.add(line)
        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".Brewfile", encoding="utf-8"
            ) as tf:
                temp_file_path = Path(tf.name)
                tf.writelines(sorted(list(all_lines)))
            yield temp_file_path
        finally:
            if temp_file_path and temp_file_path.exists():
                temp_file_path.unlink()

    def _group_print(self, lines, package_origins=None):
        """Parses and prints a grouped summary of package lines."""
        if not lines:
            print("      (none)")
            return
        grouped = defaultdict(list)
        for line in lines:
            match = PACKAGE_LINE_RE.match(line)
            if match:
                kind, name = match.groups()
                origin_info = ""
                if package_origins and line in package_origins:
                    origin_info = f" (from {package_origins[line]})"
                grouped[kind].append(f"{name}{origin_info}")
            else:
                grouped["unknown"].append(line)
        for kind in ["tap", "brew", "cask", "mas", "whalebrew", "vscode", "unknown"]:
            if kind in grouped:
                names = ", ".join(sorted(grouped[kind]))
                count = len(grouped[kind])
                print(f"      {kind} ({count}): {names}")

    def _remove_line_from_file(self, file_path, line_to_remove):
        """Reads a file, removes a specific line, and writes the file back."""
        with open(file_path, "r") as f:
            lines = f.readlines()
        with open(file_path, "w") as f:
            for line in lines:
                if line.strip() != line_to_remove:
                    f.write(line)

    # --- Main Commands ---


    def _analyze_package_status(self, args):
        """Analyzes package status across all Brewfiles and returns structured data.
        
        Returns:
            dict with keys:
            - 'files_considered': List of Brewfile paths being considered
            - 'declared_packages_by_file': Dict mapping file_path -> list of (kind, name, original_line)
            - 'all_declared_lines': Set of all declared package lines
            - 'installed_lines': Set of all installed package lines
            - 'on_system_only': Set of package lines only on system
            - 'missing_from_system': Set of declared package lines not installed
            - 'all_brewfiles': Dict mapping file_path -> list of (kind, name, original_line) for ALL Brewfiles
        """
        # Collect files to consider based on args
        files_to_consider_set = set()
        files_to_consider_set.add(self.brewfile)  # Always include main
        
        if args.all:
            for path in sorted(self.repo_dir.glob("Brewfile.*")):
                if path.is_file():
                    files_to_consider_set.add(path)
        elif args.include:
            names = args.include.split(",")
            for name in names:
                if name:
                    f = self.repo_dir / f"Brewfile.{name}"
                    if f.is_file():
                        files_to_consider_set.add(f)
        
        files_to_consider = sorted(list(files_to_consider_set))
        
        # Collect ALL Brewfiles (for cross-reference in cleanup)
        all_brewfiles = {}
        for brewfile_path in sorted(self.repo_dir.glob("Brewfile*")):
            if brewfile_path.is_file():
                all_brewfiles[brewfile_path] = []
                if brewfile_path.exists():
                    with open(brewfile_path, "r") as f:
                        for line in f:
                            cleaned_line = line.strip()
                            if cleaned_line:
                                match = PACKAGE_LINE_RE.match(cleaned_line)
                                if match:
                                    kind, name = match.groups()
                                    all_brewfiles[brewfile_path].append((kind, name, cleaned_line))
        
        # Collect declared packages from files being considered
        declared_packages_by_file = defaultdict(list)
        all_declared_lines = set()
        
        for file_path in files_to_consider:
            if file_path.exists():
                with open(file_path, "r") as f:
                    for line in f:
                        cleaned_line = line.strip()
                        if cleaned_line:
                            match = PACKAGE_LINE_RE.match(cleaned_line)
                            if match:
                                kind, name = match.groups()
                                declared_packages_by_file[file_path].append((kind, name, cleaned_line))
                                all_declared_lines.add(cleaned_line)
        
        # Collect installed packages
        installed_lines = set()
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".Brewfile-dump", encoding="utf-8"
        ) as temp_dump:
            subprocess.run(
                ["brew", "bundle", "dump", "--force", "--no-vscode", "--file", temp_dump.name],
                capture_output=True, text=True,
            )
            temp_dump.seek(0)
            for line in temp_dump:
                cleaned_line = line.strip()
                if cleaned_line:
                    installed_lines.add(cleaned_line)
        
        return {
            'files_considered': files_to_consider,
            'declared_packages_by_file': declared_packages_by_file,
            'all_declared_lines': all_declared_lines,
            'installed_lines': installed_lines,
            'on_system_only': installed_lines - all_declared_lines,
            'missing_from_system': all_declared_lines - installed_lines,
            'all_brewfiles': all_brewfiles,
        }
    
    def _print_packages_grouped(self, grouped_packages, title=None, show_cross_references=False, status_data=None):
        """Prints grouped packages in a consistent vertical format.
        
        Args:
            grouped_packages: Dict mapping kind -> list of (name, extra_info_dict)
            title: Optional title to print before the packages
            show_cross_references: Whether to show asterisks for packages in other Brewfiles
            status_data: Status data for cross-reference checking (required if show_cross_references=True)
        """
        if title:
            print(f"{YELLOW}{title}:{RESET}")
        
        has_cross_references = False
        
        for kind in ["tap", "brew", "cask", "mas", "whalebrew", "vscode"]:
            if kind in grouped_packages:
                count = len(grouped_packages[kind])
                print(f"  {kind} ({count}):")
                
                for name, extra_info in sorted(grouped_packages[kind]):
                    prefix = "    "
                    display_name = name
                    
                    # Handle cross-references (show which Brewfile declares it)
                    if show_cross_references and extra_info.get('brewfile_sources'):
                        prefix = f"    {RED}*{RESET} "
                        brewfile_names = ", ".join(sorted([f.name for f in extra_info['brewfile_sources']]))
                        display_name = f"{name} [{brewfile_names}]"
                        has_cross_references = True
                    
                    # Apply other styling
                    if extra_info.get('not_installed'):
                        display_name = f"{display_name} {YELLOW}(not on system){RESET}"
                    
                    print(f"{prefix}{display_name}")
                print()  # Blank line after each kind
        
        if show_cross_references and has_cross_references:
            print(f"{RED}* Items marked with asterisk would be removed but are declared in other Brewfiles{RESET}")
            print()
    
    def _get_brewfile_sources_for_packages(self, package_lines, status_data):
        """Returns a dict mapping package lines to the Brewfiles that declare them."""
        package_to_sources = {}
        
        for brewfile_path, packages in status_data['all_brewfiles'].items():
            if brewfile_path not in status_data['files_considered']:
                for kind, name, line in packages:
                    if line in package_lines:
                        if line not in package_to_sources:
                            package_to_sources[line] = set()
                        package_to_sources[line].add(brewfile_path)
        
        return package_to_sources
    
    def _print_cleanup_preview(self, status_data, cleanup_packages):
        """Prints a cleanup preview using the same unified format as status."""
        if not cleanup_packages:
            return
        
        # Get Brewfile sources for cross-reference
        package_sources = self._get_brewfile_sources_for_packages(cleanup_packages, status_data)
        
        # Group packages for display (identical to unified view)
        unified_cleanup = defaultdict(list)  # kind -> list of (name, extra_info_dict)
        
        for line in cleanup_packages:
            match = PACKAGE_LINE_RE.match(line)
            if match:
                kind, name = match.groups()
                sources = package_sources.get(line, set())
                
                if sources:
                    # Package is declared in other Brewfiles
                    extra_info = {
                        'brewfile_sources': sources,
                        'would_be_removed': True
                    }
                else:
                    # Package is truly only on system
                    extra_info = {
                        'brewfile_sources': set(),
                        'would_be_removed': True,
                        'system_only': True
                    }
                unified_cleanup[kind].append((name, extra_info))
        
        # Print using the same format as status
        print(f"{YELLOW}Packages that would be removed:{RESET}")
        
        for kind in ["tap", "brew", "cask", "mas", "whalebrew", "vscode"]:
            if kind in unified_cleanup:
                count = len(unified_cleanup[kind])
                print(f"  {kind} ({count}):")
                
                for name, extra_info in sorted(unified_cleanup[kind]):
                    prefix = f"    {RED}*{RESET} "  # All cleanup items get asterisks
                    
                    # Determine source label
                    if extra_info.get('system_only'):
                        source_label = "On system only"
                    elif extra_info.get('brewfile_sources'):
                        brewfile_names = ", ".join(sorted([f.name for f in extra_info['brewfile_sources']]))
                        source_label = brewfile_names
                    else:
                        source_label = "Unknown"
                    
                    display_name = f"{name} [{source_label}]"
                    print(f"{prefix}{display_name}")
                print()  # Blank line after each kind
        
        # Note: In cleanup, all items shown would be removed, so no need for redundant legend
        # The legend is already clear from the "Packages that would be removed" title
    


    def cmd_dump(self, args):
        """Dumps installed packages to the Brewfile(s)."""
        self._ensure_brew()
        installed_set = set()
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".Brewfile-dump", encoding="utf-8"
        ) as temp_dump:
            say("Dumping currently installed packages from Homebrew...")
            subprocess.run(
                [
                    "brew",
                    "bundle",
                    "dump",
                    "--force",
                    "--no-vscode",
                    "--file",
                    temp_dump.name,
                ],
                capture_output=True,
                text=True,
            )
            temp_dump.seek(0)
            for line in temp_dump:
                cleaned_line = line.strip()
                if cleaned_line:
                    installed_set.add(cleaned_line)
        include_files = self._resolve_include_files(args)
        if not args.force:
            declared_set = set()
            with self._get_merged_brewfile_path(args) as merged_file:
                with open(merged_file, "r") as f:
                    for line in f:
                        cleaned_line = line.strip()
                        if cleaned_line:
                            declared_set.add(cleaned_line)
            new_packages = sorted(list(installed_set - declared_set))
            if not new_packages:
                say("No new packages to add. Brewfile(s) are up to date.")
                return
            primary_target = include_files[0] if include_files else self.brewfile
            say(
                f"Appending {len(new_packages)} new package(s) to {primary_target.name}..."
            )
            with open(primary_target, "a+") as f:
                if f.tell() > 0:
                    f.seek(f.tell() - 1)
                    if f.read(1) != "\n":
                        f.write("\n")
                for package in new_packages:
                    f.write(f"{package}\n")
        else:
            say("Performing force-overwrite dump...")
            package_membership = {}
            all_managed_files = [self.brewfile] + include_files
            for file_path in all_managed_files:
                if file_path.exists():
                    with open(file_path, "r") as f:
                        for line in f:
                            cleaned_line = line.strip()
                            if cleaned_line:
                                package_membership[cleaned_line] = file_path
            new_item_target = self.brewfile
            if self.extra_brewfile in all_managed_files:
                new_item_target = self.extra_brewfile
            elif include_files:
                new_item_target = include_files[0]
            new_contents = defaultdict(list)
            for package in sorted(list(installed_set)):
                target_file = package_membership.get(package, new_item_target)
                new_contents[target_file].append(package)
            for file_path in all_managed_files:
                say(
                    f"Writing {len(new_contents[file_path])} items to {file_path.name}..."
                )
                with open(file_path, "w") as f:
                    if new_contents[file_path]:
                        f.write("\n".join(new_contents[file_path]) + "\n")
                    else:
                        f.write("")
        say("Dump complete.")

    def _create_unified_package_view(self, status_data):
        """Creates a unified view of all packages organized by type, showing their sources."""
        unified_packages = defaultdict(list)  # kind -> list of (name, extra_info_dict)
        
        # Add declared packages from each Brewfile
        for file_path in status_data['files_considered']:
            for kind, name, original_line in status_data['declared_packages_by_file'][file_path]:
                is_installed = original_line in status_data['installed_lines']
                extra_info = {
                    'brewfile_sources': {file_path},
                    'not_installed': not is_installed,
                    'is_declared': True
                }
                unified_packages[kind].append((name, extra_info))
        
        # Add "on system only" packages
        package_sources = self._get_brewfile_sources_for_packages(status_data['on_system_only'], status_data)
        
        for line in status_data['on_system_only']:
            match = PACKAGE_LINE_RE.match(line)
            if match:
                kind, name = match.groups()
                sources = package_sources.get(line, set())
                
                if sources:
                    # Package is declared in other Brewfiles
                    extra_info = {
                        'brewfile_sources': sources,
                        'not_installed': False,
                        'is_declared': False,  # Not declared in current scope
                        'would_be_removed': True
                    }
                else:
                    # Package is truly only on system
                    extra_info = {
                        'brewfile_sources': set(),
                        'not_installed': False,
                        'is_declared': False,
                        'would_be_removed': True,
                        'system_only': True
                    }
                unified_packages[kind].append((name, extra_info))
        
        return unified_packages
    
    def _print_status_view(self, status_data, unified_packages):
        """Prints the unified status view (shared between status and interactive commands)."""
        print()  # Add a blank line for better separation
        
        for kind in ["tap", "brew", "cask", "mas", "whalebrew", "vscode"]:
            if kind in unified_packages:
                count = len(unified_packages[kind])
                print(f"{BLUE}{kind} ({count}):{RESET}")
                
                for name, extra_info in sorted(unified_packages[kind]):
                    prefix = "  "
                    display_name = name
                    
                    # Determine source label and prefix (only color the indicators)
                    if extra_info.get('system_only'):
                        source_label = "On system only"
                        prefix = f"  {RED}*{RESET} "
                    elif extra_info.get('brewfile_sources'):
                        # Use shorter names (remove "Brewfile." prefix)
                        short_names = []
                        for f in sorted(extra_info['brewfile_sources']):
                            if f.name == "Brewfile":
                                short_names.append("main")
                            else:
                                short_names.append(f.name.replace("Brewfile.", ""))
                        source_label = ", ".join(short_names)
                        
                        if extra_info.get('would_be_removed'):
                            prefix = f"  {RED}*{RESET} "
                        elif extra_info.get('not_installed'):
                            prefix = f"  {YELLOW}!{RESET} "
                        else:
                            prefix = "  "  # Normal packages - no indicator
                    else:
                        source_label = "Unknown"
                        prefix = "  "
                    
                    # Package name and source are always normal color
                    display_name = f"{name} [{source_label}]"
                    
                    print(f"{prefix}{display_name}")
                print()  # Blank line after each kind
        
        # Print legend for visual indicators
        has_asterisks = any(
            any(extra_info.get('would_be_removed') or extra_info.get('system_only') 
                for name, extra_info in packages)
            for packages in unified_packages.values()
        )
        has_missing = any(
            any(extra_info.get('not_installed') and not extra_info.get('would_be_removed')
                for name, extra_info in packages)
            for packages in unified_packages.values()
        )
        
        # Legend is now integrated with the issue summary in interactive mode
        # Only show legend in non-interactive contexts (none currently)
        if False:  # Placeholder for future non-interactive status commands
            pass
        
        return has_asterisks, has_missing
    
    def _run_install(self, args):
        """Runs install operation for interactive mode."""
        files_to_apply = [self.brewfile] + self._resolve_include_files(args)
        for brewfile_path in files_to_apply:
            say(f"Applying → {brewfile_path}")
            result = subprocess.run(
                ["brew", "bundle", "--file", str(brewfile_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr, file=sys.stderr)
                warn(f"Failed to apply {brewfile_path}")
            else:
                say(f"Successfully applied {brewfile_path}")
    
    def _run_cleanup(self, args, status_data):
        """Runs cleanup operation for interactive mode."""
        cleanup_packages = status_data['on_system_only']
        
        if not cleanup_packages:
            say("Nothing to clean up.")
            return
        
        file_basenames = [p.name for p in status_data['files_considered']]
        say(f"Removing packages not declared in: {', '.join(file_basenames)}")
        
        with self._get_merged_brewfile_path(args) as merged_file_path:
            result = subprocess.run(
                ["brew", "bundle", "cleanup", "--file", str(merged_file_path), "--force"],
                capture_output=False, text=True,
            )
            if result.returncode == 0:
                say("Cleanup complete.")
            else:
                warn("Cleanup finished with errors.")
    
    def cmd_interactive(self, args):
        """Interactive brewfile management - primary user interface."""
        self._ensure_brew()
        
        # Use shared analysis method
        status_data = self._analyze_package_status(args)
        
        # Create unified view
        unified_packages = self._create_unified_package_view(status_data)
        
        # Print status view and get issue counts
        has_asterisks, has_missing = self._print_status_view(status_data, unified_packages)
        
        # If no issues, just show status and exit
        if not has_asterisks and not has_missing:
            say("✓ System is fully synchronized with your Brewfile(s).")
            return
        
        # Count issues for summary
        asterisk_count = sum(
            sum(1 for name, extra_info in packages 
                if extra_info.get('would_be_removed') or extra_info.get('system_only'))
            for packages in unified_packages.values()
        )
        missing_count = sum(
            sum(1 for name, extra_info in packages 
                if extra_info.get('not_installed') and not extra_info.get('would_be_removed'))
            for packages in unified_packages.values()
        )
        
        print(f"{YELLOW}Issues found:{RESET}")
        if missing_count > 0:
            print(f"  {YELLOW}!{RESET} {missing_count} package(s) need installation (declared but not installed)")
        if asterisk_count > 0:
            print(f"  {RED}*{RESET} {asterisk_count} package(s) would be removed (not in current scope)")
        print()
        
        # Interactive menu
        print("What would you like to do?")
        print("  (1) Remove extra packages")
        print("  (2) Install missing packages")
        print("  (3) Sync both (install + remove)")
        print("  (q) Quit")
        
        try:
            choice = input("Enter your choice [q]: ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            choice = "q"
            print()
        
        if choice == "1" and asterisk_count > 0:
            say("Running cleanup...")
            self._run_cleanup(args, status_data)
        elif choice == "2" and missing_count > 0:
            say("Running install...")
            self._run_install(args)
        elif choice == "3" and (asterisk_count > 0 or missing_count > 0):
            say("Running sync (install + cleanup)...")
            if missing_count > 0:
                self._run_install(args)
            if asterisk_count > 0:
                self._run_cleanup(args, status_data)
        elif choice == "1" and asterisk_count == 0:
            warn("No extra packages to remove.")
        elif choice == "2" and missing_count == 0:
            warn("No missing packages to install.")
        elif choice == "3" and asterisk_count == 0 and missing_count == 0:
            warn("No packages need synchronization.")
        elif choice in ["q", ""]:
            say("Goodbye!")
        else:
            warn("Invalid choice.")
    

    def cmd_edit(self, args):
        """Opens the Brewfile in the default editor."""
        editor = os.environ.get("EDITOR", "vi")
        say(f"Opening {self.brewfile} in {editor}...")
        subprocess.run([editor, str(self.brewfile)])


    def cmd_add(self, args):
        """Installs a package and adds it to a Brewfile."""
        self._ensure_brew()
        package_name = args.package_name
        target_file = self.brewfile
        if args.to:
            target_file = self.repo_dir / f"Brewfile.{args.to}"
        say(f"Adding '{package_name}' to {target_file.name}...")
        all_files = [self.brewfile] + list(self.repo_dir.glob("Brewfile.*"))
        for file in all_files:
            if file.exists() and package_name in file.read_text():
                warn(f"Package '{package_name}' already found in {file.name}.")
                say("To ensure it is installed, run 'brewfile install'.")
                return
        say(f"Fetching info for '{package_name}'...")
        info_result = subprocess.run(
            ["brew", "info", "--json=v2", package_name], capture_output=True, text=True
        )
        if info_result.returncode != 0:
            die(f"Failed to get info for '{package_name}'. Does it exist?")
        info = json.loads(info_result.stdout)
        kind = "cask" if info.get("casks") else "brew"
        say(f"Installing '{package_name}'...")
        install_result = subprocess.run(["brew", "install", package_name])
        if install_result.returncode != 0:
            die(f"Failed to install '{package_name}'. Please check brew's output.")
        line_to_add = f'{kind} "{package_name}"'
        say(f"Appending '{line_to_add}' to {target_file.name}")
        with open(target_file, "a+") as f:
            if f.tell() > 0:
                f.seek(f.tell() - 1)
                if f.read(1) != "\n":
                    f.write("\n")
            f.write(f"{line_to_add}\n")
        say(f"Successfully added '{package_name}'.")

    def cmd_remove(self, args):
        """Finds a package in a Brewfile and interactively removes it."""
        self._ensure_brew()
        package_name = args.package_name
        all_managed_files = [self.brewfile] + list(self.repo_dir.glob("Brewfile.*"))
        found_file = None
        line_to_remove = None
        package_re = re.compile(
            rf"^(?:tap|brew|cask|mas|whalebrew|vscode)\s+\"{re.escape(package_name)}\""
        )
        for file in all_managed_files:
            if not file.exists():
                continue
            with open(file, "r") as f:
                for line in f:
                    if package_re.match(line.strip()):
                        found_file = file
                        line_to_remove = line.strip()
                        break
            if found_file:
                break
        if not found_file:
            die(f"Package '{package_name}' not found in any of your Brewfile(s).")
        say(f"Found '{line_to_remove}' in {found_file.name}")
        print("What would you like to do?")
        print("  (1) Uninstall (remove from file and system)")
        print("  (2) Remove from file only")
        print("  (3) Cancel")
        try:
            response = input("Enter your choice [3]: ")
        except (EOFError, KeyboardInterrupt):
            response = "3"
            print()
        choice = response.lower().strip()
        if choice == "1":
            say(f"Uninstalling '{package_name}' from system...")
            uninstall_result = subprocess.run(["brew", "uninstall", package_name])
            if uninstall_result.returncode == 0:
                say(
                    f"Uninstall successful. Removing '{line_to_remove}' from {found_file.name}..."
                )
                self._remove_line_from_file(found_file, line_to_remove)
                say(
                    f"'{package_name}' has been uninstalled and removed from your configuration."
                )
            else:
                warn(
                    f"Failed to uninstall '{package_name}'. Your Brewfile has not been changed."
                )
        elif choice == "2":
            say(f"Removing '{line_to_remove}' from {found_file.name}...")
            self._remove_line_from_file(found_file, line_to_remove)
            say(f"'{package_name}' has been removed from your configuration.")
        else:
            say("Cancelled.")


def main():
    """Main function and argument parser."""
    manager = BrewfileManager()
    parser = argparse.ArgumentParser(
        description="Interactive Brewfile manager - the modern way to manage Homebrew dependencies.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    
    # Add top-level flags for the primary interactive interface
    parser.add_argument(
        "--include",
        type=str,
        help="Include Brewfile.NAME (comma-separated for multiple).",
    )
    parser.add_argument(
        "--all", action="store_true", help="Include all Brewfile.* files."
    )
    
    # Add essential utility subcommands
    subparsers = parser.add_subparsers(
        dest="command", required=False, help="Utility commands"
    )
    
    # Add package command
    add_parser = subparsers.add_parser("add", help="Install and add a package to a Brewfile")
    add_parser.add_argument("package_name", help="The name of the package to add")
    add_parser.add_argument(
        "--to",
        type=str,
        help="Short name of the Brewfile to add to (e.g., 'extra')",
    )
    
    # Remove package command
    remove_parser = subparsers.add_parser("remove", help="Remove a package from a Brewfile interactively")
    remove_parser.add_argument("package_name", help="The name of the package to remove")
    
    # Edit command
    subparsers.add_parser("edit", help="Open Brewfile in $EDITOR")
    
    # Dump command
    dump_parser = subparsers.add_parser("dump", help="Update Brewfile from current system")
    dump_parser.add_argument(
        "--include",
        type=str,
        help="Include Brewfile.NAME (comma-separated for multiple)",
    )
    dump_parser.add_argument(
        "--all", action="store_true", help="Include all Brewfile.* files"
    )
    dump_parser.add_argument(
        "--force", action="store_true", help="Force overwrite of Brewfile(s)"
    )

    args = parser.parse_args()
    
    # If no subcommand specified, run interactive mode (primary interface)
    if args.command is None:
        manager.cmd_interactive(args)
    else:
        # Run the specified utility command
        command_func = getattr(manager, f"cmd_{args.command}", None)
        if command_func:
            command_func(args)
        else:
            die(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
