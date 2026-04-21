from __future__ import annotations

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

        active_segments = self._active_runs(samples, analysis.info.duration)
        padded = [
            segment.with_padding(
                self.config.pre_roll_seconds,
                self.config.post_roll_seconds,
                analysis.info.duration,
            )
            for segment in active_segments
        ]
        merged = merge_segments(padded, self.config.merge_gap_seconds)
        return filter_short_segments(merged, self.config.min_rally_seconds)

    def _active_runs(self, samples: list[FrameSample], duration: float) -> list[Segment]:
        segments: list[Segment] = []
        start: float | None = None
        scores: list[float] = []

        for sample in samples:
            if sample.total_score >= self.config.active_threshold:
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

    @staticmethod
    def _finish_segment(start: float, end: float, scores: list[float], duration: float) -> Segment:
        score = sum(scores) / len(scores) if scores else 0.0
        return Segment(start=start, end=min(end, duration), score=score)
