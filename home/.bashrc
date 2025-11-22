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

# fzf - fuzzy finder integration
if command -v fzf >/dev/null 2>&1; then
  # Source fzf shell integration if available
  if [ -f ~/.fzf.bash ]; then
    source ~/.fzf.bash
  elif command -v brew >/dev/null 2>&1; then
    # Try to source from brew installation
    brew_prefix="$(brew --prefix)"
    [ -f "$brew_prefix/opt/fzf/shell/key-bindings.bash" ] && source "$brew_prefix/opt/fzf/shell/key-bindings.bash"
    [ -f "$brew_prefix/opt/fzf/shell/completion.bash" ] && source "$brew_prefix/opt/fzf/shell/completion.bash"
  fi

  # fzf configuration (same as zsh)
  export FZF_DEFAULT_OPTS="--cycle --height=-15 --min-height=40 --layout=reverse --info=default --border=rounded"

  # Use fd for faster, .gitignore-aware file search
  if command -v fd >/dev/null 2>&1; then
    export FZF_DEFAULT_COMMAND="fd --type f --hidden --exclude .git"
    export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
  fi
fi

[ -f "$HOME/.local/bin/env" ] && . "$HOME/.local/bin/env"

# pnpm
export PNPM_HOME="/home/localadmin/.local/share/pnpm"
case ":$PATH:" in
  *":$PNPM_HOME:"*) ;;
  *) export PATH="$PNPM_HOME:$PATH" ;;
esac
# pnpm end

# Load completion systems for dev tools
command -v gh >/dev/null 2>&1 && eval "$(gh completion --shell bash)"
command -v pnpm >/dev/null 2>&1 && source <(pnpm completion bash)

# Initialize Starship prompt
command -v starship >/dev/null 2>&1 && eval "$(starship init bash)"


# Load zoxide if available (bash version) – keep last for PROMPT_COMMAND safety
command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init --cmd cd bash)"