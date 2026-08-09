#!/usr/bin/env python3
"""Generate and validate deterministic Space Shooter profile assets."""

from __future__ import annotations

import argparse
import random
from pathlib import Path


WIDTH = 860
HEIGHT = 230
FPS = 25
RANDOM_SEED = 9707
WEBP_SOFT_LIMIT = 1_500_000
WEBP_HARD_LIMIT = 3 * 1024 * 1024
PNG_HARD_LIMIT = 1024 * 1024


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--raw-input", type=Path)
    return parser.parse_args()


def _check_webp_signature(path: Path) -> None:
    header = path.read_bytes()[:12]
    if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WEBP":
        raise ValueError(f"{path.name} is not a WebP file")


def _check_png_signature(path: Path) -> None:
    if path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path.name} is not a PNG file")


def validate_webp_and_create_static(webp_path: Path, png_path: Path) -> None:
    from PIL import Image

    if not webp_path.is_file() or webp_path.is_symlink():
        raise ValueError("space-shooter.webp must be a regular file")

    webp_size = webp_path.stat().st_size
    if webp_size == 0 or webp_size > WEBP_HARD_LIMIT:
        raise ValueError(f"space-shooter.webp has invalid size: {webp_size} bytes")
    if webp_size > WEBP_SOFT_LIMIT:
        print(f"warning: space-shooter.webp exceeds the 1.5 MiB target ({webp_size} bytes)")

    _check_webp_signature(webp_path)

    with Image.open(webp_path) as image:
        if image.format != "WEBP":
            raise ValueError(f"unexpected image format: {image.format}")
        if image.size != (WIDTH, HEIGHT):
            raise ValueError(f"unexpected image dimensions: {image.size}")
        if not getattr(image, "is_animated", False):
            raise ValueError("space-shooter.webp is not animated")

        frame_count = getattr(image, "n_frames", 1)
        if frame_count <= 1:
            raise ValueError("space-shooter.webp must contain multiple frames")

        for frame_index in range(frame_count):
            image.seek(frame_index)
            if image.size != (WIDTH, HEIGHT):
                raise ValueError(f"frame {frame_index} has unexpected dimensions: {image.size}")

        image.seek(0)
        image.convert("RGB").save(png_path, format="PNG", optimize=False)

    if not png_path.is_file() or png_path.is_symlink():
        raise ValueError("space-shooter-static.png must be a regular file")
    png_size = png_path.stat().st_size
    if png_size == 0 or png_size > PNG_HARD_LIMIT:
        raise ValueError(f"space-shooter-static.png has invalid size: {png_size} bytes")

    _check_png_signature(png_path)
    with Image.open(png_path) as image:
        if image.format != "PNG" or image.size != (WIDTH, HEIGHT):
            raise ValueError("space-shooter-static.png failed format or dimension validation")
        if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) != 1:
            raise ValueError("space-shooter-static.png must contain exactly one frame")


def render_assets(username: str, output_dir: Path, raw_input: Path | None = None) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    webp_path = output_dir / "space-shooter.webp"
    png_path = output_dir / "space-shooter-static.png"

    random.seed(RANDOM_SEED, version=2)
    from gh_space_shooter.cli import app

    cli_args = [
        username,
        "--output",
        str(webp_path),
        "--strategy",
        "random",
        "--fps",
        str(FPS),
    ]
    if raw_input is not None:
        cli_args.extend(["--raw-input", str(raw_input)])

    app(args=cli_args, prog_name="gh-space-shooter", standalone_mode=False)
    validate_webp_and_create_static(webp_path, png_path)
    return webp_path, png_path


def main() -> None:
    args = _parse_args()
    render_assets(args.username, args.output_dir, args.raw_input)


if __name__ == "__main__":
    main()
