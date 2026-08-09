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
    first.save(path, "WEBP", save_all=True, append_images=[second], duration=40, loop=0)


def _raw_contributions(level: int) -> dict:
    weeks = []
    for week in range(52):
        days = []
        for day in range(7):
            active = week == 25 and day == 3
            days.append(
                {
                    "date": f"2026-01-{day + 1:02d}",
                    "count": level if active else 0,
                    "level": level if active else 0,
                }
            )
        weeks.append({"days": days})
    return {"username": "Dev0910", "total_contributions": level, "weeks": weeks}


class ValidationTests(unittest.TestCase):
    def test_valid_animation_creates_static_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            webp = root / "space-shooter.webp"
            png = root / "space-shooter-static.png"
            _animated_webp(webp)

            render_space_shooter.validate_webp_and_create_static(webp, png)

            self.assertTrue(png.is_file())
            with Image.open(png) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (860, 230))

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

            with mock.patch.object(render_space_shooter, "WEBP_HARD_LIMIT", 1):
                with self.assertRaisesRegex(ValueError, "invalid size"):
                    render_space_shooter.validate_webp_and_create_static(
                        webp, root / "space-shooter-static.png"
                    )


@unittest.skipUnless(
    importlib.util.find_spec("gh_space_shooter") is not None,
    "gh-space-shooter is not installed",
)
class DeterminismTests(unittest.TestCase):
    def test_fixed_input_is_reproducible_and_changed_input_changes_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_data = root / "first.json"
            changed_data = root / "changed.json"
            first_data.write_text(json.dumps(_raw_contributions(1)), encoding="utf-8")
            changed_data.write_text(json.dumps(_raw_contributions(4)), encoding="utf-8")

            # Five FPS preserves the deterministic code path while keeping this
            # regression test fast; production remains pinned to 25 FPS.
            with mock.patch.object(render_space_shooter, "FPS", 5):
                first_webp, _ = render_space_shooter.render_assets(
                    "Dev0910", root / "first", first_data
                )
                second_webp, _ = render_space_shooter.render_assets(
                    "Dev0910", root / "second", first_data
                )
                changed_webp, _ = render_space_shooter.render_assets(
                    "Dev0910", root / "changed", changed_data
                )

            digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest(first_webp), digest(second_webp))
            self.assertNotEqual(digest(first_webp), digest(changed_webp))


if __name__ == "__main__":
    unittest.main()
