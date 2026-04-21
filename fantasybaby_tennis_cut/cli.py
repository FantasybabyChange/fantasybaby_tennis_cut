from __future__ import annotations

import argparse
from pathlib import Path

from .audio import filter_segments_by_audio
from .config import (
    CutConfig,
    apply_video_type_preset,
    config_to_dict,
    load_config,
    video_type_label,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tennis-cut",
        description="Cut dead time from tennis videos and keep rally segments.",
    )
    parser.add_argument("input", nargs="?", help="Input video path.")
    parser.add_argument("-o", "--output", help="Output video path.")
    parser.add_argument("--config", help="YAML config path.")
    parser.add_argument(
        "--video-type",
        choices=[
            "1",
            "2",
            "3",
            "serve",
            "serve-training",
            "training",
            "doubles",
            "doubles-match",
            "double",
            "singles",
            "singles-match",
            "single",
        ],
        help="Preset: 1=serve training, 2=doubles match optimized, 3=singles match optimized.",
    )
    parser.add_argument("--timeline", help="Write detected timeline JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, do not render video.")
    parser.add_argument(
        "--detection-mode",
        choices=["auto", "burst", "sustained", "hysteresis"],
        help="Detection strategy. auto falls back to sustained when burst cuts too aggressively.",
    )
    parser.add_argument("--active-threshold", type=float, help="Override rally activity threshold.")
    parser.add_argument("--peak-prominence", type=float, help="Override burst peak prominence.")
    parser.add_argument(
        "--local-baseline-seconds",
        type=float,
        help="Override local baseline window for burst detection.",
    )
    parser.add_argument("--sustained-threshold", type=float, help="Override sustained-mode threshold.")
    parser.add_argument(
        "--auto-fallback-min-kept-ratio",
        type=float,
        help="Override minimum kept ratio before auto mode falls back to sustained detection.",
    )
    parser.add_argument("--hysteresis-start-threshold", type=float, help="Override hysteresis start threshold.")
    parser.add_argument(
        "--hysteresis-continue-threshold",
        type=float,
        help="Override hysteresis continue threshold.",
    )
    parser.add_argument("--max-inactive-seconds", type=float, help="Override allowed inactive gap.")
    parser.add_argument("--quality-peak-threshold", type=float, help="Override quality peak threshold.")
    parser.add_argument("--min-quality-peak-count", type=int, help="Override minimum quality peaks.")
    parser.add_argument("--quality-active-threshold", type=float, help="Override quality active threshold.")
    parser.add_argument(
        "--min-quality-active-average",
        type=float,
        help="Override minimum average score over active samples.",
    )
    parser.add_argument(
        "--quality-trim-threshold",
        type=float,
        help="Trim each detected segment to this minimum activity score before padding.",
    )
    parser.add_argument(
        "--strong-tail-trim-peak-threshold",
        type=float,
        help="Trim a segment tail when it drifts too long after the final strong activity peak.",
    )
    parser.add_argument(
        "--strong-tail-trim-min-tail-seconds",
        type=float,
        help="Minimum weak-tail duration after a strong activity peak before trimming.",
    )
    parser.add_argument(
        "--strong-tail-trim-padding-seconds",
        type=float,
        help="Padding kept after the final strong activity peak when tail trimming applies.",
    )
    parser.add_argument(
        "--audio-filter-max-segment-seconds",
        type=float,
        help="Use audio transients to reject short visual-only segments up to this duration.",
    )
    parser.add_argument("--audio-peak-threshold", type=float, help="Override audio transient threshold.")
    parser.add_argument("--audio-min-peak-count", type=int, help="Override minimum audio transient peaks.")
    parser.add_argument(
        "--audio-bridge-gap-seconds",
        type=float,
        help="Merge nearby visual segments when audio transients continue through the gap.",
    )
    parser.add_argument("--audio-bridge-peak-threshold", type=float, help="Override bridge audio threshold.")
    parser.add_argument("--audio-bridge-min-peak-count", type=int, help="Override bridge audio peak count.")
    parser.add_argument(
        "--audio-tail-trim-min-segment-seconds",
        type=float,
        help="Trim long segment tails after the final audio transient.",
    )
    parser.add_argument("--audio-tail-padding-seconds", type=float, help="Padding after final audio transient.")
    parser.add_argument("--min-rally-seconds", type=float, help="Override minimum rally duration.")
    parser.add_argument("--merge-gap-seconds", type=float, help="Override maximum gap to merge.")
    parser.add_argument("--pre-roll-seconds", type=float, help="Override leading padding.")
    parser.add_argument("--post-roll-seconds", type=float, help="Override trailing padding.")
    parser.add_argument("--ignore-initial-seconds", type=float, help="Ignore initial dead time.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    interactive = args.input is None
    if interactive:
        args = _prompt_interactive_args(args)

    config = load_config(args.config)
    config = apply_video_type_preset(config, args.video_type)
    config = _apply_overrides(config, args)

    if args.input is None:
        parser.error("input video path is required.")

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}_rallies.mp4")

    print("Config:")
    selected_video_type = video_type_label(args.video_type)
    if selected_video_type:
        print(f"  video_type: {args.video_type} ({selected_video_type})")
    for key, value in config_to_dict(config).items():
        print(f"  {key}: {value}")

    from .analyzer import VideoAnalyzer
    from .detector import RallyDetector
    from .renderer import VideoRenderer, write_timeline

    analyzer = VideoAnalyzer(config)
    analysis = analyzer.analyze(input_path)
    detector = RallyDetector(config)
    segments = detector.detect(analysis)
    segments = filter_segments_by_audio(input_path, segments, config)

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


def _prompt_interactive_args(args: argparse.Namespace) -> argparse.Namespace:
    print("FantasyBaby网球视频自动剪辑")
    print("请选择视频类型:")
    print("  1. 发球训练视频")
    print("  2. 双打比赛视频（比赛优化）")
    print("  3. 单打比赛视频（比赛优化）")

    if args.video_type is None:
        args.video_type = _prompt_choice("请输入类型编号 (1/2/3): ", {"1", "2", "3"})

    args.input = _prompt_path("请输入需要转换的视频路径: ", must_exist=True)
    args.output = _prompt_path("请输入输出视频路径: ", must_exist=False)
    return args


def _prompt_choice(prompt: str, choices: set[str]) -> str:
    while True:
        value = input(prompt).strip()
        if value in choices:
            return value
        print(f"请输入有效选项: {', '.join(sorted(choices))}")


def _prompt_path(prompt: str, *, must_exist: bool) -> str:
    while True:
        value = _clean_pasted_path(input(prompt))
        if not value:
            print("路径不能为空。")
            continue

        path = Path(value)
        if must_exist and not path.exists():
            print(f"找不到文件: {path}")
            continue

        if not must_exist:
            path.parent.mkdir(parents=True, exist_ok=True)

        return str(path)


def _clean_pasted_path(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _apply_overrides(config: CutConfig, args: argparse.Namespace) -> CutConfig:
    overrides = {
        "detection_mode": args.detection_mode,
        "active_threshold": args.active_threshold,
        "peak_prominence": args.peak_prominence,
        "local_baseline_seconds": args.local_baseline_seconds,
        "sustained_threshold": args.sustained_threshold,
        "auto_fallback_min_kept_ratio": args.auto_fallback_min_kept_ratio,
        "hysteresis_start_threshold": args.hysteresis_start_threshold,
        "hysteresis_continue_threshold": args.hysteresis_continue_threshold,
        "max_inactive_seconds": args.max_inactive_seconds,
        "quality_peak_threshold": args.quality_peak_threshold,
        "min_quality_peak_count": args.min_quality_peak_count,
        "quality_active_threshold": args.quality_active_threshold,
        "min_quality_active_average": args.min_quality_active_average,
        "quality_trim_threshold": args.quality_trim_threshold,
        "strong_tail_trim_peak_threshold": args.strong_tail_trim_peak_threshold,
        "strong_tail_trim_min_tail_seconds": args.strong_tail_trim_min_tail_seconds,
        "strong_tail_trim_padding_seconds": args.strong_tail_trim_padding_seconds,
        "audio_filter_max_segment_seconds": args.audio_filter_max_segment_seconds,
        "audio_peak_threshold": args.audio_peak_threshold,
        "audio_min_peak_count": args.audio_min_peak_count,
        "audio_bridge_gap_seconds": args.audio_bridge_gap_seconds,
        "audio_bridge_peak_threshold": args.audio_bridge_peak_threshold,
        "audio_bridge_min_peak_count": args.audio_bridge_min_peak_count,
        "audio_tail_trim_min_segment_seconds": args.audio_tail_trim_min_segment_seconds,
        "audio_tail_padding_seconds": args.audio_tail_padding_seconds,
        "min_rally_seconds": args.min_rally_seconds,
        "merge_gap_seconds": args.merge_gap_seconds,
        "pre_roll_seconds": args.pre_roll_seconds,
        "post_roll_seconds": args.post_roll_seconds,
        "ignore_initial_seconds": args.ignore_initial_seconds,
    }
    for key, value in overrides.items():
        if value is not None:
            setattr(config, key, value)
    return config


if __name__ == "__main__":
    raise SystemExit(main())
