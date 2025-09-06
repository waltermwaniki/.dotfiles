#!/usr/bin/env bash
# brewfile — manage Brewfile + installs
set -euo pipefail

# ANSI colors (respect NO_COLOR and non-TTY)
BLUE="\033[1;34m"; YELLOW="\033[1;33m"; RED="\033[1;31m"; RESET="\033[0m"
if [[ -n "${NO_COLOR:-}" || ! -t 1 ]]; then BLUE=""; YELLOW=""; RED=""; RESET=""; fi

# Resolve repository root (script lives in ~/.dotfiles/home/.local/bin)
resolve_self() {
  local src="${BASH_SOURCE[0]}"
  while [ -h "$src" ]; do
    local dir; dir="$(cd -P "$(dirname "$src")" && pwd)"
    src="$(readlink "$src")"
    [[ "$src" != /* ]] && src="$dir/$src"
  done
  cd -P "$(dirname "$src")" && pwd
}

SCRIPT_DIR="$(resolve_self)"
REPO_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BREWFILE="$REPO_DIR/Brewfile"
EXTRA_BREWFILE="$REPO_DIR/Brewfile.extra"

INCLUDE_ALL=0
INCLUDE_NAMES=()
INCLUDE_FILES=()
PRIMARY_INCLUDE_FILE=""

# Discover include files based on INCLUDE_ALL/INCLUDE_NAMES
resolve_includes() {
  INCLUDE_FILES=()
  if (( INCLUDE_ALL )); then
    while IFS= read -r path; do
      [[ -f "$path" ]] && INCLUDE_FILES+=("$path")
    done < <(find "$REPO_DIR" -maxdepth 1 -type f -name 'Brewfile.*' | sort)
  else
    for name in "${INCLUDE_NAMES[@]}"; do
      local f="$REPO_DIR/Brewfile.$name"
      [[ -f "$f" ]] && INCLUDE_FILES+=("$f")
    done
  fi
  # Primary target for new lines when appending/splitting
  if ((${#INCLUDE_FILES[@]} > 0)); then
    PRIMARY_INCLUDE_FILE="${INCLUDE_FILES[0]}"
  else
    PRIMARY_INCLUDE_FILE=""
  fi
}

# Kinds we track in dumps
KINDS='tap|brew|cask|mas|whalebrew|vscode'
KIND_GREP="^(${KINDS})[[:space:]]"

EDITOR_CMD="${EDITOR:-vi}"

say()  { printf "${BLUE}==>${RESET} %s\n" "$*"; }
warn() { printf "${YELLOW}[warn]${RESET} %s\n" "$*"; }
die()  { printf "${RED}[err]${RESET} %s\n" "$*"; exit 1; }

get_files_summary() {
  local files_to_report=("$(basename "$BREWFILE")")
  for inc in "${INCLUDE_FILES[@]}"; do
    files_to_report+=("$(basename "$inc")")
  done

  # Join the array with ", " separator
  local summary=""
  local separator=""
  for file in "${files_to_report[@]}"; do
    summary+="${separator}${file}"
    separator=", "
  done
  echo "$summary"
}


ensure_brew() {
  # make brew available on Intel or Apple Silicon
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null)" || true
  eval "$(/usr/local/bin/brew shellenv 2>/dev/null)" || true
  command -v brew >/dev/null 2>&1 || die "Homebrew not found."
}

usage() {
cat <<EOF
Usage: brewfile <command> [options]

Commands:
  apply        Install/ensure everything in Brewfile (and extra if included)
  check        Show missing items and a grouped summary of differences (no changes)
  dump         Update Brewfile from current system (append or --force to overwrite)
  list         Show all dependencies currently recorded (union when --include extra)
  cleanup      Preview removals; use --apply to actually uninstall extras
  edit         Open Brewfile in \$EDITOR (${EDITOR_CMD})
  path         Print path(s) to Brewfile (and extra when included)

Options:
  --include NAME  Include Brewfile.NAME (repeat or comma-separated for multiple)
  --all           Include all Brewfile.* alongside Brewfile
  --force          For 'dump': overwrite (and split to extra when included)
  --apply          For 'cleanup': actually uninstall extras (DANGEROUS)
  -h, --help       Show this help

Examples:
  brewfile check
  brewfile apply
  brewfile apply --include extra
  brewfile apply --include work --include personal
  brewfile check --all
  brewfile dump --force
  brewfile dump --include extra
  brewfile cleanup
  brewfile cleanup --include extra
EOF
}

cmd="${1:-}"; [[ -z "$cmd" ]] && { usage; exit 2; }
shift || true

# parse shared options
APPLY=0
FORCE=0
INCLUDE_EXTRA=0
while (( "$#" )); do
  case "$1" in
    --include | --include=*)
      local val
      if [[ "$1" == --include=* ]]; then
        val="${1#--include=}"
      else
        shift; val="${1:-}"
      fi
      IFS=',' read -r -a parts <<< "$val"; for p in "${parts[@]}"; do [[ -n "$p" ]] && INCLUDE_NAMES+=("$p"); done
      ;;
    --all) INCLUDE_ALL=1 ;;
    --force) FORCE=1 ;;
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) break ;;
  esac
  shift || true
done

ensure_brew

resolve_includes

# helper: merged Brewfile (union of main + extra) in a temp file
merged_brewfile_tmp() {
  local tmp; tmp="$(mktemp)"
  if ((${#INCLUDE_FILES[@]} > 0)); then
    awk 'NF' "$BREWFILE" "${INCLUDE_FILES[@]}" 2>/dev/null | awk '!seen[$0]++' > "$tmp" || cp "$BREWFILE" "$tmp"
  else
    cp "$BREWFILE" "$tmp"
  fi
  echo "$tmp"
}

# --- Command Implementations ---
cmd_apply() {
  say "Applying Brewfile → $BREWFILE"
  brew bundle --file "$BREWFILE"
  if ((${#INCLUDE_FILES[@]} > 0)); then
    for inc in "${INCLUDE_FILES[@]}"; do
      say "Applying include → $inc"
      brew bundle --file "$inc"
    done
  fi
}

cmd_check() {
  say "Checking missing items for $(get_files_summary)"
  # brew's own check only takes one file; run against the merged view via dump compare
  if brew bundle check --file "$BREWFILE"; then
    say "All set. Nothing to install (for main Brewfile)."
  else
    warn "Some items are missing in main Brewfile. Run: brewfile apply"
  fi

  tmp="$(mktemp)"; trap 'rm -f "$tmp" "$tmp.current.sorted" "$tmp.fresh.sorted" "$current_tmp"' EXIT
  brew bundle dump --file "$tmp" --force --no-vscode >/dev/null

  current_tmp="$(merged_brewfile_tmp)"
  # --- Order-insensitive comparison ---
  grep -E "$KIND_GREP" "$current_tmp" | sed 's/[[:space:]]\+$//' | sort -u > "$tmp.current.sorted"
  grep -E "$KIND_GREP" "$tmp"         | sed 's/[[:space:]]\+$//' | sort -u > "$tmp.fresh.sorted"

  add_lines=$(comm -13 "$tmp.current.sorted" "$tmp.fresh.sorted" || true)
  rm_lines=$(comm -23 "$tmp.current.sorted" "$tmp.fresh.sorted" || true)

  group_print() {
    # $1 = label, $2+ = lines (newline-separated via heredoc/echo)
    local label="$1"; shift
    local lines="$*"
    printf "${BLUE}\t%s${RESET}\n" "$label"
    if [[ -z "$lines" ]]; then
      printf "\t  (none)\n"
      return
    fi
    echo "$lines" | awk '
      function pr(t){ if(c[t]>0){ printf("\t  %s (%d): %s\n", t, c[t], a[t]); }}
      {
        kind=$1
        # Match from the first quote to the second quote
        if (match($0, /"([^"]+)"/)) {
          # Get the captured group
          name = substr($0, RSTART + 1, RLENGTH - 2)
          if (a[kind] == "") { a[kind]=name; c[kind]=1 } else { a[kind]=a[kind] ", " name; c[kind]++ }
        }
      }
      END { pr("tap"); pr("brew"); pr("cask"); pr("mas"); pr("whalebrew"); pr("vscode"); }
    '
  }

  say "Changes (ignoring order):"
  if [[ -z "$add_lines$rm_lines" ]]; then
    say "  No net changes between current set and fresh dump."
  else
    group_print "To ADD:" "$add_lines"
    group_print "To REMOVE:" "$rm_lines"
  fi
}

cmd_dump() {
  mkdir -p "$(dirname "$BREWFILE")"
  if (( FORCE )); then
    say "Dumping current system (overwrite) → $(get_files_summary)"
    tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT # Simplified trap, will be redefined
    brew bundle dump --file "$tmp" --force --no-vscode >/dev/null
    mkdir -p "$(dirname "$BREWFILE")"
    if ((${#INCLUDE_FILES[@]} > 0)); then
      # --- Fix: cache all file contents BEFORE clearing them ---
      declare -A include_caches
      local cache_files_to_clean=()
      local main_curr_cache; main_curr_cache="$(mktemp)"
      cache_files_to_clean+=("$main_curr_cache")
      awk -v pat="$KIND_GREP" '$0 ~ pat {print}' "$BREWFILE" 2>/dev/null | sed 's/[[:space:]]\+$//' | sort -u > "$main_curr_cache" || true

      for inc in "${INCLUDE_FILES[@]}"; do
        local cache_tmp; cache_tmp="$(mktemp)"
        awk -v pat="$KIND_GREP" '$0 ~ pat {print}' "$inc" 2>/dev/null | sed 's/[[:space:]]\+$//' | sort -u > "$cache_tmp" || true
        include_caches["$inc"]="$cache_tmp"
        cache_files_to_clean+=("$cache_tmp")
      done
      trap 'rm -f "$tmp" "${cache_files_to_clean[@]}"' EXIT

      # --- New logic: determine where to put new items (hand-curated main, extras to .extra) ---
      local new_item_target="$BREWFILE"
      for inc in "${INCLUDE_FILES[@]}"; do
        if [[ "$inc" == "$EXTRA_BREWFILE" ]]; then
          new_item_target="$EXTRA_BREWFILE"
          break
        fi
      done
      if [[ "$new_item_target" == "$BREWFILE" && -n "$PRIMARY_INCLUDE_FILE" ]]; then
        # Fallback to primary include if .extra isn't specified, to protect main Brewfile
        new_item_target="$PRIMARY_INCLUDE_FILE"
      fi

      # Now, clear the files for writing
      : > "$BREWFILE"
      for inc in "${INCLUDE_FILES[@]}"; do : > "$inc"; done

      # For each line in fresh dump, place it where it used to belong
      while IFS= read -r line; do
        if [[ -s "$main_curr_cache" ]] && grep -qxF "$line" "$main_curr_cache"; then
          echo "$line" >> "$BREWFILE"; continue
        fi
        placed=0
        for inc in "${INCLUDE_FILES[@]}"; do
          local icurr="${include_caches[$inc]}"
          if [[ -s "$icurr" ]] && grep -qxF "$line" "$icurr"; then
            echo "$line" >> "$inc"; placed=1; break
          fi
        done
        # If not placed, it's a new item. Put it in the designated target file.
        if (( ! placed )); then
          echo "$line" >> "$new_item_target"
        fi
      done < <(grep -E "$KIND_GREP" "$tmp")
      say "Wrote $BREWFILE and ${#INCLUDE_FILES[@]} include file(s)"
    else
      cp "$tmp" "$BREWFILE"
      say "Wrote $BREWFILE"
    fi
  else
    say "Dumping current system (append new lines) → ${INCLUDE_ALL:+Brewfile.*, }Brewfile"
    tmp="$(mktemp)"; trap 'rm -f "$tmp" "$union_tmp"' EXIT
    brew bundle dump --file "$tmp" --force --no-vscode >/dev/null
    touch "$BREWFILE"
    if ((${#INCLUDE_FILES[@]} > 0)); then
      touch "$PRIMARY_INCLUDE_FILE"
      union_tmp="$(merged_brewfile_tmp)"
      while IFS= read -r line; do
        grep -qxF "$line" "$union_tmp" || echo "$line" >> "$PRIMARY_INCLUDE_FILE"
      done < <(grep -E "$KIND_GREP" "$tmp")
      say "Appended new items to $PRIMARY_INCLUDE_FILE"
    else
      while IFS= read -r line; do
        grep -qxF "$line" "$BREWFILE" || echo "$line" >> "$BREWFILE"
      done < <(grep -E "$KIND_GREP" "$tmp")
      say "Appended new items to $BREWFILE"
    fi
  fi
}

cmd_list() {
  say "Listing dependencies from $(get_files_summary)"
  if ((${#INCLUDE_FILES[@]} > 0)); then
    {
      brew bundle list --all --file "$BREWFILE"
      for inc in "${INCLUDE_FILES[@]}"; do brew bundle list --all --file "$inc"; done
    } | awk 'NF' | sort -u
  else
    brew bundle list --all --file "$BREWFILE"
  fi
}

cmd_cleanup() {
  say "Computing items NOT in $(get_files_summary)"
  mf="$(merged_brewfile_tmp)"; trap 'rm -f "$mf"' EXIT
  if (( APPLY )); then
    warn "Applying cleanup. This will uninstall items. Press Ctrl-C to abort."
    brew bundle cleanup --file "$mf" --force
  else
    # Preview mode: capture output so we can adjust messaging regardless of exit code
    output=$(brew bundle cleanup --file "$mf" 2>&1 || true)
    if printf "%s\n" "$output" | grep -qE '^(Would `brew cleanup`|Would remove:)'; then
      printf "%s\n" "$output" | sed -E 's/Run `brew bundle cleanup --force` to make these changes\./Run `brewfile cleanup --apply` to make these changes./'
      warn "The above would be removed. To apply, run: brewfile cleanup --apply"
    else
      say "Nothing to clean up."
    fi
  fi
}

cmd_edit() {
  "$EDITOR_CMD" "$BREWFILE"
}

cmd_path() {
  if ((${#INCLUDE_FILES[@]} > 0)); then
    echo "$BREWFILE"
    for inc in "${INCLUDE_FILES[@]}"; do echo "$inc"; done
  else
    echo "$BREWFILE"
  fi
}


# --- Main Dispatcher ---
case "$cmd" in
  apply|check|dump|list|cleanup|edit|path)
    "cmd_$cmd" "$@" ;;
  *)
    usage; exit 2;;
esac
