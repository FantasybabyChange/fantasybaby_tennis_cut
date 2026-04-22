from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from .config import CutConfig
from .segments import Segment, filter_short_segments, merge_segments


def filter_segments_by_audio(
    input_path: str | Path,
    segments: list[Segment],
    config: CutConfig,
    visual_samples: list[Any] | None = None,
) -> list[Segment]:
    if not segments:
        return segments

    max_duration = config.audio_filter_max_segment_seconds
    bridge_gap = config.audio_bridge_gap_seconds
    soft_bridge_gap = config.audio_soft_bridge_gap_seconds
    gap_rescue = config.audio_gap_rescue_gap_seconds
    gap_cluster_rescue = config.audio_gap_cluster_rescue_min_gap_seconds
    visual_audio_gap_rescue = config.visual_audio_gap_rescue_max_gap_seconds
    visual_audio_soft_bridge = config.visual_audio_soft_bridge_gap_seconds
    lead_trim_min_duration = config.audio_lead_trim_min_segment_seconds
    split_min_duration = config.audio_split_min_segment_seconds
    rally_bridge_min_duration = config.audio_rally_bridge_min_cluster_seconds
    rally_rescue_threshold = config.audio_rally_rescue_peak_threshold
    tail_trim_min_duration = config.audio_tail_trim_min_segment_seconds
    if (
        max_duration <= 0
        and bridge_gap <= 0
        and soft_bridge_gap <= 0
        and gap_rescue <= 0
        and gap_cluster_rescue <= 0
        and visual_audio_gap_rescue <= 0
        and visual_audio_soft_bridge <= 0
        and lead_trim_min_duration <= 0
        and split_min_duration <= 0
        and rally_bridge_min_duration <= 0
        and rally_rescue_threshold <= 0
        and tail_trim_min_duration <= 0
    ):
        return segments

    try:
        track = _load_transient_track(input_path)
    except Exception as exc:  # pragma: no cover - best-effort media helper
        print(f"Warning: audio filter skipped ({exc}).")
        return segments

    filtered = segments
    if max_duration > 0:
        filtered = _filter_short_segments_by_audio(track, segments, config)

    if split_min_duration > 0:
        filtered = _split_long_segments_by_audio(track, filtered, config)

    if rally_bridge_min_duration > 0:
        filtered = _bridge_long_rallies_by_audio(track, filtered, config)

    if rally_rescue_threshold > 0:
        filtered = _rescue_audio_rallies(track, filtered, config)

    if bridge_gap > 0:
        filtered = _bridge_segments_by_audio(track, filtered, config)

    if gap_rescue > 0:
        filtered = _rescue_audio_gaps(track, filtered, config)

    if visual_audio_gap_rescue > 0:
        filtered = _rescue_visual_audio_gaps(track, filtered, config, visual_samples)

    if gap_cluster_rescue > 0:
        filtered = _rescue_audio_clusters_in_gaps(track, filtered, config, visual_samples)

    if lead_trim_min_duration > 0:
        filtered = _trim_long_leads_by_audio(track, filtered, config)

    if visual_audio_gap_rescue > 0:
        filtered = _rescue_visual_audio_gaps(track, filtered, config, visual_samples)

    if visual_audio_soft_bridge > 0:
        filtered = _bridge_visual_audio_soft_gaps(track, filtered, config, visual_samples)

    if soft_bridge_gap > 0:
        filtered = _bridge_soft_continuity_gaps(track, filtered, config)

    if tail_trim_min_duration > 0:
        filtered = _trim_long_tails_by_audio(track, filtered, config)

    if config.final_continuity_merge_gap_seconds > config.merge_gap_seconds:
        filtered = merge_segments(filtered, config.final_continuity_merge_gap_seconds)

    return filtered


def _split_long_segments_by_audio(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    split_segments: list[Segment] = []
    for segment in segments:
        if segment.duration < config.audio_split_min_segment_seconds:
            split_segments.append(segment)
            continue

        clusters = track.peak_clusters(
            segment.start,
            segment.end,
            threshold=config.audio_split_peak_threshold,
            max_gap_seconds=config.audio_split_gap_seconds,
        )
        usable_clusters = [
            cluster
            for cluster in clusters
            if len(cluster) >= config.audio_split_min_peak_count
        ]
        if not usable_clusters:
            split_segments.append(segment)
            continue

        for cluster in usable_clusters:
            start = max(segment.start, cluster[0] - config.audio_split_pre_padding_seconds)
            end = min(segment.end, cluster[-1] + config.audio_split_post_padding_seconds)
            if end > start:
                split_segments.append(Segment(start, end, segment.score))

    merged = merge_segments(split_segments, config.merge_gap_seconds)
    return filter_short_segments(merged, config.min_rally_seconds)


def _bridge_long_rallies_by_audio(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    bridge_segments: list[Segment] = []
    suppress_windows: list[tuple[float, float]] = []
    tight_gap = min(config.audio_rally_bridge_gap_seconds, 8.0)
    clusters = _link_rally_audio_clusters(
        track.peak_clusters(
            0.0,
            len(track.scores) * track.window_seconds,
            threshold=config.audio_rally_bridge_peak_threshold,
            max_gap_seconds=tight_gap,
        ),
        max_link_gap_seconds=config.audio_rally_bridge_gap_seconds,
        min_peak_count=config.audio_rally_bridge_min_peak_count,
        min_cluster_seconds=config.audio_rally_bridge_min_cluster_seconds,
        ignore_before_seconds=config.ignore_initial_seconds,
    )
    for cluster in clusters:
        if len(cluster) < config.audio_rally_bridge_min_peak_count:
            continue

        cluster_duration = cluster[-1] - cluster[0]
        if cluster_duration < config.audio_rally_bridge_min_cluster_seconds:
            continue

        start = max(
            config.ignore_initial_seconds,
            cluster[0] - config.audio_rally_bridge_pre_padding_seconds,
        )
        end = cluster[-1] + config.audio_rally_bridge_post_padding_seconds
        visual_count = _count_nearby_segments(segments, start, end, config.merge_gap_seconds)
        if visual_count < config.audio_rally_bridge_min_visual_segments:
            continue

        bridge_segments.append(Segment(start, end, 0.0))
        if config.audio_rally_bridge_suppress_after_seconds > 0:
            suppress_windows.append(
                (end, end + config.audio_rally_bridge_suppress_after_seconds)
            )

    bridged = [
        segment
        for segment in segments
        if not _is_suppressed_after_bridge(segment, suppress_windows)
    ]
    bridged.extend(bridge_segments)
    merged = merge_segments(bridged, config.merge_gap_seconds)
    return filter_short_segments(merged, config.min_rally_seconds)


def _rescue_audio_rallies(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    start_time = max(config.ignore_initial_seconds, config.audio_rally_rescue_start_seconds)
    end_time = (
        config.audio_rally_rescue_end_seconds
        if config.audio_rally_rescue_end_seconds > start_time
        else len(track.scores) * track.window_seconds
    )
    clusters = track.peak_clusters(
        start_time,
        end_time,
        threshold=config.audio_rally_rescue_peak_threshold,
        max_gap_seconds=config.audio_rally_rescue_gap_seconds,
    )

    rescued = list(segments)
    for cluster in clusters:
        if not _is_significant_audio_cluster(
            cluster,
            min_peak_count=config.audio_rally_rescue_min_peak_count,
            min_cluster_seconds=config.audio_rally_rescue_min_cluster_seconds,
        ):
            continue

        start = max(
            config.ignore_initial_seconds,
            cluster[0] - config.audio_rally_rescue_pre_padding_seconds,
        )
        end = cluster[-1] + config.audio_rally_rescue_post_padding_seconds
        if end > start:
            rescued.append(Segment(start, end, 0.0))

    merged = merge_segments(rescued, config.merge_gap_seconds)
    return filter_short_segments(merged, config.min_rally_seconds)


def _link_rally_audio_clusters(
    clusters: list[list[float]],
    *,
    max_link_gap_seconds: float,
    min_peak_count: int,
    min_cluster_seconds: float,
    ignore_before_seconds: float,
) -> list[list[float]]:
    if not clusters:
        return []

    clusters = [cluster for cluster in clusters if cluster[-1] >= ignore_before_seconds]
    if not clusters:
        return []

    linked: list[list[float]] = []
    current = list(clusters[0])
    for cluster in clusters[1:]:
        gap = cluster[0] - current[-1]
        current_is_significant = _is_significant_audio_cluster(
            current,
            min_peak_count=min_peak_count,
            min_cluster_seconds=min_cluster_seconds,
        )
        next_is_significant = _is_significant_audio_cluster(
            cluster,
            min_peak_count=min_peak_count,
            min_cluster_seconds=min_cluster_seconds,
        )
        early_lead = (
            not current_is_significant
            and current[0] <= ignore_before_seconds + max_link_gap_seconds
        )
        # Link only the tiny pre-rally lead-in at the very start. Linking every
        # significant cluster later in the match tends to swallow dead-ball walks.
        should_link = gap <= max_link_gap_seconds and next_is_significant and early_lead
        if should_link:
            current.extend(cluster)
            continue

        linked.append(current)
        current = list(cluster)

    linked.append(current)
    return linked


def _is_significant_audio_cluster(
    cluster: list[float],
    *,
    min_peak_count: int,
    min_cluster_seconds: float,
) -> bool:
    return len(cluster) >= min_peak_count and cluster[-1] - cluster[0] >= min_cluster_seconds


def _count_nearby_segments(
    segments: list[Segment],
    start: float,
    end: float,
    tolerance: float,
) -> int:
    return sum(
        1
        for segment in segments
        if segment.end >= start - tolerance and segment.start <= end + tolerance
    )


def _is_suppressed_after_bridge(
    segment: Segment,
    windows: list[tuple[float, float]],
) -> bool:
    return any(start < segment.start <= end for start, end in windows)


def _filter_short_segments_by_audio(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    max_duration = config.audio_filter_max_segment_seconds
    filtered: list[Segment] = []
    for segment in segments:
        if segment.duration > max_duration:
            filtered.append(segment)
            continue

        peak_times = track.peak_times(
            segment.start,
            segment.end,
            threshold=config.audio_peak_threshold,
        )
        if len(peak_times) < config.audio_min_peak_count:
            continue

        if (
            config.audio_filter_min_peak_span_seconds > 0
            and peak_times[-1] - peak_times[0] < config.audio_filter_min_peak_span_seconds
        ):
            continue

        filtered.append(segment)

    return filtered


def _bridge_segments_by_audio(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    if len(segments) < 2:
        return segments

    merged: list[Segment] = [Segment(segments[0].start, segments[0].end, segments[0].score)]
    for segment in segments[1:]:
        previous = merged[-1]
        gap = segment.start - previous.end
        bridge_count = track.count_peaks(
            previous.end,
            segment.start,
            threshold=config.audio_bridge_peak_threshold,
        )
        if 0 <= gap <= config.audio_bridge_gap_seconds and bridge_count >= config.audio_bridge_min_peak_count:
            total_duration = previous.duration + segment.duration
            if total_duration > 0:
                previous.score = (
                    previous.score * previous.duration + segment.score * segment.duration
                ) / total_duration
            else:
                previous.score = max(previous.score, segment.score)
            previous.end = max(previous.end, segment.end)
        else:
            merged.append(Segment(segment.start, segment.end, segment.score))

    return merged


def _rescue_audio_gaps(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    if len(segments) < 2:
        return segments

    rescued = list(segments)
    final_gap = max(config.merge_gap_seconds, config.final_continuity_merge_gap_seconds)
    for previous, segment in zip(segments, segments[1:]):
        gap = segment.start - previous.end
        if gap <= final_gap or gap > config.audio_gap_rescue_gap_seconds:
            continue

        peak_times = track.peak_times(
            previous.end,
            segment.start,
            threshold=config.audio_gap_rescue_peak_threshold,
        )
        if len(peak_times) < config.audio_gap_rescue_min_peak_count:
            continue
        if peak_times[-1] - peak_times[0] < config.audio_gap_rescue_min_peak_span_seconds:
            continue

        # The bridge only needs to get close enough for the final continuity
        # merge to keep the rally whole; it intentionally favors completeness.
        start = max(
            previous.end,
            min(
                peak_times[0] - config.audio_gap_rescue_pre_padding_seconds,
                previous.end + final_gap,
            ),
        )
        end = min(
            segment.start,
            max(
                peak_times[-1] + config.audio_gap_rescue_post_padding_seconds,
                segment.start - final_gap,
            ),
        )
        if end > start:
            rescued.append(Segment(start, end, 0.0))

    return merge_segments(rescued, config.merge_gap_seconds)


def _rescue_audio_clusters_in_gaps(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
    visual_samples: list[Any] | None,
) -> list[Segment]:
    if len(segments) < 2:
        return segments

    rescued = list(segments)
    for previous, segment in zip(segments, segments[1:]):
        gap = segment.start - previous.end
        if gap < config.audio_gap_cluster_rescue_min_gap_seconds:
            continue

        clusters = track.peak_clusters(
            previous.end,
            segment.start,
            threshold=config.audio_gap_cluster_rescue_peak_threshold,
            max_gap_seconds=config.audio_gap_cluster_rescue_gap_seconds,
        )
        for cluster in clusters:
            if not _is_significant_audio_cluster(
                cluster,
                min_peak_count=config.audio_gap_cluster_rescue_min_peak_count,
                min_cluster_seconds=config.audio_gap_cluster_rescue_min_cluster_seconds,
            ):
                continue

            start = max(
                previous.end,
                cluster[0] - config.audio_gap_cluster_rescue_pre_padding_seconds,
            )
            end = min(
                segment.start,
                cluster[-1] + config.audio_gap_cluster_rescue_post_padding_seconds,
            )
            if end <= start:
                continue

            if not _has_visual_support(start, end, visual_samples, config):
                continue

            rescued.append(Segment(start, end, 0.0))

    merged = merge_segments(rescued, config.merge_gap_seconds)
    return filter_short_segments(merged, config.min_rally_seconds)


def _bridge_soft_continuity_gaps(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    if len(segments) < 2:
        return segments

    bridged = list(segments)
    final_gap = max(config.merge_gap_seconds, config.final_continuity_merge_gap_seconds)
    for previous, segment in zip(segments, segments[1:]):
        gap = segment.start - previous.end
        if gap <= final_gap or gap > config.audio_soft_bridge_gap_seconds:
            continue
        if previous.duration < config.audio_soft_bridge_min_previous_seconds:
            continue
        if segment.duration < config.audio_soft_bridge_min_next_seconds:
            continue

        peak_count = track.count_peaks(
            previous.end,
            segment.start,
            threshold=config.audio_soft_bridge_peak_threshold,
        )
        if peak_count < config.audio_soft_bridge_min_peak_count:
            continue

        # Weak, far-court rallies can fall below visual thresholds. Bridge only
        # between substantial kept rallies so short dead-ball pickups stay cut.
        bridged.append(Segment(previous.end, segment.start, 0.0))

    return merge_segments(bridged, config.merge_gap_seconds)


def _rescue_visual_audio_gaps(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
    visual_samples: list[Any] | None,
) -> list[Segment]:
    if len(segments) < 2 or not visual_samples:
        return segments

    rescued = list(segments)
    final_gap = max(config.merge_gap_seconds, config.final_continuity_merge_gap_seconds)
    for previous, segment in zip(segments, segments[1:]):
        gap = segment.start - previous.end
        if gap <= final_gap or gap > config.visual_audio_gap_rescue_max_gap_seconds:
            continue

        anchor_duration = max(previous.duration, segment.duration)
        if anchor_duration < config.visual_audio_gap_rescue_min_anchor_seconds:
            continue

        audio_times = track.peak_times(
            previous.end,
            segment.start,
            threshold=config.visual_audio_gap_rescue_audio_threshold,
        )
        if len(audio_times) < config.visual_audio_gap_rescue_min_audio_peaks:
            continue
        if _time_span(audio_times) < config.visual_audio_gap_rescue_min_audio_span_seconds:
            continue

        visual_times = [
            float(sample.time)
            for sample in visual_samples
            if previous.end <= float(sample.time) <= segment.start
            and float(sample.total_score) >= config.visual_audio_gap_rescue_visual_threshold
        ]
        visual_supported = (
            _time_span(visual_times) >= config.visual_audio_gap_rescue_min_visual_seconds
        )
        audio_supported = (
            gap > 35.0
            and len(audio_times) >= 6
            and _time_span(audio_times) >= 30.0
        )
        if not visual_supported and not audio_supported:
            continue

        # If both visual motion and hit audio span the gap, favor rally
        # completeness. Long far-court gaps can be visually under-scored, so a
        # dense strong-audio pattern can also protect a multi-rally sequence.
        rescued.append(Segment(previous.end, segment.start, 0.0))

    return merge_segments(rescued, config.merge_gap_seconds)


def _bridge_visual_audio_soft_gaps(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
    visual_samples: list[Any] | None,
) -> list[Segment]:
    if len(segments) < 2 or not visual_samples:
        return segments

    bridged = list(segments)
    final_gap = max(config.merge_gap_seconds, config.final_continuity_merge_gap_seconds)
    for previous, segment in zip(segments, segments[1:]):
        gap = segment.start - previous.end
        if gap <= final_gap or gap > config.visual_audio_soft_bridge_gap_seconds:
            continue

        if (
            previous.duration + segment.duration
            < config.visual_audio_soft_bridge_min_combined_seconds
        ):
            continue

        visual_times = [
            float(sample.time)
            for sample in visual_samples
            if previous.end <= float(sample.time) <= segment.start
            and float(sample.total_score) >= config.visual_audio_soft_bridge_visual_threshold
        ]
        if _time_span(visual_times) < config.visual_audio_soft_bridge_min_visual_seconds:
            continue

        audio_times = track.peak_times(
            previous.end,
            segment.start,
            threshold=config.visual_audio_soft_bridge_audio_threshold,
        )
        if len(audio_times) < config.visual_audio_soft_bridge_min_audio_peaks:
            continue
        if _time_span(audio_times) < config.visual_audio_soft_bridge_min_audio_span_seconds:
            continue

        # Short gaps with both motion and spaced hit sounds are usually a
        # continuation of the same rally, even when either side clip is short.
        bridged.append(Segment(previous.end, segment.start, 0.0))

    return merge_segments(bridged, config.merge_gap_seconds)


def _time_span(times: list[float]) -> float:
    if len(times) < 2:
        return 0.0
    return times[-1] - times[0]


def _has_visual_support(
    start: float,
    end: float,
    visual_samples: list[Any] | None,
    config: CutConfig,
) -> bool:
    if config.audio_gap_cluster_rescue_min_visual_seconds <= 0:
        return True
    if not visual_samples:
        return False

    active_times = [
        float(sample.time)
        for sample in visual_samples
        if start <= float(sample.time) <= end
        and float(sample.total_score) >= config.audio_gap_cluster_rescue_visual_threshold
    ]
    if not active_times:
        return False

    if len(active_times) == 1:
        return config.audio_gap_cluster_rescue_min_visual_seconds <= 0

    active_seconds = active_times[-1] - active_times[0]
    return active_seconds >= config.audio_gap_cluster_rescue_min_visual_seconds


def _trim_long_leads_by_audio(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    trimmed: list[Segment] = []
    for segment in segments:
        if segment.duration < config.audio_lead_trim_min_segment_seconds:
            trimmed.append(segment)
            continue

        peak_times = track.peak_times(
            segment.start,
            segment.end,
            threshold=config.audio_lead_trim_peak_threshold,
        )
        if not peak_times:
            trimmed.append(segment)
            continue

        first_peak = peak_times[0]
        lead = first_peak - segment.start
        if lead < config.audio_lead_trim_min_lead_seconds:
            trimmed.append(segment)
            continue

        start = max(segment.start, first_peak - config.audio_lead_trim_padding_seconds)
        if segment.end - start >= config.min_rally_seconds:
            trimmed.append(Segment(start, segment.end, segment.score))

    return trimmed


def _trim_long_tails_by_audio(
    track: "_TransientTrack",
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    trimmed: list[Segment] = []
    for segment in segments:
        if segment.duration < config.audio_tail_trim_min_segment_seconds:
            trimmed.append(segment)
            continue

        last_peak = track.last_peak_time(
            segment.start,
            segment.end,
            threshold=config.audio_bridge_peak_threshold,
        )
        if last_peak is None:
            trimmed.append(segment)
            continue

        end = min(segment.end, last_peak + config.audio_tail_padding_seconds)
        if end > segment.start:
            trimmed.append(Segment(segment.start, end, segment.score))

    return trimmed


class _TransientTrack:
    def __init__(self, scores: np.ndarray, window_seconds: float):
        self.scores = scores
        self.window_seconds = window_seconds

    def count_peaks(self, start: float, end: float, *, threshold: float) -> int:
        return len(self.peak_times(start, end, threshold=threshold))

    def peak_times(self, start: float, end: float, *, threshold: float) -> list[float]:
        start_index = max(0, int(start / self.window_seconds))
        end_index = min(len(self.scores), int(end / self.window_seconds) + 1)
        if end_index <= start_index:
            return []

        peak_indexes = np.flatnonzero(self.scores[start_index:end_index] >= threshold)
        return [float((start_index + int(index)) * self.window_seconds) for index in peak_indexes]

    def last_peak_time(self, start: float, end: float, *, threshold: float) -> float | None:
        start_index = max(0, int(start / self.window_seconds))
        end_index = min(len(self.scores), int(end / self.window_seconds) + 1)
        if end_index <= start_index:
            return None

        peak_indexes = np.flatnonzero(self.scores[start_index:end_index] >= threshold)
        if peak_indexes.size == 0:
            return None
        return float((start_index + int(peak_indexes[-1])) * self.window_seconds)

    def peak_clusters(
        self,
        start: float,
        end: float,
        *,
        threshold: float,
        max_gap_seconds: float,
    ) -> list[list[float]]:
        start_index = max(0, int(start / self.window_seconds))
        end_index = min(len(self.scores), int(end / self.window_seconds) + 1)
        if end_index <= start_index:
            return []

        peak_indexes = np.flatnonzero(self.scores[start_index:end_index] >= threshold)
        if peak_indexes.size == 0:
            return []

        max_gap_windows = max(1, int(round(max_gap_seconds / self.window_seconds)))
        clusters: list[list[float]] = []
        current: list[int] = [int(peak_indexes[0])]
        for peak_index in peak_indexes[1:]:
            peak = int(peak_index)
            if peak - current[-1] <= max_gap_windows:
                current.append(peak)
                continue

            clusters.append(
                [float((start_index + index) * self.window_seconds) for index in current]
            )
            current = [peak]

        clusters.append(
            [float((start_index + index) * self.window_seconds) for index in current]
        )
        return clusters


def _load_transient_track(input_path: str | Path) -> _TransientTrack:
    sample_rate = 16_000
    window_seconds = 0.05
    window_size = int(sample_rate * window_seconds)
    command = [
        _find_ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    raw_audio = subprocess.check_output(command)
    audio = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.size < window_size:
        return _TransientTrack(np.zeros(0, dtype=np.float32), window_seconds)

    transient = np.abs(np.diff(audio, prepend=audio[0]))
    frame_count = transient.size // window_size
    values = transient[: frame_count * window_size].reshape(frame_count, window_size).max(axis=1)
    return _TransientTrack(_robust_normalize(values), window_seconds)


def _find_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("imageio-ffmpeg is not installed") from exc

    return imageio_ffmpeg.get_ffmpeg_exe()


def _robust_normalize(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values

    low = float(np.percentile(values, 50))
    high = float(np.percentile(values, 99.5))
    if high <= low + 1e-9:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0.0, 1.0)
