"""Upload one local MP4 to a running StabilityNet backend.

This helper intentionally uses only the Python standard library so it works
after the backend dev environment is installed, without adding another client
dependency.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from uuid import uuid4

DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload a local MP4 to /analyses/upload and print the response.",
    )
    parser.add_argument("video", type=Path, help="Path to a local .mp4 file.")
    parser.add_argument(
        "--backend-url",
        default=DEFAULT_BACKEND_URL,
        help=f"Backend base URL. Default: {DEFAULT_BACKEND_URL}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    video_path = args.video.expanduser()
    backend_url = str(args.backend_url).rstrip("/")

    try:
        _validate_video_path(video_path)
        status, payload = upload_video(video_path, backend_url)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"error: backend returned HTTP {exc.code}")
        _print_response(body, backend_url)
        return 1
    except URLError as exc:
        print(f"error: could not reach backend at {backend_url}: {exc.reason}")
        return 1

    print(f"HTTP {status}")
    _print_response(payload, backend_url)
    return 0


def upload_video(video_path: Path, backend_url: str) -> tuple[int, str]:
    body, content_type = _multipart_body(video_path)
    request = Request(
        urljoin(f"{backend_url.rstrip('/')}/", "analyses/upload"),
        data=body,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    with urlopen(request, timeout=600) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def _validate_video_path(video_path: Path) -> None:
    if video_path.suffix.lower() != ".mp4":
        raise ValueError("only .mp4 files are supported")
    if not video_path.exists() or not video_path.is_file():
        raise ValueError(f"file not found: {video_path}")
    if video_path.stat().st_size == 0:
        raise ValueError(f"file is empty: {video_path}")


def _multipart_body(video_path: Path) -> tuple[bytes, str]:
    boundary = f"----StabilityNetUpload{uuid4().hex}"
    content_type = mimetypes.guess_type(video_path.name)[0] or "video/mp4"
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{video_path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return header + video_path.read_bytes() + footer, f"multipart/form-data; boundary={boundary}"


def _print_response(raw_payload: str, backend_url: str) -> None:
    try:
        payload: Any = json.loads(raw_payload)
    except json.JSONDecodeError:
        print(raw_payload)
        return

    print(json.dumps(payload, indent=2, sort_keys=True))
    if isinstance(payload, dict):
        output_url = payload.get("annotated_video_url") or payload.get("video_url")
        if isinstance(output_url, str) and output_url.startswith("/"):
            print(f"\nOpen video: {backend_url.rstrip('/')}{output_url}")


if __name__ == "__main__":
    raise SystemExit(main())
