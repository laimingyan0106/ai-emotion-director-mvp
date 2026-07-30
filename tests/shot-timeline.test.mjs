import assert from "node:assert/strict";
import test from "node:test";

import {
  recomputeShotStarts,
  reduceShotTimeline,
} from "../lib/shot-timeline.ts";

const fixture = [
  { id: "S01", duration: 10, time: "", action: "one" },
  { id: "S02", duration: 10, time: "", action: "two" },
  { id: "S03", duration: 10, time: "", action: "three" },
];

test("timeline reducer reorders and recomputes millisecond starts", () => {
  const result = reduceShotTimeline(fixture, {
    type: "reorder",
    dragId: "S03",
    targetId: "S01",
  });
  assert.deepEqual(result.map((shot) => shot.id), ["S03", "S01", "S02"]);
  assert.deepEqual(result.map((shot) => shot.start_ms), [0, 10000, 20000]);
});

test("timeline reducer updates, inserts, and deletes without mutating input", () => {
  const updated = reduceShotTimeline(fixture, {
    type: "update",
    index: 1,
    changes: { action: "edited" },
  });
  assert.equal(updated[1].action, "edited");
  assert.equal(fixture[1].action, "two");

  const split = reduceShotTimeline(updated, {
    type: "update",
    index: 0,
    changes: { duration: 5 },
  });
  const inserted = reduceShotTimeline(split, {
    type: "insert",
    index: 1,
    shot: { id: "S04", duration: 5, time: "", action: "new" },
  });
  assert.equal(inserted.reduce((sum, shot) => sum + shot.duration, 0), 30);
  const deleted = reduceShotTimeline(inserted, { type: "delete", index: 1 });
  assert.equal(deleted.reduce((sum, shot) => sum + shot.duration, 0), 30);
  assert.deepEqual(recomputeShotStarts(deleted).map((shot) => shot.start_ms), [0, 5000, 20000]);
});
