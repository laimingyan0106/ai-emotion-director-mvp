import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const clientUrl = new URL("../lib/api-client.ts", import.meta.url);

test("long-running production requests do not use the default timeout", async () => {
  const source = await readFile(clientUrl, "utf8");

  assert.match(source, /AUDIO_UPLOAD_TIMEOUT_MS = 180_000/);
  assert.match(source, /AUDIO_ANALYSIS_TIMEOUT_MS = 120_000/);
  assert.match(source, /IMAGE_GENERATION_TIMEOUT_MS = 360_000/);
  assert.match(
    source,
    /request\("\/audio\/analyze"[\s\S]*?timeoutMs: AUDIO_ANALYSIS_TIMEOUT_MS/,
  );
  assert.match(
    source,
    /characters\/references\/generate[\s\S]*?timeoutMs: IMAGE_GENERATION_TIMEOUT_MS/,
  );
  assert.match(
    source,
    /keyframes\/start[\s\S]*?timeoutMs: IMAGE_GENERATION_TIMEOUT_MS/,
  );
});

test("timeout failures explain that server work may still complete", async () => {
  const source = await readFile(clientUrl, "utf8");

  assert.match(source, /error\.name === "TimeoutError"/);
  assert.match(source, /任务可能仍在服务端完成/);
  assert.doesNotMatch(source, /AbortSignal\.timeout\(15_000\)/);
});
