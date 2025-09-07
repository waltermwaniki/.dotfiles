#!/usr/bin/env bash

# Source common shell configuration (exports, aliases, functions)
if [ -f ~/.commonshrc ]; then
  source ~/.commonshrc
fi

# Bash-specific configurations

# Bash completions (if available)
if [ -f /etc/bash_completion ]; then
  source /etc/bash_completion
elif command -v brew >/dev/null 2>&1 && [ -f "$(brew --prefix)/etc/bash_completion" ]; then
  source "$(brew --prefix)/etc/bash_completion"
fi

# Bash-specific fzf integration
[ -f ~/.fzf.bash ] && source ~/.fzf.bash

# Load zoxide if available (bash version)
command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init --cmd cd bash)"

# Initialize Starship prompt
command -v starship >/dev/null 2>&1 && eval "$(starship init bash)"
