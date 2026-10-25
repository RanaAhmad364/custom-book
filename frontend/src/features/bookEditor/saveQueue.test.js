import assert from "node:assert/strict";
import test from "node:test";
import { createSaveQueue } from "./saveQueue.js";

test("save queue serializes writes and reuses an in-flight identical save", async () => {
  const queue = createSaveQueue();
  const calls = [];
  let releaseFirst;
  const first = queue("same", async () => {
    calls.push("first-start");
    await new Promise((resolve) => { releaseFirst = resolve; });
    calls.push("first-end");
    return "saved";
  });
  const duplicate = queue("same", async () => {
    calls.push("duplicate");
  });
  const newer = queue("newer", async () => {
    calls.push("newer");
  });

  assert.equal(first, duplicate);
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(calls, ["first-start"]);
  releaseFirst();
  await Promise.all([first, duplicate, newer]);
  assert.deepEqual(calls, ["first-start", "first-end", "newer"]);
});

test("save queue continues after a failed write", async () => {
  const queue = createSaveQueue();
  await assert.rejects(queue("failed", async () => { throw new Error("save failed"); }), /save failed/);
  assert.equal(await queue("next", async () => "saved"), "saved");
});

test("a new editor queue does not wait on the previous project's pending save", async () => {
  const previousProjectQueue = createSaveQueue();
  const nextProjectQueue = createSaveQueue();
  let releasePrevious;
  const previousSave = previousProjectQueue("project-a", () => new Promise((resolve) => {
    releasePrevious = resolve;
  }));
  const nextSave = nextProjectQueue("project-b", async () => "project-b-saved");

  assert.equal(await nextSave, "project-b-saved");
  releasePrevious();
  await previousSave;
});
