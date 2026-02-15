# 飞行雪绒桌面伴侣 ❄️

鸣潮 3.1 共鸣者爱弥斯粉丝向赛博周边

## 用户安装 

1. 在右侧 `Releases` 下载最新 `.dmg`。  
2. 打开并安装应用。  
3. 首次运行时，请按提示开启 macOS 相关权限（如录屏、终端控制等）。

### DeepSeek API Key 🔑

- 建议提前准备一个 DeepSeek API Key（通常少量额度即可体验很久）。  
- 首次使用飞讯，或需要更换 Key：
  - 右键点击飞行雪绒
  - 打开设置窗口输入 Key
  - 自动保存到应用容器配置中

DeepSeek 平台地址：<https://platform.deepseek.com/>

## 开发者安装 

推荐目录结构：

```text
project-root/
├─ resources/   # 多媒体资源
├─ src/         # 代码仓库
└─ release/     # 打包产物（可不手动创建）
```

`release/` 会由 `src/release_macos.sh` 自动更新。

注意代码仓库的控制域：
```bash
git clone https://github.com/CatManJr/FleetSnowfluff src
```

### 环境准备

先在 base 环境安装 `uv`：

```bash
pip install uv
```

然后进入源码目录并运行开发者模式：

```bash
cd src
uv sync
# uv add <package_name>   # 需要新增依赖时再执行
uv run main.py
```

发布版打包器：
下载安装[Inno Setup](https://jrsoftware.org/isdl.php)
安装到默认路径即可。自定义安装请相应修改`src\windows-toolkit\release_windows.ps1`

### 打包发布版

发布版打包：
```bash
cd src
./release_macos.sh       # 获得.app文件和.dmg 安装包
```

### Windows开发者安装
#### FFmpeg 配置

打包脚本需要 ffmpeg 来转换视频容器格式（.mov → .mp4）。请按以下步骤配置：

1. **下载 FFmpeg**
   - 访问：https://www.gyan.dev/ffmpeg/builds/
   - 下载 `ffmpeg-release-essentials.zip`（或 full 版本）

2. **解压到本地**
   - 将压缩包解压到任意位置，例如：`C:\ffmpeg\`
   - 解压后应包含 `bin` 文件夹，其中有 `ffmpeg.exe`

3. **添加到 PATH 环境变量（PowerShell 方式）**
  - 打开 PowerShell（以管理员身份运行）
  - 执行以下命令添加 ffmpeg bin 目录到 PATH(复制绝对路径并替换)：
    ```powershell
    $ffmpegPath = "C:\Program Files (x86)\ffmpeg\bin"
    [Environment]::SetEnvironmentVariable("Path", $env:Path + ";$ffmpegPath", "User")

    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    ```
  - 重启 PowerShell 使更改生效

4. **验证配置**
  - 在 PowerShell 中输入：`ffmpeg -version`
  - 如果显示版本信息，说明配置成功

> **注意**：如果不配置 ffmpeg，脚本会将 .mov 文件直接重命名为 .mp4，可能导致播放卡顿或无法播放。

当前脚本位置：

- `src/windows-toolkit/convert_mov_to_mp4.ps1`
- `src/windows-toolkit/release_windows.ps1`

在 `src/` 目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\windows-toolkit\release_windows.ps1
```

该脚本会自动执行：

1. `uv sync`
2. 清理旧产物
3. 调用 `convert_mov_to_mp4.ps1` 转码
4. 仅打包 `mp4`（会过滤 `mov`）
5. 生成 Windows 安装包（`.exe`）

#### 视频换码+打包两步流程（可选）

先人工确认转码结果，再打包：

```powershell
powershell -ExecutionPolicy Bypass -File .\windows-toolkit\convert_mov_to_mp4.ps1 -Root ..\resources\Call -Recurse
powershell -ExecutionPolicy Bypass -File .\windows-toolkit\release_windows.ps1 -SkipVideoConvert
```

#### 打包输出

- 安装包输出到 `release/`
- 产物名示例：`FleetSnowfluff-v1.0.2-Windows-Installer.exe`
- 当前流程默认只保留安装包（不保留中间 app 目录）

>如需测试聊天功能，同样记得先准备 DeepSeek API Key，并在右键设置里填写。
> ⚠️ ：虽然我尽可能做了容器隔离和uv隔离，但开发环境仍建议您做好备份与隔离防止我的屎山污染您的本地路径。
> ⚠️ ：Qt6 在 MacOS 上会频繁出现环境漂移，常见睡一觉起来“qt.qpa.plugin: Could not find the Qt platform plugin "cocoa" in <Your ENV>” 这里给出一个简单粗暴的解决方法：
```bash
uv cache clean pyside6 pyside6-addons pyside6-essentials shiboken6 && rm -rf ".venv" && uv sync
```

## 功能总览 🎮

### 基本移动 

- 飞行雪绒会在屏幕中飞行或闪现。  
- 左键按住拖动，可以把她“拽”回来。

### 左键菜单 📌

- `打开飞讯`：打开聊天窗口（DeepSeek + 人设JSON 注入）。  
  ⚠️ OOC（出戏）是没有微调的大模型通病，建议先“热身几轮”稳定人设。
- `爱弥斯，变身！`：播放游戏待机动画。  
  素材待优化。
- `电子幽灵登场！`：启动终端。  
  💻 一起敲命令行！看看小爱说了什么吧～
- `召唤雪绒海豹 / 拜拜海豹`：随机生成 1～12 只雪绒海豹。  
  🦭 点击海豹可消除；也可一键清空。
- `你看，又唱`：打开飞行雪绒电台。 仿Apple Music设计 
  🎵 支持导入本地音频，最小化后有悬浮播放条，关闭播放器自动停播。
  ⚠️泪点注意，可能第一首刷到《远航星的告别》
- `拜拜`：退出应用。  
  👋 下次再见。

### 右键菜单 ⚙️

- `设置窗口`：当前用于配置 DeepSeek API Key。

## 功能演示 🎥

<details>
<summary>点击展开视频（如果您的平台支持）</summary>

[![Demo Video 封面](https://img.shields.io/badge/点击此处播放演示视频-blue?logo=playstation)](https://github.com/CatManJr/FleetSnowfluff/blob/main/demo/demov0.1.4.mp4)

如果页面无法直接播放，可手动复制链接后用本地播放器打开：  
https://github.com/CatManJr/FleetSnowfluff/blob/main/demo/demov0.1.4.mp4
</details>

## 开发日志
2-11-2026（UTC-5）：测试版锐意完善中。  
可能提供 English Version（虽然我也不知道有什么意义）  
Windows 版待开发，或请您安装开发者版本后自行封包  
2-12-2026（UTC-5）：优化飞行雪绒电台UI及交互设计，v0.1.5beta release  
2-12-2026（UTC-5）：播片堆料完成。可切换DeepSeek通用对话/推理模式。优化飞行雪绒电台功能和交互设计。v1.0.2正式版发布。
2-13-2026（UTC-5）：v1.1.0尝试加入番茄钟+备忘录。Windows版测试中。
2-14-2026（UTC-5）：更新番茄钟功能。优化跨平台、不同分辨率下的字体和窗口尺寸显示问题。 更新Windows-toolkit。