#!/usr/bin/env python3
"""Generate and validate the branded Dev Patel Space Shooter assets."""

from __future__ import annotations

import argparse
import json
import os
import random
from collections.abc import Iterator, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

WIDTH = 860
HEIGHT = 230
FPS = 15
FRAME_DURATION_MS = 1000 // FPS
RANDOM_SEED = 9707
WEBP_QUALITY = 82
WEBP_SOFT_LIMIT = 1_500_000
WEBP_HARD_LIMIT = 3 * 1024 * 1024
PNG_HARD_LIMIT = 1024 * 1024

CALENDAR_WEEKS = 52
CALENDAR_DAYS = 7
CELL_SIZE = 12
CELL_SPACING = 3
CELL_STEP = CELL_SIZE + CELL_SPACING
PADDING = 40
SHIP_TOP = 186
SHIP_SIZE = 32
UNITY_LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "unity-logo.png"

HOLD_FRAMES = 18
MOVE_FRAMES = 1
BULLET_FRAMES = 3
EXPLOSION_FRAMES = 1
RESPAWN_FRAMES = 12

BACKGROUND = (13, 17, 23)
CYAN = (34, 211, 238)
PURPLE = (167, 139, 250)
BULLET_COLOR = (255, 223, 0)
GITHUB_GREENS = (
    (14, 68, 41),
    (0, 109, 50),
    (38, 166, 65),
    (57, 211, 83),
    (87, 242, 135),
)
EXPECTED_ASSET_NAMES = {"space-shooter.webp", "space-shooter-static.png"}

WORD = "DEV PATEL"
PIXEL_FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
}

def _build_word_columns(text: str = WORD) -> tuple[tuple[int, ...], ...]:
    columns: list[tuple[int, ...]] = []
    for character in text:
        if character == " ":
            columns.extend([(0,) * CALENDAR_DAYS] * 2)
            continue

        glyph = PIXEL_FONT[character]
        for x in range(5):
            columns.append(tuple(int(glyph[y][x]) for y in range(CALENDAR_DAYS)))
        columns.append((0,) * CALENDAR_DAYS)

    return tuple(columns[:-1])


WORD_COLUMNS = _build_word_columns()
WORD_START_COLUMN = (CALENDAR_WEEKS - len(WORD_COLUMNS)) // 2
WORD_COLUMN_BY_X = {
    WORD_START_COLUMN + index: column for index, column in enumerate(WORD_COLUMNS)
}
OCCUPIED_COLUMNS = tuple(x for x, column in WORD_COLUMN_BY_X.items() if any(column))
WORD_BLOCKS = tuple(
    (x, row)
    for x, column in WORD_COLUMN_BY_X.items()
    for row, enabled in enumerate(column)
    if enabled
)
WORD_BLOCK_COUNT = sum(sum(column) for column in WORD_COLUMNS)

if len(WORD_COLUMNS) != 49 or len(OCCUPIED_COLUMNS) != 40 or WORD_BLOCK_COUNT != 122:
    raise RuntimeError("DEV PATEL pixel-font contract changed unexpectedly")


@lru_cache(maxsize=1)
def _unity_logo() -> Any:
    """Load the profile's crisp Unity badge once for deterministic compositing."""
    from PIL import Image

    with Image.open(UNITY_LOGO_PATH) as source:
        if source.format != "PNG" or source.size != (64, 64):
            raise ValueError("Unity logo must be a 64x64 PNG")
        return source.convert("RGBA").resize(
            (SHIP_SIZE, SHIP_SIZE), Image.Resampling.LANCZOS
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--raw-input", type=Path)
    return parser.parse_args()


def _blank_week() -> dict[str, list[dict[str, int]]]:
    return {"days": [{"count": 0, "level": 0} for _ in range(CALENDAR_DAYS)]}


def weekly_contribution_levels(data: dict[str, Any]) -> tuple[int, ...]:
    raw_weeks = list(data.get("weeks", []))[-CALENDAR_WEEKS:]
    weeks = [_blank_week() for _ in range(CALENDAR_WEEKS - len(raw_weeks))] + raw_weeks
    levels: list[int] = []

    for week in weeks:
        days = week.get("days", []) if isinstance(week, dict) else []
        day_levels = [int(day.get("level", 0)) for day in days if isinstance(day, dict)]
        level = max(day_levels, default=0)
        if not 0 <= level <= 4:
            raise ValueError(f"contribution level must be between 0 and 4, got {level}")
        levels.append(level)

    return tuple(levels)


def week_groups_for_word_columns() -> tuple[tuple[int, ...], ...]:
    groups: list[tuple[int, ...]] = []
    occupied_count = len(OCCUPIED_COLUMNS)
    for index in range(occupied_count):
        start = index * CALENDAR_WEEKS // occupied_count
        end = (index + 1) * CALENDAR_WEEKS // occupied_count
        groups.append(tuple(range(start, end)))
    return tuple(groups)


def contribution_levels_by_column(data: dict[str, Any]) -> dict[int, int]:
    weekly_levels = weekly_contribution_levels(data)
    groups = week_groups_for_word_columns()
    return {
        column: max(weekly_levels[index] for index in group)
        for column, group in zip(OCCUPIED_COLUMNS, groups, strict=True)
    }


def load_contribution_data(username: str, raw_input: Path | None = None) -> dict[str, Any]:
    if raw_input is not None:
        data = json.loads(raw_input.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("raw contribution input must be a JSON object")
        return data

    token = os.environ.get("GH_TOKEN")
    if not token:
        raise ValueError("GH_TOKEN is required when --raw-input is not provided")

    from gh_space_shooter.github_client import GitHubClient

    with GitHubClient(token) as client:
        return client.get_contribution_graph(username)


def build_attack_order(
    blocks: Sequence[tuple[int, int]] | None = None, seed: int = RANDOM_SEED
) -> tuple[tuple[int, int], ...]:
    remaining = set(WORD_BLOCKS if blocks is None else blocks)
    current_x = 25
    order: list[tuple[int, int]] = []
    rng = random.Random(seed)

    while remaining:
        columns = {column for column, _ in remaining}
        candidates = sorted(columns, key=lambda x: (abs(x - current_x), x))[:8]
        weights = []
        for candidate in candidates:
            distance = abs(candidate - current_x)
            if distance == 0:
                weights.append(10)
            elif distance <= 3:
                weights.append(100)
            else:
                weights.append(1)
        target = rng.choices(candidates, weights=weights, k=1)[0]
        target_row = max(row for column, row in remaining if column == target)
        target_block = (target, target_row)
        order.append(target_block)
        remaining.remove(target_block)
        current_x = target

    return tuple(order)


def expected_frame_count() -> int:
    attack_frames = MOVE_FRAMES + BULLET_FRAMES + EXPLOSION_FRAMES
    return HOLD_FRAMES + WORD_BLOCK_COUNT * attack_frames + RESPAWN_FRAMES


def expected_duration_ms() -> int:
    return expected_frame_count() * FRAME_DURATION_MS


def _lerp(first: float, second: float, amount: float) -> float:
    return first + (second - first) * amount


def _ease(amount: float) -> float:
    return amount * amount * (3 - 2 * amount)


def _blend(first: tuple[int, int, int], second: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    amount = max(0.0, min(1.0, amount))
    return tuple(round(_lerp(a, b, amount)) for a, b in zip(first, second, strict=True))


def _column_color(column: int, level: int, visibility: float = 1.0) -> tuple[int, int, int]:
    del column
    return _blend(BACKGROUND, GITHUB_GREENS[level], visibility)


def _cell_position(column: int, row: int) -> tuple[int, int]:
    return PADDING + column * CELL_STEP, PADDING + row * CELL_STEP


def _column_center(column: float) -> float:
    return PADDING + column * CELL_STEP + CELL_SIZE / 2


def _build_starfield() -> tuple[tuple[int, int, int], ...]:
    rng = random.Random(RANDOM_SEED)
    return tuple(
        (rng.randrange(WIDTH), rng.randrange(HEIGHT), rng.choice((55, 75, 105, 145, 205)))
        for _ in range(120)
    )


STARFIELD = _build_starfield()


def _draw_starfield(draw: Any) -> None:
    for x, y, brightness in STARFIELD:
        draw.point((x, y), fill=(brightness, brightness, brightness))


def _draw_word(
    draw: Any,
    levels: dict[int, int],
    live_blocks: set[tuple[int, int]],
    visibility: float = 1.0,
) -> None:
    for column, row in sorted(live_blocks):
        level = levels[column]
        color = _column_color(column, level, visibility)
        x, y = _cell_position(column, row)
        draw.rounded_rectangle(
            (x, y, x + CELL_SIZE, y + CELL_SIZE), radius=2, fill=color
        )
        if level > 0 and visibility > 0.55:
            highlight = _blend(color, (255, 255, 255), 0.18)
            draw.line((x + 2, y + 1, x + CELL_SIZE - 2, y + 1), fill=highlight)


def _draw_unity_ship(image: Any, draw: Any, center_x: float) -> None:
    left = round(center_x - SHIP_SIZE / 2)
    center = round(center_x)
    for thruster_center in (center - 6, center + 6):
        draw.polygon(
            (
                (thruster_center - 4, SHIP_TOP + SHIP_SIZE),
                (thruster_center + 4, SHIP_TOP + SHIP_SIZE),
                (thruster_center, HEIGHT - 1),
            ),
            fill=PURPLE,
        )
    logo = _unity_logo()
    image.paste(logo, (left, SHIP_TOP), logo)


def _draw_bullet(draw: Any, column: int, row: int, phase: int) -> None:
    center = round(_column_center(column))
    _, block_y = _cell_position(column, row)
    target_y = block_y + CELL_SIZE // 2
    progress = _ease((phase + 1) / BULLET_FRAMES)
    bullet_y = round(_lerp(SHIP_TOP, target_y, progress))
    draw.rounded_rectangle(
        (center - 2, bullet_y - 5, center + 2, bullet_y + 2),
        radius=2,
        fill=BULLET_COLOR,
    )
    trail_color = _blend(BACKGROUND, BULLET_COLOR, 0.45)
    draw.line((center, bullet_y + 3, center, bullet_y + 10), fill=trail_color, width=2)


def _draw_explosion(draw: Any, column: int, row: int, level: int, phase: int) -> None:
    color = _blend(_column_color(column, level), (255, 255, 255), 0.30)
    directions = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1))
    radius = 4 + phase * 3
    x, y = _cell_position(column, row)
    center_x = x + CELL_SIZE // 2
    center_y = y + CELL_SIZE // 2
    for dx, dy in directions:
        particle_x = center_x + dx * radius
        particle_y = center_y + dy * radius
        draw.rectangle(
            (particle_x - 1, particle_y - 1, particle_x + 1, particle_y + 1),
            fill=color,
        )


def render_frame(
    levels: dict[int, int],
    live_blocks: set[tuple[int, int]],
    ship_center_x: float,
    *,
    bullet: tuple[int, int, int] | None = None,
    explosion: tuple[int, int, int] | None = None,
    visibility: float = 1.0,
) -> Any:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    _draw_starfield(draw)
    _draw_word(draw, levels, live_blocks, visibility)
    if bullet is not None:
        column, row, phase = bullet
        _draw_bullet(draw, column, row, phase)
    if explosion is not None:
        column, row, phase = explosion
        _draw_explosion(draw, column, row, levels[column], phase)
    _draw_unity_ship(image, draw, ship_center_x)
    return image


def generate_frames(levels: dict[int, int]) -> Iterator[Any]:
    live_blocks = set(WORD_BLOCKS)
    initial_ship_x = _column_center(25)
    ship_x = initial_ship_x

    for _ in range(HOLD_FRAMES):
        yield render_frame(levels, live_blocks, ship_x)

    for target_column, target_row in build_attack_order():
        target_x = _column_center(target_column)
        start_x = ship_x
        for frame in range(MOVE_FRAMES):
            progress = _ease((frame + 1) / MOVE_FRAMES)
            ship_x = _lerp(start_x, target_x, progress)
            yield render_frame(levels, live_blocks, ship_x)

        for phase in range(BULLET_FRAMES):
            yield render_frame(
                levels,
                live_blocks,
                target_x,
                bullet=(target_column, target_row, phase),
            )

        live_blocks.remove((target_column, target_row))
        for phase in range(EXPLOSION_FRAMES):
            yield render_frame(
                levels,
                live_blocks,
                target_x,
                explosion=(target_column, target_row, phase),
            )

        ship_x = target_x

    all_blocks = set(WORD_BLOCKS)
    for frame in range(RESPAWN_FRAMES):
        progress = _ease((frame + 1) / RESPAWN_FRAMES)
        return_x = _lerp(ship_x, initial_ship_x, progress)
        yield render_frame(
            levels, all_blocks, return_x, visibility=(frame + 1) / RESPAWN_FRAMES
        )


def encode_webp(frames: Sequence[Any], path: Path) -> None:
    if len(frames) != expected_frame_count():
        raise ValueError(f"unexpected frame count: {len(frames)}")
    if frames[0].tobytes() != frames[-1].tobytes():
        raise ValueError("final frame must match the opening frame for a seamless loop")

    frames[0].save(
        path,
        format="WEBP",
        save_all=True,
        append_images=list(frames[1:]),
        duration=FRAME_DURATION_MS,
        loop=0,
        lossless=False,
        quality=WEBP_QUALITY,
        method=6,
    )


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


def validate_asset_file_set(output_dir: Path) -> None:
    entries = list(output_dir.iterdir())
    if {entry.name for entry in entries} != EXPECTED_ASSET_NAMES:
        raise ValueError("profile asset directory must contain exactly the expected filenames")
    for entry in entries:
        if not entry.is_file() or entry.is_symlink():
            raise ValueError(f"{entry.name} must be a regular file")


def render_assets(
    username: str, output_dir: Path, raw_input: Path | None = None
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    webp_path = output_dir / "space-shooter.webp"
    png_path = output_dir / "space-shooter-static.png"

    data = load_contribution_data(username, raw_input)
    levels = contribution_levels_by_column(data)
    frames = list(generate_frames(levels))
    encode_webp(frames, webp_path)
    validate_webp_and_create_static(webp_path, png_path)
    validate_asset_file_set(output_dir)
    return webp_path, png_path


def main() -> None:
    args = _parse_args()
    render_assets(args.username, args.output_dir, args.raw_input)


if __name__ == "__main__":
    main()
