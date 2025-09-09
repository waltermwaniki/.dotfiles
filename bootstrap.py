#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bootstrap.py — Interactive development environment setup orchestrator.

Provides a unified interface for managing packages (via brewfile) and dotfiles,
with system status overview and guided delegation to specialized tools.
"""

from pathlib import Path
from typing import Optional

from services.dotfiles import DotfilesService, DotfilesState
from services.system import SystemService, SystemState
from services.ui import ActionBuilder, Menu, StatusDisplay
from utils import error, say


class BootstrapOrchestrator:
    """Unified development environment orchestrator with service-based architecture"""

    def __init__(self):
        self.repo_dir = self._resolve_repo_dir()

        # Initialize services
        self.system_service = SystemService()
        self.dotfiles_service = DotfilesService(self.repo_dir)

    def _resolve_repo_dir(self) -> Path:
        """Resolves the git repository root from the script's location."""
        try:
            return Path(__file__).resolve().parent
        except NameError:
            return Path.cwd()
    
    def _print_package_status(self):
        """Print package status using brewfile"""
        import subprocess
        try:
            result = subprocess.run(["brewfile", "status"], text=True, timeout=30)
            # brewfile status already includes its own output formatting
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            # If brewfile fails, just skip the package status
            pass

    def cmd_interactive(self):
        """Main interactive bootstrap orchestrator with unified dotfiles management."""
        # Get system state (cached after first call)
        system_state = self.system_service.state

        # Print system status
        homebrew_ok = StatusDisplay.print_system_status(system_state)
        if not homebrew_ok:
            say(StatusDisplay.get_install_guidance())
            return

        # Analyze dotfiles if stow is available
        dotfiles_state = None
        if system_state.stow_available:
            dotfiles_state = self.dotfiles_service.state
            if dotfiles_state:
                self.dotfiles_service.print_status_summary(dotfiles_state)
        
        # Show package status if brewfile is functional
        if system_state.brewfile_functional:
            self._print_package_status()

        # Build and display main menu
        self._build_and_show_menu(system_state, dotfiles_state)

    def _build_and_show_menu(self, system_state: SystemState, dotfiles_state: Optional[DotfilesState]):
        """Build and display the main interactive menu"""
        menu = Menu("Actions:")

        # Dotfiles management (only if stow is available)
        if dotfiles_state and system_state.stow_available:
            self._add_dotfiles_menu_options(menu, dotfiles_state)

        # Package management (if brewfile is functional)
        if system_state.brewfile_functional:
            menu.add_option("Manage packages", ActionBuilder.create_package_action(self.system_service))

        # Display menu and handle interactions
        menu.display_and_handle()

    def _add_dotfiles_menu_options(self, menu: Menu, dotfiles_state: DotfilesState):
        """Add dotfiles-related options to the menu based on current state"""

        # Context-specific actions based on issues found
        if dotfiles_state.has_conflicts:
            menu.add_option(
                "Resolve conflicts (backup & replace)",
                ActionBuilder.create_dotfiles_action(self.dotfiles_service, "resolve_backup"),
            )
            menu.add_option(
                "Resolve conflicts (adopt existing)",
                ActionBuilder.create_dotfiles_action(self.dotfiles_service, "resolve_adopt"),
            )

        # Re-stow action (always available when dotfiles are functional)
        if dotfiles_state.has_broken_symlinks and not dotfiles_state.has_conflicts:
            restow_label = "Re-stow dotfiles (fixes broken links)"
        elif not dotfiles_state.has_issues:
            restow_label = "Re-stow dotfiles (refresh all symlinks)"
        else:
            restow_label = "Re-stow dotfiles (fixes broken links)"

        menu.add_option(restow_label, ActionBuilder.create_dotfiles_action(self.dotfiles_service, "restow"))

    def cmd_status(self):
        """Show current system and dotfiles status without interactive menu"""
        system_state = self.system_service.state
        StatusDisplay.print_system_status(system_state)

        if system_state.stow_available:
            dotfiles_state = self.dotfiles_service.state
            if dotfiles_state:
                self.dotfiles_service.print_status_summary(dotfiles_state)
        
        # Show package status if brewfile is functional
        if system_state.brewfile_functional:
            self._print_package_status()

    def cmd_setup_tools(self):
        """Attempt to set up foundational tools"""
        say("Attempting to set up development environment...")
        self.system_service._fetch_system_state()
        return self.cmd_status()

    def cmd_setup_packages(self):
        """Attempt to set up package management"""
        say("Attempting to set up package management...")
        self.system_service._fetch_system_state()
        return self.cmd_status()

    def cmd_setup_dotfiles(self):
        """Apply dotfiles non-interactively"""
        system_state = self.system_service.state

        if not system_state.stow_available:
            error("GNU Stow not available. Run setup tools first.")
            return False

        dotfiles_state = self.dotfiles_service.state

        if not dotfiles_state:
            error("Failed to analyze dotfiles state")
            return False

        if dotfiles_state.has_conflicts:
            error("Conflicts detected. Use interactive mode to resolve them.")
            self.dotfiles_service.print_status_summary(dotfiles_state)
            return False

        if dotfiles_state.has_broken_symlinks:
            say("Fixing broken symlinks...")
            return self.dotfiles_service.restow()

        if not dotfiles_state.has_issues:
            say("Dotfiles already properly applied")
            return True

        return self.dotfiles_service.apply()

    def cmd_setup_all(self):
        """Complete setup: environment + dotfiles"""
        say("Starting complete environment setup...")

        # Setup system environment
        self.system_service._fetch_system_state()

        # Setup dotfiles
        self.cmd_setup_dotfiles()

        say("Setup complete! Check status above for any remaining issues.")
        return self.cmd_status()


def main():
    """Main function with command line argument handling"""
    import sys

    orchestrator = BootstrapOrchestrator()

    # Handle command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "status":
            orchestrator.cmd_status()
        elif command == "setup":
            if len(sys.argv) > 2:
                setup_target = sys.argv[2].lower()
                if setup_target == "tools":
                    orchestrator.cmd_setup_tools()
                elif setup_target == "packages":
                    orchestrator.cmd_setup_packages()
                elif setup_target == "dotfiles":
                    orchestrator.cmd_setup_dotfiles()
                else:
                    error(f"Unknown setup target: {setup_target}")
                    print("Available targets: tools, packages, dotfiles")
            else:
                orchestrator.cmd_setup_all()
        elif command == "interactive":
            orchestrator.cmd_interactive()
        else:
            error(f"Unknown command: {command}")
            print("Available commands: status, setup [tools|packages|dotfiles], interactive")
            sys.exit(1)
    else:
        # Default to interactive mode
        orchestrator.cmd_interactive()


if __name__ == "__main__":
    main()
