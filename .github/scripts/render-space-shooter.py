#!/usr/bin/env python3
"""Generate and validate the branded Dev Patel Space Shooter assets."""

from __future__ import annotations

import argparse
import json
import os
import random
from collections.abc import Iterator, Sequence
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
SHIP_TOP = 190
SHIP_SIZE = 32

HOLD_FRAMES = 18
MOVE_FRAMES = 2
BEAM_FRAMES = 2
EXPLOSION_FRAMES = 2
RESPAWN_FRAMES = 12

BACKGROUND = (13, 17, 23)
CYAN = (34, 211, 238)
PURPLE = (167, 139, 250)
BRIGHTNESS = (0.50, 0.65, 0.78, 0.90, 1.00)
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

# A deliberately small, code-native pixel interpretation of the Unity mark.
UNITY_MASK = (
    "...###.###......",
    "...###.###......",
    "######...####...",
    "####......#####.",
    "####......#####.",
    "######.########.",
    "#...######..###.",
    "#...######..###.",
    "#.....#.....###.",
    "#.....#.....###.",
    "#.....#......##.",
    ".###..#...##....",
    ".###..#...##....",
    ".###########....",
    "....#####.......",
    "....#####.......",
)


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
WORD_BLOCK_COUNT = sum(sum(column) for column in WORD_COLUMNS)

if len(WORD_COLUMNS) != 49 or len(OCCUPIED_COLUMNS) != 40 or WORD_BLOCK_COUNT != 122:
    raise RuntimeError("DEV PATEL pixel-font contract changed unexpectedly")
if any(len(row) != 16 for row in UNITY_MASK) or len(UNITY_MASK) != 16:
    raise RuntimeError("Unity pixel mask must be exactly 16x16")


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
    columns: Sequence[int] | None = None, seed: int = RANDOM_SEED
) -> tuple[int, ...]:
    remaining = set(OCCUPIED_COLUMNS if columns is None else columns)
    current_x = 25
    order: list[int] = []
    rng = random.Random(seed)

    while remaining:
        candidates = sorted(remaining, key=lambda x: (abs(x - current_x), x))[:8]
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
        order.append(target)
        remaining.remove(target)
        current_x = target

    return tuple(order)


def expected_frame_count() -> int:
    attack_frames = MOVE_FRAMES + BEAM_FRAMES + EXPLOSION_FRAMES
    return HOLD_FRAMES + len(OCCUPIED_COLUMNS) * attack_frames + RESPAWN_FRAMES


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
    hue = _blend(CYAN, PURPLE, column / (CALENDAR_WEEKS - 1))
    bright = tuple(round(channel * BRIGHTNESS[level]) for channel in hue)
    return _blend(BACKGROUND, bright, visibility)


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
    live_columns: set[int],
    visibility: float = 1.0,
) -> None:
    for column in live_columns:
        bits = WORD_COLUMN_BY_X[column]
        level = levels[column]
        color = _column_color(column, level, visibility)
        for row, enabled in enumerate(bits):
            if not enabled:
                continue
            x, y = _cell_position(column, row)
            draw.rounded_rectangle(
                (x, y, x + CELL_SIZE, y + CELL_SIZE), radius=2, fill=color
            )
            if level > 0 and visibility > 0.55:
                highlight = _blend(color, (255, 255, 255), 0.18)
                draw.line((x + 2, y + 1, x + CELL_SIZE - 2, y + 1), fill=highlight)


def _draw_unity_ship(draw: Any, center_x: float) -> None:
    left = round(center_x - SHIP_SIZE / 2)
    for row, pixels in enumerate(UNITY_MASK):
        for column, enabled in enumerate(pixels):
            if enabled == "#":
                x = left + column * 2
                y = SHIP_TOP + row * 2
                draw.rectangle((x, y, x + 1, y + 1), fill=CYAN)

    center = round(center_x)
    draw.polygon(
        ((center - 4, SHIP_TOP + 29), (center + 4, SHIP_TOP + 29), (center, HEIGHT - 1)),
        fill=PURPLE,
    )


def _draw_beam(draw: Any, column: int, level: int, phase: int) -> None:
    center = round(_column_center(column))
    streak_offsets = (0, -3, 3, -6, 6)[: level + 1]
    target_rows = [row for row, enabled in enumerate(WORD_COLUMN_BY_X[column]) if enabled]
    target_y = _cell_position(column, min(target_rows))[1] + CELL_SIZE
    beam_color = _blend(CYAN, PURPLE, 0.35 + 0.25 * phase)
    for offset in streak_offsets:
        draw.line(
            (center + offset, SHIP_TOP, center + offset, target_y),
            fill=beam_color,
            width=2 if offset == 0 else 1,
        )


def _draw_explosion(draw: Any, column: int, level: int, phase: int) -> None:
    color = _blend(_column_color(column, level), (255, 255, 255), 0.30)
    directions = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1))
    radius = 3 + phase * 4
    intensity = level + 1

    for row, enabled in enumerate(WORD_COLUMN_BY_X[column]):
        if not enabled:
            continue
        x, y = _cell_position(column, row)
        center_x = x + CELL_SIZE // 2
        center_y = y + CELL_SIZE // 2
        for dx, dy in directions[:intensity]:
            particle_x = center_x + dx * radius
            particle_y = center_y + dy * radius
            draw.rectangle(
                (particle_x - 1, particle_y - 1, particle_x + 1, particle_y + 1),
                fill=color,
            )


def render_frame(
    levels: dict[int, int],
    live_columns: set[int],
    ship_center_x: float,
    *,
    beam: tuple[int, int] | None = None,
    explosion: tuple[int, int] | None = None,
    visibility: float = 1.0,
) -> Any:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    _draw_starfield(draw)
    _draw_word(draw, levels, live_columns, visibility)
    if beam is not None:
        column, phase = beam
        _draw_beam(draw, column, levels[column], phase)
    if explosion is not None:
        column, phase = explosion
        _draw_explosion(draw, column, levels[column], phase)
    _draw_unity_ship(draw, ship_center_x)
    return image


def generate_frames(levels: dict[int, int]) -> Iterator[Any]:
    live_columns = set(OCCUPIED_COLUMNS)
    initial_ship_x = _column_center(25)
    ship_x = initial_ship_x

    for _ in range(HOLD_FRAMES):
        yield render_frame(levels, live_columns, ship_x)

    for target in build_attack_order():
        target_x = _column_center(target)
        start_x = ship_x
        for frame in range(MOVE_FRAMES):
            progress = _ease((frame + 1) / MOVE_FRAMES)
            ship_x = _lerp(start_x, target_x, progress)
            yield render_frame(levels, live_columns, ship_x)

        for phase in range(BEAM_FRAMES):
            yield render_frame(levels, live_columns, target_x, beam=(target, phase))

        live_columns.remove(target)
        for phase in range(EXPLOSION_FRAMES):
            yield render_frame(levels, live_columns, target_x, explosion=(target, phase))

        ship_x = target_x

    all_columns = set(OCCUPIED_COLUMNS)
    for frame in range(RESPAWN_FRAMES):
        progress = _ease((frame + 1) / RESPAWN_FRAMES)
        return_x = _lerp(ship_x, initial_ship_x, progress)
        yield render_frame(
            levels, all_columns, return_x, visibility=(frame + 1) / RESPAWN_FRAMES
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
