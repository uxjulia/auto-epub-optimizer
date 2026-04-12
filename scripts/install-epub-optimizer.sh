#!/bin/bash
# install-epub-optimizer.sh
# Installs the epub-optimizer systemd user service.
# Run this from the scripts/ directory alongside epub-optimizer.sh and epub-optimizer.service.
#
# Prerequisites:
#   - epub-watcher.service must already be installed (run install-epub-watcher.sh first)
#   - Node.js must be available (check with: node --version)

set -e

SCRIPT_SRC="./epub-optimizer.sh"
LOAD_ENV_SRC="./load-env.sh"
SCRIPT_DEST="$HOME/.local/bin/epub-optimizer.sh"
LOAD_ENV_DEST="$HOME/.local/bin/load-env.sh"
SERVICE_SRC="./epub-optimizer.service"
SERVICE_DEST="$HOME/.config/systemd/user/epub-optimizer.service"
CONFIG_DIR="$HOME/.config/epub-optimizer"
CONFIG_FILE="$CONFIG_DIR/.env"

echo "=== epub-optimizer installer ==="

# 1. Check for Node.js
if ! command -v node &>/dev/null; then
  echo "[ERROR] Node.js not found. Install it first:"
  echo "  curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -"
  echo "  sudo apt-get install -y nodejs"
  exit 1
else
  echo "[1/5] Node.js found: $(node --version) ✓"
fi

# 2. Set up configuration
echo "[2/5] Setting up configuration"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_FILE" ]; then
  cp "../.env.example" "$CONFIG_FILE"
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
echo "[3/5] Installing scripts to $HOME/.local/bin"
mkdir -p "$HOME/.local/bin"
cp "$LOAD_ENV_SRC" "$LOAD_ENV_DEST"
cp "$SCRIPT_SRC" "$SCRIPT_DEST"
chmod +x "$LOAD_ENV_DEST" "$SCRIPT_DEST"
echo "      Done. ✓"

# 4. Create bookdrop folder structure
echo "[4/5] Creating bookdrop folder structure: $BOOKDROP_DIR"
mkdir -p "$BOOKDROP_DIR"
mkdir -p "$BOOKDROP_DIR/processing"
mkdir -p "$BOOKDROP_DIR/processed"
mkdir -p "$BOOKDROP_DIR/failed"
echo "      Done. ✓"

# 5. Install and start systemd user service
echo "[5/5] Installing systemd user service"
mkdir -p "$HOME/.config/systemd/user"
cp "$SERVICE_SRC" "$SERVICE_DEST"
systemctl --user daemon-reload
systemctl --user enable epub-optimizer.service
systemctl --user start epub-optimizer.service
echo "      Done. ✓"

echo ""
systemctl --user status epub-optimizer.service --no-pager

echo ""
echo "=== Installation complete! ==="
echo ""
echo "Full pipeline:"
echo "  $BOOKDROP_DIR  →[optimizer]→  $EPUB_OUTPUT_DIR  →[watcher]→  $WATCHER_DEST_DIR"
echo ""
echo "Bookdrop subfolders:"
echo "  processing/  — file is currently being optimized"
echo "  processed/   — successfully optimized"
echo "  failed/      — optimizer returned an error (check logs)"
echo ""
echo "Useful commands:"
echo "  Live optimizer log:  journalctl --user -u epub-optimizer -f"
echo "  Live watcher log:    journalctl --user -u epub-watcher -f"
echo "  Status of both:      systemctl --user status epub-optimizer epub-watcher"
echo "  Restart both:        systemctl --user restart epub-optimizer epub-watcher"