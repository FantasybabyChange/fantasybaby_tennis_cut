from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CutConfig:
    analysis_fps: float = 6.0
    resize_width: int = 640
    roi: tuple[float, float, float, float] | None = None

    diff_pixel_threshold: int = 18
    small_motion_min_area: int = 4
    small_motion_max_area: int = 900
    small_motion_weight: float = 0.35
    motion_weight: float = 0.65

    smooth_window_seconds: float = 1.1
    active_threshold: float = 0.34
    min_rally_seconds: float = 4.0
    merge_gap_seconds: float = 2.0
    pre_roll_seconds: float = 0.9
    post_roll_seconds: float = 1.2

    prefer_stream_copy: bool = True
    fallback_crf: int = 18
    fallback_preset: str = "medium"


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
