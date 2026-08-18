"""Command-line entrypoints for StabilityNet backend workflows."""

from __future__ import annotations

import argparse
from pathlib import Path

from app import __version__
from app.config import (
    AnalysisRequest,
    DEFAULT_DETECTOR_MODEL,
    DetectorConfig,
    PipelineConfig,
)
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
    analyze.add_argument(
        "--annotated-video",
        type=Path,
        default=None,
        help=(
            "Optional path for the annotated H.264 output video. Requires "
            "ffmpeg on PATH."
        ),
    )
    analyze.add_argument(
        "--detector-model",
        default=DEFAULT_DETECTOR_MODEL,
        help=(
            "Ultralytics detector weights to use "
            f"(default: {DEFAULT_DETECTOR_MODEL})."
        ),
    )

    prune = subparsers.add_parser(
        "prune",
        help="Delete all but the N most recent analyses, with their uploads and videos.",
    )
    prune.add_argument("--keep", type=int, default=10, help="How many recent analyses to keep.")
    prune.add_argument(
        "--outputs",
        type=Path,
        default=Path("outputs"),
        help="Outputs directory (default: outputs).",
    )
    prune.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be deleted without deleting it.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        from app.pipeline.video_pipeline import analyze_video

        request = AnalysisRequest(
            video_path=args.video,
            output_path=args.output,
            config=PipelineConfig(
                detector=DetectorConfig(model_name=args.detector_model),
            ),
            annotated_video_path=args.annotated_video,
        )
        try:
            result = analyze_video(request)
        except (DetectorDependencyError, VideoDependencyError, VideoOpenError) as exc:
            parser.exit(2, f"error: {exc}\n")
        print(
            "analysis written to "
            f"{args.output} ({result['frames_processed']} frames processed)"
        )
        if args.annotated_video is not None:
            print(f"annotated video written to {args.annotated_video}")
        return 0

    if args.command == "prune":
        return _prune(args.outputs, keep=args.keep, dry_run=args.dry_run)

    parser.print_help()
    return 0


def _prune(outputs_dir: Path, *, keep: int, dry_run: bool) -> int:
    """Drop old analyses so the outputs directory does not grow without bound.

    Each analysis owns a record, a result file, an uploaded source video and
    an annotated output; nothing removed them, so outputs/ had reached 1 GB.
    """

    import shutil

    analyses_dir = outputs_dir / "analyses"
    if not analyses_dir.exists():
        print(f"no analyses directory at {analyses_dir}")
        return 0

    records = sorted(
        (path for path in analyses_dir.glob("*.json") if not path.name.endswith(".result.json")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    doomed = records[max(0, keep):]
    if not doomed:
        print(f"{len(records)} analyses, keeping {keep} — nothing to prune")
        return 0

    freed = 0
    for record_path in doomed:
        analysis_id = record_path.stem
        targets = [
            record_path,
            analyses_dir / f"{analysis_id}.result.json",
            outputs_dir / "videos" / f"{analysis_id}.mp4",
            outputs_dir / "uploads" / analysis_id,
        ]
        for target in targets:
            if not target.exists():
                continue
            size = (
                sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
                if target.is_dir()
                else target.stat().st_size
            )
            freed += size
            if dry_run:
                continue
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)

    verb = "would free" if dry_run else "freed"
    print(f"pruned {len(doomed)} analyses (kept {min(keep, len(records))}); {verb} {freed / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
