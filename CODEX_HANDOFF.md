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
- 当前本地工作区保留 T001–T010 完整开发记录；公开仓库以验证通过的源码快照发布，并在发布提交中记录本地源提交 SHA。

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

## v1.1 增量开发状态

### V11-T001：建立 v1.1 基线与回归保护

- 状态：完成
- v1.0 公开仓库基线 SHA：`198c56404c5928d2cb75222ca0146668f3098416`
- 新增最小 GitHub Actions CI：推送至 `main` 或创建 Pull Request 时执行前端构建/测试、ESLint 和后端领域测试。
- 验证结果：
  - `npm test`：PASS（2/2）
  - `npm run lint`：PASS
  - `python -m unittest discover -s backend/tests -v`：PASS（2/2）
- 数据库迁移：无
- API 变更：无
- 页面与功能改动：无
- GitHub Actions 验收：前端与后端两个 Job 均已实际运行通过；工作流 Action 已使用当前 v7 主版本，避免旧 Node.js Action 运行时弃用警告。
- 已知风险：当前测试仍仅覆盖 v1.0 的 SSR 与纯领域逻辑，尚未包含数据库和浏览器 E2E。
- 下一任务：`V11-T002`，部署可访问的 FastAPI 服务并通过 `NEXT_PUBLIC_API_BASE_URL` 打通前端；不得删除 Demo Adapter。

### V11-T002：部署可访问的 FastAPI 服务并打通前端

- 状态：完成
- 公开前端：`https://ai-emotion-director-web.vercel.app`
- Sites 版本（工作区登录访问）：`https://ai-emotion-director-0729.nonkxybee.chatgpt.site`
- 公开 FastAPI：`https://ai-emotion-director-api.vercel.app`
- 前端配置：`NEXT_PUBLIC_API_BASE_URL=https://ai-emotion-director-api.vercel.app`
- 新增类型化 API 客户端、健康检查、Real API / Demo / 离线状态提示。
- 真实 API 模式支持创建项目、上传音频，并把 `project_id` 写入网址；刷新后通过 `GET /project/{project_id}` 回读项目与音频摘要。
- 未配置 API 地址时保留完整 Demo Adapter，不需要模型密钥。
- API 变更：
  - 新增 `GET /project/{project_id}`
  - `GET /health` 增加 `storage` 与 `durable_storage`
- 验证结果：
  - `npm test`：PASS（2/2）
  - `npm run lint`：PASS
  - `python -m unittest discover -s backend/tests -v`：PASS（3/3）
  - GitHub Actions：前端、后端 Job 均 PASS
  - 生产 API：创建项目、上传音频、GET 回读 PASS
  - 生产浏览器：Real API 健康状态、选择音频、创建项目、上传音频、网址写入 `project_id`、刷新回读 `API SAVED` 均 PASS
  - 断线提示：实际 CORS 断连时页面显示 `API 离线` 与明确错误信息；补齐 Vercel 域名 CORS 后恢复为 `Real API`
- 当前托管存储：临时 SQLite + `/tmp` 媒体目录。它满足 T002 的联网与刷新回读验收，但不保证跨实例持久化。
- 当前公开前端是由 vinext 生产构建预渲染得到的静态 Vercel 部署；Sites 工作区禁止公开发布，因此 Sites 版本继续保留为登录访问。
- 已知风险：Vercel 实例重启或请求落到其他实例时，临时数据可能不可见；严禁把它视为正式用户数据存储。
- 下一任务：`V11-T003`，接入正式数据库与对象存储，完成项目列表、详情、编辑、删除、自动保存和跨设备持久化。
