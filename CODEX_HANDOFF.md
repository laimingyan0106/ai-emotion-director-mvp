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

### V11-T003：项目列表、详情与持久化恢复

- 状态：完成
- 生产数据库：Vercel Marketplace Neon PostgreSQL（新加坡区域，免费方案）
- 生产媒体存储：私有 Vercel Blob（香港区域）
- 数据库迁移：应用启动时以幂等 DDL 创建 `projects`、`audio_assets`、`generated_assets`、`render_jobs`；外键使用 `ON DELETE CASCADE`。
- API 变更：
  - 新增 `GET /projects`
  - 新增 `GET /projects/{project_id}`
  - 新增 `PATCH /projects/{project_id}`
  - 新增 `DELETE /projects/{project_id}`
  - 保留 `GET /project/{project_id}` 兼容 T002 链路
  - `GET /health` 新增 `media_storage`
- 前端变更：
  - 新增云端项目列表、最近更新时间和音频摘要
  - 支持按 `project_id` 打开项目
  - 项目名称 700ms 防抖自动保存
  - 删除前二次确认，删除后清理当前 URL 与页面状态
- 验证结果：
  - `npm test`：PASS（2/2）
  - `npm run lint`：PASS
  - `python -m unittest discover -s backend/tests -v`：PASS（5/5）
  - 真实 Neon + Blob：创建两个项目、上传音频、改名、列表、详情回读、删除 PASS
  - 生产 API：`storage=postgres`、`durable_storage=true`、`media_storage=vercel_blob`
  - 生产 API：创建两个项目、PATCH 改名、GET 列表、独立 GET 回读、DELETE 清理 PASS
- 安全与清理：
  - 本地媒体路径执行存储根目录边界校验，禁止目录穿越
  - 删除项目时级联清理数据库关联记录和媒体对象
  - Blob 与数据库凭据仅由 Vercel 环境注入，未提交到仓库
- 已知限制：生产音频上传仍受 Vercel Function 请求体限制；大文件直传将在后续音频管线任务中处理。
- 下一任务：`V11-T004`，实现资产版本管理、唯一激活版本和回滚依赖警告。

### V11-T004：资产版本管理与激活/回滚

- 状态：完成
- 数据库迁移：
  - `generated_assets` 新增 `status`、`is_active`、`parent_asset_id`、`provider`、`model`、`prompt`、`input_snapshot`、`validation_errors`、`updated_at`
  - 新增 `(project_id, kind, version)` 唯一索引
  - 新增 `(project_id, kind) WHERE is_active` 部分唯一索引，数据库层保证同类资产至多一个激活版本
  - PostgreSQL 使用事务级 advisory lock，SQLite 使用 `BEGIN IMMEDIATE`，并发生成时版本号仍连续且唯一
- 版本行为：
  - 成功生成先写入 draft，再在同一事务内归档旧版本并激活新版本
  - 失败生成保留为 failed 版本，不替换当前激活版本
  - 新版本通过 `parent_asset_id` 保留同类版本谱系，通过 `input_snapshot` 固化上游激活资产 ID 与版本
  - 项目上下文只读取 `is_active=true` 的资产，禁止用 `created_at` 覆盖同类资产
- API 变更：
  - 新增 `GET /projects/{project_id}/assets`
  - 新增 `POST /projects/{project_id}/assets/{kind}/activate`
  - World、Character、Story、Shots 和 audio_analysis 响应增加 `asset_id`、`version`、`status`、`is_active`
  - 回滚后返回下游依赖不匹配警告；failed 版本禁止激活
- 验证结果：
  - 后端 7/7 测试 PASS
  - 6 线程并发创建同类资产，版本号 1–6 连续唯一且仅一个激活版本
  - 回滚后 Character 上游 World 依赖警告 PASS
  - failed 版本不替换激活版本且激活请求返回 409
  - `npm test`、`npm run lint`、Python compileall PASS
- 下一任务：`V11-T005`，实现 World、Character、Story、Shots 严格 Schema 校验、结构化错误与自动重试。

### V11-T005：结构化输出 Schema、校验与重试

- 状态：完成
- 新增严格领域模型：`WorldAsset`、`CharacterAsset`、`StoryAsset`、`ShotSetAsset`
  - 全部模型禁止额外字段并限制字符串、列表、ID、色值、时长、FPS 与画幅
  - Shot ID 必须唯一，时间线必须连续，镜头时长之和必须等于 ShotSet 声明时长
  - ShotSet 总时长必须等于项目 `target_duration`
  - 镜头的 `character_ids` 必须引用当前激活 Character 中真实存在的角色
- 新增结构化生成服务：
  - 支持 JSON 字符串或对象输出
  - 首次解析或 Schema 校验失败后调用 Adapter `repair` 自动修复重试
  - `GENERATION_RETRY_ATTEMPTS` 可配置，默认重试 1 次，最大 3 次
  - 每次错误记录 attempt、location、type、message，不静默吞错
  - 重试成功时错误历史写入新激活版本；最终失败时保留 last payload 为 failed 版本
  - 最终失败返回 422 和结构化 `validation_errors`，旧激活版本保持不变
- Demo Shots 增加显式 `character_ids=["CHAR-001"]`，进入与真实 LLM 相同的引用校验链路。
- 验证结果：
  - 后端 13/13 测试 PASS
  - 畸形 JSON 自动修复一次后成功 PASS
  - retry=0 时立即失败且错误可见 PASS
  - 总时长不等于目标时长被拒绝 PASS
  - 不存在的角色引用被拒绝 PASS
  - extra 字段被拒绝 PASS
  - API 最终失败写入 failed 版本且不污染旧激活版本 PASS
- 下一任务：`V11-T006`，实现 FFmpeg/librosa 真实音频特征分析并保留 Demo fallback。

### V11-T006：真实音频特征分析管线

- 状态：完成
- 音频分析：
  - 使用 librosa 提取 duration、BPM、beats、onsets、RMS、spectral centroid、chroma
  - 生成 100 点归一化 `energy_curve`，识别静音段与最多 8 个能量峰值候选
  - 输出 `source_sha256`、`analysis_version=librosa-v1` 与处理耗时，固定音频结果可重复
  - MP3/M4A 等压缩格式优先使用系统 FFmpeg；缺失时使用 `imageio-ffmpeg` 的托管二进制解码
  - 不把能量与频谱信号描述为心理学意义的情绪判断，`primary_emotion` 明确写为未进行该类识别
- 执行与降级：
  - Blob 私有音频通过鉴权读取后写入请求级临时目录分析
  - DSP 在工作线程执行，`AUDIO_ANALYSIS_TIMEOUT_SECONDS` 默认 45 秒
  - 最多分析 `AUDIO_ANALYSIS_MAX_SECONDS`（默认 600 秒），超长音频标记 `truncated`
  - 缺少解码器、读取失败、解析失败或超时均返回 `degraded=true` 和 `degraded_reason`
  - 分析结果同时缓存到 `audio_assets.analysis` 并写入版本化 `audio_analysis`；重复请求返回同一激活版本
- 验证结果：
  - 后端 16/16 测试 PASS
  - 220Hz 稳态与 880Hz 脉冲固定夹具的哈希、频谱质心、能量曲线明显不同
  - 同一夹具重复分析除处理耗时外结果逐字段一致
  - 无 FFmpeg 的压缩音频降级原因可见
  - API 重复分析命中缓存且 asset_id/version 不变
  - 热态完整后端测试约 4 秒；首次 librosa/Numba 初始化与两首夹具分析小于 30 秒
- 下一任务：`V11-T007`，实现 30 秒片段推荐、用户确认与后续上下文锁定。

### V11-T007：30 秒片段推荐与确认

- 状态：完成
- 推荐策略：
  - 高潮候选：目标窗口平均能量最高
  - 叙事转折候选：首尾变化与窗口动态最大
  - 平稳候选：窗口能量方差最低
  - 每个候选返回 start、end、duration、score 与可解释 reason
- 确认与版本：
  - 新增 `GET /projects/{project_id}/segments/recommendations`
  - 新增 `POST /projects/{project_id}/segments/confirm`
  - 服务端强制 `end-start == target_duration`，并校验 0 到音频总长边界
  - 用户确认结果保存为版本化 `segment` 资产，切换片段不覆盖旧版本
  - World/Character/Story/Shots 在没有确认片段时返回 409
  - 下游生成的 `input_snapshot` 自动记录 segment asset_id/version
  - 切换片段后资产 API 与确认响应返回需要重新生成的下游依赖警告
- 上下文：
  - 后续生成只收到确认区间内的 energy curve、beats、onsets 和 peaks
  - 片段内时间统一换算为相对 0–30 秒，同时保留 source_duration 与 source_time
  - 不再把整首歌固定曲线直接传给导演生成
- 前端：
  - 音频分析完成后展示真实能量曲线和选区
  - 展示三类推荐卡，支持分别拖动“片段起点”和“片段终点”
  - 两个手柄保持固定 30 秒，当前起止值实时可见
  - 用户必须点击“确认这个 30 秒片段”，服务端校验成功后才进入导演页面
- 验证结果：
  - 后端 18/18 测试 PASS
  - 推荐三分类、任意合法 30 秒区间、短音频、越界与错误时长测试 PASS
  - 生成资产记录 segment 版本 PASS
  - 切换片段后 World 依赖失效警告 PASS
  - 生成上下文只保留确认片段曲线 PASS
  - Next/Vinext 构建、TypeScript 与 ESLint PASS
- 下一任务：`V11-T008`，实现真实 Director LLM Adapter、结构化输出与 Demo 自动降级。
