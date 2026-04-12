#!/bin/bash
# epub-optimizer.sh
# Polls BOOKDROP_DIR for incoming .epub files, runs optimize.js on each,
# and outputs to EPUB_OUTPUT_DIR (which epub-watcher.service then moves to WATCHER_DEST_DIR).
#
# NOTE: inotify does not work on Windows NTFS mounts (/mnt/c/) in WSL2,
# so this script uses a polling loop instead.

# Load configuration from ~/.config/epub-optimizer/.env
source "$(dirname "$0")/load-env.sh"

OUTPUT_DIR="$EPUB_OUTPUT_DIR"
LOG_FILE="$OPTIMIZER_LOG_FILE"
# BOOKDROP_DIR, CALIBRE_WATCH_FOLDER, OPTIMIZER_SCRIPT, POLL_INTERVAL, KEEP_DAYS come from load-env.sh

# Subdirs inside bookdrop for processed/failed tracking
PROCESSING_DIR="$BOOKDROP_DIR/processing"
PROCESSED_DIR="$BOOKDROP_DIR/processed"
FAILED_DIR="$BOOKDROP_DIR/failed"

# --- Setup ---
mkdir -p "$OUTPUT_DIR"
[ -n "$CALIBRE_WATCH_FOLDER" ] && mkdir -p "$CALIBRE_WATCH_FOLDER"
mkdir -p "$PROCESSING_DIR" "$PROCESSED_DIR" "$FAILED_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "epub-optimizer started."
log "  Watching:  $BOOKDROP_DIR"
log "  Output:    $OUTPUT_DIR"
log "  Poll interval: ${POLL_INTERVAL}s"

# --- Main loop ---
while true; do
  # Find .epub files directly in bookdrop (not in subdirs like processing/processed/failed)
  while IFS= read -r -d '' filepath; do
    filename=$(basename "$filepath")

    # Optionally copy to Calibre's watch folder before processing
    if [ -n "$CALIBRE_WATCH_FOLDER" ]; then
      if cp "$filepath" "$CALIBRE_WATCH_FOLDER/$filename" 2>/dev/null; then
        log "Copied to Calibre watch folder: $filename"
      else
        log "WARNING: Could not copy $filename to $CALIBRE_WATCH_FOLDER — continuing anyway"
      fi
    fi

    # Atomically move to processing/ to claim the file (prevents double-processing
    # if multiple WSL2 sessions or scripts are running)
    staging="$PROCESSING_DIR/$filename"
    if ! mv "$filepath" "$staging" 2>/dev/null; then
      # Another process already claimed it — skip
      continue
    fi

    log "Processing: $filename"

    # Run the optimizer
    node "$OPTIMIZER_SCRIPT" -o "$OUTPUT_DIR" "$staging" >> "$LOG_FILE" 2>&1
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
      mv "$staging" "$PROCESSED_DIR/$filename"
      log "Done: $filename → $OUTPUT_DIR"
      log "Pruning epubs older than ${KEEP_DAYS} days..."
      find "$PROCESSED_DIR" -name "*.epub" -mtime +${KEEP_DAYS} -delete
    else
      mv "$staging" "$FAILED_DIR/$filename"
      log "ERROR (exit $exit_code): $filename moved to $FAILED_DIR"
    fi

  done < <(find "$BOOKDROP_DIR" -maxdepth 1 -name "*.epub" -print0 2>/dev/null)

  sleep "$POLL_INTERVAL"
done