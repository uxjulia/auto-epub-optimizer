#!/bin/bash
# epub-watcher.sh
# Watches the epub-optimizer output folder and publishes new files to the destination.

# Load configuration from ~/.config/epub-optimizer/.env
source "$(dirname "$0")/load-env.sh"

WATCH_DIR="$EPUB_OUTPUT_DIR"
DEST_DIR="$WATCHER_DEST_DIR"
LOG_FILE="$WATCHER_LOG_FILE"

# Ensure destination and log directories exist
mkdir -p "$DEST_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

deliver_file() {
  local src="$1"
  local filename dst tmp

  [ -f "$src" ] || return 0

  filename=$(basename "$src")
  dst="$DEST_DIR/$filename"
  tmp="$DEST_DIR/.${filename}.part.$$"

  rm -f "$tmp"

  # Publish via temp name + in-place rename inside the destination folder.
  # This is the shell equivalent of "write temp file, then rename live" in Node,
  # and tends to be noticed more reliably by Windows-side watchers than a raw
  # cross-filesystem move from Docker/WSL into an NTFS-backed folder.
  if ! cp -f "$src" "$tmp"; then
    log "ERROR staging: $filename"
    rm -f "$tmp"
    return 1
  fi

  sync "$tmp" 2>/dev/null || true

  if ! mv -f "$tmp" "$dst"; then
    log "ERROR publishing: $filename"
    rm -f "$tmp"
    return 1
  fi

  # Best-effort metadata bump after the rename for watchers that key off the
  # final file timestamp rather than the copy itself.
  touch "$dst" 2>/dev/null || true

  if rm -f "$src"; then
    log "Published: $filename"
  else
    log "WARNING published but could not remove source: $filename"
  fi
}

log "epub-watcher started. Watching: $WATCH_DIR"
log "Publishing files to: $DEST_DIR"

# Publish any files that already exist in the watch dir on startup
for f in "$WATCH_DIR"/*; do
  [ -f "$f" ] || continue
  filename=$(basename "$f")
  case "$filename" in
    .* ) continue ;;
    *.epub ) ;;
    * ) continue ;;
  esac

  log "Found existing file on startup: $filename — publishing to $DEST_DIR"
  deliver_file "$f"
done

# Watch for new files using inotifywait
inotifywait -m -e close_write -e moved_to --format '%f' "$WATCH_DIR" 2>>"$LOG_FILE" |
while read -r filename; do
  src="$WATCH_DIR/$filename"

  # Ignore hidden temp files and non-EPUB artifacts; the optimizer writes
  # a hidden staging file before atomically renaming the finished book.
  case "$filename" in
    .* ) continue ;;
    *.epub ) ;;
    * ) continue ;;
  esac

  # Skip if it's not a regular file (e.g. temp files)
  [ -f "$src" ] || continue

  log "Detected new file: $filename — publishing to $DEST_DIR"
  deliver_file "$src"
done
