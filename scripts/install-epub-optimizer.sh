#!/bin/bash
# install-epub-optimizer.sh
# Installs the epub-optimizer systemd user service.
# Run this from the scripts/ directory alongside epub-optimizer.sh and epub-optimizer.service.
#
# Prerequisites:
#   - epub-watcher.service must already be installed (run install-epub-watcher.sh first)
#   - Python 3 must be available
#   - Python dependencies must be installed from requirements.txt

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SCRIPT_SRC="$SCRIPT_DIR/epub-optimizer.sh"
LOAD_ENV_SRC="$SCRIPT_DIR/load-env.sh"
SCRIPT_DEST="$HOME/.local/bin/epub-optimizer.sh"
LOAD_ENV_DEST="$HOME/.local/bin/load-env.sh"
SERVICE_SRC="$SCRIPT_DIR/epub-optimizer.service"
SERVICE_DEST="$HOME/.config/systemd/user/epub-optimizer.service"
CONFIG_DIR="$HOME/.config/epub-optimizer"
CONFIG_FILE="$CONFIG_DIR/.env"

echo "=== epub-optimizer installer ==="

# 1. Check for Python
if ! command -v python3 &>/dev/null; then
  echo "[ERROR] Python 3 not found. Install it first."
  exit 1
else
  echo "[1/6] Python found: $(python3 --version) ✓"
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

# 3. Check Python dependencies
echo "[3/6] Checking Python dependencies"
if ! "$OPTIMIZER_PYTHON" -c "import lxml, PIL, cssutils" &>/dev/null; then
  echo "[ERROR] Missing Python dependencies."
  echo "Install them with:"
  echo "  $OPTIMIZER_PYTHON -m pip install -r $REPO_ROOT/requirements.txt"
  exit 1
else
  echo "      Dependencies found. ✓"
fi

# 4. Install scripts
echo "[4/6] Installing scripts to $HOME/.local/bin"
mkdir -p "$HOME/.local/bin"
cp "$LOAD_ENV_SRC" "$LOAD_ENV_DEST"
cp "$SCRIPT_SRC" "$SCRIPT_DEST"
chmod +x "$LOAD_ENV_DEST" "$SCRIPT_DEST"
echo "      Done. ✓"

# 5. Create bookdrop folder structure
echo "[5/6] Creating bookdrop folder structure: $BOOKDROP_DIR"
mkdir -p "$BOOKDROP_DIR"
mkdir -p "$BOOKDROP_DIR/processing"
mkdir -p "$BOOKDROP_DIR/processed"
mkdir -p "$BOOKDROP_DIR/failed"
echo "      Done. ✓"

# 6. Install and start systemd user service
echo "[6/6] Installing systemd user service"
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
