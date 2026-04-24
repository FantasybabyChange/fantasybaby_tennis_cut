# FantasyBaby Tennis Cut

Local tooling for automatically cutting tennis videos down to rally footage.

The project supports two workflows:
- `Legacy audio/visual rules`: the original rule-based cutter.
- `New model-assisted ball tracking`: the same rule-based pipeline plus YOLO tennis-ball detection to recover rallies that were cut too aggressively.

## Features

- Samples video motion to detect likely rally activity.
- Uses audio transients to reject weak segments, bridge nearby rallies, and trim dead-ball sections.
- Includes presets for serve practice, doubles matches, and singles matches.
- Optionally uses a ball-detection model to repair fragmented singles rallies.
- Can write a timeline JSON as well as the final rendered video.
- Includes interactive launcher scripts for Windows and macOS/Linux.

## Setup

Install the base dependencies:

```powershell
uv sync
```

If you want to use the model-assisted workflow, install the model extra too:

```powershell
uv sync --extra model
```

`ffmpeg` is recommended for best output quality:

```powershell
ffmpeg -version
```

If the default `uv` cache location causes permission issues, keep the cache inside the repo:

```powershell
$env:UV_CACHE_DIR = "$PWD\\.uv-cache"
uv sync
```

## Quick Start

### Windows

```powershell
.\start_tennis_cut.bat
```

The script asks you to choose:
- `1` `Legacy audio/visual rules`
- `2` `New model-assisted ball tracking`

### macOS / Linux

```bash
chmod +x start_tennis_cut.sh
./start_tennis_cut.sh
```

The shell launcher offers the same legacy vs model-assisted choice.

## CLI Usage

Basic usage:

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videos\input.mp4" -o "D:\videos\tennis_rallies.mp4"
```

Interactive mode:

```powershell
uv --cache-dir .uv-cache run tennis-cut
```

Video-type presets:

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videos\serve.mp4" -o "D:\videos\serve_cut.mp4" --video-type 1
uv --cache-dir .uv-cache run tennis-cut "D:\videos\doubles.mp4" -o "D:\videos\doubles_cut.mp4" --video-type 2
uv --cache-dir .uv-cache run tennis-cut "D:\videos\singles.mp4" -o "D:\videos\singles_cut.mp4" --video-type 3
```

Analyze only and export the timeline:

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videos\input.mp4" --dry-run --timeline "D:\videos\timeline.json"
```

Use a config file:

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videos\input.mp4" -o "D:\videos\out.mp4" --config configs\default.yaml
```

If the match clearly ends before cooldown, water, or post-match chat footage, you can clip the output at a fixed timestamp:

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videos\singles.mp4" -o "D:\videos\singles_cut.mp4" --video-type 3 --clip-end-seconds 1869
```

## Model-Assisted Workflow

Enable the ball-tracking assist:

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videomarker\aiVideoWorkspace\single1.mp4" -o "D:\videomarker\aiVideoWorkspace\output\single1_cut_model.mp4" --video-type 3 --model-assist ball
```

By default the model comes from Hugging Face:
- `RJTPP/tennis-ball-detection`

You can point to a local model file instead:

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videomarker\aiVideoWorkspace\single1.mp4" -o "D:\videomarker\aiVideoWorkspace\output\single1_cut_model.mp4" --video-type 3 --model-assist ball --model-ball-model "D:\models\tennisball.pt"
```

Useful model-related arguments:
- `--model-ball-sample-fps`
- `--model-ball-confidence`
- `--model-ball-bridge-min-confidence`
- `--model-ball-candidate-gap-seconds`
- `--model-ball-max-gap-seconds`
- `--model-ball-min-active-seconds`
- `--model-ball-min-detections`
- `--model-ball-min-motion-ratio`
- `--model-ball-bridge-padding-seconds`
- `--model-ball-max-bridges`

## Singles Test Scripts

Legacy singles test:

```powershell
.\test_single_match.bat
```

Standard model-assisted singles test:

```powershell
.\test_single_match_model.bat
```

Recommended rally-complete singles recipe:

```powershell
.\test_single_match_model_balanced_v2.bat
```

The `balanced v2` script bakes in the current recommended singles settings:
- extra pre-roll and post-roll so rallies do not feel clipped
- larger continuity merges and gap rescue windows
- no aggressive tail trimming or silent-gap trimming
- `--clip-end-seconds 1869` so post-match chat footage is removed after the net tap / handshake ending

Default outputs for the curated script:
- video: `D:\videomarker\aiVideoWorkspace\output\single1_cut_model_balanced_v2.mp4`
- timeline: `D:\videomarker\aiVideoWorkspace\output\single1_cut_model_balanced_v2.timeline.json`

## Timeline Output

The timeline JSON contains:
- `input`
- `duration_seconds`
- `kept_seconds`
- `segments`
- `samples`

## Tuning Tips

- If short rallies are missed, lower `active_threshold` or `min_rally_seconds`.
- If too much dead-ball time remains, raise `active_threshold` or `min_rally_seconds`.
- If cut points feel too tight, increase `pre_roll_seconds` or `post_roll_seconds`.
- If a rally gets split in two, increase `merge_gap_seconds` or `final_continuity_merge_gap_seconds`.
- If singles footage is over-cut, try `--model-assist ball` before changing lower-level thresholds.

## Project Layout

```text
fantasybaby_tennis_cut/
  analyzer.py
  audio.py
  cli.py
  config.py
  detector.py
  model_assist.py
  renderer.py
  segments.py
start_tennis_cut.bat
start_tennis_cut.sh
test_single_match.bat
test_single_match_model.bat
test_single_match_model_balanced_v2.bat
```
