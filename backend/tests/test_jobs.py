"""Background job submission, progress reporting, and failure recording."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.analysis_service import AnalysisService
from app.config import AnalysisRequest
from app.pipeline.result_writer import write_json
from app.main import create_app


def slow_runner(request: AnalysisRequest, progress_callback: object = None) -> dict[str, object]:
    """Report progress a few times, then complete."""

    if callable(progress_callback):
        for frames in (10, 20, 30):
            progress_callback("analyzing", frames, 30)
            time.sleep(0.02)
        progress_callback("encoding", 30, 30)
    return {
        "status": "completed",
        "analysis_version": "test",
        "frames_processed": 30,
        "tracks": [],
        "events": [],
        "video": {},
    }


def exploding_runner(request: AnalysisRequest, progress_callback: object = None) -> dict[str, object]:
    raise RuntimeError("detector exploded")


class JobTests(unittest.TestCase):
    def test_submission_returns_immediately_with_processing_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=slow_runner)
            client = TestClient(create_app(analysis_service=service))

            started = time.perf_counter()
            response = client.post(
                "/analyses/upload",
                files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
            )
            elapsed = time.perf_counter() - started

            self.assertEqual(response.status_code, 202)
            body = response.json()
            self.assertEqual(body["status"], "processing")
            self.assertIn("analysis_id", body)
            # The whole point: the caller is not blocked on the pipeline.
            self.assertLess(elapsed, 1.0)

            service.wait_for(body["analysis_id"])

    def test_progress_advances_and_completes_at_100(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=slow_runner)
            client = TestClient(create_app(analysis_service=service))

            analysis_id = client.post(
                "/analyses/upload",
                files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
            ).json()["analysis_id"]

            service.wait_for(analysis_id)
            record = client.get(f"/analyses/{analysis_id}").json()

            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["progress"]["stage"], "completed")
            self.assertEqual(record["progress"]["percent"], 100.0)

    def test_failure_is_recorded_on_the_record_not_raised_to_the_caller(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=exploding_runner)
            client = TestClient(create_app(analysis_service=service))

            response = client.post(
                "/analyses/upload",
                files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
            )
            self.assertEqual(response.status_code, 202)

            analysis_id = response.json()["analysis_id"]
            service.wait_for(analysis_id)
            record = client.get(f"/analyses/{analysis_id}").json()

            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["message"], "detector exploded")

    def test_concurrent_submissions_are_queued_and_all_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=slow_runner)
            client = TestClient(create_app(analysis_service=service))

            ids = [
                client.post(
                    "/analyses/upload",
                    files={"file": (f"clip{i}.mp4", b"fake video bytes", "video/mp4")},
                ).json()["analysis_id"]
                for i in range(3)
            ]

            for analysis_id in ids:
                service.wait_for(analysis_id)
                self.assertEqual(
                    client.get(f"/analyses/{analysis_id}").json()["status"], "completed"
                )

    def test_list_endpoint_returns_stored_analyses_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=slow_runner)
            client = TestClient(create_app(analysis_service=service))

            ids = []
            for i in range(3):
                analysis_id = client.post(
                    "/analyses/upload",
                    files={"file": (f"clip{i}.mp4", b"fake video bytes", "video/mp4")},
                ).json()["analysis_id"]
                service.wait_for(analysis_id)
                ids.append(analysis_id)
                time.sleep(0.01)  # distinct mtimes

            listing = client.get("/analyses").json()
            self.assertEqual(listing["total"], 3)
            self.assertEqual(len(listing["items"]), 3)
            self.assertEqual(listing["items"][0]["analysis_id"], ids[-1])
            self.assertIn("original_filename", listing["items"][0])

    def test_frames_endpoint_serves_the_trace_excluded_from_the_response(self) -> None:
        def runner_with_frames(
            request: AnalysisRequest, progress_callback: object = None
        ) -> dict[str, object]:
            result = {
                "status": "completed",
                "frames_processed": 2,
                "frames": [{"frame_index": 0}, {"frame_index": 1}],
                "tracks": [],
                "events": [],
                "video": {},
            }
            # analyze_video persists the full result itself; the frames
            # endpoint reads that file, so the fake has to do the same.
            write_json(request.output_path, result)
            return result

        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=runner_with_frames)
            client = TestClient(create_app(analysis_service=service))

            analysis_id = client.post(
                "/analyses/upload",
                files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
            ).json()["analysis_id"]
            service.wait_for(analysis_id)

            record = client.get(f"/analyses/{analysis_id}").json()
            self.assertNotIn("frames", record.get("result", {}))

            frames = client.get(f"/analyses/{analysis_id}/frames").json()
            self.assertEqual(len(frames["frames"]), 2)

    def test_frames_endpoint_404s_for_unknown_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=slow_runner)
            client = TestClient(create_app(analysis_service=service))
            response = client.get("/analyses/2f237428-fe22-475e-a9fc-c641902561c8/frames")
            self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
