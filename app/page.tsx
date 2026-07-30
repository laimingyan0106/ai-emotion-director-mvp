"use client";

import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  AssetVersion,
  analyzeAudio,
  checkHealth,
  confirmSegment,
  createProject,
  createWorld,
  deleteProject,
  fetchProject,
  fetchProjects,
  fetchAssetVersions,
  fetchSegmentRecommendations,
  getApiMode,
  ProjectSnapshot,
  SegmentCandidate,
  updateProject,
  updateWorld,
  uploadAudio,
} from "../lib/api-client";

type Stage = "idle" | "analyzing" | "selecting" | "ready" | "rendering";
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

function EmotionCurve({
  values = curve,
  duration = 30,
  selection,
}: {
  values?: number[];
  duration?: number;
  selection?: { start: number; end: number } | null;
}) {
  const normalized = values.length
    ? values.map((value) => value <= 1 ? value * 100 : value)
    : curve;
  const points = normalized
    .map((value, index) => `${(index / Math.max(normalized.length - 1, 1)) * 100},${100 - value}`)
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
        {selection && duration > 0 && (
          <rect
            x={(selection.start / duration) * 100}
            width={((selection.end - selection.start) / duration) * 100}
            y="0"
            height="100"
            fill="#f0c36a"
            opacity=".12"
          />
        )}
        <polyline points={points} fill="none" stroke="#f0c36a" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="curve-labels">
        <span>00:00</span>
        <span>{selection ? `已选 ${selection.start.toFixed(1)}–${selection.end.toFixed(1)}s` : "等待选择片段"}</span>
        <span>{duration.toFixed(1)}s</span>
      </div>
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
  const [projects, setProjects] = useState<ProjectSnapshot[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(getApiMode() === "real");
  const [savingProject, setSavingProject] = useState(false);
  const [segmentOptions, setSegmentOptions] = useState<SegmentCandidate[]>([]);
  const [segmentStart, setSegmentStart] = useState(0);
  const [segmentEnd, setSegmentEnd] = useState(30);
  const [segmentCategory, setSegmentCategory] = useState<SegmentCandidate["category"] | "custom">("custom");
  const [segmentLabel, setSegmentLabel] = useState("自定义片段");
  const [audioDuration, setAudioDuration] = useState(30);
  const [energyCurve, setEnergyCurve] = useState<number[]>(curve);
  const [segmentBusy, setSegmentBusy] = useState(false);
  const [segmentConfirmed, setSegmentConfirmed] = useState(false);
  const [worldAsset, setWorldAsset] = useState<AssetVersion | null>(null);
  const [worldNameDraft, setWorldNameDraft] = useState("");
  const [worldStyleDraft, setWorldStyleDraft] = useState("");
  const [worldWeatherDraft, setWorldWeatherDraft] = useState("");
  const [worldLockedFields, setWorldLockedFields] = useState<string[]>([]);
  const [worldBusy, setWorldBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const lastSavedName = useRef(projectName);

  useEffect(() => {
    if (getApiMode() === "demo") return;
    const projectId = new URLSearchParams(window.location.search).get("project_id");
    const connect = async () => {
      try {
        const projectList = await fetchProjects();
        setProjects(projectList.items);
        if (projectId) {
          const project = await fetchProject(projectId);
          lastSavedName.current = project.name;
          setProjectName(project.name);
          setApiProjectId(project.id);
          setRemoteAudio(project.audio);
          if (project.audio) {
            await restoreProjectSegment(project.id);
          }
        } else {
          await checkHealth();
        }
        setConnection("real");
        setApiError("");
      } catch (error) {
        setConnection("error");
        setApiError(error instanceof ApiError ? error.message : "导演 API 暂时不可用。");
      } finally {
        setProjectsLoading(false);
      }
    };
    void connect();
    // Initial deep-link restoration intentionally runs once for the URL at mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!apiProjectId || projectName === lastSavedName.current || getApiMode() === "demo") return;
    const timer = window.setTimeout(async () => {
      setSavingProject(true);
      try {
        const updated = await updateProject(apiProjectId, { name: projectName });
        lastSavedName.current = updated.name;
        setProjects((current) => current.map((item) => item.id === updated.id ? updated : item));
        setApiError("");
      } catch (error) {
        setApiError(error instanceof ApiError ? error.message : "项目自动保存失败。");
      } finally {
        setSavingProject(false);
      }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [apiProjectId, projectName]);

  const completedStage = Math.min(stages.length, Math.floor((progress / 100) * stages.length));
  const statusText = stage === "idle" ? "等待素材" : stage === "analyzing" ? `音频分析中 ${progress}%` : stage === "selecting" ? "等待确认 30 秒片段" : stage === "rendering" ? "渲染中" : "方案已生成";
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
    setSegmentOptions([]);
    setSegmentConfirmed(false);
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

  async function restoreProjectSegment(projectId: string) {
    const versions = await fetchAssetVersions(projectId);
    const activeSegment = versions.groups.segment?.find((asset) => asset.is_active);
    const activeAnalysis = versions.groups.audio_analysis?.find((asset) => asset.is_active);
    const activeWorld = versions.groups.world?.find((asset) => asset.is_active) ?? null;
    hydrateWorld(activeWorld);
    if (activeAnalysis) {
      const values = activeAnalysis.payload.energy_curve;
      if (Array.isArray(values)) {
        setEnergyCurve(values.map((value) => Number(value)));
      }
      setAudioDuration(Number(activeAnalysis.payload.duration || 30));
    }
    if (activeSegment) {
      setSegmentStart(Number(activeSegment.payload.start));
      setSegmentEnd(Number(activeSegment.payload.end));
      setSegmentCategory((activeSegment.payload.category as SegmentCandidate["category"] | "custom") || "custom");
      setSegmentLabel(String(activeSegment.payload.label || "已确认片段"));
      setSegmentConfirmed(true);
      setStage("ready");
      setProgress(100);
    } else if (activeAnalysis) {
      const recommendations = await fetchSegmentRecommendations(projectId);
      const preferred = recommendations.candidates[0];
      setSegmentOptions(recommendations.candidates);
      setAudioDuration(recommendations.audio_duration);
      setSegmentStart(preferred.start);
      setSegmentEnd(preferred.end);
      setSegmentCategory(preferred.category);
      setSegmentLabel(preferred.label);
      setSegmentConfirmed(false);
      setStage("selecting");
      setProgress(78);
    } else {
      setSegmentConfirmed(false);
      setStage("idle");
      setProgress(0);
    }
  }

  function hydrateWorld(asset: AssetVersion | null) {
    setWorldAsset(asset);
    const payload = asset?.payload;
    const mutableState = payload?.mutable_state;
    setWorldNameDraft(String(payload?.name || ""));
    setWorldStyleDraft(String(payload?.visual_style || ""));
    setWorldWeatherDraft(
      mutableState && typeof mutableState === "object"
        ? String((mutableState as Record<string, unknown>).weather || "")
        : "",
    );
    setWorldLockedFields(
      Array.isArray(payload?.locked_fields)
        ? payload.locked_fields.map((value) => String(value))
        : [],
    );
  }

  function toggleWorldLock(path: string) {
    setWorldLockedFields((current) =>
      current.includes(path)
        ? current.filter((item) => item !== path)
        : [...current, path],
    );
  }

  async function regenerateWorld() {
    if (!apiProjectId || !segmentConfirmed) {
      showToast("请先完成音频分析并确认 30 秒片段");
      return;
    }
    setWorldBusy(true);
    setApiError("");
    try {
      await createWorld(apiProjectId);
      await restoreProjectSegment(apiProjectId);
      showToast(worldAsset ? "World 已重新生成，锁定字段保持不变" : "World Bible 已生成");
    } catch (error) {
      setApiError(error instanceof ApiError ? error.message : "World 生成失败。");
    } finally {
      setWorldBusy(false);
    }
  }

  async function saveWorldStudio() {
    if (!apiProjectId || !worldAsset) return;
    setWorldBusy(true);
    setApiError("");
    const changes: Record<string, unknown> = {};
    if (!worldLockedFields.includes("name")) changes.name = worldNameDraft;
    if (!worldLockedFields.includes("visual_style")) changes.visual_style = worldStyleDraft;
    if (!worldLockedFields.includes("mutable_state.weather")) {
      changes.mutable_state = { weather: worldWeatherDraft };
    }
    try {
      const result = await updateWorld(apiProjectId, {
        expected_version: worldAsset.version,
        changes,
        locked_fields: worldLockedFields,
      });
      hydrateWorld(result.asset);
      showToast(result.warnings.length
        ? `World v${result.asset.version} 已保存，${result.warnings.length} 个下游资产需重新生成`
        : `World v${result.asset.version} 已保存`);
    } catch (error) {
      setApiError(error instanceof ApiError ? error.message : "World 保存失败。");
    } finally {
      setWorldBusy(false);
    }
  }

  async function openRemoteProject(projectId: string) {
    setApiError("");
    try {
      const project = await fetchProject(projectId);
      lastSavedName.current = project.name;
      setProjectName(project.name);
      setApiProjectId(project.id);
      setRemoteAudio(project.audio);
      setFile(null);
      if (project.audio) {
        await restoreProjectSegment(project.id);
      } else {
        setStage("idle");
        setProgress(0);
      }
      const url = new URL(window.location.href);
      url.searchParams.set("project_id", project.id);
      window.history.replaceState({}, "", url);
      showToast("项目已从云端恢复");
    } catch (error) {
      setApiError(error instanceof ApiError ? error.message : "项目加载失败。");
    }
  }

  async function removeRemoteProject(project: ProjectSnapshot) {
    if (!window.confirm(`确认删除“${project.name}”？关联音频和导演资产也会一并删除。`)) return;
    setApiError("");
    try {
      await deleteProject(project.id);
      setProjects((current) => current.filter((item) => item.id !== project.id));
      if (apiProjectId === project.id) {
        setApiProjectId("");
        setRemoteAudio(null);
        setFile(null);
        setProjectName("未命名导演项目");
        lastSavedName.current = "未命名导演项目";
        setStage("idle");
        setProgress(0);
        setSegmentOptions([]);
        setSegmentConfirmed(false);
        const url = new URL(window.location.href);
        url.searchParams.delete("project_id");
        window.history.replaceState({}, "", url);
      }
      showToast("项目及关联资产已删除");
    } catch (error) {
      setApiError(error instanceof ApiError ? error.message : "项目删除失败。");
    }
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
      setProgress(52);
      setApiProjectId(project.id);
      lastSavedName.current = project.name;
      setRemoteAudio({ filename: uploaded.filename, size_bytes: uploaded.size });
      setConnection("real");
      const saved = await fetchProject(project.id);
      setProjects((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      const url = new URL(window.location.href);
      url.searchParams.set("project_id", project.id);
      window.history.replaceState({}, "", url);
      const analysis = await analyzeAudio(project.id);
      setProgress(74);
      const analysisCurve = analysis.payload.energy_curve;
      if (Array.isArray(analysisCurve)) {
        setEnergyCurve(analysisCurve.map((value) => Number(value)));
      }
      setAudioDuration(Number(analysis.payload.duration || 30));
      const recommendations = await fetchSegmentRecommendations(project.id);
      const preferred = recommendations.candidates[0];
      setSegmentOptions(recommendations.candidates);
      setAudioDuration(recommendations.audio_duration);
      setSegmentStart(preferred.start);
      setSegmentEnd(preferred.end);
      setSegmentCategory(preferred.category);
      setSegmentLabel(preferred.label);
      setSegmentConfirmed(false);
      setStage("selecting");
      setProgress(78);
      showToast("真实音频分析完成，请确认导演使用的 30 秒片段");
    } catch (error) {
      setStage("idle");
      setProgress(0);
      setConnection("error");
      setApiError(error instanceof ApiError ? error.message : "项目上传失败，请稍后重试。");
    }
  }

  function chooseSegment(candidate: SegmentCandidate) {
    setSegmentStart(candidate.start);
    setSegmentEnd(candidate.end);
    setSegmentCategory(candidate.category);
    setSegmentLabel(candidate.label);
    setSegmentConfirmed(false);
  }

  function moveSegmentStart(value: number) {
    const bounded = Math.max(0, Math.min(value, audioDuration - 30));
    setSegmentStart(bounded);
    setSegmentEnd(bounded + 30);
    setSegmentCategory("custom");
    setSegmentLabel("自定义片段");
    setSegmentConfirmed(false);
  }

  function moveSegmentEnd(value: number) {
    const bounded = Math.max(30, Math.min(value, audioDuration));
    setSegmentEnd(bounded);
    setSegmentStart(bounded - 30);
    setSegmentCategory("custom");
    setSegmentLabel("自定义片段");
    setSegmentConfirmed(false);
  }

  async function confirmCurrentSegment() {
    if (!apiProjectId) return;
    setSegmentBusy(true);
    setApiError("");
    try {
      const confirmed = await confirmSegment(apiProjectId, {
        start: Number(segmentStart.toFixed(3)),
        end: Number(segmentEnd.toFixed(3)),
        category: segmentCategory,
        label: segmentLabel,
      });
      setSegmentConfirmed(true);
      setStage("ready");
      setProgress(100);
      showToast(confirmed.warnings.length
        ? `片段已切换，${confirmed.warnings.length} 个下游资产需要重新生成`
        : "30 秒导演片段已确认");
      window.setTimeout(() => setView("world"), 450);
    } catch (error) {
      setApiError(error instanceof ApiError ? error.message : "片段确认失败。");
    } finally {
      setSegmentBusy(false);
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
                  <button className="primary-button" onClick={generate} disabled={stage === "analyzing" || stage === "selecting"}>
                    {stage === "analyzing" ? `分析中 ${progress}%` : stage === "selecting" ? "请先确认片段" : "开始导演"}
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
                {file || remoteAudio ? (
                  <EmotionCurve
                    values={energyCurve}
                    duration={audioDuration}
                    selection={segmentOptions.length || segmentConfirmed ? { start: segmentStart, end: segmentEnd } : null}
                  />
                ) : <div className="empty-curve"><span>等待音频分析</span></div>}
                <div className="mood-line"><span>分析边界</span><strong>{file || remoteAudio ? "音乐结构信号，不作心理诊断" : "—"}</strong></div>
              </section>
            </div>

            {(segmentOptions.length > 0 || segmentConfirmed) && (
              <section className="segment-selector panel" aria-label="30 秒导演片段">
                <div className="section-heading">
                  <div><span>SEGMENT / 03</span><h2>确认导演使用的 30 秒</h2></div>
                  <Badge tone={segmentConfirmed ? "success" : "gold"}>
                    {segmentConfirmed ? "已确认" : "等待确认"}
                  </Badge>
                </div>
                {segmentOptions.length > 0 && (
                  <div className="segment-candidates">
                    {segmentOptions.map((candidate) => (
                      <button
                        key={candidate.category}
                        className={candidate.category === segmentCategory ? "active" : ""}
                        onClick={() => chooseSegment(candidate)}
                      >
                        <strong>{candidate.label}</strong>
                        <span>{candidate.start.toFixed(1)}–{candidate.end.toFixed(1)}s</span>
                        <small>{candidate.reason}</small>
                      </button>
                    ))}
                  </div>
                )}
                <div className="segment-range-grid">
                  <label>
                    <span>片段起点 <strong>{segmentStart.toFixed(1)}s</strong></span>
                    <input
                      aria-label="片段起点"
                      type="range"
                      min="0"
                      max={Math.max(audioDuration - 30, 0)}
                      step="0.1"
                      value={segmentStart}
                      onChange={(event) => moveSegmentStart(Number(event.target.value))}
                    />
                  </label>
                  <label>
                    <span>片段终点 <strong>{segmentEnd.toFixed(1)}s</strong></span>
                    <input
                      aria-label="片段终点"
                      type="range"
                      min="30"
                      max={Math.max(audioDuration, 30)}
                      step="0.1"
                      value={segmentEnd}
                      onChange={(event) => moveSegmentEnd(Number(event.target.value))}
                    />
                  </label>
                </div>
                <div className="segment-confirm-row">
                  <p>固定时长 30.0s · 音频总长 {audioDuration.toFixed(1)}s · 服务端会再次校验边界</p>
                  <button
                    className="primary-button"
                    onClick={() => void confirmCurrentSegment()}
                    disabled={segmentBusy || segmentConfirmed}
                  >
                    {segmentBusy ? "确认中…" : segmentConfirmed ? "片段已确认" : "确认这个 30 秒片段"}
                  </button>
                </div>
              </section>
            )}

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

            {getApiMode() === "real" && (
              <section className="project-library panel" aria-label="云端项目列表">
                <div className="project-library-head">
                  <div className="panel-title">
                    <span>PROJECT LIBRARY</span>
                    <strong>云端导演工程</strong>
                  </div>
                  {apiProjectId && (
                    <label className="project-name-editor">
                      <span>{savingProject ? "自动保存中…" : "项目名称 · 已自动保存"}</span>
                      <input
                        value={projectName}
                        onChange={(event) => setProjectName(event.target.value)}
                        maxLength={120}
                        aria-label="项目名称"
                      />
                    </label>
                  )}
                </div>
                {projectsLoading ? (
                  <p className="project-empty">正在读取云端项目…</p>
                ) : projects.length === 0 ? (
                  <p className="project-empty">还没有云端项目。上传一首歌曲即可创建。</p>
                ) : (
                  <div className="project-list">
                    {projects.map((project) => (
                      <article className={project.id === apiProjectId ? "project-row active" : "project-row"} key={project.id}>
                        <button onClick={() => void openRemoteProject(project.id)}>
                          <strong>{project.name}</strong>
                          <span>{project.audio?.filename || "尚未上传音频"}</span>
                          <small>更新于 {project.updated_at ? new Date(project.updated_at).toLocaleString("zh-CN") : "刚刚"}</small>
                        </button>
                        <button
                          className="project-delete"
                          aria-label={`删除项目 ${project.name}`}
                          onClick={() => void removeRemoteProject(project)}
                        >
                          删除
                        </button>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            )}
          </div>
        )}

        {view === "world" && (
          <div className="page studio-page">
            <PageHeading
              overline={`WORLD BIBLE / 02${worldAsset ? ` · V${worldAsset.version}` : ""}`}
              title={worldNameDraft || "等待生成世界观"}
              subtitle="稳定规则与可变状态分别管理；锁定字段在重新生成时保持不变。"
              ready={isReady}
            />
            {!worldAsset ? (
              <section className="panel world-empty">
                <span>STRUCTURED WORLD</span>
                <h3>从已确认的 30 秒音乐片段生成 World Bible</h3>
                <p>输出世界规则、地理、建筑、科技、材质、摄影系统、视觉禁区和当前环境状态。</p>
                <button className="primary-button" disabled={worldBusy || !segmentConfirmed} onClick={() => void regenerateWorld()}>
                  {worldBusy ? "生成中…" : "生成 World Bible"}
                </button>
              </section>
            ) : (
            <div className="studio-grid">
              <section className="world-hero panel">
                <div className="world-orbit"><span>{worldNameDraft}</span><i /><b /></div>
                <div className="world-copy">
                  <Badge tone="gold">{worldStyleDraft}</Badge>
                  <h3>{String(worldAsset.payload.location || "")}</h3>
                  <p>{String(worldAsset.payload.emotion_theme || "")}</p>
                </div>
              </section>
              <section className="panel world-editor">
                <div className="panel-title"><span>WORLD STUDIO</span><strong>字段编辑与锁定</strong></div>
                {[
                  ["世界名称", "name", worldNameDraft, setWorldNameDraft],
                  ["视觉风格", "visual_style", worldStyleDraft, setWorldStyleDraft],
                  ["当前天气", "mutable_state.weather", worldWeatherDraft, setWorldWeatherDraft],
                ].map(([label, path, value, setter]) => {
                  const locked = worldLockedFields.includes(path as string);
                  return (
                    <label className="world-edit-row" key={path as string}>
                      <span>{label as string}</span>
                      <input
                        aria-label={label as string}
                        value={value as string}
                        disabled={locked || worldBusy}
                        onChange={(event) => (setter as (value: string) => void)(event.target.value)}
                      />
                      <button
                        type="button"
                        className={locked ? "world-lock active" : "world-lock"}
                        aria-pressed={locked}
                        onClick={() => toggleWorldLock(path as string)}
                      >
                        {locked ? "已锁定" : "锁定"}
                      </button>
                    </label>
                  );
                })}
                <div className="world-editor-actions">
                  <button className="primary-button" disabled={worldBusy} onClick={() => void saveWorldStudio()}>
                    {worldBusy ? "处理中…" : "保存为新版本"}
                  </button>
                  <button className="ghost-button" disabled={worldBusy} onClick={() => void regenerateWorld()}>
                    重新生成
                  </button>
                </div>
              </section>
              <section className="panel field-list world-rules">
                <Field label="时代" value={String(worldAsset.payload.era || "")} />
                <Field label="地点" value={String(worldAsset.payload.location || "")} />
                <Field label="文化" value={String(worldAsset.payload.culture || "")} />
                <Field label="当前天气" value={worldWeatherDraft} />
              </section>
              <section className="panel palette-panel">
                <div className="panel-title"><span>VISUAL SYSTEM</span><strong>色彩与灯光</strong></div>
                <div className="swatches">
                  {(Array.isArray(worldAsset.payload.palette) ? worldAsset.payload.palette : []).map((color, index) => (
                    <div key={String(color)}><i style={{ background: String(color) }} /><span>色彩 {index + 1}</span><small>{String(color)}</small></div>
                  ))}
                </div>
                <p>{String(worldAsset.payload.lighting || "")}</p>
              </section>
            </div>
            )}
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
