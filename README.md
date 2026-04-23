# FantasyBaby Tennis Cut

用于网球视频自动剪辑的本地工具。它会分析画面运动、音频击球瞬态和可选的网球检测模型，尽量删除捡球、等待、走位等死球时间，保留连续回合。

当前工程支持两套方案：

- 旧方案：仅使用原有音频/画面规则。
- 新方案：在旧方案基础上，用网球检测模型补回被误切断的单打回合。

## 功能

- 自动抽样分析视频画面运动。
- 基于音频瞬态过滤短误检片段、桥接邻近回合、裁剪长尾空白。
- 为单打模式提供更激进的补桥、补回和尾部修剪参数。
- 可选启用 YOLO 网球检测模型，修复疑似被规则误切的连续回合。
- 导出剪辑后视频，也可只做分析并导出时间线 JSON。
- Windows 和 macOS/Linux 都有交互式启动脚本。

## 环境准备

项目使用 `uv` 管理依赖，建议系统已安装 `ffmpeg`。

基础依赖：

```powershell
uv sync
```

如果需要使用新模型方案，再安装模型依赖：

```powershell
uv sync --extra model
```

检查 `ffmpeg`：

```powershell
ffmpeg -version
```

如果本机 `uv` 默认缓存目录有权限问题，也可以把缓存放在项目内：

```powershell
$env:UV_CACHE_DIR = "$PWD\\.uv-cache"
uv sync
```

## 快速启动

### Windows

```powershell
.\start_tennis_cut.bat
```

脚本会先让用户选择剪辑方案：

- `1` 旧方案：`Legacy audio/visual rules`
- `2` 新方案：`New model-assisted ball tracking`

如果选择新方案，第一次运行前先执行：

```powershell
uv sync --extra model
```

然后脚本会继续提示输入视频类型、输入视频路径和输出视频路径。

### macOS / Linux

```bash
chmod +x start_tennis_cut.sh
./start_tennis_cut.sh
```

shell 启动脚本和 Windows 一样，也会先让用户选择旧方案或新模型方案。

## 命令行直接运行

基础用法：

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videos\input.mp4" -o "D:\videos\tennis_rallies.mp4"
```

不带输入路径时会进入交互模式：

```powershell
uv --cache-dir .uv-cache run tennis-cut
```

指定视频类型：

```powershell
# 1 = 发球训练
uv --cache-dir .uv-cache run tennis-cut "D:\videos\serve.mp4" -o "D:\videos\serve_cut.mp4" --video-type 1

# 2 = 双打比赛
uv --cache-dir .uv-cache run tennis-cut "D:\videos\doubles.mp4" -o "D:\videos\doubles_cut.mp4" --video-type 2

# 3 = 单打比赛
uv --cache-dir .uv-cache run tennis-cut "D:\videos\singles.mp4" -o "D:\videos\singles_cut.mp4" --video-type 3
```

只分析，不输出视频：

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videos\input.mp4" --dry-run --timeline "D:\videos\timeline.json"
```

使用配置文件：

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videos\input.mp4" -o "D:\videos\out.mp4" --config configs\default.yaml
```

## 新模型方案

启用模型辅助模式：

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videomarker\aiVideoWorkspace\single1.mp4" -o "D:\videomarker\aiVideoWorkspace\output\single1_cut_model.mp4" --video-type 3 --model-assist ball
```

`--model-assist ball` 会在原有音频/画面规则之后，再用 YOLO 网球检测模型扫描候选缺口，补回疑似被误切断的连续回合。

默认模型来源是 Hugging Face 上的 `RJTPP/tennis-ball-detection`。也可以显式传入本地模型文件：

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videomarker\aiVideoWorkspace\single1.mp4" -o "D:\videomarker\aiVideoWorkspace\output\single1_cut_model.mp4" --video-type 3 --model-assist ball --model-ball-model "D:\models\tennisball.pt"
```

常用相关参数：

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

## 单打测试脚本

旧方案单打测试：

```powershell
.\test_single_match.bat
```

如果要输出时间线：

```powershell
.\test_single_match.bat --timeline "D:\videomarker\aiVideoWorkspace\output\single1_timeline.json"
```

新模型方案单打测试：

```powershell
.\test_single_match_model.bat
```

该脚本默认输入：

- 输入视频：`D:\videomarker\aiVideoWorkspace\single1.mp4`
- 输出视频：`D:\videomarker\aiVideoWorkspace\output\single1_cut_model.mp4`

它会自动附带 `--video-type 3 --model-assist ball`，其余额外参数可以继续从命令行追加。

## 输出时间线

时间线 JSON 包含：

- `input`
- `duration_seconds`
- `kept_seconds`
- `segments`
- `samples`

## 调参建议

- 漏掉短回合：降低 `active_threshold` 或 `min_rally_seconds`。
- 捡球也被保留：提高 `active_threshold` 或 `min_rally_seconds`。
- 剪辑点太紧：增大 `pre_roll_seconds` 和 `post_roll_seconds`。
- 一段回合被切开：增大 `merge_gap_seconds`。
- 单打被误切：优先尝试 `--model-assist ball`。

## 项目结构

```text
fantasybaby_tennis_cut/
  analyzer.py               # 视频抽样和运动特征分析
  audio.py                  # 音频瞬态分析、桥接与裁剪
  cli.py                    # 命令行入口
  config.py                 # 配置与预设
  detector.py               # 回合检测
  model_assist.py           # 模型辅助补桥逻辑
  renderer.py               # 视频输出
  segments.py               # 片段结构与合并
start_tennis_cut.bat        # Windows 交互式启动脚本
start_tennis_cut.sh         # macOS/Linux 交互式启动脚本
test_single_match.bat       # Windows 单打旧方案测试脚本
test_single_match_model.bat # Windows 单打新模型方案测试脚本
```
