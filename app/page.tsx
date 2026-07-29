"use client";

import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  checkHealth,
  createProject,
  fetchProject,
  getApiMode,
  uploadAudio,
} from "../lib/api-client";

type Stage = "idle" | "analyzing" | "ready" | "rendering";
type ConnectionState = "demo" | "checking" | "real" | "error";
type View =
  | "dashboard"
  | "world"
  | "character"
  | "story"
  | "shots"
  | "render";

type Shot = {
  id: string;
  time: string;
  size: string;
  camera: string;
  action: string;
  emotion: string;
  prompt: string;
  color: string;
};

const nav: Array<{ id: View; label: string; mark: string }> = [
  { id: "dashboard", label: "导演台", mark: "01" },
  { id: "world", label: "世界观", mark: "02" },
  { id: "character", label: "角色资产", mark: "03" },
  { id: "story", label: "故事板", mark: "04" },
  { id: "shots", label: "镜头时间线", mark: "05" },
  { id: "render", label: "渲染队列", mark: "06" },
];

const stages = ["音频分析", "情绪曲线", "世界观", "角色", "故事", "分镜", "Prompt"];

const shots: Shot[] = [
  {
    id: "S01",
    time: "00–03s",
    size: "大远景",
    camera: "24mm · 缓慢推进",
    action: "雨幕中的悬浮城首次显形",
    emotion: "孤独 / 预兆",
    prompt: "A floating coastal city emerging through silver rain, lone tram line glowing, cinematic 24mm, slow dolly in, midnight cyan and warm amber, volumetric mist",
    color: "#80d8d0",
  },
  {
    id: "S02",
    time: "03–06s",
    size: "近景",
    camera: "85mm · 手持微颤",
    action: "黎夏睁眼，瞳孔倒映列车灯",
    emotion: "苏醒 / 不安",
    prompt: "Close portrait of a young memory cartographer opening her eyes, train lights reflected in pupils, rain on glass, 85mm shallow depth, subtle handheld motion",
    color: "#e7b56f",
  },
  {
    id: "S03",
    time: "06–09s",
    size: "中景",
    camera: "35mm · 横向跟拍",
    action: "她穿过无人月台追赶末班车",
    emotion: "追寻",
    prompt: "Woman running across an empty elevated station, coat trailing, camera tracks sideways, wet concrete reflections, graphic cyan light, restrained urgency",
    color: "#67a9c5",
  },
  {
    id: "S04",
    time: "09–12s",
    size: "特写",
    camera: "100mm · 静止",
    action: "掌心地图被雨水唤醒",
    emotion: "发现",
    prompt: "Macro close-up of a paper map awakening under raindrops, ink routes glowing amber, tactile fibers, precise cinematic lighting, magical realism",
    color: "#d9c47c",
  },
  {
    id: "S05",
    time: "12–15s",
    size: "全景",
    camera: "28mm · 环绕",
    action: "记忆列车从云层下方驶来",
    emotion: "震撼",
    prompt: "Impossible tram arriving beneath the clouds, camera orbits the platform, enormous scale, silver storm, amber windows, elegant retro-futurism",
    color: "#a7b7bc",
  },
  {
    id: "S06",
    time: "15–18s",
    size: "中近景",
    camera: "50mm · 推近",
    action: "失踪的引路人隔窗出现",
    emotion: "思念 / 怀疑",
    prompt: "A familiar silhouette appears behind a rain-streaked tram window, emotional push-in, face half hidden, cyan shadows and tungsten highlights",
    color: "#c58b6f",
  },
  {
    id: "S07",
    time: "18–21s",
    size: "主观镜头",
    camera: "32mm · 急速前移",
    action: "车门开启，记忆碎片逆流",
    emotion: "失控",
    prompt: "POV entering an impossible train as memory fragments flow backward, accelerated camera, paper photos and water suspended in air, controlled surrealism",
    color: "#9c81a7",
  },
  {
    id: "S08",
    time: "21–24s",
    size: "俯拍",
    camera: "35mm · 垂直下降",
    action: "城市道路拼成她遗忘的名字",
    emotion: "真相",
    prompt: "Top-down city roads rearranging into a forgotten handwritten name, camera descends through rain, architectural choreography, luminous cartography",
    color: "#70b6a7",
  },
  {
    id: "S09",
    time: "24–27s",
    size: "近景",
    camera: "65mm · 慢动作",
    action: "黎夏撕掉地图，选择留下",
    emotion: "释然",
    prompt: "Young woman tears the glowing map in slow motion, calm expression replacing fear, paper sparks dissolve into rain, intimate cinematic portrait",
    color: "#e0a95b",
  },
  {
    id: "S10",
    time: "27–30s",
    size: "大远景",
    camera: "24mm · 拉远升空",
    action: "列车穿过黎明，城市重新落地",
    emotion: "重生",
    prompt: "The memory tram crosses into dawn as the floating city gently returns to the sea, aerial pullback, pale gold horizon, cathartic final frame",
    color: "#f0cf8c",
  },
];

const curve = [14, 18, 27, 38, 34, 48, 62, 58, 76, 88, 72, 91, 68, 54, 47, 62, 44, 31, 24, 18];

function EmotionCurve() {
  const points = curve
    .map((value, index) => `${(index / (curve.length - 1)) * 100},${100 - value}`)
    .join(" ");
  return (
    <div className="curve" aria-label="歌曲情绪强度曲线">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img">
        <defs>
          <linearGradient id="curve-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f0c36a" stopOpacity=".38" />
            <stop offset="100%" stopColor="#f0c36a" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={`0,100 ${points} 100,100`} fill="url(#curve-fill)" />
        <polyline points={points} fill="none" stroke="#f0c36a" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="curve-labels"><span>00:00</span><span>情绪峰值 00:17</span><span>00:30</span></div>
    </div>
  );
}

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export default function Home() {
  const [view, setView] = useState<View>("dashboard");
  const [stage, setStage] = useState<Stage>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [projectName, setProjectName] = useState("雨停之前");
  const [progress, setProgress] = useState(0);
  const [activeShot, setActiveShot] = useState(0);
  const [toast, setToast] = useState("");
  const [dragging, setDragging] = useState(false);
  const [connection, setConnection] = useState<ConnectionState>(() => getApiMode() === "real" ? "checking" : "demo");
  const [apiError, setApiError] = useState("");
  const [apiProjectId, setApiProjectId] = useState("");
  const [remoteAudio, setRemoteAudio] = useState<{ filename: string; size_bytes: number } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (getApiMode() === "demo") return;
    const projectId = new URLSearchParams(window.location.search).get("project_id");
    const connect = async () => {
      try {
        if (projectId) {
          const project = await fetchProject(projectId);
          setProjectName(project.name);
          setApiProjectId(project.id);
          setRemoteAudio(project.audio);
          if (project.audio) {
            setStage("ready");
            setProgress(100);
          }
        } else {
          await checkHealth();
        }
        setConnection("real");
        setApiError("");
      } catch (error) {
        setConnection("error");
        setApiError(error instanceof ApiError ? error.message : "导演 API 暂时不可用。");
      }
    };
    void connect();
  }, []);

  const completedStage = Math.min(stages.length, Math.floor((progress / 100) * stages.length));
  const statusText = stage === "idle" ? "等待素材" : stage === "analyzing" ? `导演处理中 ${progress}%` : stage === "rendering" ? "渲染中" : "方案已生成";
  const chosenShot = shots[activeShot];
  const totalDuration = useMemo(() => shots.length * 3, []);

  function acceptFile(candidate?: File) {
    if (!candidate) return;
    if (!candidate.type.startsWith("audio/") && !candidate.name.match(/\.(mp3|wav|m4a|flac)$/i)) {
      showToast("请选择 MP3、WAV、M4A 或 FLAC 音频");
      return;
    }
    setFile(candidate);
    setRemoteAudio(null);
    setProjectName(candidate.name.replace(/\.[^.]+$/, "") || "未命名项目");
    setStage("idle");
    setProgress(0);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer.files[0]);
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    acceptFile(event.target.files?.[0]);
  }

  function showToast(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(""), 2200);
  }

  function runDemoPipeline() {
    setStage("analyzing");
    setProgress(4);
    const timer = window.setInterval(() => {
      setProgress((current) => {
        const next = Math.min(100, current + 4 + Math.round(Math.random() * 7));
        if (next >= 100) {
          window.clearInterval(timer);
          setStage("ready");
          window.setTimeout(() => setView("world"), 450);
        }
        return next;
      });
    }, 160);
  }

  async function generate() {
    if (!file) {
      showToast("先上传一首歌，或载入示例工程");
      return;
    }
    if (getApiMode() === "demo") {
      runDemoPipeline();
      return;
    }

    setStage("analyzing");
    setProgress(8);
    setApiError("");
    try {
      const project = await createProject(projectName, 30);
      setProgress(42);
      const uploaded = await uploadAudio(project.id, file);
      setProgress(68);
      setApiProjectId(project.id);
      setRemoteAudio({ filename: uploaded.filename, size_bytes: uploaded.size });
      setConnection("real");
      const url = new URL(window.location.href);
      url.searchParams.set("project_id", project.id);
      window.history.replaceState({}, "", url);
      showToast("项目与音频已保存到真实 API");
      runDemoPipeline();
    } catch (error) {
      setStage("idle");
      setProgress(0);
      setConnection("error");
      setApiError(error instanceof ApiError ? error.message : "项目上传失败，请稍后重试。");
    }
  }

  function loadDemo() {
    const demo = new File(["demo"], "雨停之前_demo.wav", { type: "audio/wav" });
    acceptFile(demo);
    showToast("示例歌曲已载入");
  }

  function exportPlan() {
    const payload = {
      project: projectName,
      duration: totalDuration,
      music: { bpm: 112, key: "D minor", arc: "克制 → 失控 → 释然" },
      world: {
        name: "潮汐之上的城",
        era: "近未来 · 记忆工业衰退期",
        location: "漂浮于旧海岸线之上的雨城",
        visualStyle: "诗性复古未来主义",
      },
      character: {
        id: "CHAR-001",
        name: "黎夏",
        role: "记忆地图师",
        growth: "寻找答案 → 接受缺失 → 主动选择当下",
      },
      story: "黎夏追上只在雨夜出现的末班列车，发现自己一直寻找的人是被她主动封存的一段记忆。",
      shots,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${projectName || "director-plan"}-30s-plan.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    showToast("完整导演方案已导出");
  }

  function startRender() {
    setStage("rendering");
    showToast("已创建 10 个镜头渲染任务");
    window.setTimeout(() => setStage("ready"), 2600);
  }

  const isReady = stage === "ready" || stage === "rendering";

  return (
    <main className="app-shell">
      <aside className="rail">
        <div className="brand">
          <span className="brand-mark">ED</span>
          <div><strong>情绪导演</strong><small>EMOTION DIRECTOR</small></div>
        </div>
        <nav aria-label="导演工作区">
          {nav.map((item) => (
            <button
              key={item.id}
              className={view === item.id ? "nav-item active" : "nav-item"}
              onClick={() => setView(item.id)}
            >
              <span>{item.mark}</span>{item.label}
            </button>
          ))}
        </nav>
        <div className="rail-note">
          <span className="pulse" />
          <div>
            <strong>{connection === "real" ? "Real API" : connection === "checking" ? "API 连接中" : connection === "error" ? "API 离线" : "Demo Adapter"}</strong>
            <small>{connection === "real" ? `项目 ${apiProjectId.slice(0, 8) || "待创建"}` : connection === "error" ? "可检查网络后重试" : "无需模型密钥即可运行"}</small>
          </div>
        </div>
        <p className="version">MVP v1.0 · DIRECTOR CORE</p>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="breadcrumb"><span>PROJECT</span><strong>{projectName}</strong></div>
          <div className="top-actions">
            <Badge tone={isReady ? "success" : "neutral"}>{statusText}</Badge>
            <button className="ghost-button" onClick={exportPlan} disabled={!isReady}>导出方案</button>
          </div>
        </header>

        {view === "dashboard" && (
          <div className="page dashboard-page">
            {apiError && <div className="api-error" role="alert">{apiError}</div>}
            <section className="hero">
              <div className="eyebrow"><span>AI DIRECTING SYSTEM</span><i /></div>
              <h1>把一首歌，<br />变成一个<span>可拍摄的世界。</span></h1>
              <p>上传音乐，情绪导演会自动构建情绪曲线、世界观、角色、叙事与 30 秒镜头方案。</p>
            </section>

            <div className="dashboard-grid">
              <section
                className={`upload-card ${dragging ? "dragging" : ""}`}
                onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
              >
                <div className="card-index">SOURCE / 01</div>
                <button className="upload-zone" onClick={() => fileInput.current?.click()}>
                  <span className="record-icon"><i /></span>
                  {file || remoteAudio ? (
                    <>
                      <strong>{file?.name || remoteAudio?.filename}</strong>
                      <small>{((file?.size || remoteAudio?.size_bytes || 0) / 1024 / 1024).toFixed(2)} MB · {remoteAudio ? "API SAVED" : "AUDIO READY"}</small>
                    </>
                  ) : (
                    <>
                      <strong>拖入你的歌曲</strong>
                      <small>MP3 / WAV / M4A / FLAC · 最大 200MB</small>
                    </>
                  )}
                </button>
                <input ref={fileInput} type="file" accept="audio/*,.mp3,.wav,.m4a,.flac" onChange={handleFile} hidden />
                <div className="upload-actions">
                  <button className="text-button" onClick={loadDemo}>载入示例工程</button>
                  <button className="primary-button" onClick={generate} disabled={stage === "analyzing"}>
                    {stage === "analyzing" ? `生成中 ${progress}%` : "开始导演"}
                  </button>
                </div>
              </section>

              <section className="analysis-card">
                <div className="card-index">MUSIC DNA / 02</div>
                <div className="metric-row">
                  <div><small>BPM</small><strong>{file || remoteAudio ? "112" : "—"}</strong></div>
                  <div><small>KEY</small><strong>{file || remoteAudio ? "D min" : "—"}</strong></div>
                  <div><small>ENERGY</small><strong>{file || remoteAudio ? "74%" : "—"}</strong></div>
                </div>
                {file || remoteAudio ? <EmotionCurve /> : <div className="empty-curve"><span>等待音频分析</span></div>}
                <div className="mood-line"><span>主情绪</span><strong>{file || remoteAudio ? "克制的思念" : "—"}</strong></div>
              </section>
            </div>

            <section className="pipeline">
              <div className="section-heading">
                <div><span>DIRECTING PIPELINE</span><h2>导演生成链路</h2></div>
                <strong>{progress}%</strong>
              </div>
              <div className="progress-track"><i style={{ width: `${progress}%` }} /></div>
              <div className="stage-list">
                {stages.map((item, index) => (
                  <div className={index < completedStage ? "stage done" : index === completedStage && stage === "analyzing" ? "stage current" : "stage"} key={item}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{item}</strong>
                    <i>{index < completedStage ? "完成" : index === completedStage && stage === "analyzing" ? "处理中" : "待机"}</i>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {view === "world" && (
          <div className="page studio-page">
            <PageHeading overline="WORLD BIBLE / 02" title="潮汐之上的城" subtitle="每一条视觉决策，都来自同一个可复用的世界规则。" ready={isReady} />
            <div className="studio-grid">
              <section className="world-hero panel">
                <div className="world-orbit"><span>潮汐城</span><i /><b /></div>
                <div className="world-copy">
                  <Badge tone="gold">诗性复古未来主义</Badge>
                  <h3>漂浮在旧海岸线之上，<br />靠人类遗忘维持升力。</h3>
                  <p>雨是记忆回流的物理现象。城市每晚降低高度，只有末班列车能穿过被封存的记忆层。</p>
                </div>
              </section>
              <section className="panel field-list">
                <Field label="时代" value="近未来 · 记忆工业衰退期" />
                <Field label="地点" value="东部旧海岸 · 悬浮雨城" />
                <Field label="文化" value="以纸质地图保存私人记忆" />
                <Field label="情绪母题" value="遗忘不是背叛，而是一种自救" />
              </section>
              <section className="panel palette-panel">
                <div className="panel-title"><span>VISUAL SYSTEM</span><strong>色彩与灯光</strong></div>
                <div className="swatches">
                  {[
                    ["午夜青", "#17373d"],
                    ["雨银", "#8ca4a3"],
                    ["记忆金", "#e4ad59"],
                    ["旧纸白", "#d8d2c2"],
                    ["深海黑", "#071011"],
                  ].map(([name, color]) => <div key={name}><i style={{ background: color }} /><span>{name}</span><small>{color}</small></div>)}
                </div>
                <p>主光为大面积冷青环境光；只有与真实记忆有关的物体允许出现暖金色点光源。</p>
              </section>
            </div>
          </div>
        )}

        {view === "character" && (
          <div className="page studio-page">
            <PageHeading overline="CHARACTER ASSET / 03" title="黎夏 · 记忆地图师" subtitle="角色不是一段描述，而是一套跨镜头保持一致的资产。" ready={isReady} />
            <div className="character-layout">
              <section className="character-portrait panel">
                <div className="portrait-frame">
                  <div className="portrait-silhouette"><i /><b /></div>
                  <span>CHAR-001</span>
                </div>
                <div className="identity">
                  <h3>黎夏</h3><p>27 岁 · 记忆地图师</p>
                  <div><Badge tone="gold">敏锐</Badge><Badge>克制</Badge><Badge>固执</Badge></div>
                </div>
              </section>
              <section className="panel character-spec">
                <div className="panel-title"><span>CONTINUITY LOCK</span><strong>视觉一致性描述</strong></div>
                <p>短黑发，发尾因潮气微卷；灰绿色眼睛；左眉尾有一道浅疤；穿墨绿防水长风衣、米白高领针织衫与磨旧皮靴。随身携带黄铜制图笔和折叠纸地图。</p>
                <div className="spec-grid">
                  <Field label="轮廓" value="窄肩、直线型长风衣、轻微前倾" />
                  <Field label="材质" value="湿润棉布、旧黄铜、纤维纸" />
                  <Field label="禁止漂移" value="发型、眉疤、瞳色、风衣长度" />
                  <Field label="参考提示" value="真实东亚面孔，克制表演，非偶像妆" />
                </div>
              </section>
              <section className="panel growth-panel">
                <div className="panel-title"><span>CHARACTER ARC</span><strong>成长路线</strong></div>
                <div className="arc">
                  <div><span>ACT I</span><strong>寻找答案</strong><p>相信找回记忆就能修复失去。</p></div>
                  <i />
                  <div><span>ACT II</span><strong>直面选择</strong><p>发现遗忘是自己主动做出的决定。</p></div>
                  <i />
                  <div><span>ACT III</span><strong>选择当下</strong><p>不再追赶列车，让城市回到海面。</p></div>
                </div>
              </section>
            </div>
          </div>
        )}

        {view === "story" && (
          <div className="page studio-page">
            <PageHeading overline="STORY BOARD / 04" title="末班记忆列车" subtitle="30 秒三幕式叙事，让音乐情绪峰值与故事转折对齐。" ready={isReady} />
            <section className="story-logline panel">
              <span>LOGLINE</span>
              <h3>一位替别人绘制记忆地图的女孩，追上只在雨夜出现的末班列车，却发现自己寻找多年的人，是被她亲手封存的一段记忆。</h3>
            </section>
            <div className="act-grid">
              <Act number="01" time="00–09s" title="雨城召唤" text="黎夏在无人月台醒来。掌心地图被雨水点亮，远处传来不存在的列车声。" beat="情绪 14% → 38%" />
              <Act number="02" time="09–21s" title="记忆逆流" text="她登上列车，看见失踪的引路人。碎片倒流，真相在音乐峰值前失控涌现。" beat="情绪 38% → 91%" />
              <Act number="03" time="21–30s" title="留下此刻" text="城市道路拼出她遗忘的名字。黎夏撕掉地图，列车驶入黎明，雨终于停止。" beat="情绪 91% → 18%" />
            </div>
            <section className="panel sync-panel">
              <div className="panel-title"><span>MUSIC SYNC</span><strong>音乐叙事同步点</strong></div>
              <div className="sync-track">
                {["0s 冷开场", "9s 第一次抬升", "17s 情绪峰值", "24s 留白", "30s 尾音"].map((item, index) => <div key={item} style={{ left: `${index * 25}%` }}><i /><span>{item}</span></div>)}
              </div>
            </section>
          </div>
        )}

        {view === "shots" && (
          <div className="page studio-page">
            <PageHeading overline="SHOT TIMELINE / 05" title="30 秒 · 10 个镜头" subtitle="镜头语言、人物动作、情绪与生成 Prompt 在同一张 Shot Card 中锁定。" ready={isReady} />
            <section className="timeline-strip">
              {shots.map((shot, index) => (
                <button key={shot.id} className={activeShot === index ? "shot-chip active" : "shot-chip"} onClick={() => setActiveShot(index)}>
                  <i style={{ background: shot.color }} /><span>{shot.id}</span><small>{shot.time}</small>
                </button>
              ))}
            </section>
            <div className="shot-detail">
              <section className="shot-preview panel">
                <div className="frame-lines"><span>{chosenShot.id}</span><i /></div>
                <div className="shot-art" style={{ "--shot-color": chosenShot.color } as React.CSSProperties}>
                  <div className="city-lines" /><div className="tram" />
                </div>
                <div className="timecode">{chosenShot.time} · 24 FPS · 16:9</div>
              </section>
              <section className="shot-card panel">
                <div className="panel-title"><span>SHOT CARD</span><strong>{chosenShot.action}</strong></div>
                <div className="shot-fields">
                  <Field label="景别" value={chosenShot.size} />
                  <Field label="摄影机" value={chosenShot.camera} />
                  <Field label="人物 / 动作" value={chosenShot.action} />
                  <Field label="情绪" value={chosenShot.emotion} />
                </div>
                <div className="prompt-box">
                  <span>VIDEO PROMPT</span><p>{chosenShot.prompt}</p>
                  <button onClick={() => { navigator.clipboard.writeText(chosenShot.prompt); showToast("Prompt 已复制"); }}>复制 Prompt</button>
                </div>
              </section>
            </div>
          </div>
        )}

        {view === "render" && (
          <div className="page studio-page">
            <PageHeading overline="RENDER FLOW / 06" title="渲染调度台" subtitle="Adapter 让图像与视频模型可替换，导演资产保持不变。" ready={isReady} />
            <div className="render-grid">
              <section className="panel render-summary">
                <div className="render-ring"><strong>{stage === "rendering" ? "62" : "100"}<small>%</small></strong><span>{stage === "rendering" ? "RENDERING" : "PLAN READY"}</span></div>
                <div>
                  <h3>{stage === "rendering" ? "正在渲染镜头 S07" : "30 秒方案已就绪"}</h3>
                  <p>10 个镜头 · 720 帧 · 16:9 · 24 FPS</p>
                  <button className="primary-button" onClick={startRender} disabled={!isReady || stage === "rendering"}>开始视频渲染</button>
                </div>
              </section>
              <section className="panel adapter-panel">
                <div className="panel-title"><span>MODEL ADAPTERS</span><strong>模型路由</strong></div>
                {[
                  ["LLM", "Demo Director LLM", "已连接"],
                  ["IMAGE", "Image Adapter", "待配置"],
                  ["VIDEO", "Video Adapter", "待配置"],
                ].map(([type, name, status]) => <div className="adapter-row" key={type}><span>{type}</span><strong>{name}</strong><Badge tone={status === "已连接" ? "success" : "neutral"}>{status}</Badge></div>)}
              </section>
            </div>
            <section className="panel queue-panel">
              <div className="panel-title"><span>RENDER QUEUE</span><strong>镜头任务</strong></div>
              <div className="queue-head"><span>镜头</span><span>内容</span><span>时长</span><span>状态</span></div>
              {shots.map((shot, index) => (
                <div className="queue-row" key={shot.id}>
                  <span>{shot.id}</span><strong>{shot.action}</strong><span>3.0s</span>
                  <Badge tone={stage === "rendering" && index < 6 ? "success" : index === 0 || stage === "ready" ? "neutral" : "gold"}>
                    {stage === "rendering" ? (index < 6 ? "完成" : index === 6 ? "渲染中" : "排队") : "待渲染"}
                  </Badge>
                </div>
              ))}
            </section>
          </div>
        )}
      </section>
      {toast && <div className="toast" role="status">{toast}</div>}
    </main>
  );
}

function PageHeading({ overline, title, subtitle, ready }: { overline: string; title: string; subtitle: string; ready: boolean }) {
  return (
    <header className="page-heading">
      <div><span>{overline}</span><h1>{title}</h1><p>{subtitle}</p></div>
      <Badge tone={ready ? "success" : "gold"}>{ready ? "ASSET LOCKED" : "DEMO PREVIEW"}</Badge>
    </header>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return <div className="field"><span>{label}</span><strong>{value}</strong></div>;
}

function Act({ number, time, title, text, beat }: { number: string; time: string; title: string; text: string; beat: string }) {
  return (
    <section className="act-card panel">
      <div><span>ACT {number}</span><small>{time}</small></div>
      <h3>{title}</h3><p>{text}</p><strong>{beat}</strong>
    </section>
  );
}
