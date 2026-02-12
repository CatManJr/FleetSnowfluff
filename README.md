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

> ⚠️ 温馨提示：虽然项目做了容器隔离，但开发环境仍建议做好备份与隔离策略。

## 功能总览 🎮

### 基本移动 

- 飞行雪绒会在屏幕中飞行或闪现。  
- 左键按住拖动，可以把她“拽”回来。

### 左键菜单 📌

- `飞讯`：打开聊天窗口（DeepSeek + 人设 JSON 注入）。  
  ⚠️ OOC（出戏）是没有微调的大模型通病，建议先“热身几轮”稳定人设。
- `爱弥斯，变身！`：播放游戏待机动画。  
  素材待优化。
- `电子幽灵登场！`：启动终端。  
  💻 一起敲命令行！看看小爱说了什么吧～
- `召唤雪绒海豹 / 拜拜海豹`：随机生成 1～12 只雪绒海豹。  
  🦭 点击海豹可消除；也可一键清空。
- `你看，又唱`：打开飞行雪绒电台。  
  🎵 支持导入本地音频，最小化后有悬浮迷你播放条，关闭播放器自动停播。
- `拜拜`：退出应用。  
  👋 下次再见。

### 右键菜单 ⚙️

- `设置窗口`：当前用于配置 DeepSeek API Key。

## 功能演示 🎥

[Demo Video](https://github.com/CatManJr/FleetSnowfluff/blob/main/demo/demov0.1.4.mp4)