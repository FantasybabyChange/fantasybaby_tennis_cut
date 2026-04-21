from __future__ import annotations

import argparse
from pathlib import Path

from .config import CutConfig, config_to_dict, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tennis-cut",
        description="Cut dead time from tennis videos and keep rally segments.",
    )
    parser.add_argument("input", help="Input video path.")
    parser.add_argument("-o", "--output", help="Output video path.")
    parser.add_argument("--config", help="YAML config path.")
    parser.add_argument("--timeline", help="Write detected timeline JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, do not render video.")
    parser.add_argument("--active-threshold", type=float, help="Override rally activity threshold.")
    parser.add_argument("--min-rally-seconds", type=float, help="Override minimum rally duration.")
    parser.add_argument("--merge-gap-seconds", type=float, help="Override maximum gap to merge.")
    parser.add_argument("--pre-roll-seconds", type=float, help="Override leading padding.")
    parser.add_argument("--post-roll-seconds", type=float, help="Override trailing padding.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    config = _apply_overrides(config, args)

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}_rallies.mp4")

    print("Config:")
    for key, value in config_to_dict(config).items():
        print(f"  {key}: {value}")

    from .analyzer import VideoAnalyzer
    from .detector import RallyDetector
    from .renderer import VideoRenderer, write_timeline

    analyzer = VideoAnalyzer(config)
    analysis = analyzer.analyze(input_path)
    detector = RallyDetector(config)
    segments = detector.detect(analysis)

    kept = sum(segment.duration for segment in segments)
    print(f"\nSource duration: {analysis.info.duration:.1f}s")
    print(f"Detected segments: {len(segments)}")
    print(f"Kept duration: {kept:.1f}s")

    for index, segment in enumerate(segments, start=1):
        print(
            f"  #{index:02d} {segment.start:8.2f}s -> {segment.end:8.2f}s "
            f"({segment.duration:6.2f}s, score={segment.score:.3f})"
        )

    if args.timeline:
        write_timeline(
            args.timeline,
            input_path,
            analysis.info.duration,
            segments,
            [sample.to_dict() for sample in analysis.samples],
        )
        print(f"\nTimeline written: {args.timeline}")

    if args.dry_run:
        print("\nDry run complete. No video rendered.")
        return 0

    renderer = VideoRenderer(config)
    renderer.render(input_path, output_path, segments)
    print(f"\nRendered video: {output_path}")
    return 0


def _apply_overrides(config: CutConfig, args: argparse.Namespace) -> CutConfig:
    overrides = {
        "active_threshold": args.active_threshold,
        "min_rally_seconds": args.min_rally_seconds,
        "merge_gap_seconds": args.merge_gap_seconds,
        "pre_roll_seconds": args.pre_roll_seconds,
        "post_roll_seconds": args.post_roll_seconds,
    }
    for key, value in overrides.items():
        if value is not None:
            setattr(config, key, value)
    return config


if __name__ == "__main__":
    raise SystemExit(main())
