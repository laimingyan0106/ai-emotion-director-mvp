# Codex 接手说明

## 项目目标

AI 情绪导演把一首歌曲转换成可执行的 30 秒 MV 导演方案，包括音乐情绪分析、World Bible、Character Asset、三幕故事、Shot Card、视频 Prompt 与渲染任务。

当前私有演示站：

https://ai-emotion-director-0729.nonkxybee.chatgpt.site

## 当前实现

- 前端：Next.js 16、TypeScript、Tailwind CSS、vinext。
- 后端：FastAPI。
- 数据库：PostgreSQL。
- 媒体分析：FFmpeg/ffprobe。
- AI 接口：`DirectorAdapter` 抽象及确定性 `DemoDirectorAdapter`。
- 页面：导演台、世界观、角色资产、故事板、镜头时间线、渲染队列。
- 输出：10 个三秒镜头，总时长 30 秒；可导出完整 JSON 方案。
- Git 历史按原手册保留 T001–T010 开发记录。

## 验证命令

```powershell
npm install
npm test
npm run lint
```

后端纯领域测试：

```powershell
$env:PYTHONPATH="$PWD\backend"
python -m unittest discover -s backend\tests -v
```

完整本地服务：

```powershell
docker compose up --build
```

## 当前边界

- 托管站使用 Demo Adapter，不会把上传的歌曲发送到第三方模型。
- 前端的“视频渲染”是任务队列演示，不会产生真实视频文件。
- FastAPI/PostgreSQL 后端已经实现手册 API，但托管站尚未连接独立部署的 FastAPI 服务。
- 没有提交任何 API 密钥；真实模型凭据必须通过运行环境注入。
- 情绪曲线目前是确定性 MVP 数据，尚未接入 librosa 或真实音频特征模型。

## 建议的 v1.1 开发顺序

1. 把 FastAPI 部署为独立服务，并让前端通过 `NEXT_PUBLIC_API_BASE_URL` 调用真实接口。
2. 完成项目列表、项目详情、自动保存及历史版本恢复。
3. 使用 FFmpeg + librosa 提取节拍、段落、响度、频谱与情绪特征。
4. 实现真实 LLM Adapter，并为 World、Character、Story、Shots 增加结构化输出校验与重试。
5. 增加角色参考图生成、参考图锁定和跨镜头一致性字段。
6. 实现真实图像/视频 Adapter、异步任务队列、失败重试、进度回调与成片拼接。
7. 增加 Shot Card 编辑、镜头拖拽排序、时长调整及总时长校验。
8. 增加端到端测试：上传 → 分析 → 生成 → 编辑 → 渲染 → 导出。

## 给下一次 Codex 的建议提示词

```text
请先阅读 README.md、CODEX_HANDOFF.md、docs/plans/2026-07-29-ai-emotion-director-design.md，
检查当前代码、Git 历史和测试，然后：
1. 评审 MVP 的架构、产品体验、安全性和可维护性；
2. 列出阻塞真实用户使用的问题并按 P0/P1/P2 排序；
3. 给出 v1.1 的可测试开发计划；
4. 在我确认后从第一项开始实现，不要重写已经工作的 MVP。
```
