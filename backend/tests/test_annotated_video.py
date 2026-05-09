import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.pipeline.annotated_video import AnnotatedVideoWriter, VideoWriteError


class AnnotatedVideoWriterTests(unittest.TestCase):
    def test_missing_ffmpeg_removes_raw_video_and_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "annotated.mp4"
            raw_path = Path(tmpdir) / "annotated.raw.mp4"
            raw_path.write_bytes(b"raw mp4 bytes")
            output_path.write_bytes(b"partial output")
            writer = AnnotatedVideoWriter(output_path, fps=30.0, fallback_fps=30.0)
            writer._temp_path = raw_path

            with patch("app.pipeline.annotated_video.shutil.which", return_value=None):
                with self.assertRaisesRegex(VideoWriteError, "ffmpeg is required"):
                    writer._finalize_output()

            self.assertFalse(raw_path.exists())
            self.assertFalse(output_path.exists())

    def test_ffmpeg_failure_removes_partial_output_and_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "annotated.mp4"
            raw_path = Path(tmpdir) / "annotated.raw.mp4"
            raw_path.write_bytes(b"raw mp4 bytes")
            output_path.write_bytes(b"partial output")
            writer = AnnotatedVideoWriter(output_path, fps=30.0, fallback_fps=30.0)
            writer._temp_path = raw_path

            with (
                patch("app.pipeline.annotated_video.shutil.which", return_value="/usr/bin/ffmpeg"),
                patch(
                    "app.pipeline.annotated_video.subprocess.run",
                    side_effect=subprocess.CalledProcessError(
                        1,
                        ["ffmpeg"],
                        stderr=b"invalid codec",
                    ),
                ),
            ):
                with self.assertRaisesRegex(VideoWriteError, "ffmpeg failed"):
                    writer._finalize_output()

            self.assertFalse(raw_path.exists())
            self.assertFalse(output_path.exists())

    def test_ffmpeg_transcode_uses_h264_yuv420p(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "annotated.mp4"
            raw_path = Path(tmpdir) / "annotated.raw.mp4"
            raw_path.write_bytes(b"raw mp4 bytes")
            writer = AnnotatedVideoWriter(output_path, fps=30.0, fallback_fps=30.0)
            writer._temp_path = raw_path

            def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
                output_path.write_bytes(b"h264 bytes")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with (
                patch("app.pipeline.annotated_video.shutil.which", return_value="/usr/bin/ffmpeg"),
                patch("app.pipeline.annotated_video.subprocess.run", side_effect=fake_run) as run_mock,
            ):
                writer._finalize_output()

            command = run_mock.call_args.args[0]
            self.assertIn("libx264", command)
            self.assertIn("yuv420p", command)
            self.assertTrue(output_path.exists())
            self.assertFalse(raw_path.exists())


if __name__ == "__main__":
    unittest.main()
