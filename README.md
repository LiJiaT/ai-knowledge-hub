# AI Knowledge Hub

公众号、论文与 GitHub Radar 的统一静态网站入口。

## 发布目录

| 路径 | 内容 | 当前状态 |
| --- | --- | --- |
| `docs/index.html` | 统一导航首页 | 已接入 |
| `docs/gzh/index.html` | 公众号 AI 库 | 已接入 |
| `docs/papers/` | 论文库正文和图片 | 已接入；PDF 在同仓库 Releases |
| `docs/radar/index.html` | GitHub Radar | 已接入 |

GitHub Pages 从 `main` 分支的 `/docs` 目录发布。站内链接使用相对路径，兼容项目站点子路径。

## 更新公众号站点

本地仓库置于 `data_out/ai_knowledge_hub/` 时，运行 `python3 scripts/sync_gzh.py`，将相邻项目生成的 `gzh_ai/site/index.html` 同步至 `docs/gzh/index.html`。提交并推送后，GitHub Pages 自动更新。

源目录位置不同时，可通过 `--source /path/to/site/index.html` 指定 HTML。脚本只复制该 HTML，不会复制采集数据、登录凭证、日志或管线状态。

## 更新 GitHub Radar

运行 `python3 scripts/sync_radar.py`，将相邻 `radar_project/radar_standalone/output/index.html` 同步至 `docs/radar/index.html`，再运行发布脚本。可通过 `--source /path/to/index.html` 指定其他产物。

## 更新论文库

现成页面、图片和 PDF 来自相邻 `paper_library_site/`。论文库超过 Pages 的 1 GB 容量限制，网页和图片通过 Pages 发布；PDF 通过同仓库的版本化 Release 分发，页面 PDF 按钮自动指向对应快照资产。

1. `python3 scripts/sync_papers.py` 建立当前入口可达内容的快照，并同步正文和图片；可用 `--source /path/to/site` 指定源目录。
2. `python3 scripts/publish_paper_pdfs.py --background` 上传本次快照的全部 PDF；支持断点续传，`--status` 查看进度。日志和状态保留在本地并排除出 Git。
3. PDF 状态为 `complete` 后运行 `python3 scripts/publish_github.py` 上传网站。发布脚本会阻止 PDF 尚未完成时发布论文页面。

原论文库和翻译流水线仍在本地运行；后续翻译更新完成后重新执行同步流程。只有正文和图片变化、PDF 没变时，会复用已上传的 PDF Release，避免重复上传原文。原始 PDF 保留，发布快照中只改写 PDF 按钮地址。GitHub Releases 的 PDF 通常以下载形式打开。

每日增量采集仍由各本地项目负责，GitHub Pages 托管现有静态产物。

## 发布操作

运行 `python3 scripts/publish_github.py` 提交并上传发布目录，再启用 GitHub Pages；运行 `python3 scripts/publish_github.py --status` 查看部署状态。授权优先从本机 `~/.config/github-pages/token` 读取；该文件不存在时使用进程环境，Token 不进入仓库。

## 访问地址

- 统一入口：https://lijiat.github.io/ai-knowledge-hub/
- 公众号 AI 库：https://lijiat.github.io/ai-knowledge-hub/gzh/

- GitHub Radar：https://lijiat.github.io/ai-knowledge-hub/radar/

- 论文库：https://lijiat.github.io/ai-knowledge-hub/papers/
