# FantasyBaby Tennis Cut

一个面向高清、高帧率网球素材的自动剪辑项目。它会分析视频中的运动强度和小目标活动，把捡球、等待、走回底线等无用片段尽量剪掉，保留连续击球回合，最后生成一个完整连贯的视频。

第一版是本地可运行的启发式 AI 剪辑管线：不依赖云服务，适合先批量跑素材、调参数、建立你的剪辑风格模板。后续可以在同一结构里接入 YOLO、姿态估计、网球检测、音频击球点检测等模型。

## 功能

- 自动扫描视频，按固定分析帧率抽样，适配高帧率素材。
- 使用画面运动、小目标运动和时间平滑识别击球回合。
- 合并短间隔、添加回合前后缓冲，避免剪辑点太硬。
- 优先使用 FFmpeg 无二次解码拼接；如果流拷贝失败，会尝试 FFmpeg 重编码，再退回 OpenCV。
- 支持导出 JSON 时间线，方便人工复核和二次精剪。
- 支持配置文件，能针对不同机位、球场、剪辑节奏调参数。

## 环境

本项目使用 `uv` 管理依赖。建议系统里也安装 FFmpeg，输出速度、画质和音频保留都会更好。

```powershell
uv sync
```

如果本机的 uv 默认缓存目录有权限或路径冲突，可以临时把缓存放到项目内：

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
uv sync
```

检查 FFmpeg：

```powershell
ffmpeg -version
```

## 快速使用

### Windows 启动

```powershell
.\start_tennis_cut.bat
```

`start_tennis_cut.bat` 会自动进入项目目录，并使用项目内缓存运行：

```bat
uv --cache-dir .uv-cache run tennis-cut
```

运行后按提示依次选择视频类型、输入源视频路径、输入输出视频路径。

### macOS / Linux 启动

macOS 和 Linux 用户推荐运行项目根目录下的 shell 启动脚本：

```bash
./start_tennis_cut.sh
```

如果第一次运行提示没有执行权限，先执行：

```bash
chmod +x start_tennis_cut.sh
./start_tennis_cut.sh
```

`start_tennis_cut.sh` 同样会自动进入项目目录，并使用项目内缓存运行：

```bash
uv --cache-dir .uv-cache run tennis-cut
```

### 命令行直接运行

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videos\input.mp4" -o "D:\videos\tennis_rallies.mp4"
```

不带输入路径时会进入交互模式，先选择视频类型，再输入源视频和输出路径：

```powershell
uv --cache-dir .uv-cache run tennis-cut
```

也可以直接指定视频类型：

```powershell
# 1 = 发球训练视频
uv --cache-dir .uv-cache run tennis-cut "D:\videos\serve.mp4" -o "D:\videos\serve_cut.mp4" --video-type 1

# 2 = 双打比赛视频，包含本轮针对 tennis2 调试出的参数
uv --cache-dir .uv-cache run tennis-cut "D:\videos\doubles.mp4" -o "D:\videos\doubles_cut.mp4" --video-type 2

# 3 = 单打比赛视频
uv --cache-dir .uv-cache run tennis-cut "D:\videos\singles.mp4" -o "D:\videos\singles_cut.mp4" --video-type 3
```

macOS / Linux 路径示例：

```bash
uv --cache-dir .uv-cache run tennis-cut "/Users/yourname/Videos/doubles.mp4" -o "/Users/yourname/Videos/output/doubles_cut.mp4" --video-type 2
```

本轮调试 `tennis2.mp4` 双打比赛时使用的直接生成命令：

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videomarker\aiVideoWorkspace\tennis2.mp4" -o "D:\videomarker\aiVideoWorkspace\output\mix2.mp4" --video-type 2
```

先只分析，不导出视频：

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videos\input.mp4" --dry-run --timeline "D:\videos\timeline.json"
```

使用配置文件：

```powershell
uv --cache-dir .uv-cache run tennis-cut "D:\videos\input.mp4" -o "D:\videos\out.mp4" --config configs\default.yaml
```

## 参数调试建议

- 漏掉短回合：降低 `active_threshold`，或降低 `min_rally_seconds`。
- 捡球也被保留：提高 `active_threshold`，或提高 `min_rally_seconds`。
- 剪辑点太紧：增加 `pre_roll_seconds` 和 `post_roll_seconds`。
- 两段回合被切开：增加 `merge_gap_seconds`。
- 固定机位且球场只占画面中间：配置 `roi`，减少观众、场外人员干扰。

## 配置说明

见 `configs/default.yaml`。其中 `roi` 是归一化坐标：

```yaml
roi: [0.0, 0.15, 1.0, 0.95]
```

含义是 `[左, 上, 右, 下]`，数值范围 0 到 1。比如固定机位拍半场时，可以只保留球场主体区域。

## 输出时间线

时间线 JSON 包含：

- `input`：源视频路径
- `duration_seconds`：源视频时长
- `kept_seconds`：最终保留时长
- `segments`：保留片段列表
- `samples`：分析抽样点和分数，可用于可视化调参

## 项目结构

```text
fantasybaby_tennis_cut/
  audio.py      # 音频击球瞬态分析、片段桥接和长尾修剪
  analyzer.py   # 视频抽样和运动特征
  detector.py   # 回合检测
  renderer.py   # 视频片段合成
  cli.py        # 命令行入口
  config.py     # 配置读取
  segments.py   # 片段数据结构和合并裁剪
start_tennis_cut.bat # Windows 交互式启动脚本
start_tennis_cut.sh  # macOS/Linux 交互式启动脚本
```

## 后续升级方向

- 加入网球检测模型：识别球的高速运动轨迹，提升回合边界准确率。
- 加入人体姿态模型：判断发球、准备、捡球、走回底线等状态。
- 加入音频击球点检测：利用清脆击球声辅助分割。
- 增加一个可视化调参 UI：直接拖动阈值并预览时间线。
