#!/bin/bash
# epub-optimizer.sh
# Polls BOOKDROP_DIR for incoming .epub files, runs optimize.py on each,
# and outputs to EPUB_OUTPUT_DIR (which epub-watcher.service then moves to WATCHER_DEST_DIR).
#
# NOTE: inotify does not work on Windows NTFS mounts (/mnt/c/) in WSL2,
# so this script uses a polling loop instead.

# Load configuration from ~/.config/epub-optimizer/.env
source "$(dirname "$0")/load-env.sh"

OUTPUT_DIR="$EPUB_OUTPUT_DIR"
LOG_FILE="$OPTIMIZER_LOG_FILE"
# BOOKDROP_DIR, OPTIMIZE_ONLY_DIR, CALIBRE_WATCH_FOLDER, OPTIMIZER_PYTHON,
# OPTIMIZER_SCRIPT, POLL_INTERVAL, KEEP_DAYS come from load-env.sh

# --- Setup ---
mkdir -p "$OUTPUT_DIR"
[ -n "$CALIBRE_WATCH_FOLDER" ] && mkdir -p "$CALIBRE_WATCH_FOLDER"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

setup_drop_dir() {
  local watch_dir="$1"
  mkdir -p "$watch_dir" "$watch_dir/processing" "$watch_dir/processed" "$watch_dir/failed"
}

process_drop_dir() {
  local watch_dir="$1"
  local copy_to_calibre="$2"
  local processing_dir="$watch_dir/processing"
  local processed_dir="$watch_dir/processed"
  local failed_dir="$watch_dir/failed"
  local filename filepath staging optimizer_args exit_code

  while IFS= read -r -d '' filepath; do
    filename=$(basename "$filepath")

    # Atomically move to processing/ to claim the file (prevents double-processing
    # if multiple WSL2 sessions or scripts are running)
    staging="$processing_dir/$filename"
    if ! mv "$filepath" "$staging" 2>/dev/null; then
      # Another process already claimed it — skip
      continue
    fi

    # Skip zero-byte files (Windows NTFS can recreate empty stubs after a move)
    if [ ! -s "$staging" ]; then
      log "WARNING: $filename is empty in $watch_dir — skipping and removing"
      rm -f "$staging"
      continue
    fi

    # Optionally copy to Calibre's watch folder before processing
    # (done after the empty-file check so CWA never receives a stub)
    if [ "$copy_to_calibre" = "1" ] && [ -n "$CALIBRE_WATCH_FOLDER" ]; then
      if cp "$staging" "$CALIBRE_WATCH_FOLDER/$filename" 2>/dev/null; then
        log "Copied to Calibre watch folder: $filename"
      else
        log "WARNING: Could not copy $filename to $CALIBRE_WATCH_FOLDER — continuing anyway"
      fi
    fi

    log "Processing: $filename"

    optimizer_args=(-o "$OUTPUT_DIR")
    [ -n "$EPUB_QUALITY" ] && optimizer_args+=("--quality" "$EPUB_QUALITY")
    [ -n "$EPUB_MAX_WIDTH" ] && optimizer_args+=("--max-width" "$EPUB_MAX_WIDTH")
    [ -n "$EPUB_MAX_HEIGHT" ] && optimizer_args+=("--max-height" "$EPUB_MAX_HEIGHT")
    [ -n "$EPUB_CONTRAST" ] && optimizer_args+=("--contrast")
    [ -n "$EPUB_CONTRAST_FACTOR" ] && optimizer_args+=("--contrast-factor" "$EPUB_CONTRAST_FACTOR")
    [ -n "$EPUB_NO_GRAYSCALE" ] && optimizer_args+=("--no-grayscale")
    [ -n "$EPUB_NO_REMOVE_FONTS" ] && optimizer_args+=("--no-remove-fonts")
    [ -n "$EPUB_NO_REMOVE_CSS" ] && optimizer_args+=("--no-remove-css")
    [ -n "$EPUB_LIGHT_NOVEL" ] && optimizer_args+=("--light-novel")
    [ -n "$EPUB_SPLIT_LONG_SECTIONS" ] && optimizer_args+=("--split-long-sections")
    [ -n "$EPUB_SECTION_SPLIT_WORD_THRESHOLD" ] && optimizer_args+=("--section-split-word-threshold" "$EPUB_SECTION_SPLIT_WORD_THRESHOLD")
    [ -n "$EPUB_WORDS_PER_REFERENCE_PAGE" ] && optimizer_args+=("--words-per-reference-page" "$EPUB_WORDS_PER_REFERENCE_PAGE")
    [ -n "$EPUB_FILENAME_FORMAT" ] && optimizer_args+=("--filename-format" "$EPUB_FILENAME_FORMAT")
    [ -n "$EPUB_SUFFIX" ] && optimizer_args+=("--suffix=$EPUB_SUFFIX")

    "$OPTIMIZER_PYTHON" "$OPTIMIZER_SCRIPT" "${optimizer_args[@]}" "$staging" >> "$LOG_FILE" 2>&1
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
      mv "$staging" "$processed_dir/$filename"
      log "Done: $filename → $OUTPUT_DIR"
      log "Pruning epubs older than ${KEEP_DAYS} days in $processed_dir..."
      find "$processed_dir" -name "*.epub" -mtime +${KEEP_DAYS} -delete
    else
      mv "$staging" "$failed_dir/$filename"
      log "ERROR (exit $exit_code): $filename moved to $failed_dir"
    fi

  done < <(find "$watch_dir" -maxdepth 1 -name "*.epub" -print0 2>/dev/null)
}

setup_drop_dir "$BOOKDROP_DIR"
if [ -n "$OPTIMIZE_ONLY_DIR" ] && [ "$OPTIMIZE_ONLY_DIR" != "$BOOKDROP_DIR" ]; then
  setup_drop_dir "$OPTIMIZE_ONLY_DIR"
fi

log "epub-optimizer started."
log "  Watching main drop folder: $BOOKDROP_DIR"
if [ -n "$OPTIMIZE_ONLY_DIR" ] && [ "$OPTIMIZE_ONLY_DIR" != "$BOOKDROP_DIR" ]; then
  log "  Watching optimize-only folder: $OPTIMIZE_ONLY_DIR"
elif [ -n "$OPTIMIZE_ONLY_DIR" ]; then
  log "  WARNING: OPTIMIZE_ONLY_DIR matches BOOKDROP_DIR and will be ignored"
fi
log "  Output:    $OUTPUT_DIR"
log "  Poll interval: ${POLL_INTERVAL}s"

if [ -z "$OPTIMIZER_SCRIPT" ]; then
  log "ERROR: OPTIMIZER_SCRIPT is not set. Add the absolute path to cli/optimize.py in ~/.config/epub-optimizer/.env"
  exit 1
fi

# --- Main loop ---
while true; do
  process_drop_dir "$BOOKDROP_DIR" "1"
  if [ -n "$OPTIMIZE_ONLY_DIR" ] && [ "$OPTIMIZE_ONLY_DIR" != "$BOOKDROP_DIR" ]; then
    process_drop_dir "$OPTIMIZE_ONLY_DIR" "0"
  fi

  sleep "$POLL_INTERVAL"
done
