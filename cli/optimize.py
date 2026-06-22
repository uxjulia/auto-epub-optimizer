#!/usr/bin/env python3
"""Command-line wrapper for the epubkit EPUB processing pipeline."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parent / "epubkit_pipeline"
sys.path.insert(0, str(PIPELINE_DIR))

from epub_processor import ProcessingOptions, process_epub  # noqa: E402


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    inputs = resolve_inputs(args.inputs)
    if not inputs:
        print("No EPUB files found.", file=sys.stderr)
        return 1

    output_dir = Path(args.output).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("")
    print("EPUB Optimizer (epubkit pipeline)")
    print(
        "Settings: "
        f"quality={args.quality}% | "
        f"grayscale={args.grayscale} | "
        f"contrast={args.contrast_boost} ({args.contrast_factor}x) | "
        f"4-level={args.eink_quantize} | "
        f"{args.max_width}x{args.max_height} | "
        f"remove_fonts={args.remove_fonts} | "
        f"clean_css={args.remove_css} | "
        f"text_cleanup={args.text_cleanup}"
    )
    print("")

    succeeded = 0
    failed = 0

    for input_path in inputs:
        print(f"  {input_path.name}")

        if input_path.name.lower().endswith(".kepub.epub"):
            print("     Failed: Kobo EPUB files (.kepub.epub) are not supported")
            failed += 1
            continue

        temp_path = make_temp_output(output_dir)
        try:
            options = build_options(args)
            report = process_epub(
                str(input_path),
                str(temp_path),
                options,
                make_progress_callback(args.verbose),
            )

            if not report.success:
                raise RuntimeError(report.error or "processing failed")

            final_name = report.output_filename or f"{input_path.stem}.epub"
            final_name = apply_suffix(final_name, args.suffix)
            final_path = unique_path(output_dir / final_name)
            os.replace(temp_path, final_path)

            ratio = 0.0
            if report.original_size and report.optimized_size:
                ratio = (1 - report.optimized_size / report.original_size) * 100
            sign = "-" if ratio >= 0 else "+"
            print(
                f"     OK: {format_bytes(report.original_size)} -> "
                f"{format_bytes(report.optimized_size)} ({sign}{abs(ratio):.1f}%)"
            )
            print(f"     Wrote: {final_path}")
            if args.verbose:
                print(f"     Summary: {report.summary()}")
            print("")
            succeeded += 1
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink()
            print(f"     Failed: {exc}")
            print("")
            failed += 1

    print(f"Done: {succeeded} succeeded, {failed} failed")
    print(f"Output: {output_dir.resolve()}")
    print("")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Optimize EPUBs using the epubkit Python pipeline.",
    )
    parser.add_argument("inputs", nargs="+", help="EPUB file(s) or directories")
    parser.add_argument("-o", "--output", default="./optimized", help="output directory")
    parser.add_argument("-q", "--quality", type=bounded_int(1, 100), default=70, help="JPEG quality 1-100")
    parser.add_argument("--no-grayscale", dest="grayscale", action="store_false", help="disable grayscale conversion")
    parser.add_argument("--contrast", dest="contrast_boost", action="store_true", help="enable contrast boost")
    parser.add_argument(
        "-c",
        "--contrast-factor",
        dest="contrast_factor",
        type=float,
        default=1.0,
        help="contrast multiplier used with --contrast, e.g. 1.2 or 1.5",
    )
    parser.add_argument("--no-eink-quantize", dest="eink_quantize", action="store_false", help="disable 4-level e-ink quantization")
    parser.add_argument("-W", "--max-width", type=int, default=800, help="maximum image width in px")
    parser.add_argument("-H", "--max-height", type=int, default=480, help="maximum image height in px")
    parser.add_argument(
        "--split",
        choices=("none", "h-split", "v-split"),
        default="none",
        help="compatibility flag; h-split/v-split enable epubkit light novel mode",
    )
    parser.add_argument("--light-novel", action="store_true", help="rotate/split landscape light-novel images")
    parser.add_argument("--rotate-right", action="store_true", help="rotate light-novel images right instead of left")
    parser.add_argument("--no-remove-fonts", dest="remove_fonts", action="store_false", help="keep embedded fonts")
    parser.add_argument("--no-remove-css", dest="remove_css", action="store_false", help="keep unused CSS")
    parser.add_argument("--no-generate-cover", dest="generate_cover", action="store_false", help="do not generate a missing cover")
    parser.add_argument("--no-clean-metadata", dest="clean_metadata", action="store_false", help="keep store-specific metadata")
    parser.add_argument("--no-text-cleanup", dest="text_cleanup", action="store_false", help="disable text cleanup")
    parser.add_argument("--normalize-quotes", dest="normalize_quotes", action="store_true", help="normalize curly quotes to straight quotes")
    parser.add_argument("--keep-quotes", dest="normalize_quotes", action="store_false", help="keep curly quotes unchanged")
    parser.add_argument("--normalize-dashes", dest="normalize_dashes", action="store_true", help="normalize em/en dashes to ASCII dashes")
    parser.add_argument("--keep-dashes", dest="normalize_dashes", action="store_false", help="keep em/en dashes unchanged")
    parser.add_argument("--no-normalize-ellipsis", dest="normalize_ellipsis", action="store_false", help="keep ellipsis characters unchanged")
    parser.add_argument(
        "--split-long-sections",
        action="store_true",
        help="split oversized XHTML spine items into smaller EPUB sections",
    )
    parser.add_argument(
        "--section-split-word-threshold",
        type=int,
        default=2000,
        help="visible word threshold for --split-long-sections",
    )
    parser.add_argument(
        "--filename-format",
        choices=("author-title", "title-author", "title"),
        default="author-title",
        help="output filename format derived from EPUB metadata",
    )
    parser.add_argument("--suffix", default="", help="suffix to append before .epub")
    parser.add_argument("-v", "--verbose", action="store_true", help="print progress and detailed summary")
    parser.add_argument(
        "-n",
        "--normalize",
        action="store_true",
        help="accepted for compatibility; epubkit already auto-normalizes grayscale contrast",
    )
    parser.set_defaults(
        grayscale=True,
        contrast_boost=False,
        eink_quantize=True,
        remove_fonts=True,
        remove_css=True,
        generate_cover=True,
        clean_metadata=True,
        text_cleanup=True,
        normalize_quotes=False,
        normalize_dashes=False,
        normalize_ellipsis=True,
    )
    return parser


def build_options(args: argparse.Namespace) -> ProcessingOptions:
    return ProcessingOptions(
        grayscale=args.grayscale,
        contrast_boost=args.contrast_boost,
        contrast_factor=args.contrast_factor,
        quality=args.quality,
        max_width=args.max_width,
        max_height=args.max_height,
        eink_quantize=args.eink_quantize,
        remove_fonts=args.remove_fonts,
        remove_unused_css=args.remove_css,
        light_novel_mode=args.light_novel or args.split != "none",
        light_novel_rotate_left=not args.rotate_right,
        generate_missing_cover=args.generate_cover,
        clean_metadata=args.clean_metadata,
        text_cleanup=args.text_cleanup,
        normalize_quotes=args.normalize_quotes,
        normalize_dashes=args.normalize_dashes,
        normalize_ellipsis=args.normalize_ellipsis,
        split_long_sections=args.split_long_sections,
        section_split_word_threshold=args.section_split_word_threshold,
        filename_format=args.filename_format,
    )


def resolve_inputs(raw_inputs: list[str]) -> list[Path]:
    epubs: list[Path] = []
    for raw in raw_inputs:
        path = Path(raw).expanduser()
        if not path.exists():
            print(f"Not found: {path}", file=sys.stderr)
            continue
        if path.is_dir():
            epubs.extend(sorted(p for p in path.iterdir() if p.name.lower().endswith(".epub")))
        elif path.name.lower().endswith(".epub"):
            epubs.append(path)
        else:
            print(f"Skipping non-EPUB file: {path}", file=sys.stderr)
    return epubs


def make_temp_output(output_dir: Path) -> Path:
    handle = tempfile.NamedTemporaryFile(prefix=".epubkit-", suffix=".epub", dir=output_dir, delete=False)
    handle.close()
    return Path(handle.name)


def make_progress_callback(verbose: bool):
    if not verbose:
        return None

    def progress(percent: int, message: str) -> None:
        print(f"     [{percent:3d}%] {message}")

    return progress


def apply_suffix(filename: str, suffix: str) -> str:
    if not suffix:
        return filename
    path = Path(filename)
    return f"{path.stem}{suffix}{path.suffix or '.epub'}"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not find an unused output name for {path.name}")


def format_bytes(size: int) -> str:
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def bounded_int(min_value: int, max_value: int):
    def parse(value: str) -> int:
        parsed = int(value)
        if parsed < min_value or parsed > max_value:
            raise argparse.ArgumentTypeError(f"must be between {min_value} and {max_value}")
        return parsed

    return parse


if __name__ == "__main__":
    raise SystemExit(main())
