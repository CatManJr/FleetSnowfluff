# 飞行雪绒桌面伴侣 ❄️

鸣潮 3.1 共鸣者爱弥斯粉丝向赛博周边

## 用户安装 

1. 在右侧 `Releases` 下载最新 `.dmg`。  
2. 进行以下操作（作者没钱开Apple Developer ID）：  
	a.终端中运行
  ```bash
  xattr -dr com.apple.quarantine "/Applications/Fleet Snowfluff.app"
  ```
  b.双击打开安装包 
4. 首次运行时，请按提示开启 macOS 相关权限（如录屏、终端控制等）。

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

> ⚠️ ：Qt6 在 MacOS 上会频繁出现环境漂移，常见睡一觉起来“qt.qpa.plugin: Could not find the Qt platform plugin "cocoa" in <Your ENV>” 这里给出一个简单粗暴的解决方法：


### 打包发布版

发布版打包：
```bash
cd src
./release_macos.sh       # 获得.app文件和.dmg 安装包
```

Windows发布版打包器：
下载安装[Inno Setup](https://jrsoftware.org/isdl.php)
安装到默认路径即可。自定义安装请相应修改`src\windows-toolkit\release_windows.ps1`

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

```bash
uv cache clean pyside6 pyside6-addons pyside6-essentials shiboken6 && rm -rf ".venv" && uv sync
```

## 功能总览 🎮

### 基本操作 

- 飞行雪绒会在屏幕中飞行或闪现。  
- 左键按住拖动，可以把她“拽”回来。
- 所有动画播片都可以使用 `esc`快进（重要！）

### 左键菜单/MacOS 顶部托盘 📌

- `打开飞讯`：打开聊天窗口（DeepSeek + 人设JSON 注入）。支持修改回答内容和编辑聊天记录。  
  ⚠️ OOC（出戏）是没有微调的大模型通病，建议先“热身几轮”让模型获得更多聊天样例稳定人设。  
  点击通话模式进入伴随模式（番茄钟）。小爱通讯语音提醒包括：
  - 一段接听
  - 两段随机开始专注
  - 三段随机开始休息
  - 一段完成全部轮次提醒
  - 一段挂断
  - 专注模式伴随画面
- `爱弥斯，变身！`：播放游戏待机动画。
- `电子幽灵登场！`：启动终端。  
  💻 一起敲命令行！看看小爱说了什么吧～
- `浮游星海`
  - `召唤雪绒海豹` / `拜拜海豹`：随机生成 1～12 只雪绒海豹。  
  🦭 点击海豹可消除；也可通过`拜拜海豹`一键清空。
  - `隐藏飞行雪绒`/ `回来吧飞行雪绒`：全局隐藏或显示飞行雪绒
- `你看，又唱`：打开飞行雪绒电台。 仿Apple Music设计，支持导入本地音频，最小化后有悬浮播放条，关闭播放器自动停播，与`通话模式`不冲突，但可能线程卡顿。
  ⚠️内置歌单含《远航星的告别》
- `拜拜`：退出应用。  
  👋 下次再见。
- 番茄钟运行时可从托盘菜单看到当前进度。

### 右键菜单 ⚙️

- `设置窗口`：
  - 用于配置 DeepSeek API Key。
  - 开启DeepSeek-Reasoner
  - 调整‘飞行’速度
  - 调整DeepSeek 能读取的对话长度

## 功能演示 🎥
录制中，将上传视频平台

## 开发日志
- 2-11-2026（UTC-5）：测试版锐意完善中。可能提供 English Version（虽然我也不知道有什么意义）。Windows 版待开发，或请您安装开发者版本后自行封包 
- 2-12-2026（UTC-5）：优化飞行雪绒电台UI及交互设计，v0.1.5beta release   
- 2-12-2026（UTC-5）：播片堆料完成。可切换DeepSeek通用对话/推理模式。优化飞行雪绒电台功能和交互设计。v1.0.2正式版发布。  
- 2-13-2026（UTC-5）：v1.1.0尝试加入番茄钟+备忘录。Windows版测试中。  
- 2-14-2026（UTC-5）：更新番茄钟功能。优化跨平台、不同分辨率下的字体和窗口尺寸显示问题。 更新Windows-toolkit（打包工具）。
- 2-15-2026（UTC-5）：MacOS 1.1.1 版本，增加刘海屏旁状态栏菜单，支持隐藏/显示飞行雪绒（跳动的GUI）。番茄钟 UI 待优化。
- 2-15-2026（UTC-5）：MacOS 1.1.2 版本，新增两条提醒语音，修复专注模式悬浮窗状态刷新问题。
- 下一步（v1.2.0）：调整通话模式的 UI 设计，现在有点丑。完善陪伴模式功能
