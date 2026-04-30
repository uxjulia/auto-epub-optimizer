# Automated EPUBKit Optimizer Workflow

**<div align="center">Drop EPUB into folder → Automatically gets optimized → File is moved to your library</div>**<br/>

Automatically optimizes EPUB files for e-readers like the XTEINK X4 using the Python pipeline from `epubkit`. It converts images to baseline JPEG, applies 4-level grayscale, repairs EPUB structure, strips embedded fonts, removes unused CSS, cleans metadata/text, fixes TOCs, handles SVG covers, and repackages the EPUB correctly.

Three ways to use it:

1. Automatically with a watcher via Docker Compose or Systemd
2. Manually by running the Python CLI (`cli/optimize.py`)
3. Manually via the legacy browser-based GUI (`browser/index.html`), no install required

## Why this exists

I have two e-readers: a Kindle Colorsoft and an XTEINK X4. I wanted a single drop folder where adding a book would automatically populate both devices' libraries: the original full-color EPUB going to Calibre for the Kindle, and a grayscale-optimized version landing in a separate library for the X4. That X4 library can be served by any OPDS server that doesn't require a Calibre database so the book shows up ready to read with no manual steps.

## Features

- Drop an `.epub` into one folder and have it appear in two separately managed libraries automatically
- The original is copied to your Calibre watch folder and handled from there as normal
- A grayscale-optimized copy is written to a separate X4 library, ready to serve via OPDS
- Single-library mode also supported: leave `CALIBRE_WATCH_FOLDER` unset and only the optimized copy is produced
- Uses the full `epubkit` cleanup pipeline, not only image conversion

# Usage

> Note: The default settings are for the XTEINK X4's 800x480 image bounds. For another device, set `EPUB_MAX_WIDTH` and `EPUB_MAX_HEIGHT` in your config or pass `-W`/`-H` to `cli/optimize.py`.

## Docker Compose

The repo includes a `docker-compose.yml` that runs a two-service pipeline without installing Python dependencies or `inotify-tools` on the host.

### Setup

```bash
cp .env.example .env
# Edit .env - set BOOKDROP_DIR, WATCHER_DEST_DIR, and optionally CALIBRE_WATCH_FOLDER
```

The containers use fixed internal paths (`/bookdrop`, `/output`, `/destination`, `/calibre`). You only need to set the **host-side** paths in `.env`. `EPUB_OUTPUT_DIR` is handled internally via a shared Docker volume between the two services so you do not need to set it.

#### Why two services?

The optimizer writes finished EPUBs to an intermediate Docker volume (`output`), and the watcher moves them from there to `WATCHER_DEST_DIR`. This split exists because `inotify` is unreliable on Windows NTFS paths (e.g. `/mnt/c/...`) even inside Docker on WSL2 due to a kernel-level limitation. By keeping the handoff point on a pure Linux volume, the watcher can reliably detect new files and handle moving the file to a potential Windows-backed destination.

If your `WATCHER_DEST_DIR` is a plain Linux path (e.g. another Linux directory or a Linux-backed Docker bind mount), the two-service split is unnecessary. You can remove the `epub-watcher` service from `docker-compose.yml` and set the optimizer's `EPUB_OUTPUT_DIR` directly to your destination path.

### Run

```bash
docker compose up -d
```

### Logs

```bash
docker compose logs -f epub-optimizer
docker compose logs -f epub-watcher
```

### Stop

```bash
docker compose down
```

## Systemd Automated Watcher (Linux / WSL2)

The `scripts/` folder contains two systemd user services that build a fully automated pipeline:

```
BOOKDROP_DIR  →[epub-optimizer]→  EPUB_OUTPUT_DIR  →[epub-watcher]→  WATCHER_DEST_DIR
```

- **epub-optimizer** - polls a bookdrop folder for `.epub` files, runs `optimize.py` on each, and writes the result to an output folder. Uses polling instead of `inotify` so it works on Windows NTFS mounts (`/mnt/c/`) under WSL2.
- **epub-watcher** - watches the output folder with `inotifywait` and moves finished files to a final destination (e.g. a Calibre/OPDS library folder).

### Prerequisites

- Python 3
- Python dependencies from `requirements.txt`
- `inotify-tools` (the watcher installer will install this automatically if missing)
- systemd user session enabled (standard on most modern Linux distros and WSL2 with systemd)

### 1. Configure

Copy the example config and fill in your paths:

```bash
mkdir -p ~/.config/epub-optimizer
cp .env.example ~/.config/epub-optimizer/.env
```

Edit `~/.config/epub-optimizer/.env`:

| Variable               | Description                                                                                                                        |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `BOOKDROP_DIR`         | Drop `.epub` files here to trigger processing                                                                                      |
| `CALIBRE_WATCH_FOLDER` | Optional - Calibre watch folder; files are copied here before optimization (for use when you want a separate workflow for Calibre) |
| `OPTIMIZER_PYTHON`     | Python executable used to run the optimizer, e.g. `python3` or a virtualenv path                                                   |
| `OPTIMIZER_SCRIPT`     | Absolute path to `cli/optimize.py` in this repo                                                                                    |
| `EPUB_OUTPUT_DIR`      | Where the optimizer writes finished EPUBs                                                                                          |
| `WATCHER_DEST_DIR`     | Where the watcher moves finished EPUBs (your final X4 library folder)                                                              |
| `OPTIMIZER_LOG_FILE`   | Log path for the optimizer service (default: `~/.local/log/epub-optimizer.log`)                                                    |
| `WATCHER_LOG_FILE`     | Log path for the watcher service (default: `~/.local/log/epub-watcher.log`)                                                        |
| `POLL_INTERVAL`        | Seconds between bookdrop scans (default: `5`)                                                                                      |
| `KEEP_DAYS`            | Days to keep files in `bookdrop/processed/` before auto-deletion (default: `5`)                                                    |
| `EPUB_QUALITY`         | Optional JPEG quality, default `70`                                                                                                |
| `EPUB_MAX_WIDTH`       | Optional max image width, default `800`                                                                                            |
| `EPUB_MAX_HEIGHT`      | Optional max image height, default `480`                                                                                           |
| `EPUB_CONTRAST`        | Optional contrast multiplier, default `1.5`                                                                                        |
| `EPUB_LIGHT_NOVEL`     | Optional - set to `1` to rotate/split landscape light-novel images                                                                 |
| `EPUB_SUFFIX`          | Optional suffix appended before `.epub`, e.g. `-optimized`                                                                         |

### 2. Install

Install the watcher first. `epub-optimizer.service` has `After=epub-watcher.service` in its unit file, so systemd expects the watcher unit to exist before the optimizer is registered.

```bash
# Step 1: watcher (moves optimized files to their final destination)
./scripts/install-epub-watcher.sh

# Step 2: optimizer (polls bookdrop, runs optimize.py)
./scripts/install-epub-optimizer.sh
```

Each installer will:

1. Check for dependencies
2. Create the config file from `.env.example` if it doesn't exist yet
3. Copy scripts to `~/.local/bin/`
4. Register and start the systemd user service

### 3. Use

Drop any `.epub` file into your `BOOKDROP_DIR`. The optimizer picks it up within `POLL_INTERVAL` seconds, processes it, and the watcher moves the result to `WATCHER_DEST_DIR`.

Inside `BOOKDROP_DIR` you'll find three subfolders that track state:

| Subfolder     | Meaning                                                |
| ------------- | ------------------------------------------------------ |
| `processing/` | File is currently being optimized                      |
| `processed/`  | Successfully optimized; auto-deleted after `KEEP_DAYS` |
| `failed/`     | Optimizer returned an error, check the logs            |

### Managing the services

```bash
# Status of both services
systemctl --user status epub-optimizer epub-watcher

# Follow live logs
journalctl --user -u epub-optimizer -f
journalctl --user -u epub-watcher -f

# Restart
systemctl --user restart epub-optimizer epub-watcher

# Stop
systemctl --user stop epub-optimizer epub-watcher
```

---

## Browser (no install required)

Open `browser/index.html` directly in a browser. Everything runs locally, no files leave your machine.

This browser page still uses the older JavaScript-only optimizer. The automated watcher, Docker image, and Python CLI use the newer `epubkit` pipeline.

1. Drop one or more `.epub` files onto the drop zone (or click to select)
2. Adjust settings if needed
3. Click **Optimize & Download**

### Settings

| Setting      | Default   | Description                                                               |
| ------------ | --------- | ------------------------------------------------------------------------- |
| JPEG Quality | 85%       | Compression quality for converted images                                  |
| Max Width    | 480 px    | Images wider than this are resized                                        |
| Max Height   | 800 px    | Images taller than this are resized                                       |
| Split Mode   | None      | None / H-Split (rotate & split wide images) / V-Split (split tall images) |
| Overlap      | 5%        | Overlap between split halves                                              |
| Rotation     | Clockwise | Direction images are rotated before an H-Split                            |
| Grayscale    | On        | Convert images to grayscale                                               |

Cover contrast enhancement runs automatically in the browser version as well — no setting required.

---

## CLI

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Usage

```bash
python3 cli/optimize.py [options] <input.epub ...>
python3 cli/optimize.py [options] <directory>
```

### Options

| Flag                   | Default       | Description                              |
| ---------------------- | ------------- | ---------------------------------------- |
| `-o, --output <dir>`   | `./optimized` | Output directory                         |
| `-q, --quality <n>`    | `70`          | JPEG quality (1-100)                     |
| `--no-grayscale`       | -             | Disable grayscale conversion             |
| `--no-contrast`        | -             | Disable contrast boost                   |
| `--contrast <n>`       | `1.5`         | Contrast multiplier for images           |
| `--no-eink-quantize`   | -             | Disable 4-level e-ink quantization       |
| `-W, --max-width <n>`  | `800`         | Max image width in px                    |
| `-H, --max-height <n>` | `480`         | Max image height in px                   |
| `--light-novel`        | -             | Rotate/split landscape light-novel images |
| `--no-remove-fonts`    | -             | Keep embedded fonts                      |
| `--no-remove-css`      | -             | Keep unused CSS                          |
| `--no-generate-cover`  | -             | Do not generate missing cover art        |
| `--no-clean-metadata`  | -             | Keep store-specific metadata             |
| `--no-text-cleanup`    | -             | Disable text cleanup                     |
| `--suffix <str>`       | empty         | Suffix appended to output filename       |
| `-v, --verbose`        | -             | Print progress and summary details       |
| `--help`               | -             | Show help                                |

### Pipeline

The Python CLI uses the copied `epubkit` pipeline in `cli/epubkit_pipeline/`. It checks for DRM, extracts the EPUB safely, converts images to X4-friendly JPEGs, fixes SVG covers, optionally generates a missing cover, repairs HTML, strips unnecessary attributes, removes unused CSS/fonts, normalizes text and whitespace, cleans store metadata, repairs/generates the TOC, removes OS artifacts, and repackages with the EPUB `mimetype` entry first.

### Examples

```bash
# Standard epubkit optimization
python3 cli/optimize.py book.epub

# Custom output and display size
python3 cli/optimize.py -q 80 -W 600 -H 900 --output ./out book.epub

# Keep the old filename suffix convention
python3 cli/optimize.py --suffix=-optimized book.epub

# Faster cleanup that keeps CSS and embedded fonts
python3 cli/optimize.py --no-remove-css --no-remove-fonts book.epub
```

### Dependencies

- [Pillow](https://python-pillow.org/) - image processing
- [lxml](https://lxml.de/) - XML/HTML parsing and repair
- [cssutils](https://cssutils.readthedocs.io/) - CSS parsing and cleanup
