# usr/bin/env zsh
alias src~='source ~/.zshrc'


if [ -f ~/.prompt ]; then
  source ~/.prompt
fi

if [ -f ~/.aliases ]; then
  source ~/.aliases
fi

if [ -f ~/.exports ]; then
  source ~/.exports
fi


pyactivate() {
	# Activates a Python virtual environment.
	# Defaults to ./.venv if no path is provided.
	# Usage: venv [path_to_venv_dir]
	local venv_path="${1:-.venv}"
	local activate_script

	# Check for Windows-like environments (Git Bash, MSYS, Cygwin)
	if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
		activate_script="${venv_path}/Scripts/activate"
	else
		activate_script="${venv_path}/bin/activate"
	fi

	if [ -f "${activate_script}" ]; then
		source "${activate_script}"
	else
		# Use a shell-agnostic way to print the shell name
		echo "${0##*/}: activate script not found: ${activate_script}" >&2
		return 1
	fi
}
alias venv=pyactivate

# Set up completions
autoload -Uz compinit
compinit
source $(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh
source $(brew --prefix)/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
eval "$(uv generate-shell-completion zsh)"

# [ -f ~/.fzf.zsh ] && source ~/.fzf.zsh
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

# test -e "${HOME}/.iterm2_shell_integration.zsh" && source "${HOME}/.iterm2_shell_integration.zsh"

eval "$(zoxide init --cmd cd zsh)"
