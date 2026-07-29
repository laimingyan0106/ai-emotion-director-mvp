# AI 情绪导演 MVP v1.0 设计

## 目标与验收

用户上传一首歌曲后，系统生成可编辑、可导出的完整 AI 导演方案：音乐情绪分析、World Bible、Character Asset、三幕故事、10 张 Shot Card、视频 Prompt 与 30 秒渲染计划。未配置模型密钥时，Demo Adapter 保证整条链路仍可演示和测试；配置模型后，调用方只替换 Adapter，不改变导演资产结构。

## 架构

- 前端：Next.js 16、TypeScript、Tailwind CSS，采用“电影剪辑台”视觉语言。
- 后端：FastAPI，按手册暴露项目、音频、世界、角色、故事、分镜、渲染接口。
- 数据库：PostgreSQL，保存项目、音频元数据、版本化生成资产与渲染任务。
- 媒体：FFmpeg/ffprobe 读取音频容器信息；媒体文件保存在挂载目录。
- AI：Director Adapter、Image Adapter、Video Adapter 分层。v1 内置确定性 Demo Director Adapter。

## 数据流

1. 创建项目并上传音频。
2. ffprobe 提取媒体信息，情绪分析器生成 BPM、调性、能量、曲线和同步点。
3. World → Character → Story → Shots 按顺序生成，每一步读取前置资产并写入版本记录。
4. Shot Card 包含镜头 ID、时长、景别、摄影机、运动、动作、情绪和 Prompt。
5. Render 创建任务并按 Adapter 路由；Demo 模式展示可验证队列，真实提供商由密钥启用。

## 错误处理

- 上传格式和 200MB 限制在入口校验。
- 缺少项目、音频或前置资产时返回明确的 404/409。
- ffprobe 不可用或解析失败时降级为 Demo 分析，不中断导演方案。
- 外部模型不可用时保留结构化资产并允许重试，不污染上一版本。

## 测试

- 前端生产构建与服务端渲染断言。
- 后端纯领域测试：30 秒情绪信号、世界/角色/故事/10 镜头完整性、总时长与 Prompt。
- 浏览器验收：上传示例 → 生成 → 查看各工作室 → 切换镜头 → 导出 JSON → 创建渲染队列。
