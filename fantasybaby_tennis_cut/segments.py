from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Segment:
    start: float
    end: float
    score: float = 0.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def clipped(self, duration: float) -> "Segment":
        start = min(max(self.start, 0.0), duration)
        end = min(max(self.end, start), duration)
        return Segment(start=start, end=end, score=self.score)

    def with_padding(self, before: float, after: float, duration: float) -> "Segment":
        return Segment(self.start - before, self.end + after, self.score).clipped(duration)

    def to_dict(self) -> dict[str, float]:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "score": round(self.score, 4),
        }


def merge_segments(segments: list[Segment], max_gap: float) -> list[Segment]:
    if not segments:
        return []

    ordered = sorted(segments, key=lambda item: item.start)
    merged = [ordered[0]]
    for segment in ordered[1:]:
        previous = merged[-1]
        if segment.start - previous.end <= max_gap:
            total_duration = previous.duration + segment.duration
            if total_duration <= 0:
                combined_score = max(previous.score, segment.score)
            else:
                combined_score = (
                    previous.score * previous.duration + segment.score * segment.duration
                ) / total_duration
            previous.end = max(previous.end, segment.end)
            previous.score = combined_score
        else:
            merged.append(segment)

    return merged


def filter_short_segments(segments: list[Segment], min_duration: float) -> list[Segment]:
    return [segment for segment in segments if segment.duration >= min_duration]
