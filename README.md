# AI Knowledge Hub

公众号、论文与 GitHub Radar 的统一静态网站入口。

## 发布目录

| 路径 | 内容 | 当前状态 |
| --- | --- | --- |
| `docs/index.html` | 统一导航首页 | 已接入 |
| `docs/gzh/index.html` | 公众号 AI 库 | 已接入 |
| `docs/papers/` | 论文库 | 预留，尚未接入 |
| `docs/radar/` | GitHub Radar | 预留，尚未接入 |

GitHub Pages 从 `main` 分支的 `/docs` 目录发布。站内链接使用相对路径，兼容项目站点子路径。

## 更新公众号站点

本地仓库置于 `data_out/ai_knowledge_hub/` 时，运行 `python3 scripts/sync_gzh.py`，将相邻项目生成的 `gzh_ai/site/index.html` 同步至 `docs/gzh/index.html`。提交并推送后，GitHub Pages 自动更新。

源目录位置不同时，可通过 `--source /path/to/site/index.html` 指定 HTML。脚本只复制该 HTML，不会复制采集数据、登录凭证、日志或管线状态。

论文库和 Radar 接入前应核对全部静态依赖及原文/PDF链接，再同步到各自子目录；不要只复制首页导致详情页丢失。

每日增量采集仍由各本地项目负责，GitHub Pages 托管现有静态产物。

## 发布操作

运行 `python3 scripts/publish_github.py` 提交并上传发布目录，再启用 GitHub Pages；运行 `python3 scripts/publish_github.py --status` 查看部署状态。授权优先从本机 `~/.config/github-pages/token` 读取；该文件不存在时使用进程环境，Token 不进入仓库。

## 访问地址

- 统一入口：https://lijiat.github.io/ai-knowledge-hub/
- 公众号 AI 库：https://lijiat.github.io/ai-knowledge-hub/gzh/
