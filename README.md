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

- `POST /project/create`
- `POST /audio/upload`
- `POST /audio/analyze`
- `POST /world/create`
- `POST /character/create`
- `POST /story/create`
- `POST /shots/create`
- `POST /render/start`

开发设计与验收说明见 `docs/plans/2026-07-29-ai-emotion-director-design.md`。

后续 Codex 接手时，请先阅读 `CODEX_HANDOFF.md`，其中记录了当前边界、验证方式和 v1.1 推荐开发顺序。
