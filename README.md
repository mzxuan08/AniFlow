# AniFlow

AniFlow 是一个面向个人服务器的番剧订阅与下载管理工具。它从公开的番剧目录和 RSS 中检查更新，按设定的分辨率与字幕规则筛选资源，并使用 `libtorrent` 直接下载到本地媒体库。

> 项目不提供、存储或发布任何媒体内容。请仅在符合所在地法律及资源授权条件的前提下使用。

## 功能

- 搜索季度番剧并建立订阅
- 定时检查 RSS，也可手动立即更新单个订阅
- 筛选 1080p 简体中文资源，优先内嵌/内封、MP4、AVC 和 AAC
- 同一集优先下载更高修正版本（如 `v2`、`v3`）
- 内置 `libtorrent` 下载引擎，支持暂停、续传、限速和并发数设置
- 按番剧和集数整理媒体库
- 内置 DPlayer，支持本地弹幕和播放进度记录
- 本地缓存番剧封面，减少页面等待时间
- 响应式 Web 管理界面，支持浅色、深色和跟随系统

## 运行环境

- Linux（建议 Debian 12 / Ubuntu 22.04 或更新版本）
- Python 3.10+
- `python3-libtorrent`
- 可选：Nginx 或宝塔面板，用于反向代理和访问限制

AniFlow 不需要 FFmpeg，也不会对视频进行转码。浏览器对 MKV、HEVC 等格式的支持取决于客户端；无法直播时可下载文件或使用外部播放器。

## 安装

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-libtorrent

git clone https://github.com/mzxuan08/AniFlow.git
cd aniflow
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install .
mkdir -p data downloads
```

前台启动：

```bash
ANIFLOW_DATA_DIR="$PWD/data" \
ANIFLOW_DOWNLOAD_DIR="$PWD/downloads" \
.venv/bin/uvicorn aniflow.app:app --host 127.0.0.1 --port 8765
```

浏览器打开 `http://127.0.0.1:8765`。如需加载 `.env`，可先复制示例文件，再使用 Uvicorn 的 `--env-file` 参数：

```bash
cp .env.example .env
.venv/bin/uvicorn aniflow.app:app --env-file .env --host 127.0.0.1 --port 8765
```

## 配置

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `ANIFLOW_DATA_DIR` | `./data` | SQLite 数据库、种子状态和封面缓存 |
| `ANIFLOW_DOWNLOAD_DIR` | `./downloads` | 视频下载目录 |

下载并发数、限速、磁盘保留空间和下载目录也可在 Web 界面的“设置”页修改。

## 部署

`deploy/aniflow.service` 是 systemd 示例服务，使用前请根据实际安装路径修改 `WorkingDirectory`、`Environment` 和 `ExecStart`。

```bash
sudo cp deploy/aniflow.service /etc/systemd/system/aniflow.service
sudo systemctl daemon-reload
sudo systemctl enable --now aniflow
sudo systemctl status aniflow
```

Nginx 可参考 `deploy/nginx.conf.example`。BT 连接默认使用 TCP/UDP `6881`，需在服务器防火墙放行。

## 安全说明

AniFlow 默认不带身份验证，可操作下载任务和本地文件。请不要把 Uvicorn 端口直接暴露到公网。公网部署应在 Nginx/宝塔层开启 HTTPS，并添加 Basic Auth、IP 白名单或 VPN 限制。更多内容见 [SECURITY.md](SECURITY.md)。

## 开发

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

项目结构：

```text
aniflow/              应用代码、模板和静态资源
tests/                单元测试与 Web 回归测试
deploy/               systemd 和 Nginx 部署示例
.github/              GitHub Actions 与 Issue 模板
```

## 数据源与第三方软件

AniFlow 目前使用 Mikan Project 的公开番剧页面和 Classic RSS。本项目与数据源站点没有隶属或合作关系。页面结构或访问规则变化时，目录和 RSS 功能可能需要同步调整。

内置播放器使用 DPlayer 1.27.1。第三方软件的许可信息见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 许可证

本项目使用 [MIT License](LICENSE)。
