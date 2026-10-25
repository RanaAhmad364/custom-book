import assert from "node:assert/strict";
import test from "node:test";
import { projectService } from "./projectService.js";

test("project creation preserves a server-copied published template design", async () => {
  const projectId = "60b49d00-220e-4ab3-99c8-14b81dcdd602";
  const templateId = "3f775b70-2bf6-4527-8d21-a5656cb1ba04";
  const productId = "a61e5288-2f31-4434-a70c-2e57e13b3133";
  const owner = "copy-user@example.test";
  const document = {
    schemaVersion: 1,
    metadata: { id: projectId, owner, title: "My copy", updatedAt: "2026-10-22T12:00:00Z" },
    book: { pageCount: 1, size: { width: 10, height: 10 }, template: { id: templateId, title: "Master" } },
    pageOrder: ["cover-page", "interior-page"],
    pages: [
      { id: "cover-page", type: "cover", label: "Cover", elements: [] },
      {
        id: "interior-page",
        type: "page",
        label: "Page 1",
        elements: [{
          id: "master-heading",
          type: "text",
          text: "Master page content",
          x: 0.1,
          y: 0.1,
          width: 0.8,
          height: 0.12,
        }],
      },
    ],
    assets: [],
    styles: {},
    cover: { pageId: "cover-page" },
  };
  const requests = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    const data = options.method === "POST"
      ? { project: { id: projectId, title: "My copy", status: "draft", pageCount: 1, version: 1, document } }
      : { project: { id: projectId, title: "My copy", status: "draft", pageCount: 1, version: 2, document: JSON.parse(options.body).document } };
    return {
      ok: true,
      status: options.method === "POST" ? 201 : 200,
      headers: { get: () => options.method === "POST" ? '"1"' : '"2"' },
      json: async () => data,
    };
  };
  try {
    const created = await projectService.createProject(owner, {
      title: "My copy",
      pageCount: 1,
      template: { id: productId, designTemplateId: templateId, title: "Master" },
      book: { id: productId },
    });

    assert.equal(created.document.pages[1].elements[0].text, "Master page content");
    assert.equal(JSON.parse(requests[0].options.body).productId, productId);
    assert.equal(JSON.parse(requests[0].options.body).templateId, templateId);
    assert.equal(requests.length, 2);
    assert.equal(requests[1].options.method, "PATCH");
    assert.equal(JSON.parse(requests[1].options.body).document.pages[1].elements[0].text, "Master page content");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("stale saves keep the local recovery copy and require a freshly loaded version", async () => {
  const projectId = "6a8a10b3-5572-4a58-a779-1d067d9a2adf";
  const owner = "save-recovery@example.test";
  const originalDocument = {
    schemaVersion: 1,
    metadata: { id: projectId, owner, title: "Recovery test", updatedAt: "2026-10-24T12:00:00Z" },
    book: { pageCount: 1 },
    pageOrder: ["page-one"],
    pages: [{ id: "page-one", type: "page", elements: [{ id: "text-one", type: "text", text: "Before" }] }],
    assets: [],
  };
  const recoveryDocument = structuredClone(originalDocument);
  recoveryDocument.metadata.updatedAt = "2026-10-24T12:01:00Z";
  recoveryDocument.pages[0].elements[0].text = "Unsaved text";
  const requests = [];
  const values = new Map();
  const previousFetch = globalThis.fetch;
  const previousStorage = globalThis.localStorage;
  globalThis.localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    if (options.method === "PATCH" && requests.filter((item) => item.options.method === "PATCH").length === 1) {
      return {
        ok: false,
        status: 409,
        headers: { get: () => null },
        json: async () => ({ error: { message: "This project changed on another session." } }),
      };
    }
    const saved = options.method === "PATCH" ? JSON.parse(options.body).document : originalDocument;
    const version = options.method === "PATCH"
      ? 7
      : requests.filter((item) => item.options.method !== "PATCH").length === 1 ? 5 : 6;
    return {
      ok: true,
      status: 200,
      headers: { get: () => `"${version}"` },
      json: async () => ({
        project: {
          id: projectId,
          title: "Recovery test",
          status: "draft",
          version,
          pageCount: 1,
          document: saved,
        },
      }),
    };
  };

  try {
    await projectService.getProject(owner, projectId);
    projectService.saveRecovery(owner, projectId, recoveryDocument);
    await assert.rejects(projectService.saveDocument(owner, projectId, recoveryDocument), /changed on another session/);
    const localRecovery = projectService.getRecovery(owner, projectId);
    assert.equal(localRecovery.pages[0].elements[0].text, "Unsaved text");

    await projectService.getProject(owner, projectId);
    const saved = await projectService.saveDocument(owner, projectId, recoveryDocument);
    assert.equal(saved.version, 7);
    const writes = requests.filter((request) => request.options.method === "PATCH");
    assert.deepEqual(writes.map((request) => request.options.headers["If-Match"]), ['"5"', '"6"']);
  } finally {
    globalThis.fetch = previousFetch;
    if (previousStorage === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = previousStorage;
  }
});
