# usr/bin/env zsh
alias src~='source ~/.zshrc'

# Source common shell configuration (exports, aliases, functions)
if [ -f ~/.commonshrc ]; then
  source ~/.commonshrc
fi

# Source prompt configuration if exists
if [ -f ~/.prompt ]; then
  source ~/.prompt
fi


# Set up completions
autoload -Uz compinit
compinit
# Load zsh plugins if available
if command -v brew &>/dev/null; then
  local brew_prefix="$(brew --prefix)"
  [[ -f "$brew_prefix/share/zsh-autosuggestions/zsh-autosuggestions.zsh" ]] && source "$brew_prefix/share/zsh-autosuggestions/zsh-autosuggestions.zsh"
  [[ -f "$brew_prefix/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" ]] && source "$brew_prefix/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
fi


# -------- Initialize utility tools -------

# fzf - fuzzy finder integration
if command -v fzf >/dev/null 2>&1; then
  # Source fzf shell integration if available
  if [ -f ~/.fzf.zsh ]; then
    source ~/.fzf.zsh
  elif command -v brew >/dev/null 2>&1; then
    # Try to source from brew installation
    local brew_prefix="$(brew --prefix)"
    [ -f "$brew_prefix/opt/fzf/shell/key-bindings.zsh" ] && source "$brew_prefix/opt/fzf/shell/key-bindings.zsh"
    [ -f "$brew_prefix/opt/fzf/shell/completion.zsh" ] && source "$brew_prefix/opt/fzf/shell/completion.zsh"
  fi

  # fzf configuration
  export FZF_DEFAULT_OPTS="--cycle --height=-15 --min-height=40 --layout=reverse --info=default --border=rounded"

  # Use fd for faster, .gitignore-aware file search
  if command -v fd >/dev/null 2>&1; then
    export FZF_DEFAULT_COMMAND="fd --type f --hidden --exclude .git"
    export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
  fi

  # Aliases
  alias fzf='fzf'
  alias fzfp='fzf --preview "bat --style=numbers --color=always {}"'

  # Faster directory navigation with fd
  fcd() {
    local dir
    if command -v fd >/dev/null 2>&1; then
      dir=$(fd --type d --hidden --exclude .git | fzfp +m) && cd "$dir"
    else
      dir=$(find . -type d | fzf +m) && cd "$dir"
    fi
  }
fi

# Load completion systems for dev tools
command -v uv >/dev/null 2>&1 && eval "$(uv generate-shell-completion zsh)"
command -v gh >/dev/null 2>&1 && eval "$(gh completion --shell zsh)"
command -v pnpm >/dev/null 2>&1 && source <(pnpm completion zsh)

# Load zoxide if available
command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init --cmd cd zsh)"

# Initialize Starship prompt
command -v starship >/dev/null 2>&1 && eval "$(starship init zsh)"

# Added by Antigravity
export PATH="/Users/walter.mwaniki/.antigravity/antigravity/bin:$PATH"
