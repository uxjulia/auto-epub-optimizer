#!/usr/bin/env bash
# load-env.sh — Source this file from other scripts; do not run it directly.
#
# Loads epub-optimizer configuration from ~/.config/epub-optimizer/.env.
# Override the config path by setting EPUB_OPTIMIZER_ENV before sourcing:
#   EPUB_OPTIMIZER_ENV=/custom/path/.env source load-env.sh

_env_file="${EPUB_OPTIMIZER_ENV:-$HOME/.config/epub-optimizer/.env}"

if [ -f "$_env_file" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$_env_file"
  set +a
else
  echo "[load-env] WARNING: Config not found at $_env_file" >&2
  echo "[load-env] Copy .env.example to $_env_file and customize it." >&2
fi
unset _env_file

# --- Defaults (used if a variable is not set in .env) ---
BOOKDROP_DIR="${BOOKDROP_DIR:-$HOME/bookdrop}"
# No default — leave unset if not configured so the optimizer skips the Calibre copy step
CALIBRE_WATCH_FOLDER="${CALIBRE_WATCH_FOLDER:-}"
EPUB_OUTPUT_DIR="${EPUB_OUTPUT_DIR:-$HOME/epub-optimizer/cli/optimized}"
OPTIMIZER_PYTHON="${OPTIMIZER_PYTHON:-python3}"
OPTIMIZER_SCRIPT="${OPTIMIZER_SCRIPT:-}"
WATCHER_DEST_DIR="${WATCHER_DEST_DIR:-$HOME/x4-library}"
OPTIMIZER_LOG_FILE="${OPTIMIZER_LOG_FILE:-$HOME/.local/log/epub-optimizer.log}"
WATCHER_LOG_FILE="${WATCHER_LOG_FILE:-$HOME/.local/log/epub-watcher.log}"
POLL_INTERVAL="${POLL_INTERVAL:-5}"
KEEP_DAYS="${KEEP_DAYS:-5}"
