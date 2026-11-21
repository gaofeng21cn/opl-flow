from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
ENCODER = (
    REPO_ROOT
    / "skills/software-development/references/browser-evidence/encode_gif.py"
)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "ffmpeg and ffprobe are required for GIF encoder tests",
)
class RecordBrowserGifTests(unittest.TestCase):
    def make_frame(self, path: Path, color: str, size: str = "320x180") -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s={size}:d=0.1",
                "-frames:v",
                "1",
                "-y",
                str(path),
            ],
            check=True,
        )

    def test_encoder_creates_verified_animated_gif(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frames = root / "frames"
            frames.mkdir()
            self.make_frame(frames / "00-start.png", "white")
            self.make_frame(frames / "01-finish.png", "black")
            output = root / "demo.gif"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ENCODER),
                    str(frames),
                    str(output),
                    "--durations",
                    "0.5,1.0",
                    "--fps",
                    "10",
                    "--max-width",
                    "240",
                    "--colors",
                    "32",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            summary = json.loads(completed.stdout)
            self.assertEqual(Path(summary["output"]), output.resolve())
            self.assertEqual(summary["sourceFrames"], 2)
            self.assertGreaterEqual(summary["encodedFrames"], 2)
            self.assertLessEqual(summary["width"], 240)
            self.assertGreater(summary["height"], 0)
            self.assertAlmostEqual(summary["durationSeconds"], 1.5, delta=0.2)
            self.assertEqual(summary["bytes"], output.stat().st_size)
            self.assertTrue(output.read_bytes().startswith(b"GIF"))

    def test_video_trim_speed_hold_and_failed_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "browser recording.webm"
            output = root / "demo.gif"
            subprocess.run([
                "ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                "testsrc2=size=80x60:rate=10:duration=3", "-c:v", "libvpx", str(video),
            ], check=True)
            command = [
                sys.executable, str(ENCODER), str(video), str(output),
                "--start", "0.5", "--end", "2.5", "--speed", "2", "--final-hold", "1",
            ]
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["sourceVideo"], str(video.resolve()))
            self.assertAlmostEqual(summary["durationSeconds"], 2.0, delta=0.2)
            self.assertEqual((summary["width"], summary["height"]), (80, 60))
            verified = output.read_bytes()
            for options, message in [
                ([], "already exists"),
                (["--force", "--max-bytes", "1"], "above --max-bytes"),
                (["--force", "--durations", "1"], "require a screenshot directory"),
            ]:
                with self.subTest(options=options):
                    rejected = subprocess.run(command + options, capture_output=True, text=True)
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertIn(message, rejected.stderr)
                    self.assertEqual(output.read_bytes(), verified)

    def test_encoder_rejects_mismatched_frame_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frames = root / "frames"
            frames.mkdir()
            self.make_frame(frames / "00-start.png", "white", "320x180")
            self.make_frame(frames / "01-finish.png", "black", "300x180")

            completed = subprocess.run(
                [sys.executable, str(ENCODER), str(frames), str(root / "demo.gif")],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("all frames must have identical dimensions", completed.stderr)


if __name__ == "__main__":
    unittest.main()
