from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2

from .config import CutConfig
from .segments import Segment


class VideoRenderer:
    def __init__(self, config: CutConfig):
        self.config = config

    def render(self, input_path: str | Path, output_path: str | Path, segments: list[Segment]) -> None:
        if not segments:
            raise ValueError("No rally segments were detected. Try lowering active_threshold.")

        source = Path(input_path)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = _find_ffmpeg()

        if ffmpeg:
            try:
                self._render_with_ffmpeg(
                    ffmpeg,
                    source,
                    target,
                    segments,
                    stream_copy=self.config.prefer_stream_copy,
                )
                return
            except subprocess.CalledProcessError:
                if self.config.prefer_stream_copy:
                    try:
                        self._render_with_ffmpeg(ffmpeg, source, target, segments, stream_copy=False)
                        return
                    except subprocess.CalledProcessError:
                        pass

        print("Warning: FFmpeg not found; falling back to OpenCV without audio.")
        self._render_with_opencv(source, target, segments)

    def _render_with_ffmpeg(
        self,
        ffmpeg: str,
        source: Path,
        target: Path,
        segments: list[Segment],
        stream_copy: bool,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="tennis-cut-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            part_files: list[Path] = []

            for index, segment in enumerate(segments):
                part = temp_dir / f"part_{index:04d}.mp4"
                command = [
                    ffmpeg,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{segment.start:.3f}",
                    "-i",
                    str(source),
                    "-t",
                    f"{segment.duration:.3f}",
                    *self._ffmpeg_codec_args(stream_copy),
                    "-avoid_negative_ts",
                    "make_zero",
                    str(part),
                ]
                subprocess.run(command, check=True)
                part_files.append(part)

            concat_file = temp_dir / "concat.txt"
            concat_file.write_text(
                "\n".join(f"file '{part.as_posix()}'" for part in part_files),
                encoding="utf-8",
            )
            command = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(target),
            ]
            subprocess.run(command, check=True)

    def _ffmpeg_codec_args(self, stream_copy: bool) -> list[str]:
        if stream_copy:
            return ["-c", "copy"]
        return [
            "-c:v",
            "libx264",
            "-crf",
            str(self.config.fallback_crf),
            "-preset",
            self.config.fallback_preset,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
        ]

    def _render_with_opencv(self, source: Path, target: Path, segments: list[Segment]) -> None:
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise FileNotFoundError(f"Could not open video: {source}")

        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            if fps <= 0 or width <= 0 or height <= 0:
                raise ValueError("Could not read video metadata for OpenCV fallback render.")

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(target), fourcc, fps, (width, height))
            if not writer.isOpened():
                raise ValueError(f"Could not create output video: {target}")

            try:
                for segment in segments:
                    start_frame = int(round(segment.start * fps))
                    end_frame = int(round(segment.end * fps))
                    capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                    for _ in range(max(0, end_frame - start_frame)):
                        ok, frame = capture.read()
                        if not ok:
                            break
                        writer.write(frame)
            finally:
                writer.release()
        finally:
            capture.release()


def _find_ffmpeg() -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    try:
        import imageio_ffmpeg
    except ModuleNotFoundError:
        return None

    return imageio_ffmpeg.get_ffmpeg_exe()


def write_timeline(
    output_path: str | Path,
    input_path: str | Path,
    duration: float,
    segments: list[Segment],
    samples: list[dict[str, float | int]] | None = None,
) -> None:
    payload = {
        "input": str(input_path),
        "duration_seconds": round(duration, 3),
        "kept_seconds": round(sum(segment.duration for segment in segments), 3),
        "segments": [segment.to_dict() for segment in segments],
    }
    if samples is not None:
        payload["samples"] = samples

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
