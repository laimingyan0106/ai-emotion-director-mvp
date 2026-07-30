import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the emotion director product", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /AI 情绪导演/);
  assert.match(html, /把一首歌/);
  assert.match(html, /导演生成链路/);
  assert.match(html, /Demo Adapter/);
  assert.doesNotMatch(html, /codex-preview/);
});

test("starter preview has been removed", async () => {
  await assert.rejects(access(new URL("app/_sites-preview", root)));
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("app/page.tsx", root), "utf8"),
    readFile(new URL("app/layout.tsx", root), "utf8"),
    readFile(new URL("package.json", root), "utf8"),
  ]);
  assert.doesNotMatch(page, /SkeletonPreview/);
  assert.doesNotMatch(layout, /Starter Project/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  assert.match(page, /shotCards\.reduce/);
});

test("World Studio exposes structured versioned editing controls", async () => {
  const [page, client] = await Promise.all([
    readFile(new URL("app/page.tsx", root), "utf8"),
    readFile(new URL("lib/api-client.ts", root), "utf8"),
  ]);
  assert.match(page, /WORLD STUDIO/);
  assert.match(page, /保存为新版本/);
  assert.match(page, /mutable_state\.weather/);
  assert.match(page, /重新生成/);
  assert.match(client, /export function updateWorld/);
  assert.match(client, /expected_version/);
});

test("Character Studio exposes reference generation and version locking", async () => {
  const [page, client] = await Promise.all([
    readFile(new URL("app/page.tsx", root), "utf8"),
    readFile(new URL("lib/api-client.ts", root), "utf8"),
  ]);
  assert.match(page, /REFERENCE SET/);
  assert.match(page, /生成三类参考图/);
  assert.match(page, /确认并锁定/);
  assert.match(page, /仅凭文本无法承诺跨镜头人物一致性/);
  assert.match(client, /generateCharacterReferences/);
  assert.match(client, /selectCharacterReferences/);
  assert.match(client, /characterReferenceUrl/);
});

test("Shot Studio exposes server-versioned editing and local regeneration", async () => {
  const [page, client, reducer] = await Promise.all([
    readFile(new URL("app/page.tsx", root), "utf8"),
    readFile(new URL("lib/api-client.ts", root), "utf8"),
    readFile(new URL("lib/shot-timeline.ts", root), "utf8"),
  ]);
  assert.match(page, /draggable/);
  assert.match(page, /onDrop/);
  assert.match(page, /保存新版本/);
  assert.match(page, /局部再生成/);
  assert.match(page, /总时长不匹配，禁止保存和关键帧生成/);
  assert.match(client, /export function updateShots/);
  assert.match(client, /export function regenerateShot/);
  assert.match(reducer, /start_ms/);
  assert.match(reducer, /reduceShotTimeline/);
});

test("Keyframe queue exposes retries, confirmation locks, and traceable exports", async () => {
  const [page, client] = await Promise.all([
    readFile(new URL("app/page.tsx", root), "utf8"),
    readFile(new URL("lib/api-client.ts", root), "utf8"),
  ]);
  assert.match(page, /KEYFRAME QUEUE/);
  assert.match(page, /本阶段只生成关键帧，不生成视频/);
  assert.match(page, /单镜头重试/);
  assert.match(page, /确认关键帧/);
  assert.match(page, /provider task id/);
  assert.match(page, /导出 ZIP/);
  assert.match(client, /export function startKeyframes/);
  assert.match(client, /export function retryKeyframe/);
  assert.match(client, /export function retryFailedKeyframes/);
  assert.match(client, /export function confirmKeyframe/);
  assert.match(client, /export function keyframeExportUrl/);
});
