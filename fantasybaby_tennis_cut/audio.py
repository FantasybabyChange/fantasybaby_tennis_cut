from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from .config import CutConfig
from .segments import Segment


def filter_segments_by_audio(
    input_path: str | Path,
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    if not segments:
        return segments

    max_duration = config.audio_filter_max_segment_seconds
    bridge_gap = config.audio_bridge_gap_seconds
    tail_trim_min_duration = config.audio_tail_trim_min_segment_seconds
    if max_duration <= 0 and bridge_gap <= 0 and tail_trim_min_duration <= 0:
        return segments

    try:
        track = _load_transient_track(input_path)
    except Exception as exc:  # pragma: no cover - best-effort media helper
        print(f"Warning: audio filter skipped ({exc}).")
        return segments

    filtered = segments
    if max_duration > 0:
        filtered = _filter_short_segments_by_audio(track, segments, config)

    if bridge_gap > 0:
        filtered = _bridge_segments_by_audio(track, filtered, config)

    if tail_trim_min_duration > 0:
        filtered = _trim_long_tails_by_audio(track, filtered, config)

    return filtered


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

        peak_count = track.count_peaks(
            segment.start,
            segment.end,
            threshold=config.audio_peak_threshold,
        )
        if peak_count >= config.audio_min_peak_count:
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
        start_index = max(0, int(start / self.window_seconds))
        end_index = min(len(self.scores), int(end / self.window_seconds) + 1)
        if end_index <= start_index:
            return 0
        return int(np.count_nonzero(self.scores[start_index:end_index] >= threshold))

    def last_peak_time(self, start: float, end: float, *, threshold: float) -> float | None:
        start_index = max(0, int(start / self.window_seconds))
        end_index = min(len(self.scores), int(end / self.window_seconds) + 1)
        if end_index <= start_index:
            return None

        peak_indexes = np.flatnonzero(self.scores[start_index:end_index] >= threshold)
        if peak_indexes.size == 0:
            return None
        return float((start_index + int(peak_indexes[-1])) * self.window_seconds)


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
