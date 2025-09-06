#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brewfile.py — A Python-based manager for Brewfile dependencies.
"""
import os
import sys
import subprocess
import argparse
from pathlib import Path
import shutil
import tempfile
from contextlib import contextmanager
import re
from collections import defaultdict

# ANSI colors (respect NO_COLOR and non-TTY)
BLUE = "\033[1;34m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
RESET = "\033[0m"

if "NO_COLOR" in os.environ or not sys.stdout.isatty():
    BLUE = YELLOW = RED = RESET = ""

def say(msg):
    """Prints a message to the console with a blue '==>' prefix."""
    print(f"{BLUE}==>{RESET} {msg}")

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

    def _resolve_repo_dir(self):
        """Resolves the git repository root from the script's location."""
        try:
            # Assuming script is in home/.local/bin
            script_path = Path(__file__).resolve()
            return script_path.parent.parent.parent.parent
        except NameError:
            # Fallback for interactive mode
            return Path.cwd()

    def cmd_path(self, args):
        """Prints the path to the Brewfile(s)."""
        print(self.brewfile)
        # In the future, this will handle include files.

    def _group_print(self, label, lines):
        """Parses and prints a grouped summary of package lines."""
        say(label)
        if not lines:
            print("  (none)")
            return

        grouped = defaultdict(list)
        # Regex to capture `kind "name"`
        line_re = re.compile(r"^(tap|brew|cask|mas|whalebrew|vscode)\s+\"([^\"]+)\"")

        for line in lines:
            match = line_re.match(line)
            if match:
                kind, name = match.groups()
                grouped[kind].append(name)
            else:
                # Fallback for lines that don't match
                grouped["unknown"].append(line)

        for kind in ["tap", "brew", "cask", "mas", "whalebrew", "vscode", "unknown"]:
            if kind in grouped:
                names = ", ".join(sorted(grouped[kind]))
                count = len(grouped[kind])
                print(f"  {kind} ({count}): {names}")

    def cmd_edit(self, args):
        """Opens the Brewfile in the default editor."""
        editor = os.environ.get("EDITOR", "vi")
        say(f"Opening {self.brewfile} in {editor}...")
        subprocess.run([editor, str(self.brewfile)])

    # Other commands will be added here
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
            names = args.include.split(',')
            for name in names:
                if name:  # Avoid empty strings
                    f = self.repo_dir / f"Brewfile.{name}"
                    if f.is_file():
                        include_files.append(f)
        return include_files

    def cmd_install(self, args):
        """Applies the main Brewfile and any included files."""
        self._ensure_brew()

        files_to_apply = [self.brewfile]
        files_to_apply.extend(self._resolve_include_files(args))

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

    def cmd_sync(self, args):
        """Runs 'install' then 'cleanup' to fully synchronize the system."""
        say("--- Running 'install' step ---")
        self.cmd_install(args)
        say("--- Running 'cleanup' step ---")
        self.cmd_cleanup(args)
        say("--- Sync complete ---")

    def cmd_check(self, args):
        """Checks for differences between the system and the Brewfile(s)."""
        self._ensure_brew()

        # 1. Quick check on main Brewfile
        say(f"Performing quick check on main Brewfile: {self.brewfile.name}")
        quick_check_result = subprocess.run(
            ["brew", "bundle", "check", "--file", str(self.brewfile)],
            capture_output=True, text=True
        )
        if quick_check_result.returncode == 0:
            say("Main Brewfile is up to date.")
        else:
            # brew's output is user-friendly enough here
            print(quick_check_result.stdout.strip())
            warn("Main Brewfile has missing dependencies. Run 'brewfile install'.")

        say("Performing full two-way diff...")

        # 2. Get declared packages
        declared_set = set()
        with self._get_merged_brewfile_path(args) as merged_file:
            with open(merged_file, 'r') as f:
                for line in f:
                    cleaned_line = line.strip()
                    if cleaned_line:
                        declared_set.add(cleaned_line)

        # 3. Get installed packages
        installed_set = set()
        with tempfile.NamedTemporaryFile(mode='w+', suffix=".Brewfile-dump") as temp_dump:
            subprocess.run(
                ["brew", "bundle", "dump", "--force", "--no-vscode", "--file", temp_dump.name],
                capture_output=True, text=True
            )
            temp_dump.seek(0)
            for line in temp_dump:
                cleaned_line = line.strip()
                if cleaned_line:
                    installed_set.add(cleaned_line)

        # 4. Calculate differences
        to_install = sorted(list(declared_set - installed_set))
        to_add_to_brewfile = sorted(list(installed_set - declared_set))

        # 5. Format and print
        print() # for spacing
        if not to_install and not to_add_to_brewfile:
            say("System state matches Brewfile(s). No changes needed.")
            return

        self._group_print("To INSTALL (missing from system)", to_install)
        print()
        self._group_print("To ADD (to Brewfile)", to_add_to_brewfile)

    def cmd_dump(self, args):
        """Dumps installed packages to the Brewfile(s)."""
        self._ensure_brew()

        # Get all currently installed packages
        installed_set = set()
        with tempfile.NamedTemporaryFile(mode='w+', suffix=".Brewfile-dump") as temp_dump:
            say("Dumping currently installed packages from Homebrew...")
            subprocess.run(
                ["brew", "bundle", "dump", "--force", "--no-vscode", "--file", temp_dump.name],
                capture_output=True, text=True
            )
            temp_dump.seek(0)
            for line in temp_dump:
                cleaned_line = line.strip()
                if cleaned_line:
                    installed_set.add(cleaned_line)

        include_files = self._resolve_include_files(args)

        if not args.force:
            # --- APPEND MODE --- 
            declared_set = set()
            with self._get_merged_brewfile_path(args) as merged_file:
                with open(merged_file, 'r') as f:
                    for line in f:
                        cleaned_line = line.strip()
                        if cleaned_line:
                            declared_set.add(cleaned_line)
            
            new_packages = sorted(list(installed_set - declared_set))

            if not new_packages:
                say("No new packages to add. Brewfile(s) are up to date.")
                return

            primary_target = include_files[0] if include_files else self.brewfile
            say(f"Appending {len(new_packages)} new package(s) to {primary_target.name}...")
            with open(primary_target, 'a') as f:
                f.write('\n')
                for package in new_packages:
                    f.write(f"{package}\n")
        else:
            # --- FORCE OVERWRITE MODE ---
            say("Performing force-overwrite dump...")
            package_membership = {}
            all_managed_files = [self.brewfile] + include_files

            for file_path in all_managed_files:
                if file_path.exists():
                    with open(file_path, 'r') as f:
                        for line in f:
                            cleaned_line = line.strip()
                            if cleaned_line:
                                package_membership[cleaned_line] = file_path

            # Determine where new, un-tracked packages should go
            new_item_target = self.brewfile
            if self.extra_brewfile in all_managed_files:
                new_item_target = self.extra_brewfile
            elif include_files:
                new_item_target = include_files[0]

            # Distribute all installed packages back into files
            new_contents = defaultdict(list)
            for package in sorted(list(installed_set)):
                target_file = package_membership.get(package, new_item_target)
                new_contents[target_file].append(package)

            # Write the new contents to all managed files
            for file_path in all_managed_files:
                say(f"Writing {len(new_contents[file_path])} items to {file_path.name}...")
                with open(file_path, 'w') as f:
                    if new_contents[file_path]:
                        f.write('\n'.join(new_contents[file_path]) + '\n')
                    else:
                        # If a file has no packages, it should be empty
                        f.write('')
        say("Dump complete.")

    def cmd_list(self, args):
        """Lists all dependencies from the main Brewfile and any included files."""
        self._ensure_brew()

        files_to_list = [self.brewfile]
        files_to_list.extend(self._resolve_include_files(args))

        all_deps = set()

        file_basenames = [p.name for p in files_to_list]
        say(f"Listing dependencies from {', '.join(file_basenames)}")

        for brewfile_path in files_to_list:
            result = subprocess.run(
                ["brew", "bundle", "list", "--file", str(brewfile_path)],
                capture_output=True,
                text=True,
            )
            # brew bundle list exits 1 if file is empty or doesn't exist, which is not an error for us
            for line in result.stdout.strip().split('\n'):
                if line:
                    all_deps.add(line)
            if result.stderr:
                warn(f"Error listing dependencies from {brewfile_path}:\n{result.stderr}")

        for dep in sorted(list(all_deps)):
            print(dep)

    @contextmanager
    def _get_merged_brewfile_path(self, args):
        """
        A context manager that provides the path to a temporary, merged Brewfile.
        Deletes the file on exit.
        """
        files_to_merge = [self.brewfile]
        files_to_merge.extend(self._resolve_include_files(args))

        all_lines = set()
        for file_path in files_to_merge:
            if file_path.exists():
                with open(file_path, 'r') as f:
                    for line in f:
                        if line.strip():
                            all_lines.add(line)

        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".Brewfile", encoding='utf-8') as tf:
                temp_file_path = Path(tf.name)
                tf.writelines(sorted(list(all_lines)))

            yield temp_file_path

        finally:
            if temp_file_path and temp_file_path.exists():
                temp_file_path.unlink()

    def cmd_cleanup(self, args):
        """Cleans up unlisted dependencies after a preview and confirmation."""
        self._ensure_brew()

        with self._get_merged_brewfile_path(args) as merged_file_path:
            file_basenames = [p.name for p in [self.brewfile] + self._resolve_include_files(args)]
            say(f"Checking for unused packages against: {', '.join(file_basenames)}")

            # Always run in preview mode first
            preview_result = subprocess.run(
                ["brew", "bundle", "cleanup", "--file", str(merged_file_path)],
                capture_output=True,
                text=True,
            )

            # brew bundle cleanup exits 1 if there are things to do.
            # We check stdout to be sure it's not a real error.
            if preview_result.returncode == 0 or "Would remove" not in preview_result.stdout:
                say("Nothing to clean up.")
                return

            # Show the preview
            print(preview_result.stdout.strip())
            warn("The above packages are not in your Brewfile(s) and would be removed.")

            # Prompt for confirmation
            try:
                response = input("Would you like to proceed with cleanup? (y/N): ")
            except (EOFError, KeyboardInterrupt):
                # Handle case where script is run non-interactively or user hits Ctrl+C
                response = 'n'
                print() # Add a newline for cleaner exit

            if response.lower().strip() == 'y':
                say("Proceeding with cleanup...")
                # Run with --force to actually remove packages
                force_result = subprocess.run(
                    ["brew", "bundle", "cleanup", "--file", str(merged_file_path), "--force"],
                    capture_output=False, # Stream output directly to user
                    text=True,
                )
                if force_result.returncode == 0:
                    say("Cleanup complete.")
                else:
                    warn("Cleanup command finished with errors.")
            else:
                say("Cleanup aborted.")


def main():
    """Main function and argument parser."""
    manager = BrewfileManager()

    parser = argparse.ArgumentParser(
        description="A Python-based manager for Brewfile dependencies.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    # Define commands
    commands = {
        "install": "Install all dependencies from the Brewfile(s).",
        "cleanup": "Preview or apply removals of unlisted packages.",
        "check": "Show missing items and a grouped summary of differences.",
        "sync": "Run 'install' then 'cleanup' to fully synchronize the system.",
        "dump": "Update Brewfile from current system.",
        "list": "Show all dependencies currently recorded.",
        "edit": "Open Brewfile in $EDITOR.",
        "path": "Print path(s) to Brewfile(s).",
    }

    for cmd, help_text in commands.items():
        subparser = subparsers.add_parser(cmd, help=help_text)
        # Shared arguments can be added here
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
        if cmd == "cleanup":
            subparser.add_argument(
                "--apply", action="store_true", help="Actually uninstall extras."
            )

    args = parser.parse_args()

    # Dispatch to the appropriate command method
    command_func = getattr(manager, f"cmd_{args.command}", None)
    if command_func:
        command_func(args)
    else:
        die(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
