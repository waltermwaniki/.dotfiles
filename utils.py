import os
import sys
import threading
import time
from enum import Enum

# ANSI colors (respect NO_COLOR and non-TTY)
_BLUE = "\033[1;34m"
_YELLOW = "\033[1;33m"
_RED = "\033[1;31m"
_GREEN = "\033[1;32m"
_GRAY = "\033[0;37m"
_RESET = "\033[0m"


COLOR_SUPPORTED = sys.stdout.isatty() and "NO_COLOR" not in os.environ
if not COLOR_SUPPORTED:
    _BLUE = _YELLOW = _RED = _GREEN = _GRAY = _RESET = ""


class AnsiColor(Enum):
    BLUE = _BLUE
    YELLOW = _YELLOW
    RED = _RED
    GREEN = _GREEN
    GRAY = _GRAY
    RESET = _RESET

    def __get__(self, instance, owner):
        return self.value


def colorize(text: str, color: AnsiColor) -> str:
    """Wraps text in ANSI color codes if supported."""
    return f"{color}{text}{AnsiColor.RESET}"


def say(msg: str) -> None:
    """Prints a message with blue prefix."""
    print(f"{colorize('===>', AnsiColor.BLUE)} {msg}")


def warn(msg: str) -> None:
    """Prints a warning message."""
    print(f"{colorize('[warn]', AnsiColor.YELLOW)} {msg}")


def error(msg: str) -> None:
    """Prints an error message."""
    print(f"{colorize('[error]', AnsiColor.RED)} {msg}", file=sys.stderr)


def success(msg: str) -> None:
    """Prints a success message."""
    print(f"{colorize('[success]', AnsiColor.GREEN)} {msg}")


def die(msg: str) -> None:
    """Prints an error and exits."""
    error(msg)
    sys.exit(1)


class LoadingIndicator:
    """Simple loading spinner for long-running operations."""

    def __init__(self, message: str = "Loading"):
        self.message = message
        self.running = False
        self.thread = None
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def _spin(self):
        """Spinner animation loop."""
        i = 0
        while self.running:
            char = self.spinner_chars[i % len(self.spinner_chars)]
            print(f"\r{AnsiColor.BLUE}{char}{AnsiColor.RESET} {self.message}...", end="", flush=True)
            time.sleep(0.1)
            i += 1

    def start(self):
        """Start the loading indicator."""
        if "NO_COLOR" in os.environ or not sys.stdout.isatty():
            # No spinner in non-interactive mode or when NO_COLOR is set
            print(f"{self.message}...")
            return

        self.running = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        """Stop the loading indicator."""
        if "NO_COLOR" in os.environ or not sys.stdout.isatty():
            return

        self.running = False
        if self.thread:
            self.thread.join()
        print("\r" + " " * (len(self.message) + 10) + "\r", end="", flush=True)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
