import assert from "node:assert/strict";
import test from "node:test";
import { fetchPrivateImage, isPrivateAssetUrl } from "./privateImageLoader.js";

test("private images wait for Retry-After, refresh the signed URL once, and retry", async () => {
  const calls = [];
  const waits = [];
  let refreshed = 0;
  const results = [
    new Response(null, { status: 429, headers: { "Retry-After": "2" } }),
    new Response("image", { status: 200 }),
  ];
  const result = await fetchPrivateImage("/api/v1/assets/private/old-token", {
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return results.shift();
    },
    refreshSource: async () => {
      refreshed += 1;
      return "/api/v1/assets/private/refreshed-token";
    },
    wait: async (milliseconds) => waits.push(milliseconds),
  });

  assert.deepEqual(waits, [2000]);
  assert.equal(refreshed, 1);
  assert.deepEqual(calls.map((call) => call.url), [
    "/api/v1/assets/private/old-token",
    "/api/v1/assets/private/refreshed-token",
  ]);
  assert.ok(calls.every((call) => call.options.credentials === "include"));
  assert.equal(result.source, "/api/v1/assets/private/refreshed-token");
  assert.equal(await result.blob.text(), "image");
});

test("private image URL detection only matches private asset routes", () => {
  assert.equal(isPrivateAssetUrl("/api/v1/assets/private/token"), true);
  assert.equal(isPrivateAssetUrl("/api/v1/assets/public/token"), false);
  assert.equal(isPrivateAssetUrl(""), false);
});
