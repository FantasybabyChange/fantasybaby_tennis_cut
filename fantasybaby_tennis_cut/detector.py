from __future__ import annotations

from statistics import median

from .analyzer import AnalysisResult, FrameSample
from .config import CutConfig
from .segments import Segment, filter_short_segments, merge_segments


class RallyDetector:
    def __init__(self, config: CutConfig):
        self.config = config

    def detect(self, analysis: AnalysisResult) -> list[Segment]:
        samples = analysis.samples
        if not samples:
            return []

        mode = self.config.detection_mode.strip().lower()
        if mode == "auto":
            burst_segments = self._detect_burst(samples, analysis.info.duration)
            if self._kept_ratio(burst_segments, analysis.info.duration) >= (
                self.config.auto_fallback_min_kept_ratio
            ):
                return burst_segments
            return self._detect_sustained(samples, analysis.info.duration)
        if mode == "sustained":
            return self._detect_sustained(samples, analysis.info.duration)
        if mode == "hysteresis":
            return self._detect_hysteresis(samples, analysis.info.duration)
        if mode == "burst":
            return self._detect_burst(samples, analysis.info.duration)

        raise ValueError("detection_mode must be 'auto', 'burst', 'sustained', or 'hysteresis'.")

    def _detect_burst(self, samples: list[FrameSample], duration: float) -> list[Segment]:
        return self._finalize_segments(self._burst_runs(samples, duration), duration, samples)

    def _detect_sustained(self, samples: list[FrameSample], duration: float) -> list[Segment]:
        active_segments = self._active_runs(samples, duration, self.config.sustained_threshold)
        return self._finalize_segments(active_segments, duration, samples)

    def _detect_hysteresis(self, samples: list[FrameSample], duration: float) -> list[Segment]:
        active_segments = self._hysteresis_runs(
            samples,
            duration,
            self.config.hysteresis_start_threshold,
            self.config.hysteresis_continue_threshold,
            self.config.max_inactive_seconds,
        )
        return self._finalize_segments(active_segments, duration, samples)

    def _finalize_segments(
        self,
        segments: list[Segment],
        duration: float,
        samples: list[FrameSample],
    ) -> list[Segment]:
        segments = self._trim_to_quality_window(segments, samples)
        padded = self._pad_segments(segments, duration)
        start_floor = max(0.0, self.config.ignore_initial_seconds)
        if start_floor > 0:
            padded = [
                Segment(max(segment.start, start_floor), segment.end, segment.score)
                for segment in padded
                if segment.end > start_floor
            ]

        merged = merge_segments(padded, self.config.merge_gap_seconds)
        long_enough = filter_short_segments(merged, self.config.min_rally_seconds)
        return self._filter_quality(long_enough, samples)

    def _pad_segments(self, segments: list[Segment], duration: float) -> list[Segment]:
        padded: list[Segment] = []
        previous_end: float | None = None
        for segment in segments:
            pre_roll = self.config.pre_roll_seconds
            if (
                self.config.serve_pre_roll_seconds > pre_roll
                and (
                    previous_end is None
                    or segment.start - previous_end >= self.config.serve_pre_roll_gap_seconds
                )
            ):
                pre_roll = self.config.serve_pre_roll_seconds

            padded.append(segment.with_padding(pre_roll, self.config.post_roll_seconds, duration))
            previous_end = segment.end

        return padded

    def _trim_to_quality_window(
        self,
        segments: list[Segment],
        samples: list[FrameSample],
    ) -> list[Segment]:
        threshold = self.config.quality_trim_threshold
        if threshold <= 0:
            return segments

        trimmed: list[Segment] = []
        for segment in segments:
            anchors = [
                sample
                for sample in samples
                if segment.start <= sample.time <= segment.end
                and sample.total_score >= threshold
            ]
            if not anchors:
                continue

            strong_anchors = [
                sample
                for sample in anchors
                if sample.total_score >= self.config.strong_tail_trim_peak_threshold
            ]
            end = anchors[-1].time
            if (
                self.config.strong_tail_trim_peak_threshold > 0
                and self.config.strong_tail_trim_min_tail_seconds > 0
                and strong_anchors
                and end - strong_anchors[-1].time
                >= self.config.strong_tail_trim_min_tail_seconds
            ):
                end = min(end, strong_anchors[-1].time + self.config.strong_tail_trim_padding_seconds)

            trimmed.append(
                Segment(
                    start=anchors[0].time,
                    end=end,
                    score=segment.score,
                )
            )

        return trimmed

    def _filter_quality(
        self,
        segments: list[Segment],
        samples: list[FrameSample],
    ) -> list[Segment]:
        if (
            self.config.min_quality_peak_count <= 0
            and self.config.min_quality_active_average <= 0
        ):
            return segments

        filtered: list[Segment] = []
        for segment in segments:
            scores = [
                sample.total_score
                for sample in samples
                if segment.start <= sample.time <= segment.end
            ]
            if not scores:
                continue

            if self.config.min_quality_peak_count > 0:
                peak_count = sum(
                    1 for score in scores if score >= self.config.quality_peak_threshold
                )
                if peak_count < self.config.min_quality_peak_count:
                    continue

            if self.config.min_quality_active_average > 0:
                active_scores = [
                    score
                    for score in scores
                    if score >= self.config.quality_active_threshold
                ]
                if not active_scores:
                    continue
                active_average = sum(active_scores) / len(active_scores)
                if active_average < self.config.min_quality_active_average:
                    continue

            filtered.append(segment)

        return filtered

    @staticmethod
    def _kept_ratio(segments: list[Segment], duration: float) -> float:
        if duration <= 0:
            return 0.0
        return sum(segment.duration for segment in segments) / duration

    def _burst_runs(self, samples: list[FrameSample], duration: float) -> list[Segment]:
        baselines = self._local_baselines(samples)
        peak_segments: list[Segment] = []

        for sample, baseline in zip(samples, baselines):
            prominence = sample.total_score - baseline
            if (
                sample.total_score >= self.config.active_threshold
                and prominence >= self.config.peak_prominence
            ):
                peak_segments.append(Segment(sample.time, sample.time, sample.total_score))

        if not peak_segments:
            return []

        sample_gap = self._sample_gap(samples)
        return merge_segments(peak_segments, max(sample_gap, 1.0 / self.config.analysis_fps))

    def _local_baselines(self, samples: list[FrameSample]) -> list[float]:
        sample_gap = self._sample_gap(samples)
        radius = max(1, int(round(self.config.local_baseline_seconds / sample_gap)))
        scores = [sample.total_score for sample in samples]
        baselines: list[float] = []

        for index in range(len(scores)):
            start = max(0, index - radius)
            end = min(len(scores), index + radius + 1)
            baselines.append(float(median(scores[start:end])))

        return baselines

    @staticmethod
    def _sample_gap(samples: list[FrameSample]) -> float:
        if len(samples) < 2:
            return 1.0
        gaps = [
            current.time - previous.time
            for previous, current in zip(samples, samples[1:])
            if current.time > previous.time
        ]
        return median(gaps) if gaps else 1.0

    def _active_runs(
        self,
        samples: list[FrameSample],
        duration: float,
        threshold: float,
    ) -> list[Segment]:
        segments: list[Segment] = []
        start: float | None = None
        scores: list[float] = []

        for sample in samples:
            if sample.total_score >= threshold:
                if start is None:
                    start = sample.time
                    scores = []
                scores.append(sample.total_score)
            elif start is not None:
                segments.append(self._finish_segment(start, sample.time, scores, duration))
                start = None
                scores = []

        if start is not None:
            segments.append(self._finish_segment(start, duration, scores, duration))

        return segments

    def _hysteresis_runs(
        self,
        samples: list[FrameSample],
        duration: float,
        start_threshold: float,
        continue_threshold: float,
        max_inactive_seconds: float,
    ) -> list[Segment]:
        segments: list[Segment] = []
        start: float | None = None
        last_active_time: float | None = None
        scores: list[float] = []

        for sample in samples:
            score = sample.total_score
            if start is None:
                if score >= start_threshold:
                    start = sample.time
                    last_active_time = sample.time
                    scores = [score]
                continue

            if score >= continue_threshold:
                last_active_time = sample.time
                scores.append(score)
                continue

            if last_active_time is not None and sample.time - last_active_time > max_inactive_seconds:
                segments.append(self._finish_segment(start, last_active_time, scores, duration))
                start = None
                last_active_time = None
                scores = []

                if score >= start_threshold:
                    start = sample.time
                    last_active_time = sample.time
                    scores = [score]

        if start is not None:
            end = last_active_time if last_active_time is not None else duration
            segments.append(self._finish_segment(start, end, scores, duration))

        return segments

    @staticmethod
    def _finish_segment(start: float, end: float, scores: list[float], duration: float) -> Segment:
        score = sum(scores) / len(scores) if scores else 0.0
        return Segment(start=start, end=min(end, duration), score=score)
