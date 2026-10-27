import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, apiRequest } from "./apiClient.js";

function withBrowser({ cookie = "", location = {} } = {}) {
  const originalDocument = globalThis.document;
  const originalWindow = globalThis.window;
  globalThis.document = { cookie };
  globalThis.window = {
    location: {
      pathname: "/",
      search: "",
      hash: "",
      assign() {},
      ...location,
    },
  };
  return () => {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
  };
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("sends cookies and the CSRF cookie value on unsafe requests", async () => {
  const restoreBrowser = withBrowser({ cookie: "csrf_access_token=access-csrf" });
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return jsonResponse({ ok: true });
  };

  try {
    for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
      await apiRequest("/test", { method, body: {} });
    }
    for (const { options } of requests) {
      assert.equal(options.credentials, "include");
      assert.equal(options.headers["X-CSRF-TOKEN"], "access-csrf");
    }
  } finally {
    globalThis.fetch = originalFetch;
    restoreBrowser();
  }
});

test("refreshes once after a 401 and retries with credentialed cookie auth", async () => {
  const restoreBrowser = withBrowser({
    cookie: "csrf_access_token=access-csrf; csrf_refresh_token=refresh-csrf",
  });
  const originalFetch = globalThis.fetch;
  const requests = [];
  let resourceAttempts = 0;
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    if (url.endsWith("/auth/refresh")) return jsonResponse({ ok: true });
    resourceAttempts += 1;
    return resourceAttempts === 1
      ? jsonResponse({ error: { message: "expired" } }, 401)
      : jsonResponse({ value: "loaded" });
  };

  try {
    const result = await apiRequest("/projects");
    assert.equal(result.data.value, "loaded");
    assert.equal(resourceAttempts, 2);
    assert.equal(requests.length, 3);
    assert.equal(requests[0].options.credentials, "include");
    assert.equal(requests[0].options.headers["X-CSRF-TOKEN"], "access-csrf");
    assert.equal(requests[1].options.credentials, "include");
    assert.equal(requests[1].options.headers["X-CSRF-TOKEN"], "refresh-csrf");
    assert.equal(requests[2].options.credentials, "include");
  } finally {
    globalThis.fetch = originalFetch;
    restoreBrowser();
  }
});

test("redirects to login with a safe return path when refresh fails", async () => {
  let redirect = "";
  const restoreBrowser = withBrowser({
    cookie: "csrf_refresh_token=refresh-csrf",
    location: {
      pathname: "/admin/books",
      search: "?page=2",
      hash: "#design",
      assign(path) { redirect = path; },
    },
  });
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => url.endsWith("/auth/refresh")
    ? jsonResponse({ error: { message: "expired" } }, 401)
    : jsonResponse({ error: { message: "expired" } }, 401);

  try {
    await assert.rejects(apiRequest("/admin/books"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 401);
      return true;
    });
    const target = new URL(redirect, "http://localhost");
    assert.equal(target.pathname, "/login");
    assert.equal(target.searchParams.get("expired"), "1");
    assert.equal(target.searchParams.get("returnTo"), "/admin/books?page=2#design");
  } finally {
    globalThis.fetch = originalFetch;
    restoreBrowser();
  }
});

test("does not try to refresh a failed login request", async () => {
  const restoreBrowser = withBrowser({ cookie: "csrf_refresh_token=refresh-csrf" });
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url) => {
    requests.push(url);
    return jsonResponse({ error: { message: "Email or password is incorrect." } }, 401);
  };

  try {
    await assert.rejects(
      apiRequest("/auth/login", { method: "POST", body: {} }),
      /Email or password is incorrect/,
    );
    assert.equal(requests.length, 1);
  } finally {
    globalThis.fetch = originalFetch;
    restoreBrowser();
  }
});

test("an unauthenticated session bootstrap does not redirect public routes to login", async () => {
  let redirect = "";
  const restoreBrowser = withBrowser({
    location: {
      pathname: "/",
      assign(path) { redirect = path; },
    },
  });
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url) => {
    requests.push(url);
    return jsonResponse({ error: { message: "Sign in required." } }, 401);
  };

  try {
    await assert.rejects(apiRequest("/auth/me"), /Sign in required/);
    assert.equal(redirect, "");
    assert.deepEqual(requests, ["/api/v1/auth/me"]);
  } finally {
    globalThis.fetch = originalFetch;
    restoreBrowser();
  }
});
