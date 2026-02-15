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

### 环境准备

先在 base 环境安装 `uv`：

```bash
pip install uv
```

然后进入源码目录并运行：

```bash
cd src
uv sync
# uv add <package_name>   # 需要新增依赖时再执行
uv run main.py
```

同样记得先准备 DeepSeek API Key，并在右键设置里填写。

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
2-14-2026（UTC-5）：更新番茄钟功能。