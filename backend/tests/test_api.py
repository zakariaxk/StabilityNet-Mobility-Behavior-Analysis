import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.analysis_service import AnalysisService
from app.config import AnalysisRequest
from app.main import create_app
from app.pipeline.result_writer import write_json


def fake_runner(request: AnalysisRequest) -> dict[str, object]:
    result = {
        "analysis_version": "test",
        "video": {"path": str(request.video_path)},
        "frames_processed": 0,
        "frames": [],
        "tracks": [],
        "events": [
            {
                "event_type": "low_mobility_speed",
                "severity": "medium",
                "track_id": 1,
            }
        ],
    }
    write_json(request.output_path, result)
    return result


class ApiTests(unittest.TestCase):
    def test_creates_and_retrieves_analysis_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sample_dir = Path(tmpdir) / "samples"
            sample_dir.mkdir()
            (sample_dir / "test-video.mp4").write_bytes(b"fake video bytes")
            service = AnalysisService(
                output_dir=Path(tmpdir) / "analyses",
                sample_dir=sample_dir,
                runner=fake_runner,
            )
            client = TestClient(create_app(analysis_service=service))

            create_response = client.post(
                "/analyses",
                json={"video_path": "samples/test-video.mp4"},
            )

            self.assertEqual(create_response.status_code, 201)
            created = create_response.json()
            self.assertEqual(created["status"], "completed")
            self.assertEqual(created["frames_processed"], 0)
            self.assertEqual(created["tracks_count"], 0)
            self.assertEqual(created["events_count"], 1)
            self.assertIsNone(created["fps"])
            self.assertIsNone(created["processing_fps"])
            self.assertIsNone(created["annotated_video_url"])
            self.assertEqual(created["tracks"], [])
            self.assertEqual(created["events"][0]["event_type"], "Slow Walking")
            self.assertEqual(created["events"][0]["severity"], "medium")
            self.assertTrue(created["video_path"].endswith("samples/test-video.mp4"))
            self.assertEqual(created["result"]["analysis_version"], "test")
            self.assertEqual(created["result"]["status"], "completed")
            self.assertEqual(created["result"]["events"][0]["event_type"], "Slow Walking")
            self.assertEqual(created["summary"]["frames_processed"], 0)
            self.assertEqual(created["summary"]["track_count"], 0)
            self.assertEqual(created["summary"]["event_count"], 1)
            self.assertEqual(
                created["summary"]["event_counts_by_type"],
                {"Slow Walking": 1},
            )

            get_response = client.get(f"/analyses/{created['analysis_id']}")

            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json()["analysis_id"], created["analysis_id"])

    def test_rejects_missing_sample_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(
                output_dir=Path(tmpdir) / "analyses",
                sample_dir=Path(tmpdir) / "samples",
                runner=fake_runner,
            )
            client = TestClient(create_app(analysis_service=service))

            response = client.post(
                "/analyses",
                json={"video_path": "samples/missing.mp4"},
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"], "Video file not found.")

    def test_rejects_empty_sample_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=fake_runner)
            client = TestClient(create_app(analysis_service=service))

            response = client.post("/analyses", json={"video_path": ""})

            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.json()["detail"],
                "Upload an MP4 file or select a sample video before running analysis.",
            )

    def test_rejects_unsafe_sample_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=fake_runner)
            client = TestClient(create_app(analysis_service=service))

            response = client.post(
                "/analyses",
                json={"video_path": "../secret.mp4"},
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"], "Video file not found.")

    def test_returns_404_for_missing_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=fake_runner)
            client = TestClient(create_app(analysis_service=service))

            response = client.get("/analyses/00000000-0000-0000-0000-000000000000")

            self.assertEqual(response.status_code, 404)

    def test_uploads_mp4_and_serves_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(
                output_dir=Path(tmpdir) / "analyses",
                upload_dir=Path(tmpdir) / "uploads",
                runner=fake_runner,
            )
            client = TestClient(create_app(analysis_service=service))

            create_response = client.post(
                "/analyses/upload",
                files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
            )

            self.assertEqual(create_response.status_code, 201)
            created = create_response.json()
            self.assertEqual(created["source"], "uploaded_file")
            self.assertEqual(created["original_filename"], "clip.mp4")
            self.assertTrue(created["video_path"].endswith("/clip.mp4"))
            self.assertEqual(
                created["video_url"],
                f"/analyses/{created['analysis_id']}/video",
            )

            video_response = client.get(f"/analyses/{created['analysis_id']}/video")

            self.assertEqual(video_response.status_code, 200)
            self.assertEqual(video_response.content, b"fake video bytes")

    def test_rejects_non_mp4_uploads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=fake_runner)
            client = TestClient(create_app(analysis_service=service))

            response = client.post(
                "/analyses/upload",
                files={"file": ("clip.mov", b"fake video bytes", "video/quicktime")},
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"], "Only MP4 video uploads are supported.")

    def test_rejects_missing_upload_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=fake_runner)
            client = TestClient(create_app(analysis_service=service))

            response = client.post("/analyses/upload", files={})

            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.json()["detail"],
                "Upload an MP4 file or select a sample video before running analysis.",
            )

    def test_rejects_empty_mp4_uploads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=fake_runner)
            client = TestClient(create_app(analysis_service=service))

            response = client.post(
                "/analyses/upload",
                files={"file": ("clip.mp4", b"", "video/mp4")},
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"], "Uploaded MP4 file is empty.")

    def test_allows_local_nextjs_dev_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=fake_runner)
            client = TestClient(create_app(analysis_service=service))

            response = client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.headers["access-control-allow-origin"],
                "http://localhost:3000",
            )

    def test_wildcard_cors_disables_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalysisService(output_dir=Path(tmpdir), runner=fake_runner)
            client = TestClient(create_app(analysis_service=service, cors_origins=["*"]))

            response = client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], "*")
            self.assertNotIn("access-control-allow-credentials", response.headers)


if __name__ == "__main__":
    unittest.main()
