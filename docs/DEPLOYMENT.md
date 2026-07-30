# v1.1 部署与迁移

## 全新环境启动

要求 Node.js 22+、Python 3.12+。从仓库根目录执行：

```powershell
npm ci
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
$env:PYTHONPATH="backend"
$env:STORAGE_MODE="sqlite"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

另开终端：

```powershell
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:8000"
npm run dev
```

打开 `http://localhost:3000`，并检查 `http://localhost:8000/health`。

## Demo 与真实 Provider

- `ADAPTER_MODE=demo`：LLM 与关键帧使用确定性 Demo，适合零密钥验收。
- `ADAPTER_MODE=provider`：导演文本使用 `LLM_API_KEY` 或 `OPENAI_API_KEY`；关键帧优先使用 `IMAGE_API_KEY`，否则使用 `OPENAI_API_KEY`。
- 默认图片模型是 `gpt-image-2`，尺寸 `1280x720`、质量 `medium`。
- `/health` 返回导演 adapter 与 `keyframe_provider`、`keyframe_model`、`keyframe_fallback_reason`，用于确认真实调用或回退。

OpenAI 兼容中转站应填写基础地址，而不是把单个端点写入
`LLM_BASE_URL`。例如 4sAPI：

```dotenv
LLM_BASE_URL=https://4sapi.com/v1
LLM_API_STYLE=chat_completions
IMAGE_BASE_URL=https://4sapi.com/v1
```

文本导演会调用 `/chat/completions`；关键帧仍调用专用
`/images/generations`，并兼容中转站返回 URL 或 `b64_json`。

真实密钥只放本地 `.env` 或 Vercel Environment Variables，禁止提交仓库或粘贴到任务聊天。Vercel 安全配置命令：

```powershell
npx vercel env add OPENAI_API_KEY production
npx vercel env add ADAPTER_MODE production
```

命令会在终端中接收隐藏输入。设置后重新部署 API；禁止把密钥写进 `vercel.json`、`.env.example` 或任何 `NEXT_PUBLIC_*` 变量。

## 数据库与迁移

v1.1 T009–T013 没有新增数据库表或列；版本化资产继续保存在既有 `generated_assets.payload` JSON/JSONB 中，因此本版本无待执行 SQL 迁移。生产环境使用 Postgres，Vercel Blob 存放音频、角色参考图和关键帧；SQLite/本地文件仅用于开发和自动测试。

## 剪映小助手成片

关键帧全部成功后，网页“渲染队列”会出现“交给剪映小助手”。ZIP 包包含：

- 原音频与精确裁剪起止时间；
- 10 张关键帧和校验清单；
- `timeline.json` 镜头时间线；
- `剪映小助手提示词.txt`。

在剪映小助手中上传包内素材并粘贴提示词，即可生成 16:9、24fps、1080p 成片。浏览器不能安全绕过桌面应用的本地文件选择器，因此上传和最终消耗剪映额度仍由用户在桌面端确认。

## 发布验收

```powershell
npm test
npm run lint
$env:PYTHONPATH="backend"
$env:STORAGE_MODE="sqlite"
python -m unittest discover -s backend/tests -v
python scripts/secret_scan.py
bandit -q -lll -r backend/app
npm audit --omit=dev --audit-level=high
```

`test_release_e2e_upload_to_jianying_handoff` 自动覆盖上传、真实音频分析、30 秒选段、世界观、角色参考图锁定、故事、镜头编辑、关键帧和剪映交接包，不以手工流程代替主路径测试。
