# AI 情绪导演 MVP v1.0

上传一首歌，自动生成音乐情绪分析、世界观、角色资产、三幕故事、10 个 Shot Card、视频 Prompt 和 30 秒 MV 渲染计划。

## 快速启动

前端：

```powershell
npm install
npm run dev
```

完整 FastAPI + PostgreSQL + FFmpeg：

```powershell
docker compose up --build
```

- 前端：http://localhost:3000
- API：http://localhost:8000
- API 文档：http://localhost:8000/docs

未配置模型密钥时，系统使用确定性 Demo Adapter，上传到方案导出的前端验收流程仍可完整运行。真实模型通过 `.env` 中的 Adapter 密钥接入。

## 手册 API

- `GET /health`
- `GET /project/{project_id}`
- `GET /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- `DELETE /projects/{project_id}`
- `GET /projects/{project_id}/assets`
- `POST /projects/{project_id}/assets/{kind}/activate`
- `GET /projects/{project_id}/segments/recommendations`
- `POST /projects/{project_id}/segments/confirm`
- `POST /project/create`
- `POST /audio/upload`
- `POST /audio/analyze`
- `POST /world/create`
- `POST /character/create`
- `POST /story/create`
- `POST /shots/create`
- `POST /render/start`

## v1.1 托管连接

- 公开前端：`https://ai-emotion-director-web.vercel.app`
- Sites 版本（工作区登录访问）：`https://ai-emotion-director-0729.nonkxybee.chatgpt.site`
- 公开 FastAPI：`https://ai-emotion-director-api.vercel.app`
- 前端通过 `NEXT_PUBLIC_API_BASE_URL` 选择真实 API；未配置时自动进入完整 Demo 模式。
- 当前托管 API 使用 Neon PostgreSQL 与私有 Vercel Blob；项目、音频元数据和关联资产可跨请求、跨设备恢复。
- 生成资产按项目与类型保留完整版本历史；成功版本原子激活，失败版本仅留档，回滚会返回下游依赖警告。
- World、Character、Story、ShotSet 使用严格 Pydantic 领域模型；畸形输出会按 `GENERATION_RETRY_ATTEMPTS` 自动修复重试，最终失败不会替换激活版本。
- 音频分析使用 librosa 与 FFmpeg 提取节拍、起音、RMS、频谱质心、chroma、能量曲线、静音段和峰值候选；失败会明确标记 `degraded`，不会把这些信号宣称为心理学情绪识别。
- 音频分析后提供高潮、叙事转折、平稳三类 30 秒候选；用户可拖动起止点并显式确认，未确认片段时 World/Character/Story/Shots API 返回 409。
- `ADAPTER_MODE=provider` 且配置 `LLM_API_KEY`/`OPENAI_API_KEY` 时使用 OpenAI Responses API；模型默认 `gpt-5.6-terra` 并可由 `LLM_MODEL` 覆盖。缺少密钥或 Provider 不支持时自动回落完整 Demo，并在 `/health` 的实际 adapter 与 fallback reason 中明确显示。
- 导演台提供云端项目列表、项目详情加载、名称自动保存和带确认的级联删除。
- 当前公开前端由已验证的 vinext 构建产物预渲染为静态 Vercel 部署；源码和 Sites 版本仍保留完整 vinext/Cloudflare Worker 架构。

开发设计与验收说明见 `docs/plans/2026-07-29-ai-emotion-director-design.md`。

后续 Codex 接手时，请先阅读 `CODEX_HANDOFF.md`，其中记录了当前边界、验证方式和 v1.1 推荐开发顺序。
