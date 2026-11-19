# AI 日报

每天早上 09:00（北京时间）自动抓取近一周的 AI 资讯，去重聚类、按兴趣排序、生成中文摘要，输出一个手机友好的静态站点。

- 站点：`docs/`（GitHub Pages，`main` 分支 `/docs`）
- 定时：GitHub Actions（`0 1 * * *` UTC）
- 兴趣画像与阅读行为：Google Sheet（不落仓库）
- 推送：Bark

## 本地运行

```bash
python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 无 LLM，跑通流程
.venv/bin/python -m src.run --offline --limit 30

# 打开 docs/index.html 预览
```

## 环境变量

| 变量 | 用途 | 必需 |
|---|---|---|
| `LLM_API_KEY` | OpenAI 兼容接口的 key | 建议 |
| `LLM_BASE_URL` | 默认 `https://opencode.ai/inference/openai/v1` | 否 |
| `LLM_MODEL` | 默认 `deepseek-v4.1-flash` | 否 |
| `BARK_KEY` | iOS 推送 | 否 |
| `SITE_URL` | 推送里点开的地址 | 否 |
| `FEEDBACK_POST_URL` | 页面埋点写入地址（公开） | 否 |
| `FEEDBACK_READ_URL` | Actions 读取反馈（含 token，Secret） | 否 |
| `FEEDBACK_WRITE_URL` | Actions 回写画像（含 token，Secret） | 否 |

没有 `LLM_API_KEY` 时会自动降级为「标题 + 原文摘要截断」版本，流程不中断。

## 目录

```
config/          信源、画像默认值、提示词
src/ingest/      RSS 抓取
src/process/     聚类与分类
src/rank/        打分与选稿
src/write/       LLM 摘要（含降级）
src/render/      Jinja2 模板 → docs/
src/publish/     Bark 推送
assets/          CSS / JS（埋点、15 秒判定、反馈）
apps-script/     Google Sheet 后端
```

## 反馈机制

- 列表页：卡片 50% 可见 1 秒记曝光；点卡片进详情页
- 详情页：前台停留 ≥15 秒记 `read_qualified`；离开时补 `read_end`；不足 15 秒记 `bounce`
- 15 秒内的 `bounce` 不计入兴趣，只用于来源质量分
- 👍 / `···` 菜单（少推这类 / 屏蔽来源 / 已读 / 收藏）走 `feedback` 事件

## 部署清单

1. 仓库 Settings → Pages → Source: `Deploy from a branch` → `main` / `/docs`
2. Settings → Secrets and variables → Actions
   - Secrets: `LLM_API_KEY`、`BARK_KEY`、`FEEDBACK_READ_URL`、`FEEDBACK_WRITE_URL`
   - Variables: `SITE_URL`、`FEEDBACK_POST_URL`、`LLM_BASE_URL`、`LLM_MODEL`
3. Google Sheet 按 `apps-script/Code.gs` 顶部注释部署 Web App
