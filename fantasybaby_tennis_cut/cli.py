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
        "--model-assist",
        choices=["off", "ball"],
        help="Use an optional open-source model to refine rally continuity.",
    )
    parser.add_argument(
        "--model-ball-model",
        help="YOLO tennis-ball model path or Hugging Face repo id used when --model-assist ball is enabled.",
    )
    parser.add_argument("--model-ball-sample-fps", type=float, help="Frames per second sampled for ball detection.")
    parser.add_argument("--model-ball-confidence", type=float, help="Minimum ball detection confidence.")
    parser.add_argument(
        "--model-ball-bridge-min-confidence",
        type=float,
        help="Minimum confidence among moving-ball detections before bridging a cut gap.",
    )
    parser.add_argument("--model-ball-image-size", type=int, help="YOLO inference image size for ball detection.")
    parser.add_argument(
        "--model-ball-candidate-gap-seconds",
        type=float,
        help="Only run ball detection around existing cut gaps up to this length.",
    )
    parser.add_argument(
        "--model-ball-max-gap-seconds",
        type=float,
        help="Maximum gap between moving-ball detections considered the same rally.",
    )
    parser.add_argument(
        "--model-ball-min-active-seconds",
        type=float,
        help="Minimum moving-ball cluster duration before model assist adds a rally segment.",
    )
    parser.add_argument(
        "--model-ball-min-detections",
        type=int,
        help="Minimum moving-ball detections before model assist adds a rally segment.",
    )
    parser.add_argument(
        "--model-ball-min-motion-ratio",
        type=float,
        help="Minimum normalized ball displacement between detections to count as active play.",
    )
    parser.add_argument(
        "--model-ball-bridge-padding-seconds",
        type=float,
        help="Padding around model-detected moving-ball rally clusters.",
    )
    parser.add_argument(
        "--model-ball-max-bridges",
        type=int,
        help="Maximum number of model-assisted cut gaps to bridge per video.",
    )
    parser.add_argument(
        "--model-ball-trim-silent-gaps",
        action=argparse.BooleanOptionalAction,
        help="Allow model assist to trim long gaps without moving-ball detections inside kept segments.",
    )
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
    parser.add_argument("--audio-filter-min-peak-span-seconds", type=float, help="For short segments, require audio peaks to span at least this long.")
    parser.add_argument(
        "--audio-bridge-gap-seconds",
        type=float,
        help="Merge nearby visual segments when audio transients continue through the gap.",
    )
    parser.add_argument("--audio-bridge-peak-threshold", type=float, help="Override bridge audio threshold.")
    parser.add_argument("--audio-bridge-min-peak-count", type=int, help="Override bridge audio peak count.")
    parser.add_argument("--audio-soft-bridge-gap-seconds", type=float, help="Bridge medium gaps between substantial rallies when soft audio hints suggest continuity.")
    parser.add_argument("--audio-soft-bridge-peak-threshold", type=float, help="Override soft continuity bridge audio threshold.")
    parser.add_argument("--audio-soft-bridge-min-peak-count", type=int, help="Override soft continuity bridge peak count.")
    parser.add_argument("--audio-soft-bridge-min-previous-seconds", type=float, help="Minimum previous segment length before soft continuity bridge applies.")
    parser.add_argument("--audio-soft-bridge-min-next-seconds", type=float, help="Minimum next segment length before soft continuity bridge applies.")
    parser.add_argument("--audio-gap-rescue-gap-seconds", type=float, help="Recover short missing gaps between kept segments when audio hits continue inside the gap.")
    parser.add_argument("--audio-gap-rescue-peak-threshold", type=float, help="Override missing-gap rescue audio threshold.")
    parser.add_argument("--audio-gap-rescue-min-peak-count", type=int, help="Override missing-gap rescue peak count.")
    parser.add_argument("--audio-gap-rescue-min-peak-span-seconds", type=float, help="Override missing-gap rescue minimum peak span.")
    parser.add_argument("--audio-gap-rescue-pre-padding-seconds", type=float, help="Padding before missing-gap rescue peaks.")
    parser.add_argument("--audio-gap-rescue-post-padding-seconds", type=float, help="Padding after missing-gap rescue peaks.")
    parser.add_argument("--audio-gap-cluster-rescue-min-gap-seconds", type=float, help="Recover longer missing gaps when sustained audio hit clusters and visual motion agree.")
    parser.add_argument("--audio-gap-cluster-rescue-peak-threshold", type=float, help="Override long-gap cluster rescue audio threshold.")
    parser.add_argument("--audio-gap-cluster-rescue-gap-seconds", type=float, help="Maximum gap inside a long-gap rescue audio cluster.")
    parser.add_argument("--audio-gap-cluster-rescue-min-peak-count", type=int, help="Minimum peaks per long-gap rescue audio cluster.")
    parser.add_argument("--audio-gap-cluster-rescue-min-cluster-seconds", type=float, help="Minimum span for a long-gap rescue audio cluster.")
    parser.add_argument("--audio-gap-cluster-rescue-visual-threshold", type=float, help="Visual score threshold for long-gap cluster rescue.")
    parser.add_argument("--audio-gap-cluster-rescue-min-visual-seconds", type=float, help="Minimum visual activity span for long-gap cluster rescue.")
    parser.add_argument("--audio-gap-cluster-rescue-pre-padding-seconds", type=float, help="Padding before a long-gap rescue audio cluster.")
    parser.add_argument("--audio-gap-cluster-rescue-post-padding-seconds", type=float, help="Padding after a long-gap rescue audio cluster.")
    parser.add_argument("--visual-audio-gap-rescue-max-gap-seconds", type=float, help="Recover full medium gaps when visual motion and audio hits both indicate an omitted rally.")
    parser.add_argument("--visual-audio-gap-rescue-min-anchor-seconds", type=float, help="Minimum neighboring segment length for full visual/audio gap rescue.")
    parser.add_argument("--visual-audio-gap-rescue-visual-threshold", type=float, help="Visual score threshold for full visual/audio gap rescue.")
    parser.add_argument("--visual-audio-gap-rescue-min-visual-seconds", type=float, help="Minimum visual activity span for full visual/audio gap rescue.")
    parser.add_argument("--visual-audio-gap-rescue-audio-threshold", type=float, help="Audio transient threshold for full visual/audio gap rescue.")
    parser.add_argument("--visual-audio-gap-rescue-min-audio-peaks", type=int, help="Minimum audio peaks for full visual/audio gap rescue.")
    parser.add_argument("--visual-audio-gap-rescue-min-audio-span-seconds", type=float, help="Minimum audio peak span for full visual/audio gap rescue.")
    parser.add_argument("--visual-audio-soft-bridge-gap-seconds", type=float, help="Bridge short continuity gaps when both visual motion and audio hits span the gap.")
    parser.add_argument("--visual-audio-soft-bridge-visual-threshold", type=float, help="Visual score threshold for short visual/audio continuity bridging.")
    parser.add_argument("--visual-audio-soft-bridge-min-visual-seconds", type=float, help="Minimum visual activity span for short visual/audio continuity bridging.")
    parser.add_argument("--visual-audio-soft-bridge-audio-threshold", type=float, help="Audio transient threshold for short visual/audio continuity bridging.")
    parser.add_argument("--visual-audio-soft-bridge-min-audio-peaks", type=int, help="Minimum audio peaks for short visual/audio continuity bridging.")
    parser.add_argument("--visual-audio-soft-bridge-min-audio-span-seconds", type=float, help="Minimum audio peak span for short visual/audio continuity bridging.")
    parser.add_argument("--visual-audio-soft-bridge-min-combined-seconds", type=float, help="Minimum combined duration of neighboring clips for short visual/audio continuity bridging.")
    parser.add_argument("--audio-lead-trim-min-segment-seconds", type=float, help="Trim long dead-ball lead-ins from segments at least this long.")
    parser.add_argument("--audio-lead-trim-peak-threshold", type=float, help="Audio threshold used to find the first strong hit for lead trimming.")
    parser.add_argument("--audio-lead-trim-min-lead-seconds", type=float, help="Minimum quiet lead-in before trimming applies.")
    parser.add_argument("--audio-lead-trim-padding-seconds", type=float, help="Seconds kept before the first strong hit when trimming a lead-in.")
    parser.add_argument(
        "--audio-split-min-segment-seconds",
        type=float,
        help="Split visual segments longer than this duration by audio transient clusters.",
    )
    parser.add_argument("--audio-split-peak-threshold", type=float, help="Override audio split peak threshold.")
    parser.add_argument("--audio-split-gap-seconds", type=float, help="Override maximum gap inside an audio split cluster.")
    parser.add_argument("--audio-split-min-peak-count", type=int, help="Override minimum peaks per audio split cluster.")
    parser.add_argument("--audio-split-pre-padding-seconds", type=float, help="Padding before an audio split cluster.")
    parser.add_argument("--audio-split-post-padding-seconds", type=float, help="Padding after an audio split cluster.")
    parser.add_argument(
        "--audio-rally-bridge-min-cluster-seconds",
        type=float,
        help="Bridge fragmented visual segments when an audio cluster spans at least this duration.",
    )
    parser.add_argument("--audio-rally-bridge-peak-threshold", type=float, help="Override rally bridge audio threshold.")
    parser.add_argument("--audio-rally-bridge-gap-seconds", type=float, help="Override maximum gap inside a rally bridge audio cluster.")
    parser.add_argument("--audio-rally-bridge-min-peak-count", type=int, help="Override minimum peaks per rally bridge cluster.")
    parser.add_argument("--audio-rally-bridge-min-visual-segments", type=int, help="Override minimum visual segments near a rally bridge cluster.")
    parser.add_argument("--audio-rally-bridge-pre-padding-seconds", type=float, help="Padding before a rally bridge audio cluster.")
    parser.add_argument("--audio-rally-bridge-post-padding-seconds", type=float, help="Padding after a rally bridge audio cluster.")
    parser.add_argument("--audio-rally-bridge-suppress-after-seconds", type=float, help="Drop visual-only dead-ball segments shortly after a bridged rally.")
    parser.add_argument("--audio-rally-rescue-peak-threshold", type=float, help="Recover low-motion rallies from softer audio transient clusters.")
    parser.add_argument("--audio-rally-rescue-gap-seconds", type=float, help="Maximum gap inside a softer audio rescue cluster.")
    parser.add_argument("--audio-rally-rescue-min-peak-count", type=int, help="Minimum peaks per softer audio rescue cluster.")
    parser.add_argument("--audio-rally-rescue-min-cluster-seconds", type=float, help="Minimum duration for a softer audio rescue cluster.")
    parser.add_argument("--audio-rally-rescue-start-seconds", type=float, help="Only apply softer audio rescue after this timestamp.")
    parser.add_argument("--audio-rally-rescue-end-seconds", type=float, help="Stop softer audio rescue at this timestamp; 0 means no limit.")
    parser.add_argument("--audio-rally-rescue-pre-padding-seconds", type=float, help="Padding before a softer audio rescue cluster.")
    parser.add_argument("--audio-rally-rescue-post-padding-seconds", type=float, help="Padding after a softer audio rescue cluster.")
    parser.add_argument(
        "--audio-tail-trim-min-segment-seconds",
        type=float,
        help="Trim long segment tails after the final audio transient.",
    )
    parser.add_argument("--audio-tail-padding-seconds", type=float, help="Padding after final audio transient.")
    parser.add_argument(
        "--audio-silent-gap-trim-min-segment-seconds",
        type=float,
        help="Trim long no-hit gaps inside kept segments at least this long.",
    )
    parser.add_argument(
        "--audio-silent-gap-trim-peak-threshold",
        type=float,
        help="Audio threshold used to detect hits around long silent gaps.",
    )
    parser.add_argument(
        "--audio-silent-gap-trim-gap-seconds",
        type=float,
        help="Minimum no-hit gap inside a kept segment before trimming applies.",
    )
    parser.add_argument(
        "--audio-silent-gap-trim-pre-padding-seconds",
        type=float,
        help="Seconds kept after the previous hit before trimming a silent gap.",
    )
    parser.add_argument(
        "--audio-silent-gap-trim-post-padding-seconds",
        type=float,
        help="Seconds kept before the next hit after trimming a silent gap.",
    )
    parser.add_argument("--min-rally-seconds", type=float, help="Override minimum rally duration.")
    parser.add_argument("--merge-gap-seconds", type=float, help="Override maximum gap to merge.")
    parser.add_argument("--final-continuity-merge-gap-seconds", type=float, help="Final merge for short gaps after all filters; favors complete rallies over tighter dead-ball cuts.")
    parser.add_argument("--pre-roll-seconds", type=float, help="Override leading padding.")
    parser.add_argument("--post-roll-seconds", type=float, help="Override trailing padding.")
    parser.add_argument("--serve-pre-roll-seconds", type=float, help="Longer leading padding for rallies after a dead-time gap, useful for toss/serve setup.")
    parser.add_argument("--serve-pre-roll-gap-seconds", type=float, help="Minimum previous gap before serve pre-roll padding applies.")
    parser.add_argument("--ignore-initial-seconds", type=float, help="Ignore initial dead time.")
    parser.add_argument(
        "--prefer-stream-copy",
        action=argparse.BooleanOptionalAction,
        help="Prefer copying original video/audio streams to preserve source bitrate.",
    )
    parser.add_argument(
        "--preserve-source-bitrate",
        action=argparse.BooleanOptionalAction,
        help="When re-encoding, target the source video bitrate instead of CRF.",
    )
    parser.add_argument("--fallback-crf", type=int, help="CRF used only when stream copy fails and re-encoding is required.")
    parser.add_argument("--fallback-preset", help="x264 preset used only when re-encoding is required.")
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
    from .model_assist import refine_segments_with_model
    from .renderer import VideoRenderer, write_timeline

    analyzer = VideoAnalyzer(config)
    analysis = analyzer.analyze(input_path)
    detector = RallyDetector(config)
    segments = detector.detect(analysis)
    segments = filter_segments_by_audio(input_path, segments, config, analysis.samples)
    segments = refine_segments_with_model(input_path, segments, config)

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
    print("FantasyBaby Tennis Cut")
    print("Select video type:")
    print("  1. Serve training")
    print("  2. Doubles match")
    print("  3. Singles match")

    if args.video_type is None:
        args.video_type = _prompt_choice("Enter video type (1/2/3): ", {"1", "2", "3"})

    args.input = _prompt_path("Enter input video path: ", must_exist=True)
    args.output = _prompt_path("Enter output video path: ", must_exist=False)
    return args


def _prompt_choice(prompt: str, choices: set[str]) -> str:
    while True:
        value = input(prompt).strip()
        if value in choices:
            return value
        print(f"Please enter one of: {', '.join(sorted(choices))}")


def _prompt_path(prompt: str, *, must_exist: bool) -> str:
    while True:
        value = _clean_pasted_path(input(prompt))
        if not value:
            print("Path cannot be empty.")
            continue

        path = Path(value)
        if must_exist and not path.exists():
            print(f"Path not found: {path}")
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
        "audio_filter_min_peak_span_seconds": args.audio_filter_min_peak_span_seconds,
        "audio_bridge_gap_seconds": args.audio_bridge_gap_seconds,
        "audio_bridge_peak_threshold": args.audio_bridge_peak_threshold,
        "audio_bridge_min_peak_count": args.audio_bridge_min_peak_count,
        "audio_soft_bridge_gap_seconds": args.audio_soft_bridge_gap_seconds,
        "audio_soft_bridge_peak_threshold": args.audio_soft_bridge_peak_threshold,
        "audio_soft_bridge_min_peak_count": args.audio_soft_bridge_min_peak_count,
        "audio_soft_bridge_min_previous_seconds": args.audio_soft_bridge_min_previous_seconds,
        "audio_soft_bridge_min_next_seconds": args.audio_soft_bridge_min_next_seconds,
        "audio_gap_rescue_gap_seconds": args.audio_gap_rescue_gap_seconds,
        "audio_gap_rescue_peak_threshold": args.audio_gap_rescue_peak_threshold,
        "audio_gap_rescue_min_peak_count": args.audio_gap_rescue_min_peak_count,
        "audio_gap_rescue_min_peak_span_seconds": args.audio_gap_rescue_min_peak_span_seconds,
        "audio_gap_rescue_pre_padding_seconds": args.audio_gap_rescue_pre_padding_seconds,
        "audio_gap_rescue_post_padding_seconds": args.audio_gap_rescue_post_padding_seconds,
        "audio_gap_cluster_rescue_min_gap_seconds": args.audio_gap_cluster_rescue_min_gap_seconds,
        "audio_gap_cluster_rescue_peak_threshold": args.audio_gap_cluster_rescue_peak_threshold,
        "audio_gap_cluster_rescue_gap_seconds": args.audio_gap_cluster_rescue_gap_seconds,
        "audio_gap_cluster_rescue_min_peak_count": args.audio_gap_cluster_rescue_min_peak_count,
        "audio_gap_cluster_rescue_min_cluster_seconds": args.audio_gap_cluster_rescue_min_cluster_seconds,
        "audio_gap_cluster_rescue_visual_threshold": args.audio_gap_cluster_rescue_visual_threshold,
        "audio_gap_cluster_rescue_min_visual_seconds": args.audio_gap_cluster_rescue_min_visual_seconds,
        "audio_gap_cluster_rescue_pre_padding_seconds": args.audio_gap_cluster_rescue_pre_padding_seconds,
        "audio_gap_cluster_rescue_post_padding_seconds": args.audio_gap_cluster_rescue_post_padding_seconds,
        "visual_audio_gap_rescue_max_gap_seconds": args.visual_audio_gap_rescue_max_gap_seconds,
        "visual_audio_gap_rescue_min_anchor_seconds": args.visual_audio_gap_rescue_min_anchor_seconds,
        "visual_audio_gap_rescue_visual_threshold": args.visual_audio_gap_rescue_visual_threshold,
        "visual_audio_gap_rescue_min_visual_seconds": args.visual_audio_gap_rescue_min_visual_seconds,
        "visual_audio_gap_rescue_audio_threshold": args.visual_audio_gap_rescue_audio_threshold,
        "visual_audio_gap_rescue_min_audio_peaks": args.visual_audio_gap_rescue_min_audio_peaks,
        "visual_audio_gap_rescue_min_audio_span_seconds": args.visual_audio_gap_rescue_min_audio_span_seconds,
        "visual_audio_soft_bridge_gap_seconds": args.visual_audio_soft_bridge_gap_seconds,
        "visual_audio_soft_bridge_visual_threshold": args.visual_audio_soft_bridge_visual_threshold,
        "visual_audio_soft_bridge_min_visual_seconds": args.visual_audio_soft_bridge_min_visual_seconds,
        "visual_audio_soft_bridge_audio_threshold": args.visual_audio_soft_bridge_audio_threshold,
        "visual_audio_soft_bridge_min_audio_peaks": args.visual_audio_soft_bridge_min_audio_peaks,
        "visual_audio_soft_bridge_min_audio_span_seconds": args.visual_audio_soft_bridge_min_audio_span_seconds,
        "visual_audio_soft_bridge_min_combined_seconds": args.visual_audio_soft_bridge_min_combined_seconds,
        "audio_lead_trim_min_segment_seconds": args.audio_lead_trim_min_segment_seconds,
        "audio_lead_trim_peak_threshold": args.audio_lead_trim_peak_threshold,
        "audio_lead_trim_min_lead_seconds": args.audio_lead_trim_min_lead_seconds,
        "audio_lead_trim_padding_seconds": args.audio_lead_trim_padding_seconds,
        "audio_split_min_segment_seconds": args.audio_split_min_segment_seconds,
        "audio_split_peak_threshold": args.audio_split_peak_threshold,
        "audio_split_gap_seconds": args.audio_split_gap_seconds,
        "audio_split_min_peak_count": args.audio_split_min_peak_count,
        "audio_split_pre_padding_seconds": args.audio_split_pre_padding_seconds,
        "audio_split_post_padding_seconds": args.audio_split_post_padding_seconds,
        "audio_rally_bridge_min_cluster_seconds": args.audio_rally_bridge_min_cluster_seconds,
        "audio_rally_bridge_peak_threshold": args.audio_rally_bridge_peak_threshold,
        "audio_rally_bridge_gap_seconds": args.audio_rally_bridge_gap_seconds,
        "audio_rally_bridge_min_peak_count": args.audio_rally_bridge_min_peak_count,
        "audio_rally_bridge_min_visual_segments": args.audio_rally_bridge_min_visual_segments,
        "audio_rally_bridge_pre_padding_seconds": args.audio_rally_bridge_pre_padding_seconds,
        "audio_rally_bridge_post_padding_seconds": args.audio_rally_bridge_post_padding_seconds,
        "audio_rally_bridge_suppress_after_seconds": args.audio_rally_bridge_suppress_after_seconds,
        "audio_rally_rescue_peak_threshold": args.audio_rally_rescue_peak_threshold,
        "audio_rally_rescue_gap_seconds": args.audio_rally_rescue_gap_seconds,
        "audio_rally_rescue_min_peak_count": args.audio_rally_rescue_min_peak_count,
        "audio_rally_rescue_min_cluster_seconds": args.audio_rally_rescue_min_cluster_seconds,
        "audio_rally_rescue_start_seconds": args.audio_rally_rescue_start_seconds,
        "audio_rally_rescue_end_seconds": args.audio_rally_rescue_end_seconds,
        "audio_rally_rescue_pre_padding_seconds": args.audio_rally_rescue_pre_padding_seconds,
        "audio_rally_rescue_post_padding_seconds": args.audio_rally_rescue_post_padding_seconds,
        "audio_tail_trim_min_segment_seconds": args.audio_tail_trim_min_segment_seconds,
        "audio_tail_padding_seconds": args.audio_tail_padding_seconds,
        "audio_silent_gap_trim_min_segment_seconds": args.audio_silent_gap_trim_min_segment_seconds,
        "audio_silent_gap_trim_peak_threshold": args.audio_silent_gap_trim_peak_threshold,
        "audio_silent_gap_trim_gap_seconds": args.audio_silent_gap_trim_gap_seconds,
        "audio_silent_gap_trim_pre_padding_seconds": args.audio_silent_gap_trim_pre_padding_seconds,
        "audio_silent_gap_trim_post_padding_seconds": args.audio_silent_gap_trim_post_padding_seconds,
        "min_rally_seconds": args.min_rally_seconds,
        "merge_gap_seconds": args.merge_gap_seconds,
        "final_continuity_merge_gap_seconds": args.final_continuity_merge_gap_seconds,
        "pre_roll_seconds": args.pre_roll_seconds,
        "post_roll_seconds": args.post_roll_seconds,
        "serve_pre_roll_seconds": args.serve_pre_roll_seconds,
        "serve_pre_roll_gap_seconds": args.serve_pre_roll_gap_seconds,
        "ignore_initial_seconds": args.ignore_initial_seconds,
        "model_assist_mode": args.model_assist,
        "model_ball_model": args.model_ball_model,
        "model_ball_sample_fps": args.model_ball_sample_fps,
        "model_ball_confidence": args.model_ball_confidence,
        "model_ball_bridge_min_confidence": args.model_ball_bridge_min_confidence,
        "model_ball_image_size": args.model_ball_image_size,
        "model_ball_candidate_gap_seconds": args.model_ball_candidate_gap_seconds,
        "model_ball_max_gap_seconds": args.model_ball_max_gap_seconds,
        "model_ball_min_active_seconds": args.model_ball_min_active_seconds,
        "model_ball_min_detections": args.model_ball_min_detections,
        "model_ball_min_motion_ratio": args.model_ball_min_motion_ratio,
        "model_ball_bridge_padding_seconds": args.model_ball_bridge_padding_seconds,
        "model_ball_max_bridges": args.model_ball_max_bridges,
        "model_ball_trim_silent_gaps": args.model_ball_trim_silent_gaps,
        "prefer_stream_copy": args.prefer_stream_copy,
        "preserve_source_bitrate": args.preserve_source_bitrate,
        "fallback_crf": args.fallback_crf,
        "fallback_preset": args.fallback_preset,
    }
    for key, value in overrides.items():
        if value is not None:
            setattr(config, key, value)
    return config


if __name__ == "__main__":
    raise SystemExit(main())
