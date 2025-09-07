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

if [ -f ~/.fzf.zsh ]; then
  source ~/.fzf.zsh

  # Consolidate standard fzf options
  export FZF_DEFAULT_OPTS="--cycle --height=-15 --min-height=40 --layout=reverse --info=default --border=rounded"

  # Use fd for faster, .gitignore-aware file search
  export FZF_DEFAULT_COMMAND="fd --type f --hidden --exclude .git"
  export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"

  # Aliases
  alias fzf='fzf'
  alias fzfp='fzf --preview "bat --style=numbers --color=always {}"'

  # Faster directory navigation with fd
  fcd() {
    local dir
    dir=$(fd --type d --hidden --exclude .git | fzfp +m) && cd "$dir"
  }
fi

# Load uv completion if available
command -v uv &>/dev/null && eval "$(uv generate-shell-completion zsh)"

# Load zoxide if available
command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init --cmd cd zsh)"

# Initialize Starship prompt
command -v starship >/dev/null 2>&1 && eval "$(starship init zsh)"
