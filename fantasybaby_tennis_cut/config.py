from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CutConfig:
    analysis_fps: float = 6.0
    resize_width: int = 640
    roi: tuple[float, float, float, float] | None = None

    detection_mode: str = "auto"
    diff_pixel_threshold: int = 18
    small_motion_min_area: int = 4
    small_motion_max_area: int = 900
    small_motion_weight: float = 0.35
    motion_weight: float = 0.65

    smooth_window_seconds: float = 1.1
    active_threshold: float = 0.70
    peak_prominence: float = 0.12
    local_baseline_seconds: float = 2.0
    sustained_threshold: float = 0.46
    hysteresis_start_threshold: float = 0.55
    hysteresis_continue_threshold: float = 0.32
    max_inactive_seconds: float = 1.0
    quality_peak_threshold: float = 0.0
    min_quality_peak_count: int = 0
    quality_active_threshold: float = 0.0
    min_quality_active_average: float = 0.0
    quality_trim_threshold: float = 0.0
    strong_tail_trim_peak_threshold: float = 0.0
    strong_tail_trim_min_tail_seconds: float = 0.0
    strong_tail_trim_padding_seconds: float = 0.0
    audio_filter_max_segment_seconds: float = 0.0
    audio_peak_threshold: float = 0.55
    audio_min_peak_count: int = 1
    audio_bridge_gap_seconds: float = 0.0
    audio_bridge_peak_threshold: float = 0.55
    audio_bridge_min_peak_count: int = 2
    audio_tail_trim_min_segment_seconds: float = 0.0
    audio_tail_padding_seconds: float = 1.4
    auto_fallback_min_kept_ratio: float = 0.15
    min_rally_seconds: float = 3.0
    merge_gap_seconds: float = 2.2
    pre_roll_seconds: float = 0.8
    post_roll_seconds: float = 2.0
    ignore_initial_seconds: float = 0.0

    prefer_stream_copy: bool = False
    fallback_crf: int = 18
    fallback_preset: str = "medium"


VIDEO_TYPE_PRESETS: dict[str, dict[str, Any]] = {
    "1": {
        "label": "serve-training",
        "detection_mode": "burst",
        "active_threshold": 0.70,
        "peak_prominence": 0.12,
        "local_baseline_seconds": 2.0,
        "min_rally_seconds": 1.0,
        "merge_gap_seconds": 1.0,
        "pre_roll_seconds": 0.55,
        "post_roll_seconds": 1.1,
    },
    "2": {
        "label": "doubles-match",
        "roi": (0.04, 0.08, 0.96, 0.88),
        "detection_mode": "hysteresis",
        "motion_weight": 0.45,
        "small_motion_weight": 0.55,
        "hysteresis_start_threshold": 0.46,
        "hysteresis_continue_threshold": 0.32,
        "max_inactive_seconds": 1.0,
        "quality_peak_threshold": 0.54,
        "min_quality_peak_count": 0,
        "quality_active_threshold": 0.28,
        "min_quality_active_average": 0.38,
        "quality_trim_threshold": 0.46,
        "strong_tail_trim_peak_threshold": 0.62,
        "strong_tail_trim_min_tail_seconds": 6.5,
        "strong_tail_trim_padding_seconds": 0.0,
        "audio_filter_max_segment_seconds": 0.0,
        "audio_peak_threshold": 0.55,
        "audio_min_peak_count": 1,
        "audio_bridge_gap_seconds": 8.0,
        "audio_bridge_peak_threshold": 0.55,
        "audio_bridge_min_peak_count": 2,
        "audio_tail_trim_min_segment_seconds": 20.0,
        "audio_tail_padding_seconds": 1.4,
        "min_rally_seconds": 3.0,
        "merge_gap_seconds": 1.2,
        "pre_roll_seconds": 0.8,
        "post_roll_seconds": 2.4,
        "ignore_initial_seconds": 18.0,
    },
    "3": {
        "label": "singles-match",
        "detection_mode": "sustained",
        "sustained_threshold": 0.46,
        "min_rally_seconds": 3.0,
        "merge_gap_seconds": 2.2,
        "pre_roll_seconds": 0.8,
        "post_roll_seconds": 2.0,
    },
}

VIDEO_TYPE_ALIASES = {
    "serve": "1",
    "serve-training": "1",
    "training": "1",
    "doubles": "2",
    "doubles-match": "2",
    "double": "2",
    "singles": "3",
    "singles-match": "3",
    "single": "3",
}


def apply_video_type_preset(config: CutConfig, video_type: str | None) -> CutConfig:
    if video_type is None:
        return config

    key = normalize_video_type(video_type)
    preset = VIDEO_TYPE_PRESETS[key]
    for name, value in preset.items():
        if name != "label":
            setattr(config, name, value)
    return config


def normalize_video_type(video_type: str) -> str:
    key = video_type.strip().lower()
    key = VIDEO_TYPE_ALIASES.get(key, key)
    if key not in VIDEO_TYPE_PRESETS:
        raise ValueError("video_type must be 1, 2, or 3.")
    return key


def video_type_label(video_type: str | None) -> str | None:
    if video_type is None:
        return None
    key = normalize_video_type(video_type)
    return str(VIDEO_TYPE_PRESETS[key]["label"])


def load_config(path: str | Path | None) -> CutConfig:
    if path is None:
        return CutConfig()

    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise RuntimeError("PyYAML is required to read config files. Run `uv sync` first.") from exc

    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {config_path}")

    allowed = {field.name for field in fields(CutConfig)}
    unknown = sorted(set(data) - allowed)
    if unknown:
        joined = ", ".join(unknown)
        raise ValueError(f"Unknown config key(s): {joined}")

    if data.get("roi") is not None:
        roi = tuple(float(value) for value in data["roi"])
        if len(roi) != 4:
            raise ValueError("roi must contain 4 normalized values: [left, top, right, bottom]")
        data["roi"] = roi

    return CutConfig(**data)


def config_to_dict(config: CutConfig) -> dict[str, Any]:
    return {field.name: getattr(config, field.name) for field in fields(config)}
