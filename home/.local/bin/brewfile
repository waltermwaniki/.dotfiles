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
            return script_path.parent.parent.parent.parent
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

    def cmd_install(self, args):
        """Applies the main Brewfile and any included files."""
        self._ensure_brew()
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

    def cmd_cleanup(self, args):
        """Cleans up unlisted dependencies after a preview and confirmation."""
        self._ensure_brew()
        with self._get_merged_brewfile_path(args) as merged_file_path:
            file_basenames = [
                p.name for p in [self.brewfile] + self._resolve_include_files(args)
            ]
            say(f"Checking for unused packages against: {', '.join(file_basenames)}")
            preview_result = subprocess.run(
                ["brew", "bundle", "cleanup", "--file", str(merged_file_path)],
                capture_output=True,
                text=True,
            )
            if (
                preview_result.returncode == 0
                or "Would remove" not in preview_result.stdout
            ):
                say("Nothing to clean up.")
                return
            print(preview_result.stdout.strip())
            warn("The above packages are not in your Brewfile(s) and would be removed.")
            try:
                response = input("Would you like to proceed with cleanup? (y/N): ")
            except (EOFError, KeyboardInterrupt):
                response = "n"
                print()
            if response.lower().strip() == "y":
                say("Proceeding with cleanup...")
                force_result = subprocess.run(
                    [
                        "brew",
                        "bundle",
                        "cleanup",
                        "--file",
                        str(merged_file_path),
                        "--force",
                    ],
                    capture_output=False,
                    text=True,
                )
                if force_result.returncode == 0:
                    say("Cleanup complete.")
                else:
                    warn("Cleanup command finished with errors.")
            else:
                say("Cleanup aborted.")

    def cmd_sync(self, args):
        """Runs 'install' then 'cleanup' to fully synchronize the system."""
        say("-- Running 'install' step --")
        self.cmd_install(args)
        say("-- Running 'cleanup' step --")
        self.cmd_cleanup(args)
        say("-- Sync complete --")

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

    def cmd_list(self, args):
        """Lists all dependencies from the main Brewfile and any included files,
        showing their installation status and grouping them."""
        self._ensure_brew()

        # Ensure all relevant Brewfiles are considered by default
        files_to_consider_set = set()
        files_to_consider_set.add(self.brewfile)  # Always include the main Brewfile

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

        files_to_consider = sorted(
            list(files_to_consider_set)
        )  # Convert back to sorted list

        # 1. Collect Declared Packages
        declared_packages_by_file = defaultdict(
            list
        )  # file_path -> list of (kind, name, original_line)
        declared_package_lines_set = set()  # set of all unique original_line strings

        for file_path in files_to_consider:
            if file_path.exists():
                with open(file_path, "r") as f:
                    for line in f:
                        cleaned_line = line.strip()
                        if cleaned_line:
                            match = PACKAGE_LINE_RE.match(cleaned_line)
                            if match:
                                kind, name = match.groups()
                                declared_packages_by_file[file_path].append(
                                    (kind, name, cleaned_line)
                                )
                                declared_package_lines_set.add(cleaned_line)
                            # else: # No need to handle unknown lines for now

        # 2. Collect Installed Packages
        installed_package_lines_set = set()
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".Brewfile-dump", encoding="utf-8"
        ) as temp_dump:
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
                    installed_package_lines_set.add(cleaned_line)

        # 3. Print Brewfile Sections
        print()  # Add a blank line for better separation

        for file_path in files_to_consider:
            if not declared_packages_by_file[file_path]:
                continue  # Skip if no packages declared in this file

            print(f"{BLUE}Brewfile: {file_path.name}{RESET}")
            grouped_for_print = defaultdict(
                list
            )  # kind -> list of (name, is_installed)

            for kind, name, original_line in declared_packages_by_file[file_path]:
                is_installed = original_line in installed_package_lines_set
                grouped_for_print[kind].append((name, is_installed))

            for kind in [
                "tap",
                "brew",
                "cask",
                "mas",
                "whalebrew",
                "vscode",
            ]:  # Order matters
                if kind in grouped_for_print:
                    items_to_display = []
                    for name, is_installed in sorted(
                        grouped_for_print[kind], key=lambda x: x[0]
                    ):
                        display_name = name
                        if not is_installed:
                            display_name = f"{name} {YELLOW}(not on system){RESET}"
                        items_to_display.append(display_name)
                    print(
                        f"  {kind} ({len(items_to_display)}): {', '.join(items_to_display)}"
                    )
            print()  # Blank line after each Brewfile section

        # 4. Print "On system only" Section
        on_system_only_lines = installed_package_lines_set - declared_package_lines_set
        print(f"{BLUE}On system only:{RESET}")
        if on_system_only_lines:
            on_system_only_grouped = defaultdict(list)  # kind -> list of name

            for line in on_system_only_lines:
                match = PACKAGE_LINE_RE.match(line)
                if match:
                    kind, name = match.groups()
                    on_system_only_grouped[kind].append(name)
                else:
                    on_system_only_grouped["unknown"].append(
                        line
                    )  # For lines that don't match regex

            for kind in [
                "tap",
                "brew",
                "cask",
                "mas",
                "whalebrew",
                "vscode",
                "unknown",
            ]:
                if kind in on_system_only_grouped:
                    names = ", ".join(sorted(on_system_only_grouped[kind]))
                    count = len(on_system_only_grouped[kind])
                    print(f"  {kind} ({count}): {names}")
            print()  # Blank line at the end
        else:
            print("  ✓ System is up to date with Brewfile(s).")

    def cmd_edit(self, args):
        """Opens the Brewfile in the default editor."""
        editor = os.environ.get("EDITOR", "vi")
        say(f"Opening {self.brewfile} in {editor}...")
        subprocess.run([editor, str(self.brewfile)])

    def cmd_path(self, args):
        """Prints the path to the Brewfile(s)."""
        print(self.brewfile)

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
        description="A Python-based manager for Brewfile dependencies.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Available commands"
    )
    commands = {
        "install": "Install all dependencies from the Brewfile(s) (formerly 'sync').",
        "cleanup": "Preview or apply removals of unlisted packages.",
        "list": "List all dependencies from Brewfile(s) and compare with system state.",
        "sync": "Run 'install' then 'cleanup' to fully synchronize the system.",
        "dump": "Update Brewfile from current system.",
        "edit": "Open Brewfile in $EDITOR.",
        "path": "Print path(s) to Brewfile(s).",
        "add": "Install a package and add it to a Brewfile.",
        "remove": "Remove a package from a Brewfile interactively.",
    }
    for cmd, help_text in commands.items():
        subparser = subparsers.add_parser(cmd, help=help_text)
        subparser.add_argument(
            "--include",
            type=str,
            help="Include Brewfile.NAME (comma-separated for multiple).",
        )
        subparser.add_argument(
            "--all", action="store_true", help="Include all Brewfile.* files."
        )
        if cmd == "dump":
            subparser.add_argument(
                "--force", action="store_true", help="Force overwrite of Brewfile(s)."
            )
        if cmd == "add":
            subparser.add_argument(
                "package_name", help="The name of the package to add."
            )
            subparser.add_argument(
                "--to",
                type=str,
                help="Short name of the Brewfile to add to (e.g., 'extra').",
            )
        if cmd == "remove":
            subparser.add_argument(
                "package_name", help="The name of the package to remove."
            )

    args = parser.parse_args()
    command_func = getattr(manager, f"cmd_{args.command}", None)
    if command_func:
        command_func(args)
    else:
        die(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
