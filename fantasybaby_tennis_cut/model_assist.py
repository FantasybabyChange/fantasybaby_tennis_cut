from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from tempfile import gettempdir
from typing import Any

import cv2

from .config import CutConfig
from .segments import Segment, filter_short_segments, merge_segments


@dataclass(slots=True)
class BallDetection:
    time: float
    x: float
    y: float
    confidence: float


@dataclass(slots=True)
class BridgeCandidate:
    index: int
    segment: Segment
    score: float


def refine_segments_with_model(
    input_path: str | Path,
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    mode = config.model_assist_mode.lower().strip()
    if mode in {"", "off", "none"}:
        return segments
    if mode != "ball":
        raise ValueError(f"Unsupported model assist mode: {config.model_assist_mode}")

    windows = _candidate_windows(segments, config)
    if not windows:
        print("Model assist: no candidate gaps to scan.")
        return segments

    detections, duration = detect_ball_trajectory(input_path, config, windows)
    if not detections:
        print("Model assist: no ball detections found; keeping audio/visual segments.")
        return segments

    bridge_segments = build_model_gap_bridges(detections, segments, config)
    if not bridge_segments:
        print("Model assist: no moving-ball cut gaps found; keeping audio/visual segments.")
        return segments

    refined = merge_segments([*segments, *bridge_segments], config.merge_gap_seconds)
    if config.model_ball_trim_silent_gaps:
        refined = trim_no_ball_gaps(refined, detections, config)
    refined = filter_short_segments(refined, config.min_rally_seconds)
    print(f"Model assist: bridged {len(bridge_segments)} moving-ball cut gap(s).")
    for bridge in bridge_segments:
        print(f"  model bridge {bridge.start:.2f}s -> {bridge.end:.2f}s")
    return refined


def detect_ball_trajectory(
    input_path: str | Path,
    config: CutConfig,
    windows: list[tuple[float, float]] | None = None,
) -> tuple[list[BallDetection], float]:
    model_path = _resolve_model_path(config.model_ball_model)
    model = _load_yolo_model(model_path)

    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open video for model assist: {input_path}")

    source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    duration = frame_count / source_fps if source_fps > 0 else 0.0
    step = max(1, int(round(source_fps / max(config.model_ball_sample_fps, 0.1))))

    detections: list[BallDetection] = []
    scan_windows = windows or [(0.0, duration)]
    for start, end in scan_windows:
        start_frame = max(0, int(start * source_fps))
        end_frame = min(int(frame_count), int(end * source_fps) + 1)
        frame_index = start_frame
        while frame_index < end_frame:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                break

            time = frame_index / source_fps
            detection = _best_ball_detection(model, frame, time, config)
            if detection is not None:
                detections.append(detection)
            frame_index += step

    capture.release()
    return detections, duration


def build_ball_rally_segments(
    detections: list[BallDetection],
    duration: float,
    config: CutConfig,
) -> list[Segment]:
    moving_times = _moving_ball_times(detections, config)
    if not moving_times:
        return []

    clusters: list[list[float]] = []
    current = [moving_times[0]]
    for time in moving_times[1:]:
        if time - current[-1] <= config.model_ball_max_gap_seconds:
            current.append(time)
        else:
            clusters.append(current)
            current = [time]
    clusters.append(current)

    segments: list[Segment] = []
    for cluster in clusters:
        if len(cluster) < config.model_ball_min_detections:
            continue
        if cluster[-1] - cluster[0] < config.model_ball_min_active_seconds:
            continue
        start = max(0.0, cluster[0] - config.model_ball_bridge_padding_seconds)
        end = min(duration, cluster[-1] + config.model_ball_bridge_padding_seconds)
        if end - start >= config.min_rally_seconds:
            segments.append(Segment(start, end, 0.0))

    return merge_segments(segments, config.merge_gap_seconds)


def build_model_gap_bridges(
    detections: list[BallDetection],
    segments: list[Segment],
    config: CutConfig,
) -> list[Segment]:
    moving_times = _moving_ball_times(detections, config)
    if not moving_times or len(segments) < 2:
        return []

    candidates: list[BridgeCandidate] = []
    for index, (previous, current) in enumerate(zip(segments, segments[1:])):
        gap = current.start - previous.end
        if gap <= config.merge_gap_seconds:
            continue
        if gap > config.model_ball_candidate_gap_seconds:
            continue

        start = previous.end
        end = current.start
        gap_times = [time for time in moving_times if start <= time <= end]
        if not gap_times:
            continue

        context_start = max(0.0, start - config.model_ball_bridge_padding_seconds)
        context_end = end + config.model_ball_bridge_padding_seconds
        times = [time for time in moving_times if context_start <= time <= context_end]
        if len(times) < config.model_ball_min_detections:
            continue
        if times[-1] - times[0] < config.model_ball_min_active_seconds:
            continue
        active_detections = [
            detection
            for detection in detections
            if context_start <= detection.time <= context_end
            and any(abs(detection.time - time) < 0.02 for time in times)
        ]
        if not active_detections:
            continue
        max_confidence = max(item.confidence for item in active_detections)
        if max_confidence < config.model_ball_bridge_min_confidence:
            continue

        active_span = max(0.0, times[-1] - times[0])
        fragmented_rally_bonus = 0.0
        if min(previous.duration, current.duration) <= 20.0 and max(previous.duration, current.duration) >= 25.0:
            fragmented_rally_bonus = 1.0
        score = (
            max_confidence * 2.0
            + min(active_span / max(gap, 1e-6), 1.0)
            + min(len(times) / 10.0, 1.0)
            + min(gap / max(config.model_ball_candidate_gap_seconds, 1e-6), 1.0)
            + fragmented_rally_bonus
        )
        candidates.append(BridgeCandidate(index=index, segment=Segment(start, end, score), score=score))

    if not candidates:
        return []

    selected: list[BridgeCandidate] = []
    used_indexes: set[int] = set()
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        if len(selected) >= config.model_ball_max_bridges:
            break
        if candidate.index in used_indexes:
            continue
        if candidate.index - 1 in used_indexes or candidate.index + 1 in used_indexes:
            continue
        selected.append(candidate)
        used_indexes.add(candidate.index)

    return [candidate.segment for candidate in sorted(selected, key=lambda item: item.index)]


def trim_no_ball_gaps(
    segments: list[Segment],
    detections: list[BallDetection],
    config: CutConfig,
) -> list[Segment]:
    moving_times = _moving_ball_times(detections, config)
    if not moving_times:
        return segments

    trimmed: list[Segment] = []
    for segment in segments:
        times = [time for time in moving_times if segment.start <= time <= segment.end]
        if len(times) < 2:
            trimmed.append(segment)
            continue

        current_start = segment.start
        points = [segment.start, *times, segment.end]
        pieces: list[Segment] = []
        for previous, current in zip(points, points[1:]):
            if current - previous <= config.model_ball_max_gap_seconds * 2:
                continue
            cut_start = min(segment.end, previous + config.model_ball_bridge_padding_seconds)
            cut_end = max(segment.start, current - config.model_ball_bridge_padding_seconds)
            if cut_end <= cut_start:
                continue
            if cut_start - current_start >= config.min_rally_seconds:
                pieces.append(Segment(current_start, cut_start, segment.score))
            current_start = cut_end
        if segment.end - current_start >= config.min_rally_seconds:
            pieces.append(Segment(current_start, segment.end, segment.score))

        trimmed.extend(pieces or [segment])

    return merge_segments(trimmed, config.merge_gap_seconds)


def _moving_ball_times(
    detections: list[BallDetection],
    config: CutConfig,
) -> list[float]:
    if len(detections) < 2:
        return []

    moving: set[float] = set()
    for previous, current in zip(detections, detections[1:]):
        time_gap = current.time - previous.time
        if time_gap <= 0 or time_gap > config.model_ball_max_gap_seconds:
            continue

        distance = math.hypot(current.x - previous.x, current.y - previous.y)
        if distance >= config.model_ball_min_motion_ratio:
            moving.add(previous.time)
            moving.add(current.time)

    return sorted(moving)


def _candidate_windows(
    segments: list[Segment],
    config: CutConfig,
) -> list[tuple[float, float]]:
    if len(segments) < 2:
        return []

    windows: list[tuple[float, float]] = []
    for previous, current in zip(segments, segments[1:]):
        gap = current.start - previous.end
        if gap <= config.merge_gap_seconds:
            continue
        if gap > config.model_ball_candidate_gap_seconds:
            continue
        start = max(0.0, previous.end - config.model_ball_bridge_padding_seconds)
        end = current.start + config.model_ball_bridge_padding_seconds
        if end > start:
            windows.append((start, end))

    return merge_time_windows(windows, config.model_ball_bridge_padding_seconds)


def merge_time_windows(
    windows: list[tuple[float, float]],
    max_gap: float,
) -> list[tuple[float, float]]:
    if not windows:
        return []

    ordered = sorted(windows)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        previous_start, previous_end = merged[-1]
        if start - previous_end <= max_gap:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def _best_ball_detection(
    model: Any,
    frame: Any,
    time: float,
    config: CutConfig,
) -> BallDetection | None:
    height, width = frame.shape[:2]
    results = model.predict(
        source=frame,
        imgsz=config.model_ball_image_size,
        conf=config.model_ball_confidence,
        verbose=False,
    )
    if not results:
        return None

    boxes = getattr(results[0], "boxes", None)
    if boxes is None or len(boxes) == 0:
        return None

    best: BallDetection | None = None
    best_confidence = -1.0
    for box in boxes:
        confidence = float(box.conf[0])
        if confidence < best_confidence:
            continue
        xyxy = box.xyxy[0].tolist()
        x = ((float(xyxy[0]) + float(xyxy[2])) / 2.0) / max(width, 1)
        y = ((float(xyxy[1]) + float(xyxy[3])) / 2.0) / max(height, 1)
        best = BallDetection(time=time, x=x, y=y, confidence=confidence)
        best_confidence = confidence

    return best


def _load_yolo_model(model_path: str) -> Any:
    try:
        from ultralytics import YOLO
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Model assist requires ultralytics. Install it with: "
            "uv pip install ultralytics huggingface-hub"
        ) from exc
    return YOLO(model_path)


def _resolve_model_path(model: str) -> str:
    path = Path(model)
    if path.exists():
        return str(path)

    if "/" not in model:
        return model

    try:
        from huggingface_hub import hf_hub_download
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Hugging Face model ids require huggingface-hub. Install it with: "
            "uv pip install huggingface-hub"
        ) from exc

    cache_dir = Path(gettempdir()) / "fantasybaby_tennis_cut_models"
    candidates = ("tennisball.pt", "best.pt", "yolov8_best.pt", "model.pt")
    last_error: Exception | None = None
    for filename in candidates:
        try:
            return hf_hub_download(
                repo_id=model,
                filename=filename,
                cache_dir=str(cache_dir),
            )
        except Exception as exc:  # pragma: no cover - depends on remote model layout
            last_error = exc

    raise RuntimeError(
        f"Could not download a YOLO .pt file from Hugging Face repo '{model}'. "
        "Pass a local model path with --model-ball-model."
    ) from last_error
