from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

from .config import CutConfig


@dataclass(slots=True)
class VideoInfo:
    path: Path
    fps: float
    frame_count: int
    duration: float
    width: int
    height: int


@dataclass(slots=True)
class FrameSample:
    frame_index: int
    time: float
    motion_score: float
    small_motion_score: float
    total_score: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "frame_index": self.frame_index,
            "time": round(self.time, 3),
            "motion_score": round(self.motion_score, 4),
            "small_motion_score": round(self.small_motion_score, 4),
            "total_score": round(self.total_score, 4),
        }


@dataclass(slots=True)
class AnalysisResult:
    info: VideoInfo
    samples: list[FrameSample]


class VideoAnalyzer:
    def __init__(self, config: CutConfig):
        self.config = config

    def analyze(self, path: str | Path) -> AnalysisResult:
        video_path = Path(path)
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise FileNotFoundError(f"Could not open video: {video_path}")

        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
            if fps <= 0:
                raise ValueError("Video FPS could not be detected.")

            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            duration = frame_count / fps if frame_count else 0.0
            info = VideoInfo(video_path, fps, frame_count, duration, width, height)

            stride = max(1, int(round(fps / self.config.analysis_fps)))
            frame_indexes = range(0, max(frame_count, 1), stride)

            raw_samples = self._collect_raw_samples(capture, info, frame_indexes)
            samples = self._normalize_and_smooth(raw_samples)
            return AnalysisResult(info=info, samples=samples)
        finally:
            capture.release()

    def _collect_raw_samples(
        self,
        capture: cv2.VideoCapture,
        info: VideoInfo,
        frame_indexes: range,
    ) -> list[FrameSample]:
        previous_gray: np.ndarray | None = None
        samples: list[FrameSample] = []
        total = len(frame_indexes)
        current_frame_index = 0

        for frame_index in tqdm(frame_indexes, total=total, desc="Analyzing video", unit="sample"):
            while current_frame_index < frame_index:
                if not capture.grab():
                    return samples
                current_frame_index += 1

            ok, frame = capture.read()
            if not ok:
                break
            current_frame_index = frame_index + 1

            gray = self._prepare_frame(frame, info)
            if previous_gray is None:
                motion_score = 0.0
                small_motion_score = 0.0
            else:
                diff = cv2.absdiff(gray, previous_gray)
                motion_score = self._motion_score(diff)
                small_motion_score = self._small_motion_score(diff)

            samples.append(
                FrameSample(
                    frame_index=frame_index,
                    time=frame_index / info.fps,
                    motion_score=motion_score,
                    small_motion_score=small_motion_score,
                    total_score=0.0,
                )
            )
            previous_gray = gray

        return samples

    def _prepare_frame(self, frame: np.ndarray, info: VideoInfo) -> np.ndarray:
        frame = self._crop_roi(frame, info)
        height, width = frame.shape[:2]
        if width > self.config.resize_width:
            scale = self.config.resize_width / width
            frame = cv2.resize(frame, (self.config.resize_width, int(height * scale)))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (5, 5), 0)

    def _crop_roi(self, frame: np.ndarray, info: VideoInfo) -> np.ndarray:
        if self.config.roi is None:
            return frame

        left, top, right, bottom = self.config.roi
        left_px = int(np.clip(left, 0.0, 1.0) * info.width)
        top_px = int(np.clip(top, 0.0, 1.0) * info.height)
        right_px = int(np.clip(right, 0.0, 1.0) * info.width)
        bottom_px = int(np.clip(bottom, 0.0, 1.0) * info.height)
        if right_px <= left_px or bottom_px <= top_px:
            return frame
        return frame[top_px:bottom_px, left_px:right_px]

    def _motion_score(self, diff: np.ndarray) -> float:
        mask = diff > self.config.diff_pixel_threshold
        if not np.any(mask):
            return 0.0
        return float(np.mean(diff[mask]) / 255.0 * np.mean(mask))

    def _small_motion_score(self, diff: np.ndarray) -> float:
        _, binary = cv2.threshold(
            diff,
            self.config.diff_pixel_threshold,
            255,
            cv2.THRESH_BINARY,
        )
        component_count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        if component_count <= 1:
            return 0.0

        areas = stats[1:, cv2.CC_STAT_AREA]
        valid = areas[
            (areas >= self.config.small_motion_min_area)
            & (areas <= self.config.small_motion_max_area)
        ]
        if valid.size == 0:
            return 0.0
        return float(np.sum(valid) / diff.size)

    def _normalize_and_smooth(self, samples: list[FrameSample]) -> list[FrameSample]:
        if not samples:
            return []

        motion = np.array([sample.motion_score for sample in samples], dtype=np.float32)
        small = np.array([sample.small_motion_score for sample in samples], dtype=np.float32)
        motion = _robust_normalize(motion)
        small = _robust_normalize(small)

        total = self.config.motion_weight * motion + self.config.small_motion_weight * small
        window = max(1, int(round(self.config.smooth_window_seconds * self.config.analysis_fps)))
        total = _moving_average(total, window)

        normalized_samples: list[FrameSample] = []
        for index, sample in enumerate(samples):
            normalized_samples.append(
                FrameSample(
                    frame_index=sample.frame_index,
                    time=sample.time,
                    motion_score=float(motion[index]),
                    small_motion_score=float(small[index]),
                    total_score=float(np.clip(total[index], 0.0, 1.0)),
                )
            )
        return normalized_samples


def _robust_normalize(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    low = float(np.percentile(values, 10))
    high = float(np.percentile(values, 95))
    if high <= low + 1e-9:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if values.size == 0 or window <= 1:
        return values
    kernel = np.ones(window, dtype=np.float32) / window
    padded = np.pad(values, (window // 2, window - 1 - window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")
