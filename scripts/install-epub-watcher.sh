#!/bin/bash
# install-epub-watcher.sh
# One-shot installer for the epub-watcher systemd service.
# Run this from the scripts/ directory alongside epub-watcher.sh and epub-watcher.service.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SCRIPT_SRC="$SCRIPT_DIR/epub-watcher.sh"
LOAD_ENV_SRC="$SCRIPT_DIR/load-env.sh"
SCRIPT_DEST="$HOME/.local/bin/epub-watcher.sh"
LOAD_ENV_DEST="$HOME/.local/bin/load-env.sh"
SERVICE_SRC="$SCRIPT_DIR/epub-watcher.service"
SERVICE_DEST="$HOME/.config/systemd/user/epub-watcher.service"
CONFIG_DIR="$HOME/.config/epub-optimizer"
CONFIG_FILE="$CONFIG_DIR/.env"

echo "=== epub-watcher installer ==="

# 1. Check for inotify-tools
if ! command -v inotifywait &>/dev/null; then
  echo "[1/6] inotify-tools not found. Installing..."
  sudo apt-get update -qq && sudo apt-get install -y inotify-tools
else
  echo "[1/6] inotify-tools already installed. ✓"
fi

# 2. Set up configuration
echo "[2/6] Setting up configuration"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_FILE" ]; then
  cp "$REPO_ROOT/.env.example" "$CONFIG_FILE"
  echo "      Created $CONFIG_FILE from .env.example"
  echo "      *** Edit $CONFIG_FILE before continuing! ***"
  echo "      Then re-run this installer."
  exit 0
else
  echo "      Config already exists at $CONFIG_FILE ✓"
fi

# Load config so we can use its values below
# shellcheck source=/dev/null
source "$LOAD_ENV_SRC"

# 3. Install scripts
echo "[3/6] Installing scripts to $HOME/.local/bin"
mkdir -p "$HOME/.local/bin"
cp "$LOAD_ENV_SRC" "$LOAD_ENV_DEST"
cp "$SCRIPT_SRC" "$SCRIPT_DEST"
chmod +x "$LOAD_ENV_DEST" "$SCRIPT_DEST"
echo "      Done. ✓"

# 4. Create destination folder
echo "[4/6] Creating destination folder: $WATCHER_DEST_DIR"
mkdir -p "$WATCHER_DEST_DIR"
echo "      Done. ✓"

# 5. Install systemd user service
echo "[5/6] Installing systemd user service"
mkdir -p "$HOME/.config/systemd/user"
cp "$SERVICE_SRC" "$SERVICE_DEST"
systemctl --user daemon-reload
systemctl --user enable epub-watcher.service
systemctl --user restart epub-watcher.service
echo "      Done. ✓"

# 6. Status check
echo "[6/6] Checking service status..."
systemctl --user status epub-watcher.service --no-pager

echo ""
echo "=== Installation complete! ==="
echo "Files placed in:  $EPUB_OUTPUT_DIR"
echo "will be moved to: $WATCHER_DEST_DIR"
echo ""
echo "Useful commands:"
echo "  Check status:  systemctl --user status epub-watcher"
echo "  View logs:     journalctl --user -u epub-watcher -f"
echo "  Stop watcher:  systemctl --user stop epub-watcher"
echo "  Restart:       systemctl --user restart epub-watcher"
