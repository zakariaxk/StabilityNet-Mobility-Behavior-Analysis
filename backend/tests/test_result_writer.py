from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.pipeline.result_writer import write_json


class ResultWriterTests(unittest.TestCase):
    def test_write_failure_preserves_existing_file_and_removes_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result.json"
            original = {"status": "previous"}
            path.write_text(json.dumps(original), encoding="utf-8")

            with patch(
                "app.pipeline.result_writer.json.dump",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    write_json(path, {"status": "replacement"})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)
            self.assertEqual(list(Path(tmpdir).iterdir()), [path])

    def test_replace_failure_preserves_existing_file_and_removes_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result.json"
            original = {"status": "previous"}
            path.write_text(json.dumps(original), encoding="utf-8")

            with patch(
                "app.pipeline.result_writer.os.replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_json(path, {"status": "replacement"})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)
            self.assertEqual(list(Path(tmpdir).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
