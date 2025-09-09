"""
ui_service.py - UI components and menu system for bootstrap orchestrator.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Optional

from utils import AnsiColor, colorize, say, warn


@dataclass
class MenuOption:
    """Represents a menu option with label and action"""

    label: str
    action: Callable[[], bool]
    condition: Callable[[], bool] = field(default=lambda: True)

    def is_available(self) -> bool:
        """Check if this option should be shown"""
        return self.condition()


class Menu:
    """Interactive menu builder"""

    def __init__(self, title: str):
        self.title = title
        self.options: list[MenuOption] = []

    def add_option(
        self, label: str, action: Callable[[], bool], condition: Callable[[], bool] = lambda: True
    ) -> "Menu":
        """Add an option to the menu"""
        self.options.append(MenuOption(label, action, condition))
        return self

    def add_conditional_option(self, label: str, action: Callable[[], bool], condition: Callable[[], bool]) -> "Menu":
        """Add a conditional option to the menu"""
        self.options.append(MenuOption(label, action, condition))
        return self

    def display_and_handle(self) -> bool:
        """Display the menu and handle user input. Returns True to continue, False to quit"""
        available_options = [opt for opt in self.options if opt.is_available()]

        print(f"\n{colorize(self.title, AnsiColor.BLUE)}")

        for i, option in enumerate(available_options, 1):
            print(f"  ({i}) {option.label}")

        print("  (q) Quit")

        try:
            choice = input("Enter your choice [q]: ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            choice = "q"
            print()

        if choice == "q" or choice == "":
            say("Goodbye!")
            return False

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(available_options):
                try:
                    result = available_options[idx].action()
                    # If action returns a boolean False, don't continue
                    return result is not False
                except Exception as e:
                    warn(f"Action failed: {e}")
                    return True
            else:
                warn("Invalid choice.")
                return True
        else:
            warn("Invalid choice.")
            return True


class StatusDisplay:
    """Handles system and component status displays"""

    @staticmethod
    def print_system_status(system_state) -> bool:
        """Print simple system status focusing on what's available."""
        print(f"\n{colorize('Development Environment Status:', AnsiColor.BLUE)}")

        # Check package manager
        if not system_state.homebrew_available:
            print("  ! Package manager missing (install Homebrew first)")
            return False
        print("  ✓ Package manager installed (Homebrew)")

        # Check foundational tools status
        needs_install = []
        if not system_state.stow_available:
            needs_install.append("stow")
        if not system_state.mas_available:
            needs_install.append("mas")
        if not system_state.brewfile_functional:
            needs_install.append("brewfile")

        if needs_install:
            print(f"  ! Foundational tools missing: {', '.join(needs_install)}")
        else:
            print("  ✓ Foundational tools installed (stow, mas, brewfile)")

        # Check mas sign-in status
        if system_state.mas_available:
            if system_state.mas_signed_in:
                print(f"  ✓ App Store management ready ({system_state.mas_account})")
            else:
                print("  ! App Store management available (sign-in needed)")

        # Check package management
        if system_state.brewfile_functional:
            print("  ✓ Package management ready (brewfile via Homebrew)")
        else:
            print("  ! Package management needs attention")
            import shutil

            if not shutil.which("brewfile"):
                print("    → brewfile command not found (run foundational tools setup)")
            else:
                print("    → brewfile command found but not functional")

        return True

    @staticmethod
    def get_install_guidance() -> str:
        """Get guidance message for Homebrew installation"""
        return "Please install Homebrew first: https://brew.sh"


class UserInput:
    """Handles user input with appropriate error handling"""

    @staticmethod
    def get_confirmation(prompt: str, default: bool = False) -> bool:
        """Get yes/no confirmation from user"""
        default_char = "Y/n" if default else "y/N"
        try:
            response = input(f"{prompt} ({default_char}): ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            response = ""
            print()

        if response == "":
            return default
        return response in ["y", "yes"]

    @staticmethod
    def get_choice(prompt: str, default: str = "") -> str:
        """Get a choice from user with default"""
        try:
            choice = input(f"{prompt} [{default}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = ""
            print()

        return choice if choice else default

    @staticmethod
    def handle_interrupt() -> str:
        """Handle keyboard interrupts gracefully"""
        print()
        say("Operation cancelled by user.")
        return "q"


class ActionBuilder:
    """Builds actions for menu options with proper closures"""

    @staticmethod
    def create_dotfiles_action(dotfiles_service, action_name: str):
        """Create a dotfiles service action"""
        if action_name == "resolve_backup":

            def action():
                return dotfiles_service.resolve_conflicts_backup()

            return action

        elif action_name == "resolve_adopt":

            def action():
                return dotfiles_service.resolve_conflicts_adopt()

            return action

        elif action_name == "restow":

            def action():
                return dotfiles_service.restow()

            return action

        else:
            raise ValueError(f"Unknown dotfiles action: {action_name}")

    @staticmethod
    def create_package_action(system_service):
        """Create a package management action using SystemService"""

        def action():
            return system_service.start_package_tool()

        return action

    @staticmethod
    def create_composite_action(actions: list[Callable[[], bool]], description: Optional[str] = None):
        """Create an action that runs multiple actions in sequence"""

        def composite_action():
            if description:
                say(description)

            for action in actions:
                if not action():
                    return False
            return True

        return composite_action
