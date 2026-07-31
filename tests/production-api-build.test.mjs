import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const EXPECTED_PRODUCTION_API =
  "https://ai-emotion-director-api.vercel.app";

async function listFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await listFiles(entryPath)));
    } else {
      files.push(entryPath);
    }
  }

  return files;
}

test("Sites production client contains the real API endpoint", async () => {
  const clientDirectory = path.resolve("dist", "client");
  const files = await listFiles(clientDirectory);
  const scripts = files.filter((file) => file.endsWith(".js"));
  const contents = await Promise.all(
    scripts.map((file) => readFile(file, "utf8")),
  );

  assert.ok(
    contents.some((content) => content.includes(EXPECTED_PRODUCTION_API)),
    "production build must not silently fall back to Demo mode",
  );
});
