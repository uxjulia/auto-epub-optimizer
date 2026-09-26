# <div align="center">Automated EPUB Optimizer Workflow</div>

**<div align="center">Drop EPUB into folder → Automatically gets optimized → File is moved to your library</div>**<br/>

Optimizes EPUB files for e-readers like the Xteink X3/X4 using a modified Python pipeline from [epubkit](https://github.com/b1rdmania/epubkit). It converts images, including SVG resources, to baseline JPEG, applies 4-level grayscale, repairs EPUB structure, strips embedded fonts, removes unused CSS, flattens CrossInk-supported stylesheet rules into XHTML, cleans metadata/text, fixes TOCs, handles SVG covers, and repackages the EPUB correctly.

Use it in three ways:

1. Automatically with a watcher via Docker Compose or Systemd
2. Manually by running the Python CLI (`cli/optimize.py`)
3. Manually via the browser-based GUI (`browser/index.html`), no install required

## Features

- Drop an `.epub` into one folder and have it appear in two separately managed libraries automatically
- The original is copied to your Calibre watch folder and handled from there as normal
- A grayscale-optimized copy is written to a separate library, ready to serve via OPDS
- Optional second drop folder supported for "optimize only" runs that skip the Calibre copy
- Single-library mode also supported: leave `CALIBRE_WATCH_FOLDER` unset and only the optimized copy is produced
- Uses the full `epubkit` cleanup pipeline, not only image conversion
- Writes CrossInk word-based location metadata into optimized EPUBs for future stable reading-position support
- Flattens CrossInk-supported CSS into inline XHTML styles so low-power devices do less stylesheet parsing

# Usage/Installation

There are four ways to install or use this workflow:

1. [Docker](#docker-compose)
2. [Systemd](#systemd-automated-watcher-linux--wsl2)
3. [Manually via your local Browser](#browser-no-install-required)
4. [Manually via CLI](#cli)

> Note: The default settings are for the XTEINK X4's 800x480 image bounds. For another device, set `EPUB_MAX_WIDTH` and `EPUB_MAX_HEIGHT` in your config or pass `-W`/`-H` to `cli/optimize.py`.

## Docker Compose

The repo includes a `docker-compose.yml` that runs the automated pipeline without installing Python dependencies or `inotify-tools` on the host.

### Setup

```bash
cp .env.example .env
# Edit .env - set BOOKDROP_DIR, WATCHER_DEST_DIR, and optionally CALIBRE_WATCH_FOLDER
```

The containers use fixed internal paths (`/bookdrop`, `/output`, `/destination`, `/calibre`). You only need to set the host-side paths in `.env`. `EPUB_OUTPUT_DIR` is handled internally via a shared Docker volume between the two services.

#### Why two services?

The optimizer writes finished EPUBs to an intermediate Docker volume (`output`), and the watcher publishes them from there to `WATCHER_DEST_DIR`. This split exists because `inotify` is unreliable on Windows NTFS paths like `/mnt/c/...` inside Docker on WSL2. Keeping the handoff point on a Linux volume makes the watcher reliable.

For Windows-backed destinations, the watcher now stages each file under a temporary non-`.epub` name inside `WATCHER_DEST_DIR` and then renames it into place. That is the same pattern many Node apps use for "write temp file, then swap live", and it helps Windows-side folder watchers notice the finished book more consistently than a direct cross-filesystem move.

If your `WATCHER_DEST_DIR` is a plain Linux path, you can remove the `epub-watcher` service and point `EPUB_OUTPUT_DIR` directly at the destination.

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

### Apply changes

If you change Python code, shell scripts, Dockerfiles, or `docker-compose.yml`, rebuild and recreate the containers:

```bash
docker compose up -d --build
```

If you only change `.env`, re-apply the Compose config:

```bash
docker compose up -d
```

If you want a completely fresh restart:

```bash
docker compose down
docker compose up -d --build
```

## Systemd Automated Watcher (Linux / WSL2)

The `scripts/` folder contains two systemd user services that build a fully automated pipeline:

```
BOOKDROP_DIR  →[epub-optimizer]→  EPUB_OUTPUT_DIR  →[epub-watcher]→  WATCHER_DEST_DIR
```

- **epub-optimizer** - polls a bookdrop folder for `.epub` files, runs `optimize.py` on each, and writes the result to an output folder. Uses polling instead of `inotify` so it works on Windows NTFS mounts (`/mnt/c/`) under WSL2.
- **epub-watcher** - watches the output folder with `inotifywait` and publishes finished files to a final destination (e.g. a Calibre/OPDS library folder) using a temp-name-then-rename handoff that is friendlier to Windows watchers.

### 1. Configure

Copy the example config and fill in your paths:

```bash
mkdir -p ~/.config/epub-optimizer
cp .env.example ~/.config/epub-optimizer/.env
```

Edit `~/.config/epub-optimizer/.env`:

For switch variables below, set `1` to enable them or leave them unset to keep the CLI default. A nonempty value such as `0` also enables a switch. `EPUB_SPLIT_LONG_SECTIONS=0` is the exception: it disables splitting.

| Variable                             | Description                                                                                                                        |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| `BOOKDROP_DIR`                       | Drop `.epub` files here to trigger processing                                                                                      |
| `OPTIMIZE_ONLY_DIR`                  | Optional second drop folder; files placed here skip the Calibre copy step and only go through optimization                         |
| `CALIBRE_WATCH_FOLDER`               | Optional - Calibre watch folder; files are copied here before optimization (for use when you want a separate workflow for Calibre) |
| `OPTIMIZER_PYTHON`                   | Python executable used to run the optimizer, e.g. `python3` or a virtualenv path                                                   |
| `OPTIMIZER_SCRIPT`                   | Absolute path to `cli/optimize.py` in this repo                                                                                    |
| `EPUB_OUTPUT_DIR`                    | Where the optimizer writes finished EPUBs                                                                                          |
| `WATCHER_DEST_DIR`                   | Where the watcher publishes finished EPUBs (your final X4 library folder)                                                          |
| `OPTIMIZER_LOG_FILE`                 | Log path for the optimizer service (default: `~/.local/log/epub-optimizer.log`)                                                    |
| `WATCHER_LOG_FILE`                   | Log path for the watcher service (default: `~/.local/log/epub-watcher.log`)                                                        |
| `POLL_INTERVAL`                      | Seconds between bookdrop scans (default: `5`)                                                                                      |
| `KEEP_DAYS`                          | Days to keep files in `bookdrop/processed/` before auto-deletion (default: `5`)                                                    |
| `EPUB_QUALITY`                       | Optional JPEG quality, default `70`                                                                                                |
| `EPUB_MAX_WIDTH`                     | Optional max image width, default `800`                                                                                            |
| `EPUB_MAX_HEIGHT`                    | Optional max image height, default `480`                                                                                           |
| `EPUB_CONTRAST`                      | Optional - set to `1` to enable contrast boost                                                                                     |
| `EPUB_NO_CONTRAST`                   | Disable contrast boost, overriding `EPUB_CONTRAST`                                                                                 |
| `EPUB_CONTRAST_FACTOR`               | Optional contrast multiplier used when contrast boost is enabled, default `1.0`                                                    |
| `EPUB_NO_GRAYSCALE`                  | Disable grayscale conversion                                                                                                       |
| `EPUB_NO_EINK_QUANTIZE`              | Disable 4-level e-ink quantization                                                                                                 |
| `EPUB_LIGHT_NOVEL`                   | Optional - set to `1` to rotate/split landscape light-novel images                                                                 |
| `EPUB_SPLIT_MODE`                    | Compatibility mode: `none`, `h-split`, or `v-split`; either split value enables light-novel mode                                    |
| `EPUB_ROTATE_RIGHT`                  | Rotate light-novel images right instead of left                                                                                    |
| `EPUB_PRESERVE_COVER_COLOR`          | Optional - set to `1` to keep the cover in color; covers are grayscale by default                                                  |
| `EPUB_GRAYSCALE_COVER`               | Convert the cover to grayscale; overrides `EPUB_PRESERVE_COVER_COLOR`                                                               |
| `EPUB_NO_GENERATE_COVER`             | Do not generate missing cover art                                                                                                  |
| `EPUB_NO_REMOVE_FONTS`               | Keep embedded fonts                                                                                                                |
| `EPUB_NO_REMOVE_CSS`                 | Keep unused CSS                                                                                                                    |
| `EPUB_NO_CLEAN_METADATA`             | Keep store metadata, including Calibre series information                                                                         |
| `EPUB_NO_TEXT_CLEANUP`               | Disable text cleanup                                                                                                               |
| `EPUB_NORMALIZE_QUOTES`              | Convert curly quotes to straight quotes                                                                                            |
| `EPUB_KEEP_QUOTES`                   | Leave curly quotes unchanged; overrides `EPUB_NORMALIZE_QUOTES`                                                                    |
| `EPUB_NORMALIZE_DASHES`              | Convert em/en dashes to ASCII dashes                                                                                                |
| `EPUB_KEEP_DASHES`                   | Leave em/en dashes unchanged; overrides `EPUB_NORMALIZE_DASHES`                                                                    |
| `EPUB_NO_NORMALIZE_ELLIPSIS`         | Keep ellipsis characters unchanged                                                                                                 |
| `EPUB_CHARACTERS_PER_REFERENCE_PAGE` | Optional character count used for generated CrossInk reference pages, default `1500`                                               |
| `EPUB_SPLIT_LONG_SECTIONS`           | Set to `0` to disable splitting oversized XHTML sections                                                                          |
| `EPUB_SECTION_SPLIT_WORD_THRESHOLD` | Secondary visible-word safeguard for section splitting                                                                            |
| `EPUB_SECTION_SPLIT_BYTE_THRESHOLD` | Target uncompressed HTML size for split sections                                                                                   |
| `EPUB_SECTION_SPLIT_HARD_BYTE_LIMIT` | Safe-boundary maximum for split sections                                                                                            |
| `EPUB_FILENAME_FORMAT`               | Optional output name pattern: `author-title`, `title-author`, or `title`                                                           |
| `EPUB_SUFFIX`                        | Optional suffix appended before `.epub`, e.g. `-optimized`                                                                         |
| `EPUB_VERBOSE`                       | Print progress and detailed summaries in the optimizer log                                                                        |

To preserve Calibre series metadata in watcher output, add `EPUB_NO_CLEAN_METADATA=1` to your `.env`.

### 2. Install

Install the watcher first. `epub-optimizer.service` has `After=epub-watcher.service` in its unit file, so systemd expects the watcher unit to exist before the optimizer is registered.

```bash
# Step 1: watcher (publishes optimized files to their final destination)
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

Drop any `.epub` file into your `BOOKDROP_DIR`. The optimizer picks it up within `POLL_INTERVAL` seconds, copies the original to Calibre if configured, processes it, and the watcher publishes the result to `WATCHER_DEST_DIR`.

If you set `OPTIMIZE_ONLY_DIR`, files dropped there go through the same optimization flow but skip the Calibre copy entirely. This is useful for books that are already in your Calibre library and only need an optimized X4 copy.

Inside each configured drop folder you'll find three subfolders that track state:

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

### Apply changes

What you need to do depends on what changed:

- If you changed `cli/optimize.py` or files in `cli/epubkit_pipeline/`, restart the services so they pick up the updated repo code.
- If you changed `~/.config/epub-optimizer/.env`, restart the services so they reload the config.
- If you changed files in `scripts/` such as `epub-optimizer.sh`, `epub-watcher.sh`, `load-env.sh`, or either `.service` file, re-run the installers so the copies in `~/.local/bin/` and `~/.config/systemd/user/` are updated.

For code or config changes only:

```bash
systemctl --user restart epub-optimizer epub-watcher
```

For script or service-unit changes:

```bash
./scripts/install-epub-watcher.sh
./scripts/install-epub-optimizer.sh
```

Those installer scripts will copy the updated files, run `systemctl --user daemon-reload`, and restart the services for you.

---

## Browser (no install required)

Open `browser/index.html` directly in a browser. Everything runs locally, no files leave your machine.

This browser page uses the older JavaScript-only optimizer. The automated watcher, Docker image, and Python CLI use the newer `epubkit` pipeline.

1. Drop one or more `.epub` files onto the drop zone (or click to select)
2. Adjust settings if needed
3. Click **Optimize & Download**

Main browser settings: JPEG quality, reference-page word count, max width/height, split mode, overlap, rotation, and grayscale. Cover contrast enhancement runs automatically.

---

## CLI

### Setup

```bash
# Debian/Ubuntu/WSL
sudo apt-get install -y libcairo2

# macOS
brew install cairo

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Usage

```bash
python3 cli/optimize.py [options] <input.epub ...>
python3 cli/optimize.py [options] <directory>
```

The output filename may be normalized from the EPUB's internal metadata or title, so it will not always exactly match the input basename.

### Options

| Flag                                      | Default        | Description                                                 |
| ----------------------------------------- | -------------- | ----------------------------------------------------------- |
| `-o, --output <dir>`                      | `./optimized`  | Output directory                                            |
| `-q, --quality <n>`                       | `70`           | JPEG quality (1-100)                                        |
| `--no-grayscale`                          | -              | Disable grayscale conversion                                |
| `--preserve-cover-color`                  | -              | Keep the cover image in color                               |
| `--grayscale-cover`                       | default        | Convert the cover image to grayscale                        |
| `--contrast`                              | -              | Enable contrast boost                                       |
| `--no-contrast`                           | default        | Disable contrast boost                                      |
| `-c, --contrast-factor <n>`               | `1.0`          | Contrast multiplier used with `--contrast`                  |
| `--no-eink-quantize`                      | -              | Disable 4-level e-ink quantization                          |
| `-W, --max-width <n>`                     | `800`          | Max image width in px                                       |
| `-H, --max-height <n>`                    | `480`          | Max image height in px                                      |
| `--split <mode>`                          | `none`         | Compatibility mode; `h-split` or `v-split` enables light-novel mode |
| `--light-novel`                           | -              | Rotate/split landscape light-novel images                   |
| `--rotate-right`                          | -              | Rotate light-novel images right instead of left             |
| `--no-remove-fonts`                       | -              | Keep embedded fonts                                         |
| `--no-remove-css`                         | -              | Keep unused CSS                                             |
| `--no-generate-cover`                     | -              | Do not generate missing cover art                           |
| `--no-clean-metadata`                     | -              | Keep store-specific metadata                                |
| `--no-text-cleanup`                       | -              | Disable text cleanup                                        |
| `--normalize-quotes`                      | -              | Convert curly quotes to straight quotes                     |
| `--keep-quotes`                           | default        | Leave curly quotes unchanged                                |
| `--normalize-dashes`                      | -              | Convert em/en dashes to ASCII dashes                        |
| `--keep-dashes`                           | default        | Leave em/en dashes unchanged                                |
| `--no-normalize-ellipsis`                 | -              | Keep ellipsis characters unchanged                          |
| `--characters-per-reference-page <chars>` | `1500`         | Character count used for generated CrossInk reference pages |
| `--no-split-long-sections`                | -              | Do not split oversized XHTML sections                       |
| `--section-split-word-threshold <n>`      | `8000`         | Secondary word limit for section splitting                  |
| `--section-split-byte-threshold <n>`      | `32768`        | Target uncompressed size of split sections                  |
| `--section-split-hard-byte-limit <n>`     | `49152`        | Maximum size at a safe split boundary                       |
| `--filename-format`                       | `author-title` | Output filename pattern from metadata                       |
| `--suffix <str>`                          | empty          | Suffix appended to output filename                          |
| `-v, --verbose`                           | -              | Print progress and summary details                          |
| `--help`                                  | -              | Show help                                                   |

### Pipeline

The Python CLI uses the copied `epubkit` pipeline in `cli/epubkit_pipeline/`. It checks for DRM, extracts the EPUB safely, converts raster and SVG images to X4-friendly JPEGs, fixes SVG covers, optionally generates a missing cover, repairs HTML, strips unnecessary attributes, removes unused CSS/fonts, normalizes text and whitespace, optionally cleans store metadata, repairs or generates the TOC, removes OS artifacts, and repackages with the EPUB `mimetype` entry first.

### Examples

```bash
# Standard epubkit optimization
python3 cli/optimize.py book.epub

# Custom output and display size
python3 cli/optimize.py -q 80 -W 600 -H 900 --output ./out book.epub

# Keep the old filename suffix convention
python3 cli/optimize.py --suffix=-optimized book.epub

# Name outputs as "Title - Author"
python3 cli/optimize.py --filename-format=title-author book.epub

# Faster cleanup that keeps CSS and embedded fonts
python3 cli/optimize.py --no-remove-css --no-remove-fonts book.epub

```
