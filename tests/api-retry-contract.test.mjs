import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const clientUrl = new URL("../lib/api-client.ts", import.meta.url);

test("safe reads retry one transient network or server failure", async () => {
  const source = await readFile(clientUrl, "utf8");

  assert.match(source, /method === "GET" \|\| method === "HEAD"/);
  assert.match(source, /TRANSIENT_STATUS_CODES = new Set\(\[500, 502, 503, 504\]\)/);
  assert.match(source, /error instanceof ApiError && error\.retryable/);
  assert.match(source, /TRANSIENT_STATUS_CODES\.has\(response\.status\)/);
  assert.match(source, /SAFE_REQUEST_RETRY_DELAY_MS = 500/);
});

test("write requests are not automatically replayed", async () => {
  const source = await readFile(clientUrl, "utf8");

  assert.doesNotMatch(source, /method === "POST"[^\n]*canRetry/);
  assert.doesNotMatch(source, /method === "PATCH"[^\n]*canRetry/);
});
