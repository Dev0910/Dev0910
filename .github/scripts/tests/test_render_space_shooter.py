from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "render-space-shooter.py"
SPEC = importlib.util.spec_from_file_location("render_space_shooter", SCRIPT_PATH)
assert SPEC and SPEC.loader
render_space_shooter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_space_shooter)


def _animated_webp(path: Path, size: tuple[int, int] = (860, 230)) -> None:
    first = Image.new("RGB", size, "#0d1117")
    second = Image.new("RGB", size, "#22d3ee")
    first.save(path, "WEBP", save_all=True, append_images=[second], duration=66, loop=0)


def _raw_contributions(level: int = 0, active_week: int = 25) -> dict:
    weeks = []
    for week in range(52):
        days = []
        for day in range(7):
            active = week == active_week and day == 3
            days.append(
                {
                    "date": f"2026-W{week:02d}-{day}",
                    "count": level if active else 0,
                    "level": level if active else 0,
                }
            )
        weeks.append({"days": days})
    return {"username": "Dev0910", "total_contributions": level, "weeks": weeks}


class WordmarkTests(unittest.TestCase):
    def test_wordmark_contract(self) -> None:
        self.assertEqual(len(render_space_shooter.WORD_COLUMNS), 49)
        self.assertEqual(render_space_shooter.WORD_START_COLUMN, 1)
        self.assertEqual(len(render_space_shooter.OCCUPIED_COLUMNS), 40)
        self.assertEqual(render_space_shooter.WORD_BLOCK_COUNT, 122)

    def test_week_groups_cover_every_week_once(self) -> None:
        groups = render_space_shooter.week_groups_for_word_columns()
        self.assertEqual(len(groups), 40)
        self.assertEqual([week for group in groups for week in group], list(range(52)))

    def test_levels_fold_chronologically_with_max_intensity(self) -> None:
        data = _raw_contributions(level=4, active_week=51)
        mapped = render_space_shooter.contribution_levels_by_column(data)
        self.assertEqual(mapped[render_space_shooter.OCCUPIED_COLUMNS[-1]], 4)
        self.assertTrue(all(level == 0 for level in list(mapped.values())[:-1]))

    def test_contribution_levels_zero_through_four_are_supported(self) -> None:
        for level in range(5):
            mapped = render_space_shooter.contribution_levels_by_column(
                _raw_contributions(level=level)
            )
            self.assertIn(level, mapped.values())

    def test_attack_order_is_seeded_and_complete(self) -> None:
        first = render_space_shooter.build_attack_order()
        second = render_space_shooter.build_attack_order()
        self.assertEqual(first, second)
        self.assertEqual(set(first), set(render_space_shooter.WORD_BLOCKS))
        self.assertEqual(len(first), 122)

        for column in render_space_shooter.OCCUPIED_COLUMNS:
            attacked_rows = [row for attacked_column, row in first if attacked_column == column]
            self.assertEqual(attacked_rows, sorted(attacked_rows, reverse=True))

    def test_frame_zero_contains_every_wordmark_block_and_unity_ship(self) -> None:
        levels = render_space_shooter.contribution_levels_by_column(_raw_contributions())
        frame = next(render_space_shooter.generate_frames(levels))
        for column, bits in render_space_shooter.WORD_COLUMN_BY_X.items():
            for row, enabled in enumerate(bits):
                if not enabled:
                    continue
                x, y = render_space_shooter._cell_position(column, row)
                self.assertNotEqual(
                    frame.getpixel((x + render_space_shooter.CELL_SIZE // 2, y + render_space_shooter.CELL_SIZE // 2)),
                    render_space_shooter.BACKGROUND,
                )

        unity_logo = render_space_shooter._unity_logo()
        self.assertEqual(unity_logo.mode, "RGBA")
        self.assertEqual(unity_logo.size, (32, 32))
        ship_center = round(render_space_shooter._column_center(25))
        ship_region = frame.crop(
            (
                ship_center - render_space_shooter.SHIP_SIZE // 2,
                render_space_shooter.SHIP_TOP,
                ship_center + render_space_shooter.SHIP_SIZE // 2,
                render_space_shooter.SHIP_TOP + render_space_shooter.SHIP_SIZE,
            )
        )
        non_background_pixels = sum(
            count
            for count, color in ship_region.getcolors(
                maxcolors=render_space_shooter.SHIP_SIZE**2
            )
            if color != render_space_shooter.BACKGROUND
        )
        self.assertGreater(non_background_pixels, 500)
        thruster_y = render_space_shooter.SHIP_TOP + 34
        self.assertEqual(
            frame.getpixel((ship_center - 6, thruster_y)),
            render_space_shooter.PURPLE,
        )
        self.assertEqual(
            frame.getpixel((ship_center + 6, thruster_y)),
            render_space_shooter.PURPLE,
        )
        self.assertEqual(
            frame.getpixel((ship_center, thruster_y)),
            render_space_shooter.BACKGROUND,
        )
        first_column, first_row = render_space_shooter.WORD_BLOCKS[0]
        x, y = render_space_shooter._cell_position(first_column, first_row)
        self.assertEqual(
            frame.getpixel((x + render_space_shooter.CELL_SIZE // 2, y + render_space_shooter.CELL_SIZE // 2)),
            render_space_shooter.GITHUB_GREENS[0],
        )

    def test_animation_contract_is_density_independent_and_loops(self) -> None:
        counts = []
        for level in (0, 4):
            levels = render_space_shooter.contribution_levels_by_column(
                _raw_contributions(level=level)
            )
            iterator = render_space_shooter.generate_frames(levels)
            first = next(iterator)
            last = first
            count = 1
            for last in iterator:
                count += 1
            counts.append(count)
            self.assertEqual(first.tobytes(), last.tobytes())

        self.assertEqual(counts, [render_space_shooter.expected_frame_count()] * 2)
        self.assertGreaterEqual(render_space_shooter.expected_duration_ms(), 40_000)
        self.assertLessEqual(render_space_shooter.expected_duration_ms(), 45_000)


class ValidationTests(unittest.TestCase):
    def test_valid_animation_creates_static_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            webp = root / "space-shooter.webp"
            png = root / "space-shooter-static.png"
            _animated_webp(webp)

            render_space_shooter.validate_webp_and_create_static(webp, png)

            with Image.open(png) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (860, 230))
                self.assertEqual(getattr(image, "n_frames", 1), 1)

    def test_rejects_non_webp_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            webp = root / "space-shooter.webp"
            webp.write_bytes(b"not-a-webp")
            with self.assertRaisesRegex(ValueError, "not a WebP"):
                render_space_shooter.validate_webp_and_create_static(
                    webp, root / "space-shooter-static.png"
                )

    def test_rejects_wrong_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            webp = root / "space-shooter.webp"
            _animated_webp(webp, (320, 200))
            with self.assertRaisesRegex(ValueError, "unexpected image dimensions"):
                render_space_shooter.validate_webp_and_create_static(
                    webp, root / "space-shooter-static.png"
                )

    def test_rejects_single_frame_webp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            webp = root / "space-shooter.webp"
            Image.new("RGB", (860, 230), "black").save(webp, "WEBP")
            with self.assertRaisesRegex(ValueError, "not animated"):
                render_space_shooter.validate_webp_and_create_static(
                    webp, root / "space-shooter-static.png"
                )

    def test_rejects_oversize_webp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            webp = root / "space-shooter.webp"
            _animated_webp(webp)
            with (
                mock.patch.object(render_space_shooter, "WEBP_HARD_LIMIT", 1),
                self.assertRaisesRegex(ValueError, "invalid size"),
            ):
                render_space_shooter.validate_webp_and_create_static(
                    webp, root / "space-shooter-static.png"
                )

    def test_rejects_extra_and_wrong_asset_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "space-shooter.webp").write_bytes(b"webp")
            (root / "wrong.png").write_bytes(b"png")
            (root / "extra.txt").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected filenames"):
                render_space_shooter.validate_asset_file_set(root)

    def test_rejects_symlinked_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            webp = root / "space-shooter.webp"
            png = root / "space-shooter-static.png"
            webp.write_bytes(b"webp")
            png.write_bytes(b"png")
            with mock.patch.object(Path, "is_symlink", autospec=True) as is_symlink:
                is_symlink.side_effect = lambda path: path.name == "space-shooter.webp"
                with self.assertRaisesRegex(ValueError, "regular file"):
                    render_space_shooter.validate_asset_file_set(root)


@unittest.skipUnless(
    importlib.util.find_spec("gh_space_shooter") is not None,
    "gh-space-shooter is not installed",
)
class DeterminismTests(unittest.TestCase):
    def test_fixed_input_is_reproducible_and_changed_input_changes_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixed = root / "fixed.json"
            changed = root / "changed.json"
            fixed.write_text(json.dumps(_raw_contributions(1)), encoding="utf-8")
            changed.write_text(json.dumps(_raw_contributions(4)), encoding="utf-8")

            short_columns = render_space_shooter.OCCUPIED_COLUMNS[:4]
            short_blocks = tuple(
                block
                for block in render_space_shooter.WORD_BLOCKS
                if block[0] in short_columns
            )
            patches = (
                mock.patch.object(render_space_shooter, "OCCUPIED_COLUMNS", short_columns),
                mock.patch.object(render_space_shooter, "WORD_BLOCKS", short_blocks),
                mock.patch.object(render_space_shooter, "WORD_BLOCK_COUNT", len(short_blocks)),
                mock.patch.object(render_space_shooter, "HOLD_FRAMES", 1),
                mock.patch.object(render_space_shooter, "MOVE_FRAMES", 1),
                mock.patch.object(render_space_shooter, "BULLET_FRAMES", 1),
                mock.patch.object(render_space_shooter, "EXPLOSION_FRAMES", 1),
                mock.patch.object(render_space_shooter, "RESPAWN_FRAMES", 2),
            )
            for patch in patches:
                patch.start()
            try:
                first_webp, _ = render_space_shooter.render_assets(
                    "Dev0910", root / "first", fixed
                )
                second_webp, _ = render_space_shooter.render_assets(
                    "Dev0910", root / "second", fixed
                )
                changed_webp, _ = render_space_shooter.render_assets(
                    "Dev0910", root / "changed-output", changed
                )
            finally:
                for patch in reversed(patches):
                    patch.stop()

            digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest(first_webp), digest(second_webp))
            self.assertNotEqual(digest(first_webp), digest(changed_webp))


if __name__ == "__main__":
    unittest.main()
