"""Command-line entrypoints for StabilityNet backend workflows."""

from __future__ import annotations

import argparse
from pathlib import Path

from app import __version__
from app.config import AnalysisRequest
from app.pipeline.frame_reader import VideoDependencyError, VideoOpenError
from app.vision.detector import DetectorDependencyError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stabilitynet",
        description="Analyze mobility behavior in local video files.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    analyze = subparsers.add_parser("analyze", help="Analyze a local video file.")
    analyze.add_argument("--video", required=True, type=Path, help="Path to a video file.")
    analyze.add_argument("--output", required=True, type=Path, help="Path for JSON output.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        from app.pipeline.video_pipeline import analyze_video

        request = AnalysisRequest(video_path=args.video, output_path=args.output)
        try:
            result = analyze_video(request)
        except (DetectorDependencyError, VideoDependencyError, VideoOpenError) as exc:
            parser.exit(2, f"error: {exc}\n")
        print(
            "analysis written to "
            f"{args.output} ({result['frames_processed']} frames processed)"
        )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
